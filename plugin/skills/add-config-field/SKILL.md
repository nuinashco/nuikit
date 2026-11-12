---
name: add-config-field
description: Use when adding or changing a setting in a project built on nuikit, anything a user might tune, including a value that is a constant in code today. Covers which schema owns it, its default and description, regenerating the YAML mirrors, and which file to edit to change its value.
paths:
  - "src/**/config.py"
  - "src/**/base.py"
  - "src/**/items/*.py"
  - "configs/**/*.yaml"
---

# Add a config setting

Every tunable value has one source: a field with a default on a `nuikit.config.Schema` (CFG-3, CFG-7). The YAML
mirrors are generated from it. Rules: [docs/guide.md](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md)
CFG-1..CFG-7; conventions DOC-7, STY-6, TYP-7.

## Steps

1. Pick the schema that owns it:

   | the setting belongs to | schema | its mirror |
   |---|---|---|
   | one command | `<Command>Config` in `src/<pkg>/config.py` | `configs/defaults/<command>.yaml` |
   | one kind of a family | `<Kind><Family>Config` in `items/<kind>.py` | `configs/<group>/<kind>.yaml` |
   | every kind of a family | `<Family>Config` in `<family>/base.py` | every `configs/<group>/*.yaml` |

2. Add the field with a default. A value with no sensible default has none, and the mirror shows `???` (CFG-4); never
   a placeholder value. Type it as narrowly as pydantic checks: `PositiveInt`, `Literal["a", "b"]` for a small closed
   set (TYP-7), `X | None` when `null` means something. A number with a unit ends in its suffix: `timeout_s`,
   `budget_tokens`, `wait_minutes` (STY-6).
3. Add a `description` only for what the name, type and default leave open: the options (`auto|console|json`), a unit
   the name lacks, what `null` or an edge value means, a side effect, a source. Never restate the key (DOC-7).

   ```python
   retries: NonNegativeInt = 3
   rpm: PositiveInt | None = Field(default=None, description="null: unlimited")
   log_format: LogFormat = Field(
       default="auto", description="auto|console|json; auto: console in a terminal"
   )
   ```

4. A secret is typed `SecretStr | None` with default `None` when it is optional, or `SecretStr` with no default when
   the run needs it. Its value comes from the environment in the hand-written entry config:
   `api_key: ${oc.env:SERVICE_API_KEY,null}` (CFG-6). The run's `config.yaml` masks it.
5. Run `make configs`. Mirrors are never edited by hand, and `check-protected` refuses edits to them.
6. Read the value as `cfg.<field>` in the composition root or `self.config.<field>` in an item, and pass it down as
   an argument. Remove the constant it replaces; constants in code are only facts with a provenance comment (CFG-7).
7. A setting that changes behaviour gets a test of that behaviour. `make check` fails while a mirror is stale.
8. After writing descriptions, run the conventions plugin's `descriptions-judge` agent and apply its verdicts.

## Changing a value

Change it in the narrowest place that fits (CFG-3):

| to change | edit |
|---|---|
| one run | `key=value` on the command line; the run directory records it |
| a reusable variant of one part | a preset in its group, such as `configs/<group>/<preset>.yaml` composing a kind's mirror |
| every run of this repo | the entry config `configs/<command>.yaml`, below its `defaults:` list |
| the default itself, which tests and Python callers also get | the schema, then `make configs` |
