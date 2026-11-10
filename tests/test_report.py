from __future__ import annotations

from pathlib import Path

import pytest

from dccapacity import analysis, bench, report
from dccapacity.params import Params


@pytest.fixture(scope="module")
def rep(sim) -> dict:  # type: ignore[no-untyped-def]
    return analysis.build_report(sim.inventory.at(59), sim.facility, Params(), sim.truth, "test source")


def test_markdown_has_every_section_and_the_numbers_of_the_report(rep: dict) -> None:  # type: ignore[type-arg]
    md = report.render_report(rep)
    for head in (
        "# Capacity report: Synthetic data center",
        "## 1. Where things stand",
        "## 2. When each resource",
        "## 3. Racks",
        "## 4. Stranded",
        "## 5. How many more fit",
        "## 6. Against what happened next",
    ):
        assert head in md
    now = rep["analysis"]["now"]["space"]
    assert f"| Space | rack units in use | {now['used']:,.1f} U |" in md
    assert md.count("\n") > 40 and "n/a" not in md.split("## 2.")[0]


def test_markdown_without_a_truth_has_no_section_6(rep: dict) -> None:  # type: ignore[type-arg]
    r = {**rep, "accuracy": None}
    assert "## 6." not in report.render_report(r)


def test_notes_for_every_status_and_a_long_rack_list() -> None:
    from dccapacity.model import Facility, Inventory, Plant, Rack

    from .conftest import small

    fac = Facility(
        "big", "2024-01", tuple(Rack(f"R{i:02d}", 10, 5.0) for i in range(40)), Plant(10.0, 3, 1), Plant(10.0, 3, 1)
    )
    inv = Inventory()
    for r in range(40):
        inv.add(f"d{r}", r, 1, 1, 300.0, 100.0, 0)
    rep = analysis.build_report(inv, fac, Params(), None, "x", asof=3)  # four months: short history
    md = report.render_report(rep)
    assert "too little history" in md and "the 30 fullest of 40" in md and "No resource is forecast" in md
    inv2 = Inventory()
    inv2.add("a", 0, 1, 10, 300.0, 100.0, 0)
    rep = analysis.build_report(inv2, small(), Params(space_limit=0.2), None, "x", asof=8)
    assert "already at or over the limit" in report.render_report(rep)
    flat = analysis.build_report(inv2, small(), Params(), None, "x", asof=8)
    assert "not growing" in report.render_report(flat)


def test_over_the_horizon(sim) -> None:  # type: ignore[no-untyped-def]
    rep = analysis.build_report(sim.inventory.at(30), sim.facility, Params(horizon=1), None, "x")
    assert "later than the horizon" in report.render_report(rep)


def test_figures_are_written(rep: dict, tmp_path: Path) -> None:  # type: ignore[type-arg]
    report.report_figure(rep, tmp_path / "r.png")
    assert (tmp_path / "r.png").stat().st_size > 20_000
    b = bench.run_bench([300, 600], 1, 1, 2, "test", 200, 1)
    report.bench_figure(b, tmp_path / "b.png")
    assert (tmp_path / "b.png").stat().st_size > 20_000
    md = report.render_bench(b)
    assert "## 4. Agreement" in md and "all match" in md


def test_helpers() -> None:
    assert report.pct(None) == "n/a" and report.pct(0.1234, 2) == "12.34%"
    assert report.num(None) == "n/a" and report.num(1234.5) == "1,234.5"
    assert report.months(None) == "n/a" and report.months(2.6) == "3"
    assert [report._t(x) for x in (5e-5, 0.0123, 2.0)] == ["50 us", "12.3 ms", "2.00 s"]
