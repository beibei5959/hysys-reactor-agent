"""
步骤 01：只读连接诊断
=====================
目标：验证 Python → pywin32 → HYSYS COM 连接链路。
不创建、不修改任何案例。

预期输出：
  - HYSYS 版本号
  - 活动案例名称
  - Flowsheet 对象类型
  - 如果失败，记录错误类型和原因

运行前：确保 HYSYS 已打开（可以有空白案例或无案例）。
"""

import sys
import datetime


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def main():
    log("=== HYSYS 连接诊断 ===")
    log(f"Python 版本：{sys.version}")

    # 1. 检查 pywin32
    try:
        import pythoncom
        import win32com.client
        log("pywin32 可用")
    except ImportError as exc:
        log(f"FAIL: pywin32 未安装 - {exc}")
        log("请运行: pip install pywin32")
        return 1

    # 2. 初始化 COM
    pythoncom.CoInitialize()
    log("COM 初始化成功")

    try:
        # 3. 连接 HYSYS
        app = win32com.client.GetActiveObject("HYSYS.Application")
        log(f"HYSYS 应用对象类型：{type(app).__name__}")

        # 4. 尝试获取版本信息
        try:
            version = app.Version
            log(f"HYSYS 版本：{version}")
        except Exception as exc:
            log(f"版本属性不可用：{exc}")

        # 5. 检查活动案例
        case = app.ActiveDocument
        if case is None:
            log("WARN: 没有活动案例（请先在 HYSYS 中打开或创建一个案例）")
        else:
            log(f"活动案例类型：{type(case).__name__}")
            try:
                case_name = case.Name
                log(f"活动案例名称：{case_name}")
            except Exception as exc:
                log(f"案例名称属性不可用：{exc}")

            # 6. 检查 Flowsheet
            flowsheet = case.Flowsheet
            if flowsheet is None:
                log("WARN: Flowsheet 为 None")
            else:
                log(f"Flowsheet 类型：{type(flowsheet).__name__}")
                # 探索 Flowsheet 的关键子对象
                try:
                    streams = flowsheet.MaterialStreams
                    log(f"MaterialStreams 类型：{type(streams).__name__}")
                    log(f"物流数量：{streams.Count}")
                except Exception as exc:
                    log(f"MaterialStreams 不可用：{exc}")

                try:
                    operations = flowsheet.Operations
                    log(f"Operations 类型：{type(operations).__name__}")
                    log(f"单元操作数量：{operations.Count}")
                except Exception as exc:
                    log(f"Operations 不可用：{exc}")

                try:
                    energy_streams = flowsheet.EnergyStreams
                    log(f"EnergyStreams 类型：{type(energy_streams).__name__}")
                    log(f"能量流数量：{energy_streams.Count}")
                except Exception as exc:
                    log(f"EnergyStreams 不可用：{exc}")

                try:
                    reactors = flowsheet.Reactors
                    log(f"Reactors 类型：{type(reactors).__name__}")
                    log(f"反应器数量：{reactors.Count}")
                except Exception as exc:
                    log(f"Reactors 不可用：{exc}")

    except Exception as exc:
        log(f"FAIL: 连接 HYSYS 失败 - {type(exc).__name__}: {exc}")
        log("可能原因：")
        log("  1. HYSYS 未运行")
        log("  2. Python 与 HYSYS 位数不匹配（都是 64 位或都是 32 位）")
        log("  3. 用户权限不足")
        return 1
    finally:
        pythoncom.CoUninitialize()
        log("COM 已释放")

    log("=== 连接诊断完成 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
