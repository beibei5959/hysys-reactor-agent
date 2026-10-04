# AI 驱动 HYSYS 反应器智能选择系统——工程设计与开发实施方案

## 1. 项目边界与不可变约束

本文件为后续开发施工图，依据用户确认的方案编写。后端统一使用 **Python**；保留 LangGraph、Pydantic、工程规则及 HYSYS Automation/COM 分层，不另起架构。0.2版本依据用户确认的工程自查增加单机 SQLite 持久化、租约与恢复能力；不引入分布式队列或复杂服务框架。提供中文命令行入口，界面不作为前置依赖。

目标：自然语言描述反应条件，提取结构化信息，按可解释规则选择反应器，检查参数，调用模拟器，解释结果。LLM（大语言模型）负责语言理解与中文解释；工程规则负责确定性约束；HYSYS 负责真实工程计算。Mock 只验证软件流程，不提供热力学计算结论。

当前参考对话能确认三类场景及甲烷蒸汽重整、给定转化率、复杂体系等背景，但没有完整任务书原文或全部数值。仓库的三场景数据必须标明为开发示例，不能冒充原始任务规格；完整参数到位后替换示例而不改选择逻辑。

## 2. 三场景与选择规则

|场景|工程证据|选择|不能省略的条件|
|---|---|---|---|
|给定转化率|明确转化率，例如 80%|Conversion Reactor（转化反应器）|定义计量反应、基准组分、转化率及工况|
|具体可逆反应达到平衡|具体反应已知、可逆、受平衡控制|Equilibrium Reactor（平衡反应器）|反应方程、平衡数据来源/方法、工况|
|复杂体系|多反应体系，反应路径或产物分布不明确|Gibbs Reactor（吉布斯反应器）|仍须定义候选组分、进料、物性及工况|

优先级：明确给定转化率优先；其次检查已知具体可逆平衡反应；再检查复杂体系且路径/产物分布未知。仅温度高、只有多反应、或信息不足时不能自动选择 Gibbs，应追问。未知布尔值使用 None，不能把未提及误判为 False。转化率统一为 0～1，温度 K、压力 kPa（绝压）、流量 kmol/h。置信度只表达规则证据完整度，不代表工程计算精度或模型概率。

## 3. 总体链路及职责

用户自然语言 → 反应信息结构化解析 → 工程规则/反应器选择 → 参数完整性校验 → LangGraph 状态编排 → HYSYS Tool → HysysController → Python/pywin32 → HYSYS Automation/COM → SimulationCase → Flowsheet → Streams/Operations/Reactor → 运行/收敛检查 → 结果提取 → AI 中文解释。

LangGraph 实际编排上述解析、选择、校验、执行、解释全过程。工具层只组织参数与控制器调用；不包含反应器选择规则。真实与 Mock 控制器共享接口，通过显式配置注入，真实模式失败不得静默降级到 Mock。

## 4. 第一版工作流

|节点|输入与输出|分支|
|---|---|---|
|parse_reaction|自然语言 → Pydantic ReactionInfo|无在线模型时仅接受明确标注的离线结构化输入；解析失败进入解释节点|
|select_reactor|结构化特征 → 类型、理由、置信度|证据不足保留未选择，由校验收集缺失项|
|validate_input|反应信息 + simulation_inputs → 缺参数清单|缺参数直接解释并暂停，本轮不调用 HYSYS；用户补全后重新提交|
|run_hysys|调用工具层和控制器|仅明确可重试错误有限重试，其他错误直接解释|
|explain_result|选择、校验、运行结果 → 中文答案|固定输出真实/Mock 标志与收敛状态，再附 LLM 解释|

固定顺序：parse → select → validate → run → explain → END。解析失败 parse → explain；校验失败 validate → explain；临时运行错误 run → run，最多追加 2 次（合计最多 3 次调用）。失败状态不伪装成收敛。参数错误、未验证 API 和配置错误不重试。每次尝试释放本次拥有的资源；真实控制器未完成幂等性/清理验证前，不启用真实 COM 建模重试。

## 5. 数据契约

ReactionInfo 使用 Pydantic，拒绝未知字段、非法数值和相互矛盾的转化率标志。

|字段|类型/含义|
|---|---|
|reaction_name|可空字符串，反应名称|
|reactants / products|字符串列表，已知反应物/产物|
|temperature / pressure|可空浮点数，温度 K / 压力 kPa（绝压），必须为正|
|reversible|可空布尔，是否可逆|
|multiple_reactions|可空布尔，是否复杂/多反应体系|
|conversion_known / conversion|可空布尔 / 0～1 浮点数，转化率是否明确及其数值|
|equilibrium_controlled|可空布尔，是否受平衡控制|
|products_known|可空布尔，产物/分布是否明确|
|reaction_path_known|可空布尔，具体反应路径是否明确|

ReactorAgentState 使用 TypedDict，节点返回局部更新；每次请求初始化全部运行状态，避免上次结果残留。

|字段|中文用途|
|---|---|
|user_query|用户原始中文请求|
|reaction_info|经 Pydantic 校验的反应特征|
|selected_reactor|规则选出的类型，可为空|
|selection_reason|选择依据与命中规则|
|confidence|规则证据完整度评分|
|simulation_inputs|进料、组分、物性、反应及操作参数|
|missing_parameters|缺失/无效参数与补充提示|
|validation_passed|是否允许进入模拟步骤|
|simulation_status|not_started / needs_input / running / success / failed|
|simulation_results|控制器结果，必须含数据来源、收敛标志与单位|
|error|本轮错误信息，不输出密钥|
|retry_count|已追加重试次数|
|final_answer|面向用户的中文说明|
|llm_trace|解析/解释阶段按模型记录成功、失败、降级原因；不含密钥或服务原始错误体|

simulation_inputs 同样用 Pydantic 校验：components（候选组分），property_package（物性包），feed_composition（摩尔分率且和为 1），feed_flow_kmol_h，反应器温度及压力来自 ReactionInfo。定温且出口压力指定是开发版边界，进料示例采用同一温压；热负荷、压降、相态及更复杂操作规格须在真实接入前确认。Conversion/Equilibrium 须 reactions（计量系数映射，反应物负、产物正），Conversion 另须 conversion_basis，Equilibrium 另须 equilibrium_method。校验必须检查组分引用、计量正负、基准反应物与进料一致性。化学式/元素守恒、物性适用性与平衡参数正确性仍需工程核验，不能把基础格式校验当成物理有效性证明。

## 6. 控制器及 COM 验证边界

HysysController 接口：connect、create_case、configure_components、configure_property_package、create_feed_stream、create_conversion_reactor、create_equilibrium_reactor、create_gibbs_reactor、run、get_results、close。MockHysysController 实现同一流程，返回明确的占位结果，不编造组成、收率、能耗或平衡转化率。真实实现放在 com_client.py，未验证接口明确抛出“尚未验证”，禁止猜测 COM 属性/方法。

**用户在远程 Windows 工作站已实际验证**：Python 3.12.4；pywin32 可用；win32com.client.GetActiveObject('HYSYS.Application')；app.ActiveDocument；case.Flowsheet。本地未复验，证据来源是用户确认。

**尚未验证**：创建案例、组分与物性配置、物流集合/单元集合、三个反应器的创建及规格、反应集绑定、求解器控制、收敛标志及结果字段。不能把 Streams/Operations/Reactor 的具体 Automation 调用写成已验证。

远程第一步只读附着已打开的案例并检查上述三层对象，绝不关闭用户 HYSYS 或修改活动案例。随后用官方 HYSYS V15 Help/工作站最小验证逐项记录对象路径、版本、单位、返回值及异常，才编写对应实现。真实建模只针对用户指定副本，资源所有权明确，close 默认仅释放 Python 引用。

## 7. 精简目录

```text
README.md / requirements.txt / .env.example / .gitignore / app.py
config/settings.py
src/agent/graph.py / state.py / nodes/{parse_reaction,select_reactor,validate_input,run_hysys,explain_result}.py
src/models/{reaction,simulation}.py
src/knowledge/reactor_rules.py
src/hysys/{controller,mock_controller,com_client,exceptions}.py
src/tools/hysys_tools.py
tests/ / examples/ / docs/
```

## 8. 阶段施工与验证闸门

|阶段|产物|通过条件|
|---|---|---|
|1 文档/骨架|本施工图、依赖、入口及配置|文件齐全，无原文件被覆盖|
|2 数据模型/State|Pydantic 模型和状态定义|字段齐全，负温度、非法转化率及矛盾输入被拒绝|
|3 示例/规则|三场景 JSON、规则代码|稳定输出 Equilibrium/Conversion/Gibbs；高温和证据不足不误选|
|4 LangGraph|五节点与分支|缺参数不执行；解析失败可解释；重试有上限|
|5 Mock/本地端到端|工具层、Mock、CLI、可选 LLM 接口|三场景完整通过并显式标 Mock；失败不伪装成功|
|6 远程 COM|只读探测、V15 Help/API 证据、真实实现|先验证 API 再写实现；真实收敛和单位可核验|
|7 真实三场景|HYSYS 案例和结果|人工界面与程序结果对照，质量/元素守恒及物理合理性核验|
|8 产出|README、开发记录、测试结果、1～2 页报告、Live Demo|分别列出本地、在线 LLM、真实 HYSYS 的实际已验/待验状态|

每阶段测试通过后再继续下一阶段；没有远程连接/真实 HYSYS 时阶段 6～7 保持待验证，不填假结果。可以先准备阶段 8 的本地版材料，明确它不等于真实工程验收。

## 9. 评分项与验收证据

系统设计：本文件、目录分层、工作流与状态契约。AI 分析质量：原文提取、未知保留、规则理由、缺参追问、结果中文解释。技术实现：Python/Pydantic/LangGraph、统一控制器、COM 已验边界。健壮性/调试：数值校验、边界规则、错误分支、有限重试、Mock 标识、可重复测试与远程证据记录。

LLM 不允许直接决定反应器或调用 COM。在线返回必须满足 JSON/Pydantic 契约；数值不能补猜；解释不得增加结果中没有的数值。无凭据时用离线结构化示例演示，不能将离线输入宣称为真实自然语言模型解析。

## 10. 模型降级策略（用户追加确认）

固定优先级：**LOCAL 本地 Qwen → DEEPSEEK → SILICONFLOW 硅基流动**。本地地址从 `.env` 读取（形如 `http://<本机模型服务IP>:1234/v1`，按实际环境填写）。每个阶段每个模型最多请求一次，不对同一失败服务无限重试。解析和解释分别从本地开始，成功即停止该阶段的后续调用。

连接失败、超时、HTTP 非成功响应、无效 JSON 或不符合解析数据契约触发下一级；缺少配置则记录跳过。工程参数缺失是业务结果，应追问用户，不能通过换模型填造参数。三个模型全部解析失败则结束本次请求，不执行 HYSYS；三个模型全部解释失败则保留规则生成的中文说明和已有模拟状态。模型降级次数不计入 HYSYS retry_count。

从项目根目录 .env 读取三组配置，系统环境变量优先。密钥不进源码、日志、文档或压缩包，.env 已加入忽略清单。LLM_TIMEOUT_SECONDS 默认 60 秒（每个 HTTP 阶段的超时配置），每个节点最多三家顺序调用。llm_trace 记录阶段、提供商、模型名、状态和脱敏原因。

本地接口实测不接受 json_object；json_schema 模式正式 content 为空。因此本地使用 text 模式，提示词包含 JSON Schema（数据契约），只解析正式 content 并统一做本地数据契约校验，失败仍降级；不把思考字段当正式结果。云服务使用 JSON 对象模式。模型服务兼容性不得以协议相似代替实测。DeepSeek 模型列表未列出用户指定模型，但实际 deepseek-v4-flash 调用成功，以实际调用证据为准，不擅自替换模型名。

## 11. 产出与待提供信息

0.2版本的运行入口、持久化与降级细节以 README 和 `0.2版本验收记录.md` 为准。原五节点及核心状态字段保留；新增 task_id/attempt 等任务元数据，以及 error_code、explanation_status、cleanup_status 用于恢复和部分成功表达。节点快照在应用层事务保存，没有把 LangGraph 内存状态误称为持久化。

本地发布应包含能运行的三场景、测试、工程设计、开发记录、验证报告与演示步骤。远程继续需要任务书原文及参数、可访问的工作站/用户执行只读检查结果、官方 V15 Automation 相关 Help、可操作的案例副本。在线 AI 联调需要用户自行配置模型服务地址、模型名、密钥，不把密钥写进日志或版本库。
