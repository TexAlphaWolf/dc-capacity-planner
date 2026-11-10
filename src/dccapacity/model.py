"""The facility (racks, power, cooling) and the inventory of devices installed in it, with strict reading and validation."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

NEVER = 10**9  # "removed" for a device that is still installed
COLUMNS = ("name", "rack", "u", "height", "nameplate_w", "avg_w", "installed", "removed")


class ModelError(ValueError):
    pass


def month_index(label: str, start: str) -> int:
    """Months from the start month to a 'YYYY-MM' label."""
    try:
        y, m = (int(x) for x in label.strip().split("-"))
        sy, sm = (int(x) for x in start.split("-"))
    except ValueError as exc:
        raise ModelError(f"'{label}' is not a month written YYYY-MM") from exc
    if not 1 <= m <= 12:
        raise ModelError(f"'{label}' is not a month written YYYY-MM")
    return (y - sy) * 12 + (m - sm)


def month_label(index: int, start: str) -> str:
    sy, sm = (int(x) for x in start.split("-"))
    total = sy * 12 + (sm - 1) + index
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


@dataclass(frozen=True)
class Rack:
    name: str
    units: int
    power_kw: float


@dataclass(frozen=True)
class Plant:
    """Power or cooling equipment in identical units, some of them spare: the usable capacity is what is left without them."""

    unit_kw: float
    units: int
    redundant: int

    @property
    def usable_kw(self) -> float:
        return (self.units - self.redundant) * self.unit_kw


@dataclass(frozen=True)
class Facility:
    name: str
    start: str  # the month with index 0, 'YYYY-MM'
    racks: tuple[Rack, ...]
    power: Plant
    cooling: Plant

    def __post_init__(self) -> None:
        month_index(self.start, "2000-01")
        if not self.racks:
            raise ModelError("a facility needs at least one rack")
        if len({r.name for r in self.racks}) != len(self.racks):
            raise ModelError("rack names must be unique")
        for r in self.racks:
            if r.units < 1 or not r.power_kw > 0:
                raise ModelError(f"rack {r.name}: units and power_kw must be positive")
        for what, pl in (("power", self.power), ("cooling", self.cooling)):
            if not pl.unit_kw > 0 or pl.units < 1 or not 0 <= pl.redundant < pl.units:
                raise ModelError(f"{what}: unit_kw must be positive and redundant must be below units")

    @property
    def total_units(self) -> int:
        return sum(r.units for r in self.racks)

    def rack_index(self) -> dict[str, int]:
        return {r.name: i for i, r in enumerate(self.racks)}

    def label(self, month: int) -> str:
        return month_label(month, self.start)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start,
            "racks": [{"name": r.name, "units": r.units, "power_kw": r.power_kw} for r in self.racks],
            "power": {"unit_kw": self.power.unit_kw, "units": self.power.units, "redundant": self.power.redundant},
            "cooling": {
                "unit_kw": self.cooling.unit_kw,
                "units": self.cooling.units,
                "redundant": self.cooling.redundant,
            },
        }

    @classmethod
    def from_dict(cls, d: Any) -> Facility:
        try:
            racks = tuple(Rack(str(r["name"]), int(r["units"]), float(r["power_kw"])) for r in d["racks"])
            plants = [
                Plant(float(d[k]["unit_kw"]), int(d[k]["units"]), int(d[k]["redundant"])) for k in ("power", "cooling")
            ]
            return cls(str(d["name"]), str(d["start"]), racks, plants[0], plants[1])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            if isinstance(exc, ModelError):
                raise
            raise ModelError(f"the facility file is not valid: {exc!r}") from exc


@dataclass
class Inventory:
    """Devices as parallel lists; `rack` is an index into the facility's racks, `u` the lowest unit the device occupies (1-based)."""

    name: list[str] = field(default_factory=list)
    rack: list[int] = field(default_factory=list)
    u: list[int] = field(default_factory=list)
    height: list[int] = field(default_factory=list)
    nameplate_w: list[float] = field(default_factory=list)
    avg_w: list[float] = field(default_factory=list)
    installed: list[int] = field(default_factory=list)
    removed: list[int] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.name)

    def add(
        self,
        name: str,
        rack: int,
        u: int,
        height: int,
        nameplate_w: float,
        avg_w: float,
        installed: int,
        removed: int = NEVER,
    ) -> None:
        self.name.append(name)
        self.rack.append(rack)
        self.u.append(u)
        self.height.append(height)
        self.nameplate_w.append(nameplate_w)
        self.avg_w.append(avg_w)
        self.installed.append(installed)
        self.removed.append(removed)

    def last_month(self) -> int:
        """The latest month in which anything was installed or removed."""
        months = list(self.installed) + [r for r in self.removed if r != NEVER]
        return max(months) if months else 0

    def at(self, asof: int) -> Inventory:
        """What was known at the end of month `asof`: later installs are not there yet, later removals have not happened."""
        out = Inventory()
        for i in range(len(self)):
            if self.installed[i] <= asof:
                rem = self.removed[i] if self.removed[i] <= asof else NEVER
                out.add(
                    self.name[i],
                    self.rack[i],
                    self.u[i],
                    self.height[i],
                    self.nameplate_w[i],
                    self.avg_w[i],
                    self.installed[i],
                    rem,
                )
        return out

    def arrays(self) -> dict[str, np.ndarray[Any, Any]]:
        return {
            "rack": np.asarray(self.rack, dtype=np.int64),
            "u": np.asarray(self.u, dtype=np.int64),
            "height": np.asarray(self.height, dtype=np.int64),
            "nameplate": np.asarray(self.nameplate_w, dtype=np.float64),
            "avg": np.asarray(self.avg_w, dtype=np.float64),
            "installed": np.asarray(self.installed, dtype=np.int64),
            "removed": np.asarray(self.removed, dtype=np.int64),
        }


def find_overlap(inv: Inventory) -> tuple[int, int] | None:
    """Two devices that occupy the same rack unit in overlapping months: their indices, or None. Sorted by month in each unit
    slot, any overlap shows up between two neighbours, so one pass over the sorted slots finds it."""
    n = len(inv)
    if n == 0:
        return None
    a = inv.arrays()
    h = a["height"]
    dev = np.repeat(np.arange(n), h)
    slot = a["u"][dev] + (np.arange(dev.size) - np.repeat(np.cumsum(h) - h, h))
    rack = a["rack"][dev]
    inst = a["installed"][dev]
    rem = a["removed"][dev]
    order = np.lexsort((inst, slot, rack))
    rack, slot, inst, rem, dev = rack[order], slot[order], inst[order], rem[order], dev[order]
    bad = (rack[1:] == rack[:-1]) & (slot[1:] == slot[:-1]) & (inst[1:] < rem[:-1])
    if not bad.any():
        return None
    k = int(np.argmax(bad))
    return int(dev[k]), int(dev[k + 1])


def validate(inv: Inventory, fac: Facility) -> None:
    seen: set[str] = set()
    for i in range(len(inv)):
        where = f"device '{inv.name[i]}'"
        if inv.name[i] in seen:
            raise ModelError(f"{where}: the name is used twice")
        seen.add(inv.name[i])
        if not 0 <= inv.rack[i] < len(fac.racks):
            raise ModelError(f"{where}: no such rack")
        rk = fac.racks[inv.rack[i]]
        if inv.height[i] < 1 or inv.u[i] < 1 or inv.u[i] + inv.height[i] - 1 > rk.units:
            raise ModelError(
                f"{where}: units {inv.u[i]}..{inv.u[i] + inv.height[i] - 1} do not fit in rack {rk.name} ({rk.units} U)"
            )
        if not (inv.nameplate_w[i] > 0 and inv.avg_w[i] > 0) or inv.avg_w[i] > inv.nameplate_w[i]:
            raise ModelError(f"{where}: needs 0 < avg_w <= nameplate_w")
        if inv.installed[i] < 0:
            raise ModelError(f"{where}: installed before the facility start")
        if inv.removed[i] <= inv.installed[i]:
            raise ModelError(f"{where}: removed in or before the month it was installed")
    pair = find_overlap(inv)
    if pair is not None:
        i, j = pair
        raise ModelError(
            f"devices '{inv.name[i]}' and '{inv.name[j]}' occupy the same unit of rack {fac.racks[inv.rack[i]].name} at the same time"
        )


def read_facility(path: str | Path) -> Facility:
    try:
        return Facility.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelError(f"cannot read the facility file {path}: {exc}") from exc


def write_facility(fac: Facility, path: str | Path) -> None:
    Path(path).write_text(json.dumps(fac.to_dict(), indent=1) + "\n", encoding="utf-8")


def parse_inventory(text: str, fac: Facility, source: str = "inventory") -> Inventory:
    rows = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(rows)]
    except StopIteration:
        raise ModelError(f"{source}: the file is empty") from None
    if tuple(header) != COLUMNS:
        raise ModelError(f"{source}: the header must be {','.join(COLUMNS)}, got {','.join(header)}")
    racks = fac.rack_index()
    inv = Inventory()
    for line, row in enumerate(rows, start=2):
        if not row or all(not c.strip() for c in row):
            continue
        if len(row) != len(COLUMNS):
            raise ModelError(f"{source}, line {line}: {len(row)} columns instead of {len(COLUMNS)}")
        name, rack, u, height, npw, avg, inst, rem = (c.strip() for c in row)
        try:
            if rack not in racks:
                raise ModelError(f"unknown rack '{rack}'")
            inv.add(
                name,
                racks[rack],
                int(u),
                int(height),
                float(npw),
                float(avg),
                month_index(inst, fac.start),
                month_index(rem, fac.start) if rem else NEVER,
            )
        except ValueError as exc:  # ModelError is a ValueError too
            raise ModelError(f"{source}, line {line}: {exc}") from exc
    validate(inv, fac)
    return inv


def read_inventory(path: str | Path, fac: Facility) -> Inventory:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelError(f"cannot read {path}: {exc}") from exc
    return parse_inventory(text, fac, str(path))


def to_csv(inv: Inventory, fac: Facility) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS)
    for i in range(len(inv)):
        w.writerow(
            [
                inv.name[i],
                fac.racks[inv.rack[i]].name,
                inv.u[i],
                inv.height[i],
                repr(inv.nameplate_w[i]),
                repr(inv.avg_w[i]),
                fac.label(inv.installed[i]),
                "" if inv.removed[i] == NEVER else fac.label(inv.removed[i]),
            ]
        )
    return out.getvalue()


def write_inventory(inv: Inventory, fac: Facility, path: str | Path) -> None:
    Path(path).write_text(to_csv(inv, fac), encoding="utf-8", newline="")
