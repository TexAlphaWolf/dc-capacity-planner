from pathlib import Path

import pytest

from dccapacity import model
from dccapacity.model import NEVER, Facility, Inventory, ModelError

from .conftest import inv_of, small


def test_month_labels_round_trip() -> None:
    assert model.month_index("2025-03", "2024-01") == 14
    assert model.month_label(14, "2024-01") == "2025-03"
    assert model.month_label(0, "2024-12") == "2024-12"
    assert model.month_label(1, "2024-12") == "2025-01"
    for bad in ("2024", "2024-13", "x-y", "2024-00"):
        with pytest.raises(ModelError):
            model.month_index(bad, "2024-01")


def test_plant_usable_capacity_leaves_out_the_spare_units() -> None:
    f = small()
    assert f.power.usable_kw == 20.0 and f.cooling.usable_kw == 10.0 and f.total_units == 20


def test_facility_json_round_trip_and_errors(tmp_path: Path) -> None:
    f = small()
    model.write_facility(f, tmp_path / "f.json")
    assert model.read_facility(tmp_path / "f.json") == f
    (tmp_path / "bad.json").write_text('{"name": "x"}', encoding="utf-8")
    with pytest.raises(ModelError, match="not valid"):
        model.read_facility(tmp_path / "bad.json")
    (tmp_path / "bad2.json").write_text("{", encoding="utf-8")
    with pytest.raises(ModelError, match="cannot read"):
        model.read_facility(tmp_path / "bad2.json")
    with pytest.raises(ModelError, match="cannot read"):
        model.read_facility(tmp_path / "nope.json")
    d = f.to_dict()
    d["racks"] = []
    with pytest.raises(ModelError, match="at least one rack"):
        Facility.from_dict(d)
    d = f.to_dict()
    d["racks"][1]["name"] = "A"
    with pytest.raises(ModelError, match="unique"):
        Facility.from_dict(d)
    d = f.to_dict()
    d["power"]["redundant"] = 3
    with pytest.raises(ModelError, match="redundant"):
        Facility.from_dict(d)
    d = f.to_dict()
    d["racks"][0]["units"] = 0
    with pytest.raises(ModelError, match="positive"):
        Facility.from_dict(d)


def test_inventory_csv_round_trip(tmp_path: Path) -> None:
    f = small()
    inv = inv_of((0, 1, 2, 500.0, 250.0, 0), (1, 3, 1, 300.5, 100.25, 2, 7))
    model.write_inventory(inv, f, tmp_path / "i.csv")
    back = model.read_inventory(tmp_path / "i.csv", f)
    assert back == inv
    assert (tmp_path / "i.csv").read_text().splitlines()[2].endswith("2024-03,2024-08")


def test_at_hides_the_future() -> None:
    inv = inv_of((0, 1, 1, 300.0, 200.0, 0, 5), (0, 2, 1, 300.0, 200.0, 4))
    now = inv.at(3)
    assert len(now) == 1 and now.removed == [
        NEVER
    ]  # removal in month 5 not happened yet; second device not installed yet
    assert len(inv.at(4)) == 2
    assert inv.last_month() == 5 and Inventory().last_month() == 0


HEADER = "name,rack,u,height,nameplate_w,avg_w,installed,removed\n"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("a,Z,1,1,300,200,2024-01,", "unknown rack"),
        ("a,A,0,1,300,200,2024-01,", "do not fit"),
        ("a,A,10,2,300,200,2024-01,", "do not fit"),
        ("a,A,1,1,300,400,2024-01,", "avg_w <= nameplate_w"),
        ("a,A,1,1,0,0,2024-01,", "avg_w <= nameplate_w"),
        ("a,A,1,1,300,200,2023-12,", "before the facility start"),
        ("a,A,1,1,300,200,2024-03,2024-03", "removed in or before"),
        ("a,A,1,1,300,200,2024-01", "columns instead of 8"),
        ("a,A,x,1,300,200,2024-01,", "line 2"),
        ("a,A,1,1,300,200,soon,", "YYYY-MM"),
    ],
)
def test_bad_rows_are_refused_with_the_line(row: str, message: str) -> None:
    with pytest.raises(ModelError, match=message):
        model.parse_inventory(HEADER + row + "\n", small())


def test_overlaps_and_duplicates_are_refused() -> None:
    f = small()
    with pytest.raises(ModelError, match="same unit"):
        model.parse_inventory(HEADER + "a,A,1,3,300,200,2024-01,\nb,A,3,1,300,200,2024-02,\n", f)
    with pytest.raises(ModelError, match="same unit"):  # nested in time: a long stay and a short one inside it
        model.parse_inventory(HEADER + "a,A,1,1,300,200,2024-01,2024-12\nb,A,1,1,300,200,2024-03,2024-04\n", f)
    with pytest.raises(ModelError, match="used twice"):
        model.parse_inventory(HEADER + "a,A,1,1,300,200,2024-01,\na,A,2,1,300,200,2024-01,\n", f)
    # one after the other in the same unit is fine, and so are the same units in two racks
    inv = model.parse_inventory(
        HEADER + "a,A,1,1,300,200,2024-01,2024-03\nb,A,1,1,300,200,2024-03,\nc,B,1,1,300,200,2024-01,\n", f
    )
    assert len(inv) == 3


def test_file_level_errors(tmp_path: Path) -> None:
    f = small()
    with pytest.raises(ModelError, match="empty"):
        model.parse_inventory("", f)
    with pytest.raises(ModelError, match="header"):
        model.parse_inventory("a,b\n", f)
    with pytest.raises(ModelError, match="cannot read"):
        model.read_inventory(tmp_path / "nope.csv", f)
    assert len(model.parse_inventory(HEADER + "\n,,,,,,,\n", f)) == 0  # blank lines are skipped
