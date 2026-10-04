"""
步骤 05：创建进料/出料物流
============================
目标：在 HYSYS 中创建甲苯歧化场景的进料物流和出料物流。

甲苯歧化场景参数：
  - 甲苯进料：1000 kg/h → 约 10.85 kmol/h（甲苯 MW=92.14）
  - 进料温度：380°C = 653.15 K
  - 操作压力：2.5 MPa = 2500 kPa（绝压）
  - 进料组成：纯甲苯（摩尔分率 1.0）

出料物流由反应器计算得出，此处先创建占位物流。

运行前：步骤 03-04 已完成。
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
# 甲苯歧化场景参数
# ============================================================
FEED_NAME = "FEED"
PRODUCT_NAME = "PRODUCT"

FEED_TEMPERATURE_C = 380.0       # °C → 653.15 K
FEED_PRESSURE_KPA = 2500.0       # 2.5 MPa → 2500 kPa
FEED_FLOW_KG_H = 1000.0          # kg/h
TOLUENE_MW = 92.14               # g/mol (C7H8)
FEED_FLOW_KMOL_H = FEED_FLOW_KG_H / TOLUENE_MW  # ≈ 10.85 kmol/h

# 进料组成：纯甲苯
FEED_COMPOSITION = {"TOLUENE": 1.0}


def main():
    log("=== 创建物流 ===")
    log(f"进料温度：{FEED_TEMPERATURE_C}°C = {FEED_TEMPERATURE_C + 273.15} K")
    log(f"进料压力：{FEED_PRESSURE_KPA} kPa (2.5 MPa)")
    log(f"进料流量：{FEED_FLOW_KG_H} kg/h = {FEED_FLOW_KMOL_H:.4f} kmol/h")
    log(f"进料组成：{FEED_COMPOSITION}")

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

        streams = flowsheet.MaterialStreams
        log(f"当前物流数量：{streams.Count}")

        # ----------------------------------------------------------
        # 创建进料物流
        # ----------------------------------------------------------
        # 【待验证】创建物流的 COM API：
        # 可能的方式：
        #   streams.Add() → 返回新物流对象
        #   streams.Add("FEED") → 指定名称
        #   flowsheet.CreateStream("FEED")

        feed_stream = None

        # 尝试方式 1: streams.Add()
        try:
            feed_stream = streams.Add()
            feed_stream.Name = FEED_NAME
            log(f"[方式1] streams.Add() 成功，设置名称为 {FEED_NAME}")
        except Exception as exc:
            log(f"[方式1] streams.Add() 失败：{exc}")

        # 尝试方式 2: streams.Add(name)
        if feed_stream is None:
            try:
                feed_stream = streams.Add(FEED_NAME)
                log(f"[方式2] streams.Add('{FEED_NAME}') 成功")
            except Exception as exc:
                log(f"[方式2] streams.Add(name) 失败：{exc}")

        # 尝试方式 3: 查找已存在的物流
        if feed_stream is None:
            try:
                for i in range(streams.Count):
                    s = streams.Item(i)
                    if s.Name == FEED_NAME:
                        feed_stream = s
                        log(f"[方式3] 找到已存在的物流 {FEED_NAME}")
                        break
            except Exception:
                pass

        if feed_stream is None:
            log("ERROR: 无法创建进料物流")
            return 1

        log(f"进料物流已创建：{feed_stream.Name}")

        # ----------------------------------------------------------
        # 设置物流参数
        # ----------------------------------------------------------
        # 【待验证】设置物流温度、压力、流量、组成的 API
        # HYSYS 中通常通过 TPFlash 或属性设置

        # 尝试设置温度
        try:
            # HYSYS 内部单位通常是 °C 或 K
            feed_stream.TemperatureValue = FEED_TEMPERATURE_C + 273.15  # K
            log(f"  温度：{FEED_TEMPERATURE_C + 273.15} K")
        except Exception as exc:
            log(f"  设置温度失败（方式1）：{exc}")
            try:
                feed_stream.Temperature = FEED_TEMPERATURE_C  # °C
                log(f"  温度：{FEED_TEMPERATURE_C}°C（方式2）")
            except Exception as exc2:
                log(f"  设置温度失败（方式2）：{exc2}")

        # 尝试设置压力
        try:
            feed_stream.PressureValue = FEED_PRESSURE_KPA  # kPa
            log(f"  压力：{FEED_PRESSURE_KPA} kPa")
        except Exception as exc:
            log(f"  设置压力失败（方式1）：{exc}")
            try:
                feed_stream.Pressure = FEED_PRESSURE_KPA
                log(f"  压力：{FEED_PRESSURE_KPA} kPa（方式2）")
            except Exception as exc2:
                log(f"  设置压力失败（方式2）：{exc2}")

        # 尝试设置流量
        try:
            feed_stream.MolarFlowValue = FEED_FLOW_KMOL_H  # kmol/h
            log(f"  摩尔流量：{FEED_FLOW_KMOL_H:.4f} kmol/h")
        except Exception as exc:
            log(f"  设置摩尔流量失败：{exc}")
            try:
                feed_stream.MolarFlow = FEED_FLOW_KMOL_H
                log(f"  摩尔流量：{FEED_FLOW_KMOL_H:.4f} kmol/h（方式2）")
            except Exception as exc2:
                log(f"  设置摩尔流量失败（方式2）：{exc2}")

        # 尝试设置组成
        for comp_name, mole_frac in FEED_COMPOSITION.items():
            try:
                feed_stream.ComponentMoleFraction(comp_name) = mole_frac
                log(f"  组成 {comp_name} = {mole_frac}")
            except Exception:
                try:
                    feed_stream.SetComponentMoleFraction(comp_name, mole_frac)
                    log(f"  组成 {comp_name} = {mole_frac}（SetComponentMoleFraction）")
                except Exception as exc:
                    log(f"  设置组成 {comp_name} 失败：{exc}")

        # ----------------------------------------------------------
        # 创建出料物流（占位，后续由反应器连接）
        # ----------------------------------------------------------
        product_stream = None
        try:
            product_stream = streams.Add()
            product_stream.Name = PRODUCT_NAME
            log(f"\n出料物流已创建：{PRODUCT_NAME}")
        except Exception as exc:
            log(f"\n出料物流创建失败：{exc}（可后续手动创建）")

        log(f"\n当前物流总数：{streams.Count}")

        # 列出所有物流
        for i in range(streams.Count):
            s = streams.Item(i)
            log(f"  [{i}] {s.Name}")

        log("=== 物流创建完成 ===")
        log("下一步：运行 06_create_reactions.py 创建反应和反应集")
        return 0

    except Exception as exc:
        log(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
