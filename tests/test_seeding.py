"""One seed makes Python, NumPy and the returned Generator repeatable."""

from __future__ import annotations

import random

import numpy as np

from nuikit.seeding import seed_everything


def draws(seed: int) -> tuple[float, float, float]:
    rng = seed_everything(seed)
    return random.random(), np.random.random(), rng.random()  # noqa: NPY002


def test_same_seed_repeats_every_source():
    assert draws(7) == draws(7)
    assert draws(7) != draws(8)
