#!/usr/bin/env python3
"""Optional local Python API for the browser workbench.

The web page remains usable without this service. Start this file when a
Python process or a persistent SQLite database is preferred.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple
from urllib.parse import urlparse


@dataclass
class ParseResult:
    format: str
    records: List[Dict[str, Any]]
    warnings: List[str]


class DatasetRepository(Protocol):
    """Storage boundary kept replaceable for a future database service."""

    def list(self) -> List[Dict[str, Any]]: ...

    def get(self, dataset_id: str) -> Optional[Dict[str, Any]]: ...

    def save(self, item: Dict[str, Any]) -> Dict[str, Any]: ...

    def delete(self, dataset_id: str) -> None: ...


class SQLiteDatasetRepository:
    """Small SQLite adapter; callers do not depend on SQL details."""

    def __init__(self, path: str = "workbench.sqlite3") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def list(self) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM datasets ORDER BY updated_at DESC"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM datasets WHERE id = ?", (dataset_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def save(self, item: Dict[str, Any]) -> Dict[str, Any]:
        now = item.get("updatedAt") or utc_now()
        normalized = {
            "id": item.get("id") or uuid.uuid4().hex,
            "name": item.get("name") or "未命名",
            "createdAt": item.get("createdAt") or now,
            "updatedAt": now,
            "count": int(item.get("count") or len(item.get("records") or [])),
            "sourceCount": int(item.get("sourceCount") or len(item.get("sources") or [])),
            "settings": item.get("settings") or {},
            "records": item.get("records") or [],
            "sources": item.get("sources") or [],
        }
        payload = json.dumps(normalized, ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO datasets (id, name, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    normalized["id"],
                    normalized["name"],
                    normalized["createdAt"],
                    normalized["updatedAt"],
                    payload,
                ),
            )
        return normalized

    def delete(self, dataset_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def non_empty_lines(text: str) -> Iterable[Tuple[int, str]]:
    for number, raw in enumerate(str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        value = raw.strip()
        if value:
            yield number, value


def parse_as_google(text: str) -> ParseResult:
    records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    extra = 0
    for line_number, line in non_empty_lines(text):
        fields = [part.strip() for part in line.split("----")]
        if len(fields) < 3:
            warnings.append(f"邮箱文件第 {line_number} 行缺少字段：需要 账号----密码----2FA")
            continue
        account, password, two_fa = fields[:3]
        if not account or not password or not two_fa:
            warnings.append(f"邮箱文件第 {line_number} 行存在空字段，已跳过")
            continue
        extra += len(fields) > 3
        records.append({"account": account, "password": password, "twoFa": two_fa, "lineNumber": line_number})
    if extra:
        warnings.insert(0, f"邮箱文件中 {extra} 行包含额外字段，已按需求只输出前三段。")
    return ParseResult("AS 谷歌邮箱", records, warnings)


def parse_as_proxy(text: str) -> ParseResult:
    records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for line_number, line in non_empty_lines(text):
        fields = [part.strip() for part in line.split(":")]
        if len(fields) < 4 or any(not part for part in fields[:4]):
            warnings.append(f"代理文件第 {line_number} 行格式不完整：需要 IP:端口:用户名:密码")
            continue
        records.append({"proxy": line, "lineNumber": line_number})
    return ParseResult("AS 代理", records, warnings)


def convert_as(google_text: str, proxy_text: str) -> Dict[str, Any]:
    google = parse_as_google(google_text)
    proxy = parse_as_proxy(proxy_text)
    count = min(len(google.records), len(proxy.records))
    rows = []
    for index in range(count):
        account = google.records[index]
        proxy_record = proxy.records[index]
        output = "--".join([account["account"], account["password"], account["twoFa"], proxy_record["proxy"]])
        rows.append({**account, **proxy_record, "output": output})
    warnings = [*google.warnings, *proxy.warnings]
    if len(google.records) != len(proxy.records):
        longer = "邮箱文件" if len(google.records) > len(proxy.records) else "代理文件"
        warnings.insert(0, f"{longer}有效行更多，已按较少的一份配对输出。")
    return {
        "rows": rows,
        "warnings": warnings,
        "googleCount": len(google.records),
        "proxyCount": len(proxy.records),
    }


def parse_cookie_text(text: str, filename: str = "") -> ParseResult:
    """Minimal backend parser; the browser keeps its broader format parser."""
    stripped = str(text or "").lstrip("\ufeff").strip()
    if not stripped:
        return ParseResult("空文件", [], ["内容为空"])
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data = None
    if data is not None:
        candidates = data if isinstance(data, list) else data.get("cookies", data.get("records", [])) if isinstance(data, dict) else []
        records = []
        for item in candidates:
            if isinstance(item, str) and "=" in item:
                records.append({"cookie": item.strip()})
            elif isinstance(item, dict):
                cookie = item.get("cookie") or item.get("cookieString")
                if isinstance(cookie, str) and "=" in cookie:
                    records.append({"cookie": cookie.strip()})
        return ParseResult("JSON", records, [] if records else ["JSON 中没有找到可转换的 cookie"])
    if "\t" in stripped:
        rows = list(csv.DictReader(io.StringIO(stripped), delimiter="\t"))
        if rows and any("cookie" in row for row in rows[0]):
            return ParseResult("TSV", [{"cookie": row.get("cookie", "").strip()} for row in rows if row.get("cookie", "").strip()], [])
    lines = [line for _, line in non_empty_lines(stripped) if not line.startswith("#")]
    records = [{"cookie": line.removeprefix("Cookie:").strip()} for line in lines if "=" in line]
    return ParseResult("文本", records, [] if records else [f"{filename or '文件'}中没有识别到 cookie"])


class WorkbenchHandler(BaseHTTPRequestHandler):
    repository: DatasetRepository

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        value = json.loads(raw or "{}")
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return value

    def do_OPTIONS(self) -> None:
        self._send({"ok": True})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send({"ok": True, "service": "workbench-backend"})
        elif path == "/api/datasets":
            self._send({"datasets": self.repository.list()})
        else:
            self._send({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            data = self._read_json()
            if path == "/api/as-convert":
                self._send(convert_as(str(data.get("googleText", "")), str(data.get("proxyText", ""))))
            elif path == "/api/parse":
                result = parse_cookie_text(str(data.get("text", "")), str(data.get("filename", "")))
                self._send(asdict(result))
            elif path == "/api/datasets":
                self._send(self.repository.save(data), HTTPStatus.CREATED)
            else:
                self._send({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except (ValueError, json.JSONDecodeError) as error:
            self._send({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:
        prefix = "/api/datasets/"
        if not self.path.startswith(prefix):
            self._send({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return
        dataset_id = self.path[len(prefix):]
        self.repository.delete(dataset_id)
        self._send({"ok": True})


def run_server(host: str, port: int, database: str) -> None:
    repository = SQLiteDatasetRepository(database)

    def handler(*args: Any, **kwargs: Any) -> None:
        WorkbenchHandler.repository = repository
        WorkbenchHandler(*args, **kwargs)

    server = ThreadingHTTPServer((host, port), handler)
    print(f"工作台 Python 接口已启动：http://{host}:{port}")
    print(f"SQLite 数据库：{Path(database).resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="工作台本地 Python API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--database", default="workbench.sqlite3")
    args = parser.parse_args()
    run_server(args.host, args.port, args.database)


if __name__ == "__main__":
    main()
