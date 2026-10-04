"""Python 工作流入口：提交、查询、恢复和补充任务参数。"""

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from config.settings import Settings
from src.agent.llm import JsonLLM
from src.hysys.com_client import ComHysysController
from src.hysys.exceptions import HysysError
from src.hysys.mock_controller import MockHysysController
from src.runtime.service import TaskService
from src.runtime.store import TaskConflict, TaskStore
from src.runtime.telemetry import configure_logging, failure
from src.tools.hysys_tools import make_hysys_runner


def arguments():
    parser = argparse.ArgumentParser(description="AI 驱动 HYSYS 反应器智能选择系统")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--example", choices=["equilibrium", "conversion", "gibbs"])
    source.add_argument("--input", type=Path, help="结构化 JSON 输入")
    source.add_argument("--query", help="自然语言输入")
    source.add_argument("--status", help="查询任务 ID")
    source.add_argument("--resume", help="恢复中断的任务 ID")
    source.add_argument("--retry-explanation", help="只补做失败的 AI 解释，保留计算结果")
    source.add_argument("--amend", help="补充已结束任务的参数，创建新修订")
    source.add_argument("--purge-days", type=int, help="清理指定天数前的完成/失败任务")
    source.add_argument("--probe-com", action="store_true", help="只读连接诊断")
    parser.add_argument("--parameters", type=Path, help="与 --amend 配合使用的参数补丁文件")
    parser.add_argument("--task-id", help="提交幂等键；相同 ID 不重复执行")
    parser.add_argument("--data-dir", type=Path, default=Path("var"), help="本机任务和日志目录")
    parser.add_argument("--mode", choices=["mock", "real"])
    parser.add_argument("--json", action="store_true", help="输出任务结果 JSON")
    args = parser.parse_args()
    if bool(args.amend) != bool(args.parameters):
        parser.error("--amend 与 --parameters 必须配合使用")
    return args


def display(row, as_json):
    result = {
        "task_id": row["id"],
        "status": row["status"],
        "attempt": row["attempt"],
        "stage": row["stage"],
        "state": row["state"],
    }
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Task: {row['id']} | Status: {row['status']}")
        print(row["state"].get("final_answer") or f"Stage: {row['stage']}")


def main():
    # AUTO_REFERENCE_DISPATCH_V1
    if "--auto-reference" in __import__("sys").argv:
        from auto_reference_workflow import main as run_auto_reference
        return run_auto_reference()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = arguments()
    try:
        configure_logging(args.data_dir / "events.jsonl")
        if args.probe_com:
            controller = ComHysysController()
            try:
                controller.connect()
                print("Connection OK: HYSYS -> Active Case -> Flowsheet. Case not modified.")
            finally:
                controller.close()
            return 0
        store = TaskStore(args.data_dir / "tasks.sqlite3")
        if args.status:
            display(store.get(args.status), args.json)
            return 0
        if args.purge_days is not None:
            print(f"已清理 {store.purge(args.purge_days)} 个过期终止任务")
            return 0
        cfg = Settings.from_env()
        mode = args.mode or cfg.mode
        data = {}
        if args.example:
            data = json.loads(
                files("examples").joinpath(f"{args.example}.json").read_text(encoding="utf-8")
            )
        elif args.input:
            data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if args.example or args.input:
            if not isinstance(data, dict) or not isinstance(data.get("reaction_info"), dict):
                raise ValueError("结构化输入必须包含 reaction_info 对象")
        online = bool(args.query or args.retry_explanation)
        if args.resume:
            online = store.get(args.resume)["request"]["reaction_info"] is None
        llm = JsonLLM(cfg) if online else None
        service = TaskService(
            store,
            make_hysys_runner(MockHysysController if mode == "mock" else ComHysysController),
            llm,
            max_retries=cfg.max_retries if mode == "mock" else 0,
            deadline_seconds=cfg.task_timeout_seconds,
        )
        if args.resume:
            row = service.execute(args.resume)
        elif args.retry_explanation:
            row = service.retry_explanation(args.retry_explanation)
        elif args.amend:
            row = service.amend(
                args.amend,
                json.loads(args.parameters.read_text(encoding="utf-8-sig")),
                task_id=args.task_id,
            )
        else:
            row = service.submit(
                args.query or data.get("user_query", ""),
                data.get("reaction_info"),
                data.get("simulation_inputs", {}),
                task_id=args.task_id,
            )
        display(row, args.json)
        return {"completed": 0, "needs_input": 2}.get(row["status"], 1)
    except (ValueError, OSError, HysysError, TaskConflict) as exc:
        failure("command_failed", exc)
        message = (
            str(exc)
            if isinstance(exc, (HysysError, TaskConflict, ValueError))
            else type(exc).__name__
        )
        print("FAILED: " + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Task interrupted. Query persisted state with --status.", file=sys.stderr)
        return 130
    except Exception as exc:
        failure("command_failed", exc)
        print("FAILED. Check task records and diagnostics.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
