"""The plugin's skills name themselves, and their templates build what they promise."""

from __future__ import annotations

import ast
import importlib
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from omegaconf import OmegaConf

from nuikit import registry

PLACEHOLDER = re.compile(r"<[^<>\n]+>")
NAME = re.compile(r"<\w+>")
NAMES = {
    "<pkg>": "skillcheck",
    "<family>": "samplers",
    "<Family>": "Sampler",
    "<group>": "sampler",
    "<kind>": "constant",
    "<Kind>": "Constant",
    "<method>": "draw",
    "<Result>": "float",
    "<setting>": "value",
    "<type>": "float",
    "<default>": "1.0",
    "<body reading self.config>": "return self.config.value",
    "<behaviour_as_a_sentence>": "constant_sampler_always_draws_its_value",
    "<value>": "2.5",
    "<expected>": "2.5",
    "<cli>": "skillcheck",
    "<command>": "sample",
    "<Command>": "Sample",
}
FAMILY = {
    "add-family/templates/base.py.tmpl": "<pkg>/<family>/base.py",
    "add-family/templates/family__init__.py.tmpl": "<pkg>/<family>/__init__.py",
    "add-family/templates/items__init__.py.tmpl": "<pkg>/<family>/items/__init__.py",
    "add-family-item/templates/item.py.tmpl": "<pkg>/<family>/items/<kind>.py",
}
SKILLS = ["add-config-field", "add-family", "add-family-item", "entry-point"]


def render(text: str) -> str:
    """Fill the template's names, then turn each prose placeholder into one word."""
    for placeholder, name in NAMES.items():
        text = text.replace(placeholder, name)
    return PLACEHOLDER.sub("placeholder", text)


@pytest.fixture(scope="module")
def skills(pytestconfig: pytest.Config) -> Path:
    return pytestconfig.rootpath / "plugin" / "skills"


@pytest.fixture(scope="module")
def family(skills: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Render the family templates once, as the importable package `skillcheck`."""
    root = tmp_path_factory.mktemp("family")
    for template, target in FAMILY.items():
        path = root / render(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render((skills / template).read_text(encoding="utf-8")))
    sys.path.insert(0, str(root))
    yield root
    sys.path.remove(str(root))


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_names_itself_says_when_to_use_it_and_ships_its_templates(skills, skill):
    text = (skills / skill / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---\n", maxsplit=2)
    meta = OmegaConf.create(frontmatter)

    assert (meta.name, meta.description.startswith("Use when")) == (skill, True)
    # Claude Code shows `<` and `>` of a description as `&lt;` and `&gt;`.
    assert not set("<>") & set(meta.description)
    shipped = {p.name for p in (skills / skill).glob("templates/*.tmpl")}
    assert set(re.findall(r"templates/([\w.]+\.tmpl)", body)) == shipped


@pytest.mark.parametrize("skill", SKILLS)
def test_placeholder_table_explains_every_name_of_the_source_templates(skills, skill):
    body = (skills / skill / "SKILL.md").read_text(encoding="utf-8")
    table = [line for line in body.splitlines() if line.startswith("| `<")]
    sources = [
        path.read_text(encoding="utf-8")
        for path in (skills / skill).glob("templates/*.tmpl")
        if not path.name.startswith("test_")
    ]

    assert set(NAME.findall("".join(sources))) <= set(NAME.findall("".join(table)))


def test_family_templates_build_a_family_that_registers_and_generates_configs(family):
    [file] = registry.config_files("skillcheck")
    base = importlib.import_module("skillcheck.samplers.base")

    sampler = base.SamplerFactory.from_config({"kind": "constant", "value": 2.0})

    assert (file.path, file.kind, sampler.draw()) == (
        "sampler/constant.yaml",
        "constant",
        2,
    )


def test_item_test_template_passes_against_the_rendered_family(skills, family):
    template = skills / "add-family-item" / "templates" / "test_item.py.tmpl"
    rendered = family / "skillcheck_test_constant.py"
    rendered.write_text(render(template.read_text(encoding="utf-8")))

    module = importlib.import_module("skillcheck_test_constant")

    module.test_constant_sampler_always_draws_its_value()


@pytest.mark.parametrize(
    ("template", "functions"),
    [
        ("command.py.tmpl", ["main"]),
        (
            "test_command.py.tmpl",
            ["test_sample_records_its_config_in_the_run_directory"],
        ),
    ],
)
def test_entry_point_template_is_python_that_ruff_takes_once_filled(
    skills, template, functions
):
    path = skills / "entry-point" / "templates" / template

    tree = ast.parse(render(path.read_text(encoding="utf-8")))

    # A project's ruff asks for the docstring (D100) and, below 3.14, the import (I002).
    future = tree.body[1]
    assert (
        bool(ast.get_docstring(tree)),
        isinstance(future, ast.ImportFrom) and future.module,
        [n.name for n in tree.body if isinstance(n, ast.FunctionDef)],
    ) == (True, "__future__", functions)
