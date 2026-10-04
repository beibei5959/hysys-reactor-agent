# AI 开发记录（时间线）

考核交付物 3：使用 AI 编程辅助的开发过程记录。本文件为时间线摘要；原始会话记录：
前期 Codex/ChatGPT 会话（见 docs/README_codex_original.md 所溯源的工程文档与验收 json）、
本次 Claude Code 会话（会话导出随交付包提交）。前期阶段性验收记录见同目录
《0.2版本验收记录.md》《Web前端验收记录.md》《真实HYSYS联调进度.md》《远程HYSYS验证清单.md》等。

## 阶段一：框架与 mock（10-03，Codex/ChatGPT 协作）

- 搭建 agent 骨架：NL 入口 app.py、选型规则 reactor_rules、校验层、mock 执行通道、Web 前端；
- 建立甲苯参考案例真机 COM 拼接序列（1000 kg/h 基准）并通过 12 项检查；
- 产出工程设计方案、验收记录、Web 联调 json（见 docs/）。

## 阶段二：三场景真机验证与统一入口（10-04 凌晨—上午，Claude Code 协作）

- 接手复核：确认场景 2 守卫容差（1e-7）与题目 10000 kg/h 的精确换算关系（108.52955420760267
  kmol/h = 10 × 已验证参考流），修正预设与示例；
- 新增 scenario_presets + run_nl.py 确定性路由；新增 verified_runners 与 hysys_tools 真机分派；
- 独立验证脚本 reforming/gasification MVP 在真机通过（保存 .hsc：06:07 / 06:08）；
- 集成包 NL_v1/v2 远程安装（原文件逐一 .bak 备份），三场景经统一 NL 入口全部 EXIT_CODE 0；
- 排错记录：GetActiveObject 需 HYSYS 运行中；冷启动会话不求解；supports_simulation 检查顺序；
  案例激活守卫（标题栏核对）。

## 阶段三：录制与交付包装（10-04 下午，Claude Code 协作）

- 三场景运行录屏 ×3（输入→命令→HYSYS→结果滚屏），本机归档为交付名；
- 拼装交付仓库树：原始 agent 层 + 集成层，剔除 .env/缓存/备份快照；原 README 存档为
  docs/README_codex_original.md；
- 撰写交付版 README（含运行证据链、假设与偏差、改动清单）、技术报告、本时间线；
- 真机证据文件（queries/*.input.json、*.result.json）从远程工作站回收入库。

## AI 协作方式说明

全程以 AI 编程助手为结对开发主体：需求拆解、代码生成与修改、真机排错、验证判据设计、
文档撰写均由人机对话推进；每次真机结论以 result.json / .hsc / 录屏为证据闭环，
未验证不宣称成功。人工职责：远程工作站操作、HYSYS 界面确认、录屏与交付决策。
