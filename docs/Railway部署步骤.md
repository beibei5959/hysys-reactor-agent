# Railway 部署步骤（网页 Mock 备胎演示 · 链接私发）

定位：项目不要求网页接真机。本页把 Web 工作台（Mock 执行通道）部署到 Railway 公网，
拿到 https 链接后**私发给需要看演示的人**——链接不写进 README 或任何公开文档。页面与答复始终
标注"未接 HYSYS"；真实计算演示走远程工作站 CLI 链路（README 第 2、3 节）。

## 0. 仓库已备好（已推送 GitHub）

- `web_bridge/api.py`：监听地址/端口改为环境变量 `HYSYS_WEB_HOST` / `PORT`
  （默认仍是本机 8765，本地行为不变）；
- `web_bridge/manage.py`：新增 `--password-env VAR`，非交互建账号（云平台启动命令用，已本地验证）；
- `web/dist` 前端构建产物已入库（.gitignore 的 `dist/` 规则曾把它挡掉，已强制加入；
  否则 Railway 从 GitHub 拉代码后没有页面）。

## 1. Railway 操作步骤（自己在网页上点，约 10 分钟）

1. railway.com 登录 → New Project → **Deploy from GitHub repo** → 选
   `beibei5959/hysys-reactor-agent`（首次会要求授权 Railway 的 GitHub App，建议只勾这一个仓库）；
2. 服务 → Settings → Build：
   - Build Command：`pip install -r requirements.txt -r web_bridge/requirements.txt`
   - Start Command：
     `sh -c "python -m web_bridge.manage admin --admin --password-env ADMIN_PASSWORD; python -m web_bridge.api"`
     前半句每次启动自动建 admin 账号（适配 Railway 临时磁盘）；账号已存在时报错跳过，
     `;` 保证后半句照常起服务；
3. Settings → Variables：
   - `HYSYS_WEB_HOST=0.0.0.0`
   - `HYSYS_WEB_SECURE_COOKIE=1`
   - `ADMIN_PASSWORD=`（自定 ≥12 字符，即网页登录密码。**用一次性密码**，它明文存在
     Railway 环境变量里，别复用你其他网站的密码）
   - 可选 `DEEPSEEK_API_KEY` 等模型密钥：不填则自由文本解析不可用，演示改用
     "从示例载入"入口即可，选型预览与 Mock 执行不受影响；
4. Settings → Networking → **Generate Domain**，得到 `https://<服务名>.up.railway.app`；
5. 回 Variables 新增：`HYSYS_WEB_ORIGINS=https://<服务名>.up.railway.app`
   （必须与浏览器地址栏完全一致，https、无结尾斜杠）→ 自动重新部署；
6. 打开该域名 → admin / ADMIN_PASSWORD 登录 → 走一遍
   "从示例载入 → 选型预览 → Mock 执行"确认可用。

## 2. 私发链接与注意事项

- 私发时附上：https 域名 + 账号密码 + 一句说明
  （"网页为 Mock 交互通道演示；真实 HYSYS 计算见仓库录屏与远程 CLI 链路"）；
- **任何对外材料、私聊里都不要出现 localhost / 127.0.0.1 地址**（别人打不开）；
- Railway 磁盘临时：重启后账号/任务库清空，账号由启动命令自动重建，任务现场重跑即可；
- 起不来先看 Deploy Logs，常见两个原因：Build Command 没填（fastapi/uvicorn 未装）、
  `HYSYS_WEB_HOST` 漏填（服务监听在 127.0.0.1，平台探测不到端口）。

## 3. 演示话术绑定

- 网页演示开场先指页面标注："本通道为 Mock 执行，用于展示交互与选型流程"；
- 被问"真算在哪"→ 展示录屏 / queries/*.result.json / .hsc 留档，或远程工作站现场跑 CLI；
- 被问"网页能不能接真机"→ 能，但需另行开发后端到远程 COM 的桥接并端到端验证，
  属可选增强（通道说明见技术报告第 1、5 节），不在本次发布内。
