import json

import httpx
import pytest

from config.settings import ModelEndpoint, Settings
from src.agent.llm import JsonLLM, ModelChainError

PAYLOAD = {"reaction_info": {"conversion": 0.8}, "simulation_inputs": {}}


def client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    return JsonLLM(
        Settings(
            llm_providers=tuple(
                ModelEndpoint(n, "https://" + n + ".invalid/v1", n, "secret")
                for n in ["local", "deepseek", "siliconflow"]
            )
        )
    )


def response(payload=PAYLOAD):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})


def test_local_success_no_cloud(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        assert json.loads(req.content)["response_format"]["type"] == "text"
        return response()

    llm = client(monkeypatch, handler)
    assert llm.extract("转化率80%") == PAYLOAD
    assert calls == ["local.invalid"]


def test_ordered_three_providers(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        if req.url.host == "local.invalid":
            raise httpx.ConnectError("secret should not appear", request=req)
        if req.url.host == "deepseek.invalid":
            return httpx.Response(404)
        return response()

    llm = client(monkeypatch, handler)
    llm.extract("转化率80%")
    assert calls == ["local.invalid", "deepseek.invalid", "siliconflow.invalid"]
    assert "secret" not in json.dumps(llm.trace)
    assert llm.trace[-1]["status"] == "success"


@pytest.mark.parametrize("mode", ["timeout", "invalid_json", "invalid_schema", "http429"])
def test_failure_types_fall_back(monkeypatch, mode):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        if req.url.host == "local.invalid":
            if mode == "timeout":
                raise httpx.ReadTimeout("timeout", request=req)
            if mode == "invalid_json":
                return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})
            if mode == "invalid_schema":
                return response({"reaction_info": {"conversion": 80}, "simulation_inputs": {}})
            return httpx.Response(429)
        return response()

    llm = client(monkeypatch, handler)
    llm.extract("转化率80%")
    assert calls == ["local.invalid", "deepseek.invalid"]


def test_all_fail_finite(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(503)

    llm = client(monkeypatch, handler)
    with pytest.raises(ModelChainError):
        llm.extract("测试")
    assert len(calls) == 3


def test_missing_engineering_inputs_is_not_provider_failure(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        return response({"reaction_info": {}, "simulation_inputs": {}})

    llm = client(monkeypatch, handler)
    assert llm.extract("仅温度高")["reaction_info"] == {}
    assert len(calls) == 1


def test_explanation_uses_same_order(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        return (
            httpx.Response(500)
            if req.url.host == "local.invalid"
            else response({"explanation": "Mock非真实计算"})
        )

    llm = client(monkeypatch, handler)
    assert llm.explain({}) == "Mock非真实计算"
    assert calls == ["local.invalid", "deepseek.invalid"]


def test_missing_provider_config_skips_without_request(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.host)
        return response()

    llm = client(monkeypatch, handler)
    llm.settings = Settings(
        llm_providers=(
            ModelEndpoint("local", "", "", ""),
            ModelEndpoint("deepseek", "https://deepseek.invalid/v1", "test", "secret"),
        )
    )
    llm.extract("转化率80%")
    assert calls == ["deepseek.invalid"] and llm.trace[0]["status"] == "skipped"


def test_credentials_not_in_config_repr():
    # Settings 已经移除了裸 api_key 字段；凭据只存在于 ModelEndpoint.api_key（repr=False）。
    assert "hidden-secret" not in repr(
        Settings(
            llm_providers=(ModelEndpoint("local", "url", "model", "hidden-secret"),),
        )
    )


def test_empty_final_content_falls_back(monkeypatch):
    def handler(req):
        if req.url.host == "local.invalid":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "", "reasoning_content": json.dumps(PAYLOAD)}}
                    ]
                },
            )
        return response()

    llm = client(monkeypatch, handler)
    llm.extract("转化率80%")
    assert [e["status"] for e in llm.trace] == ["failed", "success"]


def test_siliconflow_uses_non_thinking_json(monkeypatch):
    def handler(req):
        data = json.loads(req.content)
        assert data["enable_thinking"] is False
        assert data["response_format"]["type"] == "json_object"
        return response()

    llm = client(monkeypatch, handler)
    llm.settings = Settings(llm_providers=(llm.settings.llm_providers[2],))
    llm.extract("转化率80%")
