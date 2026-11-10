from __future__ import annotations

import json

import numpy as np
import pytest

from dccapacity import model, pipeline
from dccapacity.generate import GenParams, Truth, generate, simulate
from dccapacity.params import RESOURCES, Params

from .conftest import SEED


def test_it_is_deterministic_and_the_seed_matters() -> None:
    a, b, c = (
        simulate(GenParams(months=24, future=12, seed=3)),
        simulate(GenParams(months=24, future=12, seed=3)),
        simulate(GenParams(months=24, future=12, seed=4)),
    )
    assert a.inventory == b.inventory and a.truth == b.truth
    assert a.inventory != c.inventory and a.facility != c.facility  # the plants are drawn from the seed too


def test_the_inventory_is_valid_and_within_the_facility(sim) -> None:  # type: ignore[no-untyped-def]
    model.validate(sim.inventory, sim.facility)  # no overlaps, everything fits its rack, avg <= nameplate
    assert len(sim.inventory) > 300


def test_the_simulation_respects_the_physical_limits(sim) -> None:  # type: ignore[no-untyped-def]
    for r in RESOURCES:
        assert max(sim.truth.series[r]) <= 1.0 + 1e-9
    a = pipeline.analyze(sim.inventory, sim.facility, Params(), asof=len(sim.truth.series["space"]) - 1)
    assert all(x["alloc_kw"] <= x["power_kw"] + 1e-9 for x in a["racks"])


def test_the_truth_is_what_the_analysis_measures_on_the_history(sim) -> None:  # type: ignore[no-untyped-def]
    """Two bookkeepings that share no code (the simulation's running totals and the analysis' sums over months) agree."""
    hist = sim.inventory.at(sim.truth.months - 1)
    a = pipeline.analyze(hist, sim.facility, Params(), asof=sim.truth.months - 1)
    for r in RESOURCES:
        assert a["series"][r] == pytest.approx(sim.truth.series[r][: sim.truth.months], abs=1e-9)


def test_generate_hands_over_the_history_only() -> None:
    fac, inv, truth = generate(GenParams(months=30, future=20, seed=SEED))
    assert inv.last_month() <= 29
    assert all(r == model.NEVER or r <= 29 for r in inv.removed)
    assert len(truth.series["space"]) == 50 and truth.months == 30 and len(truth.rejected) == 50
    assert len(fac.racks) == 24


def test_truth_round_trip_and_first_crossing() -> None:
    t = Truth(3, 1, {"space": [0.1, 0.5, 0.9, 0.95], "power": [0.0] * 4, "cooling": [0.0] * 4}, [0, 0, 1, 0])
    assert Truth.from_dict(json.loads(json.dumps(t.to_dict()))) == t
    assert t.first_crossing("space", 0.9, 0) == 2
    assert t.first_crossing("space", 0.9, 2) == 3  # strictly after
    assert t.first_crossing("space", 0.99, 0) is None


def test_the_demand_grows_and_something_is_rejected_once_full() -> None:
    s = simulate(GenParams(months=60, future=72, seed=1))
    assert s.truth.series["space"][59] > s.truth.series["space"][0] + 0.2
    assert sum(s.truth.rejected) > 0
    assert np.isfinite(list(s.truth.series.values())).all()


def test_fixed_plants_are_used_as_given() -> None:
    s = simulate(GenParams(months=6, future=2, seed=1, power_unit_kw=100.0, cooling_unit_kw=50.0, racks=4))
    assert s.facility.power.usable_kw == 200.0 and s.facility.cooling.usable_kw == 100.0 and len(s.facility.racks) == 4
