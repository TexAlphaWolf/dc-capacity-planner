import pytest

from dccapacity.params import ParamError, Params


def test_defaults_and_round_trip() -> None:
    p = Params()
    assert Params.from_dict(p.as_dict()) == p
    assert (p.space_limit, p.power_limit, p.cooling_limit) == (0.90, 0.80, 0.85)
    assert p.limit("power") == 0.80


@pytest.mark.parametrize(
    "bad",
    [
        {"derate": 0.0},
        {"derate": 1.1},
        {"space_limit": float("nan")},
        {"power_limit": -1.0},
        {"window": 3, "min_history": 4},
        {"min_history": 2},
        {"z": 0.0},
        {"horizon": 0},
        {"window": 12.5},
        {"horizon": True},
    ],
)
def test_bad_parameters_are_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ParamError):
        Params(**bad)  # type: ignore[arg-type]
