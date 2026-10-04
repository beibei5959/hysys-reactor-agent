NAMES = {
    "Conversion": "Conversion Reactor（转化反应器）",
    "Equilibrium": "Equilibrium Reactor（平衡反应器）",
    "Gibbs": "Gibbs Reactor（吉布斯反应器）",
}


def make_explain_node(llm):
    def explain_result(state):
        if llm is not None and hasattr(llm, "trace"):
            llm.trace = state.get("llm_trace", [])
        explanation_status = "template"
        lines = [
            "反应器：" + NAMES.get(state.get("selected_reactor"), "尚不能确定"),
            "选择依据：" + state.get("selection_reason", "解析未完成"),
        ]
        if state.get("missing_parameters"):
            lines.append(
                "请补充/修正以下参数后重新提交：\n- " + "\n- ".join(state["missing_parameters"])
            )
        if state.get("error"):
            lines.append("未完成模拟：" + state["error"])
        results = state.get("simulation_results", {})
        if results.get("source") == "mock":
            lines.append(
                "【Mock 流程演示】调用链已跑通，未进行真实 HYSYS 计算；没有真实收敛、组成或能耗结果。"
            )
        elif results.get("source") == "hysys":
            lines.append(
                "【真实 HYSYS】收敛检查已通过。工程结果请核对 simulation_results 中的原始值和单位。"
            )
        if llm and state.get("reaction_info") is not None:
            try:
                explanation = llm.explain(
                    {
                        k: state.get(k)
                        for k in [
                            "selected_reactor",
                            "selection_reason",
                            "missing_parameters",
                            "simulation_status",
                            "simulation_results",
                            "error",
                        ]
                    }
                )
                if not isinstance(explanation, str) or not explanation.strip():
                    raise ValueError("空解释")
                lines.append("AI 补充解释（待人工核对，以以上规则和原始结果为准）：" + explanation)
                explanation_status = "success"
            except Exception:
                explanation_status = "degraded"
                lines.append("在线解释暂不可用，以上为规则与运行状态生成的中文说明。")
        if state.get("cleanup_status") == "failed":
            lines.append("结果已保留，但资源清理失败，请检查执行环境。")
        trace = list(getattr(llm, "trace", state.get("llm_trace", [])))
        if trace:
            labels = {
                "local": "本地模型",
                "deepseek": "DeepSeek",
                "siliconflow": "硅基流动",
                "custom": "自定义模型",
            }
            lines.append(
                "模型调用记录："
                + "；".join(
                    ("解析" if e["phase"] == "parse_reaction" else "解释")
                    + "/"
                    + labels.get(e["provider"], e["provider"])
                    + "/"
                    + ("成功" if e["status"] == "success" else e.get("reason", e["status"]))
                    for e in trace
                )
            )
        return {
            "final_answer": "\n".join(lines),
            "llm_trace": trace,
            "explanation_status": explanation_status,
        }

    return explain_result
