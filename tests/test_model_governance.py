import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from config.settings import ModelEndpoint, Settings
from src.agent.graph import build_graph, run_agent
from src.agent.llm import JsonLLM, ModelChainError


def setup_client(monkeypatch, handler, **settings):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    return JsonLLM(
        Settings(
            llm_providers=(ModelEndpoint("local", "https://local.invalid/v1", "model", "secret"),),
            **settings,
        )
    )


def answer(query="test"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"reaction_info": {"reaction_name": query}, "simulation_inputs": {}}
                        )
                    }
                }
            ]
        },
    )


def test_request_deadline_cancels_inflight_http(monkeypatch):
    cancelled = []

    async def handler(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
        return answer()

    llm = setup_client(monkeypatch, handler, llm_timeout_seconds=0.03)
    started = time.monotonic()
    with pytest.raises(ModelChainError):
        llm.extract("test")
    assert time.monotonic() - started < 1 and cancelled
    assert llm.trace[-1]["reason"] == "请求超时"


def test_local_timeout_does_not_shorten_cloud_timeout(monkeypatch):
    called = []

    async def handler(request):
        called.append(request.url.host)
        if request.url.host == "cloud.invalid":
            assert json.loads(request.content)["thinking"] == {"type": "disabled"}
        await asyncio.sleep(0.10 if request.url.host == "cloud.invalid" else 1)
        return answer()

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    llm = JsonLLM(
        Settings(
            llm_timeout_seconds=1,
            local_llm_timeout_seconds=0.02,
            llm_providers=(
                ModelEndpoint("local", "https://local.invalid", "test", "secret"),
                ModelEndpoint("deepseek", "https://cloud.invalid", "test", "secret"),
            ),
        )
    )
    assert llm.extract("test")["reaction_info"]["reaction_name"] == "test"
    assert called == ["local.invalid", "cloud.invalid"]
    assert [row["status"] for row in llm.trace] == ["failed", "success"]
    assert llm.trace[0]["reason"] == "请求超时"


def test_exhausted_task_budget_never_sends(monkeypatch):
    llm = setup_client(monkeypatch, lambda req: pytest.fail("预算已用尽"))
    llm.begin(time.monotonic() - 1)
    with pytest.raises(ModelChainError):
        llm.extract("test")
    assert llm.trace[0]["status"] == "skipped"


def test_retry_after_opens_circuit(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "120"})

    llm = setup_client(monkeypatch, handler)
    for _ in range(2):
        with pytest.raises(ModelChainError):
            llm.extract("test")
    assert len(calls) == 1
    assert llm.trace[0]["reason"] == "服务熔断冷却中"


def test_half_open_probe_recovers(monkeypatch):
    llm = setup_client(monkeypatch, lambda req: answer())
    key = ("local", "https://local.invalid/v1", "model")
    llm._circuits[key] = (2, time.monotonic() - 1, False)
    assert llm.extract("test")["reaction_info"]["reaction_name"] == "test"
    assert key not in llm._circuits


def test_shared_client_trace_is_request_local(monkeypatch):
    def handler(request):
        query = json.loads(json.loads(request.content)["messages"][1]["content"])
        return answer(query)

    llm = setup_client(monkeypatch, handler, max_model_concurrency=4)

    def execute(query):
        result = llm.extract(query)
        return result["reaction_info"]["reaction_name"], llm.trace

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(execute, ["a", "b", "c", "d"]))
    assert [r[0] for r in results] == ["a", "b", "c", "d"]
    assert all(len(r[1]) == 1 for r in results)


def test_concurrent_capacity_is_bounded(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def handler(request):
        entered.set()
        assert release.wait(2)
        return answer()

    llm = setup_client(monkeypatch, handler, max_model_concurrency=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(llm.extract, "first")
        assert entered.wait(1)
        try:
            with pytest.raises(ModelChainError):
                llm.extract("second")
            assert llm.trace[0]["reason"] == "模型并发容量已满"
        finally:
            release.set()
        assert first.result()["reaction_info"]["reaction_name"] == "test"


def test_graph_keeps_parse_and_explanation_trace(monkeypatch):
    def handler(request):
        content = json.loads(request.content)["messages"][0]["content"]
        if "explanation" in content:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": '{"explanation":"请补充参数"}'}}]}
            )
        return answer()

    llm = setup_client(monkeypatch, handler)
    state = run_agent(build_graph(lambda *args: pytest.fail("缺参不能运行"), llm), "test")
    assert [e["phase"] for e in state["llm_trace"]] == ["parse_reaction", "explain_result"]


def test_sensitive_exception_text_not_logged(caplog):
    from src.runtime.telemetry import failure

    with caplog.at_level("INFO", logger="reactor"):
        try:
            raise RuntimeError("secret-do-not-log")
        except RuntimeError as exc:
            failure("failed", exc)
    assert "secret-do-not-log" not in caplog.text
    assert "RuntimeError" in caplog.text and "frames" in caplog.text
