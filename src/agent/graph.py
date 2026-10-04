import time

from langgraph.graph import END, START, StateGraph

from src.agent.nodes.explain_result import make_explain_node
from src.agent.nodes.parse_reaction import make_parse_node
from src.agent.nodes.run_hysys import make_run_node
from src.agent.nodes.select_reactor import select_reactor
from src.agent.nodes.validate_input import validate_input
from src.agent.state import ReactorAgentState
from src.runtime.telemetry import emit, failure


def next_stage(name, state):
    if name == "parse_reaction":
        return "explain_result" if state.get("error") else "select_reactor"
    if name == "select_reactor":
        return "validate_input"
    if name == "validate_input":
        return "run_hysys" if state["validation_passed"] else "explain_result"
    if name == "run_hysys":
        return "run_hysys" if state["simulation_status"] == "retrying" else "explain_result"
    return None


def build_graph(runner, llm=None, max_retries=2, *, start_at="parse_reaction", observer=None):
    if not 0 <= max_retries <= 2:
        raise ValueError("最多追加 2 次重试")
    graph = StateGraph(ReactorAgentState)
    nodes = {
        "parse_reaction": make_parse_node(llm),
        "select_reactor": select_reactor,
        "validate_input": validate_input,
        "run_hysys": make_run_node(runner, max_retries),
        "explain_result": make_explain_node(llm),
    }
    if start_at not in nodes:
        raise ValueError("未知恢复阶段")

    def observed(name, node):
        def invoke(state):
            if observer:
                observer("before", name, state)
            started = time.monotonic()
            emit("node_started", node=name)
            try:
                update = node(state)
                if observer:
                    observer("after", name, {**state, **update})
                emit(
                    "node_completed",
                    node=name,
                    duration_ms=round((time.monotonic() - started) * 1000),
                )
                return update
            except Exception as exc:
                failure("node_failed", exc)
                raise

        return invoke

    for name, node in nodes.items():
        graph.add_node(name, observed(name, node))
    graph.add_edge(START, start_at)
    graph.add_conditional_edges(
        "parse_reaction", lambda s: "explain_result" if s.get("error") else "select_reactor"
    )
    graph.add_edge("select_reactor", "validate_input")
    graph.add_conditional_edges(
        "validate_input", lambda s: "run_hysys" if s["validation_passed"] else "explain_result"
    )
    graph.add_conditional_edges(
        "run_hysys",
        lambda s: "run_hysys" if s["simulation_status"] == "retrying" else "explain_result",
    )
    graph.add_edge("explain_result", END)
    return graph.compile()


def run_agent(graph, user_query, reaction_info=None, simulation_inputs=None):
    return graph.invoke(
        initial_state(user_query, reaction_info, simulation_inputs), config={"recursion_limit": 20}
    )


def initial_state(user_query, reaction_info=None, simulation_inputs=None):
    return {
        "user_query": user_query,
        "reaction_info": reaction_info,
        "selected_reactor": None,
        "selection_reason": "",
        "confidence": 0.0,
        "simulation_inputs": simulation_inputs or {},
        "missing_parameters": [],
        "validation_passed": False,
        "simulation_status": "not_started",
        "simulation_results": {},
        "error": None,
        "error_code": None,
        "retry_count": 0,
        "final_answer": "",
        "llm_trace": [],
        "explanation_status": "not_started",
        "cleanup_status": "not_started",
    }
