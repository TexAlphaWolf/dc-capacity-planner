"""How fast the analysis is, how good the forecasts are, and that the two implementations still agree."""

from __future__ import annotations

import os
import platform
import statistics
import time
from collections.abc import Callable
from functools import partial
from typing import Any

import numpy as np

from dccapacity import __version__, model, pipeline, reference, score, verify
from dccapacity.generate import GenParams, simulate
from dccapacity.params import RESOURCES, Params
from dccapacity.synth import large_inventory

MONTHS = 120  # months of history of the benchmark inventories
CUTS = (36, 48, 60, 72)  # the months the facilities are analysed as of in the accuracy sweep


def timed(fn: Callable[[], object], repeat: int) -> float:
    runs = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return statistics.median(runs)


def sweep(seeds: int, cuts: tuple[int, ...] = CUTS, p: Params | None = None) -> dict[str, Any]:
    """Simulate facilities with seeds 1..seeds, forecast as of each cut and score every forecast against what happened."""
    p = p or Params()
    records: list[dict[str, Any]] = []
    excluded = 0
    total = 0
    for seed in range(1, seeds + 1):
        sim = simulate(GenParams(seed=seed))
        total = len(sim.truth.series["space"])
        for cut in cuts:
            a = pipeline.analyze(sim.inventory.at(cut), sim.facility, p, cut)
            for r in RESOURCES:
                rec = score.case(a, sim.truth, p, r)
                if rec is None:
                    excluded += 1
                else:
                    records.append(rec)
    return {"seeds": seeds, "cuts": list(cuts), "total_months": total, "summary": score.summarize(records, excluded)}


def run_bench(
    sizes: list[int],
    repeat: int,
    seed: int,
    draws: int,
    command: str,
    ref_devices: int = 3000,
    seeds: int = 50,
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    p = Params()
    progress("simulate a data center with its truth")
    sim = simulate(GenParams(seed=seed))
    sim_s = timed(partial(simulate, GenParams(seed=seed)), repeat)
    hist = sim.inventory.at(59)
    progress("write and parse the inventory CSV text")
    text = model.to_csv(hist, sim.facility)
    write_s = timed(partial(model.to_csv, hist, sim.facility), repeat)
    parse_s = timed(partial(model.parse_inventory, text, sim.facility), repeat)
    rows = []
    for n in sizes:
        progress(f"analysis of about {n:,} devices")
        fac, inv = large_inventory(n, MONTHS, seed)
        rows.append(
            {
                "devices": len(inv),
                "racks": len(fac.racks),
                "months": MONTHS,
                "seconds": timed(partial(pipeline.analyze, inv, fac, p, MONTHS - 1), repeat),
            }
        )
        del inv
    progress(f"literal implementation on about {ref_devices:,} devices")
    rfac, rinv = large_inventory(ref_devices, MONTHS, seed)
    ref_s = timed(partial(reference.analyze, rinv, rfac, p, MONTHS - 1), max(1, repeat // 2))
    progress(f"agreement with the literal implementation on {draws} random facilities")
    checks = verify.verify(draws, seed)
    progress(f"forecast accuracy over {seeds} simulated data centers")
    accuracy = sweep(seeds)
    return {
        "kind": "bench",
        "environment": {
            "dccapacity": __version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "system": f"{platform.system()} {platform.machine()}",
            "cpus": os.cpu_count(),
            "seed": seed,
            "repeat": repeat,
            "command": command,
            "seconds": round(time.perf_counter() - t0, 1),
        },
        "analysis": rows,
        "reference": {"devices": len(rinv), "seconds": ref_s},
        "simulate": {"devices": len(sim.inventory), "seconds": sim_s},
        "write": {"devices": len(hist), "seconds": write_s},
        "parse": {"devices": len(hist), "seconds": parse_s},
        "accuracy": accuracy,
        "verification": {
            "checks": len(checks),
            "numbers": sum(c.numbers for c in checks),
            "ok": all(c.ok for c in checks),
            "max_rel_error": max(c.max_rel_error for c in checks),
            "tolerance": verify.RTOL,
        },
    }
