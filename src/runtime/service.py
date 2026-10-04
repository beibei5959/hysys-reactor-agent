"""单机同步任务执行；节点快照与操作执行权独立于图的内存状态。"""

import random
import threading
import time

from src.agent.graph import build_graph, initial_state, next_stage
from src.models.reaction import ReactionInfo
from src.runtime.store import TaskConflict
from src.runtime.telemetry import failure, task_context


class TaskService:
    def __init__(
        self, store, runner, llm=None, *, max_retries=2, lease_seconds=30, deadline_seconds=240
    ):
        if lease_seconds < 0.1 or deadline_seconds <= 0:
            raise ValueError("租约和执行时限必须为正数")
        self.store, self.runner, self.llm = store, runner, llm
        self.max_retries = max_retries
        self.lease_seconds = lease_seconds
        self.deadline_seconds = deadline_seconds

    def submit(
        self, query, reaction_info=None, simulation_inputs=None, *, task_id=None, parent_id=None
    ):
        if not isinstance(query, str) or len(query) > 20000:
            raise ValueError("用户描述必须为字符串，最长20000字符")
        request = {
            "user_query": query,
            "reaction_info": reaction_info,
            "simulation_inputs": simulation_inputs or {},
            "parent_id": parent_id,
        }
        task_id = self.store.create(
            request, initial_state(query, reaction_info, simulation_inputs), task_id
        )
        return self.execute(task_id)

    def retry_explanation(self, task_id):
        self.store.retry_explanation(task_id)
        return self.execute(task_id)

    def amend(self, parent_id, patch, *, task_id=None):
        parent = self.store.get(parent_id)
        if parent["status"] not in {"needs_input", "completed", "failed"}:
            raise TaskConflict("仅可修改已结束任务的输入；运行中或结果待核对的任务不可修改")
        if not isinstance(patch, dict) or not set(patch) <= {"reaction_info", "simulation_inputs"}:
            raise ValueError("参数文件只允许 reaction_info 和 simulation_inputs")
        if any(not isinstance(v, dict) for v in patch.values()):
            raise ValueError("补充参数必须为对象")
        previous = parent["state"]
        info = {**(previous.get("reaction_info") or {}), **patch.get("reaction_info", {})}
        inputs = {**previous.get("simulation_inputs", {}), **patch.get("simulation_inputs", {})}
        return self.submit(
            parent["request"]["user_query"], info, inputs, task_id=task_id, parent_id=parent_id
        )

    def execute(self, task_id):
        token = self.store.claim(task_id, self.lease_seconds)
        if token is None:
            return self.store.get(task_id)
        row = self.store.get(task_id)
        state, stage = row["state"], row["stage"]
        if state.get("error_code") == "TASK_INTERRUPTED":
            state["error_code"] = None
        stopped, lost = threading.Event(), threading.Event()
        deadline = time.monotonic() + self.deadline_seconds
        context = task_context.set({"task_id": task_id, "attempt": row["attempt"]})

        def heartbeat():
            while not stopped.wait(self.lease_seconds / 3):
                try:
                    self.store.heartbeat(task_id, token, self.lease_seconds)
                except Exception:
                    lost.set()
                    return

        thread = threading.Thread(target=heartbeat, daemon=True, name="task-heartbeat")
        thread.start()

        def observe(when, name, snapshot):
            nonlocal state, stage
            if lost.is_set():
                raise TaskConflict("任务执行权已失效")
            if when == "before":
                if time.monotonic() >= deadline and name != "explain_result":
                    raise TimeoutError("任务执行预算已用尽")
                self.store.save(task_id, token, snapshot, name, in_flight=True)
                stage = name
            else:
                following = next_stage(name, snapshot)
                self.store.save(task_id, token, snapshot, following)
                state, stage = snapshot, following
                # 重试退避统一在节点外执行，避免阻塞 web 线程池的 worker slot；
                # 仅在未超时时才 sleep，超时让下一节点的 before 钩子抛 TimeoutError。
                if (
                    following == "run_hysys"
                    and snapshot.get("simulation_status") == "retrying"
                    and time.monotonic() < deadline
                ):
                    retry_count = snapshot.get("retry_count", 1)
                    backoff = random.uniform(0, min(2 ** (retry_count - 1), 4))
                    time.sleep(min(backoff, max(0, deadline - time.monotonic())))

        try:
            if (
                state.get("reaction_info") is not None
                and stage != "parse_reaction"
                and not state.get("error")
            ):
                state["reaction_info"] = ReactionInfo.model_validate(state["reaction_info"])
            if self.llm and hasattr(self.llm, "begin"):
                self.llm.begin(deadline, state.get("llm_trace", []))
            graph = build_graph(
                self.runner,
                self.llm,
                self.max_retries,
                start_at=stage or "explain_result",
                observer=observe,
            )
            state = graph.invoke(state, config={"recursion_limit": 20})
            status = {
                "success": "completed",
                "needs_input": "needs_input",
                "outcome_unknown": "outcome_unknown",
            }.get(state["simulation_status"], "failed")
            self.store.save(task_id, token, state, None, status, release=True)
        except BaseException as exc:
            failure("task_interrupted", exc)
            status = "outcome_unknown" if stage == "run_hysys" else "interrupted"
            state = {
                **state,
                "error_code": "OUTCOME_UNKNOWN"
                if status == "outcome_unknown"
                else "TASK_INTERRUPTED",
            }
            try:
                self.store.save(
                    task_id, token, state, stage, status, release=status != "outcome_unknown"
                )
            except Exception as persistence_error:
                failure("interruption_persistence_failed", persistence_error)
            raise
        finally:
            stopped.set()
            thread.join(timeout=2)
            task_context.reset(context)
        return self.store.get(task_id)
