"""Static type-checker proof for the generated typed mirror (ADR-0035, Stage 2).

These functions are never called — they exist so ``uvx ty check src/`` (and any
IDE) verifies the generated classes expose precisely-typed fields a downstream
consumer can read with autocomplete and static checking, NOT a stringly-keyed
generic tree. If a generated class lost a field or mis-typed it, ty would flag
the attribute access below. The runtime counterpart is
``test_card_ir_mirror.test_typed_attribute_access_nested_chain``.

Importing the generated symbols also proves they are real, importable classes /
type aliases (the Stage-2 substitute for the generic ``MirrorNode``).
"""

from __future__ import annotations

from mtg_utils._card_ir.mirror.generated_types import (
    S_abilities,
    S_filter,
    S_Root,
    S_sub_ability,
    T_effect__SearchLibrary,
    U_count,
    U_effect,
    U_filter,
    U_properties,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant, TypedMirrorNode


def read_search_library(effect: T_effect__SearchLibrary) -> object:
    """A SearchLibrary effect's fields are typed, not ``dict`` lookups."""
    count: U_count = effect.count
    do_reveal: bool = effect.reveal
    target: U_filter = effect.filter
    return (count, do_reveal, target)


def read_filter(f: S_filter) -> list[object]:
    """A filter struct exposes a typed ``properties`` list."""
    controller: str = f.controller
    props: list[U_properties] = f.properties
    kinds: list[MirrorVariant] = f.type_filters
    return [controller, props, kinds]


def read_nested_chain(sub: S_sub_ability) -> object:
    """The recursive ``sub_ability`` chain is statically typed end to end."""
    effect: U_effect = sub.effect  # the effect union, ty-narrowable by isinstance
    inner: S_sub_ability | None = sub.sub_ability
    if inner is not None:
        # nested field access is type-checked: inner is S_sub_ability, not dict
        nested_effect: U_effect = inner.effect
        return nested_effect
    return effect


def read_card_root(root: S_Root) -> object:
    """The card record itself is a typed struct with a typed abilities list."""
    abilities: list[S_abilities] = root.abilities
    name: str = root.name
    return (name, abilities)


def consume_base(node: TypedMirrorNode) -> dict:
    """Every generated node is a ``TypedMirrorNode`` with a typed ``to_dict``."""
    return node.to_dict()
