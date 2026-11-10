"""Random but valid inventories (no two devices in the same unit at the same time), for `verify` and the benchmark."""

from __future__ import annotations

import math

import numpy as np

from dccapacity.model import NEVER, Facility, Inventory, Plant, Rack


def random_facility(rng: np.random.Generator, racks: int | None = None) -> Facility:
    n = int(rng.integers(2, 9)) if racks is None else racks
    units = [int(rng.integers(6, 49)) for _ in range(n)]
    plant = [Plant(float(rng.uniform(10, 120)), int(rng.integers(2, 5)), 1) for _ in range(2)]
    return Facility(
        "random",
        "2020-01",
        tuple(Rack(f"R{i:03d}", units[i], float(rng.uniform(3, 20))) for i in range(n)),
        plant[0],
        plant[1],
    )


def random_inventory(
    fac: Facility, rng: np.random.Generator, months: int, chain: int = 4, fill: float = 0.8, max_height: int = 4
) -> Inventory:
    """Each rack is cut into bands of 1 to `max_height` units; a band holds a chain of devices one after the other, each
    installed when the previous one is removed or later, the last one possibly still there."""
    inv = Inventory()
    k = 0
    for r, rack in enumerate(fac.racks):
        u = 1
        while u <= rack.units:
            h = min(int(rng.integers(1, max_height + 1)), rack.units - u + 1)
            if rng.random() < fill:
                cuts = np.sort(rng.integers(0, max(months, 2), size=2 * int(rng.integers(1, chain + 1))))
                for j in range(0, cuts.size - 1, 2):
                    a, b = int(cuts[j]), int(cuts[j + 1])
                    if b <= a:
                        continue
                    nameplate = float(rng.uniform(150, 2500) * math.sqrt(h))
                    avg = nameplate * float(rng.uniform(0.2, 0.95))
                    last = j + 2 >= cuts.size
                    inv.add(f"d{k}", r, u, h, nameplate, avg, a, NEVER if last and rng.random() < 0.5 else b)
                    k += 1
            u += h
    return inv


def large_inventory(devices: int, months: int, seed: int) -> tuple[Facility, Inventory]:
    """About `devices` devices in a facility sized to hold them (70% of the units in use, plants at about 55% of the policy),
    built without a Python loop per device: every used unit holds one device until a random month and another after it."""
    rng = np.random.default_rng(seed)
    units = 42
    racks = max(1, math.ceil(devices / (units * 0.7 * 2)))
    fac = Facility(
        "large",
        "2020-01",
        tuple(Rack(f"R{i:05d}", units, 12.0) for i in range(racks)),
        Plant(round(5.4 * racks, 1) + 1.0, 4, 1),
        Plant(round(3.9 * racks, 1) + 1.0, 4, 1),
    )
    used = rng.random(racks * units) < 0.7
    rack = np.repeat(np.arange(racks), units)[used]
    u = np.tile(np.arange(1, units + 1), racks)[used]
    n = int(used.sum())
    cut = rng.integers(1, max(months, 3), size=n)
    nameplate = rng.uniform(150, 600, size=2 * n)
    avg = nameplate * rng.uniform(0.2, 0.95, size=2 * n)
    inv = Inventory()
    inv.name = [f"d{i}" for i in range(2 * n)]
    inv.rack = np.concatenate([rack, rack]).tolist()
    inv.u = np.concatenate([u, u]).tolist()
    inv.height = [1] * (2 * n)
    inv.nameplate_w = nameplate.tolist()
    inv.avg_w = avg.tolist()
    inv.installed = np.concatenate([np.zeros(n, dtype=np.int64), cut]).tolist()
    inv.removed = np.concatenate([cut, np.full(n, NEVER)]).tolist()
    return fac, inv
