"""docs/api.md names the public API, no more and no less."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import nuikit

API = Path(__file__).parent.parent / "docs" / "api.md"
MODULES = sorted(
    path.stem
    for path in Path(nuikit.__file__).parent.glob("*.py")
    if path.stem != "__init__"
)


def public_names(module: str) -> set[str]:
    """Return the module-level names of `module` without a leading underscore."""
    source = (Path(nuikit.__file__).parent / f"{module}.py").read_text("utf-8")
    names: list[str] = []
    for node in ast.parse(source).body:
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                names.append(node.name)
            case ast.Assign():
                names += [t.id for t in node.targets if isinstance(t, ast.Name)]
            case ast.AnnAssign(target=ast.Name(id=name)):
                names.append(name)
            case ast.TypeAlias():
                names.append(node.name.id)
            case _:
                pass
    return {name for name in names if not name.startswith("_")}


def documented_names(module: str) -> set[str]:
    """Return the names the first table column of the module's section holds."""
    sections = API.read_text("utf-8").split("\n## ")
    section = next(s for s in sections if s.startswith(f"nuikit.{module}\n"))
    return set(re.findall(r"^\| `(\w+)` \|", section, flags=re.MULTILINE))


@pytest.mark.parametrize("module", MODULES)
def test_api_page_names_exactly_the_public_names_of_each_module(module: str):
    assert documented_names(module) == public_names(module)
