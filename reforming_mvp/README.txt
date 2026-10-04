蒸汽重整 MVP 验证包

把 reforming_mvp 整个文件夹放到远程外层 v2 项目 app.py 旁边。
无需安装，不覆盖任何已有脚本。保持 HYSYS 打开。
从 v2 项目 CMD 运行：
C:\Users\azureuser\.venv\Scripts\python.exe -X utf8 reforming_mvp\run_reforming.py

首次运行新建一个独立案例，内含 ER-600 和 ER-710 两个平衡反应器。
每个反应器进料：Methane 100 kmol/h、H2O 270 kmol/h，520 C，1350 kPa绝压。
出口分别指定600 C和710 C；零压降；能量流由求解器计算。
反应：甲烷蒸汽重整、水煤气变换。气相、分压atm基准。
采用用户从HYSYS库导出的完整精度A-D参数，E-H均为零。
说明：随包library_source.json的failed是旧导出脚本对LnKSource枚举的检查失败；
反应参数本身完整读出，公式已在本地复现全部KCalculated数据点。
新建反应用Ln(K)公式，不强行把源报告的数值4解释为某种枚举。

建模进程退出后独立核验：两种温度、进料、质量及反应组分衡算、
出口反应商与库平衡常数、求解器空闲。连续三次通过才保存。
报告：reforming_mvp\diagnostics；成功案例：reforming_mvp\generated_cases。
失败时保留打开的新案例和报告，不要连续重复运行。
没有关闭、删除或保存其他打开案例的操作。

本包先验证真实建模计算，尚未接入自然语言/LangGraph。
本地仅做语法和数值校验测试；HYSYS接口组合尚待本次远程验证。
数值测试不是HYSYS输出，也没有作为仿真结果写入报告。
