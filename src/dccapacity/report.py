"""Markdown and figures built from a report or a benchmark (both are plain JSON)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dccapacity.model import month_label
from dccapacity.params import CATALOG, RESOURCES

COLORS = {"space": "#0072b2", "power": "#d55e00", "cooling": "#009e73", "grey": "#666666", "pink": "#cc79a7"}
UNIT = {"space": "U", "power": "kW", "cooling": "kW"}
NAME = {"space": "Space", "power": "Power", "cooling": "Cooling"}
WHAT = {
    "space": "rack units in use",
    "power": "allocated power (nameplate x derate)",
    "cooling": "heat (measured draw)",
}
BLOCK = {
    "cooling": "cooling capacity",
    "power": "power capacity",
    "space": "rack space",
    "rack_power": "power in the racks that have room",
    "limit": "the counting limit",
}
MAX_RACKS_SHOWN = 30


def pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def num(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:,.{digits}f}"


def months(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0f}"


def _t(s: float) -> str:
    if s < 1e-3:
        return f"{s * 1e6:.0f} us"
    if s < 1.0:
        return f"{s * 1e3:.1f} ms"
    return f"{s:.2f} s"


def growth_text(f: dict[str, Any], cap: float, res: str) -> str:
    if f["slope"] is None:
        return "n/a"
    if f["model"] == "linear":
        return f"{f['slope'] * cap:+.1f} {UNIT[res]} a month"
    return f"{100 * f['slope']:+.2f}% a month"


NOTE = {
    "ok": "",
    "crossed": "already at or over the limit",
    "no growth": "not growing",
    "short history": "too little history",
    "beyond horizon": "later than the horizon",
}


def render_report(rep: dict[str, Any]) -> str:
    a = rep["analysis"]
    fac = a["facility"]
    p = rep["params"]
    out = [
        f"# Capacity report: {rep['facility_name']}",
        "",
        f"Source: {rep['source']}. As of {a['asof']['label']} (month {a['asof']['month']}): {a['inventory']['installed_now']:,} devices installed "
        f"in {fac['racks']} racks ({fac['total_units']:,} U), usable power {fac['power_usable_kw']:,.1f} kW, usable cooling {fac['cooling_usable_kw']:,.1f} kW "
        f"(spare units already taken out). Policy: use at most {pct(p['space_limit'], 0)} of the space, {pct(p['power_limit'], 0)} of the power and "
        f"{pct(p['cooling_limit'], 0)} of the cooling; power is allocated at {pct(p['derate'], 0)} of nameplate.",
        "",
        "## 1. Where things stand",
        "",
        "| Resource | Measured as | Used | Capacity | Utilization | Limit | Room to the limit |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in RESOURCES:
        n = a["now"][r]
        room = n["headroom"]
        out.append(
            f"| {NAME[r]} | {WHAT[r]} | {n['used']:,.1f} {UNIT[r]} | {n['capacity']:,.1f} {UNIT[r]} | {pct(n['utilization'])} | {pct(n['limit'], 0)} | "
            + (f"{room:,.1f} {UNIT[r]}" if room >= 0 else f"over by {-room:,.1f} {UNIT[r]}")
            + " |"
        )
    ratio = a["now"]["power"]["used"] / a["now"]["cooling"]["used"] if a["now"]["cooling"]["used"] > 0 else None
    out += [
        "",
        f"The racks could draw {fac['rack_power_kw']:,.0f} kW between them, {num(fac['oversubscription'], 2)} times the usable power: power is oversubscribed across racks."
        + (f" The power allocated is {num(ratio, 2)} times what the devices actually draw." if ratio else ""),
        "",
        "## 2. When each resource reaches its limit",
        "",
        f"A line and an exponential are fitted to the last {p['window']} months and the one that follows the data more closely is kept. The interval is the crossing time "
        f"plus and minus {p['z']:g} standard deviations ({'90%' if abs(p['z'] - 1.645) < 1e-9 else 'z = ' + format(p['z'], 'g')}) of how long a random walk with that drift and the "
        f"month-to-month spread seen in the window takes to cover the remaining distance. Crossings later than {p['horizon']} months are not reported.",
        "",
        "| Resource | Model | Growth | Reaches the limit | In months | Interval (months) | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in RESOURCES:
        f = a["forecast"][r]
        if f["months_early"] is None:
            interval = "n/a"
        elif f["months_late"] is None:
            interval = f"{months(f['months_early'])} to no upper bound"
        else:
            interval = f"{months(f['months_early'])} to {months(f['months_late'])}"
        out.append(
            f"| {NAME[r]} | {f['model'] or 'n/a'} | {growth_text(f, a['now'][r]['capacity'], r)} | {f['month'] or 'n/a'} | {months(f['months_left'])} | {interval} | {NOTE[f['status']]} |"
        )
    b = a["binding"]
    out += [
        "",
        f"First to run out: {NAME[b['resource']].lower()}, in about {b['months_left']:.0f} months."
        if b
        else "No resource is forecast to reach its limit within the horizon.",
    ]
    racks = sorted(a["racks"], key=lambda x: -x["used_u"] / x["units"])[:MAX_RACKS_SHOWN]
    out += [
        "",
        "## 3. Racks"
        + (f" (the {MAX_RACKS_SHOWN} fullest of {len(a['racks'])})" if len(a["racks"]) > MAX_RACKS_SHOWN else ""),
        "",
        "| Rack | Units used | Largest free block | Allocated power | Heat | Power left in the rack |",
        "|---|---|---|---|---|---|",
    ]
    for x in racks:
        out.append(
            f"| {x['name']} | {x['used_u']} of {x['units']} | {x['largest_free_u']} U | {x['alloc_kw']:.1f} of {x['power_kw']:.1f} kW | {x['meas_kw']:.1f} kW | {x['power_headroom_kw']:.1f} kW |"
        )
    s = a["stranded"]
    out += [
        "",
        "## 4. Stranded capacity",
        "",
        f"{s['space_u']:,} free rack units sit in racks with too little power left for even the smallest standard device; "
        f"{s['power_kw']:.1f} kW of rack power is left in racks that have no free unit.",
        "",
        "## 5. How many more fit",
        "",
        "Devices of one model placed one after another, first fit, under the same limits (counting stops at 1,000).",
        "",
        "| Model | Size | Allocated power | Heat | More that fit | Stopped by |",
        "|---|---|---|---|---|---|",
    ]
    for name, h in a["headroom"].items():
        u, nameplate, avg = CATALOG[name]
        derate = p["derate"]
        out.append(
            f"| {name} | {u} U | {nameplate * derate / 1000:.2f} kW | {avg / 1000:.2f} kW | {h['count']:,}{'+' if h['blocked_by'] == 'limit' else ''} | {BLOCK[h['blocked_by']]} |"
        )
    acc = rep.get("accuracy")
    if acc:
        out += [
            "",
            "## 6. Against what happened next",
            "",
            f"The simulation ran {acc['months_known']} more months after this date. Months until the limit was reached, forecast against true:",
            "",
            "| Resource | True | Forecast | Error | Inside the interval |",
            "|---|---|---|---|---|",
        ]
        for r in RESOURCES:
            c = acc["resources"][r]
            if c is None:
                out.append(f"| {NAME[r]} | already over the limit | | | |")
                continue
            err = f"{c['error']:+.1f}" if "error" in c else "n/a"
            inside = {True: "yes", False: "no"}.get(c.get("in_interval"), "n/a")
            true_txt = "not within the simulated future" if c["true_left"] is None else f"{c['true_left']}"
            pred_txt = "no crossing" if c["pred_left"] is None else f"{c['pred_left']:.1f}"
            out.append(f"| {NAME[r]} | {true_txt} | {pred_txt} | {err} | {inside} |")
    return "\n".join(out) + "\n"


def _curve(f: dict[str, Any], asof: int, upto: int) -> tuple[list[int], list[float]] | None:
    if f["fitted_now"] is None or f["slope"] is None:
        return None
    xs = list(range(asof, upto + 1))
    if f["model"] == "linear":
        return xs, [f["fitted_now"] + f["slope"] * (x - asof) for x in xs]
    return xs, [f["fitted_now"] * math.exp(f["slope"] * (x - asof)) for x in xs]


def report_figure(rep: dict[str, Any], path: Path) -> None:
    a = rep["analysis"]
    start = a["facility"]["start"]
    asof = a["asof"]["month"]
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.9), gridspec_kw={"width_ratios": [1.5, 1.2, 1.0]})
    ax = axes[0]
    far = [f["months_late"] or f["months_left"] for f in a["forecast"].values() if f["months_left"] is not None]
    reach = min(max([24] + [math.ceil(v) + 12 for v in far if v is not None]), 96)
    for r in RESOURCES:
        s = a["series"][r]
        ax.plot(range(len(s)), [100 * v for v in s], color=COLORS[r], lw=1.8, label=NAME[r])
        if rep.get("accuracy") and "truth" in rep["accuracy"]:
            t = rep["accuracy"]["truth"][r][: reach + 1]
            ax.plot(range(asof, asof + len(t)), [100 * v for v in t], color=COLORS[r], lw=1.0, alpha=0.35)
        c = _curve(a["forecast"][r], asof, asof + reach)
        if c:
            ax.plot(c[0], [100 * v for v in c[1]], color=COLORS[r], lw=1.4, ls="--")
        ax.axhline(100 * a["now"][r]["limit"], color=COLORS[r], lw=0.8, ls=":")
    ax.axvline(asof, color=COLORS["grey"], lw=0.8)
    ax.set_ylim(0, 110)
    ticks = list(range(0, asof + reach + 1, 24))
    ax.set_xticks(ticks, [month_label(m, start)[:4] for m in ticks])
    ax.set_ylabel("utilization (%)")
    ax.set_title(
        "History, forecast (dashed) and, faint, what happened next\ndotted lines: the policy limits", fontsize=10
    )
    ax.legend(loc="upper left", fontsize=8)
    ax = axes[1]
    racks = a["racks"]
    xs = range(len(racks))
    ax.bar(
        [x - 0.2 for x in xs],
        [100 * r["used_u"] / r["units"] for r in racks],
        width=0.4,
        color=COLORS["space"],
        label="space (U)",
    )
    ax.bar(
        [x + 0.2 for x in xs],
        [100 * r["alloc_kw"] / r["power_kw"] for r in racks],
        width=0.4,
        color=COLORS["power"],
        label="allocated power",
    )
    ax.set_xticks(
        list(xs)[:: max(1, len(racks) // 12)],
        [racks[i]["name"] for i in list(xs)[:: max(1, len(racks) // 12)]],
        rotation=60,
        fontsize=7,
    )
    ax.set_ylabel("share of the rack (%)")
    ax.set_title("Racks: space and power", fontsize=10)
    ax.legend(fontsize=8)
    ax = axes[2]
    names = list(a["headroom"])
    counts = [a["headroom"][n]["count"] for n in names]
    colors = [
        COLORS[
            {"cooling": "cooling", "power": "power", "space": "space", "rack_power": "pink", "limit": "grey"}[
                a["headroom"][n]["blocked_by"]
            ]
        ]
        for n in names
    ]
    ax.barh(names, counts, color=colors)
    for i, n in enumerate(names):
        ax.text(counts[i], i, f" {BLOCK[a['headroom'][n]['blocked_by']]}", va="center", fontsize=7)
    ax.set_xlim(0, max([*counts, 1]) * 1.8)
    ax.set_xlabel("more devices that fit")
    ax.set_title("How many more fit, and what stops them", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def render_bench(b: dict[str, Any]) -> str:
    e = b["environment"]
    ref = b["reference"]
    ref_rate = ref["devices"] / ref["seconds"]
    out = [
        "# Benchmark",
        "",
        f"Run on {e['system']}, {e['cpus']} CPUs, Python {e['python']}, NumPy {e['numpy']}; seed {e['seed']}; each time is the median of {e['repeat']} runs; command `{e['command']}`.",
        "",
        "## 1. Analysis time by inventory size",
        "",
        f"Inventories of {b['analysis'][0]['months']} months of history, synthetic, with the facility sized to hold them. The time covers everything: series, racks, forecast and the "
        "'how many more fit' search. *Literal implementation* is the time of the loop-by-loop Python version on a small inventory, scaled to each size: an extrapolation, not a measurement.",
        "",
        "| Devices | Racks | Time | Devices per second | Literal implementation (extrapolated) | Speed-up |",
        "|---|---|---|---|---|---|",
    ]
    for r in b["analysis"]:
        lit = r["devices"] / ref_rate
        out.append(
            f"| {r['devices']:,} | {r['racks']:,} | {_t(r['seconds'])} | {r['devices'] / r['seconds']:,.0f} | {_t(lit)} | {lit / r['seconds']:.0f}x |"
        )
    out += [
        "",
        f"The literal implementation analyses {ref['devices']:,} devices in {_t(ref['seconds'])} ({ref_rate:,.0f} devices per second).",
        "",
        "## 2. Simulating, reading and writing",
        "",
        "| Step | Devices | Time | Devices per second |",
        "|---|---|---|---|",
    ]
    for key, label in (
        ("simulate", "Simulate 11 years of a data center with its truth"),
        ("write", "Write the inventory CSV text"),
        ("parse", "Parse and validate the inventory CSV text"),
    ):
        r = b[key]
        out.append(f"| {label} | {r['devices']:,} | {_t(r['seconds'])} | {r['devices'] / r['seconds']:,.0f} |")
    acc = b["accuracy"]
    s = acc["summary"]
    k = s["kinds"]
    out += [
        "",
        f"## 3. Forecast accuracy against the truth, over {acc['seeds']} synthetic data centers",
        "",
        f"Seeds 1 to {acc['seeds']}; each facility is simulated for {acc['total_months']} months and analysed as of month {', '.join(str(c) for c in acc['cuts'])} "
        f"(only what was installed by then is visible). That is {s['cases'] + s['excluded_over_limit']} resource and date pairs; {s['excluded_over_limit']} were already over their limit and are left out. "
        f"Of the {s['cases']} forecasts: {k['estimate']} give a month for a crossing that really happens, {k['agree_no_crossing']} correctly say there is none within the simulated future, "
        f"{k['missed']} miss a crossing, {k['false_alarm']} announce one that does not happen.",
        "",
        f"Error is the forecast months until the limit minus the true months. Over all {s['all']['n']} estimates: median absolute error {num(s['all']['abs_error_median'])} months, "
        f"95th percentile {num(s['all']['abs_error_p95'])}, median signed error {num(s['all']['bias_median'])}; the true month is inside the 90% interval in {pct(s['all']['coverage'])} of them.",
        "",
        "| How far ahead the crossing really is | Estimates | Median abs. error (months) | 95th percentile | Median signed error | Inside the interval |",
        "|---|---|---|---|---|---|",
    ]
    for lab, x in s["by_distance"].items():
        out.append(
            f"| {lab} | {x['n']} | {num(x['abs_error_median'])} | {num(x['abs_error_p95'])} | {num(x['bias_median'])} | {pct(x['coverage'])} |"
        )
    out += [
        "",
        "| Resource | Estimates | Median abs. error (months) | 95th percentile | Median signed error | Inside the interval |",
        "|---|---|---|---|---|---|",
    ]
    for lab, x in s["by_resource"].items():
        out.append(
            f"| {NAME[lab]} | {x['n']} | {num(x['abs_error_median'])} | {num(x['abs_error_p95'])} | {num(x['bias_median'])} | {pct(x['coverage'])} |"
        )
    v = b["verification"]
    out += [
        "",
        "## 4. Agreement with the literal implementation",
        "",
        f"{v['checks']} comparisons (a simulated facility and {v['checks'] - 1} random facilities with random policy): {v['numbers']:,} numbers compared. "
        f"Largest relative difference {v['max_rel_error']:.2e} (tolerance {v['tolerance']:.0e}); {'all match' if v['ok'] else 'THERE ARE DIFFERENCES'}.",
    ]
    return "\n".join(out) + "\n"


def bench_figure(b: dict[str, Any], path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.6))
    ax = axes[0]
    ref = b["reference"]
    rows = b["analysis"]
    ax.loglog([r["devices"] for r in rows], [r["seconds"] for r in rows], "o-", color=COLORS["space"], label="NumPy")
    ax.loglog(
        [r["devices"] for r in rows],
        [r["devices"] * ref["seconds"] / ref["devices"] for r in rows],
        "s--",
        color=COLORS["grey"],
        label="literal (extrapolated)",
    )
    ax.set_xlabel("devices in the inventory")
    ax.set_ylabel("seconds")
    ax.set_title("Analysis time", fontsize=10)
    ax.legend(fontsize=8)
    s = b["accuracy"]["summary"]
    labels = list(s["by_distance"])
    ax = axes[1]
    med = [s["by_distance"][k]["abs_error_median"] or 0 for k in labels]
    p95 = [s["by_distance"][k]["abs_error_p95"] or 0 for k in labels]
    xs = range(len(labels))
    ax.bar([x - 0.2 for x in xs], med, width=0.4, color=COLORS["space"], label="median")
    ax.bar([x + 0.2 for x in xs], p95, width=0.4, color=COLORS["power"], label="95th percentile")
    ax.set_xticks(list(xs), [k.replace(" months", "") for k in labels])
    ax.set_xlabel("months until the limit is really reached")
    ax.set_ylabel("absolute error (months)")
    ax.set_title("Forecast error by how far ahead", fontsize=10)
    ax.legend(fontsize=8)
    ax = axes[2]
    cov = [100 * (s["by_distance"][k]["coverage"] or 0) for k in labels]
    ax.bar(list(xs), cov, color=COLORS["cooling"])
    ax.axhline(90, color=COLORS["grey"], ls=":", lw=1)
    ax.text(len(labels) - 0.5, 91, "90% target", ha="right", fontsize=8)
    ax.set_xticks(list(xs), [k.replace(" months", "") for k in labels])
    ax.set_ylim(0, 105)
    ax.set_xlabel("months until the limit is really reached")
    ax.set_ylabel("true month inside the interval (%)")
    ax.set_title("Interval coverage", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
