"""One seed makes Python, NumPy and the returned Generator repeatable."""

from __future__ import annotations

import random

import numpy as np
import pytest

from nuikit.seeding import seed_everything


def draws(seed: int) -> tuple[float, float, float]:
    rng = seed_everything(seed)
    return random.random(), np.random.random(), rng.random()  # noqa: NPY002


def test_same_seed_repeats_every_source():
    assert draws(7) == draws(7)
    assert draws(7) != draws(8)


def test_seed_beyond_32_bits_repeats_and_numpys_legacy_rng_gets_its_low_32_bits():
    timestamp = 20261112050000

    assert draws(timestamp) == draws(timestamp)
    python, legacy_numpy, generator = draws(2**32 + 7)
    assert (python, generator) != draws(7)[::2]
    assert legacy_numpy == draws(7)[1]


def test_negative_seed_is_refused_before_anything_is_seeded():
    random.seed(7)
    untouched = random.getstate()

    with pytest.raises(ValueError, match="seed is -1; pass 0 or a positive integer"):
        seed_everything(-1)

    assert random.getstate() == untouched
