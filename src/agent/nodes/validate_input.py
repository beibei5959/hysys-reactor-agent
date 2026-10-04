from pydantic import ValidationError

from src.models.simulation import SimulationInputs


def validate_input(state):
    info = state["reaction_info"]
    reactor = state.get("selected_reactor")
    missing = []
    if reactor is None:
        missing.append(
            "反应器选择依据：明确转化率，或已知可逆平衡反应，或复杂体系未知路径/产物分布"
        )
    if info.temperature is None:
        missing.append("temperature：温度（K）")
    if info.pressure is None:
        missing.append("pressure：绝对压力（kPa）")
    if not info.reactants:
        missing.append("reactants：反应物名称")
    inputs = None
    try:
        inputs = SimulationInputs.model_validate(state.get("simulation_inputs", {}))
    except ValidationError as exc:
        for e in exc.errors():
            path = ".".join(map(str, e["loc"])) or "simulation_inputs"
            # Pydantic 的原始输入不回显，避免泄漏无关内容。
            missing.append(f"{path}：缺失或不符合参数约束")
    if inputs:
        if not set(info.reactants + info.products) <= set(inputs.components):
            missing.append("components：需包含全部已知反应物与产物")
        if reactor in {"Conversion", "Equilibrium"} and not inputs.reactions:
            missing.append("reactions：具体反应计量方程")
        if reactor == "Conversion":
            basis = inputs.conversion_basis
            if (
                not basis
                or inputs.feed_composition.get(basis, 0) <= 0
                or not any(r.get(basis, 0) < 0 for r in inputs.reactions)
            ):
                missing.append("conversion_basis：必须是进料中存在且计量系数为负的基准反应物")
            if len(inputs.reactions) > 1:
                missing.append("第一版转化模型仅支持一个计量反应；多个反应需逐一指定转化率后扩展")
        if reactor == "Equilibrium" and not (inputs.equilibrium_method or "").strip():
            missing.append("equilibrium_method：经确认的平衡数据来源/方法")
    if reactor == "Conversion" and info.conversion is None:
        missing.append("conversion：转化率数值（0～1）")
    return {
        "missing_parameters": missing,
        "validation_passed": not missing,
        "simulation_status": "needs_input" if missing else "not_started",
    }
