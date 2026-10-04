import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.agent.graph import initial_state
from src.hysys.mock_controller import MockHysysController
from src.runtime.service import TaskService
from src.runtime.store import TaskConflict, TaskStore
from src.tools.hysys_tools import make_hysys_runner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def data():
    return json.loads((ROOT / "examples/conversion.json").read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.sqlite3")


def submit(service, data, task_id="task"):
    return service.submit(
        data["user_query"], data["reaction_info"], data["simulation_inputs"], task_id=task_id
    )


def expire(store, task_id):
    with store.connect() as db:
        db.execute("UPDATE tasks SET lease_until=? WHERE id=?", (time.time() - 1, task_id))


def test_idempotent_submit_and_conflicting_input(store, data):
    calls = []
    runner = make_hysys_runner(MockHysysController)

    def counted(*args):
        calls.append(1)
        return runner(*args)

    service = TaskService(store, counted)
    assert submit(service, data)["status"] == "completed"
    assert submit(service, data)["attempt"] == 1
    assert len(calls) == 1
    data["reaction_info"]["pressure"] += 1
    with pytest.raises(TaskConflict):
        submit(service, data)


def test_restart_restores_checkpoint_without_recomputing(store, data):
    state = initial_state(data["user_query"], data["reaction_info"], data["simulation_inputs"])
    state.update(
        error_code="TASK_INTERRUPTED",
        selected_reactor="Conversion",
        validation_passed=True,
        simulation_status="success",
        simulation_results={"source": "mock", "workflow_verified": True},
    )
    store.create({}, state, "task")
    token = store.claim("task", 30)
    store.save("task", token, state, "explain_result")
    expire(store, "task")
    restarted = TaskService(TaskStore(store.path), lambda *args: pytest.fail("不应重复计算"))
    result = restarted.execute("task")
    assert result["status"] == "completed" and result["attempt"] == 2
    assert result["state"]["error_code"] is None


def test_resume_failed_parse_can_finish_explanation(store):
    state = initial_state("", {"conversion": 80})
    state.update(error="反应信息格式错误", simulation_status="failed")
    store.create({}, state, "task")
    token = store.claim("task", 30)
    store.save("task", token, state, "explain_result")
    expire(store, "task")
    row = TaskService(store, lambda *args: pytest.fail("不能执行模拟")).execute("task")
    assert row["status"] == "failed"
    assert "反应信息格式错误" in row["state"]["final_answer"]


def test_interrupted_external_operation_never_replayed(store):
    store.create({}, initial_state(""), "task")
    token = store.claim("task", 30)
    store.save("task", token, initial_state(""), "run_hysys", in_flight=True)
    expire(store, "task")
    with pytest.raises(TaskConflict, match="待核对"):
        TaskService(store, lambda *args: pytest.fail("不能重放")).execute("task")
    assert store.get("task")["status"] == "outcome_unknown"


def test_checkpoint_before_external_operation_is_resumable(store, data):
    state = initial_state(data["user_query"], data["reaction_info"], data["simulation_inputs"])
    state.update(selected_reactor="Conversion", validation_passed=True)
    store.create({}, state, "task")
    token = store.claim("task", 30)
    store.save("task", token, state, "run_hysys", in_flight=False)
    expire(store, "task")
    result = TaskService(store, make_hysys_runner(MockHysysController)).execute("task")
    assert result["status"] == "completed"


def test_only_one_concurrent_claim(store):
    store.create({}, initial_state(""), "task")

    def claim(_):
        try:
            return store.claim("task", 30)
        except TaskConflict:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(token is not None for token in pool.map(claim, range(4))) == 1


def test_cross_process_cannot_steal_active_task(store):
    store.create({}, initial_state(""), "task")
    store.claim("task", 30)
    code = "from src.runtime.store import TaskStore,TaskConflict; import sys\ntry: TaskStore(sys.argv[1]).claim('task',30)\nexcept TaskConflict: sys.exit(9)"
    result = subprocess.run(
        [sys.executable, "-c", code, str(store.path)], cwd=ROOT, capture_output=True
    )
    assert result.returncode == 9


def test_expired_owner_cannot_commit(store):
    state = initial_state("")
    store.create({}, state, "task")
    old = store.claim("task", 30)
    expire(store, "task")
    new = store.claim("task", 30)
    with pytest.raises(TaskConflict):
        store.save("task", old, state, "explain_result")
    store.save("task", new, state, "parse_reaction")


def test_cleanup_failure_preserves_success(store, data):
    class BadCleanup(MockHysysController):
        def close(self):
            raise RuntimeError("cleanup error")

    row = submit(TaskService(store, make_hysys_runner(BadCleanup)), data)
    assert row["status"] == "completed"
    assert row["state"]["cleanup_status"] == "failed"
    assert row["state"]["simulation_results"]["source"] == "mock"


def test_explanation_can_be_retried_without_simulation(store, data):
    class Unavailable:
        def explain(self, facts):
            raise RuntimeError("offline")

    row = submit(TaskService(store, make_hysys_runner(MockHysysController), Unavailable()), data)
    assert row["state"]["explanation_status"] == "degraded"

    class Available:
        def explain(self, facts):
            return "转化反应器，Mock流程已完成。"

    row = TaskService(store, lambda *a: pytest.fail("不能重算"), Available()).retry_explanation(
        "task"
    )
    assert row["state"]["explanation_status"] == "success" and row["attempt"] == 2


def test_amend_invalidates_results_and_preserves_parent(store, data):
    service = TaskService(store, make_hysys_runner(MockHysysController))
    original = submit(service, data)
    revised = service.amend("task", {"reaction_info": {"pressure": None}}, task_id="revision")
    assert revised["status"] == "needs_input"
    assert revised["state"]["simulation_results"] == {}
    assert revised["request"]["parent_id"] == "task"
    assert store.get("task")["state"] == original["state"]


def test_purge_preserves_pending_unknown_and_waiting(store):
    for status in ["completed", "failed", "pending", "needs_input", "outcome_unknown"]:
        store.create({}, initial_state(""), status)
        with store.connect() as db:
            db.execute(
                "UPDATE tasks SET status=?,updated=? WHERE id=?",
                (status, time.time() - 864000, status),
            )
    assert store.purge(5) == 2
    assert store.get("needs_input")["status"] == "needs_input"
    assert store.get("outcome_unknown")["status"] == "outcome_unknown"


def test_cli_persistence_and_real_mode_preflight(tmp_path):
    command = [sys.executable, str(ROOT / "app.py"), "--data-dir", str(tmp_path), "--json"]
    first = subprocess.run(
        command + ["--example", "gibbs", "--task-id", "cli"],
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    assert first.returncode == 0
    assert json.loads(first.stdout)["state"]["selected_reactor"] == "Gibbs"
    cached = subprocess.run(
        command + ["--resume", "cli"], capture_output=True, encoding="utf-8", cwd=ROOT
    )
    assert json.loads(cached.stdout)["attempt"] == 1
    real = subprocess.run(
        command + ["--query", "test", "--mode", "real"],
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    assert real.returncode == 1 and "真实计算适配器未就绪" in real.stderr
