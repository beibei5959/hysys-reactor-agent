# HYSYS 反应器选型系统 — Web 工作台

基于浏览器的图形操作界面，复用后端五节点 LangGraph 工作流、工程规则校验和任务持久化层。

## 功能

- **自然语言分析**：输入反应描述，自动解析反应特征并推荐反应器类型（Conversion / Equilibrium / Gibbs）
- **参数确认与修订**：编辑温度、压力、进料组成、物性包、计量方程，提交后重新选型校验
- **模拟执行**：完整五节点流程（解析 → 选型 → 校验 → 模拟 → 解释），前端实时轮询进度
- **任务管理**：历史搜索、分页浏览、JSON 导出、版本修订链
- **权限隔离**：普通用户仅访问自己的任务，管理员可管理全部任务

## 部署

### 环境要求

- Python 3.12+（已在 3.14.3 验证）
- 无需 Node.js（已构建的前端静态文件已包含在发布包中）

### 安装

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r web_bridge/requirements.txt
```

### 配置

复制 `.env.example` 为 `.env`，填写模型 API 密钥。模型降级顺序：本地 → DeepSeek → 硅基流动。

创建账号：

```powershell
python -m web_bridge.manage admin --admin    # 管理员
python -m web_bridge.manage engineer          # 普通用户
```

### 启动

```powershell
python -m web_bridge.api
```

服务默认监听本机 8765 端口。局域网部署需通过 HTTPS 反向代理转发，并配置 `HYSYS_WEB_ORIGINS` 与实际域名。

前端开发构建（需要 Node.js）：

```powershell
cd web
npm ci && npm run build
cd ..
```

## 使用流程

1. **登录**：使用管理员分配的账号
2. **新建分析**：输入反应的自然语言描述，或从开发示例中载入
3. **查看选型**：系统展示推荐反应器类型及依据
4. **确认参数**：编辑温度、压力、进料组成等，提交创建新修订
5. **等待执行**：前端轮询后端状态，完成后查看结果说明
6. **导出/修订**：JSON 导出完整数据，或基于历史任务创建修订版本

## 安全

- 密码：PBKDF2-SHA256（600,000 次迭代）+ 随机盐
- 会话：8 小时有效期，HttpOnly + SameSite=Strict Cookie，服务端仅存令牌摘要
- CSRF：写请求校验 Origin 与 Token
- 限流：每来源 5 分钟最多 10 次失败登录
- 并发：后台最多 2 个任务同时执行，队列上限 16

## 约束

- 单机单进程部署，数据存储在 `var/web` 目录
- Web 工作台使用 Mock 模式执行模拟，真实 HYSYS 计算通过 CLI `--mode real` 使用
- 不提供分布式队列、自助注册或跨实例同步
