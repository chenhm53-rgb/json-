# 收银王 Cookie 失效恢复功能

这是独立于 Cookie JSON 工作台的批量邮箱恢复页面。

## 运行

把这三个文件放在同一目录：

- `shouyinwang_recovery.html`
- `shouyinwang_recovery_proxy.py`
- `SHOUYINWANG_README.md`

macOS / Linux：

```bash
export SHOUYINWANG_API_KEY='你的 API Key'
export SHOUYINWANG_AUTH_MODE='x-api-key'
export SHOUYINWANG_ALLOW_HTTP='1'  # 文档接口是 HTTP；仅在确认网络可信时设置
python3 shouyinwang_recovery_proxy.py
```

Windows PowerShell：

```powershell
$env:SHOUYINWANG_API_KEY = "你的 API Key"
$env:SHOUYINWANG_AUTH_MODE = "x-api-key"
$env:SHOUYINWANG_ALLOW_HTTP = "1"  # 仅在确认网络可信时设置
python shouyinwang_recovery_proxy.py
```

然后打开代理终端显示的 `http://127.0.0.1:8787/`。

页面按接口文档提交邮箱数组和并发数，默认单批不超过 20 个邮箱，并发数限制为 1~10。页面只显示邮箱、状态和说明；代理不会把上游响应中的完整 `cookie` 字段返回给浏览器，也不会把 API Key 写入前端。

不要把 API Key、Cookie 或 Token 上传 GitHub。GitHub Pages 只能托管 HTML，不能替代本机代理或安全后端。

文档中的上游地址是 HTTP，代理默认阻止通过 HTTP 发送 API Key；仅在确认网络可信时设置 `SHOUYINWANG_ALLOW_HTTP=1`。
