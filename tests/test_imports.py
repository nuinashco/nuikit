"""Importing nuikit needs none of its optional dependencies."""

from __future__ import annotations

import subprocess
import sys

# `None` in `sys.modules` makes an import fail as if the module were not installed.
WITHOUT_EXTRAS = """
import importlib, pkgutil, sys
sys.modules.update(dict.fromkeys(("wandb", "torch"), None))
import nuikit
for module in pkgutil.iter_modules(nuikit.__path__):
    importlib.import_module(f"nuikit.{module.name}")
"""


def test_every_module_imports_without_wandb_or_torch():
    subprocess.run([sys.executable, "-c", WITHOUT_EXTRAS], check=True)
