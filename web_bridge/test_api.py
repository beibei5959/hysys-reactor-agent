"""接口集成测试：真实 SQLite、实际工程节点与 Mock 控制器。"""

import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from web_bridge.api import ROOT, create_app

PASSWORD = "testing-only-password-123"
ORIGIN = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, llm_factory=lambda: None)
    app.state.accounts.create_user("alice", PASSWORD)
    app.state.accounts.create_user("bob", PASSWORD)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client


def login(client, name="alice"):
    response = client.post(
        "/api/login", json={"username": name, "password": PASSWORD}, headers=ORIGIN
    )
    assert response.status_code == 200
    return {**ORIGIN, "X-CSRF-Token": response.json()["csrf"]}


def wait(client, task_id):
    for _ in range(200):
        row = client.get(f"/api/tasks/{task_id}").json()
        if row["status"] not in {"pending", "running"}:
            return row
        time.sleep(0.01)
    pytest.fail("任务未在测试期限内结束")


@pytest.mark.parametrize(
    "name,reactor",
    [("conversion", "Conversion"), ("equilibrium", "Equilibrium"), ("gibbs", "Gibbs")],
)
def test_confirmed_flow_and_idempotency(client, name, reactor):
    headers = login(client)
    example = json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))
    body = {
        "query": example["user_query"],
        "reaction_info": example["reaction_info"],
        "simulation_inputs": example["simulation_inputs"],
        "idempotency_key": uuid4().hex,
    }
    response = client.post("/api/tasks", json=body, headers=headers)
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    row = wait(client, task_id)
    assert row["status"] == "awaiting_confirmation"
    assert row["state"]["selected_reactor"] == reactor
    assert not row["state"]["simulation_results"]
    duplicate = client.post("/api/tasks", json=body, headers=headers)
    assert duplicate.json()["id"] == task_id
    conflict = client.post("/api/tasks", json={**body, "query": "changed"}, headers=headers)
    assert conflict.status_code == 409
    run_body = {k: body[k] for k in ("reaction_info", "simulation_inputs")}
    run_body["idempotency_key"] = uuid4().hex
    response = client.post(f"/api/tasks/{task_id}/run", json=run_body, headers=headers)
    assert response.status_code == 202, response.text
    result = wait(client, response.json()["id"])
    assert result["status"] == "completed", result
    assert result["state"]["simulation_results"]["source"] == "mock"
    assert result["state"]["simulation_results"]["converged"] is None
    assert result["parent_id"] == task_id
    assert result["revision"] == 1
    assert result["root_id"] == task_id
    assert (
        client.post(f"/api/tasks/{task_id}/run", json=run_body, headers=headers).json()["id"]
        == result["id"]
    )
    assert len(client.get("/api/tasks").json()) == 2


def test_auth_isolation_csrf_logout(client):
    assert client.get("/api/tasks").status_code == 401
    headers = login(client)
    response = client.post(
        "/api/tasks", json={"query": "test", "idempotency_key": "one"}, headers=ORIGIN
    )
    assert response.status_code == 403
    response = client.post(
        "/api/tasks", json={"query": "test", "idempotency_key": "one"}, headers=headers
    )
    task_id = response.json()["id"]
    wait(client, task_id)
    original_cookie = client.cookies.get("hysys_session")
    assert client.post("/api/logout", headers=headers).status_code == 200
    assert client.get("/api/session").status_code == 401
    headers = login(client, "bob")
    assert client.get("/api/tasks").json() == []
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
    assert client.post(f"/api/tasks/{task_id}/resume", headers=headers).status_code == 404
    client.cookies.set("hysys_session", original_cookie, domain="127.0.0.1", path="/")
    assert client.get("/api/session").status_code == 401


def test_missing_parameters_and_invalid_input(client):
    headers = login(client)
    response = client.post(
        "/api/tasks",
        json={
            "query": "明确转化率",
            "reaction_info": {"conversion": 0.8},
            "idempotency_key": "missing",
        },
        headers=headers,
    )
    row = wait(client, response.json()["id"])
    assert row["status"] == "needs_input"
    assert row["state"]["missing_parameters"]
    assert not row["state"]["simulation_results"]
    response = client.post(
        "/api/login",
        json={"username": "a", "password": "SECRET", "extra": "SECRET"},
        headers=ORIGIN,
    )
    assert response.status_code == 422
    assert "SECRET" not in response.text
    assert (
        client.post("/api/logout", headers={**headers, "Origin": "http://evil.example"}).status_code
        == 403
    )


def test_persistence_and_unknown_outcome(client):
    headers = login(client)
    response = client.post(
        "/api/tasks", json={"query": "test", "idempotency_key": "restart"}, headers=headers
    )
    task_id = response.json()["id"]
    wait(client, task_id)
    with client.app.state.store.transaction() as db:
        db.execute(
            "UPDATE tasks SET status='running',stage='run_hysys',owner='old',lease_until=0,in_flight=1 WHERE id=?",
            (task_id,),
        )
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "outcome_unknown"
    assert client.post(f"/api/tasks/{task_id}/resume", headers=headers).status_code == 409
    other = create_app(client.app.state.store.path.parent, llm_factory=lambda: None)
    with TestClient(other, base_url="http://127.0.0.1:8765") as restarted:
        login(restarted)
        assert restarted.get(f"/api/tasks/{task_id}").json()["status"] == "outcome_unknown"


def test_cookie_and_login_rate_limit(client):
    response = client.post(
        "/api/login", json={"username": "alice", "password": PASSWORD}, headers=ORIGIN
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"
    for _ in range(10):
        assert (
            client.post(
                "/api/login", json={"username": "alice", "password": "wrong"}, headers=ORIGIN
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/login", json={"username": "alice", "password": "wrong"}, headers=ORIGIN
        ).status_code
        == 429
    )


def test_analyze_exception_persists_real_stage(client, monkeypatch):
    """analyze() 在中段节点抛异常时，必须把真实的失败节点写回 stage，而不是硬编码 parse_reaction。"""
    from web_bridge import api as api_module

    def boom(state):
        raise RuntimeError("select_reactor 故障测试")

    monkeypatch.setattr(api_module, "select_reactor", boom)
    headers = login(client)
    # 提供结构化 reaction_info 让 parse_reaction 不依赖 LLM 直接通过，
    # 从而让循环推进到 select_reactor 触发 monkeypatch 的异常。
    response = client.post(
        "/api/tasks",
        json={
            "query": "高温反应",
            "idempotency_key": "stage-test",
            "reaction_info": {"temperature": 1000.0, "pressure": 100.0, "reactants": ["A"]},
        },
        headers=headers,
    )
    task_id = response.json()["id"]
    row = wait(client, task_id)
    assert row["status"] == "interrupted"
    raw = client.app.state.store.get(task_id)
    assert raw["stage"] == "select_reactor", (
        f"异常恢复 stage 应为真实失败节点，实际为 {raw['stage']!r}"
    )


def test_history_full_search_pagination_and_owner(client):
    from src.agent.graph import initial_state

    headers = login(client)
    owner = client.get("/api/session").json()["user"]["id"]
    for index in range(105):
        query = "历史样本" + str(index)
        if index == 0:
            query = "历史任务" * 30 + "远期关键字"
        task_id = f"history-{index:03d}"
        client.app.state.store.create(
            {"user_query": query, "parent_id": None}, initial_state(query), task_id
        )
        with client.app.state.accounts.connect() as db:
            db.execute(
                "INSERT INTO access VALUES(?,?,?,?)", (task_id, owner, float(index), "analysis")
            )
    first = client.get("/api/task-history").json()
    assert first["total"] == 105 and len(first["items"]) == 20
    second = client.get("/api/task-history?page=2").json()
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    found = client.get("/api/task-history", params={"q": "远期关键字"}).json()
    assert found["total"] == 1 and found["items"][0]["id"] == "history-000"
    assert client.get("/api/task-history", params={"q": "%"}).json()["total"] == 0
    assert client.get("/api/task-history?page=0").status_code == 422
    client.post("/api/logout", headers=headers)
    login(client, "bob")
    assert client.get("/api/task-history", params={"q": "远期关键字"}).json()["total"] == 0


def test_preview_uses_execution_rules_without_task_side_effects(client):
    headers = login(client)
    for name, expected in [
        ("conversion", "Conversion"),
        ("equilibrium", "Equilibrium"),
        ("gibbs", "Gibbs"),
    ]:
        info = json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))[
            "reaction_info"
        ]
        response = client.post("/api/selection-preview", json=info, headers=headers)
        assert response.status_code == 200
        assert response.json()["selected_reactor"] == expected
    response = client.post("/api/selection-preview", json={"temperature": 2000.0}, headers=headers)
    assert response.json()["selected_reactor"] is None
    assert client.get("/api/tasks").json() == []
    assert (
        client.post("/api/selection-preview", json={"conversion": 1.5}, headers=headers).status_code
        == 422
    )
    assert client.post("/api/selection-preview", json={}, headers=ORIGIN).status_code == 403
