"""Score the forecast of when each resource reaches its limit against what the simulation did next."""

from __future__ import annotations

import statistics
from typing import Any

import numpy as np

from dccapacity.generate import Truth
from dccapacity.params import RESOURCES, Params

BUCKETS = ((1, 12), (13, 24), (25, 48), (49, 10_000))


def bucket_label(lo: int, hi: int) -> str:
    return f"{lo}+ months" if hi >= 10_000 else f"{lo}-{hi} months"


def case(analysis: dict[str, Any], truth: Truth, p: Params, resource: str) -> dict[str, Any] | None:
    """One resource at one point in time, or None if it is over its limit already (there is nothing to forecast)."""
    asof = analysis["asof"]["month"]
    limit = p.limit(resource)
    series = truth.series[resource]
    if asof >= len(series) - 1 or series[asof] >= limit:
        return None
    known = len(series) - 1 - asof  # months of future the truth covers
    t = truth.first_crossing(resource, limit, asof)
    f = analysis["forecast"][resource]
    left = f["months_left"]
    if left is not None and left > known:
        left = None  # a crossing beyond the simulated future cannot be checked either way
    true_left = None if t is None else t - asof
    rec: dict[str, Any] = {
        "resource": resource,
        "asof": asof,
        "true_left": true_left,
        "pred_left": left,
        "early": f["months_early"],
        "late": f["months_late"],
        "model": f["model"],
        "status": f["status"],
    }
    if true_left is None and left is None:
        rec["kind"] = "agree_no_crossing"
    elif true_left is not None and left is None:
        rec["kind"] = "missed"
    elif true_left is None:
        rec["kind"] = "false_alarm"
    else:
        rec["kind"] = "estimate"
        rec["error"] = left - true_left
        early = f["months_early"]
        late = f["months_late"]
        rec["in_interval"] = bool(early is not None and early <= true_left and (late is None or true_left <= late))
    return rec


def score(analysis: dict[str, Any], truth: Truth, p: Params) -> dict[str, Any]:
    out = {}
    for r in RESOURCES:
        c = case(analysis, truth, p, r)
        out[r] = c
    return {
        "asof": analysis["asof"]["month"],
        "months_known": len(truth.series["space"]) - 1 - analysis["asof"]["month"],
        "resources": out,
    }


def summarize(records: list[dict[str, Any]], excluded: int) -> dict[str, Any]:
    kinds = {
        k: sum(1 for r in records if r["kind"] == k) for k in ("estimate", "agree_no_crossing", "missed", "false_alarm")
    }
    est = [r for r in records if r["kind"] == "estimate"]
    err = [abs(r["error"]) for r in est]

    def block(sel: list[dict[str, Any]]) -> dict[str, Any]:
        e = [abs(r["error"]) for r in sel]
        return {
            "n": len(sel),
            "abs_error_median": statistics.median(e) if e else None,
            "abs_error_p95": float(np.percentile(e, 95)) if e else None,
            "bias_median": statistics.median([r["error"] for r in sel]) if sel else None,
            "coverage": sum(1 for r in sel if r["in_interval"]) / len(sel) if sel else None,
        }

    return {
        "cases": len(records),
        "excluded_over_limit": excluded,
        "kinds": kinds,
        "false_alarm_within_24": sum(1 for r in records if r["kind"] == "false_alarm" and r["pred_left"] <= 24),
        "all": block(est),
        "by_resource": {res: block([r for r in est if r["resource"] == res]) for res in RESOURCES},
        "by_distance": {
            bucket_label(lo, hi): block([r for r in est if lo <= r["true_left"] <= hi]) for lo, hi in BUCKETS
        },
        "by_model": {m: block([r for r in est if r["model"] == m]) for m in ("linear", "exponential")},
        "abs_error_max": max(err) if err else None,
    }
