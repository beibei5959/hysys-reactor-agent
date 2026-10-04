# Live Demo（本地版，约 5 分钟）

开场：后端全 Python；AI 负责理解，规则负责选型，HYSYS 负责真实计算。本次演示使用 Mock 验证流程，没有真实工程数值。

1. 展示工程设计：五个节点、State、真实与 Mock 控制器分层。
2. 运行 `python app.py --example equilibrium`：已知具体可逆反应且受平衡控制，选平衡反应器。
3. 运行 `python app.py --example conversion`：明确给定 80% 转化率，选转化反应器。
4. 运行 `python app.py --example gibbs`：复杂体系的路径/产物分布不明确，选吉布斯反应器；理由不是高温。
5. 运行 `python app.py --example conversion --json`：查看选择理由、校验状态、Mock 来源、converged=null、engineering_results=null。
6. 复制开发示例为自己的新文件，删除 pressure 后用 `--input` 运行：显示缺参且不会执行模拟。补回参数再次提交后通过。
7. 运行 `python -m pytest -q -p no:cacheprovider`：展示高温不误选、有限重试、未收敛不出结果、异常释放资源等测试。

有模型凭据后可以补充 `--query` 在线演示；未配置时不得宣称离线示例为自然语言识别成果。远程部分仅在考试机执行 `--probe-com`；建模 API 验证与真实三场景通过后再升级演示。

已配置本机 .env 后，在线演示将按“本地 → DeepSeek → 硅基流动”自动降级；输出底部查看“模型调用记录”。可展示 docs 中的模型降级实测记录，说明本地空回答如何被识别并由 DeepSeek 接手。要现场模拟断线，请先关闭属于自己的测试服务或使用独立测试配置；不要修改用户其他服务。
