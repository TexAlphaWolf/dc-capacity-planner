"""Command line: generate, validate, analyze, plan, verify, bench, render."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from dccapacity import __version__, analysis, bench, model, report, verify
from dccapacity.generate import GenParams, Truth, generate
from dccapacity.model import Facility, Inventory, ModelError
from dccapacity.params import CATALOG, RESOURCES, ParamError, Params

Error = (ModelError, ParamError, ValueError)
DEMO = "demo data center (synthetic, 60 months, seed 1)"
UNIT = {"space": "U", "power": "kW", "cooling": "kW"}


def params_from(args: argparse.Namespace) -> Params:
    given = {f.name: getattr(args, f.name) for f in fields(Params) if getattr(args, f.name, None) is not None}
    return Params(**given)


def read_truth(path: str) -> Truth:
    try:
        return Truth.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ModelError(f"cannot read the truth file {path}: {exc}") from exc


def load(a: argparse.Namespace) -> tuple[Facility, Inventory, Truth | None, str]:
    if a.facility or a.inventory:
        if not (a.facility and a.inventory):
            raise ModelError("give both the facility file and the inventory file, or neither (the demo data center)")
        fac = model.read_facility(a.facility)
        return (
            fac,
            model.read_inventory(a.inventory, fac),
            (read_truth(a.truth) if getattr(a, "truth", None) else None),
            a.inventory,
        )
    if getattr(a, "truth", None):
        raise ModelError("--truth needs the facility and inventory files it belongs to")
    fac, inv, truth = generate(GenParams())
    return fac, inv, truth, DEMO


def asof_of(a: argparse.Namespace, fac: Facility, default: int | None) -> int | None:
    if not getattr(a, "asof", None):
        return default
    m = model.month_index(a.asof, fac.start)
    if m < 0:
        raise ModelError(f"--asof {a.asof} is before the facility start {fac.start}")
    return m


def summary_lines(rep: dict[str, Any]) -> list[str]:
    a = rep["analysis"]
    n = a["now"]
    fac = a["facility"]
    lines = [
        f"{rep['source']}: {fac['racks']} racks, {fac['total_units']:,} U; {a['inventory']['installed_now']:,} devices installed as of {a['asof']['label']}",
        f"space {100 * n['space']['utilization']:.1f}% of {n['space']['capacity']:,.0f} U (limit {100 * n['space']['limit']:.0f}%), "
        f"power {100 * n['power']['utilization']:.1f}% of {n['power']['capacity']:,.1f} kW (limit {100 * n['power']['limit']:.0f}%), "
        f"cooling {100 * n['cooling']['utilization']:.1f}% of {n['cooling']['capacity']:,.1f} kW (limit {100 * n['cooling']['limit']:.0f}%)",
    ]
    b = a["binding"]
    if b:
        f = a["forecast"][b["resource"]]
        span = (
            f"{f['months_early']:.0f} to {f['months_late']:.0f}"
            if f["months_late"] is not None
            else f"{f['months_early']:.0f} or more"
        )
        lines.append(
            f"first to run out: {b['resource']} in {b['months_left']:.0f} months ({f['month']}), interval {span} months"
        )
    else:
        lines.append("no resource is forecast to reach its limit within the horizon")
    more = ", ".join(f"{k} {v['count']:,}{'+' if v['blocked_by'] == 'limit' else ''}" for k, v in a["headroom"].items())
    lines.append(f"how many more fit: {more}")
    acc = rep["accuracy"]
    if acc:
        parts = []
        for r in RESOURCES:
            c = acc["resources"][r]
            if c is None:
                parts.append(f"{r} already over")
            elif c["true_left"] is None:
                parts.append(f"{r} never reaches it")
            else:
                parts.append(f"{r} {c['true_left']} months")
        lines.append("what happened next (months to the limit): " + ", ".join(parts))
    return lines


def cmd_generate(a: argparse.Namespace) -> int:
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("facility.json", "inventory.csv", "truth.json"):
        if (out / name).exists():
            raise ModelError(f"{out / name} already exists")
    fac, inv, truth = generate(GenParams(months=a.months, future=a.future, seed=a.seed))
    model.write_facility(fac, out / "facility.json")
    model.write_inventory(inv, fac, out / "inventory.csv")
    (out / "truth.json").write_text(json.dumps(truth.to_dict(), indent=1) + "\n", encoding="utf-8")
    print(
        f"written: {out / 'facility.json'}, {out / 'inventory.csv'}, {out / 'truth.json'} ({len(inv):,} devices, {a.months} months)"
    )
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    fac = model.read_facility(a.facility)
    inv = model.read_inventory(a.inventory, fac)
    print(
        f"ok: {len(fac.racks)} racks ({fac.total_units:,} U) from {fac.start}; {len(inv):,} devices, "
        f"installed between {fac.label(min(inv.installed)) if len(inv) else 'n/a'} and {fac.label(inv.last_month())}"
    )
    return 0


def cmd_analyze(a: argparse.Namespace) -> int:
    fac, inv, truth, source = load(a)
    rep = analysis.build_report(inv, fac, params_from(a), truth, source, asof_of(a, fac, None))
    for line in summary_lines(rep):
        print(line)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
        (out / "report.md").write_text(report.render_report(rep), encoding="utf-8")
        report.report_figure(rep, out / "summary.png")
        print(f"written: {out / 'report.json'}, {out / 'report.md'}, {out / 'summary.png'}")
    return 0


def pairs(items: list[str] | None, what: str) -> list[tuple[str, int]]:
    out = []
    for it in items or []:
        name, _, count = it.partition("=")
        if name not in CATALOG:
            raise ParamError(f"{what}: unknown model '{name}' (known: {', '.join(CATALOG)})")
        try:
            n = int(count)
        except ValueError:
            raise ParamError(f"{what}: '{it}' is not written MODEL=COUNT") from None
        if n < 1:
            raise ParamError(f"{what}: the count in '{it}' must be at least 1")
        out.append((name, n))
    return out


def cmd_plan(a: argparse.Namespace) -> int:
    fac, inv, _truth, source = load(a)
    p = params_from(a)
    asof = asof_of(a, fac, None)
    asof = inv.last_month() if asof is None else asof
    adds, monthly = pairs(a.add, "--add"), pairs(a.monthly, "--monthly")
    if not adds and not monthly:
        raise ParamError("nothing to plan: give --add MODEL=COUNT and/or --monthly MODEL=COUNT")
    res = analysis.plan(inv, fac, p, asof, adds, monthly)
    print(f"{source}, as of {res['asof']['label']}")
    for r in res["adds"]:
        tail = "" if r["placed"] == r["wanted"] else f"; the next one does not fit: {report.BLOCK[r['blocked_by']]}"
        print(f"add {r['wanted']:,} x {r['model']}: {r['placed']:,} placed{tail}")
    if adds:
        print(
            "after that: "
            + ", ".join(f"{k} {100 * v:.1f}% (limit {100 * p.limit(k):.0f}%)" for k, v in res["after"].items())
        )
    run = res["runway"]
    if run:
        what = ", ".join(f"{c} x {m}" for m, c in monthly)
        if run["beyond_horizon"]:
            print(f"adding {what} every month: fits for the whole horizon of {run['months']} months")
        else:
            print(
                f"adding {what} every month: {run['months']} full months fit; in month {run['months'] + 1} "
                f"{run['placed_in_last_month']} fit and then {report.BLOCK[run['blocked_by']]} stops it"
            )
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    checks = verify.verify(a.draws, a.seed)
    bad = [c for c in checks if not c.ok]
    for c in checks:
        print(
            f"{'ok  ' if c.ok else 'FAIL'} {c.name}: {c.numbers:,} values, largest relative difference {c.max_rel_error:.2e} ({c.detail})"
        )
    print(f"{len(checks) - len(bad)} of {len(checks)} comparisons agree with the literal implementation")
    return 1 if bad else 0


def cmd_bench(a: argparse.Namespace) -> int:
    sizes = [int(p.replace("_", "")) for p in a.sizes.split(",") if p.strip()]
    if not sizes or any(s < 100 for s in sizes):
        raise ValueError("--sizes needs at least one whole number of 100 or more")
    result = bench.run_bench(
        sizes, a.repeat, a.seed, a.draws, a.cmdline, a.ref_devices, a.seeds, lambda m: print(m, flush=True)
    )
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bench.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    (out / "bench.md").write_text(report.render_bench(result), encoding="utf-8")
    report.bench_figure(result, out / "summary.png")
    print(f"written: {out / 'bench.json'}, {out / 'bench.md'}, {out / 'summary.png'}")
    return 0 if result["verification"]["ok"] else 1


def cmd_render(a: argparse.Namespace) -> int:
    try:
        data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelError(f"cannot read {a.file}: {exc}") from exc
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind not in ("report", "bench"):
        raise ModelError(f"{a.file} is neither a report.json nor a bench.json")
    text = report.render_report(data) if kind == "report" else report.render_bench(data)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"written: {a.output}")
    else:
        print(text, end="")
    if a.figure:
        (report.report_figure if kind == "report" else report.bench_figure)(data, Path(a.figure))
        print(f"written: {a.figure}")
    return 0


HELP = {
    "derate": "power is allocated as nameplate times this",
    "space_limit": "share of the rack units that may be used",
    "power_limit": "share of the usable power that may be allocated",
    "cooling_limit": "share of the usable cooling that the heat may reach",
    "window": "months of history the forecast is fitted to",
    "min_history": "fewest months a forecast is made from",
    "z": "width of the interval in standard deviations (1.645 is 90%%)",
    "horizon": "months ahead beyond which a crossing is not reported",
}


def policy_args(sp: argparse.ArgumentParser) -> None:
    for f in fields(Params):
        sp.add_argument(
            "--" + f.name.replace("_", "-"),
            dest=f.name,
            type=int if f.type == "int" else float,
            help=f"{HELP[f.name]} (default {f.default:g})",
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dccap", description="Capacity planning for a data center.")
    p.add_argument("--version", action="version", version=f"dccap {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def inputs(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("facility", nargs="?", help="facility JSON (default: a synthetic demo data center)")
        sp.add_argument("inventory", nargs="?", help="inventory CSV")
        sp.add_argument("--asof", help="analyse the data center as it was at the end of this month (YYYY-MM)")

    g = sub.add_parser("generate", help="write a synthetic data center: facility.json, inventory.csv and truth.json")
    g.add_argument("output", help="directory to write into")
    g.add_argument("--months", type=int, default=60, help="months of history in the inventory")
    g.add_argument("--future", type=int, default=72, help="months simulated after it, kept in the truth")
    g.add_argument("--seed", type=int, default=1)
    g.set_defaults(func=cmd_generate)

    v = sub.add_parser("validate", help="read a facility and an inventory and say what is in them")
    v.add_argument("facility")
    v.add_argument("inventory")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser(
        "analyze", help="where space, power and cooling stand and when each runs out (the demo without files)"
    )
    inputs(r)
    r.add_argument("--truth", help="the truth file of a synthetic data center, to score the forecast")
    r.add_argument("--out", help="write report.json, report.md and summary.png here")
    policy_args(r)
    r.set_defaults(func=cmd_analyze)

    q = sub.add_parser(
        "plan", help="what-if: place new devices, or keep adding some every month until something stops it"
    )
    inputs(q)
    q.add_argument(
        "--add", action="append", metavar="MODEL=COUNT", help=f"add devices now (models: {', '.join(CATALOG)})"
    )
    q.add_argument("--monthly", action="append", metavar="MODEL=COUNT", help="then keep adding these every month")
    policy_args(q)
    q.set_defaults(func=cmd_plan)

    c = sub.add_parser(
        "verify", help="compare with the literal implementation on random facilities; exit 1 on a difference"
    )
    c.add_argument("--draws", type=int, default=25)
    c.add_argument("--seed", type=int, default=1)
    c.set_defaults(func=cmd_verify)

    b = sub.add_parser(
        "bench", help="speed of the analysis, forecast accuracy, and agreement with the literal implementation"
    )
    b.add_argument("--sizes", default="10000,100000,300000,1000000")
    b.add_argument("--repeat", type=int, default=5)
    b.add_argument("--draws", type=int, default=50)
    b.add_argument("--ref-devices", type=int, default=3000)
    b.add_argument("--seeds", type=int, default=50, help="simulated data centers (seeds 1..N) for the accuracy sweep")
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--out", default="dccap-out")
    b.set_defaults(func=cmd_bench)

    n = sub.add_parser("render", help="rebuild the Markdown (and figure) from report.json or bench.json")
    n.add_argument("file")
    n.add_argument("-o", "--output")
    n.add_argument("--figure")
    n.set_defaults(func=cmd_render)
    return p


def main(argv: list[str] | None = None) -> int:
    given = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(given)
    args.cmdline = " ".join(given)
    try:
        return int(args.func(args))
    except Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
