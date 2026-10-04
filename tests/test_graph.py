import json
from pathlib import Path

import pytest

from src.agent.graph import build_graph, run_agent
from src.hysys.exceptions import RetryableHysysError, UnverifiedAPIError


def case():
    return json.loads(
        (Path(__file__).resolve().parents[1] / "examples/conversion.json").read_text(
            encoding="utf-8"
        )
    )


def invoke(runner, data=None, **kwargs):
    d = data or case()
    return run_agent(
        build_graph(runner, **kwargs), d["user_query"], d["reaction_info"], d["simulation_inputs"]
    )


def test_missing_never_runs():
    d = case()
    d["reaction_info"]["pressure"] = None

    def forbidden(*args):
        pytest.fail("缺参数不应调用模拟器")

    s = invoke(forbidden, d)
    assert s["simulation_status"] == "needs_input"
    assert "pressure" in s["final_answer"]


def test_bounded_retry():
    calls = []

    def failing(*args):
        calls.append(1)
        raise RetryableHysysError("测试临时错误")

    s = invoke(failing)
    assert len(calls) == 3 and s["retry_count"] == 2
    assert s["simulation_status"] == "failed"


def test_retry_recovery():
    calls = []

    def recovery(*args):
        calls.append(1)
        if len(calls) == 1:
            raise RetryableHysysError("测试临时错误")
        return {"source": "mock", "workflow_verified": True, "converged": None}

    s = invoke(recovery)
    assert len(calls) == 2 and s["error"] is None
    assert s["simulation_status"] == "success"


def test_no_retry_unverified_api():
    calls = []

    def unavailable(*args):
        calls.append(1)
        raise UnverifiedAPIError("API 未验证")

    s = invoke(unavailable)
    assert len(calls) == 1 and s["retry_count"] == 0


def test_no_llm_no_fake_parsing():
    s = run_agent(build_graph(lambda *args: pytest.fail("不得运行")), "高温反应")
    assert s["simulation_status"] == "failed"
    assert "未配置在线模型" in s["final_answer"]


def test_no_real_convergence_no_results():
    s = invoke(lambda *args: {"source": "hysys", "converged": False, "yield": 0.8})
    assert s["simulation_status"] == "failed" and not s["simulation_results"]


def test_parse_rejects_invalid_payload():
    d = case()
    d["reaction_info"]["conversion"] = 80
    s = invoke(lambda *args: pytest.fail("不得运行"), d)
    assert s["simulation_status"] == "failed"


def test_unknown_does_not_default_to_gibbs():
    d = case()
    d["reaction_info"] = {"temperature": 1800.0, "pressure": 1000.0, "reactants": ["CH4"]}
    s = invoke(lambda *args: pytest.fail("不得运行"), d)
    assert s["selected_reactor"] is None and s["simulation_status"] == "needs_input"
