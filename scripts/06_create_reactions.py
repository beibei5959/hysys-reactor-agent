"""
步骤 06：创建反应和反应集
==========================
目标：在 HYSYS 中创建甲苯歧化反应及反应集。

反应：2 C7H8 → C6H6 + C8H10
  （2 甲苯 → 苯 + 二甲苯）

注意：二甲苯有三种异构体（邻/间/对），题目未指定分配比例。
      本脚本先创建总反应（C8H10 作为通用二甲苯），后续可能需要拆分。

运行前：步骤 03-04 已完成（组分已添加）。
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
# 甲苯歧化反应参数
# ============================================================
REACTION_NAME = "Toluene_Disproportionation"
REACTION_SET_NAME = "Toluene_RXN_Set"

# 反应计量系数（反应物为负，产物为正）
# 2 C7H8 → C6H6 + C8H10
STOICHIOMETRY = {
    "TOLUENE": -2.0,    # 反应物
    "BENZENE": 1.0,     # 产物
    # C8H10 在 HYSYS 中可能是 O-XYLENE / M-XYLENE / P-XYLENE
    # 先尝试用 O-XYLENE 作为代表（后续可修改分配）
    "O-XYLENE": 1.0,    # 产物（暂用邻二甲苯代表 C8H10）
}

# 待确认参数 ⚠️
# 1. 二甲苯异构体分配比例（题目未给出）
#    当前假设：全部为邻二甲苯（O-XYLENE）
#    实际可能需要：邻:间:对 = 某比例
# 2. 反应基准（Conversion Basis）
#    通常以关键反应物为基准，这里是以 TOLUENE 为基准

log("""
============================================================
️  待确认参数（不能擅自填写）：

1. 二甲苯异构体分配比例
   题目说"产物包含苯、邻/间/对二甲苯"，但未给出比例。
   当前脚本使用 O-XYLENE 作为代表，你可能需要修改为三种二甲苯的混合。
   常见工业比例：邻:间:对 ≈ 20:50:30（仅供参考，需确认）

2. 反应器热工条件
   题目给出进料温度 380°C，但未说明反应器是绝热还是等温。
   Conversion Reactor 需要指定：
   - 等温操作：指定反应器温度
   - 绝热操作：不指定温度，由能量平衡计算
   - 指定热负荷

============================================================
""")


def main():
    log("=== 创建反应和反应集 ===")

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()

    try:
        app = win32com.client.GetActiveObject("HYSYS.Application")
        case = app.ActiveDocument
        if case is None:
            log("ERROR: 没有活动案例")
            return 1

        # ----------------------------------------------------------
        # 探索 Reaction 相关的 COM 对象
        # ----------------------------------------------------------
        # HYSYS 中反应通常在 Environment 或单独的 Reactions 集合中管理

        # 尝试路径 1: case.Environment.Reactions
        reaction_manager = None

        try:
            env = case.Environment
            # 列出 Environment 的所有成员，找 Reaction 相关
            members = [m for m in dir(env) if not m.startswith("_")]
            rxn_members = [m for m in members if "rxn" in m.lower() or "react" in m.lower()]
            log(f"Environment 中反应相关成员：{rxn_members}")

            # 尝试常见属性名
            for attr in ["Reactions", "ReactionManager", "ReactionsFolder", "ReactionSets"]:
                try:
                    obj = getattr(env, attr)
                    log(f"  env.{attr} = {type(obj).__name__}")
                    reaction_manager = obj
                    break
                except Exception:
                    pass
        except Exception as exc:
            log(f"Environment 不可用：{exc}")

        # 尝试路径 2: case.Reactions
        if reaction_manager is None:
            try:
                reaction_manager = case.Reactions
                log(f"[路径2] case.Reactions = {type(reaction_manager).__name__}")
            except Exception as exc:
                log(f"[路径2] case.Reactions 不可用：{exc}")

        # 尝试路径 3: 通过 Flowsheet
        if reaction_manager is None:
            try:
                reaction_manager = case.Flowsheet.Reactions
                log(f"[路径3] Flowsheet.Reactions = {type(reaction_manager).__name__}")
            except Exception as exc:
                log(f"[路径3] Flowsheet.Reactions 不可用：{exc}")

        if reaction_manager is None:
            log("ERROR: 无法找到反应管理对象。")
            log("请查阅 Help → Automation → Reactions 相关章节。")
            log("也可以在 HYSYS 中手动创建反应，然后在此探索其 COM 路径。")
            return 1

        # ----------------------------------------------------------
        # 探索 reaction_manager 的方法
        # ----------------------------------------------------------
        members = [m for m in dir(reaction_manager) if not m.startswith("_")]
        log(f"\n反应管理对象的方法/属性：")
        for m in members[:50]:
            try:
                val = getattr(reaction_manager, m)
                if callable(val):
                    log(f"  {m}()")
                else:
                    log(f"  {m}: {type(val).__name__}")
            except Exception:
                log(f"  {m} (访问被拒)")

        # ----------------------------------------------------------
        # 创建反应（具体 API 取决于上面的探索结果）
        # ----------------------------------------------------------
        log("\n尝试创建反应...")

        # 可能的方式：
        # reaction_manager.AddReaction(name, stoichiometry)
        # reaction_manager.CreateReaction(name)
        # 或通过 ReactionSet 创建

        created = False

        # 尝试方式 1
        try:
            rxn = reaction_manager.Add(REACTION_NAME)
            log(f"[方式1] Add('{REACTION_NAME}') 成功")
            # 设置计量系数
            for comp, coeff in STOICHIOMETRY.items():
                try:
                    rxn.SetStoichiometricCoefficient(comp, coeff)
                    log(f"  {comp}: {coeff}")
                except Exception as exc:
                    log(f"  设置 {comp} 系数失败：{exc}")
            created = True
        except Exception as exc:
            log(f"[方式1] 失败：{exc}")

        if not created:
            log("\n无法自动创建反应。建议：")
            log("1. 在 HYSYS 中手动创建反应和反应集")
            log("2. 然后运行此脚本探索已创建对象的 COM 路径")
            log("3. 根据探索结果修改脚本")

        log("=== 反应创建完成 ===")
        log("下一步：运行 07_conversion_reactor.py 创建反应器并运行")
        return 0

    except Exception as exc:
        log(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
