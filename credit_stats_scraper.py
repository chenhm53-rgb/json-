"""Cookie 积分接口检测器：逐条携带 Cookie 请求接口并统计积分。"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


# ------------------------- 接口配置 -------------------------
INPUT_JSON = Path("cookies.json")
API_URL = "https://firefly.adobe.io/v1/credits/balance"
API_METHOD = "GET"
POINTS_PATH = ""  # Adobe 返回结构可能因账号/版本不同，留空时按字段名自动识别
EXTRA_HEADERS: dict[str, str] = {"Accept": "application/json"}
BODY_TEMPLATE = ""  # POST 示例：'{"account_id":"{identifier}"}'
REQUEST_DELAY_SECONDS = 0.3
REQUEST_TIMEOUT_SECONDS = 20
RETRIES = 2
OUTPUT_DIR = Path("credit_api_output")
Number = Union[int, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用每条 Cookie 调用积分接口并统计")
    parser.add_argument("--config", type=Path, default=None, help="网页导出的接口配置 JSON")
    parser.add_argument("--input", type=Path, default=INPUT_JSON, help="输入 JSON 文件")
    parser.add_argument("--url", default=API_URL, help="接口 URL，可用 {identifier}")
    parser.add_argument("--method", choices=("GET", "POST"), default=API_METHOD.upper())
    parser.add_argument("--points-path", default=POINTS_PATH, help="返回 JSON 的积分字段路径")
    parser.add_argument("--cookie-field", default="", help="Cookie 字段名，留空自动识别")
    parser.add_argument("--identifier-field", default="", help="标识字段名，留空自动识别")
    parser.add_argument("--headers-json", default="", help="额外请求头 JSON 文件路径")
    parser.add_argument("--body", default=BODY_TEMPLATE, help="POST 请求体模板")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS)
    parser.add_argument("--timeout", type=float, default=REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=RETRIES)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--no-cookie-header", action="store_true", help="不发送 Cookie 请求头")
    args = parser.parse_args()
    if args.config:
        with args.config.open("r", encoding="utf-8-sig") as file:
            config = json.load(file)
        if not isinstance(config, dict):
            raise ValueError("接口配置必须是 JSON 对象")
        for target, source in (("url", "api_url"), ("points_path", "points_path"), ("cookie_field", "cookie_field"), ("identifier_field", "identifier_field"), ("body", "body_template"), ("delay", "delay_seconds"), ("timeout", "timeout_seconds"), ("retries", "retries")):
            if source in config and config[source] not in (None, ""):
                setattr(args, target, config[source])
        if config.get("method"):
            args.method = str(config["method"]).upper()
        args.no_cookie_header = not bool(config.get("send_cookie_header", True))
        args.config_headers = config.get("headers", {})
    else:
        args.config_headers = {}
    try:
        args.delay = max(0.0, float(args.delay))
        args.timeout = max(0.1, float(args.timeout))
        args.retries = max(0, int(args.retries))
    except (TypeError, ValueError) as error:
        raise ValueError("请求间隔、超时和重试次数必须是数字") from error
    return args


def first_value(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"找不到输入文件：{path.resolve()}")
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    if isinstance(data, list):
        values = data
    elif isinstance(data, dict):
        values = next((data[key] for key in ("records", "items", "data", "cookies", "accounts") if isinstance(data.get(key), list)), [data])
    else:
        raise ValueError("JSON 顶层必须是数组或对象")
    records = [item for item in values if isinstance(item, dict)]
    if not records:
        raise ValueError("JSON 中没有找到对象记录")
    return records


def cookie_header_to_text(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"^Cookie\s*:\s*", "", value.strip(), flags=re.I).strip()
    if isinstance(value, dict):
        if value.get("name"):
            return f"{value['name']}={value.get('value', '')}"
        return "; ".join(f"{name}={item}" for name, item in value.items() if item not in (None, ""))
    if isinstance(value, list):
        return "; ".join(f"{item['name']}={item.get('value', '')}" for item in value if isinstance(item, dict) and item.get("name"))
    return ""


def get_cookie(record: dict[str, Any], field: str = "") -> str:
    value = record.get(field) if field else first_value(record, ("cookie", "Cookie", "cookie_string", "cookie_header", "cookieString", "header", "cookies"))
    return cookie_header_to_text(value)


def get_identifier(record: dict[str, Any], index: int, field: str = "") -> str:
    value = record.get(field) if field else first_value(record, ("id", "cookie_id", "account_id", "uid", "username", "email", "name"))
    return str(value) if value not in (None, "") else str(index)


def render_template(template: str, identifier: str, index: int, cookie: str, *, url_encode: bool = True) -> str:
    if url_encode:
        identifier_value = quote(identifier, safe="")
        cookie_value = quote(cookie, safe="")
    else:
        identifier_value = identifier
        cookie_value = cookie
    return (template.replace("{identifier}", identifier_value)
            .replace("{index}", str(index)).replace("{cookie}", cookie_value))


def parse_number(value: Any) -> Optional[Number]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return value
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"\+?(?:\d+(?:\.\d+)?|\.\d+)", text):
        return None
    number = float(text)
    return int(number) if number.is_integer() else number


def json_path_get(data: Any, path: str) -> Any:
    current = data
    for part in filter(None, path.split(".")):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def auto_points(data: Any, path: str = "", depth: int = 0) -> list[tuple[Number, str]]:
    if depth > 3 or not isinstance(data, (dict, list)):
        return []
    found: list[tuple[Number, str]] = []
    items = data.items() if isinstance(data, dict) else enumerate(data)
    for key, value in items:
        current_path = f"{path}.{key}" if path else str(key)
        if re.search(r"credit|point|balance|quota|amount|积分|额度|余额|点数", current_path, re.I) and not re.search(r"used|total|date|time|id|token|expire|过期", current_path, re.I):
            number = parse_number(value)
            if number is not None:
                found.append((number, current_path))
        found.extend(auto_points(value, current_path, depth + 1))
    return found


def extract_points(data: Any, path: str) -> tuple[Optional[Number], str]:
    if path:
        value = parse_number(json_path_get(data, path))
        if value is not None:
            return value, path
        raise ValueError(f"返回 JSON 找不到数字字段：{path}")
    found = auto_points(data)
    if not found:
        raise ValueError("返回 JSON 中没有识别到积分字段，请填写 POINTS_PATH")
    return found[0]


def load_headers(path: str, config_headers: Any = None) -> dict[str, str]:
    headers = {str(key): str(value) for key, value in EXTRA_HEADERS.items()}
    if isinstance(config_headers, dict):
        headers.update({str(key): str(value) for key, value in config_headers.items()})
    if path:
        with Path(path).open("r", encoding="utf-8-sig") as file:
            extra = json.load(file)
        if not isinstance(extra, dict):
            raise ValueError("额外请求头文件必须是 JSON 对象")
        headers.update({str(key): str(value) for key, value in extra.items()})
    return headers


def safe_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, URLError):
        return f"网络错误：{error.reason}"
    return str(error).replace("\n", " ").strip()[:300] or error.__class__.__name__


def request_one(url: str, method: str, headers: dict[str, str], body: str, timeout: float) -> tuple[int, Any]:
    request = Request(url, data=body.encode("utf-8") if body else None, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8-sig", errors="replace")
        status = int(response.status)
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"接口返回不是 JSON：{raw[:120]}") from error


def check_record(record: dict[str, Any], index: int, args: argparse.Namespace, base_headers: dict[str, str]) -> dict[str, Any]:
    cookie = get_cookie(record, args.cookie_field)
    identifier = get_identifier(record, index, args.identifier_field)
    result: dict[str, Any] = {"index": index, "identifier": identifier, "status": "failed", "points": None, "points_field": "", "http_status": None, "error": ""}
    if not cookie:
        result["error"] = "记录中没有找到 Cookie 字段"
        return result
    # URL 和 POST 请求体都支持使用当前记录的 Cookie；Cookie 请求头仍是默认方式。
    url = render_template(args.url, identifier, index, cookie)
    headers = dict(base_headers)
    if not args.no_cookie_header:
        headers["Cookie"] = cookie
    body = render_template(args.body, identifier, index, cookie, url_encode=False) if args.method == "POST" else ""
    if body:
        headers.setdefault("Content-Type", "application/json")
    for attempt in range(max(0, args.retries) + 1):
        try:
            status, payload = request_one(url, args.method, headers, body, args.timeout)
            result["http_status"] = status
            points, field = extract_points(payload, args.points_path)
            result.update(status="success", points=points, points_field=field)
            return result
        except Exception as error:
            result["error"] = safe_error(error)
            if attempt < max(0, args.retries):
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
    return result


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    points = [row["points"] for row in results if row["status"] == "success" and row["points"] is not None]
    counts = Counter(points)
    return {"total_cookies": len(results), "success_count": len(points), "failed_count": len(results) - len(points), "minimum_points": min(points) if points else None, "maximum_points": max(points) if points else None, "average_points": statistics.mean(points) if points else None, "groups": [{"points": value, "count": counts[value]} for value in sorted(counts, key=float)]}


def format_number(value: Any) -> str:
    if value is None:
        return "无"
    return f"{int(value):,}" if float(value).is_integer() else f"{float(value):,.2f}"


def print_summary(summary: dict[str, Any]) -> None:
    print("\n积分接口统计结果\n" + "=" * 48)
    print(f"总记录数：{summary['total_cookies']}\n接口成功：{summary['success_count']}\n接口失败：{summary['failed_count']}")
    print(f"最低积分：{format_number(summary['minimum_points'])}\n最高积分：{format_number(summary['maximum_points'])}\n平均积分：{format_number(summary['average_points'])}")
    print("\n按积分从低到高\n积分\t数量\n" + "-" * 24)
    for group in summary["groups"]:
        print(f"{format_number(group['points'])}\t{group['count']}")


def main() -> int:
    try:
        args = parse_args()
    except Exception as error:
        print(f"读取配置失败：{safe_error(error)}")
        return 1
    try:
        records = load_json_records(args.input)
        headers = load_headers(args.headers_json, args.config_headers)
    except Exception as error:
        print(f"准备失败：{safe_error(error)}")
        return 1
    args.method = args.method.upper()
    if args.method not in {"GET", "POST"}:
        print("准备失败：请求方式只能是 GET 或 POST")
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        print(f"正在检测 {index}/{len(records)} ...", end=" ", flush=True)
        result = check_record(record, index, args, headers)
        results.append(result)
        print(f"成功，积分：{format_number(result['points'])}" if result["status"] == "success" else f"失败，{result['error']}")
        if index < len(records) and args.delay > 0:
            time.sleep(args.delay)
    summary = build_summary(results)
    fields = ["index", "identifier", "status", "points", "points_field", "http_status", "error"]
    write_json(args.output_dir / "接口检测明细.json", results)
    write_csv(args.output_dir / "接口检测明细.csv", results, fields)
    write_json(args.output_dir / "积分接口汇总.json", summary)
    write_csv(args.output_dir / "积分接口汇总.csv", summary["groups"], ["points", "count"])
    print_summary(summary)
    print(f"\n结果文件已保存到：{args.output_dir.resolve()}")
    return 0 if summary["success_count"] else 2


if __name__ == "__main__":
    sys.exit(main())
