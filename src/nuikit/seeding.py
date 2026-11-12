"""Seed every random source once, at the entry point."""

from __future__ import annotations

import importlib
import importlib.util
import os
import random

import numpy as np


def seed_everything(seed: int, *, deterministic: bool = False) -> np.random.Generator:
    """Seed Python, NumPy and torch (if installed); return a Generator to pass around.

    Code should draw from the returned Generator, not from global state.
    `deterministic` also forces deterministic torch kernels, which are slower.
    A negative `seed` is a ValueError. Python, torch and the Generator get `seed`
    itself; NumPy's legacy global RNG takes 32 bits and gets `seed % 2**32`.
    """
    if seed < 0:
        raise ValueError(f"seed is {seed}; pass 0 or a positive integer")
    random.seed(seed)
    # Third-party code still draws from NumPy's legacy global RNG.
    np.random.seed(seed % 2**32)  # noqa: NPY002
    if importlib.util.find_spec("torch") is not None:
        torch = importlib.import_module("torch")
        torch.manual_seed(seed)  # Seeds every device, CUDA included.
        if deterministic:
            # cuBLAS refuses deterministic GEMMs without a fixed workspace, and reads
            # its size from the environment.
            os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
            torch.use_deterministic_algorithms(mode=True)
            torch.backends.cudnn.benchmark = False
    return np.random.default_rng(seed)
