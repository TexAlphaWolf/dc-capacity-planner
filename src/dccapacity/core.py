"""What both implementations share: the placement loops built on a `place` step, and the final report layout. The two
implementations (pipeline.py with NumPy, reference.py with plain loops) each compute the series, the rack table, the
forecast fits and the placement step on their own; they are compared by `verify`."""

from __future__ import annotations

import math
from typing import Any, Protocol

from dccapacity.model import Facility, Inventory
from dccapacity.params import CATALOG, RESOURCES, Params

MAX_FILL = 1_000  # "how many more fit" stops counting here
REASONS = ("cooling", "power", "space", "rack_power")


class State(Protocol):
    """Where things stand in the facility; `place` puts one more device in (first fit) or says what stopped it."""

    def place(self, height: int, alloc_kw: float, meas_kw: float) -> str | None: ...

    def clone(self) -> State: ...


def device_of(model: str, p: Params) -> tuple[int, float, float]:
    """(height in U, allocated kW, measured kW) of a catalog device."""
    h, nameplate, avg = CATALOG[model]
    return h, nameplate * p.derate / 1000.0, avg / 1000.0


def fill(state: State, height: int, alloc_kw: float, meas_kw: float) -> tuple[int, str]:
    """Put identical devices in one after another until one does not fit: how many, and what stopped the next one."""
    n = 0
    while n < MAX_FILL:
        why = state.place(height, alloc_kw, meas_kw)
        if why is not None:
            return n, why
        n += 1
    return n, "limit"


def runway(state: State, monthly: list[tuple[int, float, float, int]], max_months: int) -> dict[str, Any]:
    """Add the same devices every month until something does not fit: how many full months that lasts, and what stopped it."""
    work = state.clone()
    months = 0
    placed = 0
    while months < max_months:
        for h, a, m, count in monthly:
            for _ in range(count):
                why = work.place(h, a, m)
                if why is not None:
                    return {
                        "months": months,
                        "placed_in_last_month": placed,
                        "blocked_by": why,
                        "beyond_horizon": False,
                    }
                placed += 1
        months += 1
        placed = 0
    return {"months": months, "placed_in_last_month": 0, "blocked_by": None, "beyond_horizon": True}


def capacities(fac: Facility) -> dict[str, float]:
    return {"space": float(fac.total_units), "power": fac.power.usable_kw, "cooling": fac.cooling.usable_kw}


def assemble(inv: Inventory, fac: Facility, p: Params, asof: int, parts: dict[str, Any]) -> dict[str, Any]:
    """The report layout, from what an implementation computed (`parts`). Plain Python on small data."""
    cap = capacities(fac)
    series = parts["series"]  # resource -> utilization per month, 0..asof
    used = {r: series[r][asof] * cap[r] for r in RESOURCES}
    present = sum(1 for i in range(len(inv)) if inv.installed[i] <= asof < inv.removed[i])
    now = {}
    for r in RESOURCES:
        limit = p.limit(r)
        now[r] = {
            "used": used[r],
            "capacity": cap[r],
            "limit": limit,
            "utilization": series[r][asof],
            "headroom": cap[r] * limit - used[r],
            "over_limit": series[r][asof] >= limit,
        }
    racks = []
    min_alloc = min(device_of(k, p)[1] for k in CATALOG)
    stranded_u = 0
    stranded_kw = 0.0
    for rk, x in zip(fac.racks, parts["racks"], strict=True):
        free_u = rk.units - x["used_u"]
        head = rk.power_kw - x["alloc_kw"]
        if head < min_alloc:
            stranded_u += free_u
        if x["largest_free_u"] == 0 and head > 0:
            stranded_kw += head
        racks.append(
            {
                "name": rk.name,
                "units": rk.units,
                "used_u": x["used_u"],
                "free_u": free_u,
                "largest_free_u": x["largest_free_u"],
                "power_kw": rk.power_kw,
                "alloc_kw": x["alloc_kw"],
                "meas_kw": x["meas_kw"],
                "power_headroom_kw": head,
            }
        )
    forecast = {}
    for r in RESOURCES:
        f = dict(parts["fits"][r])
        f["limit"] = p.limit(r)
        for k in ("months_left", "months_early", "months_late"):
            if f.get(k) is not None and f[k] > p.horizon:
                f[k] = None
                if k == "months_left":
                    f["status"] = "beyond horizon"
        for k, name in (("months_left", "month"), ("months_early", "month_early"), ("months_late", "month_late")):
            v = f.get(k)
            f[name] = None if v is None else fac.label(asof + max(0, math.ceil(v - 1e-9)))
        forecast[r] = f
    crossing = [(f["months_left"], r) for r, f in forecast.items() if f["months_left"] is not None]
    binding = min(crossing) if crossing else None
    return {
        "asof": {"month": asof, "label": fac.label(asof)},
        "facility": {
            "start": fac.start,
            "racks": len(fac.racks),
            "total_units": fac.total_units,
            "power_usable_kw": cap["power"],
            "cooling_usable_kw": cap["cooling"],
            "rack_power_kw": sum(r.power_kw for r in fac.racks),
            "oversubscription": sum(r.power_kw for r in fac.racks) / cap["power"],
        },
        "inventory": {"devices": len(inv), "installed_now": present},
        "now": now,
        "racks": racks,
        "stranded": {"space_u": stranded_u, "power_kw": stranded_kw},
        "forecast": forecast,
        "binding": None if binding is None else {"resource": binding[1], "months_left": binding[0]},
        "headroom": parts["headroom"],
        "series": {"labels": [fac.label(m) for m in range(asof + 1)], **{r: series[r] for r in RESOURCES}},
    }
