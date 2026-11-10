"""The literal implementation: every number from plain loops over devices, months, racks and rack units, written the way the
definition reads. Slow on purpose; `verify` holds the NumPy implementation (pipeline.py) to it."""

from __future__ import annotations

import math
from typing import Any

from dccapacity import core
from dccapacity.model import Facility, Inventory
from dccapacity.params import CATALOG, RESOURCES, Params


class RefState:
    """Occupancy as a list of booleans per rack; first fit scans the units one by one."""

    def __init__(self, fac: Facility, p: Params) -> None:
        self.fac = fac
        self.p = p
        self.occ: list[list[bool]] = [[False] * r.units for r in fac.racks]
        self.rack_alloc = [0.0] * len(fac.racks)
        self.used_u = 0
        self.alloc = 0.0
        self.meas = 0.0

    def clone(self) -> RefState:
        c = RefState(self.fac, self.p)
        c.occ = [list(o) for o in self.occ]
        c.rack_alloc = list(self.rack_alloc)
        c.used_u, c.alloc, c.meas = self.used_u, self.alloc, self.meas
        return c

    def put(self, rack: int, u: int, height: int, alloc_kw: float, meas_kw: float) -> None:
        for k in range(height):
            self.occ[rack][u - 1 + k] = True
        self.rack_alloc[rack] += alloc_kw
        self.used_u += height
        self.alloc += alloc_kw
        self.meas += meas_kw

    def window(self, rack: int, height: int) -> int | None:
        """The lowest unit (1-based) where `height` free units in a row start, or None."""
        occ = self.occ[rack]
        for s in range(len(occ) - height + 1):
            if all(not occ[s + k] for k in range(height)):
                return s + 1
        return None

    def place(self, height: int, alloc_kw: float, meas_kw: float) -> str | None:
        fac, p = self.fac, self.p
        if self.meas + meas_kw > fac.cooling.usable_kw * p.cooling_limit + 1e-9:
            return "cooling"
        if self.alloc + alloc_kw > fac.power.usable_kw * p.power_limit + 1e-9:
            return "power"
        if self.used_u + height > fac.total_units * p.space_limit + 1e-9:
            return "space"
        fits_somewhere = False
        for r, rk in enumerate(fac.racks):
            u = self.window(r, height)
            if u is None:
                continue
            fits_somewhere = True
            if self.rack_alloc[r] + alloc_kw <= rk.power_kw + 1e-9:
                self.put(r, u, height, alloc_kw, meas_kw)
                return None
        return "rack_power" if fits_somewhere else "space"


def state_of(inv: Inventory, fac: Facility, p: Params, asof: int) -> RefState:
    st = RefState(fac, p)
    for i in range(len(inv)):
        if inv.installed[i] <= asof < inv.removed[i]:
            st.put(inv.rack[i], inv.u[i], inv.height[i], inv.nameplate_w[i] * p.derate / 1000.0, inv.avg_w[i] / 1000.0)
    return st


def monthly_series(inv: Inventory, fac: Facility, p: Params, asof: int) -> dict[str, list[float]]:
    cap = core.capacities(fac)
    out: dict[str, list[float]] = {r: [] for r in RESOURCES}
    for m in range(asof + 1):
        u = 0
        alloc = 0.0
        meas = 0.0
        for i in range(len(inv)):
            if inv.installed[i] <= m < inv.removed[i]:
                u += inv.height[i]
                alloc += inv.nameplate_w[i] * p.derate / 1000.0
                meas += inv.avg_w[i] / 1000.0
        out["space"].append(u / cap["space"])
        out["power"].append(alloc / cap["power"])
        out["cooling"].append(meas / cap["cooling"])
    return out


def rack_table(st: RefState, inv: Inventory, fac: Facility, p: Params, asof: int) -> list[dict[str, Any]]:
    meas = [0.0] * len(fac.racks)
    for i in range(len(inv)):
        if inv.installed[i] <= asof < inv.removed[i]:
            meas[inv.rack[i]] += inv.avg_w[i] / 1000.0
    rows = []
    for r in range(len(fac.racks)):
        best = run = 0
        for busy in st.occ[r]:
            run = 0 if busy else run + 1
            best = max(best, run)
        rows.append(
            {
                "used_u": sum(1 for b in st.occ[r] if b),
                "largest_free_u": best,
                "alloc_kw": st.rack_alloc[r],
                "meas_kw": meas[r],
            }
        )
    return rows


def _ols(t: list[float], y: list[float]) -> tuple[float, float, float]:
    """Centroid of t and of y, and the least-squares slope of y on t."""
    n = len(t)
    tb = sum(t) / n
    yb = sum(y) / n
    sxx = sum((x - tb) ** 2 for x in t)
    b = sum((x - tb) * (v - yb) for x, v in zip(t, y, strict=True)) / sxx
    return tb, yb, b


def _spread(path: list[float], target: float, slope: float, z: float) -> float:
    """Half-width, in months, of the interval around the crossing time. The path is treated as a random walk with drift: the
    time a walk with drift `slope` and step standard deviation s needs to cover a distance d has standard deviation
    sqrt(d s^2 / slope^3) (the first-passage time), and the drift itself is known only to s / sqrt(steps)."""
    steps = [path[i] - path[i - 1] for i in range(1, len(path))]
    m = len(steps)
    mean = sum(steps) / m
    var = sum((x - mean) ** 2 for x in steps) / (m - 1) if m > 1 else 0.0
    d = target - path[-1]
    sd = math.sqrt(d * var / slope**3 + (d / slope**2) ** 2 * var / m)
    return z * sd


def fit(util: list[float], asof: int, p: Params, limit: float) -> dict[str, Any]:
    """Fit a line, and an exponential if every value is positive, to the last `window` months; keep the one that follows the
    data more closely (the exponential only if it is clearly better); say when the limit is reached, with an interval."""
    n = min(p.window, len(util))
    y = util[len(util) - n :]
    out: dict[str, Any] = {
        "status": "ok",
        "model": None,
        "window": n,
        "slope": None,
        "fitted_now": None,
        "months_left": None,
        "months_early": None,
        "months_late": None,
    }
    if n < p.min_history:
        out["status"] = "short history"
        return out
    if y[-1] >= limit:
        out["status"] = "crossed"
        out["months_left"] = out["months_early"] = out["months_late"] = 0.0
        return out
    t = [float(asof - n + 1 + k) for k in range(n)]
    tb, yb, b = _ols(t, y)
    sse_lin = sum((v - yb - b * (x - tb)) ** 2 for x, v in zip(t, y, strict=True))
    model, centre, target, slope, path = "linear", yb, limit, b, y
    if all(v > 0 for v in y):
        ly = [math.log(v) for v in y]
        _, lb, d = _ols(t, ly)
        sse_exp = sum((v - math.exp(lb + d * (x - tb))) ** 2 for x, v in zip(t, y, strict=True))
        if sse_exp < sse_lin * (1.0 - 1e-9):
            model, centre, target, slope, path = "exponential", lb, math.log(limit), d, ly
    out["model"] = model
    out["slope"] = slope
    out["fitted_now"] = (centre + slope * (asof - tb)) if model == "linear" else math.exp(centre + slope * (asof - tb))
    if slope <= 0:
        out["status"] = "no growth"
        return out
    left = max(0.0, tb + (target - centre) / slope - asof)
    half = _spread(path, target, slope, p.z)
    out["months_left"] = left
    out["months_early"] = max(0.0, left - half)
    out["months_late"] = left + half
    return out


def analyze(inv: Inventory, fac: Facility, p: Params | None = None, asof: int | None = None) -> dict[str, Any]:
    p = p or Params()
    asof = inv.last_month() if asof is None else asof
    state = state_of(inv, fac, p, asof)
    series = monthly_series(inv, fac, p, asof)
    parts: dict[str, Any] = {
        "series": series,
        "racks": rack_table(state, inv, fac, p, asof),
        "fits": {r: fit(series[r], asof, p, p.limit(r)) for r in RESOURCES},
        "headroom": {},
    }
    for name in CATALOG:
        h, a, m = core.device_of(name, p)
        count, why = core.fill(state.clone(), h, a, m)
        parts["headroom"][name] = {"count": count, "blocked_by": why}
    return core.assemble(inv, fac, p, asof, parts)


def make_state(inv: Inventory, fac: Facility, p: Params, asof: int) -> RefState:
    return state_of(inv, fac, p, asof)
