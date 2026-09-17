# 收银王 Cookie 失效恢复功能

这是一个独立功能，不依赖 Cookie JSON 工作台的导入、积分统计或本地数据库。

## 安全边界

- HTML 只提交邮箱列表和并发数。
- API Key 只放在本机代理的环境变量中，不写入 HTML，不上传 GitHub。
- 代理会过滤上游返回中的 `cookie` 字段，网页只显示邮箱、成功/失败和说明。
- 只对你有权限管理的账号使用，不要把真实 API Key、Cookie 或 Token 发到聊天和公开仓库。

## 文件

- `收银王_cookie失效恢复.html`：独立网页界面。
- `shouyinwang_recovery.html`：同一页面的英文文件名版本，便于服务器和压缩工具使用。
- `shouyinwang_recovery_proxy.py`：本机安全代理，按接口文档转发请求。

## macOS / Linux 使用

把两个文件放在同一目录，在终端执行：

```bash
export SHOUYINWANG_API_KEY='替换为你自己的 API Key'
export SHOUYINWANG_AUTH_MODE='x-api-key'
export SHOUYINWANG_ALLOW_HTTP='1'  # 文档接口是 HTTP；仅在确认网络可信时设置
python3 shouyinwang_recovery_proxy.py
```

然后打开终端显示的地址：

```text
http://127.0.0.1:8787/
```

不要直接双击 HTML；通过本机代理打开可以避免浏览器跨域问题。

如果接口要求 `Authorization: Bearer ...`，改为：

```bash
export SHOUYINWANG_AUTH_MODE='authorization'
```

文档给出的上游地址是明文 HTTP。代理默认不会通过 HTTP 发送 API Key；只有确认这是可信内网，并明确设置 `SHOUYINWANG_ALLOW_HTTP=1` 后才会转发。生产环境应优先使用 HTTPS 上游地址。

## Windows PowerShell

```powershell
$env:SHOUYINWANG_API_KEY = "替换为你自己的 API Key"
$env:SHOUYINWANG_AUTH_MODE = "x-api-key"
$env:SHOUYINWANG_ALLOW_HTTP = "1"  # 仅在确认网络可信时设置
python shouyinwang_recovery_proxy.py
```

浏览器打开 `http://127.0.0.1:8787/`。

## 按文档转发的请求

代理向文档中的上游接口发送：

```http
POST http://167.160.91.234:17081/api/v1/email-pool/revive-api
Content-Type: application/json
x-api-key: 你的环境变量值
```

```json
{
  "emails": ["example@example.com"],
  "concurrency": 5
}
```

单批最多 20 个邮箱，并发数限制为 1~10。单个账号可能需要 30~60 秒，代理超时设置为 330 秒。

## GitHub Pages 说明

GitHub Pages 只能托管 HTML，不能运行这个 Python 代理，也不应把 API Key 写入前端。因此完整功能需要在每台使用机器本地运行代理，或部署到你自己控制的 HTTPS 后端，并用环境变量配置密钥。
