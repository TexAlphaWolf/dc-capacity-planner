"""The report: the analysis of one inventory, and how it did against the truth when there is one."""

from __future__ import annotations

from typing import Any

from dccapacity import core, pipeline, score
from dccapacity.generate import Truth
from dccapacity.model import Facility, Inventory
from dccapacity.params import RESOURCES, Params


def build_report(
    inv: Inventory, fac: Facility, p: Params, truth: Truth | None, source: str, asof: int | None = None
) -> dict[str, Any]:
    if asof is None:
        asof = truth.months - 1 if truth is not None else inv.last_month()
    a = pipeline.analyze(inv, fac, p, asof)
    return {
        "kind": "report",
        "source": source,
        "facility_name": fac.name,
        "params": p.as_dict(),
        "analysis": a,
        "accuracy": _accuracy(a, truth, p) if truth is not None else None,
    }


def _accuracy(a: dict[str, Any], truth: Truth, p: Params) -> dict[str, Any]:
    sc = score.score(a, truth, p)
    asof = a["asof"]["month"]
    sc["truth"] = {r: truth.series[r][asof:] for r in RESOURCES}  # what the utilization really did from now on
    return sc


def plan(
    inv: Inventory,
    fac: Facility,
    p: Params,
    asof: int,
    adds: list[tuple[str, int]],
    monthly: list[tuple[str, int]],
    horizon: int | None = None,
) -> dict[str, Any]:
    """Put new devices in (first fit, under the limits) and say what fits; optionally keep adding the same devices every month
    until something stops them."""
    state = pipeline.make_state(inv, fac, p, asof)
    rows = []
    for model, count in adds:
        h, a, m = core.device_of(model, p)
        placed, why = 0, None
        for _ in range(count):
            w = state.place(h, a, m)
            if w is not None:
                why = w
                break
            placed += 1
        rows.append({"model": model, "wanted": count, "placed": placed, "blocked_by": why})
    cap = core.capacities(fac)
    after = {
        "space": state.used_u / cap["space"],
        "power": state.alloc / cap["power"],
        "cooling": state.meas / cap["cooling"],
    }
    run = None
    if monthly:
        run = core.runway(
            state, [(*core.device_of(mo, p), c) for mo, c in monthly], p.horizon if horizon is None else horizon
        )
    return {"asof": {"month": asof, "label": fac.label(asof)}, "adds": rows, "after": after, "runway": run}
