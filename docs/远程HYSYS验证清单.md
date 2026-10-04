# 远程 HYSYS V15 验证清单

当前只能确认用户曾验证 Python 3.12.4、pywin32、GetActiveObject、ActiveDocument、Flowsheet。本轮没有访问工作站。

## 第一轮：只读连接

1. 在远程项目目录记录 `python --version`，安装 requirements.txt，运行全套测试。
2. 检查已有 pywin32（必要时安装），手动打开 HYSYS 与案例。
3. 执行 `python app.py --probe-com`，保存实际输出和日期；该命令不创建/修改案例。
4. 如果失败，记录 HYSYS 是否打开、是否有活动案例、Python/HYSYS 位数、账户权限；不要通过猜测属性或自动重启来绕过。

## 第二轮：官方 Help 与最小 API 实验

需要用户提供本机 HYSYS V15 Help 中 Automation 对应内容，或在工作站打开 Help 查阅。每项先记录证据再填实现；文档中的应用层接口名称不是 COM API 名称。

|任务|应用层接口|必须记录|当前状态|
|---|---|---|---|
|创建案例副本|create_case|官方对象和方法、所有权、保存/关闭语义|待验|
|组分/物性|configure_components / configure_property_package|组分标识、物性包名称、进入/退出配置方式|待验|
|进料|create_feed_stream|物流集合访问、创建方法、单位和摩尔分率顺序|待验|
|转化反应器|create_conversion_reactor|单元创建、计量、基准组分、转化率及连接|待验|
|平衡反应器|create_equilibrium_reactor|计量与平衡数据、反应集、连接和规格|待验|
|吉布斯反应器|create_gibbs_reactor|候选组分、相态/限制、温压及连接|待验|
|求解|run|求解触发、收敛/失败标志、超时处理|待验|
|结果|get_results|组成、流量、温压、热负荷路径与单位|待验|

API 证据模板：日期、HYSYS 完整版本、Help 页标题/章节、最小验证代码、只读或写操作、实际输出、异常、单位、案例副本路径。不要记录密钥或与任务无关的数据。

## 第三轮：真实三场景验收

按任务书原文替换开发参数。逐例保存独立案例副本，人工检查物性与反应模型。确认转化率基准；核对平衡数据与候选组分；核对物料/元素守恒、出口组成非负、组成和为 1、流量/温压单位。只有真实收敛检查通过后才允许 `source=hysys, converged=true`。

记录“任务书预期选型、规则实际选型、HYSYS 收敛、人工界面与程序结果、异常/修复、最终通过与否”。当前三行都必须保持待验，不能以 Mock 成功替代。
