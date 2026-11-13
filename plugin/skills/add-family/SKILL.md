---
name: add-family
description: Use when a project built on nuikit needs a new family, a concept with several interchangeable implementations chosen by a config `kind` (endpoints, samplers, metrics, collectors). Creates base.py with the abstract base, config and factory, items/, the import layer, the first kind, the generated configs and the tests.
paths:
  - "src/**/*.py"
  - "configs/**/*.yaml"
  - "pyproject.toml"
---

# Add a family

A family is `src/<pkg>/<family>/`: `base.py` with the abstract base, its config schema and its factory, plus `items/`
with one module per kind (FAM-1). Rules: [docs/guide.md](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md)
FAM-1..FAM-5; conventions TYP-5, TYP-6, ARC-1, ARC-4.

Pick the names, then fill every `<...>` in the templates next to this file. Drop `from __future__ import annotations`
when the project's `requires-python` is 3.14 or later (TYP-3).

| placeholder | is | example |
|---|---|---|
| `<pkg>` | the project's import package | `toy` |
| `<family>` | the subpackage, a plural noun | `samplers` |
| `<Family>` | the base class, singular | `Sampler` |
| `<group>` | the config group, singular snake_case | `sampler` |
| `<method>`, `<Result>` | what every kind does, and returns | `draw`, `np.ndarray` |

## Steps

1. `templates/base.py.tmpl` -> `src/<pkg>/<family>/base.py`. The base is an attrs ABC whose type argument is its
   config. Declare the interface as abstract methods. `from_config` passes only the config, so collaborators and
   randomness are method arguments: `rng: np.random.Generator`, never global state (RUN-2). A feature only some kinds
   have is a `ClassVar[bool]` on the base that callers test, never `kind ==` (ARC-4). Settings every kind shares go on
   `<Family>Config`.
2. `templates/items__init__.py.tmpl` -> `src/<pkg>/<family>/items/__init__.py`, and
   `templates/family__init__.py.tmpl` -> `src/<pkg>/<family>/__init__.py`: importing the family registers its kinds.
3. Place the family in the layers contract in `pyproject.toml`; the contract is exhaustive, so `make check` fails
   until you do. A domain that imports no other domain joins the domain layer as an independent sibling
   (`"signals | stats | <family>"`); one that imports another sits in a layer above it.
4. Add the first kind with the `add-family-item` skill.
5. Select it from the entry config: a field typed as the base config, resolved by `kind` (CFG-8), and left out of the
   entry mirror because the group provides it.

   ```python
   from collections.abc import Mapping
   from typing import Any

   from pydantic import SerializeAsAny, field_validator

   from nuikit.registry import KindConfig

   from <pkg>.<family>.base import <Family>Config, <Family>Factory


   class MainConfig(Schema):
       ...
       # SerializeAsAny keeps the kind's own fields in the run's config.yaml.
       <group>: SerializeAsAny[<Family>Config]

       @field_validator("<group>", mode="before")
       @classmethod
       def _<group>_by_kind(cls, data: Mapping[str, Any] | KindConfig) -> KindConfig:
           return <Family>Factory.validate(data)


   GENERATED = (ConfigFile("defaults/run.yaml", MainConfig, groups=("<group>",)),)
   ```

   Then add `- <group>: <kind>` to the `defaults:` list of `configs/<command>.yaml`, above `_self_`. The composition
   root builds the item with `<Family>Factory.from_config(cfg.<group>)`. A `kind` that no item registered then fails
   validation with exit code 2: `error: unknown sampler kind 'sobl'; registered: sobol, uniform`. Hydra itself
   refuses a mistyped group option (`sampler=sobl`) before that, and lists the options the group has.
6. `make configs` writes `configs/<group>/<kind>.yaml`. Never edit generated files; presets that name variants of a
   kind are hand-written files in the same group with names that no kind takes (CFG-3).
7. Add the family to the "Extending" table in CONTRIBUTING.md: what to add, where, what selects it (FAM-5).
8. `make check`.

## Families that share a base

Two families whose kinds are variants of one thing, such as rewards and penalties that add up to one score, may
share a package instead of one each (FAM-1):

```text
src/<pkg>/<package>/
  __init__.py      imports <family_a> and <family_b>, so importing the package registers every kind
  base.py          the shared base, then each family's base, config and factory
  <logic>.py       what works over both, such as a scoring.py that sums the kinds
  <family_a>/      __init__.py calls import_submodules(__name__); one module per kind
  <family_b>/      the same
```

Each factory keeps its own `config_group`, so each family gets its own `configs/<group>/` and is selected on its own.
A family that shares nothing with another keeps the layout above.

## Kinds that run together

A family whose kinds all run in one run, such as metrics, sets `multiple = True` on its factory (FAM-4). Each
generated file then starts with `# @package <group>.<kind>`, and so does a preset that composes it. The entry config
selects a list (`- <group>: [a, b]`, overridden as `'<group>=[a]'`, quoted because zsh expands square brackets), and
the schema field maps each kind to its config. Each value has its own validator and the mapping has none, so that an
error names its kind (`metric.f1.threshold`) and the errors of every kind are listed:

```python
from typing import Annotated

from pydantic import BeforeValidator, SerializeAsAny

from <pkg>.<family>.base import <Family>Config, <Family>Factory


class MainConfig(Schema):
    ...
    <group>: dict[
        str,
        Annotated[
            SerializeAsAny[<Family>Config],
            BeforeValidator(<Family>Factory.validate),
        ],
    ]
```
