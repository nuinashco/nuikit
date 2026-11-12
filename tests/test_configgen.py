"""Generated YAML lists every field with its default and description."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass  # conventions: TYP-4 - a dataclass default is tested.
from datetime import timedelta
from typing import Any

import pytest
from omegaconf import DictConfig, OmegaConf
from pydantic import (
    AliasChoices,
    Field,
    Secret,
    SecretBytes,
    SecretStr,
    create_model,
    field_serializer,
)

from nuikit.config import Schema
from nuikit.configgen import ConfigFile, render, stale, write
from nuikit.errors import ConfigError

# Hash order puts eight members in sorted order once in 40320 processes.
EIGHT = frozenset({"train", "val", "test", "dev", "probe", "holdout", "unseen", "tune"})
SORTED = '["dev", "holdout", "probe", "test", "train", "tune", "unseen", "val"]'


class Inner(Schema):
    """Nested block."""

    timeout_s: float = Field(default=30.0, description="seconds")


class Outer(Schema):
    """Top-level config."""

    name: str = Field(description="required, no default")
    tags: list[str] = Field(default_factory=lambda: ["a"])
    inner: Inner = Field(default_factory=Inner, description="nested settings")
    optional: Inner | None = Field(default_factory=Inner)
    disabled: Inner | None = None
    endpoint: str = Field(description="provided by a config group")


class Grouped(Schema):
    """Config whose every field comes from a group."""

    endpoint: str


class Search(Schema):
    """Nested block that a group fills in part."""

    endpoint: str
    batch_size: int = 4


class Nested(Schema):
    """Config with a group inside a nested block."""

    search: Search


class Tuned(Inner):
    """Nested block with a field of its own."""

    retries: int = 5


class Renamed(Schema):
    """Nested block whose field validation reads from another key."""

    schema_: str = Field(default="x", alias="schema")


class Keyed(Schema):
    """Nested block whose default is a secret."""

    token: SecretStr = SecretStr("EMPTY")


class Tagged(Schema):
    """Nested block whose default is a set."""

    tags: set[str] = Field(default_factory=lambda: set(EIGHT))


@dataclass(frozen=True)  # conventions: TYP-4 - a dataclass default is tested.
class Split:
    """Dataclass whose default is a set."""

    names: frozenset[str] = EIGHT


class Queued(Schema):
    """List item whose only set is in a deque."""

    queue: deque[frozenset[str]] = Field(default_factory=lambda: deque([EIGHT]))


class Splits(Schema):
    """Config whose defaults hold sets at every depth."""

    names: frozenset[str] = EIGHT
    mixed: frozenset[int | str] = frozenset({10, 9, "a"})
    by_stage: dict[str, set[str]] = Field(default_factory=lambda: {"fit": set(EIGHT)})
    rounds: list[frozenset[str]] = Field(default_factory=lambda: [EIGHT])
    queue: deque[frozenset[str]] = Field(default_factory=lambda: deque([EIGHT]))
    split: Split = Field(default_factory=Split)
    block: Tagged = Field(default_factory=Tagged)
    items: list[Tagged] = Field(default_factory=lambda: [Tagged()])
    queues: list[Queued] = Field(default_factory=lambda: [Queued()])


class Span(Schema):
    """List item whose field a serializer of its own writes as JSON."""

    length: timedelta = timedelta(minutes=5)

    @field_serializer("length", when_used="json")
    def _seconds(self, length: timedelta) -> float:
        return length.total_seconds()


class Spans(Schema):
    """Config whose list and dict defaults hold models."""

    spans: list[Span] = Field(default_factory=lambda: [Span()])
    by_stage: dict[str, Span] = Field(default_factory=lambda: {"fit": Span()})


class Described(Schema):
    """Config whose descriptions hold line breaks and stray spaces."""

    warmup_steps: int = Field(
        default=0,
        description="""steps of linear warmup;
        0: no warmup""",
    )
    rate: float = Field(default=0.1, description="per  step \n")
    blank: int = Field(default=1, description=" \n ")


class Limits(Schema):
    """Config whose defaults are floats that JSON cannot write."""

    high: float | str = math.inf
    low: Any = -math.inf
    unknown: Any = math.nan
    each: list[float] = Field(default_factory=lambda: [math.inf, 1.5])


class Aliased(Schema):
    """Config whose fields validation reads from other keys than their names."""

    schema_: str = Field(default="x", alias="schema")
    size: int = Field(default=4, alias="shown", validation_alias="batch-size")
    endpoint: str = Field(default="local", alias="from-a-group")


def load(text: str) -> DictConfig:
    """Return the config that Hydra reads from a generated file."""
    config = OmegaConf.create(text)
    assert isinstance(config, DictConfig)
    return config


def test_render_writes_defaults_required_markers_comments_and_spaced_nested_blocks():
    text = render(ConfigFile("outer.yaml", Outer, groups=("endpoint",)))

    assert text.splitlines()[1:] == [
        "# Chosen through config groups, not listed here: endpoint.",
        "",
        "name: ???  # required, no default",
        'tags: ["a"]',
        "inner:  # nested settings",
        "  timeout_s: 30.0  # seconds",
        "",
        "optional:",
        "  timeout_s: 30.0  # seconds",
        "",
        "disabled: null",
    ]


def test_render_ends_without_a_blank_line_when_groups_give_every_field():
    text = render(ConfigFile("grouped.yaml", Grouped, groups=("endpoint",)))

    assert text.splitlines()[1:] == [
        "# Chosen through config groups, not listed here: endpoint.",
    ]


def test_render_leaves_out_a_group_inside_a_nested_block():
    text = render(ConfigFile("nested.yaml", Nested, groups=("search/endpoint",)))

    assert text.splitlines()[1:] == [
        "# Chosen through config groups, not listed here: search/endpoint.",
        "",
        "search:",
        "  batch_size: 4",
    ]


def test_render_puts_a_package_first_for_hydra():
    text = render(ConfigFile("metric/a.yaml", Inner, package="metric.a"))

    assert text.splitlines()[:2] == [
        "# @package metric.a",
        "# Generated by `make configs` from Inner; edit the schema, not this file.",
    ]


def test_write_rewrites_only_stale_files(tmp_path):
    files = [ConfigFile("a/outer.yaml", Outer), ConfigFile("inner.yaml", Inner)]
    (tmp_path / "inner.yaml").write_text(render(files[1]), encoding="utf-8")

    assert write(files, tmp_path) == [tmp_path / "a" / "outer.yaml"]
    assert stale(files, tmp_path) == []


def test_render_writes_a_set_as_a_sorted_list_at_any_depth():
    text = render(ConfigFile("splits.yaml", Splits))

    assert text.splitlines()[2:] == [
        f"names: {SORTED}",
        'mixed: ["a", 10, 9]',
        f'by_stage: {{"fit": {SORTED}}}',
        f"rounds: [{SORTED}]",
        f"queue: [{SORTED}]",
        f'split: {{"names": {SORTED}}}',
        "block:",
        f"  tags: {SORTED}",
        "",
        f'items: [{{"tags": {SORTED}}}]',
        f'queues: [{{"queue": [{SORTED}]}}]',
    ]
    assert Splits.from_hydra(load(text)) == Splits()


def test_render_writes_a_model_in_a_default_with_its_json_serializers():
    text = render(ConfigFile("spans.yaml", Spans))

    assert text.splitlines()[2:] == [
        'spans: [{"length": 300.0}]',
        'by_stage: {"fit": {"length": 300.0}}',
    ]
    assert Spans.from_hydra(load(text)) == Spans()


def test_render_writes_a_description_on_one_comment_line():
    text = render(ConfigFile("described.yaml", Described))

    assert text.splitlines()[2:] == [
        "warmup_steps: 0  # steps of linear warmup; 0: no warmup",
        "rate: 0.1  # per step",
        "blank: 1",
    ]
    assert Described.from_hydra(load(text)) == Described()


def test_render_writes_an_interpolation_as_it_stands():
    named = create_model("Named", __base__=Schema, run_name=(str, "${now:%Y-%m-%d}"))

    text = render(ConfigFile("named.yaml", named))

    assert text.splitlines()[2:] == ['run_name: "${now:%Y-%m-%d}"']
    assert OmegaConf.is_interpolation(load(text), "run_name")


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        pytest.param(
            {"prompt": (str, "${")},
            "no viable alternative at input '${'",
            id="interpolation-omegaconf-cannot-parse",
        ),
        pytest.param(
            {"a": (int, Field(1, alias="x")), "b": (int, Field(2, alias="x"))},
            "found duplicate key x",
            id="two-fields-under-one-key",
        ),
        pytest.param(
            {"prompt": (str, "a \ud800 b")},
            "'utf-8' codec can't encode character '\\ud800' in position 87: "
            "surrogates not allowed",
            id="lone-surrogate",
        ),
    ],
)
def test_render_refuses_text_that_hydra_would_not_load(fields, reason):
    broken = create_model("Broken", __base__=Schema, **fields)

    with pytest.raises(ConfigError) as error:
        render(ConfigFile("broken.yaml", broken))

    assert str(error.value) == (
        f"config generated from Broken does not load: {reason}; "
        "fix the default that causes it"
    )


def test_render_writes_non_finite_floats_as_yaml_reads_them():
    text = render(ConfigFile("limits.yaml", Limits))

    assert text.splitlines()[2:] == [
        "high: .inf",
        "low: -.inf",
        "unknown: .nan",
        "each: [.inf, 1.5]",
    ]
    limits = Limits.from_hydra(load(text))
    assert (limits.high, limits.low, limits.each) == (
        math.inf,
        -math.inf,
        [math.inf, 1.5],
    )
    assert math.isnan(limits.unknown)


@pytest.mark.parametrize(
    "char",
    ["\x7f", "\x85", "\x9f", "\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}"],
    ids=["delete", "next-line", "c1-control", "line-separator", "paragraph-separator"],
)
def test_render_escapes_a_character_that_yaml_does_not_take_raw(char):
    prompt = create_model(
        "Prompt",
        __base__=Schema,
        text=(str, f"a {char} b"),
        by_mark=(dict[str, str], {char: char}),
    )

    text = render(ConfigFile("prompt.yaml", prompt))

    assert text.isascii()
    assert prompt.from_hydra(load(text)) == prompt()


@pytest.mark.parametrize(
    "word", ["on", "off", "yes", "no", "true", "null", "1", "Yes", "ON", "Null"]
)
def test_render_quotes_a_key_that_yaml_would_not_read_as_that_string(word):
    fields: dict[str, Any] = {word: (int, 1)}
    keyword = create_model("Keyword", __base__=Schema, **fields)

    text = render(ConfigFile("keyword.yaml", keyword))

    assert text.splitlines()[2:] == [f'"{word}": 1']
    assert keyword.from_hydra(load(text)) == keyword()


def test_render_writes_a_field_under_the_key_validation_reads_it_from():
    text = render(ConfigFile("aliased.yaml", Aliased, groups=("endpoint",)))

    assert text.splitlines()[3:] == ['schema: "x"', '"batch-size": 4']
    assert Aliased.from_hydra(load(text)) == Aliased()


def test_render_writes_the_alias_beside_alias_choices_which_validation_rejects():
    either = Field(default=2, validation_alias=AliasChoices("a", "b"), alias="one")
    choices = create_model("Choices", __base__=Schema, either=(int, either))

    text = render(ConfigFile("choices.yaml", choices))

    assert text.splitlines()[2:] == ["one: 2"]
    with pytest.raises(ConfigError, match="one: Extra inputs are not permitted"):
        choices.from_hydra(load(text))


@pytest.mark.parametrize(
    ("annotation", "default", "field"),
    [
        pytest.param(SecretStr, SecretStr("EMPTY"), "api_key", id="str"),
        pytest.param(SecretBytes, SecretBytes(b"EMPTY"), "api_key", id="bytes"),
        pytest.param(Secret[int], Secret[int](7), "api_key", id="generic"),
        pytest.param(list[SecretStr], [SecretStr("EMPTY")], "api_key", id="in-a-list"),
        pytest.param(list[Keyed], [Keyed()], "api_key", id="in-a-model-in-a-list"),
        pytest.param(Keyed, Keyed(), "api_key.token", id="in-a-nested-block"),
    ],
)
def test_render_refuses_a_secret_default_which_it_would_write_as_its_mask(
    annotation, default, field
):
    remote = create_model("Remote", __base__=Schema, api_key=(annotation, default))

    with pytest.raises(ConfigError) as error:
        render(ConfigFile("remote.yaml", remote))

    assert str(error.value) == (
        f"default of Remote.{field} is a secret, which a generated file would show "
        "as its mask; default it to None and read the secret from the environment "
        "(CFG-6)"
    )


def test_render_writes_a_secret_without_a_value_as_null_or_required():
    remote = create_model(
        "Remote",
        __base__=Schema,
        api_key=(SecretStr | None, None),
        token=(SecretStr, ...),
    )

    text = render(ConfigFile("remote.yaml", remote))

    assert text.splitlines()[2:] == ["api_key: null", "token: ???"]


def test_render_gives_a_default_factory_the_defaults_above_it():
    run_name = Field(default_factory=lambda data: f"{data['kind']}-{data['seed']}")
    dependent = create_model(
        "Dependent",
        __base__=Schema,
        kind=(str, ...),
        seed=(int, 1),
        run_name=(str, run_name),
    )

    text = render(ConfigFile("dependent.yaml", dependent, kind="sweep"))

    assert text.splitlines()[2:] == ['kind: "sweep"', "seed: 1", 'run_name: "sweep-1"']


def test_render_reports_a_default_factory_that_fails_on_the_defaults_above_it():
    run_name = Field(default_factory=lambda data: f"run-{data['seed']}")
    dependent = create_model(
        "Dependent", __base__=Schema, seed=(int, ...), run_name=(str, run_name)
    )

    with pytest.raises(ConfigError) as error:
        render(ConfigFile("dependent.yaml", dependent))

    assert str(error.value) == (
        "default factory of Dependent.run_name fails on the defaults above it: "
        "KeyError: 'seed'; make it read only fields above it that have a default"
    )


@pytest.mark.parametrize(
    ("annotation", "default", "block"),
    [
        pytest.param(
            Inner,
            Field(default_factory=lambda: Tuned(timeout_s=5.0)),
            ["  timeout_s: 5.0  # seconds", "  retries: 5"],
            id="subclass-instance",
        ),
        pytest.param(
            Inner,
            Field(default={"timeout_s": 5.0}, validate_default=True),
            ["  timeout_s: 5.0  # seconds"],
            id="mapping",
        ),
        pytest.param(
            Renamed,
            Field(default={"schema": "y"}, validate_default=True),
            ['  schema: "y"'],
            id="mapping-by-alias",
        ),
    ],
)
def test_render_writes_a_nested_block_from_the_default_of_its_field(
    annotation, default, block
):
    outer = create_model("Outer", __base__=Schema, inner=(annotation, default))

    text = render(ConfigFile("outer.yaml", outer))

    assert text.splitlines()[2:] == ["inner:", *block]
