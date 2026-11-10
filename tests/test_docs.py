"""The documentation must say what the measurements say."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from dccapacity import analysis, cli, report
from dccapacity.generate import GenParams, generate
from dccapacity.params import Params
from dccapacity.report import pct

ROOT = Path(__file__).resolve().parent.parent
REPORT = json.loads((ROOT / "docs" / "report.json").read_text(encoding="utf-8"))
BENCH = json.loads((ROOT / "docs" / "bench.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
ANALYSIS = (ROOT / "docs" / "analysis.md").read_text(encoding="utf-8")
A, ACC = REPORT["analysis"], REPORT["accuracy"]
NOW, FC, RACKS = A["now"], A["forecast"], A["racks"]
SW = BENCH["accuracy"]["summary"]
ROWS = {r["devices"]: r for r in BENCH["analysis"]}
REF_RATE = BENCH["reference"]["devices"] / BENCH["reference"]["seconds"]
ONE_LINE = re.compile(r"\s+")


def flat(text: str) -> str:
    return ONE_LINE.sub(" ", text.replace("**", ""))


def assert_close(a: Any, b: Any) -> None:
    """Equal structure; numbers equal to 9 digits (libm differs in the last digits between platforms)."""
    if isinstance(b, dict):
        assert a.keys() == b.keys()
        for k in b:
            assert_close(a[k], b[k])
    elif isinstance(b, list):
        assert len(a) == len(b)
        for x, y in zip(a, b, strict=True):
            assert_close(x, y)
    elif isinstance(b, float):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-12)
    else:
        assert a == b


def test_the_benchmark_is_what_the_text_says_it_is() -> None:
    env = BENCH["environment"]
    assert env["dccapacity"] == "1.0.0" and env["seed"] == 1 and env["repeat"] == 5 and env["cpus"] == 12
    assert env["python"] == "3.14.10" and env["numpy"] == "2.5.4"
    assert sorted(ROWS) == [10_000, 99_852, 300_082, 999_670]
    v = BENCH["verification"]
    assert (
        v["ok"] is True
        and v["checks"] == 51
        and v["numbers"] == 12_714
        and v["max_rel_error"] == pytest.approx(8.20e-14, rel=1e-2)
    )
    assert BENCH["accuracy"]["seeds"] == 50 and BENCH["accuracy"]["cuts"] == [36, 48, 60, 72]
    assert BENCH["accuracy"]["total_months"] == 132


def test_markdown_is_the_render_of_the_json(tmp_path: Path) -> None:
    for name in ("report", "bench"):
        out = tmp_path / f"{name}.md"
        assert cli.main(["render", str(ROOT / "docs" / f"{name}.json"), "-o", str(out)]) == 0
        assert out.read_text(encoding="utf-8") == (ROOT / "docs" / f"{name}.md").read_text(encoding="utf-8")


def test_the_report_is_what_the_demo_gives_today() -> None:
    fac, inv, truth = generate(GenParams())
    fresh = analysis.build_report(inv, fac, Params(), truth, cli.DEMO, None)
    assert_close(json.loads(json.dumps(fresh)), REPORT)


def test_figures_exist() -> None:
    for name in ("report.png", "bench.png"):
        assert (ROOT / "docs" / name).stat().st_size > 10_000


@pytest.mark.parametrize("text", [README, ANALYSIS], ids=["README", "analysis"])
def test_no_scaffold_left(text: str) -> None:
    assert not re.search(
        r"work in progress|TODO|TBD|lorem|measurements pending|provisional|pre-measurement", text, re.I
    )


@pytest.mark.parametrize("name", ["README.md", "docs/analysis.md"])
def test_local_links_resolve(name: str) -> None:
    path = ROOT / name
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://")):
            continue
        assert (path.parent / target).exists(), f"{name}: {target}"


def test_the_real_output_blocks_are_the_real_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["analyze"]) == 0
    block = re.search(r"`dccap analyze` \(the demo data center\):\n\n```text\n(.*?)```", README, re.S)
    assert block and block.group(1) == capsys.readouterr().out
    assert cli.main(["plan", "--add", "gpu-4u=10", "--monthly", "srv-1u=10"]) == 0
    block = re.search(r"`dccap plan --add gpu-4u=10 --monthly srv-1u=10`:\n\n```text\n(.*?)```", README, re.S)
    assert block and block.group(1) == capsys.readouterr().out


def test_the_readme_numbers_are_the_measurements() -> None:
    fac = A["facility"]
    sp, po, co = NOW["space"], NOW["power"], NOW["cooling"]
    must = [
        f"{fac['racks']} racks and {fac['total_units']:,} U",
        f"{A['inventory']['installed_now']} devices\ninstalled",
        f"space is {pct(sp['utilization'])} used (limit {pct(sp['limit'], 0)})",
        f"power {pct(po['utilization'])} allocated (limit\n   {pct(po['limit'], 0)})",
        f"cooling {pct(co['utilization'])} (limit {pct(co['limit'], 0)})",
        f"Power is forecast to reach its limit in {FC['power']['month']}, with a 90% interval of "
        f"{FC['power']['months_early']:.0f} to {FC['power']['months_late']:.0f} months",
        f"{po['used']:.1f} kW",
        f"{co['used']:.1f} kW",
        f"{po['used'] / co['used']:.2f} times what is drawn",
        f"{fac['rack_power_kw']:.0f} kW between them, {fac['oversubscription']:.2f} times the usable power",
        f"{A['stranded']['space_u']} free units",
        f"{A['stranded']['power_kw']:.1f} kW of rack power",
        f"{ACC['resources']['power']['true_left']} months (forecast {FC['power']['months_left']:.1f}",
        f"space after {ACC['resources']['space']['true_left']} (forecast {FC['space']['months_left']:.1f}",
        f"{FC['cooling']['months_left']:.1f} months and never reaches its limit",
        f"{SW['kinds']['estimate'] + SW['kinds']['agree_no_crossing'] + SW['kinds']['missed'] + SW['kinds']['false_alarm']} forecasts could be checked",
        f"median error is {SW['all']['abs_error_median']:.1f} months (95th percentile {SW['all']['abs_error_p95']:.1f})",
        f"inside the 90% interval {pct(SW['all']['coverage'])} of the\n   time",
        f"{pct(SW['by_distance']['1-12 months']['coverage'])} when the limit is 1 to 12 months away",
        f"{pct(SW['by_distance']['13-24 months']['coverage'])} at 13 to 24",
        f"{pct(SW['by_distance']['25-48 months']['coverage'])} at 25\n   to 48",
        f"{pct(SW['by_distance']['49+ months']['coverage'])} beyond that",
        f"Power and cooling are {pct(SW['by_resource']['power']['coverage'])} and {pct(SW['by_resource']['cooling']['coverage'])}",
        f"space is {pct(SW['by_resource']['space']['coverage'])}",
        f"{SW['kinds']['false_alarm']} of the {SW['cases']} forecasts announce a crossing that does not happen "
        f"({SW['false_alarm_within_24']} of them within 24 months) and {SW['kinds']['missed']} miss one",
        f"{BENCH['verification']['max_rel_error']:.2e}",
        f"{BENCH['verification']['checks']} comparisons\n   and {BENCH['verification']['numbers']:,} numbers",
        f"{max(ROWS):,} devices in {ROWS[max(ROWS)]['racks']:,} racks",
        f"{ROWS[max(ROWS)]['seconds']:.2f} s, {max(ROWS) / ROWS[max(ROWS)]['seconds']:,.0f}\n   devices a second",
        f"{REF_RATE:,.0f} a second",
        f"{BENCH['environment']['cpus']} CPUs, Python {BENCH['environment']['python']} and NumPy {BENCH['environment']['numpy']}",
    ]
    text = flat(README)
    for s in must:
        assert flat(s) in text, s
    for k, count in A["headroom"].items():
        assert f"{count['count']} {k}" in text, k
        assert count["blocked_by"] == "power"


def test_the_demo_claims() -> None:
    assert FC["power"]["status"] == FC["space"]["status"] == FC["cooling"]["status"] == "ok"
    assert A["binding"]["resource"] == "power" and round(A["binding"]["months_left"]) == 9
    empty = [r["name"] for r in RACKS if r["used_u"] == 0]
    assert len(empty) == 6
    full = [r for r in RACKS if r["used_u"] > 0]
    assert len(full) == 18
    assert min(r["used_u"] for r in full) == 36 and max(r["used_u"] for r in full) == 42
    assert min(r["alloc_kw"] for r in full) == pytest.approx(9.9, abs=0.05)
    assert max(r["alloc_kw"] for r in full) == pytest.approx(12.0, abs=0.05)
    assert round(NOW["space"]["headroom"]) == 162 and NOW["power"]["headroom"] == pytest.approx(20.9, abs=0.05)
    assert round(NOW["power"]["headroom"] / 0.28) == 75  # "about 75 1U servers"
    assert NOW["space"]["utilization"] > NOW["power"]["utilization"] > NOW["cooling"]["utilization"]
    # the three forecasts are early
    for r in ("space", "power"):
        assert ACC["resources"][r]["pred_left"] < ACC["resources"][r]["true_left"]
    assert ACC["resources"]["cooling"]["kind"] == "false_alarm"
    assert ACC["resources"]["space"]["in_interval"] is True and ACC["resources"]["power"]["in_interval"] is False
    assert ACC["resources"]["space"]["error"] == pytest.approx(-11.6, abs=0.05)
    assert ACC["resources"]["power"]["error"] == pytest.approx(-11.7, abs=0.05)


def test_the_analysis_tables() -> None:
    for name, row in (("sw-1u", "1 U | 0.24 kW | 0.15 kW"), ("gpu-4u", "4 U | 1.60 kW | 1.10 kW")):
        assert f"| {name} | {row} | {A['headroom'][name]['count']} | power capacity |" in ANALYSIS
    for r in ("space", "power", "cooling"):
        f = FC[r]
        row = (
            f"| {r.capitalize()} | {f['model']} | {100 * f['slope']:+.2f}% a month | {f['month']} | "
            f"{f['months_left']:.0f} | {f['months_early']:.0f} to {f['months_late']:.0f} |"
        )
        assert row in ANALYSIS, row
    for k, label in (
        ("1-12 months", "1-12 months"),
        ("13-24 months", "13-24 months"),
        ("25-48 months", "25-48 months"),
        ("49+ months", "49+ months"),
    ):
        b = SW["by_distance"][k]
        row = (
            f"| {label} | {b['n']} | {b['abs_error_median']:.1f} | {b['abs_error_p95']:.1f} | "
            f"{b['bias_median']:.1f} | {pct(b['coverage'])} |"
        )
        assert row in ANALYSIS, row
    for k, label in (("space", "Space"), ("power", "Power"), ("cooling", "Cooling")):
        b = SW["by_resource"][k]
        row = (
            f"| {label} | {b['n']} | {b['abs_error_median']:.1f} | {b['abs_error_p95']:.1f} | "
            f"{b['bias_median']:.1f} | {pct(b['coverage'])} |"
        )
        assert row in ANALYSIS, row
    kinds = SW["kinds"]
    for label, k in (
        ("A month is forecast for a crossing that really happens (an *estimate*)", "estimate"),
        ("Correctly no crossing within the simulated future", "agree_no_crossing"),
        ("The crossing happens and the forecast does not announce one", "missed"),
        ("A crossing is announced and does not happen in the simulated future", "false_alarm"),
    ):
        assert f"| {label} | {kinds[k]} |" in ANALYSIS, label
    assert SW["cases"] == sum(kinds.values()) == 505 and SW["excluded_over_limit"] == 95
    assert f"{SW['abs_error_max']:.1f}" in ANALYSIS
    assert f"| 10,000 | {ROWS[10_000]['racks']:,} |" in ANALYSIS
    for n, row in ROWS.items():
        s = row["seconds"]
        assert f"| {n:,} | {row['racks']:,} | {report._t(s)} | {n / s:,.0f} |" in ANALYSIS
    assert f"{REF_RATE:,.0f} devices a second" in ANALYSIS
    assert f"{BENCH['parse']['devices'] / BENCH['parse']['seconds']:,.0f} devices a second" in ANALYSIS
    assert f"{BENCH['write']['devices'] / BENCH['write']['seconds']:,.0f}" in ANALYSIS


def test_the_claims_about_distance_resource_and_model() -> None:
    d = SW["by_distance"]
    near = d["1-12 months"]["n"] * d["1-12 months"]["coverage"] + d["13-24 months"]["n"] * d["13-24 months"]["coverage"]
    n_near = d["1-12 months"]["n"] + d["13-24 months"]["n"]
    assert round(near) == 159 and n_near == 184 and near / n_near == pytest.approx(0.86, abs=0.005)
    far = d["49+ months"]
    assert far["bias_median"] == -far["abs_error_median"] and far["coverage"] < 0.5
    assert [d[k]["abs_error_median"] for k in d] == sorted(d[k]["abs_error_median"] for k in d)
    assert (
        SW["by_resource"]["space"]["coverage"]
        < 0.6
        < 0.84
        < min(SW["by_resource"][k]["coverage"] for k in ("power", "cooling"))
    )
    assert abs(SW["by_resource"]["power"]["bias_median"]) < 1 and abs(SW["by_resource"]["cooling"]["bias_median"]) < 1
    m = SW["by_model"]
    assert m["exponential"]["abs_error_median"] == pytest.approx(8.0, abs=0.05)
    assert m["linear"]["abs_error_median"] == pytest.approx(10.2, abs=0.05)
    assert pct(m["exponential"]["coverage"]) == "75.0%" and pct(m["linear"]["coverage"]) == "78.8%"


def test_the_speed_claims() -> None:
    speedups = [(n / REF_RATE) / row["seconds"] for n, row in ROWS.items()]
    assert round(min(speedups)) == 7 and round(max(speedups)) == 54
    t10k, t1m = ROWS[10_000]["seconds"], ROWS[999_670]["seconds"]
    assert t1m / t10k == pytest.approx(13.5, abs=0.1)  # "a hundred times more devices costs 13 times more time"
    assert ROWS[999_670]["devices"] / ROWS[10_000]["devices"] > 99
    assert BENCH["parse"]["devices"] / BENCH["parse"]["seconds"] > 0.3 * max(n / r["seconds"] for n, r in ROWS.items())


def test_the_defaults_are_the_ones_the_docs_give() -> None:
    p = Params()
    assert (p.derate, p.space_limit, p.power_limit, p.cooling_limit) == (0.8, 0.90, 0.80, 0.85)
    assert (p.window, p.min_history, p.z, p.horizon) == (24, 6, 1.645, 120)
    method = (ROOT / "docs" / "method.md").read_text(encoding="utf-8")
    for row in (
        "| `derate` | 0.8 |",
        "| `space_limit` | 0.90 |",
        "| `power_limit` | 0.80 |",
        "| `cooling_limit` | 0.85 |",
        "| `window` | 24 |",
        "| `min_history` | 6 |",
        "| `z` | 1.645 |",
        "| `horizon` | 120 |",
    ):
        assert row in method, row
    from dccapacity.params import CATALOG

    for name, (h, plate, avg) in CATALOG.items():
        assert f"| {name} | {h} U | {plate:,.0f} W | {avg:,.0f} W | {plate * p.derate / 1000:.2f} kW |" in method, name
