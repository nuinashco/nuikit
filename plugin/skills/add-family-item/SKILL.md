---
name: add-family-item
description: Use when adding a kind to an existing nuikit family in a project, a new implementation that a config `kind` selects (a new endpoint, sampler, metric), or when writing a family's first kind. Creates items/<kind>.py with its config, registers it, regenerates configs and adds its test.
paths:
  - "src/**/items/*.py"
  - "src/**/base.py"
  - "configs/**/*.yaml"
---

# Add a kind to a family

A kind is one module, `src/<pkg>/<family>/items/<kind>.py`, holding its config schema and its item class. `items/`
imports every module in it, so the new file is all the registration there is (FAM-1). Rules:
[docs/guide.md](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md) FAM-1..FAM-3, CFG-3, CFG-4; conventions
TYP-4, TYP-5, STY-5.

Read the family's `base.py` first: `<Family>`, `<Family>Config`, `<Family>Factory` and the abstract methods to
implement. Fill every `<...>` in the templates next to this file; drop `from __future__ import annotations` when
`requires-python` is 3.14 or later (TYP-3).

| placeholder | is | example |
|---|---|---|
| `<kind>`, `<Kind>` | the kind, snake_case and CapWords | `sobol`, `Sobol` |
| `<setting>: <type> = <default>` | its settings, one line each | `scramble: bool = True` |

## Steps

1. `templates/item.py.tmpl` -> `src/<pkg>/<family>/items/<kind>.py`. Keep its shape:
   - `@<Family>Factory.register("<kind>")` stays the outermost decorator, above `@define` (FAM-2);
   - the class names carry the family suffix, `<Kind><Family>` and `<Kind><Family>Config` (STY-5);
   - `<Family>[<Kind><Family>Config]` binds `Config` and types `self.config` (FAM-3);
   - the item has no `__init__` and no fields besides `config`; derived private state is a `field(init=False)` set
     in `__attrs_post_init__` (TYP-4).
2. Settings go on `<Kind><Family>Config`, each with a default unless none is sensible (then no default, `???` in YAML,
   CFG-4). Add a `Field(description=...)` only for what the name, type and default leave open, per the
   `add-config-field` skill. Numbers with units take a suffix: `timeout_s`, `size_mb` (STY-6).
3. Implement the abstract methods from `self.config`. Randomness comes in as an `np.random.Generator` argument, and
   no tunable value is a constant in code (RUN-2, CFG-7). If the kind lacks a feature others have, set the base's
   capability `ClassVar[bool]` rather than letting callers test the kind (ARC-4).
4. `make configs` writes `configs/<group>/<kind>.yaml`; the invariant tests build every kind from it. A preset of this
   kind (same kind, other values) is a hand-written file in the group that composes the mirror and never takes a
   kind's name (CFG-3).
5. `templates/test_item.py.tmpl` -> `tests/<pkg>/<family>/test_<kind>.py`: one sentence-named test per behaviour the
   kind adds, built through `<Family>Factory.from_config` as users build it, with fakes for collaborators (TST-1,
   TST-3). Building from the generated YAML is already the invariant tests' job.
6. `make check`.
