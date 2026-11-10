"""Check the NumPy analysis against the literal one on generated facilities and on random ones with odd parameters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from dccapacity import core, pipeline, reference
from dccapacity.generate import GenParams, simulate
from dccapacity.model import Facility, Inventory
from dccapacity.params import Params
from dccapacity.synth import random_facility, random_inventory

RTOL = 1e-9


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    numbers: int  # how many numbers (and strings) were compared
    max_rel_error: float
    detail: str


def compare(a: Any, b: Any, path: str = "") -> tuple[int, float, str | None]:
    """(values compared, largest relative difference, the first mismatch or None); floats within RTOL, everything else equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return 0, math.inf, f"{path}: keys differ: {sorted(a.keys() ^ b.keys())}"
        total, worst, bad = 0, 0.0, None
        for k in a:
            n, w, m = compare(a[k], b[k], f"{path}/{k}")
            total, worst, bad = total + n, max(worst, w), bad or m
        return total, worst, bad
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return 0, math.inf, f"{path}: {len(a)} items against {len(b)}"
        total, worst, bad = 0, 0.0, None
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            n, w, m = compare(x, y, f"{path}[{i}]")
            total, worst, bad = total + n, max(worst, w), bad or m
        return total, worst, bad
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return 1, 0.0, None
        rel = abs(a - b) / max(abs(a), abs(b), 1e-6)  # below 1e-6 the difference is measured against 1e-6
        if math.isclose(a, b, rel_tol=RTOL, abs_tol=1e-12):
            return 1, rel, None
        return 1, rel, f"{path}: {a!r} against {b!r}"
    if type(a) is not type(b) or a != b:
        return 1, math.inf, f"{path}: {a!r} against {b!r}"
    return 1, 0.0, None


def random_params(rng: np.random.Generator) -> Params:
    window = int(rng.integers(6, 40))
    return Params(
        derate=float(rng.uniform(0.4, 1.0)),
        space_limit=float(rng.uniform(0.3, 1.0)),
        power_limit=float(rng.uniform(0.3, 1.0)),
        cooling_limit=float(rng.uniform(0.3, 1.0)),
        window=window,
        min_history=int(rng.integers(3, window + 1)),
        z=float(rng.uniform(0.5, 3.0)),
        horizon=int(rng.integers(6, 300)),
    )


def case(name: str, inv: Inventory, fac: Facility, p: Params, asof: int | None = None) -> Check:
    a = pipeline.analyze(inv, fac, p, asof)
    b = reference.analyze(inv, fac, p, asof)
    n, worst, bad = compare(a, b)
    # the "runway" loop goes through the same two placement steps: compare it too
    mon = [(*core.device_of(m, p), c) for m, c in (("srv-1u", 3), ("gpu-4u", 1))]
    at = a["asof"]["month"]
    ra = core.runway(pipeline.make_state(inv, fac, p, at), mon, 60)
    rb = core.runway(reference.make_state(inv, fac, p, at), mon, 60)
    n2, w2, bad2 = compare(ra, rb)
    return Check(
        name,
        bad is None and bad2 is None,
        n + n2,
        max(worst, w2),
        bad or bad2 or f"{len(inv):,} devices, {len(fac.racks)} racks, {at + 1} months",
    )


def verify(draws: int = 25, seed: int = 1) -> list[Check]:
    rng = np.random.default_rng(seed)
    out = []
    sim = simulate(GenParams(months=80, seed=seed))
    out.append(case("simulated facility, default policy", sim.inventory.at(60), sim.facility, Params(), 60))
    for k in range(draws):
        fac = random_facility(rng)
        months = int(rng.integers(3, 70))
        inv = random_inventory(fac, rng, months, fill=float(rng.choice([0.1, 0.5, 0.9, 1.0])))
        asof = int(rng.integers(0, months + 6)) if k % 3 else None
        out.append(case(f"random facility {k + 1}", inv, fac, random_params(rng), asof))
    return out
