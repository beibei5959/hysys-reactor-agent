import pytest
from pydantic import ValidationError

from src.models.reaction import ReactionInfo
from src.models.simulation import SimulationInputs


@pytest.mark.parametrize(
    "data",
    [
        dict(temperature=-1),
        dict(pressure=0),
        dict(conversion=80),
        dict(conversion=-0.1),
        dict(temperature=float("nan")),
        dict(conversion=0.5, conversion_known=False),
        dict(reversible="false"),
    ],
)
def test_reject_invalid_reaction(data):
    with pytest.raises(ValidationError):
        ReactionInfo(**data)


def test_unknown_is_not_false():
    assert ReactionInfo().reaction_path_known is None
    assert ReactionInfo(conversion=0).conversion_known is True


def test_composition_balance():
    with pytest.raises(ValidationError):
        SimulationInputs(
            components=["A"],
            property_package="test",
            feed_composition={"A": 0.8},
            feed_flow_kmol_h=1,
        )
