"""The ADR-0038 Unimplemented recovery stage.

Re-decorates ``concept == "other"`` :class:`~mtg_utils._card_ir.crosswalk.
ConceptNode`\\ s whose ``.node`` is phase's ``T_effect__Unimplemented`` via the
shared clause grammar (:func:`~mtg_utils._card_ir.clause_grammar.parse_clause`,
falling back to :func:`~mtg_utils._card_ir.clause_grammar.scan_clause`, falling
back to :func:`~mtg_utils._card_ir.clause_grammar.static_token` for a STATIC
idiom phase's own static parser failed on but still parked in a role=effect
Unimplemented node — Staff of the Ages's "Static pattern matched but line
failed static parser: …" diagnostic wrapper), admitting only allowlisted
tokens (:data:`ALLOWLIST`).

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
from mtg_utils._card_ir.clause_grammar import parse_clause, scan_clause, static_token
from mtg_utils._card_ir.crosswalk import OTHER, ConceptNode, ConceptTree, tag_of
from mtg_utils._card_ir.project import _DICE_TRIG


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
    # evasion-denial idiom (CR 509.1b/702.14): "can be blocked as though
    # it/they didn't have [landwalk/those abilities]" — an anti-evasion
    # static (Staff of the Ages) whose own static parser fails, leaving an
    # Unimplemented parse-failure residue (still role=effect) the typed
    # IgnoreLandwalkForBlocking static read never reaches. Matched via
    # clause_grammar.static_token (the STATIC_TOKENS table), not the
    # imperative-verb grammar.
    "evasion_denial": TokenRule(concept="evasion_denial", category="evasion_denial"),
    # end-the-turn ACTION idiom (CR 724): "(may) end the turn" — expedite
    # the rest of the turn. Obeka's player-scoped grant ("The player whose
    # turn it is may end the turn") leaves an Unimplemented effect phase
    # doesn't structure; the shared grammar's "the player whose turn it is "
    # subject peel + "end the turn" verb tag re-decorates it so the typed
    # effect_concepts("end_the_turn") read sees it directly.
    "end_the_turn": TokenRule(concept="end_the_turn", category="end_the_turn"),
    # roll-a-die ACTION idiom (CR 706): "roll a d20", "roll two d8 and choose
    # one result", "roll the planar die". A spell/cost-form die roll ("the
    # *Endeavor cycle", Six-Sided Die, Danse Macabre's sacrifice-then-roll)
    # leaves the roll itself as an Unimplemented effect phase doesn't
    # structure (the consequence that follows often DOES parse) — the
    # grammar's "roll_die" token re-decorates it so the dice_makers lane's
    # typed effect_concepts("roll_die") read (CR 706) sees it directly.
    "roll_die": TokenRule(concept="roll_die", category="roll_die"),
    # coin-flip idiom (CR 705.1/705.3): "flip a coin" (Molten Sentry's modal
    # ETB flip) / a flip-fixing static ("Two-Headed Coin — the first time
    # you flip ..., those coins come up heads and you win those flips" —
    # Edgar, King of Figaro). Matched via clause_grammar.static_token (the
    # STATIC_TOKENS table, mirroring the OLD-IR ``_COIN`` regex), not the
    # imperative-verb grammar (a flip-fixing static never itself instructs
    # a plain "flip" the way SIMPLE_VERB's other rows do). Maps to the
    # native FlipCoin/FlipCoins tags' own concept ("flip_coin") so the
    # coin_flip lane's ordinary ``effect_concepts("flip_coin")`` read
    # covers the recovered node with no special-case.
    "coin_flip": TokenRule(concept="flip_coin", category="coin_flip"),
    # opponent cast-lock idiom (CR 601.3/604.1): "each opponent can't cast
    # noncreature spells with mana value greater than ..." (Lavinia,
    # Azorius Renegade) -- maps straight to the REAL "stax_taxes" concept
    # so the ordinary stax lane's iter_concepts() read covers the
    # recovered node with no special-casing (ADR-0038: the synth_* marker
    # namespace retires; a recovered node earns its real concept name).
    "stax_cast_lock": TokenRule(concept="stax_taxes", category="restriction"),
    # fight ACTION idiom (CR 701.12): "~ fights up to one target creature"
    # (Gimli, Mournful Avenger's third-resolution rider) / a Saga modal
    # bullet ("Fight! — ~ fights up to one target creature an opponent
    # controls" — Summon: Magus Sisters). Maps to the native Fight tag's
    # own concept ("fight") so the fight_makers lane's ordinary
    # effect_concepts("fight") read covers the recovered node with no
    # special-case.
    "fight": TokenRule(concept="fight", category="fight"),
    # reveal/exile-until-a-condition dig idiom (CR 701.13/701.20a): "reveal
    # cards from the top of your library until you reveal ..." (Mass
    # Polymorph, Synthetic Destiny) / "Reveal cards from the top of your
    # library until you decide to stop" (Push Your Luck) / a
    # replacement-wrapped "instead exile cards from the top of your library
    # until ..." (Unpredictable Cyclone). Maps to the native RevealUntil /
    # ExileFromTopUntil tags' own concept ("reveal_until") so the
    # dig_until lane's ordinary structural arm covers the recovered node
    # with no special-case — the grammar's "your library"-gated match
    # already establishes the digger is YOU (the same direction the typed
    # path's ``reveal_until_player`` reads off the node's own ``player``
    # field), so the lane trusts a recovered node unconditionally (see
    # ``tree_synthesis._arm_dig_until``'s ``c.recovered_by`` branch).
    "dig_until": TokenRule(concept="reveal_until", category="dig_until"),
    # phasing ACTION idiom (CR 702.26a): "phase(s) out" / "phase(s) in" as an
    # imperative instruction (Dream Fighter, Spectral Adversary, The Phasing
    # of Zhalfir) — maps to the native PhaseOut/PhaseIn tags' own concept
    # ("phasing") so the phasing_makers lane's ordinary
    # ``tree.effect_concepts("phasing")`` read covers the recovered node
    # with no special-case.
    "phasing": TokenRule(concept="phasing", category="phasing"),
    # hand-revealed idiom (CR 402.3's disclosure family): "plays with
    # {their/its} hand revealed" (Sen Triplets, Stromgald Spy). Maps to
    # the native RevealHand static mode's own concept ("reveal_hand") so
    # the hand_disruption lane's static arm covers it — the recovered
    # node's own ``.node`` carries no target field to re-check (it is
    # still the phase Unimplemented wrapper), so the lane trusts a
    # recovered node unconditionally via ``recovered_by`` (the STATIC_
    # TOKENS regex's third-person-only gate already establishes the
    # digger is NOT you).
    "hand_revealed": TokenRule(concept="reveal_hand", category="hand_disruption"),
    # ADR-0038 deferral sweep unit 4: the IMPERATIVE "reveal(s) {their/his
    # or her/its} hand" ACTION idiom (Alhammarret, High Arbiter: "each
    # opponent reveals their hand. You choose the name of a nonland card
    # revealed this way." — a two-sentence blob phase parks whole as ONE
    # Unimplemented node, no other residue). Maps to the same
    # "reveal_hand" concept as the STATIC hand_revealed idiom above so the
    # hand_disruption lane's existing ``concept == "reveal_hand"`` arm
    # covers it with no special-case; the recovered node's ``.node``
    # carries no target field of its own to re-check, so the lane trusts
    # a recovered node unconditionally (the grammar's third-person-only
    # gate already establishes the digger is NOT you).
    "reveal_hand": TokenRule(concept="reveal_hand", category="hand_disruption"),
    # ADR-0038 W4 giants (lifeloss_makers): the life-LOSS ACTION idiom (CR
    # 119.3): "[Target player/opponent] loses N life" / "you lose life equal
    # to X" as the clause's OWN main verb — a computed-amount loss ("Target
    # opponent loses 5 life unless..." — Remorseless Punishment; "loses life
    # equal to the difference between..." — Jaws of Defeat; "loses 2 life and
    # you gain 2 life" inside a conditional — Knights of the Black Rose;
    # "loses life equal to the number of creatures attacking them" — Within
    # Range; "loses life equal to the damage already dealt" — Final
    # Punishment) or an "unless"-guarded drain (Remorseless Punishment) leaves
    # the whole clause as an Unimplemented residue phase's own amount-ref
    # grammar can't structure. Distinct from a "lost life this turn"
    # CONDITION reference (Savage Gorger, Rakdos, Lord of Riots) — that shape
    # phase parses into its OWN typed consequence node (PlaceCounter,
    # Surveil, cost-reduction, …) with a condition wrapper, never an
    # Unimplemented residue, so it never reaches this table (verified:
    # ADR-0038 W4 giants corpus check, 0 false hits). Maps to the native
    # LoseLife tag's own concept ("lose_life") so the lane's ordinary
    # ``effect_concepts("lose_life")`` read covers the recovered node with no
    # special-case.
    "lose_life": TokenRule(concept="lose_life", category="lose_life"),
    # ADR-0038 post-giants main-session batch: the token-creation ACTION
    # idiom (CR 701.7 "Create" keyword action; CR 111.2 token ownership;
    # CR 205.3g predefined artifact-token subtypes): "create a red Aura
    # enchantment token named ... attached to that creature" (Smoke
    # Spirits' Aid — the whole for-each-target clause parks as ONE
    # Unimplemented residue; phase's token grammar can't structure the
    # named-Aura-attached shape). The grammar's "create" verb row already
    # discriminates create-a-COPY (the "clone" token, ahead of this row in
    # _VERB order) so a token-copy clause never lands here — the
    # token_copy_makers boundary holds by grammar order. Maps to the
    # native Token tag's own concept ("make_token") so token_maker /
    # enchantments_matter / every make_token-reading lane's ordinary
    # effect_concepts read covers the recovered node with no special-case.
    "make_token": TokenRule(concept="make_token", category="make_token"),
}


def _recover(c: ConceptNode, table: dict[str, TokenRule]) -> ConceptNode | None:
    """Recover one concept-node, or ``None`` if it is not a recovery candidate
    or its grammar token is not in ``table``."""
    if c.concept != OTHER or c.recovered_by or tag_of(c.node) != "Unimplemented":
        return None
    if not c.raw:
        return None
    token = parse_clause(c.raw) or scan_clause(c.raw) or static_token(c.raw)
    if token is None or token not in table:
        return None
    # roll_die's grammar token is a broad "roll(s)" verb match that ALSO
    # matches a die-roll REFERENCE — a replacement's "would roll ...,
    # instead roll ..." modifier (Pixie Guide) or an "after/whenever you
    # roll ..." payoff timing clause (Xenosquirrels) — not an instruction
    # to roll (CR 706's dice_makers DOER). ``_DICE_TRIG`` is the OLD-IR's
    # own doer/payoff discriminator for this exact ambiguity
    # (project._narrow_mechanic_refs's "doer loop" reroutes a matching
    # cat=='roll_die' raw to dice_matters, never dice_makers); reused
    # verbatim so the crosswalk draws the identical line rather than
    # widening a reference-only card into a maker.
    if token == "roll_die" and _DICE_TRIG.search(c.raw):
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

    Scans ``unit.effects`` (role=effect) ONLY — a genuine cost/static
    ConceptNode (``unit.costs`` / ``unit.statics``) is never re-decorated;
    that migrates later, per-key. A STATIC-shaped clause CAN still be
    recovered today when phase parks it in a role=effect Unimplemented node
    (its own static parser having failed — Staff of the Ages), via
    :func:`~mtg_utils._card_ir.clause_grammar.static_token`. Returns the
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
