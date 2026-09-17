# Cookie 转 JSON 小工具

## 功能
- 把每行一个 cookie 字符串的文本文件，转换成带 `id` / `name` / `cookie` 字段的 JSON 数组
- 支持多个文件合并为一个 JSON（id 连续编号）
- 提供前端可视化界面，拖拽即用

## 文件说明
| 文件 | 说明 |
|---|---|
| `index.html` | 前端界面，双击打开即可使用 |
| `cookie_to_json.py` | 命令行转换工具（含合并功能） |
| `credit_stats_scraper.py` | 逐条携带 Cookie 调用积分接口并统计的 Python 工具 |
| `credit_api_config.example.json` | 积分接口配置示例 |
| `积分统计抓取说明.md` | 积分接口检测工具的完整配置、安装和运行说明 |
| `cookies.txt` | 输入示例 1（50 条） |
| `50-1.txt` | 输入示例 2（50 条） |
| `cookies_output.json` | cookies.txt 转换结果 |
| `50-1_output.json` | 50-1.txt 转换结果 |
| `merged_output.json` | 两文件合并结果（100 条） |

## 前端界面用法（推荐）
双击 `index.html`，在浏览器中打开：
1. 点击或拖拽选择多个 `.txt` 文件
2. 点击「转换并合并」
3. 预览结果、搜索过滤、下载 JSON

纯前端运行，数据不上传任何服务器。

网页中的“积分接口检测配置”用于填写并导出接口配置；真实的逐条 Cookie 请求由 `credit_stats_scraper.py` 在本机完成，避免浏览器 CORS 和 Cookie 安全策略导致按钮无响应。

## 命令行用法

### 转换单个文件
```
python cookie_to_json.py convert 输入.txt 输出.json
```

### 合并多个文件（txt 和 json 可混合）
```
python cookie_to_json.py merge 输出.json 文件1.txt 文件2.txt 文件3.json
```

### 旧用法（兼容）
```
python cookie_to_json.py 输入.txt 输出.json
```

不传参数时默认读取 `cookies.txt`，输出到 `cookies_output.json`。

## 输出格式
```json
[
  {
    "id": "0000001",
    "name": "cookie_1",
    "cookie": "aux_sid=xxx; key2=value2; ..."
  },
  {
    "id": "0000002",
    "name": "cookie_2",
    "cookie": "..."
  }
]
```
