import json
from pathlib import Path

import pytest

from config.settings import Settings
from src.agent.graph import build_graph, run_agent
from src.agent.llm import JsonLLM

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("feed_composition", {"C7H8": 0.2, "H2": 0.3}),
        ("feed_flow_kmol_h", 0),
        ("components", ["C7H8"]),
        ("conversion_basis", "C6H6"),
        ("reactions", []),
        ("property_package", " "),
        ("reactions", [{"C7H8": 1.0, "H2": 1.0}]),
        ("feed_composition", {"C7H8": float("nan"), "H2": 0.5}),
    ],
)
def test_invalid_simulation_inputs_block_run(field, value):
    d = json.loads((ROOT / "examples/conversion.json").read_text(encoding="utf-8"))
    d["simulation_inputs"][field] = value
    graph = build_graph(lambda *a: pytest.fail("无效参数不应执行"))
    s = run_agent(graph, d["user_query"], d["reaction_info"], d["simulation_inputs"])
    assert s["simulation_status"] == "needs_input"
    assert not s["validation_passed"]


def test_missing_conversion_numeric_value():
    s = run_agent(build_graph(lambda *a: pytest.fail("不应执行")), "", {"conversion_known": True})
    assert any("conversion：" in x for x in s["missing_parameters"])


def test_json_llm_wire_contract(monkeypatch):
    """只验证本地 HTTP 适配，不代表在线服务或模型质量已验证。"""
    import httpx

    from config.settings import ModelEndpoint

    payload = {
        "reaction_info": {"conversion_known": True, "conversion": 0.8},
        "simulation_inputs": {},
    }

    def handler(request):
        assert str(request.url) == "https://example.invalid/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        data = json.loads(request.content)
        assert data["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw)
    )
    # 旧版本通过 llm_base_url/llm_model/llm_api_key 三个裸字段描述自定义 provider；
    # 现在统一使用 llm_providers 列表，每个 provider 用 ModelEndpoint 表示。
    llm = JsonLLM(
        Settings(
            llm_providers=(
                ModelEndpoint(
                    name="test",
                    base_url="https://example.invalid/v1",
                    model="test",
                    api_key="test-key",
                ),
            )
        )
    )
    assert llm.extract("转化率80%") == payload


def test_llm_malformed_output_fails_closed():
    class BadLLM:
        def extract(self, query):
            return {"selected_reactor": "Gibbs"}

    s = run_agent(build_graph(lambda *a: pytest.fail("不应执行"), BadLLM()), "高温")
    assert s["simulation_status"] == "failed" and s["selected_reactor"] is None


def test_clean_state_between_requests():
    d = json.loads((ROOT / "examples/conversion.json").read_text(encoding="utf-8"))
    graph = build_graph(lambda *a: {"source": "mock", "workflow_verified": True, "converged": None})
    first = run_agent(graph, d["user_query"], d["reaction_info"], d["simulation_inputs"])
    second = run_agent(graph, "", {})
    assert first["simulation_status"] == "success"
    assert second["simulation_status"] == "needs_input" and second["simulation_results"] == {}
