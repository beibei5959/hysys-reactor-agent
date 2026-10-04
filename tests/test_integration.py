import json
from pathlib import Path

import pytest

from src.agent.graph import build_graph, run_agent
from src.hysys.com_client import ComHysysController
from src.hysys.exceptions import HysysError, UnverifiedAPIError
from src.hysys.mock_controller import MockHysysController
from src.tools.hysys_tools import make_hysys_runner

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name,expected",
    [("equilibrium", "Equilibrium"), ("conversion", "Conversion"), ("gibbs", "Gibbs")],
)
def test_end_to_end(name, expected):
    d = json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))
    controller = MockHysysController()
    graph = build_graph(make_hysys_runner(lambda: controller))
    s = run_agent(graph, d["user_query"], d["reaction_info"], d["simulation_inputs"])
    assert s["selected_reactor"] == expected and s["simulation_status"] == "success"
    assert s["simulation_results"]["source"] == "mock"
    assert s["simulation_results"]["converged"] is None
    assert s["simulation_results"]["engineering_results"] is None
    assert "Mock" in s["final_answer"] and controller.closed
    assert controller.calls[-3:] == ["run", "get_results", "close"]


def test_controller_cleanup_on_error():
    class Broken(MockHysysController):
        def run(self):
            raise HysysError("故障测试")

    controller = Broken()
    d = json.loads((ROOT / "examples/conversion.json").read_text(encoding="utf-8"))
    s = run_agent(
        build_graph(make_hysys_runner(lambda: controller)),
        d["user_query"],
        d["reaction_info"],
        d["simulation_inputs"],
    )
    assert controller.closed and s["simulation_status"] == "failed"


def test_real_building_blocked_without_guessing_com():
    controller = ComHysysController()
    with pytest.raises(UnverifiedAPIError):
        controller.create_case()
    controller.close()


def test_fake_llm_extraction_and_explanation():
    d = json.loads((ROOT / "examples/conversion.json").read_text(encoding="utf-8"))

    class FakeLLM:
        def extract(self, query):
            return {k: d[k] for k in ["reaction_info", "simulation_inputs"]}

        def explain(self, facts):
            assert facts["simulation_results"]["source"] == "mock"
            return "指定转化率决定转化反应器；本次只是 Mock 演示。"

    s = run_agent(build_graph(make_hysys_runner(MockHysysController), FakeLLM()), d["user_query"])
    assert s["simulation_status"] == "success" and "AI 补充解释" in s["final_answer"]


def test_llm_explanation_failure_retains_result():
    d = json.loads((ROOT / "examples/conversion.json").read_text(encoding="utf-8"))

    class BrokenLLM:
        def explain(self, facts):
            raise RuntimeError("故障测试")

    s = run_agent(
        build_graph(make_hysys_runner(MockHysysController), BrokenLLM()),
        d["user_query"],
        d["reaction_info"],
        d["simulation_inputs"],
    )
    assert s["simulation_status"] == "success" and "在线解释暂不可用" in s["final_answer"]
