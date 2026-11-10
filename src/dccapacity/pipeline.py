"""The analysis with NumPy: monthly series from sums over install and removal months, rack occupancy as a matrix, the forecast
as least squares on arrays, first-fit placement as window sums over the occupancy matrix. Everything here is held to the literal
implementation in reference.py by `verify`."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from dccapacity import core
from dccapacity.model import Facility, Inventory
from dccapacity.params import CATALOG, RESOURCES, Params

Array = np.ndarray[Any, Any]
CHUNK = 64  # racks looked at together by the first-fit search


class NpState:
    """Occupancy as a racks x units boolean matrix (units a rack does not have count as busy)."""

    def __init__(self, fac: Facility, p: Params) -> None:
        self.fac = fac
        self.p = p
        width = max(r.units for r in fac.racks)
        self.occ: Array = np.arange(width)[None, :] >= np.asarray([r.units for r in fac.racks])[:, None]
        self.units = np.asarray([r.units for r in fac.racks], dtype=np.int64)
        self.rack_power = np.asarray([r.power_kw for r in fac.racks], dtype=np.float64)
        self.rack_alloc: Array = np.zeros(len(fac.racks))
        self.free: Array = self.units.copy()
        self.total_u = int(self.units.sum())
        self.used_u = 0
        self.alloc = 0.0
        self.meas = 0.0

    def clone(self) -> NpState:
        c = NpState(self.fac, self.p)
        c.occ = self.occ.copy()
        c.rack_alloc = self.rack_alloc.copy()
        c.free = self.free.copy()
        c.used_u, c.alloc, c.meas = self.used_u, self.alloc, self.meas
        return c

    def place(self, height: int, alloc_kw: float, meas_kw: float) -> str | None:
        fac, p = self.fac, self.p
        if self.meas + meas_kw > fac.cooling.usable_kw * p.cooling_limit + 1e-9:
            return "cooling"
        if self.alloc + alloc_kw > fac.power.usable_kw * p.power_limit + 1e-9:
            return "power"
        if self.used_u + height > self.total_u * p.space_limit + 1e-9:
            return "space"
        fits_somewhere = False
        cand = np.flatnonzero(self.free >= height)  # racks with enough free units, in rack order
        for lo in range(0, cand.size, CHUNK):
            rows = cand[lo : lo + CHUNK]
            cs = np.concatenate([np.zeros((rows.size, 1), dtype=np.int64), np.cumsum(self.occ[rows], axis=1)], axis=1)
            ok = (cs[:, height:] - cs[:, : cs.shape[1] - height]) == 0
            has = ok.any(axis=1)
            fits_somewhere = fits_somewhere or bool(has.any())
            feasible = has & (self.rack_alloc[rows] + alloc_kw <= self.rack_power[rows] + 1e-9)
            if feasible.any():
                j = int(np.argmax(feasible))
                r = int(rows[j])
                s = int(np.argmax(ok[j]))
                self.occ[r, s : s + height] = True
                self.free[r] -= height
                self.rack_alloc[r] += alloc_kw
                self.used_u += height
                self.alloc += alloc_kw
                self.meas += meas_kw
                return None
        return "rack_power" if fits_somewhere else "space"


def state_of(inv: Inventory, fac: Facility, p: Params, asof: int) -> NpState:
    st = NpState(fac, p)
    if len(inv) == 0:
        return st
    a = inv.arrays()
    now = (a["installed"] <= asof) & (asof < a["removed"])
    rack, u, h = a["rack"][now], a["u"][now], a["height"][now]
    width = st.occ.shape[1]
    diff = np.zeros((len(fac.racks), width + 1), dtype=np.int64)
    np.add.at(diff, (rack, u - 1), 1)
    np.add.at(diff, (rack, u - 1 + h), -1)
    st.occ |= np.cumsum(diff, axis=1)[:, :width] > 0
    alloc = a["nameplate"][now] * p.derate / 1000.0
    st.rack_alloc = np.bincount(rack, weights=alloc, minlength=len(fac.racks)).astype(np.float64)
    st.free = st.units - np.bincount(rack, weights=h, minlength=len(fac.racks)).astype(np.int64)
    st.used_u = int(h.sum())
    st.alloc = float(alloc.sum())
    st.meas = float((a["avg"][now] / 1000.0).sum())
    return st


def monthly_series(inv: Inventory, fac: Facility, p: Params, asof: int) -> dict[str, list[float]]:
    cap = core.capacities(fac)
    n = asof + 1
    if len(inv) == 0:
        return {r: [0.0] * n for r in RESOURCES}
    a = inv.arrays()
    keep = a["installed"] <= asof
    inst = a["installed"][keep]
    rem = a["removed"][keep]
    gone = rem <= asof
    weights = {
        "space": a["height"][keep].astype(np.float64),
        "power": a["nameplate"][keep] * p.derate / 1000.0,
        "cooling": a["avg"][keep] / 1000.0,
    }
    count = np.cumsum(np.bincount(inst, minlength=n)[:n] - np.bincount(rem[gone], minlength=n)[:n])
    out = {}
    for r in RESOURCES:
        w = weights[r]
        add = np.bincount(inst, weights=w, minlength=n)[:n]
        sub = np.bincount(rem[gone], weights=w[gone], minlength=n)[:n]
        used = np.where(count > 0, np.maximum(np.cumsum(add - sub), 0.0), 0.0)  # an empty facility is exactly zero
        out[r] = (used / cap[r]).tolist()
    return out


def rack_table(st: NpState, inv: Inventory, fac: Facility, asof: int) -> list[dict[str, Any]]:
    R = len(fac.racks)
    meas = np.zeros(R)
    if len(inv):
        a = inv.arrays()
        now = (a["installed"] <= asof) & (asof < a["removed"])
        meas = np.bincount(a["rack"][now], weights=a["avg"][now] / 1000.0, minlength=R).astype(np.float64)
    free = ~st.occ
    run = np.zeros(R, dtype=np.int64)
    best = np.zeros(R, dtype=np.int64)
    for k in range(st.occ.shape[1]):
        run = np.where(free[:, k], run + 1, 0)
        best = np.maximum(best, run)
    used = st.occ.sum(axis=1) - (st.occ.shape[1] - st.units)
    return [
        {
            "used_u": int(used[r]),
            "largest_free_u": int(best[r]),
            "alloc_kw": float(st.rack_alloc[r]),
            "meas_kw": float(meas[r]),
        }
        for r in range(R)
    ]


def _ols(t: Array, y: Array) -> tuple[float, float, float]:
    tb = float(t.mean())
    yb = float(y.mean())
    dt = t - tb
    return tb, yb, float((dt * (y - yb)).sum()) / float((dt**2).sum())


def _spread(path: Array, target: float, slope: float, z: float) -> float:
    """Half-width of the interval around the crossing time: the path is a random walk with drift (see reference.py)."""
    steps = np.diff(path)
    m = steps.size
    var = float(((steps - steps.mean()) ** 2).sum()) / (m - 1) if m > 1 else 0.0
    d = target - float(path[-1])
    return z * math.sqrt(d * var / slope**3 + (d / slope**2) ** 2 * var / m)


def fit(util: list[float], asof: int, p: Params, limit: float) -> dict[str, Any]:
    n = min(p.window, len(util))
    y = np.asarray(util[len(util) - n :], dtype=np.float64)
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
    t = np.arange(asof - n + 1, asof + 1, dtype=np.float64)
    tb, yb, b = _ols(t, y)
    dt = t - tb
    sse_lin = float(((y - yb - b * dt) ** 2).sum())
    model, centre, target, slope, path = "linear", yb, limit, b, y
    if bool((y > 0).all()):
        ly = np.log(y)
        _, lb, d = _ols(t, ly)
        sse_exp = float(((y - np.exp(lb + d * dt)) ** 2).sum())
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
        "racks": rack_table(state, inv, fac, asof),
        "fits": {r: fit(series[r], asof, p, p.limit(r)) for r in RESOURCES},
        "headroom": {},
    }
    for name in CATALOG:
        h, a, m = core.device_of(name, p)
        count, why = core.fill(state.clone(), h, a, m)
        parts["headroom"][name] = {"count": count, "blocked_by": why}
    return core.assemble(inv, fac, p, asof, parts)


def make_state(inv: Inventory, fac: Facility, p: Params, asof: int) -> NpState:
    return state_of(inv, fac, p, asof)
