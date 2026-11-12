"""Families: config-first creation, registration rules, discovery, generated configs."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import Any

import pytest
from attrs import define
from pydantic import Field

from nuikit.errors import ConfigError
from nuikit.registry import (
    Configurable,
    ConfigurableFactory,
    KindConfig,
    config_files,
    import_submodules,
    import_tree,
)


class ShapeConfig(KindConfig):
    """Config shared by every shape."""


@define
class Shape[C: ShapeConfig](Configurable[C], ABC):
    """Toy family base."""

    @abstractmethod
    def area(self) -> float: ...


class ShapeFactory(ConfigurableFactory[Shape[Any]]):
    """Toy family registry."""

    config_group = "shape"


class SquareConfig(ShapeConfig):
    """Square settings."""

    side_m: float = Field(default=1.0, gt=0, description="metres")


@ShapeFactory.register("square")
@define
class Square(Shape[SquareConfig]):
    """Toy item."""

    def area(self) -> float:
        return self.config.side_m**2


def test_from_config_validates_against_the_kinds_schema_and_builds_it():
    square = ShapeFactory.from_config({"kind": "square", "side_m": 2})

    assert (type(square), square.area()) == (Square, 4.0)
    with pytest.raises(ConfigError, match="registered: square"):
        ShapeFactory.from_config({"kind": "circle"})


def test_family_value_that_is_not_a_mapping_is_a_config_error():
    with pytest.raises(ConfigError) as error:
        ShapeFactory.validate(2.0)  # pyright: ignore[reportArgumentType]

    assert str(error.value) == (
        "shape config is 2.0, not a mapping with a `kind`; registered: square"
    )


def test_kind_that_is_not_a_name_is_a_config_error():
    with pytest.raises(ConfigError) as error:
        ShapeFactory.validate({"kind": ["square"]})

    assert str(error.value) == (
        "shape kind is ['square'], not a name; registered: square"
    )


def test_items_are_slotted_so_attribute_typos_fail():
    square = ShapeFactory.from_config({"kind": "square"})

    with pytest.raises(AttributeError):
        square.sied_m = 3  # pyright: ignore[reportAttributeAccessIssue]


def register_twice() -> None:
    ShapeFactory.register("square")(Square)


def register_below_define() -> None:
    @define
    @ShapeFactory.register("triangle")  # conventions: FAM-2 - wrong order on purpose.
    class Triangle(Shape[ShapeConfig]):
        """Decorators in the wrong order."""

        def area(self) -> float:
            return 0.0


def register_outsider() -> None:
    @ShapeFactory.register("outsider")
    @define
    class Outsider:
        """Not a Shape."""


def register_without_config() -> None:
    @ShapeFactory.register("bare")
    @define
    class Bare(Shape):
        """Item that leaves out its type argument."""

        def area(self) -> float:
            return 0.0


def register_with_another_type() -> None:
    @ShapeFactory.register("odd")
    @define
    class Odd(Shape[int]):  # pyright: ignore[reportInvalidTypeArguments]
        """Item whose type argument is no config schema."""

        def area(self) -> float:
            return 0.0


@pytest.mark.parametrize(
    ("register", "error"),
    [
        (register_twice, ValueError),
        (register_below_define, TypeError),
        (register_outsider, TypeError),
    ],
)
def test_registration_rejects_mistakes(register, error):
    with pytest.raises(error):
        register()


@pytest.mark.parametrize(
    ("register", "item"),
    [(register_without_config, "Bare"), (register_with_another_type, "Odd")],
    ids=["no-type-argument", "type-argument-that-is-no-schema"],
)
def test_item_that_names_no_config_is_refused_with_the_declaration_to_write(
    register, item
):
    with pytest.raises(TypeError) as error:
        register()

    assert str(error.value) == (
        f"ShapeFactory: {item} must name its config: class {item}(Shape[{item}Config])"
    )
    assert ShapeFactory.list_registered() == ["square"]


def test_item_may_name_the_base_config_or_take_the_schema_of_the_item_it_extends():
    class Shapes(ConfigurableFactory[Shape[Any]]):
        """Family of its own, so that the kinds below stay out of ShapeFactory."""

    @Shapes.register("plain")
    @define
    class Plain(Shape[ShapeConfig]):
        """Item without settings of its own."""

        def area(self) -> float:
            return 0.0

    @Shapes.register("square")
    @define
    class LocalSquare(Shape[SquareConfig]):
        """Item with its own schema."""

        def area(self) -> float:
            return self.config.side_m**2

    @Shapes.register("big_square")
    @define
    class BigSquare(LocalSquare):
        """Item that extends a registered one and names no schema again."""

    @Shapes.register("fixed")
    @define
    class Fixed(Shape):
        """Item that sets its schema as a class attribute."""

        Config = SquareConfig

        def area(self) -> float:
            return 1.0

    built = Shapes.from_config({"kind": "big_square", "side_m": 3})
    assert (Plain.Config, BigSquare.Config, Fixed.Config, built.area()) == (
        ShapeConfig,
        SquareConfig,
        SquareConfig,
        9.0,
    )


def test_subclassed_factory_shares_the_registry():
    class Shapes(ShapeFactory):
        """Same family, another name."""

    assert Shapes.get_class("square") is Square


def test_import_submodules_imports_every_module(tmp_path, monkeypatch):
    package = tmp_path / "toy_items"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "a.py").write_text("LOADED = True\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    import_submodules("toy_items")

    assert sys.modules["toy_items.a"].LOADED


def test_import_tree_imports_nested_modules_but_no_cli_or_main(tmp_path, monkeypatch):
    package = tmp_path / "toy_tree"
    for sub in ("", "shapes", "shapes/items", "cli"):
        (package / sub).mkdir(exist_ok=True)
        (package / sub / "__init__.py").write_text("")
    (package / "shapes" / "square.py").write_text("")
    (package / "shapes" / "items" / "round.py").write_text("")
    (package / "shapes" / "__main__.py").write_text("")
    (package / "cli" / "run.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))

    import_tree("toy_tree")

    assert sorted(name for name in sys.modules if name.startswith("toy_tree")) == [
        "toy_tree",
        "toy_tree.shapes",
        "toy_tree.shapes.items",
        "toy_tree.shapes.items.round",
        "toy_tree.shapes.square",
    ]


def test_every_kind_of_a_config_group_gets_a_generated_file():
    [file] = config_files(ShapeFactory.__module__)

    assert (file.path, file.schema, file.kind, file.package) == (
        "shape/square.yaml",
        SquareConfig,
        "square",
        None,
    )


def test_a_multiple_family_places_each_kind_at_its_own_key(monkeypatch):
    monkeypatch.setattr(ShapeFactory, "multiple", True)
    monkeypatch.setattr(ShapeFactory, "config_group", "eval/shape")

    [file] = config_files(ShapeFactory.__module__)

    assert (file.path, file.package) == ("eval/shape/square.yaml", "eval.shape.square")
