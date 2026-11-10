from __future__ import annotations

import math

import numpy as np

from dccapacity import synth, verify
from dccapacity.model import validate

from .conftest import DRAWS, SEED


def test_the_two_implementations_agree_on_generated_and_random_facilities() -> None:
    checks = verify.verify(DRAWS, SEED)
    assert len(checks) == DRAWS + 1
    bad = [(c.name, c.detail) for c in checks if not c.ok]
    assert not bad, bad
    assert max(c.max_rel_error for c in checks) < verify.RTOL
    assert sum(c.numbers for c in checks) > 1000


def test_compare_notices_differences_and_tolerates_rounding() -> None:
    assert verify.compare({"a": [1.0, 2.0]}, {"a": [1.0, 2.0 + 1e-12]})[2] is None
    _n, w, bad = verify.compare({"a": [1.0, 2.0]}, {"a": [1.0, 2.1]})
    assert bad is not None and "/a[1]" in bad and w > 0.04
    assert verify.compare({"a": 1}, {"b": 1})[2] is not None
    assert verify.compare([1], [1, 2])[2] is not None
    assert verify.compare("x", "y")[2] is not None
    assert verify.compare(1, 1.0)[2] is not None  # an int is not a float
    assert verify.compare(math.nan, math.nan) == (1, 0.0, None)
    assert verify.compare(None, None) == (1, 0.0, None)


def test_random_params_are_always_valid_and_random_inventories_too() -> None:
    rng = np.random.default_rng(SEED)
    for _ in range(40):
        verify.random_params(rng)
        fac = synth.random_facility(rng)
        inv = synth.random_inventory(fac, rng, int(rng.integers(3, 60)))
        validate(inv, fac)


def test_the_large_synthetic_inventory_is_valid_and_sized() -> None:
    fac, inv = synth.large_inventory(2000, 60, 1)
    validate(inv, fac)
    assert 1900 < len(inv) < 2100
