from src.knowledge.reactor_rules import select_reactor as apply_rules


def select_reactor(state):
    reactor, reason, confidence = apply_rules(state["reaction_info"])
    return {"selected_reactor": reactor, "selection_reason": reason, "confidence": confidence}
