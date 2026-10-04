"""
步骤 03：创建新测试案例 + 添加组分
===================================
目标：在 HYSYS 中创建一个新的空白案例，并添加甲苯歧化所需的组分。

甲苯歧化场景（Conversion Reactor）所需组分：
  - TOLUENE（甲苯，C7H8）
  - BENZENE（苯，C6H6）
  - O-XYLENE（邻二甲苯）
  - M-XYLENE（间二甲苯）
  - P-XYLENE（对二甲苯）

运行前：HYSYS 已打开，步骤 01 和 02 已通过。

注意：此脚本创建新案例，不影响你手动建立的甲苯歧化案例。
"""

import sys
import datetime

SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ============================================================
# 配置区：根据步骤 02 探索结果修改下面的 API 调用方式
# ============================================================

# 甲苯歧化所需组分列表（HYSYS 中的标准名称）
COMPONENTS = [
    "TOLUENE",
    "BENZENE",
    "O-XYLENE",
    "M-XYLENE",
    "P-XYLENE",
]


def main():
    log("=== 创建测试案例 + 添加组分 ===")

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()

    try:
        app = win32com.client.GetActiveObject("HYSYS.Application")
        log(f"HYSYS 已连接")

        # ----------------------------------------------------------
        # 第一步：创建新案例
        # ----------------------------------------------------------
        # 【待验证】创建案例的 COM API 路径未知，以下有多种可能：
        # 方案 A: app.CreateCase()
        # 方案 B: app.Documents.Add()
        # 方案 C: win32com.client.Dispatch("HYSYS.SimulationCase")
        # 方案 D: 打开一个模板文件

        case = None

        # 尝试方案 A
        try:
            case = app.CreateCase()
            log(f"[方案A] CreateCase() 成功，类型：{type(case).__name__}")
        except Exception as exc:
            log(f"[方案A] CreateCase() 失败：{exc}")

        # 尝试方案 B
        if case is None:
            try:
                case = app.Documents.Add()
                log(f"[方案B] Documents.Add() 成功，类型：{type(case).__name__}")
            except Exception as exc:
                log(f"[方案B] Documents.Add() 失败：{exc}")

        # 尝试方案 C
        if case is None:
            try:
                case = win32com.client.Dispatch("HYSYS.SimulationCase")
                log(f"[方案C] Dispatch SimulationCase 成功，类型：{type(case).__name__}")
            except Exception as exc:
                log(f"[方案C] Dispatch 失败：{exc}")

        if case is None:
            log("ERROR: 所有创建案例的方案都失败了。")
            log("请检查 HYSYS Help → Automation 文档中创建案例的正确方法。")
            return 1

        log(f"新案例已创建")

        # ----------------------------------------------------------
        # 第二步：访问组分列表
        # ----------------------------------------------------------
        # 【待验证】组分管理的 COM API 路径：
        # 通常路径：case.Environment → ComponentList
        # 或：case.Flowsheet.Environment → ComponentList

        component_list = None

        # 尝试路径 1
        try:
            env = case.Environment
            component_list = env.ComponentList
            log(f"[路径1] case.Environment.ComponentList 成功")
        except Exception as exc:
            log(f"[路径1] case.Environment 失败：{exc}")

        # 尝试路径 2
        if component_list is None:
            try:
                env = case.Flowsheet.Environment
                component_list = env.ComponentList
                log(f"[路径2] case.Flowsheet.Environment.ComponentList 成功")
            except Exception as exc:
                log(f"[路径2] Flowsheet.Environment 失败：{exc}")

        # 尝试路径 3
        if component_list is None:
            try:
                comp_lists = case.ComponentLists
                component_list = comp_lists.Item(0)  # 使用第一个组分列表
                log(f"[路径3] case.ComponentLists.Item(0) 成功")
            except Exception as exc:
                log(f"[路径3] case.ComponentLists 失败：{exc}")

        if component_list is None:
            log("ERROR: 无法访问组分列表。请查阅 Help → Automation 中组分管理 API。")
            return 1

        # ----------------------------------------------------------
        # 第三步：添加组分
        # ----------------------------------------------------------
        # 【待验证】添加组分的方法：
        # 可能的方式：
        #   component_list.Add("TOLUENE")
        #   component_list.AddComponent("TOLUENE")
        #   component_list.Components.Add("TOLUENE")

        added = []
        failed = []

        for comp_name in COMPONENTS:
            success = False

            # 尝试方式 1: Add
            if not success:
                try:
                    component_list.Add(comp_name)
                    log(f"  添加 {comp_name}: Add() 成功")
                    added.append(comp_name)
                    success = True
                except Exception as exc:
                    pass  # 静默尝试下一个方式

            # 尝试方式 2: AddComponent
            if not success:
                try:
                    component_list.AddComponent(comp_name)
                    log(f"  添加 {comp_name}: AddComponent() 成功")
                    added.append(comp_name)
                    success = True
                except Exception as exc:
                    pass

            # 尝试方式 3: Components.Add
            if not success:
                try:
                    component_list.Components.Add(comp_name)
                    log(f"  添加 {comp_name}: Components.Add() 成功")
                    added.append(comp_name)
                    success = True
                except Exception as exc:
                    pass

            if not success:
                log(f"  添加 {comp_name}: 所有方式都失败")
                failed.append(comp_name)

        log(f"\n结果：成功 {len(added)}/{len(COMPONENTS)}，失败 {len(failed)}")
        if failed:
            log(f"失败组分：{failed}")
            log("可能原因：组分名称格式不对（HYSYS 可能要求化学式而非名称）")
            log("尝试用化学式：C7H8, C6H6 等")
            return 1

        # ----------------------------------------------------------
        # 第四步：保存案例
        # ----------------------------------------------------------
        test_case_path = str(SCRIPT_DIR / "test_toluene_disproportionation.hsc")
        try:
            case.SaveAs(test_case_path)
            log(f"案例已保存：{test_case_path}")
        except Exception as exc:
            log(f"保存失败：{exc}（案例仍可在 HYSYS 中手动保存）")

        log("=== 组分添加完成 ===")
        log("下一步：运行 04_property_package.py 配置物性包")
        return 0

    except Exception as exc:
        log(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
