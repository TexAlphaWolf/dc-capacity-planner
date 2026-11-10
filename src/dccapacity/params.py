"""Planning policy: how much of each resource may be used, and how the forecast is made."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from math import isfinite
from typing import Any

RESOURCES = ("space", "power", "cooling")

# name -> (height in U, nameplate watts, typical measured watts): the standard devices a "how many more" question is asked in
CATALOG: dict[str, tuple[int, float, float]] = {
    "sw-1u": (1, 300.0, 150.0),
    "srv-1u": (1, 350.0, 180.0),
    "srv-2u": (2, 750.0, 380.0),
    "stor-2u": (2, 600.0, 320.0),
    "gpu-4u": (4, 2000.0, 1100.0),
}


class ParamError(ValueError):
    pass


@dataclass(frozen=True)
class Params:
    derate: float = 0.8  # power is allocated as nameplate times this
    space_limit: float = 0.90  # share of the rack units that may be used
    power_limit: float = 0.80  # share of the usable UPS capacity that may be allocated
    cooling_limit: float = 0.85  # share of the usable cooling capacity that the heat may reach
    window: int = 24  # months of history the forecast is fitted to
    min_history: int = 6  # fewest months a forecast is made from
    z: float = 1.645  # width of the interval around the slope (1.645 is a 90% interval)
    horizon: int = 120  # months ahead beyond which a crossing is not reported

    def __post_init__(self) -> None:
        for f in fields(self):
            v = getattr(self, f.name)
            if f.type == "int":
                if not isinstance(v, int) or isinstance(v, bool):
                    raise ParamError(f"{f.name} must be a whole number, got {v!r}")
            elif not isinstance(v, int | float) or isinstance(v, bool) or not isfinite(v):
                raise ParamError(f"{f.name} must be a finite number, got {v!r}")
        for name in ("derate", "space_limit", "power_limit", "cooling_limit"):
            if not 0.0 < getattr(self, name) <= 1.0:
                raise ParamError(f"{name} must be above 0 and at most 1, got {getattr(self, name)!r}")
        if self.min_history < 3:
            raise ParamError("min_history must be at least 3 (a line and its uncertainty need three points)")
        if self.window < self.min_history:
            raise ParamError("window must be at least min_history")
        if self.z <= 0:
            raise ParamError("z must be positive")
        if self.horizon < 1:
            raise ParamError("horizon must be at least 1")

    def limit(self, resource: str) -> float:
        return {"space": self.space_limit, "power": self.power_limit, "cooling": self.cooling_limit}[resource]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Params:
        return cls(**d)
