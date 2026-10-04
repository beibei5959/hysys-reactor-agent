# HYSYS 反应器智能选型系统

化工反应工程 AI 助手。输入自然语言描述反应条件，系统自动完成反应器选型、参数校验与模拟执行，输出中文工程说明。

## 核心能力

| 能力 | 说明 |
|------|------|
| **智能选型** | 根据反应特征（转化率已知 / 可逆平衡 / 复杂体系）自动推荐 Conversion、Equilibrium 或 Gibbs 反应器 |
| **参数校验** | 温度、压力、组分、摩尔分率归一化、计量系数完整性检查 |
| **模拟执行** | 通过 HYSYS COM 接口驱动真实仿真，或 Mock 模式验证软件流程 |
| **多级模型降级** | 本地模型 → DeepSeek → 硅基流动，自动故障切换 |
| **任务持久化** | SQLite WAL + 租约令牌，支持中断恢复与版本修订 |
| **Web 工作台** | 浏览器界面，支持任务管理、历史搜索、JSON 导出 |

## 快速开始

### CLI

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env 填写模型 API 密钥

# 离线示例（无需模型服务）
python app.py --example conversion --task-id demo-001

# 自然语言查询
python app.py --query "甲苯歧化反应，380°C，2.5MPa，转化率50%"

# 查询结果
python app.py --status demo-001 --json
```

### Web 工作台

```powershell
pip install -r web_bridge/requirements.txt
python -m web_bridge.manage admin --admin
python -m web_bridge.api
```

详见 [README-WEB.md](README-WEB.md)。

## 工作流

```
自然语言输入 → 反应解析 → 反应器选型 → 参数校验 → 模拟执行 → 结果解释
```

五个节点由 LangGraph 编排，每步原子保存状态，支持中断恢复。

## HYSYS 集成

| 模式 | 说明 |
|------|------|
| `mock`（默认） | Mock 控制器，验证完整软件流程，不依赖 HYSYS |
| `real` | ComHysysController，通过 pywin32 连接 HYSYS V15 COM 接口执行真实仿真 |

真实模式需要在运行 HYSYS 的机器上安装 `pywin32`，并通过 `.env` 设置 `HYSYS_MODE=real`。连接链路（`GetActiveObject → ActiveDocument → Flowsheet`）已验证；反应器创建、参数写入等写入操作已实现，需在目标环境联调确认。

## 项目结构

```
hysys-reactor-agent/
├── app.py                    # CLI 入口
├── src/
│   ├── agent/                # LangGraph 工作流与节点
│   ├── hysys/                # COM 控制器（com_client）与 Mock 控制器
│   ├── models/               # Pydantic 数据模型
│   ├── runtime/              # 任务执行引擎与 SQLite 存储
│   └── tools/                # 工具层封装
├── web_bridge/               # Web API 与认证
├── web/                      # React 前端
── tests/                    # 单元与集成测试
└── docs/                     # 工程文档
```

## 测试

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

所有测试不依赖外部模型服务或 HYSYS 环境。

## 配置参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HYSYS_MODE` | `mock` | `mock` 或 `real` |
| `LLM_TIMEOUT_SECONDS` | 60 | 云模型超时（秒） |
| `TASK_TIMEOUT_SECONDS` | 240 | 任务总预算（秒） |
| `MAX_RETRIES` | 2 | 模拟阶段最大重试次数 |

完整配置见 `.env.example`。
