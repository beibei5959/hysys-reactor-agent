"""
步骤 04：配置物性包
====================
目标：为测试案例配置 Peng-Robinson 物性包。

运行前：步骤 03 已完成（案例已创建，组分已添加）。
"""

import sys
import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def main():
    log("=== 配置物性包 ===")

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()

    try:
        app = win32com.client.GetActiveObject("HYSYS.Application")
        case = app.ActiveDocument
        if case is None:
            log("ERROR: 没有活动案例。请先运行 03 创建案例。")
            return 1

        log(f"活动案例：{case.Name}")

        # ----------------------------------------------------------
        # 配置物性包
        # ----------------------------------------------------------
        # 【待验证】物性包配置的 COM API：
        # 可能路径：
        #   case.Environment.PropertyPackage = "Peng-Robinson"
        #   case.PropertyPackages.Add("Peng-Robinson")
        #   case.Flowsheet.PropertyPackage = "Peng-Robinson"

        configured = False

        # 尝试路径 1：通过 Environment
        try:
            env = case.Environment
            pp = env.PropertyPackage
            log(f"当前物性包类型：{type(pp).__name__}")
            # 尝试设置
            try:
                pp.Name = "Peng-Robinson"
                log(f"[路径1] 物性包名称已设为 Peng-Robinson")
                configured = True
            except Exception as exc:
                log(f"[路径1] 设置名称失败：{exc}")
                # 尝试列出可用物性包
                try:
                    log(f"物性包属性：{dir(pp)}")
                except Exception:
                    pass
        except Exception as exc:
            log(f"[路径1] Environment 不可用：{exc}")

        # 尝试路径 2：通过 PropertyPackages 集合
        if not configured:
            try:
                pp_list = case.PropertyPackages
                log(f"PropertyPackages 类型：{type(pp_list).__name__}")
                try:
                    pp_list.Add("Peng-Robinson")
                    log(f"[路径2] Add(Peng-Robinson) 成功")
                    configured = True
                except Exception as exc:
                    log(f"[路径2] Add 失败：{exc}")
            except Exception as exc:
                log(f"[路径2] PropertyPackages 不可用：{exc}")

        if not configured:
            log("WARN: 物性包配置方式未确认。")
            log("请在 HYSYS 界面中手动确认物性包是否为 Peng-Robinson，")
            log("并查阅 Help → Automation 找到正确的 API。")
            log("你可以继续下一步，但需要确保物性包正确。")

        # 验证：读取当前物性包设置
        try:
            env = case.Environment
            pp = env.PropertyPackage
            log(f"当前物性包：{pp.Name}")
        except Exception:
            pass

        log("=== 物性包配置完成 ===")
        log("下一步：运行 05_create_streams.py 创建物流")
        return 0

    except Exception as exc:
        log(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
