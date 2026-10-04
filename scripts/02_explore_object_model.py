"""
步骤 02：探索 COM 对象模型
===========================
目标：列出 HYSYS 关键 COM 对象的所有属性和方法，找到正确的 API 路径。
不修改任何数据，只读探索。

输出保存到 api_evidence.md，供后续脚本参考。

运行前：HYSYS 已打开，有活动案例。
"""

import sys
import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_FILE = SCRIPT_DIR / "api_evidence.md"


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def explore_object(obj, name, depth=0, max_depth=2):
    """递归探索 COM 对象的属性和方法。"""
    indent = "  " * depth
    results = []

    if depth > max_depth:
        return results

    try:
        members = dir(obj)
    except Exception as exc:
        results.append(f"{indent}{name}: dir() 失败 - {exc}")
        return results

    # 分类属性和方法
    props = []
    methods = []
    collections = []

    for attr in sorted(members):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(obj, attr)
            val_type = type(val).__name__
            # 判断类型
            if callable(val):
                methods.append(f"{attr}()")
            elif val_type in ("int", "float", "str", "bool"):
                props.append(f"{attr} = {val!r}")
            elif hasattr(val, "Count"):
                try:
                    count = val.Count
                    collections.append(f"{attr} (Count={count})")
                except Exception:
                    collections.append(f"{attr} (集合)")
            else:
                props.append(f"{attr}: {val_type}")
        except Exception:
            props.append(f"{attr} (访问被拒)")

    if collections:
        results.append(f"{indent}{name} [集合]:")
        for c in collections:
            results.append(f"{indent}  - {c}")
    if methods:
        results.append(f"{indent}{name} [方法]:")
        for m in methods[:30]:  # 限制数量
            results.append(f"{indent}  - {m}")
        if len(methods) > 30:
            results.append(f"{indent}  ... 还有 {len(methods) - 30} 个方法")
    if props:
        results.append(f"{indent}{name} [属性]:")
        for p in props[:30]:
            results.append(f"{indent}  - {p}")
        if len(props) > 30:
            results.append(f"{indent}  ... 还有 {len(props) - 30} 个属性")

    return results


def main():
    log("=== HYSYS COM 对象模型探索 ===")
    evidence_lines = [
        f"# HYSYS COM API 证据记录",
        f"探索日期：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
    ]

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
            log("ERROR: Flowsheet 为 None")
            return 1

        # 探索层级
        objects_to_explore = [
            (app, "HYSYS.Application"),
            (case, "SimulationCase"),
            (flowsheet, "Flowsheet"),
        ]

        # 探索物流集合中的第一个对象
        try:
            streams = flowsheet.MaterialStreams
            if streams.Count > 0:
                objects_to_explore.append((streams, "MaterialStreams (集合)"))
                # 尝试获取第一个物流
                try:
                    first_stream = streams.Item(0)
                    objects_to_explore.append((first_stream, "MaterialStream (第一个物流)"))
                except Exception:
                    try:
                        first_stream = streams[0]
                        objects_to_explore.append((first_stream, "MaterialStream (第一个物流)"))
                    except Exception:
                        log("WARN: 无法获取第一个物流对象")
        except Exception as exc:
            log(f"WARN: MaterialStreams 不可用 - {exc}")

        # 探索单元操作集合
        try:
            ops = flowsheet.Operations
            objects_to_explore.append((ops, "Operations (集合)"))
        except Exception as exc:
            log(f"WARN: Operations 不可用 - {exc}")

        # 探索反应器
        try:
            reactors = flowsheet.Reactors
            objects_to_explore.append((reactors, "Reactors (集合)"))
        except Exception as exc:
            log(f"WARN: Reactors 不可用 - {exc}")

        # 探索 Environment（组分/物性）
        try:
            env = case.Environment
            objects_to_explore.append((env, "Environment (组分/物性环境)"))
        except Exception:
            try:
                env = flowsheet.Environment
                objects_to_explore.append((env, "Flowsheet.Environment"))
            except Exception as exc:
                log(f"WARN: Environment 不可用 - {exc}")

        # 逐个探索
        all_results = []
        for obj, name in objects_to_explore:
            log(f"探索 {name} ...")
            results = explore_object(obj, name, depth=0, max_depth=1)
            all_results.extend(results)
            evidence_lines.append(f"## {name}")
            evidence_lines.append("```")
            for line in results:
                evidence_lines.append(line)
            evidence_lines.append("```")
            evidence_lines.append("")
            log(f"  发现 {len(results)} 行信息")

        # 保存证据
        evidence_text = "\n".join(evidence_lines)
        EVIDENCE_FILE.write_text(evidence_text, encoding="utf-8")
        log(f"\n证据已保存到：{EVIDENCE_FILE}")
        log(f"请打开该文件，找到创建物流、反应器相关的方法名，反馈给我。")

    except Exception as exc:
        log(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        pythoncom.CoUninitialize()

    log("=== 探索完成 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
