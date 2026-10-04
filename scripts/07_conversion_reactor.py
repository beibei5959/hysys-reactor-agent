"""
步骤 07：创建 Conversion 反应器、运行仿真、读取结果
======================================================
目标：
  1. 创建 Conversion Reactor
  2. 关联反应集
  3. 连接进料/出料物流
  4. 设置转化率（甲苯 50%）
  5. 运行仿真
  6. 读取结果（组成、流量、温度、热负荷）

甲苯歧化场景最终参数：
  - 进料：1000 kg/h 纯甲苯，380°C，2.5 MPa
  - 转化率：甲苯 50%
  - 反应：2 C7H8 → C6H6 + C8H10

⚠️ 待确认：
  - 二甲苯异构体分配比例
  - 反应器热工条件（绝热/等温/指定温度）

运行前：步骤 03-06 已完成。
"""

import sys
import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ============================================================
# 场景参数
# ============================================================
REACTOR_NAME = "TOLUENE_RXN"
FEED_STREAM_NAME = "FEED"
PRODUCT_STREAM_NAME = "PRODUCT"
REACTION_SET_NAME = "Toluene_RXN_Set"

# 甲苯转化率
TOLUENE_CONVERSION = 0.50  # 50%

# 待确认 ⚠️
# 反应器操作模式：
#   - 等温：指定 reactor_temperature
#   - 绝热：不指定温度
#   - 指定热负荷
REACTOR_MODE = "isothermal"  # 或 "adiabatic"
REACTOR_TEMPERATURE_C = 380.0  # 如果等温，反应器温度（当前假设与进料相同）


def main():
    log("=== Conversion 反应器 — 运行仿真 ===")
    log(f"反应器名称：{REACTOR_NAME}")
    log(f"进料物流：{FEED_STREAM_NAME}")
    log(f"出料物流：{PRODUCT_STREAM_NAME}")
    log(f"甲苯转化率：{TOLUENE_CONVERSION * 100}%")
    log(f"反应器模式：{REACTOR_MODE}")
    if REACTOR_MODE == "isothermal":
        log(f"反应器温度：{REACTOR_TEMPERATURE_C}°C")

    log("""
⚠️  待确认参数：
  1. 二甲苯异构体分配比例（当前用 O-XYLENE 代表）
  2. 反应器热工条件（当前假设等温 380°C，需确认）
    """)

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()

    try:
        app = win32com.client.GetActiveObject("HYSYS.Application")
        case = app.ActiveDocument
        if case is None:
            log("ERROR: 没有活动案例")
            return 1

        flowsheet = case.Flowsheet
        if flowsheet is None:
            log("ERROR: Flowsheet 不可用")
            return 1

        # ----------------------------------------------------------
        # 第一步：创建 Conversion Reactor
        # ----------------------------------------------------------
        # 【待验证】创建反应器的 COM API：
        # 可能的方式：
        #   flowsheet.Operations.Add("Conversion Reactor", name)
        #   flowsheet.Reactors.Add("Conversion", name)
        #   flowsheet.AddUnitOp("Conversion Reactor", name)

        reactor = None

        # 尝试方式 1: Operations.Add
        try:
            ops = flowsheet.Operations
            reactor = ops.Add("Conversion Reactor")
            reactor.Name = REACTOR_NAME
            log(f"[方式1] Operations.Add('Conversion Reactor') 成功")
        except Exception as exc:
            log(f"[方式1] 失败：{exc}")

        # 尝试方式 2: Reactors.Add
        if reactor is None:
            try:
                reactors = flowsheet.Reactors
                reactor = reactors.Add("Conversion")
                reactor.Name = REACTOR_NAME
                log(f"[方式2] Reactors.Add('Conversion') 成功")
            except Exception as exc:
                log(f"[方式2] 失败：{exc}")

        # 尝试方式 3: 查找已存在的反应器
        if reactor is None:
            try:
                reactors = flowsheet.Reactors
                for i in range(reactors.Count):
                    r = reactors.Item(i)
                    if r.Name == REACTOR_NAME:
                        reactor = r
                        log(f"[方式3] 找到已存在的反应器 {REACTOR_NAME}")
                        break
            except Exception:
                pass

        if reactor is None:
            log("ERROR: 无法创建 Conversion 反应器")
            log("请查阅 Help → Automation → Unit Operations → Reactors")
            return 1

        log(f"反应器已创建：{reactor.Name}")

        # ----------------------------------------------------------
        # 第二步：连接物流
        # ----------------------------------------------------------
        # 【待验证】连接进料/出料物流的 API：
        # 可能的方式：
        #   reactor.InletStreams.Add(feed_stream)
        #   reactor.SetInletStream(feed_stream)
        #   reactor.FeedStream = feed_stream

        feed_stream = None
        product_stream = None

        # 查找进料物流
        try:
            streams = flowsheet.MaterialStreams
            for i in range(streams.Count):
                s = streams.Item(i)
                if s.Name == FEED_STREAM_NAME:
                    feed_stream = s
                elif s.Name == PRODUCT_STREAM_NAME:
                    product_stream = s
        except Exception as exc:
            log(f"查找物流失败：{exc}")

        if feed_stream is None:
            log(f"ERROR: 找不到进料物流 '{FEED_STREAM_NAME}'，请先运行 05_create_streams.py")
            return 1

        log(f"进料物流：{feed_stream.Name}")
        if product_stream:
            log(f"出料物流：{product_stream.Name}")

        # 连接进料
        try:
            reactor.FeedStream = feed_stream
            log("进料物流已连接")
        except Exception:
            try:
                reactor.SetFeedStream(feed_stream)
                log("进料物流已连接（SetFeedStream）")
            except Exception as exc:
                log(f"连接进料失败：{exc}")

        # 连接出料
        if product_stream:
            try:
                reactor.ProductStream = product_stream
                log("出料物流已连接")
            except Exception:
                try:
                    reactor.SetProductStream(product_stream)
                    log("出料物流已连接（SetProductStream）")
                except Exception as exc:
                    log(f"连接出料失败：{exc}")

        # ----------------------------------------------------------
        # 第三步：关联反应集
        # ----------------------------------------------------------
        # 【待验证】关联反应集的 API

        try:
            reactor.ReactionSet = REACTION_SET_NAME
            log(f"反应集已关联：{REACTION_SET_NAME}")
        except Exception:
            try:
                reactor.SetReactionSet(REACTION_SET_NAME)
                log(f"反应集已关联（SetReactionSet）：{REACTION_SET_NAME}")
            except Exception as exc:
                log(f"关联反应集失败：{exc}")

        # ----------------------------------------------------------
        # 第四步：设置转化率
        # ----------------------------------------------------------
        # 【待验证】设置转化率的 API：
        # Conversion Reactor 需要指定：
        #   - 基准组分（TOLUENE）
        #   - 转化率（0.50）

        try:
            reactor.ConversionBasis = "TOLUENE"
            reactor.Conversion = TOLUENE_CONVERSION
            log(f"转化率已设置：TOLUENE = {TOLUENE_CONVERSION * 100}%")
        except Exception:
            try:
                reactor.SetConversion("TOLUENE", TOLUENE_CONVERSION)
                log(f"转化率已设置（SetConversion）：TOLUENE = {TOLUENE_CONVERSION * 100}%")
            except Exception as exc:
                log(f"设置转化率失败：{exc}")

        # ----------------------------------------------------------
        # 第五步：设置反应器模式（等温/绝热）
        # ----------------------------------------------------------
        if REACTOR_MODE == "isothermal":
            try:
                reactor.Temperature = REACTOR_TEMPERATURE_C + 273.15  # K
                log(f"反应器温度：{REACTOR_TEMPERATURE_C}°C")
            except Exception as exc:
                log(f"设置温度失败：{exc}")

        # ----------------------------------------------------------
        # 第六步：运行仿真
        # ----------------------------------------------------------
        log("\n--- 运行仿真 ---")

        try:
            # 方式 1：通过案例级别求解
            case.Solve()
            log("case.Solve() 完成")
        except Exception:
            try:
                # 方式 2：通过反应器求解
                reactor.Solve()
                log("reactor.Solve() 完成")
            except Exception as exc:
                log(f"求解失败：{exc}")

        # 检查收敛状态
        try:
            converged = reactor.IsConverged
            log(f"反应器收敛状态：{converged}")
        except Exception:
            try:
                converged = reactor.Converged
                log(f"反应器收敛状态：{converged}")
            except Exception:
                log("无法获取收敛状态")

        # ----------------------------------------------------------
        # 第七步：读取结果
        # ----------------------------------------------------------
        log("\n--- 仿真结果 ---")

        if product_stream is not None:
            try:
                # 读取温度
                try:
                    temp_c = product_stream.Temperature - 273.15
                    log(f"出料温度：{temp_c:.1f}°C")
                except Exception:
                    log("出料温度不可读")

                # 读取压力
                try:
                    pressure_kpa = product_stream.Pressure
                    log(f"出料压力：{pressure_kpa:.0f} kPa")
                except Exception:
                    log("出料压力不可读")

                # 读取总流量
                try:
                    molar_flow = product_stream.MolarFlow
                    log(f"出料摩尔流量：{molar_flow:.4f} kmol/h")
                except Exception:
                    log("出料流量不可读")

                # 读取组分摩尔分率
                log("\n出料组成（摩尔分率）：")
                try:
                    components = ["TOLUENE", "BENZENE", "O-XYLENE", "M-XYLENE", "P-XYLENE"]
                    for comp in components:
                        try:
                            frac = product_stream.ComponentMoleFraction(comp)
                            log(f"  {comp}: {frac:.4f}")
                        except Exception:
                            pass
                except Exception as exc:
                    log(f"读取组成失败：{exc}")

            except Exception as exc:
                log(f"读取结果失败：{exc}")
        else:
            log("无出料物流，无法读取结果")

        # ----------------------------------------------------------
        # 保存案例
        # ----------------------------------------------------------
        result_path = str(SCRIPT_DIR / "test_toluene_result.hsc")
        try:
            case.SaveAs(result_path)
            log(f"\n案例已保存：{result_path}")
        except Exception as exc:
            log(f"保存失败：{exc}")

        log("\n=== Conversion 反应器仿真完成 ===")
        log("""
后续步骤：
  1. 如果此脚本成功，将结果反馈给我，我会实现 ComHysysController
  2. 然后接入前后端，跑通完整流程
  3. 再依次实现 Equilibrium（甲烷重整）和 Gibbs（水煤浆气化）
        """)
        return 0

    except Exception as exc:
        log(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
