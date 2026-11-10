from __future__ import annotations

from typing import Any

import pytest

from dccapacity import analysis, bench, pipeline, score
from dccapacity.generate import GenParams, Truth, simulate
from dccapacity.params import RESOURCES, Params

from .conftest import SEED

P = Params()


def fake_analysis(asof: int, **forecast: dict[str, Any]) -> dict[str, Any]:
    base = {"months_left": None, "months_early": None, "months_late": None, "model": None, "status": "ok"}
    return {"asof": {"month": asof}, "forecast": {r: {**base, **forecast.get(r, {})} for r in RESOURCES}}


def truth_of(space: list[float]) -> Truth:
    return Truth(
        len(space), 1, {"space": space, "power": [0.0] * len(space), "cooling": [0.0] * len(space)}, [0] * len(space)
    )


def test_each_kind_of_outcome() -> None:
    t = truth_of([0.1, 0.5, 0.7, 0.85, 0.9, 0.95])  # crosses 0.9 in month 4
    # an estimate: 3 months left from month 1; the truth is 3
    c = score.case(
        fake_analysis(1, space={"months_left": 2.0, "months_early": 1.0, "months_late": 4.0, "model": "linear"}),
        t,
        P,
        "space",
    )
    assert c is not None and (c["kind"], c["true_left"], c["error"], c["in_interval"]) == ("estimate", 3, -1.0, True)
    c = score.case(
        fake_analysis(1, space={"months_left": 1.0, "months_early": 0.5, "months_late": 2.0, "model": "linear"}),
        t,
        P,
        "space",
    )
    assert c is not None and c["error"] == -2.0 and c["in_interval"] is False
    # a missed crossing, and a crossing predicted beyond the simulated future (treated as none)
    c = score.case(fake_analysis(1), t, P, "space")
    assert c is not None and c["kind"] == "missed"
    c = score.case(
        fake_analysis(1, space={"months_left": 50.0, "months_early": 40.0, "months_late": 60.0}), t, P, "space"
    )
    assert c is not None and c["kind"] == "missed" and c["pred_left"] is None
    # nothing happens and nothing is predicted / a false alarm
    flat = truth_of([0.1] * 6)
    c = score.case(fake_analysis(1), flat, P, "space")
    assert c is not None and c["kind"] == "agree_no_crossing"
    c = score.case(
        fake_analysis(1, space={"months_left": 2.0, "months_early": 1.0, "months_late": 3.0}), flat, P, "space"
    )
    assert c is not None and c["kind"] == "false_alarm"
    # nothing to forecast when the resource is over its limit, or when there is no future left
    assert score.case(fake_analysis(4), t, P, "space") is None
    assert score.case(fake_analysis(5), t, P, "space") is None


def test_open_interval_counts_as_inside_when_the_true_month_is_past_its_start() -> None:
    t = truth_of([0.1, 0.5, 0.7, 0.85, 0.9, 0.95])
    c = score.case(
        fake_analysis(1, space={"months_left": 1.0, "months_early": 0.5, "months_late": None}), t, P, "space"
    )
    assert c is not None and c["in_interval"] is True


def test_summarize_on_known_records() -> None:
    recs = [
        {
            "kind": "estimate",
            "resource": "space",
            "true_left": 5,
            "error": 1.0,
            "in_interval": True,
            "model": "linear",
            "pred_left": 6.0,
        },
        {
            "kind": "estimate",
            "resource": "power",
            "true_left": 30,
            "error": -4.0,
            "in_interval": False,
            "model": "exponential",
            "pred_left": 26.0,
        },
        {"kind": "false_alarm", "resource": "space", "true_left": None, "pred_left": 10.0, "model": "linear"},
        {"kind": "missed", "resource": "power", "true_left": 4, "pred_left": None, "model": None},
    ]
    s = score.summarize(recs, 2)
    assert s["cases"] == 4 and s["excluded_over_limit"] == 2 and s["false_alarm_within_24"] == 1
    assert s["kinds"] == {"estimate": 2, "agree_no_crossing": 0, "missed": 1, "false_alarm": 1}
    assert s["all"]["abs_error_median"] == 2.5 and s["all"]["coverage"] == 0.5 and s["all"]["bias_median"] == -1.5
    assert s["by_distance"]["1-12 months"]["n"] == 1 and s["by_distance"]["25-48 months"]["n"] == 1
    assert s["by_resource"]["cooling"]["n"] == 0 and s["by_resource"]["cooling"]["abs_error_median"] is None
    assert s["by_model"]["linear"]["n"] == 1


def test_a_report_is_scored_against_its_own_truth() -> None:
    sim = simulate(GenParams(months=48, future=36, seed=SEED))
    inv = sim.inventory.at(47)
    rep = analysis.build_report(inv, sim.facility, P, sim.truth, "test")
    assert rep["accuracy"]["months_known"] == 36 and set(rep["accuracy"]["resources"]) == set(RESOURCES)
    assert len(rep["accuracy"]["truth"]["space"]) == 37  # from now on, including now
    assert analysis.build_report(inv, sim.facility, P, None, "test")["accuracy"] is None


def test_the_sweep_adds_up() -> None:
    r = bench.sweep(2, (30, 40))
    s = r["summary"]
    assert r["seeds"] == 2 and r["cuts"] == [30, 40] and r["total_months"] == 132
    assert s["cases"] + s["excluded_over_limit"] == 2 * 2 * 3
    assert sum(s["kinds"].values()) == s["cases"]


def test_the_forecast_from_the_pipeline_matches_a_manual_scoring() -> None:
    sim = simulate(GenParams(months=60, future=48, seed=SEED))
    a = pipeline.analyze(sim.inventory.at(50), sim.facility, P, 50)
    sc = score.score(a, sim.truth, P)
    assert sc["asof"] == 50 and sc["months_known"] == 57
    for r in RESOURCES:
        c = sc["resources"][r]
        if c and c["kind"] == "estimate":
            assert c["error"] == pytest.approx(c["pred_left"] - c["true_left"])
