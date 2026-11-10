from __future__ import annotations

import os
from typing import Any

import pytest

from dccapacity import pipeline, reference
from dccapacity.generate import GenParams, Sim, simulate
from dccapacity.model import NEVER, Facility, Inventory, Plant, Rack
from dccapacity.params import Params

SEED = int(os.environ.get("DCCAP_TEST_SEED", "1"))
DRAWS = int(os.environ.get("DCCAP_TEST_DRAWS", "12"))


def small(power_kw: float = 5.0) -> Facility:
    """Two racks of 10 U (5 kW each), usable power 20 kW (3 units of 10, one spare), usable cooling 10 kW (3 units of 5, one spare)."""
    return Facility(
        "small", "2024-01", (Rack("A", 10, power_kw), Rack("B", 10, power_kw)), Plant(10.0, 3, 1), Plant(5.0, 3, 1)
    )


def inv_of(*devices: tuple[Any, ...]) -> Inventory:
    """(rack, u, height, nameplate_w, avg_w, installed[, removed]) per device."""
    inv = Inventory()
    for i, d in enumerate(devices):
        inv.add(f"d{i}", *d[:6], d[6] if len(d) > 6 else NEVER)
    return inv


def both(inv: Inventory, fac: Facility, p: Params | None = None, asof: int | None = None) -> dict[str, Any]:
    """Analyse with both implementations, insist they agree, and return the result."""
    from dccapacity.verify import compare

    a = pipeline.analyze(inv, fac, p, asof)
    b = reference.analyze(inv, fac, p, asof)
    _, _, bad = compare(a, b)
    assert bad is None, bad
    return a


@pytest.fixture(scope="session")
def sim() -> Sim:
    return simulate(GenParams(months=60, future=48, seed=SEED))
