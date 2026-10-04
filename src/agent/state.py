from typing import Any, TypedDict

from src.models.reaction import ReactionInfo


class ReactorAgentState(TypedDict, total=False):
    """LangGraph 节点间流转的状态。

    契约说明：
    - 本 TypedDict 没有为 list/dict 字段定义 reducer，节点返回 update 即整字段覆盖。
    - ``llm_trace`` 必须由**最后一个执行 LLM 调用的节点**写入（parse_reaction 或
      explain_result）；其他节点不得返回该字段，否则会让上游累积的 trace 丢失。
    """

    user_query: str
    reaction_info: ReactionInfo | None
    selected_reactor: str | None
    selection_reason: str
    confidence: float
    simulation_inputs: dict[str, Any]
    missing_parameters: list[str]
    validation_passed: bool
    simulation_status: str
    simulation_results: dict[str, Any]
    error: str | None
    retry_count: int
    final_answer: str
    llm_trace: list[dict[str, Any]]
    error_code: str | None
    explanation_status: str
    cleanup_status: str
