"""A synthetic data center with a known future. Projects arrive month by month (more of them as time goes on, more in some
seasons, now and then a big one), devices are placed first fit under the physical limits of racks, power and cooling, and are
removed when their life ends. The simulation runs past the history that is handed to the analysis, so what really happened
next is known and the forecasts can be scored."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from dccapacity.model import NEVER, Facility, Inventory, Plant, Rack
from dccapacity.params import CATALOG, RESOURCES

Array = np.ndarray[Any, Any]

# (model, weight): what a project is made of
MIX = (("srv-1u", 0.32), ("srv-2u", 0.26), ("stor-2u", 0.14), ("gpu-4u", 0.06), ("sw-1u", 0.22))


@dataclass(frozen=True)
class GenParams:
    months: int = 60  # the history handed to the analysis
    future: int = 72  # months simulated after it, kept for the truth
    seed: int = 1
    racks: int = 24
    units: int = 42
    rack_kw: float = 12.0
    power_unit_kw: float | None = None  # None: drawn from the seed, so every seed is a different facility
    cooling_unit_kw: float | None = None
    rate: float = 1.1  # projects per month at the start
    growth: float = 0.011  # monthly growth of that rate
    initial_fill: float = 0.25  # share of the rack units used at month 0
    life_mean: float = 66.0
    life_sd: float = 14.0


@dataclass
class Truth:
    """What really happened, month by month, for the whole simulation (history and future)."""

    months: int  # history length: the analysis sees months 0..months-1
    seed: int
    series: dict[str, list[float]] = field(default_factory=dict)  # resource -> true utilization
    rejected: list[int] = field(default_factory=list)  # devices that did not fit, per month

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Truth:
        return cls(
            int(d["months"]),
            int(d["seed"]),
            {k: [float(x) for x in v] for k, v in d["series"].items()},
            [int(x) for x in d["rejected"]],
        )

    def first_crossing(self, resource: str, limit: float, after: int) -> int | None:
        """The first month after `after` in which the utilization reaches `limit`, or None if it never does."""
        for m in range(after + 1, len(self.series[resource])):
            if self.series[resource][m] >= limit:
                return m
        return None


@dataclass
class Sim:
    facility: Facility
    inventory: Inventory  # everything, including what is installed after the history
    truth: Truth


def facility_of(g: GenParams, rng: np.random.Generator) -> Facility:
    pw = float(rng.uniform(110, 170)) if g.power_unit_kw is None else g.power_unit_kw
    cl = float(rng.uniform(70, 110)) if g.cooling_unit_kw is None else g.cooling_unit_kw
    return Facility(
        "Synthetic data center",
        "2020-01",
        tuple(Rack(f"R{i + 1:02d}", g.units, g.rack_kw) for i in range(g.racks)),
        Plant(round(pw, 1), 3, 1),
        Plant(round(cl, 1), 3, 1),
    )


def simulate(g: GenParams | None = None) -> Sim:
    g = g or GenParams()
    rng = np.random.default_rng(g.seed)
    fac = facility_of(g, rng)
    total = g.months + g.future
    cap = {"space": float(fac.total_units), "power": fac.power.usable_kw, "cooling": fac.cooling.usable_kw}
    occ: Array = np.zeros((g.racks, g.units), dtype=bool)
    rack_alloc = np.zeros(g.racks)
    used_u, alloc, meas = 0, 0.0, 0.0
    inv = Inventory()
    removals: dict[int, list[tuple[int, int, int, float, float]]] = {}
    names = [m for m, _ in MIX]
    weights = np.array([w for _, w in MIX])
    weights = weights / weights.sum()
    truth = Truth(g.months, g.seed, {r: [] for r in RESOURCES}, [])
    derate = 0.8  # the truth of "power" is the allocation the planner makes at its default derate: nameplate x 0.8

    def place(model: str, month: int, life: int) -> bool:
        nonlocal used_u, alloc, meas
        h, nameplate, avg = CATALOG[model]
        nameplate *= float(rng.uniform(0.9, 1.1))
        avg = min(nameplate, avg * float(rng.uniform(0.7, 1.3)))
        a, m = nameplate * derate / 1000.0, avg / 1000.0
        if meas + m > cap["cooling"] or alloc + a > cap["power"]:
            return False
        cs = np.concatenate([np.zeros((g.racks, 1), dtype=np.int64), np.cumsum(occ, axis=1)], axis=1)
        ok = (cs[:, h:] - cs[:, : g.units + 1 - h]) == 0
        feasible = ok.any(axis=1) & (rack_alloc + a <= g.rack_kw)
        if not feasible.any():
            return False
        r = int(np.argmax(feasible))
        s = int(np.argmax(ok[r]))
        occ[r, s : s + h] = True
        rack_alloc[r] += a
        used_u += h
        alloc += a
        meas += m
        end = month + life
        inv.add(f"{model}-{len(inv):05d}", r, s + 1, h, nameplate, avg, month, end if end < total else NEVER)
        if end < total:
            removals.setdefault(end, []).append((r, s, h, a, m))
        return True

    def life() -> int:
        return max(24, round(float(rng.normal(g.life_mean, g.life_sd))))

    while used_u < g.initial_fill * fac.total_units:  # the facility as it stands at month 0
        place(names[int(rng.choice(len(names), p=weights))], 0, int(rng.integers(6, round(g.life_mean * 1.3))))
    for m in range(total):
        if m > 0:
            for r, s, h, a, mm in removals.pop(m, []):
                occ[r, s : s + h] = False
                rack_alloc[r] -= a
                used_u -= h
                alloc -= a
                meas -= mm
            lam = g.rate * (1 + g.growth) ** m * (1 + 0.25 * math.sin(2 * math.pi * (m + 3) / 12))
            rejected = 0
            for _ in range(int(rng.poisson(lam))):
                big = rng.random() < 0.03
                count = int(rng.integers(15, 41)) if big else 1 + int(rng.geometric(1 / 3.0)) - 1 + 1
                model = names[int(rng.choice(len(names), p=weights))]
                for _ in range(min(count, 40)):
                    if not place(model, m, life()):
                        rejected += 1
            truth.rejected.append(rejected)
        else:
            truth.rejected.append(0)
        truth.series["space"].append(used_u / cap["space"])
        truth.series["power"].append(max(alloc, 0.0) / cap["power"])
        truth.series["cooling"].append(max(meas, 0.0) / cap["cooling"])
    return Sim(fac, inv, truth)


def generate(g: GenParams | None = None) -> tuple[Facility, Inventory, Truth]:
    """The facility, its inventory as known at the end of the history, and the truth (history and future)."""
    g = g or GenParams()
    sim = simulate(g)
    return sim.facility, sim.inventory.at(g.months - 1), sim.truth
