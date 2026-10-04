import json
from pathlib import Path

import pytest

from src.knowledge.reactor_rules import select_reactor
from src.models.reaction import ReactionInfo

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name,expected",
    [("equilibrium", "Equilibrium"), ("conversion", "Conversion"), ("gibbs", "Gibbs")],
)
def test_three_cases(name, expected):
    data = json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))
    assert select_reactor(ReactionInfo(**data["reaction_info"]))[0] == expected


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"temperature": 1800},
        {"multiple_reactions": True},
        {"reaction_path_known": False},
        {"reversible": True},
        {"reaction_path_known": True, "reversible": True, "equilibrium_controlled": False},
    ],
)
def test_insufficient_evidence(data):
    assert select_reactor(ReactionInfo(**data))[0] is None


def test_conversion_priority():
    assert (
        select_reactor(
            ReactionInfo(
                conversion=0.8,
                reversible=True,
                equilibrium_controlled=True,
                reaction_path_known=True,
            )
        )[0]
        == "Conversion"
    )


def test_known_multiple_equilibria():
    assert (
        select_reactor(
            ReactionInfo(
                multiple_reactions=True,
                reversible=True,
                equilibrium_controlled=True,
                reaction_path_known=True,
            )
        )[0]
        == "Equilibrium"
    )
