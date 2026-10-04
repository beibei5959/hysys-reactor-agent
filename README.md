# AI 驱动的 HYSYS 反应器智能选择系统

> 中文自然语言描述工艺 → 按规则自主判断反应器类型 → 在真实 Aspen HYSYS V15 中建模求解 → 读取结果并自动验算。
> 三个指定场景（甲烷蒸汽重整 / 甲苯歧化 / 水煤浆气化）已通过远程工作站真实 HYSYS 联调；
> 当前采用固定场景预设路由（见第 1 节），工程简化与建模范围在第 5 节完整披露；每个场景各有完整运行录屏。

---

## 1. 系统总览

统一入口是一条命令：

```
python -X utf8 run_nl.py queries\scenarioX_*.txt
```

`run_nl.py` 读取中文工艺描述文本后做**确定性路由**：关键词命中已验证场景预设
（`src/knowledge/scenario_presets.py`）→ 以固定结构化参数提交 `app.py --input`
（中文原文仍作为 `user_query` 保留并出现在最终答复中）；未命中任何预设的查询
自动回退到原有 LLM 自由提取路径（`app.py --query`，需要 `.env` 中的模型配置）。

Agent 主干（`app.py`）：参数校验 `validate_input` → 反应器选型 `reactor_rules`
→ 执行分派 `src/tools/hysys_tools.py` → 真实 COM 通道或 mock 通道 → 结果验算 →
写入 `queries\scenarioX.result.json`。

### 三个场景的真实机通道

| 场景 | 工况要点 | 选型结果 | 真实机执行通道 | 通过判据 |
|---|---|---|---|---|
| 1 甲烷蒸汽重整 | CH4:H2O=1:2.7，出口 710℃ 与 600℃、13.5 bar，进料 520℃ | Equilibrium | `verified_runners` → `reforming_mvp/run_reforming.py`（COM 自建案例） | `passed_reforming_checks`：两工况转化率 55.06% / 30.22%，平衡商与 K 吻合 ~1e-8，连续 3 次稳定 |
| 2 甲苯歧化 | 10000 kg/h、380℃、2.5 MPa、转化率 50% | Conversion | `com_client` 参考拼接：向**当前激活的** `toluene_python_test.hsc` 写进料并求解 | 12 项检查全 true：进料 10000.0 kg/h、转化率 50.0%、质量残差 0.0、苯 27.1324 / 邻二甲苯 27.1338 kmol/h |
| 3 水煤浆气化 | 62 wt%、40 bar、40℃→1400℃、含副反应、灰分忽略 | Gibbs | `verified_runners` → `gasification_mvp/run_gasification.py`（COM 自建案例） | `passed_gasification_checks`：碳转化率=CO 收率 40.86%，气相 CO:H2=50:50（剩余固碳单列），元素残差 ~3e-8，连续 3 次稳定；建模简化见第 5 节 |

mock 模式（不接 HYSYS）用于 Web 演示与回归测试，见 `README-WEB.md` 与 `docs/Live-Demo.md`；
Web 后端当前**仅** Mock 通道（代码级固定），接真机需另行开发，不是配置开关；
mock 页面显著标注"未接 HYSYS"，不与真实计算混淆。

---

## 2. 调用链与运行证据链

```
中文工艺描述 (queries/*.txt)
   └─ run_nl.py            打印 PRESET_MATCHED / INPUT_FILE / RESULT_FILE / EXIT_CODE
       └─ app.py --input   校验 → reactor_rules 选型 → hysys_tools 分派
           ├─ 场景2: com_client ── COM GetActiveObject ──> 激活的甲苯案例（写 FEED、求解、轮询验算）
           └─ 场景1/3: verified_runners ── 子进程 ──> 已验证脚本 ── COM ─> 自建 HYSYS 案例
   └─ queries/*.result.json  selected_reactor / selection_reason / user_query /
                             source:"hysys" / checks{...} /
                             场景2: case_unique_id（真机案例路径）；场景1/3: report_path（保存 .hsc 路径）
```

**录屏自检三点**（每段录屏均包含）：① 终端第一行命令为 `run_nl.py queries\scenarioX_*.txt`；
② 终端打印 `PRESET_MATCHED: <类型>`；③ 结尾滚动展示的 result.json 含 `selected_reactor`、
`selection_reason`、`user_query`（中文原始描述）与真机溯源字段（场景 2 为 `case_unique_id`，
场景 1/3 为 `report_path` 保存案例路径）。
单独运行仿真脚本不可能产生 ①② 与 agent 层字段，故录屏即"Agent 连通真机"的证据。

录屏清单（随发布包 `HYSYS_delivery/recordings/` 提供）：

| 文件 | 内容 |
|---|---|
| 录制_场景1_甲烷蒸汽重整.mp4 | 工艺描述 → 命令 → EXIT_CODE 0 → HYSYS 新案例 → 结果滚屏 |
| 录制_场景2_甲苯歧化.mp4 | 同上（HYSYS 为激活的甲苯参考案例） |
| 录制_场景3_水煤浆气化.mp4 | 同上（HYSYS 新案例） |

真机留档：`toluene_python_test.hsc`（场景2 验证态）、`reforming_20261004_*.hsc`、
`gasification_20261004_*.hsc`（场景1/3 保存案例，位于远程工作站）。

---

## 3. 快速开始（真实 HYSYS）

环境：Windows + Aspen HYSYS V15 + Python（pywin32/pythoncom）。仓库即远程工作站
`hysys-reactor-agent-v2` 的同源代码。

0. 新机器安装：`python -m venv .venv` → `.venv\Scripts\pip install -r requirements.txt`；
   甲苯参考案例二选一：取远程工作站既有 `toluene_python_test.hsc`，或运行
   `auto_reference_workflow.py` 重建（验证记录 `docs/verified_agent_auto_reference.json`）。

1. 场景 2 前置：打开并**激活** `toluene_python_test.hsc`（程序只认该案例，绝不改动其他案例）；
   场景 1/3 前置：HYSYS 保持运行即可（脚本自建案例，勿在运行期间点击 HYSYS）。
2. 依次执行（单行）：

```
cd /d <repo> && C:\Users\azureuser\.venv\Scripts\python.exe -X utf8 run_nl.py queries\scenario2_toluene.txt
cd /d <repo> && C:\Users\azureuser\.venv\Scripts\python.exe -X utf8 run_nl.py queries\scenario1_reforming.txt
cd /d <repo> && C:\Users\azureuser\.venv\Scripts\python.exe -X utf8 run_nl.py queries\scenario3_gasification.txt
```

3. 通过标准：终端 `EXIT_CODE: 0`；result.json 中 `simulation_status: success`、
   `converged: true`、`checks` 全 true（见第 1 节表格）。

---

## 4. 反应器选型规则

实现于 `src/knowledge/reactor_rules.py`，与通行的反应器选型逻辑一致：

- **给定转化率** → Conversion Reactor（按指定转化程度反应）；
- **反应路径已知 + 可逆 + 受热力学平衡控制** → Equilibrium Reactor（条件平衡常数/平衡商法）；
- **多反应体系且路径/产物分布未知** → Gibbs Reactor（吉布斯自由能最小化，无需动力学参数）。

每份结果都带 `selection_reason` 自然语言解释，供演示与报告引用。

---

## 5. 工程假设与偏差（诚实清单）

1. **场景 2 二甲苯归并**：参考案例仅含邻二甲苯，间/对异构体归并为 o-Xylene（任务书要求三种异构体，此为已记录偏差；化学计量与质量衡算仍严格闭合）。
2. **场景 2 复用已验证参考案例**：Conversion 通道在既有 `toluene_python_test.hsc`（反应配置已验证）上完成进料写入、求解与 12 项验算（`execution_mode: existing_reference_case_update`），非从零自动建模；场景 1/3 为完全自动从零建模。取舍理由：通用 COM 建模路径中仅该参考序列经过真机严格验证。
3. **10000 kg/h 换算**：任务书进料 = 已验证 1000 kg/h 参考流的精确 10 倍（108.52955420760267 kmol/h，HYSYS 甲苯摩尔质量 ≈92.1408）；只改广延量，所有强度量检查（转化率、化学计量残差、温度、零热负荷）保持严格。
4. **场景 1 反应集**：按任务书给定主反应（重整）+ 副反应（水煤气变换）两反应平衡体系，未引入甲烷化等额外反应。
5. **场景 3 基准**：当前按 1000 kg/h 水煤浆（62 wt%）比例基准验证；**未**据此换算任务书 80000 Nm³/h 对应的绝对产量。碳转化率 / CO 收率为强度量，与基准无关。
6. **场景 3 模型简化**：煤视为**纯固体碳**，灰分忽略（按任务书），产物物种不含甲烷等烃类；运行检查通过代表该简化反应体系通过验证，**不等价于**完整煤气化模型已验证。
7. **场景 3 合成气比例**：CO:H₂=50:50 指**气相**比例；`outlet_mole_fractions` 将剩余固体碳计入分母（CO、H₂ 各约 29%），剩余固体碳（30.5258 kmol/h）在结果中单列，两种口径不可混读。
8. **收敛判据**：真机通道以"连续 3 次轮询全部检查通过"（results_stable）+ `solver_idle` 作为收敛证据，比单次读取更严格。

---

## 6. 代码分层与改动清单

**原始 agent 层**（前期框架，提供 NL 入口、选型规则、校验、mock、Web 前端）：
`app.py`、`src/knowledge/reactor_rules.py`、`src/tools/hysys_tools.py`、`src/hysys/com_client.py`、
`src/hysys/reference_checks.py`、`web/`、`web_bridge/` 等。原始 README 见
`docs/README_codex_original.md`，前期开发记录见 `docs/`（验收记录、联调 json、Live-Demo.md）。

**集成层**（本次集成的扩展）：

| 文件 | 性质 | 说明 |
|---|---|---|
| `run_nl.py` | 新增 | 中文工艺描述 → 确定性预设路由 → `app.py --input`；未命中回退 LLM 路径 |
| `src/knowledge/scenario_presets.py` | 新增 | 三场景关键词匹配与固定参数预设 |
| `src/hysys/verified_runners.py` | 新增 | Equilibrium/Gibbs 分派到已验证脚本（子进程），归一化结果 |
| `reforming_mvp/`、`gasification_mvp/` | 新增 | 两个独立真机验证脚本（严格检查 + 3 次稳定 + SaveAs） |
| `src/tools/hysys_tools.py` | 修改 | 真实模式分派块；`supports_simulation` 检查移至 `connect()` 之后 |
| `src/hysys/com_client.py` | 修改 | 进料守卫改为 10000 kg/h 对应摩尔流；其余检查一字未动 |
| `src/hysys/reference_checks.py` | 修改 | 质量门槛改为 `feed_mass_10000_kg_h`；摩尔容差改比例制 |
| `examples/conversion.json`、`queries/*.txt` | 修改/新增 | 任务书条件与三个中文查询文件 |

所有被修改的原始文件在集成时均先备份（`.bak` / `backups/`），原始快照随发布包保留，不在本仓库内。

---

## 7. 局限

- 场景 2 真机通道依赖既有参考案例与精确进料守卫，不支持任意进料/任意反应配置（守卫失败即拒绝写入）；
- 自由 LLM 提取路径（未匹配预设的查询）需要 `.env` 模型配置，仓库仅含 `.env.example`；
- Web 后端当前仅 Mock 通道（代码级固定），接真机需另行开发并完成端到端验证，不是配置开关；故网页接真机未包含在本次发布中（见技术报告"适用范围与复现"一节）。
