"""The ADR-0038 Unimplemented recovery stage.

Re-decorates ``concept == "other"`` :class:`~mtg_utils._card_ir.crosswalk.
ConceptNode`\\ s whose ``.node`` is phase's ``T_effect__Unimplemented`` via the
shared clause grammar (:func:`~mtg_utils._card_ir.clause_grammar.parse_clause`,
falling back to :func:`~mtg_utils._card_ir.clause_grammar.scan_clause`),
admitting only allowlisted tokens (:data:`ALLOWLIST`).

Re-decoration keeps the SAME ``.node`` object, so substrate purity (object
identity of phase L1 nodes) holds by construction — this stage only ever
rewrites the overlay's own decoration fields, never the mirror node.

Substrate-wide: wired at the end of ``build_concept_tree``, so signal lanes
AND the compat projection both see recovered readings — ``concept`` for
lanes, the ``category`` override field for compat (``compat._effect_category``
short-circuits on ``cnode.category``).

See ``mtg-utils/CONTEXT.md`` for the **Recovery stage** / **Re-decoration** /
**Token allowlist** glossary entries.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from mtg_utils._card_ir._substrate_purity import assert_substrate_pure, l1_identity
from mtg_utils._card_ir.clause_grammar import parse_clause, scan_clause
from mtg_utils._card_ir.crosswalk import OTHER, ConceptNode, ConceptTree, tag_of


@dataclass(frozen=True)
class TokenRule:
    """One allowlisted grammar token -> the decoration it earns."""

    concept: str  # signal-facing ConceptNode.concept the lanes read
    category: str  # compat-facing old-IR category override
    zones: tuple[str, ...] = ()  # optional zone correction (e.g. reanimate)


# ADR-0038 token allowlist — grows per-key with corpus measurement + pinned
# tests; empty at introduction (behavior-neutral).
ALLOWLIST: dict[str, TokenRule] = {
    # discover ACTION idiom (CR 701.57): "discover N" / "discover again". A
    # re-trigger ("whenever you discover, discover again for the same value"
    # — Curator of Sun's Creation) leaves the inner discover ACTION as an
    # Unimplemented effect phase doesn't structure; the grammar's "discover"
    # token re-decorates it so the typed effect_concepts("discover") read
    # (the discover_makers lane's structural arm) sees it directly.
    "discover": TokenRule(concept="discover", category="discover"),
}


def _recover(c: ConceptNode, table: dict[str, TokenRule]) -> ConceptNode | None:
    """Recover one concept-node, or ``None`` if it is not a recovery candidate
    or its grammar token is not in ``table``."""
    if c.concept != OTHER or c.recovered_by or tag_of(c.node) != "Unimplemented":
        return None
    if not c.raw:
        return None
    token = parse_clause(c.raw) or scan_clause(c.raw)
    if token is None or token not in table:
        return None
    rule = table[token]
    return replace(
        c,
        concept=rule.concept,
        category=rule.category,
        zones=rule.zones or c.zones,
        recovered_by=token,
    )


def apply_unimplemented_recovery(
    tree: ConceptTree, allowlist: dict[str, TokenRule] | None = None
) -> ConceptTree:
    """Re-decorate every recoverable ``other``/``Unimplemented`` node in
    ``tree`` via the shared clause grammar, admitting only ``allowlist``
    tokens (:data:`ALLOWLIST` by default).

    Effects-role ONLY for now — the grammar parses imperative EFFECT clauses;
    static-line recovery (costs/statics) migrates later, per-key. Returns the
    SAME ``tree`` object (identity) when nothing changed (the empty-allowlist
    fast path this commit ships behavior-neutral).
    """
    table = ALLOWLIST if allowlist is None else allowlist
    if not table:
        return tree

    before = l1_identity(tree)
    changed = False
    new_units = []
    for unit in tree.units:
        new_effects = tuple(_recover(c, table) or c for c in unit.effects)
        pairs = zip(new_effects, unit.effects, strict=True)
        if any(new is not old for new, old in pairs):
            changed = True
            new_units.append(replace(unit, effects=new_effects))
        else:
            new_units.append(unit)

    if not changed:
        return tree

    out = replace(tree, units=tuple(new_units))
    assert_substrate_pure(before, out)
    return out


__all__ = ["ALLOWLIST", "TokenRule", "apply_unimplemented_recovery"]
