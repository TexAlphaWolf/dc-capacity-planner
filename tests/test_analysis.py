"""Hand-computed cases, each run through both implementations."""

from __future__ import annotations

import pytest

from dccapacity import core, pipeline, reference
from dccapacity.model import Facility, Plant, Rack
from dccapacity.params import Params

from .conftest import both, inv_of, small


def test_series_and_present_values_by_hand() -> None:
    # 20 U in total, usable power 20 kW, usable cooling 10 kW; power allocated at 0.8 x nameplate
    inv = inv_of(
        (0, 1, 2, 500.0, 250.0, 0),  # month 0 on: 2 U, 0.4 kW, 0.25 kW
        (0, 3, 2, 500.0, 250.0, 1),
        (1, 1, 4, 1000.0, 600.0, 1, 3),  # months 1 and 2 only: 4 U, 0.8 kW, 0.6 kW
    )
    a = both(inv, small(), asof=4)
    assert a["series"]["space"] == pytest.approx([2 / 20, 8 / 20, 8 / 20, 4 / 20, 4 / 20])
    assert a["series"]["power"] == pytest.approx([0.4 / 20, 1.6 / 20, 1.6 / 20, 0.8 / 20, 0.8 / 20])
    assert a["series"]["cooling"] == pytest.approx([0.25 / 10, 1.1 / 10, 1.1 / 10, 0.5 / 10, 0.5 / 10])
    now = a["now"]["space"]
    assert (now["used"], now["capacity"], now["headroom"]) == pytest.approx((4.0, 20.0, 20 * 0.9 - 4))
    assert a["inventory"] == {"devices": 3, "installed_now": 2}


def test_an_empty_facility_and_a_day_zero_facility() -> None:
    a = both(inv_of(), small(), asof=0)
    assert a["now"]["space"]["used"] == 0 and a["forecast"]["space"]["status"] == "short history"
    assert a["binding"] is None and a["racks"][0]["largest_free_u"] == 10
    assert a["headroom"]["srv-1u"]["count"] > 0


def test_rack_table_and_stranded_capacity() -> None:
    # rack A is full (4 + 4 + 2 units) and has 5 - 4.4 = 0.6 kW of power left; rack B holds one small device
    inv = inv_of(
        (0, 1, 4, 2000.0, 1000.0, 0),
        (0, 5, 4, 2000.0, 1000.0, 0),
        (0, 9, 2, 1500.0, 700.0, 0),
        (1, 1, 1, 300.0, 100.0, 0),
    )
    a = both(inv, small(), asof=0)
    ra, rb = a["racks"]
    assert (ra["used_u"], ra["free_u"], ra["largest_free_u"]) == (10, 0, 0)
    assert ra["alloc_kw"] == pytest.approx(1.6 + 1.6 + 1.2) and ra["power_headroom_kw"] == pytest.approx(5 - 4.4)
    assert rb["used_u"] == 1 and rb["largest_free_u"] == 9 and rb["meas_kw"] == pytest.approx(0.1)
    # no free unit is stranded (rack A has none free) but the 0.6 kW left in the full rack is
    assert a["stranded"]["space_u"] == 0 and a["stranded"]["power_kw"] == pytest.approx(0.6)


def test_stranded_space() -> None:
    inv = inv_of(
        (0, 1, 1, 3125.0, 1000.0, 0), (0, 2, 1, 1000.0, 500.0, 0)
    )  # 2.5 + 0.8 = 3.3 kW of 5; make it tighter with 3 more
    inv.add("big", 0, 3, 1, 2000.0, 900.0, 0, 10**9)  # +1.6 kW: 4.9 kW allocated, 0.1 kW left, 7 free units
    a = both(inv, small(), asof=0)
    assert a["racks"][0]["power_headroom_kw"] == pytest.approx(0.1)
    assert a["stranded"]["space_u"] == 7


def test_largest_free_block() -> None:
    inv = inv_of((0, 1, 2, 300.0, 100.0, 0), (0, 5, 1, 300.0, 100.0, 0), (0, 7, 2, 300.0, 100.0, 0))
    a = both(inv, small(), asof=0)
    assert a["racks"][0]["largest_free_u"] == 2 and a["racks"][0]["used_u"] == 5  # free units: 3-4, 6 and 9-10


HEAVY = (2000.0, 1000.0)  # nameplate, avg: 1.6 kW allocated, 1.0 kW of heat


def fill_of(fac: Facility, h: int, nameplate: float, avg: float, inv=None, p: Params | None = None) -> tuple[int, str]:
    """Count with both state implementations."""
    p = p or Params()
    inv = inv or inv_of()
    a, b = pipeline.make_state(inv, fac, p, 0), reference.make_state(inv, fac, p, 0)
    args = (h, nameplate * p.derate / 1000.0, avg / 1000.0)
    ra, rb = core.fill(a, *args), core.fill(b, *args)
    assert ra == rb
    return ra


def test_first_fit_stops_on_rack_power_before_anything_else() -> None:
    # 1.6 kW each: 3 fit in a 5 kW rack (4.8 kW), so 6 in two racks; the 7th finds room in the racks but no power in them
    assert fill_of(small(), 1, *HEAVY) == (6, "rack_power")


def test_room_power_stops_it_when_the_racks_could_take_more() -> None:
    f = Facility("f", "2024-01", (Rack("A", 42, 50.0), Rack("B", 42, 50.0)), Plant(10.0, 3, 1), Plant(50.0, 3, 1))
    # usable power 20 kW x 0.8 = 16 kW: ten devices of 1.6 kW fit exactly, the eleventh does not (exact equality is allowed)
    assert fill_of(f, 1, *HEAVY) == (10, "power")


def test_cooling_stops_it() -> None:
    f = Facility("f", "2024-01", (Rack("A", 42, 50.0),), Plant(100.0, 3, 1), Plant(5.0, 3, 1))
    # usable cooling 10 kW x 0.85 = 8.5 kW: eight devices of 1 kW
    assert fill_of(f, 1, *HEAVY) == (8, "cooling")


def test_space_policy_and_physical_space() -> None:
    # 20 U x 0.9 = 18 U may be used: 9 devices of 2 U, and the room power is not the limit (9 x 0.4 kW)
    f = Facility("f", "2024-01", (Rack("A", 10, 50.0), Rack("B", 10, 50.0)), Plant(100.0, 3, 1), Plant(100.0, 3, 1))
    assert fill_of(f, 2, 500.0, 250.0) == (9, "space")
    # a 4 U device does not fit where only 3 free units in a row are left, even if the policy would allow it
    inv = inv_of((0, 4, 1, 300.0, 100.0, 0), (1, 4, 1, 300.0, 100.0, 0))  # splits both racks into 3 U and 6 U
    assert fill_of(f, 6, 300.0, 100.0, inv)[0] == 2  # one 6 U block in each rack
    assert fill_of(f, 7, 300.0, 100.0, inv) == (0, "space")


def test_first_fit_takes_the_lowest_rack_then_the_lowest_unit() -> None:
    f = small()
    for st in (pipeline.make_state(inv_of(), f, Params(), 0), reference.make_state(inv_of(), f, Params(), 0)):
        for _ in range(3):
            assert st.place(1, 1.6, 1.0) is None  # three heavy ones fill rack A's power
        assert st.place(1, 0.1, 0.1) is None  # 4.8 + 0.1 = 4.9 of 5 kW: still rack A
        assert st.place(1, 0.3, 0.1) is None  # 4.9 + 0.3 > 5 kW: moves to rack B
    a = pipeline.make_state(inv_of(), f, Params(), 0)
    for dev in (1.6, 1.6, 1.6, 0.1, 0.3):
        a.place(1, dev, 0.1)
    assert a.occ[0, :4].tolist() == [True] * 4 and not a.occ[0, 4] and a.occ[1, 0] and not a.occ[1, 1]
    assert a.rack_alloc.tolist() == pytest.approx([4.9, 0.3])


def test_clone_does_not_share_state() -> None:
    f = small()
    for st in (pipeline.make_state(inv_of(), f, Params(), 0), reference.make_state(inv_of(), f, Params(), 0)):
        c = st.clone()
        assert c.place(2, 0.4, 0.2) is None
        assert st.used_u == 0 and c.used_u == 2


def test_runway_counts_full_months() -> None:
    f = Facility(
        "f", "2024-01", (Rack("A", 42, 50.0),), Plant(100.0, 3, 1), Plant(5.0, 3, 1)
    )  # cooling: 8.5 kW at 1 kW each
    for make in (pipeline.make_state, reference.make_state):
        st = make(inv_of(), f, Params(), 0)
        r = core.runway(
            st, [(1, 1.6, 1.0, 3)], 20
        )  # 3 a month: months 1 and 2 fit (6), month 3 places 2 and the 9th is refused
        assert r == {"months": 2, "placed_in_last_month": 2, "blocked_by": "cooling", "beyond_horizon": False}
        assert core.runway(st, [(1, 0.1, 0.0001, 1)], 5) == {
            "months": 5,
            "placed_in_last_month": 0,
            "blocked_by": None,
            "beyond_horizon": True,
        }
        assert st.used_u == 0  # the runway works on a copy
