"""收银王 Cookie 失效恢复的本机安全代理。

浏览器只提交邮箱和并发数到本机代理。上游 API Key 通过环境变量读取，
上游返回的 cookie 字段会在代理层被过滤，浏览器只收到邮箱、状态和说明。
"""

from __future__ import annotations

import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HOST = os.getenv("SHOUYINWANG_PROXY_HOST", "127.0.0.1")
PORT = int(os.getenv("SHOUYINWANG_PROXY_PORT", "8787"))
UPSTREAM_URL = os.getenv(
    "SHOUYINWANG_UPSTREAM_URL",
    "http://167.160.91.234:17081/api/v1/email-pool/revive-api",
)
API_KEY = os.getenv("SHOUYINWANG_API_KEY", "").strip()
AUTH_MODE = os.getenv("SHOUYINWANG_AUTH_MODE", "x-api-key").strip().lower()
ALLOW_INSECURE_UPSTREAM = os.getenv("SHOUYINWANG_ALLOW_HTTP", "0").strip().lower() in {"1", "true", "yes"}
PAGE_PATH = Path(__file__).with_name("shouyinwang_recovery.html")
FALLBACK_PAGE_PATH = Path(__file__).with_name("收银王_cookie失效恢复.html")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def clean_emails(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("emails 必须是数组")
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        email = str(item).strip()
        key = email.lower()
        if not EMAIL_RE.fullmatch(email):
            raise ValueError(f"邮箱格式不正确：{email[:80]}")
        if key not in seen:
            seen.add(key)
            output.append(email)
    if not output:
        raise ValueError("emails 不能为空")
    if len(output) > 20:
        raise ValueError("单批最多提交 20 个邮箱")
    return output


def sanitize_response(payload: Any) -> dict[str, Any]:
    """只保留状态字段，永不把上游 cookie 返回给浏览器。"""
    if not isinstance(payload, dict):
        raise ValueError("上游响应不是 JSON 对象")
    raw_results = payload.get("results")
    results: list[dict[str, Any]] = []
    if isinstance(raw_results, list):
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "email": str(item.get("email", "")),
                    "ok": item.get("ok") is True,
                    "message": str(item.get("message", "")),
                }
            )
    return {
        "status": str(payload.get("status", "ok")),
        "total": int(payload.get("total", len(results)) or 0),
        "success": int(payload.get("success", sum(item["ok"] for item in results)) or 0),
        "failed": int(payload.get("failed", sum(not item["ok"] for item in results)) or 0),
        "results": results,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ShouyinwangRecoveryProxy/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # 不记录邮箱、请求体、API Key 或上游响应内容。
        print(f"[{self.log_date_time_string()}] {format % args}")

    def send_json(self, status: int, payload: Any) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8787")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/favicon.ico", "/.well-known/appspecific/com.chrome.devtools.json"}:
            # Chrome 会自动探测这些可选资源；没有业务内容时返回 204，避免终端显示无意义的 404。
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path == "/health":
            self.send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "收银王 Cookie 失效恢复本机代理",
                    "api_key_configured": bool(API_KEY),
                    "upstream_allowed": not UPSTREAM_URL.startswith("http://") or ALLOW_INSECURE_UPSTREAM,
                },
            )
            return
        if self.path in {"/", "/shouyinwang_recovery.html", "/收银王_cookie失效恢复.html"}:
            try:
                page_path = PAGE_PATH if PAGE_PATH.exists() else FALLBACK_PAGE_PATH
                body = page_path.read_bytes()
            except OSError:
                self.send_json(HTTPStatus.NOT_FOUND, {"message": "找不到 HTML 页面"})
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"message": "路径不存在"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/revive":
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "路径不存在"})
            return
        if not API_KEY:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"message": "本机代理未配置 SHOUYINWANG_API_KEY"})
            return
        if UPSTREAM_URL.startswith("http://") and not ALLOW_INSECURE_UPSTREAM:
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"message": "上游接口使用 HTTP，默认已阻止发送 API Key；确认网络可信后设置 SHOUYINWANG_ALLOW_HTTP=1"},
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 64 * 1024:
                raise ValueError("请求体过大")
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8"))
            emails = clean_emails(body.get("emails") if isinstance(body, dict) else None)
            concurrency = int(body.get("concurrency", 5)) if isinstance(body, dict) else 5
            concurrency = min(10, max(1, concurrency))
            upstream_payload = {"emails": emails, "concurrency": concurrency}
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if AUTH_MODE == "authorization":
                headers["Authorization"] = f"Bearer {API_KEY}"
            else:
                headers["x-api-key"] = API_KEY
            request = Request(
                UPSTREAM_URL,
                data=json_bytes(upstream_payload),
                headers=headers,
                method="POST",
            )
            with urlopen(request, timeout=330) as response:
                upstream = json.loads(response.read().decode("utf-8-sig"))
            self.send_json(HTTPStatus.OK, sanitize_response(upstream))
        except HTTPError as error:
            self.send_json(int(error.code), {"status": "error", "message": f"上游接口返回 HTTP {error.code}"})
        except URLError as error:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"status": "error", "message": f"无法连接上游接口：{error.reason}"})
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "message": str(error)})
        except Exception:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"status": "error", "message": "代理处理失败，请查看本机终端日志"})


def main() -> None:
    if not API_KEY:
        print("警告：未设置 SHOUYINWANG_API_KEY，恢复请求会返回 503。")
    if UPSTREAM_URL.startswith("http://"):
        if ALLOW_INSECURE_UPSTREAM:
            print("警告：已显式允许通过 HTTP 发送 API Key，请确认网络为可信内网。")
        else:
            print("已阻止 HTTP 上游请求；如确认网络可信，设置 SHOUYINWANG_ALLOW_HTTP=1 后重启。")
    print(f"收银王 Cookie 失效恢复功能：http://{HOST}:{PORT}/")
    print("按 Ctrl+C 停止本机代理。")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
