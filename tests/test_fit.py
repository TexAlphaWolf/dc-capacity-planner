"""The forecast on series whose answer is known."""

from __future__ import annotations

import math

import numpy as np
import pytest

from dccapacity import pipeline, reference
from dccapacity.params import Params
from dccapacity.verify import compare

P = Params()


def both_fit(util: list[float], limit: float, p: Params = P) -> dict[str, object]:
    asof = len(util) - 1
    a, b = pipeline.fit(util, asof, p, limit), reference.fit(util, asof, p, limit)
    _, _, bad = compare(a, b)
    assert bad is None, bad
    return a


def test_a_straight_line_is_found_exactly() -> None:
    y = [0.2 + 0.01 * t for t in range(40)]  # 0.59 now, 0.8 at t = 60
    f = both_fit(y, 0.8)
    assert f["model"] == "linear" and f["status"] == "ok"
    assert f["months_left"] == pytest.approx(60 - 39)
    assert f["slope"] == pytest.approx(0.01) and f["fitted_now"] == pytest.approx(0.59)
    # no noise, no steps to wander: the interval collapses onto the estimate
    assert f["months_early"] == pytest.approx(21, abs=1e-6) and f["months_late"] == pytest.approx(21, abs=1e-6)


def test_an_exponential_is_chosen_when_it_follows_the_data() -> None:
    y = [0.1 * 1.03**t for t in range(40)]
    f = both_fit(y, 0.8)
    assert f["model"] == "exponential"
    assert f["slope"] == pytest.approx(math.log(1.03))
    assert f["months_left"] == pytest.approx(math.log(0.8 / y[-1]) / math.log(1.03))


def test_only_the_window_counts() -> None:
    y = [0.5 - 0.005 * t for t in range(30)] + [
        0.2 + 0.01 * t for t in range(24)
    ]  # decline, then growth in the last 24 months
    f = both_fit(y, 0.9, Params(window=24))
    assert f["slope"] == pytest.approx(0.01) and f["window"] == 24
    assert both_fit(y, 0.9, Params(window=54))["window"] == 54


@pytest.mark.parametrize(
    ("y", "status"),
    [
        ([0.3, 0.4, 0.5], "short history"),
        ([0.5] * 12, "no growth"),
        ([0.6 - 0.01 * t for t in range(12)], "no growth"),
        ([0.5, 0.6, 0.7, 0.8, 0.85, 0.9], "crossed"),
    ],
)
def test_statuses(y: list[float], status: str) -> None:
    f = both_fit(y, 0.8)
    assert f["status"] == status
    if status == "crossed":
        assert (f["months_left"], f["months_early"], f["months_late"]) == (0.0, 0.0, 0.0)
    if status in ("short history", "no growth"):
        assert f["months_left"] is None and f["months_early"] is None


def test_zeros_rule_out_the_exponential_and_cannot_break_it() -> None:
    y = [0.0] * 6 + [0.01 * t for t in range(1, 13)]
    f = both_fit(y, 0.5)
    assert f["model"] == "linear" and f["status"] == "ok"


def test_the_interval_widens_with_the_wandering_and_with_z() -> None:
    rng = np.random.default_rng(5)
    y = list(np.cumsum(rng.normal(0.01, 0.01, 40)) + 0.2)
    f1 = both_fit(y, 1.5, Params(z=1.0))
    f2 = both_fit(y, 1.5, Params(z=2.0))
    w1 = f1["months_late"] - f1["months_early"]  # type: ignore[operator]
    w2 = f2["months_late"] - f2["months_early"]  # type: ignore[operator]
    assert f1["months_early"] > 0 and w1 > 0  # type: ignore[operator]
    assert w2 == pytest.approx(2 * w1, rel=1e-6)  # the interval is the estimate plus and minus z standard deviations
    assert f1["months_early"] <= f1["months_left"] <= f1["months_late"]  # type: ignore[operator]
    calm = list(0.2 + 0.01 * np.arange(40) + rng.normal(0, 0.0005, 40))
    f3 = both_fit(calm, 1.5, Params(z=1.0))
    assert f3["months_late"] - f3["months_early"] < w1  # type: ignore[operator]


def test_a_crossing_that_has_apparently_already_happened_is_clamped_to_zero() -> None:
    y = [
        0.5,
        0.6,
        0.55,
        0.62,
        0.58,
        0.66,
        0.7,
        0.75,
        0.74,
        0.79,
    ]  # fitted line is above the limit, the last value is not
    f = both_fit(y, 0.8)
    assert f["status"] == "ok" and f["months_left"] >= 0.0  # type: ignore[operator]
