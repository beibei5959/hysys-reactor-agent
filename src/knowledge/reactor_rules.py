from src.models.reaction import ReactionInfo


def select_reactor(info: ReactionInfo) -> tuple[str | None, str, float]:
    if info.conversion_known is True:
        return (
            "Conversion",
            "明确给定转化率，按指定转化程度选择转化反应器。",
            1.0 if info.conversion is not None else 0.8,
        )
    if (
        info.reaction_path_known is True
        and info.reversible is True
        and info.equilibrium_controlled is True
    ):
        return "Equilibrium", "具体反应路径已知，反应可逆且受平衡控制，选择平衡反应器。", 1.0
    if info.multiple_reactions is True and (
        info.reaction_path_known is False or info.products_known is False
    ):
        return (
            "Gibbs",
            "复杂多反应体系，路径或产物分布不明确，采用吉布斯自由能最小化；依据不是高温。",
            0.9,
        )
    return None, "证据不足：请明确转化率，或具体可逆平衡反应，或复杂体系的未知路径/产物分布。", 0.0
