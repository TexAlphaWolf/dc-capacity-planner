from __future__ import annotations

import json
from pathlib import Path

import pytest

from dccapacity import cli


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("dc")
    assert cli.main(["generate", str(d), "--months", "36", "--future", "24", "--seed", "3"]) == 0
    return d


def test_generate_validate_analyze_with_truth(files: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out, _ = run(capsys, "validate", str(files / "facility.json"), str(files / "inventory.csv"))
    assert code == 0 and out.startswith("ok: 24 racks (1,008 U) from 2020-01; ")
    out_dir = tmp_path / "out"
    code, out, _ = run(
        capsys,
        "analyze",
        str(files / "facility.json"),
        str(files / "inventory.csv"),
        "--truth",
        str(files / "truth.json"),
        "--out",
        str(out_dir),
    )
    assert code == 0
    assert out.splitlines()[0].startswith(f"{files / 'inventory.csv'}: 24 racks, 1,008 U; ")
    assert "what happened next (months to the limit):" in out
    rep = json.loads((out_dir / "report.json").read_text())
    assert rep["kind"] == "report" and rep["analysis"]["asof"]["month"] == 35
    assert (out_dir / "summary.png").read_bytes()[1:4] == b"PNG"
    # the Markdown is rebuilt exactly from the JSON
    again = tmp_path / "again.md"
    assert cli.main(["render", str(out_dir / "report.json"), "-o", str(again)]) == 0
    assert again.read_text() == (out_dir / "report.md").read_text()


def test_generate_refuses_to_overwrite(files: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "generate", str(files))
    assert code == 2 and "already exists" in err


def test_asof_and_policy_flags(files: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(
        capsys,
        "analyze",
        str(files / "facility.json"),
        str(files / "inventory.csv"),
        "--asof",
        "2021-06",
        "--space-limit",
        "0.5",
    )
    assert code == 0 and "as of 2021-06" in out and "limit 50%" in out
    code, _, err = run(
        capsys, "analyze", str(files / "facility.json"), str(files / "inventory.csv"), "--asof", "2019-01"
    )
    assert code == 2 and "before the facility start" in err


def test_the_demo_runs_without_files(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "analyze")
    assert code == 0 and out.startswith("demo data center (synthetic, 60 months, seed 1): 24 racks, 1,008 U; ")
    assert "first to run out: " in out and "how many more fit: " in out and "what happened next" in out


def test_plan(files: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ("plan", str(files / "facility.json"), str(files / "inventory.csv"))
    code, out, _ = run(capsys, *args, "--add", "srv-1u=5")
    assert code == 0 and "add 5 x srv-1u: 5 placed" in out and "after that: space " in out
    code, out, _ = run(capsys, *args, "--add", "gpu-4u=100000", "--monthly", "srv-1u=10")
    assert code == 0 and "does not fit: " in out and "every month: 0 full months fit" in out
    code, out, _ = run(
        capsys,
        *args,
        "--monthly",
        "sw-1u=1",
        "--horizon",
        "6",
        "--space-limit",
        "1.0",
        "--power-limit",
        "1.0",
        "--cooling-limit",
        "1.0",
    )
    assert (code == 0 and "full months fit" in out) or "whole horizon of 6 months" in out


def test_plan_errors(files: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ("plan", str(files / "facility.json"), str(files / "inventory.csv"))
    for bad, message in (
        ([], "nothing to plan"),
        (["--add", "toaster=3"], "unknown model"),
        (["--add", "srv-1u"], "MODEL=COUNT"),
        (["--add", "srv-1u=0"], "at least 1"),
    ):
        code, _, err = run(capsys, *args, *bad)
        assert code == 2 and message in err


def test_verify_and_bench(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "verify", "--draws", "3")
    assert code == 0 and "4 of 4 comparisons agree with the literal implementation" in out
    out_dir = tmp_path / "b"
    code, out, _ = run(
        capsys,
        "bench",
        "--sizes",
        "300,600",
        "--repeat",
        "1",
        "--draws",
        "2",
        "--ref-devices",
        "200",
        "--seeds",
        "1",
        "--out",
        str(out_dir),
    )
    assert code == 0 and "written: " in out
    data = json.loads((out_dir / "bench.json").read_text())
    assert data["kind"] == "bench" and data["verification"]["ok"] and len(data["analysis"]) == 2
    again = tmp_path / "again.md"
    assert cli.main(["render", str(out_dir / "bench.json"), "-o", str(again), "--figure", str(tmp_path / "f.png")]) == 0
    assert again.read_text() == (out_dir / "bench.md").read_text()


def test_bad_inputs_exit_2(files: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fac, inv = str(files / "facility.json"), str(files / "inventory.csv")
    cases = [
        (["validate", str(tmp_path / "nope.json"), inv], "cannot read"),
        (["analyze", fac], "both the facility file and the inventory file"),
        (["analyze", "--truth", str(files / "truth.json")], "needs the facility and inventory"),
        (["analyze", fac, inv, "--truth", str(tmp_path / "no.json")], "cannot read the truth file"),
        (["analyze", fac, inv, "--derate", "0"], "derate"),
        (["bench", "--sizes", "5"], "100 or more"),
        (["render", str(tmp_path / "no.json")], "cannot read"),
    ]
    (tmp_path / "other.json").write_text("{}", encoding="utf-8")
    cases.append((["render", str(tmp_path / "other.json")], "neither a report.json nor a bench.json"))
    for args, message in cases:
        code, _, err = run(capsys, *args)
        assert code == 2 and message in err, (args, err)


def test_render_prints_to_stdout_without_output(
    files: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out_dir = tmp_path / "o"
    assert cli.main(["analyze", "--out", str(out_dir)]) == 0
    capsys.readouterr()
    code, out, _ = run(capsys, "render", str(out_dir / "report.json"))
    assert code == 0 and out == (out_dir / "report.md").read_text()


def test_parser_builds_and_help_renders(capsys):
    # Python 3.14 validates help strings when the argument is added; a bare % breaks it
    from dccapacity.cli import build_parser

    parser = build_parser()
    for command in ("analyze", "plan"):
        with pytest.raises(SystemExit) as stop:
            parser.parse_args([command, "--help"])
        assert stop.value.code == 0
    assert "90%" in capsys.readouterr().out
