# nuikit guide

The rules for code built on nuikit: families, configuration, the CLI error boundary, logging, run directories and
seeding. They name nuikit's API, so they live and change with it; `<pkg>` below is the import package of the project
that uses nuikit.

The other rule IDs live elsewhere:

- [nuinashco/conventions](https://github.com/nuinashco/conventions) (`GUIDE.md`), the rules for every Python repo:
  LAY-1..LAY-3, LAY-5, LAY-6, ARC, TYP, STY, DOC, ERR-3..ERR-6, LOG-2, LOG-4, LOG-5, TST-1..TST-4, TST-6..TST-8,
  RDOC, GIT, TOOL-1, TOOL-2 and TOOL-4..TOOL-6. It also says how to read a rule and lists the retired IDs.
- [nuinashco/rnd-template](https://github.com/nuinashco/rnd-template), the project layout built on nuikit: LAY-4,
  LAY-7, ENV-1..ENV-3, TST-5, RUN-3..RUN-7 and TOOL-3.

**MUST**, **SHOULD** and **MAY** follow [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) as clarified by
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174). Each rule ends with its *Check*: a test in this repo, a tool, a
test that a project built from the rnd template carries, or `review` when no tool can tell. A project that can't
follow a rule yet lists it under "Deviations" in its CONTRIBUTING.md, with the reason. Changing a rule means changing
this file and the code and tests it names in the same commit, then tagging a release.

- [Quick reference](#quick-reference) · [Families](#families-fam) · [Configuration](#configuration-cfg) ·
  [Errors](#errors-err) · [Logging](#logging-log) · [Runs](#runs-run) · [Decisions](#decisions) · [Sources](#sources)

## Quick reference

| area | rule |
|---|---|
| extension points | family = `base.py` + `items/`, `@Factory.register(kind)` outermost, auto-discovered |
| config | Hydra composes, `Schema.from_hydra` validates (forbid + frozen), defaults in `Field` mirrored to `defaults/` and one file per kind, hand-written entry configs and presets on top |
| errors | `nuikit.errors.UserError` with `exit_code`, one `cli_boundary` |
| logging | structlog over stdlib, configured once by `configure_logging`, console in a TTY, JSON otherwise |
| runs | `runs/<name>/` with config, git SHA and outputs; seed once, pass generators |

## Families (FAM)

A family is any concept with several interchangeable implementations chosen by a config `kind`: endpoints, patch
sources, collectors, processors. `nuikit.registry` holds the parts: `KindConfig`, `Configurable`,
`ConfigurableFactory`, `import_submodules` and the discovery that `make configs` uses.

```text
<pkg>/endpoints/
  base.py            Endpoint (abstract), EndpointConfig, EndpointFactory
  items/
    __init__.py      import_submodules(__name__)
    passthrough.py   @EndpointFactory.register("passthrough")
    litellm.py       @EndpointFactory.register("litellm")
```

Registration through eager auto-import is a deliberate choice at this scale. Its known costs are import time, the global
registry, and breakage under [PEP 810](https://peps.python.org/pep-0810/) lazy imports
([Wu](https://ppwwyyxx.com/blog/2023/Registration-Does-Not-Scale-Well/)). If import time becomes a problem, switch the
family to a lazy `kind -> "module:Class"` map.

### FAM-1 MUST

A family is `base.py` (abstract base, its config schema, its factory) plus an `items/` folder with one module per
implementation. `items/__init__.py` calls `nuikit.registry.import_submodules(__name__)`, so adding an item is adding a
file. The family's `__init__.py` imports `items`, so importing the family registers its kinds. `make configs` and the
invariant tests import the whole package (`nuikit.registry.import_tree`), so they see every family even before code
uses it. `import_tree` reads only folders with an `__init__.py`, so every folder between `<pkg>` and a family has one;
it never imports `<pkg>.cli` or a `__main__` module.

*Check:* review; `tests/test_registry.py` covers `import_submodules` and `import_tree`.

### FAM-2 MUST

Items register with `@<Family>Factory.register("<kind>")` as the **outermost** decorator. Kinds are snake_case and
unique; registering a kind twice raises.

*Why:* attrs replaces a slotted class, so a decorator applied before `@define` would register the discarded class
(TYP-5).

*Check:* `register` raises on a duplicate kind and on a class that is not yet an attrs class (`tests/test_registry.py`);
`check-conventions` flags a `register` below another decorator.

### FAM-3 MUST

An item binds its config schema through the family's type argument: `class Square(Shape[SquareConfig])` sets
`Square.Config` and types `self.config` precisely. An explicit `Config = X` still wins. An item without settings of
its own names the family's config, `class Unit(Shape[ShapeConfig])`, and an item that extends a registered one keeps
that item's schema. `register` refuses any other item, since its settings would be rejected as unknown keys:
`class Tri(Shape)` raises `TypeError: ShapeFactory: Tri must name its config: class Tri(Shape[TriConfig])`.
`<Family>Factory.from_config(data)` reads `kind`, validates the rest against that item's `Config` and builds the item
(config-first creation); `validate(data)` only validates.

*Check:* `tests/test_registry.py`; pyright.

### FAM-4 MUST

Each factory declares `config_group`. `make configs` writes `configs/<group>/<kind>.yaml` for every registered kind
(CFG-3), the files `nuikit.registry.config_files("<pkg>")` lists. A family whose kinds run together, such as metrics,
sets `multiple = True`: the entry config selects a list (`<group>: [a, b]`, overridden as `'<group>=[a]'`, quoted
because zsh expands square brackets), each generated file starts with `# @package <group>.<kind>` because Hydra reads
a package only from the first line, and the schema field maps each kind to its config. A preset of such a family
starts with the same `# @package <group>.<kind>` line as the mirror it composes. The field validates each value on its
own and has no validator for the whole mapping, so that an error names its kind (`metric.f1.threshold`) and the
errors of every kind are listed:

```python
metric: dict[
    str,
    Annotated[
        SerializeAsAny[MetricConfig],
        BeforeValidator(MetricFactory.validate),
    ],
]
```

*Check:* the project's `tests/test_invariants.py` (TST-5) fails on stale or missing files; `tests/test_registry.py`
covers the paths and packages, and `tests/test_plugin.py` the error paths of that field.

### FAM-5 SHOULD

CONTRIBUTING's "Extending" table lists every family: what to add, where, and what selects it.

*Check:* review.

## Configuration (CFG)

### CFG-1 MUST

Hydra composes YAML; the entry point validates the composed config with `MainConfig.from_hydra(cfg)` before anything
runs. No `DictConfig` travels past the entry point, and YAML never names Python classes (`_target_`).

*Why:* configs are parsed at the boundary ([King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/));
renames can't break YAML.

*Check:* the project's `tests/test_invariants.py` composes and validates every entry config (TST-5).

### CFG-2 MUST

Schemas extend `nuikit.config.Schema` (`extra="forbid"`, `frozen=True`). A typo is an error with one line per bad
field, and validated configs are read-only. Read-only is shallow: a list or dict held in a field can still be changed
in place, so a field that must not change is typed as a tuple or a frozenset. Pydantic's default coercion stays on,
and a `str` field also takes a number, which is what YAML and the command line make of `run_name=7`; it still refuses
a boolean. The text is the number as Python writes it, so `run_name=1.50` gives `1.5`: quote the value to keep what was
typed, `'run_name="1.50"'`.

*Why:* "it should be possible to detect unused or redundant settings"
([Sculley et al. 2015](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html)).

*Check:* `tests/test_config.py`.

### CFG-3 MUST

Defaults live in the schema, and so does what a setting needs explained: a `description` only when the name, type and
default leave something open (DOC-7). `make configs` renders each schema to a mirror with `nuikit.configgen`: every
field, its default (or `???`) and its description as a comment, with a blank line after each nested block. A default
that holds `${...}` is written as it stands, so the generated file resolves it as an interpolation and code that builds
the schema directly gets the raw text. A set is written as a list sorted by the JSON text of its items. Mirrors are
committed and never edited, so the YAML shows what is tunable without opening Python. An entry config's mirror is
`configs/defaults/<command>.yaml` and leaves out the fields that config groups provide; a family item's mirror is
`configs/<group>/<kind>.yaml`, the option that `<group>=<kind>` selects. After a kind is renamed or removed, delete its
generated file: `make configs` writes files and never removes one. Everything else is hand-written, composes a mirror
and only sets values: the entry config `configs/<command>.yaml`, whose defaults list picks the mirror, the groups and
Hydra's settings with `_self_` last, and the presets in each group, which name variants of a kind
(`configs/endpoint/gemini.yaml` composing `litellm`) and never take a kind's name. A value changes in the narrowest
place that fits:

| to change | edit |
|---|---|
| one run | `key=value` on the command line; the run directory records it |
| a reusable variant of one part | a preset in its group (`configs/endpoint/gemini.yaml`) |
| every run of this repo | the entry config `configs/<command>.yaml` |
| the default itself, which tests and Python callers also get | the schema, then `make configs` |

```python
class LiteLLMConfig(RemoteEndpointConfig):
    """Endpoint that calls a provider through LiteLLM."""

    model: str = Field(description="provider/model, e.g. gemini/gemini-2.5-pro")
    rpm: PositiveInt | None = Field(
        None, description="requests per minute; null = unlimited"
    )
    timeout_s: PositiveFloat = Field(600, description="per request")
    max_retries: NonNegativeInt = 3
```

Its mirror, `configs/endpoint/litellm.yaml`, as `make configs` writes it:

```yaml
# Generated by `make configs` from LiteLLMConfig; edit the schema, not this file.

kind: "litellm"
model: ???  # provider/model, e.g. gemini/gemini-2.5-pro
rpm: null  # requests per minute; null = unlimited
timeout_s: 600  # per request
max_retries: 3
```

A preset, `configs/endpoint/gemini.yaml`, composes the mirror and sets what differs; `endpoint=gemini` selects it:

```yaml
defaults:
  - litellm

model: gemini/gemini-2.5-pro
```

*Why:* defaults have one source, and every file is plainly either generated or yours to edit.

*Check:* the project's `tests/test_invariants.py` fails when a mirror is stale, and composes every entry config with
its mirror; `tests/test_configgen.py` pins the rendering.

### CFG-4 MUST

A value with no sensible default has no default in the schema and is `???` in YAML. Never use a placeholder value.

*Check:* review.

### CFG-5 MUST

The config tree mirrors the code:

- a family selected through config has a group `configs/<config_group>/` ↔ `<pkg>/<family>/`;
- each entry config `configs/<command>.yaml` and its mirror `configs/defaults/<command>.yaml` ↔ a schema in
  `<pkg>/config.py` (or a `<pkg>/config/` package once there are several);
- a group of presets for one schema (`configs/eval/`) ↔ that schema.

A family chosen by a CLI argument rather than by config needs no group.

*Check:* review.

### CFG-6 MUST

Secrets come from the environment (`.env`, loaded by `rootutils.setup_root`) through `${oc.env:VAR,null}`, never from
the command line, and reach child processes through the environment. Every secret is typed `SecretStr | None = None`;
the command that needs it checks it before any work (ERR-4) and raises
`ConfigError("no service key; set SERVICE_API_KEY in .env")`, naming the variable, and a test that runs that command
sets the variable itself (`monkeypatch.setenv`).

Masking follows the type and nothing else. Only fields typed `SecretStr`, `SecretBytes` or `Secret[...]` are masked:
`config.yaml` and the config sent to W&B show `**********` for them, and `run.json` records the command line with the
value of every `key=value` that sets one masked, however Hydra lets the key be spelled (`tokens.0`, `tokens[0]`) and
whether it gives the field's name or an alias, except `~key=value` that deletes a value containing a schema with a
secret. A token in a plain `str`, a URL that carries a password or a header in a plain dict is written
as it is, so a credential is typed as a secret: `SecretStr` for the whole URL, `dict[str, SecretStr]` for headers.
W&B records the command line as typed, in its files under the run directory (`runs/<run_name>/wandb/`) and in the
run it uploads, so a secret given there stays unmasked in a mirrored run.

*Why:* a secret without a default fails `make check` wherever the variable is not exported, CI included, and the
error never names the variable. A mask by key name or inside URLs would blank ordinary settings and still miss
credentials, so it would promise more than it keeps.

*Check:* `tests/test_runs.py` checks that the run snapshot, the config sent to W&B and the recorded command line mask
the fields typed as secrets, and only those; gitleaks.

### CFG-7 MUST

Anything a user might tune comes from config. Constants in code are for facts: protocol limits, measured values, unit
conversions. Each one gets a comment giving its provenance.

*Check:* review.

### CFG-8 SHOULD

A polymorphic config field resolves through its family factory by `kind`; an unknown kind lists the registered ones in
its error.

*Check:* `tests/test_registry.py` covers the unknown-kind error; review.

## Errors (ERR)

### ERR-1 MUST

A problem the user can fix raises `nuikit.errors.UserError` or a subclass; a package that needs its own family of
errors subclasses it (`ProxyError(UserError)`). Each carries an `exit_code`: `ConfigError` exits with 2 and
`DataError` with 3. Every other exception is a bug and keeps its traceback.

*Why:* "a bug is a kind of error the programmer didn't expect"; recoverable errors are expected
([Duffy](https://joeduffyblog.com/2016/02/07/the-error-model/)). This is the model click's `ClickException` uses.

*Check:* `tests/test_errors.py`.

### ERR-2 MUST

Each entry point has one boundary, `@cli_boundary`. It turns package errors, pydantic `ValidationError` and OmegaConf
errors into `error: <message>` on stderr and the matching exit code. Nothing else catches broadly. The decorator sits
directly on the function, below `@hydra.main`: Hydra catches what the function it wraps raises and exits with 1, so a
boundary above it reports nothing. Errors Hydra finds itself while composing, such as an unknown key or group option
on the command line, never reach the boundary: Hydra prints them and exits with 1.

*Check:* review; `tests/test_errors.py` covers what the boundary reports.

## Logging (LOG)

### LOG-1 MUST

Logging is structlog over the standard library. Each module that logs has `log = structlog.stdlib.get_logger()` at
the top (typed, unlike `structlog.get_logger()`). `nuikit.logging.configure_logging()` is called once, by the entry
point; no other code configures logging.

*Why:* one pipeline for our events and for third-party stdlib logs (LiteLLM, httpx, Hydra)
([structlog](https://www.structlog.org/en/stable/standard-library.html)).

*Check:* review; `tests/test_logging.py` checks that structlog and stdlib records share one renderer.

### LOG-3 MUST

The renderer is pretty console output when stderr is a TTY and JSON otherwise. Hydra's `job_logging` and
`hydra_logging` are disabled.

*Check:* `tests/test_logging.py` covers `fmt="auto"`; the rnd template's `configs/hydra/default.yaml` disables Hydra's
logging.

## Runs (RUN)

### RUN-1 MUST

Every run writes `runs/<run_name>/` containing:

- `config.yaml`: the resolved config with the fields typed as secrets masked (CFG-6). A literal `${` or `???` in a
  string is written escaped (`\${`, `\???`), so that loading the file gives the text that ran and not a new
  interpolation or a missing value, and a set is written as a list sorted by the JSON text of its items, so that two
  runs of one config write the same file;
- `run.json`: the commit and the dirty flag of the project's checkout, the start time and argv, the command line with
  the value of every `key=value` that sets a secret masked (CFG-6);
- the run's outputs.

`nuikit.runs.start_run` writes the first two. The entry point passes `repo=paths.ROOT`, the checkout whose state
`run.json` records (the working directory when left out). `start_run` reads the commit and the dirty flag there, never
in the run directory, and before it creates that directory: `runs/` on another disk or inside another repository changes
neither, and a run cannot make its own record dirty. Untracked files count as dirty, since a new module that is not
added yet is code that ran, so a project git-ignores `runs/`, or each run after the first is recorded dirty. Before the
first commit the commit is `null`. Both are `null` without git or outside a checkout; when git fails for another reason
they are `null` too, and one `git_state_unreadable` warning carries the first line of git's error.

`start_run` refuses a `run_name` that leaves `runs/` or names it itself, and a directory that exists, so each job of a
sweep needs its own name: `-m seed=1,2 'run_name=sweep_${hydra:job.num}'`. For a single run Hydra writes nothing else; a
sweep (`-m`) still writes its `multirun.yaml` and an empty folder per job where `hydra.sweep.dir` points, with the
overrides as they were typed. A run mirrored to W&B also gives W&B the command line, as typed (CFG-6).

*Why:* any result can be traced back to its code and config.

*Check:* `tests/test_runs.py`.

### RUN-2 MUST

Seed once in the entry point with `seed_everything(cfg.seed)`. Code that needs randomness takes an explicit
`np.random.Generator` or `torch.Generator`. Never call the global `np.random.*` functions.

*Why:* "global state is always problematic" ([NEP 19](https://numpy.org/neps/nep-0019-rng-policy.html)); full
determinism also needs PyTorch's flags ([PyTorch](https://docs.pytorch.org/docs/stable/notes/randomness.html)).

*Check:* ruff NPY002; `tests/test_seeding.py`.

## Decisions

Contested choices, what was weighed and why nuikit picks what it does. Revisit an entry when its reason no longer
holds.

| topic | decision | alternatives | why |
|---|---|---|---|
| shared building blocks | the `nuikit` library, a versioned dependency | vendored by the template (until nuikit 0.1.0); copying by hand | one repo with its own tests, tags and Claude plugin; a fix reaches a project as a lock update, and no copy drifts |
| implementation lookup | registry with auto-discovery | explicit imports; lazy map; discriminated union | adding a file is all it takes; costs accepted at this scale (FAM) |
| config bridge | `Schema.from_hydra` | `_target_` + instantiate; Hydra structured configs | parse at the boundary; YAML never names classes |
| config defaults | schema is the source, YAML generated | YAML + schema + parity test; YAML only | one source of truth while YAML stays readable |
| entry configs | hand-written, composing a generated mirror | generated entry config; hand-written only | one place to edit the standard run while every default stays documented |
| errors | base error with exit codes | single UserError; builtins only | scripts can tell config errors from data errors |
| logging | structlog over stdlib, snake_case events | stdlib %-style; loguru | structured events for cloud pipelines; one renderer for third-party logs |

## Sources

- Design: Wu, [Registration Does Not Scale Well](https://ppwwyyxx.com/blog/2023/Registration-Does-Not-Scale-Well/);
  [PEP 810](https://peps.python.org/pep-0810/).
- Configuration: King, [Parse, don't validate](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/);
  Sculley et al., [Hidden Technical Debt in ML Systems](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html)
  (2015).
- Errors and logging:
  - Duffy, [The Error Model](https://joeduffyblog.com/2016/02/07/the-error-model/)
  - [Logging HOWTO](https://docs.python.org/3/howto/logging.html)
  - [structlog and the standard library](https://www.structlog.org/en/stable/standard-library.html)
- Reproducibility: [NEP 19](https://numpy.org/neps/nep-0019-rng-policy.html),
  [PyTorch reproducibility](https://docs.pytorch.org/docs/stable/notes/randomness.html).
- Process: [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).
