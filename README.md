# Cookie JSON 工作台 - 部署包

这是一个可直接部署到静态托管的纯前端版本。

## 文件
- `index.html`：站点入口
- `404.html`：GitHub Pages 兼容兜底
- `netlify.toml`：Netlify 兼容配置
- `vercel.json`：Vercel 兼容配置

## 部署到 GitHub Pages
1. 新建一个仓库。
2. 把这个目录里的文件上传到仓库根目录。
3. 在仓库设置里打开 GitHub Pages。
4. 选择分支和根目录。
5. 等待生成 HTTPS 地址。

## 部署到 Netlify
1. 登录 Netlify。
2. 直接拖拽这个目录，或连接 Git 仓库。
3. 发布后会得到一个 HTTPS 域名。

## 部署到 Vercel
1. 登录 Vercel。
2. 导入这个目录对应的仓库。
3. 直接部署静态站点。

## 说明
- 本工具不依赖后端。
- 本地数据库保存在浏览器 IndexedDB 中。
- 如需跨电脑迁移，请使用“导出数据库”备份文件。
