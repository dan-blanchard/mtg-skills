"""The surviving old-IR ``_recover_*`` FIELD-correction arms + shared anchors.

phase parses *what a card does* into a mechanics-shaped IR, but it only adds a
grammar rule for a mechanic once it implements the *engine* for it, so its parse
coverage is structurally bounded by its engine roadmap and trails the live card
pool. This module was the legacy builder's oracle-text gap-filler for that
Unimplemented tail (a :class:`ClauseRule` registry orchestrated by
``supplement_card``); ADR-0039 step 7 deleted the builder (``project.py``) and,
with it, every arm whose sole consumer was the builder — the registry, the
token-clause grammar, and the whole-clause recovery dispatch included.

What remains is exactly the surviving-consumer surface: the ``_recover_*``
FIELD-correction arms the crosswalk's parallel machinery reuses on the compat
Card (:mod:`dropped_clauses` — the bucket-(c) synthesis stage — and
:mod:`field_corrections` — the bucket-(b) completion seam), plus the shared
anchors/parsers ``_deck_forge._signals_ir``, ``tree_synthesis``, and
``bridge_ledger`` import (the exile-removal exclusions, ``_EACH_PLAYER_P`` /
``_TAP_OPP_CONTROL_P``, ``_BASE_POWER_REF`` / ``_anchored``). Each kept arm's
own docstring still names the phase gap it bridges.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from mtg_utils._card_ir import _combinators as comb

# ADR-0039 step 2: this symbol's DEFINITION lives in text_idioms.py (the
# crosswalk imports it from there too) — imported back here for this module's
# own internal use. See text_idioms.py's docstring.
from mtg_utils._card_ir.text_idioms import _CAST_FROM_EXILE_P
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity, Trigger

# Exclusions read from raw, mirroring the structural arm's predicate/zone/sibling
# gates (which can't fire when the subject/zone is the thing phase dropped):
#  - RETURN → blink/flicker (CR 603.6e / 400.7 — the object returns as a NEW object,
#    not permanent removal — Eldrazi Displacer "exile … then return it");
#  - TIME COUNTER / SUSPEND → impulse/suspend temporary exile (CR 702.62), returns;
#  - from GRAVEYARD / HAND → GY-hate / hand-exile setup, not battlefield removal;
#  - "you own"/"you control" on the TARGET → self-exile / blink-of-own (value, not
#    removal — Cloudshift, Kaya's -2).
_EXILE_REMOVAL_RETURN = re.compile(
    r"\breturn (?:it|that card|those cards|them|the exiled|each)", re.IGNORECASE
)
_EXILE_REMOVAL_SUSPEND = re.compile(r"time counter|\bsuspend\b", re.IGNORECASE)
_EXILE_REMOVAL_FROM_ZONE = re.compile(
    r"from (?:a|your|their|its owner's|each|all)?\s*(?:graveyard|hand)", re.IGNORECASE
)
_EXILE_REMOVAL_SELF_TARGET = re.compile(
    r"target (?:[a-z]+ )*(?:creature|permanent|artifact|enchantment|planeswalker)"
    r" you (?:own|control)",
    re.IGNORECASE,
)


# ── #24e P1 parser-substrate: anchor-then-parse dispatch ──────────────────────
# The bucket-B card-level recoveries below detect with a `_combinators` word-parser
# instead of a regex. A word-combinator costs more per call than a compiled regex
# (it walks the clause word by word), so running it on every card's whole oracle
# would bloat the build. phase avoids this by ANCHORING via a cheap dispatch and
# parsing only the structured part; we mirror that: a fast lowercase-substring gate
# (a NECESSARY lead substring of the parser's match — never a false negative) keeps
# the combinator off the ~99% of cards that cannot match. The combinator stays the
# DETECTOR (whole-word, slot-by-slot); the substring is only the dispatch key.


def _anchored[T](text: str, anchor: str, parser: comb.Parser[T]) -> bool:
    """``anchor in text.lower()`` (cheap dispatch) AND ``parser`` matches (the real
    word-combinator detection). ``anchor`` must be a necessary lead substring of any
    string the parser accepts, so gating never drops a real match."""
    return anchor in text.lower() and parser.run(text) is not None


def _iter_spans(text: str, parser: comb.Parser[Any]) -> Iterator[tuple[str, Any]]:
    """Yield ``(matched_span, value)`` for every NON-overlapping place ``parser``
    matches, left to right — the structural analogue of ``re.finditer`` (advances past
    each match's end, like ``finditer``). ``parser`` anchors at its own lead word."""
    rest = text
    while True:
        r = parser.run(rest)
        if r is not None:
            span = rest[: len(rest) - len(r[1])].strip()
            yield (span, r[0])
            rest = r[1]
            continue
        w = comb.word().run(rest)
        if w is None:
            return
        rest = w[1]


def _scan_span(text: str, parser: comb.Parser[Any]) -> str | None:
    """The first clause-span in ``text`` where ``parser`` matches at a word boundary,
    returned as the matched substring (start-of-anchor → end-of-parser) — the
    structural analogue of ``re.search(...).group(0)`` for recovering a synthetic
    Effect's ``raw``. ``None`` if the parser never matches. ``parser`` should anchor at
    its OWN lead word (it is tried at each successive boundary, like ``scan``)."""
    rest = text
    while True:
        r = parser.run(rest)
        if r is not None:
            return rest[: len(rest) - len(r[1])].strip()
        w = comb.word().run(rest)
        if w is None:
            return None
        rest = w[1]


# ── ADR-0027 base-P/T SET static residue (SIDECAR v45) ────────────────────────
# phase v0.1.60 has a TOTAL blind spot for the layer-7b "set base power and/or
# toughness to a specific value" static (CR 613.4b): ALL 222 commander-legal cards
# whose oracle carries "base power and toughness N/M" / "base power N" / "base
# toughness N" parse to ZERO abilities — Maha, Lignify, Humility, Curse of
# Conformity, Biomass Mutation, Godhead of Awe, Flatline. base_pt_set already fires
# for them off the carved kept word mirror (it scans the raw oracle), but the
# MIGRATED debuff_makers lane reads IR and saw nothing for an opponent / symmetric
# MASS shrink — Maha "Creatures your opponents control have base toughness 1" is a
# -1/-1 enabler (7b sets toughness 1, a 7c -1/-1 then drops it to 0 → dies, CR
# 613.4c / 704.5g). This card-level recovery (the _recover_combat_damage_recipients
# precedent — phase dropped the WHOLE ability, so synthesize from the raw oracle)
# emits the base_pt_set static so the lane reads STRUCTURE, not a regex mirror.
#
# Fires ONLY on a FIXED LITERAL value: the dynamic "change base power to <the
# greatest power among …>" / "base power and toughness X/X" forms (Halfdane, Brine
# Hag, Candlekeep Inspiration) carry no digit after the phrase, so the value regex
# skips them — matching the carved word mirror's fixed-only firing set, so
# base_pt_set stays drift-0. CR 613.4b layer 7b.
# #24e P3 parser-substrate: the base-P/T-SET reads are STRUCTURAL. The VALUE parser
# returns the toughness it sets (int) — or None for a power-only set (amount variable,
# no toughness shrink) — so it doubles as the detector (run is not None) and the
# amount.factor source. Forms, in regex-alternation order: "base power and toughness
# N/M" (toughness = M), "base toughness N" (= N), "base power N" (power-only → None).
_BASE_PT_PAIR_RE = re.compile(r"\d+/\d+")
_BASE_PT_VALUE_P = comb.scan(
    comb.alt(
        comb.seq2(
            comb.phrase({"base"}, {"power"}, {"and"}, {"toughness"}),
            comb.regex_word(_BASE_PT_PAIR_RE),
        ).map(lambda v: int(comb.norm_word(v[1]).split("/")[1])),
        comb.seq2(
            comb.phrase({"base"}, {"toughness"}),
            comb.satisfy(lambda w: w.isdigit()),
        ).map(lambda v: int(comb.norm_word(v[1]))),
        comb.value(
            None,
            comb.seq2(
                comb.phrase({"base"}, {"power"}),
                comb.satisfy(lambda w: w.isdigit()),
            ),
        ),
    )
)
# The SET-EFFECT signature: the value is set by a "have/has/are/is base power…"
# verb. This is the precision gate that keeps a REFERENCE / FILTER out — "creatures
# you control WITH base power and toughness 1/1" (Bess, Zinnia — a tribal count
# condition), "different from ITS base power" (Jason Bright), "with base power OR
# toughness 1" (Sword of the Squeak) all use "with"/"its base", NOT a setting verb,
# so they are not a layer-7b set and must not synthesize one. CR 613.4b vs a mere
# characteristic reference.
_BASE_PT_SET_VERB_P = comb.scan(
    comb.phrase({"have", "has", "are", "is"}, {"base"}, {"power", "toughness"})
)
# The MASS-anthem affected set is a plural "creatures" the clause sets P/T on with
# a "have/has base" verb. A SINGLE-target / aura / equipment / self set ("target
# creature", "enchanted/equipped creature", "this creature") is a neutralize —
# removal, NOT a -1/-1 anthem — so it must NOT be scoped opp/each (the lane
# discriminator wants MASS+low). A "<perms> become … creatures with base …"
# animation (The Antiquities War, Tezzeret — artifacts becoming creatures) is its
# OWN type-animator theme, not a creature anthem, so the "become" verb is excluded
# from the mass arm too.
# The regex anchored `\btarget creature` (no trailing boundary), so "target creatures"
# (a small targeted set — "up to two target creatures each have base …", Will Kenrith,
# Phantasmal Form) read as single/targeted, NOT a go-wide anthem. Mirror that by
# accepting the plural in the noun slot (a true mass anthem says "Creatures you control
# have base …", with no "target"/"enchanted"/"equipped"/"this" qualifier).
_BASE_PT_SINGLE_P = comb.scan(
    comb.alt(
        comb.phrase({"target"}, {"creature", "creatures"}),
        comb.phrase({"enchanted"}, {"creature", "creatures"}),
        comb.phrase({"equipped"}, {"creature", "creatures"}),
        comb.phrase({"this"}, {"creature", "creatures"}),
        comb.phrase({"target"}, {"artifact", "artifacts"}),
        comb.phrase({"enchanted"}, {"artifact", "artifacts"}),
    )
)
_BASE_PT_BECOME_P = comb.scan(
    comb.seq2(
        comb.keyword({"become", "becomes"}),
        comb.bounded_scan(comb.phrase({"base"}, {"power", "toughness"})),
    )
)
# Whose creatures the set affects (read from the value-bearing clause): a PLAIN
# go-wide "creatures you control/own" (controller you — the creatures_matter anthem
# shape the legacy path already fires) vs an opponent set ("your opponents control"
# / an enchanted-player curse / "that player controls" → opp) vs a symmetric
# "all/other/each/non-X creatures" or "creatures target player controls" → each.
# The PLAIN you tell is anchored at the clause START ("[Other/All] creatures you
# control/own …") so a QUALIFIED you set ("Commander creatures you own" — Raised by
# Giants, a narrow commander buff, NOT a go-wide anthem) does NOT read as a generic
# controller-you creatures_matter subject (it falls to the symmetric controller-any
# arm, which fires no lane for a >2 toughness). Head-anchored (not scanned) — the
# regex's `^`.
_BASE_PT_YOU_PLAIN_P = comb.seq2(
    comb.opt(comb.keyword({"other", "all"})),
    comb.phrase({"creatures"}, {"you"}, {"control", "own"}),
)
_BASE_PT_OPP_P = comb.scan(
    comb.alt(
        comb.phrase({"opponent", "opponents"}, {"control"}),
        comb.phrase({"enchanted"}, {"player"}, {"control", "controls"}),
        comb.phrase({"that"}, {"player"}, {"controls"}),
    )
)


def _base_pt_set_fields(clause: str) -> tuple[str, Filter | None, Quantity]:
    """The (scope, subject, amount) of a layer-7b base-P/T set from its raw clause.
    A MASS "creatures … have base …" anthem → a Creature subject (controller you/opp/
    any) + a discriminated scope, so the debuff_makers arm reads the shrink SCOPE
    and the land-animator arms — which key on a LAND subject — stay out; a single-
    target / self / "become" set → subject None + scope "any" (a neutralize is
    removal, not a -1/-1 anthem). The toughness is carried in ``amount.factor`` (the
    death-relevant stat); a power-only set → amount op="variable" (no toughness
    shrink). CR 613.4b. Shared by the per-clause supplement (``_recover_static_
    pattern``) and the card-level empty-IR recovery (``_recover_base_pt_set``)."""
    r = _BASE_PT_VALUE_P.run(clause)
    tough = r[0] if r is not None else None  # int (toughness) or None (power-only)
    amount = (
        Quantity(op="fixed", factor=tough)
        if tough is not None
        else Quantity(op="variable")  # power-only / dynamic — no toughness shrink
    )
    cl = clause.strip()
    is_mass = (
        comb.find_word({"creatures"}).run(cl) is not None
        and _BASE_PT_SINGLE_P.run(cl) is None
        and _BASE_PT_BECOME_P.run(cl) is None
    )
    if not is_mass:
        return "any", None, amount
    if _BASE_PT_OPP_P.run(cl) is not None:
        scope, ctrl = "opp", "opp"
    elif _BASE_PT_YOU_PLAIN_P.run(cl) is not None:
        scope, ctrl = "you", "you"
    else:
        scope, ctrl = "each", "any"
    return scope, Filter(card_types=("Creature",), controller=ctrl), amount


def _recover_base_pt_set(card: Card, oracle: str) -> Card:
    """Append a synthetic ``base_pt_set`` static Effect for the layer-7b set-P/T
    statics phase left wholly unstructured (it drops the whole ability — empty IR).
    Append-only: a face already carrying a base_pt_set Effect is left alone (the
    per-clause supplement or native projection already structured it). One Effect per
    value-bearing clause, fields from ``_base_pt_set_fields``. CR 613.4b."""
    if not card.faces:
        return card
    if any(
        e.category == "base_pt_set" for ab in card.all_abilities() for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    # cheap dispatch — the value + verb both need "base power"/"base toughness".
    if "base power" not in low and "base toughness" not in low:
        return card
    synth: list[Ability] = []
    for clause in re.split(r"[.\n]", text):
        if (
            _BASE_PT_VALUE_P.run(clause) is None
            or _BASE_PT_SET_VERB_P.run(clause) is None
        ):
            continue
        scope, subject, amount = _base_pt_set_fields(clause)
        synth.append(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="base_pt_set",
                        scope=scope,
                        subject=subject,
                        amount=amount,
                        raw=clause.strip(),
                    ),
                ),
            )
        )
    if not synth:
        return card
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, *synth)), *rest),
    )


# ── ADR-0027 #24m F1 — DYNAMIC / QUOTED base-P/T SET residue (SIDECAR v61) ─────
# The `_recover_base_pt_set` pass above is the DEBUFF path: it fires only on a FIXED
# LITERAL "creatures … have/has/are/is base power N" mass shrink (Maha, Humility) and
# scopes opp/each so debuff_makers reads the SHRINK. It deliberately ignores the
# DYNAMIC / quoted / type-conferral SETTERS — phase routes those to animate / clone /
# reanimate / pump / place_counter / emblem / type_set WITHOUT a base_pt_set Effect, so
# the base_pt_set LANE (CR 613.4b layer 7b) leaned wholly on the carved kept word
# mirror for them. This pass re-synthesizes a base_pt_set Effect for the SETTER residue
# the lane needs (scope "any", subject None, amount variable — a build-around set, NOT a
# mass debuff anthem, so it never feeds debuff_makers):
#   • "<perm> becomes a N/N <Type> creature in addition to its other types" the dynamic
#     forms where phase emitted no base_pt_set Effect (Cool Fluffy Loxodon → type_set,
#     Displaced Dinosaurs → type_set, Mindlink Mech → a clone P/T override "it's 4/3 …
#     in addition to its other types"). CR 205.1b + 613.4b.
#   • "has/have base power [and toughness] …" dynamic or quoted (Trench Gorger "base
#     power and base toughness each equal to the lands exiled", Gigantoplasm '"{X}: This
#     creature has base power and toughness X/X"').
#   • "becomes/is a <Type> with base power and toughness N" (Fractalize "with base power
#     and toughness each equal to X plus 1", Goddric "is a Dragon with base power and
#     toughness 4/4", The Master "a green Mutant with base power and toughness 3/3",
#     Tezzeret the Schemer's emblem "becomes an artifact creature with base power and
#     toughness 5/5").
#   • "base power and toughness of each <perms> become …" (Sita Varma).
# It EXCLUDES the base-power REFERENCE grammar "creatures you control WITH base power N"
# (Bess Soul Nourisher, Zinnia, Duskana, Primo, Rapid Augmenter): those merely REFER to
# base P/T (CR 613.4b sentence 2), set nothing, and await a separate base_power_matters
# decision — they stay on the narrowed base_pt_set kept mirror, NOT synthesized here.
# Append-only and gated to bps==0 so the DEBUFF pass (which runs first) owns the mass
# shrinks. The symmetric MASS-animators (Living Plane "All lands are 1/1 creatures",
# March of the Machines "… with power and toughness equal to its mana value", Mycosynth
# Lattice) say neither "base power" nor "N/N … in addition to its other types", so they
# are not matched. Upstream-to-phase candidate (phase should keep the dropped set as a
# base_pt_set node).
# #24e P3 parser-substrate: the 6 DYNAMIC-setter arms read STRUCTURE. A digit-leading
# word (`_DIGIT_LEAD`: "3", "1/1", "4/4,") stands in for the regex `\d`; `_PT_PAIR_W`
# is the `\b\d+/\d+\b` word. `[^.]*` gaps become `bounded_scan` (clause-bounded). Arm 6
# keys on bare "become" (not "becomes"); arms 4/5 on "become(s) a/an". Ports to phase-rs
# as a nom alt of tuples.
_DIGIT_LEAD = comb.satisfy(lambda w: bool(w) and w[0].isdigit())
_PT_PAIR_W = comb.regex_word(_BASE_PT_PAIR_RE)
_DYN_BASE_PT_SET_P = comb.alt(
    comb.scan(comb.phrase({"has", "have"}, {"base"}, {"power", "toughness"})),
    comb.scan(
        comb.seq3(
            comb.phrase({"base"}, {"power"}),
            comb.opt(comb.phrase({"and"}, {"toughness"})),
            _DIGIT_LEAD,
        )
    ),
    comb.scan(comb.seq2(comb.phrase({"base"}, {"toughness"}), _DIGIT_LEAD)),
    comb.scan(
        comb.seq3(
            comb.keyword({"become", "becomes"}),
            comb.keyword({"a", "an"}),
            comb.bounded_scan(comb.phrase({"with"}, {"base"}, {"power", "toughness"})),
        )
    ),
    comb.scan(
        comb.seq2(
            comb.seq2(comb.keyword({"become", "becomes"}), comb.keyword({"a", "an"})),
            comb.seq2(
                comb.bounded_scan(_PT_PAIR_W),
                comb.bounded_scan(
                    comb.phrase(
                        {"in"}, {"addition"}, {"to"}, {"its"}, {"other"}, {"types"}
                    )
                ),
            ),
        )
    ),
    comb.scan(
        comb.seq2(
            comb.phrase({"base"}, {"power", "toughness"}),
            comb.bounded_scan(comb.keyword({"become"})),
        )
    ),
)
# The REFERENCE grammar: "creature(s) you control WITH base power N" — a noun qualifier,
# not a set. Excluded so the references stay on the narrowed mirror (await
# base_power_matters), not synthesized into the SETTER lane.
_REF_BASE_PT_P = comb.scan(
    comb.phrase(
        {"creature", "creatures"},
        {"you"},
        {"control", "own"},
        {"with"},
        {"base"},
        {"power", "toughness"},
    )
)


def _recover_dynamic_base_pt_set(card: Card, oracle: str) -> Card:
    """Append a synthetic ``base_pt_set`` static Effect for the DYNAMIC / quoted /
    type-conferral base-P/T SETTERS phase folded into a sibling category (animate /
    clone / reanimate / pump / place_counter / emblem / type_set) without a base_pt_set
    node. Append-only and gated to bps==0 (the DEBUFF ``_recover_base_pt_set`` pass owns
    the mass shrinks and runs first). One Effect per non-reference SETTER clause; scope
    "any", subject None, amount variable so it feeds the base_pt_set LANE but never the
    debuff_makers mass-shrink read. CR 613.4b layer 7b."""
    if not card.faces:
        return card
    if any(
        e.category == "base_pt_set" for ab in card.all_abilities() for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    # cheap dispatch — every arm needs "base power"/"base toughness" or the
    # type-conferral tail "in addition to its other types".
    if not (
        "base power" in low
        or "base toughness" in low
        or "in addition to its other types" in low
    ):
        return card
    synth: list[Ability] = []
    for clause in re.split(r"[.\n]", text):
        if _DYN_BASE_PT_SET_P.run(clause) is None:
            continue
        if _REF_BASE_PT_P.run(clause) is not None:
            continue
        synth.append(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="base_pt_set",
                        scope="any",
                        subject=None,
                        amount=Quantity(op="variable"),
                        raw=clause.strip(),
                    ),
                ),
            )
        )
    if not synth:
        return card
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, *synth)), *rest),
    )


# ── ADR-0027 C10 — DROPPED gain_life residue (SIDECAR v50) ────────────────────
# phase sometimes emits NO gain_life Effect though the raw oracle plainly says YOU
# gain life: a multi-clause / symmetric fold (Game of Chaos "you gain 1 life and
# target opponent loses 1 life" → only coin_flip + lose_life(opp), the gain is
# dropped) or a dynamic "gain life equal to X" the engine didn't model. The gainer
# survives only in the raw, so this card-level pass — the _recover_base_pt_set /
# _recover_combat_damage_recipients precedent (phase dropped the structure, so
# synthesize it from the joined oracle) — emits a gain_life Effect (scope you) so
# the EXISTING gain_life signals arm fires lifegain_matters STRUCTURALLY, retiring
# the deleted regex's gain-act arm from the kept mirror. CR 119.3. Upstream-to-phase
# candidate (phase should keep the dropped gain clause).
#
# Append-only and gated to a YOU gainer: a card already carrying ANY gain_life
# Effect (phase structured at least one gain clause) is untouched — the lane needs
# only one, so a second dropped clause is moot. The patterns are the YOU-anchored
# gain phrasings the deleted ARM-A regex matched ("you gain N/X life", "gain life
# equal to", "you gain that much life"); an opponent/each gainer ("target opponent
# gains 3 life") is NOT synthesized here (that gain_life rides phase's own scope-any
# node + the existing arm, not a forced scope-you marker).
# #24e P2 parser-substrate: DETECTION is a per-clause `_combinators` scan over three
# arms (the deleted YOU-anchored regex):
#   A: you gain <N|X> life   (value slot = satisfy(isdigit-or-x); folds multi-digit)
#   B: gain life equal to
#   C: you gain that much life
# WHOLE-WORD ("life" never matches inside "lifelink"). Ports to phase-rs as
# `alt((tuple((tag("you"), tag("gain"), digit, tag("life"))), ...))`. CR 119.3.
_GAIN_LIFE_VALUE = comb.satisfy(lambda w: w.isdigit() or w == "x")
_GAIN_LIFE_DROPPED = comb.scan(
    comb.alt(
        comb.value(
            None,
            comb.seq3(
                comb.keyword({"you"}),
                comb.keyword({"gain"}),
                comb.seq2(_GAIN_LIFE_VALUE, comb.keyword({"life"})),
            ),
        ),
        comb.value(None, comb.phrase({"gain"}, {"life"}, {"equal"}, {"to"})),
        comb.value(None, comb.phrase({"you"}, {"gain"}, {"that"}, {"much"}, {"life"})),
    )
)


def _recover_dropped_gain_life(card: Card, oracle: str) -> Card:
    """Append a synthetic ``gain_life`` Effect (scope you) for the gain-life clauses
    phase dropped (no gain_life node though the raw says you gain life). Append-only:
    a card already carrying a gain_life Effect is left alone. One Effect per
    value-bearing clause. CR 119.3."""
    if not card.faces:
        return card
    # Skip only when a gain_life the signals arm WOULD read (scope you/any) already
    # exists — NOT a gain_life phase mis-scoped to 'opp'. phase's third-party
    # possessive heuristic flips "You gain life equal to the cards in target
    # opponent's hand" (Gerrard Capashen, Search Warrant, Daxos, Froghemoth) to
    # scope='opp' because the COUNT references an opponent, though the GAINER is you.
    # Those never fire the you/any arm, so the synth must still run. CR 119.3.
    if any(
        e.category == "gain_life" and e.scope in ("you", "any")
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    synth: list[Ability] = []
    for clause in re.split(r"[.\n]", text):
        if _anchored(clause, "gain", _GAIN_LIFE_DROPPED):
            synth.append(
                Ability(
                    kind="static",
                    effects=(
                        Effect(
                            category="gain_life",
                            scope="you",
                            raw=clause.strip(),
                        ),
                    ),
                )
            )
    if not synth:
        return card
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, *synth)), *rest),
    )


# ── ADR-0027 #24 — GRANTED damage-reflection residue (SIDECAR v52) ─────────────
# phase has no first-class node for a damage-REFLECTION ability granted to (or
# quoted onto) a CLASS of creatures: 'Sliver creatures you control have "Whenever
# this creature is dealt damage, it deals that much damage to target player or
# planeswalker."' (Spiteful Sliver) parses to a `board_grant` carrying the whole
# quoted reflection in its raw, plus a split-off `damage` static — NOT a
# damage_reflect Effect. The damage_reflect signals arm reads a `damage_reflect`
# CATEGORY marker (the conferred-keyword read) and an on-card damage_received
# trigger; neither fires for the GRANTED form (board_grant is not a grant carrier
# and there is no card-level trigger), so the lane saw nothing — the previously
# dead `cat=='damage_reflect'` IR read becomes load-bearing here. This card-level
# pass — the _recover_base_pt_set / _recover_combat_damage_recipients precedent
# (phase dropped the structure, so synthesize it from the joined oracle) — emits a
# damage_reflect Effect so the lane reads STRUCTURE. CR 120.3 / 119.3.
#
# Anchored TIGHTLY on the reflection signature (the same two anchors the project-
# side _narrow_conferred_keyword_refs grant-carrier marker uses): a "whenever ~ is
# dealt damage" TRIGGER + a "deals that much damage" CONSEQUENCE (the reflection
# mirrors the received amount — not "deals N damage to it", a source dealing its
# own damage). Both required so a mere "if dealt damage this way" side-effect
# (Marauding Raptor) never fires.
#
# Append-only and gated to the GRANTED form: skip a card already carrying a
# damage_reflect Effect, and skip an ON-CARD reflector (a damage_received trigger
# with a damage effect — Boros Reckoner, Stuffy Doll), which the signals arm reads
# off the trigger. The granted/quoted reflectors phase leaves wholly unstructured
# (Spiteful Sliver's tribal grant, Arcbond's targeted grant, Donna Noble's
# paired-subject trigger phase couldn't model) carry neither, so they recover here.
# #24e P2 parser-substrate: both required anchors are `_combinators`:
#   TRIG: "whenever … is dealt damage" — the bounded `[^.""]*?` gap is honored by
#         splitting the text on period / quote chars and running, per segment,
#         `preceded(find_word({"whenever"}), scan(phrase("is","dealt","damage")))`
#         (whenever BEFORE is-dealt-damage, within one no-period-no-quote run).
#   DEALS: `scan(phrase("deals","that","much","damage"))` over the whole text.
# WHOLE-WORD throughout. Ports to phase-rs as a nom `tuple` inside a sentence-bounded
# `take_until('.')`. CR 120.3.
_DAMAGE_REFLECT_TRIG = comb.preceded(
    comb.find_word({"whenever"}),
    comb.scan(comb.phrase({"is"}, {"dealt"}, {"damage"})),
)
_DAMAGE_REFLECT_DEALS = comb.scan(
    comb.phrase({"deals"}, {"that"}, {"much"}, {"damage"})
)


def _has_damage_reflect_grant(text: str) -> bool:
    """The GRANTED damage-reflection tell: a "whenever … is dealt damage" trigger (in a
    no-period-no-quote run) AND a "deals that much damage" consequence somewhere in the
    text. Mirrors the two deleted regexes; the trigger's sentence/quote bound is the
    per-segment split."""
    if "dealt damage" not in text.lower() or "that much damage" not in text.lower():
        return False
    segments = re.split(r"[.\"“”]", text)
    if not any(_DAMAGE_REFLECT_TRIG.run(seg) is not None for seg in segments):
        return False
    return _DAMAGE_REFLECT_DEALS.run(text) is not None


def _recover_damage_reflect(card: Card, oracle: str) -> Card:
    """Append a synthetic ``damage_reflect`` static Effect for the GRANTED/quoted
    damage-reflection abilities phase leaves wholly unstructured (a `board_grant`
    raw, a targeted grant, or a compound-subject trigger phase couldn't model).
    Append-only: a card already carrying a damage_reflect Effect, or an on-card
    reflector (a damage_received trigger + a damage effect the signals arm reads
    directly), is left alone. CR 120.3."""
    if not card.faces:
        return card
    if any(
        e.category == "damage_reflect"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    if any(
        ab.trigger is not None
        and ab.trigger.event == "damage_received"
        and any(e.category == "damage" for e in ab.effects)
        for ab in card.all_abilities()
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if not _has_damage_reflect_grant(text):
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="damage_reflect", scope="you", raw=text.strip()),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24 — OPPONENT cast-lock restriction residue (SIDECAR v52) ────────
# phase drops the "your opponents can't cast spells [during your turn/combat]"
# player-restriction static WHOLLY for a body that has no other modelled ability
# (Dragonlord Dromoka parses to ZERO abilities; Tidal Barracuda, Voice of Victory,
# Kutzil, Marisi, Myrel, Conqueror's Flail, Narset Transcendent's emblem all drop
# it too). The migrated stax arm reads a `restriction` Effect scope='opp' →
# stax_taxes (CR 601.3: an effect prohibits opponents from casting — a hard lock,
# CR 604.1 static). With no Effect the arm saw nothing, so the lane fired only off
# the broad `\bopponents? can't\b` residue byte-mirror. This card-level pass — the
# _recover_base_pt_set precedent (phase dropped the WHOLE ability, so synthesize it
# from the joined oracle) — emits the restriction Effect so the stax arm reads
# STRUCTURE, and the residue mirror's opponent-cast branch is narrowed to defer to
# it (see _STAX_TAXES_RESIDUE_RE's `(?! cast)` guard). CR 601.3 / 604.1.
#
# Scope is unambiguously 'opp' (the OPPONENTS form only — "your/each opponent(s)
# can't cast"). The SYMMETRIC "players can't cast" locks (Grafdigger's Cage,
# Basandra) and the messier "that/defending player can't cast" forms are left to
# the residue mirror: their scope is 'each' (symmetric_stax) or situational, and
# folding them here would risk the symmetric/opp split. Append-only and gated to a
# body phase left WITHOUT any restriction Effect (the 21 cleanly-structured
# opponent cast-locks — Grand Abolisher, Drannith Magistrate, Azor — already fire
# the structural arm and are untouched).
# #24e P1 parser-substrate: DETECTION is a `_combinators` clause scan
# (``scan(phrase({"opponent","opponents"}, {"cant"}, {"cast"}))``) — the three
# consecutive words "opponent(s) can't cast" ("can't" normalizes to "cant"). Behavior-
# neutral with the deleted `\bopponents? can't cast\b` mirror; ports to phase-rs as a
# nom `tuple((alt((tag("opponents"), tag("opponent"))), tag("can't"), tag("cast")))`.
_OPP_CAST_LOCK = comb.scan(comb.phrase({"opponent", "opponents"}, {"cant"}, {"cast"}))


def _recover_opponent_cast_lock(card: Card, oracle: str) -> Card:
    """Append a synthetic ``restriction`` static Effect (scope opp) for the
    "your opponents can't cast spells" player-lock phase drops wholly. Append-only
    and gated: a card already carrying ANY restriction Effect (phase structured the
    lock, or a sibling restriction) is left alone. One Effect for the card. CR
    601.3 / 604.1."""
    if not card.faces:
        return card
    if any(
        e.category == "restriction" for ab in card.all_abilities() for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    clause = next(
        (
            cl.strip()
            for cl in re.split(r"[.\n]", text)
            if _anchored(cl, "can't cast", _OPP_CAST_LOCK)
        ),
        None,
    )
    if clause is None:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="restriction", scope="opp", raw=clause),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24c — SELF dies-return residue (SIDECAR v53) ─────────────────────
# The aristocrats/reanimator CORE mechanic "When this dies, return it to the
# battlefield" — phase flattens the granted/quoted form to a place_counter / pump
# effect (Feign Death → place_counter(p1p1); Abnormal Endurance → pump) and DROPS the
# reanimate, and the body-borne form (Bronzehide Lion, Ashcloud Phoenix) parses as a
# dies-trigger + reanimate that would over-broaden if read directly (a dies-triggered
# reanimate of OTHERS is NOT self-recursion). The undying/persist keyword BEARERS ride
# _IR_KEYWORD_MAP and the keyword-LESS GRANTERS ride the `undying_persist` marker; this
# pass covers the third class — the literal self dies-return clause — by synthesizing a
# dedicated `self_recursion` marker Effect ONLY dies_recursion reads (zero collateral
# into death_matters / graveyard_matters / reanimate lanes). The patterns mirror the
# deleted DIES_RECURSION_REGEX's two non-keyword arms EXACTLY (self-return + the
# would-die-instead-exile-with-counters delayed return — Darigaaz Reincarnated), run
# over the joined oracle, so the recovered set is byte-identical sans the keyword arm
# (now structural). CR 700.4 (dies = battlefield→graveyard) / 603.6c.
# #24e P3 parser-substrate: the two non-keyword DIES_RECURSION arms read STRUCTURE.
# Arm A — "when ~ dies, return it to the battlefield": `when` anchor, a bounded-gap
# scan over the creature description (no period crossed), then the fixed return phrase
# (the pronoun bag covers it/her/him/them). `keyword({when})` matches ONLY "when", not
# "whenever" (norm keeps them distinct), mirroring the regex's `when ` space-anchor.
# Arm B — "if ~ would die, instead exile it with N counters" (Darigaaz Reincarnated's
# delayed return): `if` anchor, bounded-gap to the fixed "would die instead exile it
# with" phrase, then a second bounded gap to the `counter(s)` word. Both `[^.]*` gaps
# become `bounded_scan` (clause-bounded). Ports to phase-rs as two nom tuples.
_DIES_RETURN_ARM_A = comb.seq2(
    comb.keyword({"when"}),
    comb.bounded_scan(
        comb.phrase(
            {"dies"},
            {"return"},
            {"it", "her", "him", "them"},
            {"to"},
            {"the"},
            {"battlefield"},
        )
    ),
)
_DIES_RETURN_ARM_B = comb.seq2(
    comb.keyword({"if"}),
    comb.bounded_scan(
        comb.seq2(
            comb.phrase({"would"}, {"die"}, {"instead"}, {"exile"}, {"it"}, {"with"}),
            comb.bounded_scan(comb.keyword({"counter", "counters"})),
        )
    ),
)


# ── v0.8.0 bump regression-recovery ROOT A (SIDECAR 66, no bump) ──────────────
# phase v0.8.0 collapses a "Whenever <event>, ... (return|exile) THIS card from your
# graveyard ..." TRIGGERED graveyard-recursion ability (the Recover template, CR
# 702.59a) into a CONTENTLESS spell-kind ability — it strips BOTH the trigger AND the
# in:graveyard zone, emitting a bare `bounce` Effect (raw="", zones=()). Two losses:
# (1) the lane that EXCLUDES graveyard-recursion bounces (bounce_tempo guards on
# `not any("graveyard" in z)`) now LEAKS these as if they were battlefield→hand tempo
# bounces — A Good Day to Pie, Punishing Fire, Unlawful Entry, Spit Flame, Sosuke's
# Summons, Killian's Confidence, Vivi's Persistence, Reach of Branches, Unconventional
# Tactics are all "return this card from YOUR GRAVEYARD" (CR 400.7 graveyard→hand zone
# change), NOT a tempo bounce of an opponent's permanent; (2) the tribal-ETB recursion
# trigger ("Whenever a <subtype> you control enters" — Snake/Dragon/Zombie) and the
# scry-recursion trigger ("Whenever you scry" — Council's Deliberation) vanish, so
# tribal_etb_multi / scry_surveil_matters drop a real member. This card-level pass
# re-bridges the structure v0.8.0 drops — the proven #24 supplement precedent
# (_recover_dies_return / _recover_combat_damage_recipients): it stamps in:graveyard
# back onto the contentless recursion bounce (re-arming the bounce_tempo graveyard
# guard → the 9 over-fires drop) and, when the recursion's "Whenever" condition is a
# creature-subtype ETB or a scry, rebuilds that Trigger onto the ability so the tribal/
# scry payoff lanes read STRUCTURE again. Decoy Gambit ("return that creature to its
# owner's hand", a battlefield→hand opponent-creature tempo bounce) carries a NON-empty
# bounce raw and NO graveyard mention, so it is untouched and correctly stays in
# bounce_tempo. CR 702.59a / 400.7 / 603.
_GY_RECUR_MARK = re.compile(
    r"\b(?:return|exile) this card from your graveyard\b", re.IGNORECASE
)
_GY_RECUR_WHENEVER = re.compile(r"\bwhenever\b", re.IGNORECASE)
# "a [nontoken] <Subtype> you control enters [the battlefield]" — the tribal-ETB head.
_GY_RECUR_TRIBAL_ETB = re.compile(
    r"\b(?:a|an|another) (?:nontoken )?([A-Za-z]+) you control enters\b",
    re.IGNORECASE,
)
_GY_RECUR_SCRY = re.compile(r"\byou scry\b", re.IGNORECASE)


def _gy_recursion_trigger(oracle: str) -> Trigger | None:
    """Reconstruct the Trigger v0.8.0 dropped from a graveyard-recursion ability, or
    None when the "Whenever" condition is neither a creature-subtype ETB nor a scry
    (a sticker / opp-lifegain / commander-ETB / combat-damage condition needs no
    rebuilt trigger — the in:graveyard zone stamp alone excludes its bounce)."""
    mark = _GY_RECUR_MARK.search(oracle)
    if mark is None:
        return None
    head = oracle[: mark.start()]
    whenevers = list(_GY_RECUR_WHENEVER.finditer(head))
    if not whenevers:
        return None
    cond = oracle[whenevers[-1].end() : mark.start()].split(",", 1)[0]
    etb = _GY_RECUR_TRIBAL_ETB.search(cond)
    if etb is not None:
        sub = etb.group(1).capitalize()
        return Trigger(
            event="etb",
            subject=Filter(subtypes=(sub,), controller="you"),
            scope="you",
        )
    if _GY_RECUR_SCRY.search(cond):
        return Trigger(event="scried", scope="you")
    return None


def _is_gy_recursion_bounce(e: Effect) -> bool:
    """A CONTENTLESS bounce v0.8.0 left from a collapsed GY-recursion trigger — empty
    raw / zones / counter_kind / subject. The empty raw is the discriminator vs a real
    tempo bounce (which carries its clause), so a card with BOTH a real bounce and a
    Recover clause keeps the real bounce in bounce_tempo."""
    return (
        e.category == "bounce"
        and not e.raw
        and not e.zones
        and not e.counter_kind
        and e.subject is None
    )


def _is_gy_recursion_exile(e: Effect) -> bool:
    """The exile-from-graveyard form of a collapsed GY-recursion trigger (Council's
    Deliberation "exile this card from your graveyard. If you do, draw a card"). phase
    keeps the from:graveyard zone but DROPS the trigger; the empty raw marks it as the
    collapsed-trigger half (vs a real exile-removal clause, which carries its raw)."""
    return e.category == "exile" and not e.raw and "from:graveyard" in e.zones


def _is_gy_recursion_ability(ab: Ability) -> bool:
    """An ability holding a collapsed GY-recursion effect — either the contentless
    bounce or the exile-from-graveyard form. NOT gated on kind/trigger: the
    createdelayedtrigger trigger-lift (project._lift_delayed_trigger) now projects the
    etb/lifegain recursion ability as kind='triggered', but the contentless SelfRef
    Bounce still carries no origin zone (node-absent), so this pass must still stamp
    in:graveyard onto it regardless of whether the trigger was lifted natively. The
    card-level _GY_RECUR_MARK oracle gate in _recover_gy_recursion already restricts
    this to genuine 'return/exile this card from your graveyard' cards."""
    return any(
        _is_gy_recursion_bounce(e) or _is_gy_recursion_exile(e) for e in ab.effects
    )


def _recover_gy_recursion(card: Card, oracle: str) -> Card:
    """Re-bridge the v0.8.0 GY-recursion regression (ROOT A): stamp in:graveyard onto
    the contentless recursion bounce (so bounce_tempo's graveyard guard excludes it)
    and rebuild the dropped creature-subtype-ETB / scry Trigger so tribal_etb_multi /
    scry_surveil_matters fire. Gated to cards whose oracle carries the literal
    "(return|exile) this card from your graveyard"; idempotent (a contentless recursion
    bounce already carrying a graveyard zone is left alone). CR 702.59a / 400.7."""
    if not card.faces or not _GY_RECUR_MARK.search(oracle):
        return card
    trig = _gy_recursion_trigger(oracle)
    changed = False
    attached = False
    new_faces: list[Face] = []
    for face in card.faces:
        new_abilities: list[Ability] = []
        for ab in face.abilities:
            if not _is_gy_recursion_ability(ab):
                new_abilities.append(ab)
                continue
            changed = True
            effects = tuple(
                replace(e, zones=("in:graveyard",)) if _is_gy_recursion_bounce(e) else e
                for e in ab.effects
            )
            # rebuild the dropped trigger onto the FIRST recursion ability only
            # (each target card has exactly one recursion clause). Skip when the
            # ability already carries a trigger — project._lift_delayed_trigger now
            # projects the etb/lifegain recursion trigger natively, so the recovery
            # only backstops the still-node-absent in:graveyard zone stamp (else
            # branch) and the regex-only scry trigger (mode:Unknown, ab.trigger None).
            if trig is not None and not attached and ab.trigger is None:
                new_abilities.append(
                    replace(ab, kind="triggered", trigger=trig, effects=effects)
                )
                attached = True
            else:
                new_abilities.append(replace(ab, effects=effects))
        new_faces.append(replace(face, abilities=tuple(new_abilities)))
    if not changed:
        return card
    return replace(card, faces=tuple(new_faces))


def _recover_dies_return(card: Card, oracle: str) -> Card:
    """Append a synthetic `self_recursion` static marker Effect when the joined
    oracle carries the literal self dies-return (or would-die-instead-exile-with-
    counters) clause, so dies_recursion reads STRUCTURE. Append-only and idempotent
    (skip a card already carrying the marker)."""
    if not card.faces:
        return card
    if any(
        e.category == "self_recursion"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    span: str | None = None
    # cheap necessary-substring dispatch per arm (the combinator stays the detector).
    if "battlefield" in low:
        span = _scan_span(text, _DIES_RETURN_ARM_A)
    if span is None and "exile it with" in low:
        span = _scan_span(text, _DIES_RETURN_ARM_B)
    if span is None:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="self_recursion", scope="you", raw=span),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24c — +1/+1 / -1/-1 counter REMOVAL-as-cost residue (SIDECAR v53) ─
# counter_manipulation reads a counter_move / remove_counter Effect of kind p1p1/m1m1
# (the structured MOVE + remove-as-effect halves). The remaining mirror tail is the
# counter REMOVAL phase leaves OUTSIDE an effect: as an activation COST (phase emits
# the `removecounter` cost token but DROPS the counter kind — Triskelion, Walking
# Ballista, Quillspike, Spike Weaver) and as a damage-prevention REPLACEMENT (Phantom
# Centaur / Flock / Nantuko, Oathsworn Knight — "prevent that damage … remove a +1/+1
# counter"). phase keeps neither as a remove_counter Effect, so the kind survives only
# in raw. This pass recovers the dropped KIND (the audit's named upstream gap) by
# synthesizing a remove_counter Effect with counter_kind=p1p1/m1m1 from the raw
# removal clause — the existing counter_manipulation arm then reads STRUCTURE. Gated to
# skip a card already carrying a p1p1/m1m1 counter_move/remove_counter (the structured
# MOVE/effect cards are untouched); the kind gate keeps a charge/oil/loyalty cost-side
# removal (Coretapper, Surge Node) OUT. CR 122.1 / 122.6.
# #24e P3 parser-substrate: the +1/+1-vs--1/-1 counter-removal detector reads STRUCTURE
# with the new SIGN-PRESERVING `signed_word` (`norm_word` folds both to "1/1", losing
# the kind the lane needs). Shape mirrors `(?:remove|move) <qty> [gap] (+1/+1|-1/-1)
# counter(s)`: verb anchor + a quantity (a|one|x|N|"any number of") + a bounded gap to
# the signed token + the `counter(s)` word. The value threaded out is the signed form,
# mapped p1p1/m1m1 by the caller. Ports to phase-rs as a nom tuple with a sign-tag.
_COUNTER_REMOVE_QTY = comb.alt(
    comb.phrase({"any"}, {"number"}, {"of"}),
    comb.satisfy(lambda w: w in {"a", "one", "x"} or w.isdigit()),
)
# The gap is bounded by ``:`` too (not just sentence delims): a ``Remove a charge
# counter from ~: Put a -1/-1 counter`` activation removes a charge/quest counter as a
# COST and puts the signed counter in the EFFECT — the signed token after the colon is
# a different clause and must not be read as the removed kind (Trigon of Corruption,
# Quest for the Gemblades, The Duke). The regex's 20-char cap blocked these by accident;
# the colon is the STRUCTURAL boundary (cost ``:`` effect, CR 602.1).
_COUNTER_REMOVE_P = comb.seq2(
    comb.seq2(comb.keyword({"remove", "move"}), _COUNTER_REMOVE_QTY),
    comb.bounded_scan(
        comb.seq2(
            comb.signed_word({"+1/+1", "-1/-1"}),
            comb.keyword({"counter", "counters"}),
        ),
        delims='.;:"“”',
    ),
).map(lambda v: v[1][0])


def _recover_counter_removal(card: Card, oracle: str) -> Card:
    """Append a synthetic remove_counter Effect (counter_kind p1p1/m1m1) for a
    +1/+1 or -1/-1 counter removal phase left as an activation cost / damage-
    prevention replacement (kind dropped). Append-only; skip a card already carrying
    a p1p1/m1m1 counter_move/remove_counter (structured) Effect. CR 122.1."""
    if not card.faces:
        return card
    if any(
        e.category in ("counter_move", "remove_counter")
        and e.counter_kind in ("p1p1", "m1m1")
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    # cheap dispatch: a removal verb AND a signed counter token must both be present.
    if ("remove" not in low and "move" not in low) or (
        "+1/+1" not in text and "-1/-1" not in text
    ):
        return card
    rest = text
    sign: str | None = None
    span = ""
    while True:
        r = _COUNTER_REMOVE_P.run(rest)
        if r is not None:
            sign = r[0]
            span = rest[: len(rest) - len(r[1])].strip()
            break
        w = comb.word().run(rest)
        if w is None:
            break
        rest = w[1]
    if sign is None:
        return card
    kind = "p1p1" if sign == "+1/+1" else "m1m1"
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="remove_counter",
                scope="you",
                counter_kind=kind,
                raw=span,
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24b SUPPLEMENT_RECOVER batch B1 (SIDECAR v54) ───────────────────
# Five lanes phase PARSES but whose zone / count / devotion operand it DROPS, today
# carried by a signals-side regex mirror. Each recovery below RECOVERS the dropped
# structure from the joined oracle (the recovery seam) onto the IR — the
# ``_recover_base_pt_set`` / ``_recover_combat_damage_recipients`` precedent (phase
# dropped the structure, synthesize it) — so the migrated lane reads STRUCTURE and
# the mirror is deleted. Where phase DID leave usable partial structure (a
# leaves/dies Land-subject trigger, an ``in:exile`` count operand, a
# ``cast_from_zone`` Effect), the signals arm reads it directly and the supplement
# only fills the residue; where phase scattered the operand across many effect
# categories (lands_matter's land count, devotion's collapsed ``op``) the
# supplement appends ONE inert marker carrying the recovered operand rather than
# mutating the overloaded ``amount`` of each (which cascades into pump_makers /
# ramp that read ``amount.op``). All append-only / idempotent.

# lands_matter — DEFERRED (mirror kept): phase's card-data.json omits the AFTERMATH
# back face entirely (Road // Ruin projects only "Road"; "Ruin deals damage … equal
# to the number of lands you control" is absent from the IR), so a supplement that
# reads the records oracle cannot recover that real member — deleting the mirror
# would silently drop it. The count operand also scatters across 12+ effect
# categories (characteristic_pt P/T scalers, pump_target, make_token, tutor,
# place_counter, cost_reduction) and a few cost/restriction bodies with no effect
# raw, so a clean structural read awaits a phase aftermath-face fix. CR 305.

# devotion_matters — phase preserves Quantity.op=='devotion' on SOME effects (Gray
# Merchant, the Theros gods) but COLLAPSES it to op=='variable' on a devotion-scaled
# ramp (Nyx Lotus, Karametra's Acolyte, Nykthos) and DROPS it on a devotion pump /
# characteristic_pt (Aspect of Hydra, Daxos). Re-stamping the op in place would
# cascade (ramp reads op=='variable' for its accel split, pump_makers reads
# op=='fixed'); instead append ONE inert devotion marker so the devotion_matters arm
# reads op=='devotion' without disturbing those neighbors. Gated to a card not
# already carrying a devotion operand. CR 700 (devotion).
#
# #24e P1 parser-substrate: DETECTION is a `_combinators` clause scan
# (``scan(seq3(keyword({"devotion"}), keyword({"to"}), word()))``) — "devotion to
# <color>" read as three consecutive words, the trailing ``word()`` enforcing the
# `\w`-after-"to" the regex required. Behavior-neutral with the deleted `devotion to
# \w` mirror; ports to phase-rs as a nom `tuple((tag("devotion"), tag("to"), word))`.
_DEVOTION_TO_COLOR = comb.scan(
    comb.seq3(comb.keyword({"devotion"}), comb.keyword({"to"}), comb.word())
)


def _recover_devotion_operand(card: Card, oracle: str) -> Card:
    """Append a synthetic devotion marker (op='devotion') for the devotion operand
    phase collapses to op='variable' (ramp) or drops (pump / characteristic_pt), so
    the devotion_matters arm reads it structurally without re-stamping the overloaded
    ``amount.op`` of the real ramp/pump effect (which ramp / pump_makers
    read). Append-only; skipped when an op=='devotion' operand already exists."""
    if not card.faces:
        return card
    if any(
        e.amount is not None and e.amount.op == "devotion"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    m = _DEVOTION_TO_COLOR.run(text) if "devotion to" in text.lower() else None
    if m is None:
        return card
    raw = " ".join(m[0])  # the matched "devotion to <color>" words (inert marker raw)
    synth = Ability(
        kind="static",
        effects=(Effect(category="other", amount=Quantity(op="devotion"), raw=raw),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


def _recover_cast_from_exile_zone(card: Card, oracle: str) -> Card:
    """Stamp ``from:exile`` onto the ``cast_from_zone`` Effect and ``cast_spell``
    Trigger phase leaves zones=() (Eternal Scourge, Misthollow, Squee, Vega), and
    synthesize a from:exile marker for the exile-and-cast engines phase leaves with
    neither, so the cast_from_exile lane reads the cast-from zone structurally.
    Idempotent; gated to the cast-from-exile oracle. CR 601.3b."""
    if not card.faces:
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    low = stripped.lower()
    # cheap dispatch: every arm needs one of these substrings (combinator detects).
    if not ("exile" in low or "plot" in low or "anywhere other than your hand" in low):
        return card
    if _CAST_FROM_EXILE_P.run(stripped) is None:
        return card
    stamped = False
    new_faces = []
    for face in card.faces:
        new_abs = []
        for ab in face.abilities:
            trig = ab.trigger
            if (
                trig is not None
                and trig.event == "cast_spell"
                and "from:exile" not in trig.zones
            ):
                trig = replace(trig, zones=(*trig.zones, "from:exile"))
                stamped = True
            effs = []
            for e in ab.effects:
                new_e = e
                if e.category == "cast_from_zone" and "from:exile" not in e.zones:
                    new_e = replace(e, zones=(*e.zones, "from:exile"))
                    stamped = True
                effs.append(new_e)
            new_abs.append(replace(ab, trigger=trig, effects=tuple(effs)))
        new_faces.append(replace(face, abilities=tuple(new_abs)))
    card = replace(card, faces=tuple(new_faces))
    if stamped:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="other", zones=("from:exile",), raw=""),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# exile_matters — the EXILE-ZONE-AS-RESOURCE lane. phase SCATTERS the reference: it
# tags ``in:exile`` on a count operand (Ulamog place_counter) and ``exile`` on a
# Condition (Ketramose) — those the signals arm reads directly — but DROPS the zone
# off a ``characteristic_pt`` P/T scaler ("cards you own in exile" — Cosmogoyf,
# Crackling Drake) and an "exiled with ~" persistent-pile payoff (Gorex). Stamp
# ``in:exile`` onto the standing-in-exile effects phase left zoneless; synthesize a
# marker for the oracle-only residue. Distinct from exile_removal (``to:exile``).
# CR 406.
# #24e P2 parser-substrate: the CARD-LEVEL standing-in-exile gate is a `_combinators`
# scan over two opt()-bearing arms (the deleted regex's two alternations) — a showcase
# of opt() for the "(you own )?(that are )?"/"(you own )?(in )?" optional slots:
#   A: cards [you own]? [that are]? in exile*
#   B: for each card [you own]? [in]? exile*
# The terminal slot matches the WHOLE word with the "exile" PREFIX (exile/exiled/exiles)
# because the deleted regex's bare "exile" matched the "card exiled this way" / "cards
# exiled" PAYOFFS by substring (the prefix of "exiled") — those are real exile_matters
# members (Gorex, Lumbering Battlement, Crypt Incursion, the March cost-reducers), so
# the gate must keep them; the per-effect ``_EXILE_STANDING_CLAUSE_RE`` (`card(s)
# exiled` / `exiled with`) is the structural stamp the gate guards. Set-equal to the
# deleted regex. Ports to phase-rs as nom `alt((..., ...))` with `opt`. CR 406.
_EXILE_WORD = comb.satisfy(lambda w: w.startswith("exile"))
_EXILE_STANDING = comb.scan(
    comb.alt(
        comb.value(
            None,
            comb.preceded(
                comb.keyword({"card", "cards"}),
                comb.preceded(
                    comb.opt(comb.seq2(comb.keyword({"you"}), comb.keyword({"own"}))),
                    comb.preceded(
                        comb.opt(
                            comb.seq2(comb.keyword({"that"}), comb.keyword({"are"}))
                        ),
                        comb.seq2(comb.keyword({"in"}), _EXILE_WORD),
                    ),
                ),
            ),
        ),
        comb.value(
            None,
            comb.preceded(
                comb.seq3(
                    comb.keyword({"for"}),
                    comb.keyword({"each"}),
                    comb.keyword({"card"}),
                ),
                comb.preceded(
                    comb.opt(comb.seq2(comb.keyword({"you"}), comb.keyword({"own"}))),
                    comb.preceded(comb.opt(comb.keyword({"in"})), _EXILE_WORD),
                ),
            ),
        ),
    )
)
# Per-effect anchor (the clause references cards STANDING in exile, not exiling TO
# exile) — used to pick which zoneless effect carries the in:exile tag.
_EXILE_STANDING_CLAUSE_RE = re.compile(
    r"\bin exile\b|exiled with\b|\bcard exiled\b|\bcards exiled\b", re.IGNORECASE
)


def _recover_exile_zone_ref(card: Card, oracle: str) -> Card:
    """Stamp ``in:exile`` onto the standing-in-exile effects phase leaves zoneless (a
    ``characteristic_pt`` P/T scaler — Cosmogoyf; an "exiled with ~" pile payoff —
    Gorex), and synthesize an in:exile marker for the oracle-only residue, so the
    exile_matters arm reads the zone structurally (additive to the ``in:exile`` count
    operand / ``exile`` Condition phase already structures). Idempotent; gated to the
    standing-in-exile oracle. CR 406."""
    if not card.faces:
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "exile", _EXILE_STANDING):
        return card
    has_zone = any(
        "in:exile" in e.zones for ab in card.all_abilities() for e in ab.effects
    )
    stamped = False
    new_faces = []
    for face in card.faces:
        new_abs = []
        for ab in face.abilities:
            effs = []
            for e in ab.effects:
                new_e = e
                if (
                    "in:exile" not in e.zones
                    and "to:exile" not in e.zones
                    and _EXILE_STANDING_CLAUSE_RE.search(e.raw or "")
                ):
                    new_e = replace(e, zones=(*e.zones, "in:exile"))
                    stamped = True
                effs.append(new_e)
            new_abs.append(replace(ab, effects=tuple(effs)))
        new_faces.append(replace(face, abilities=tuple(new_abs)))
    card = replace(card, faces=tuple(new_faces))
    if stamped or has_zone:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="other", zones=("in:exile",), raw=""),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# land_sacrifice_matters — phase emits real structure for most of the lane: the
# land-to-graveyard PAYOFF is a leaves/dies Trigger whose subject is a Land you
# control (Slogurk leaves subj=Land; Titania dies subj=Land) — the signals arm reads
# it directly. The sac OUTLET (Zuran Orb "Sacrifice a land:") is an activated
# Ability whose cost projects to a bare 'sacrifice' token, DROPPING the sacrificed
# Land type into the raw. Synthesize a ``sacrifice`` Effect with a Land-you subject
# for the cost-sac (and any "whenever you sacrifice a land" / "unless you sacrifice a
# land" body phase leaves unstructured) so the lane reads the sacrificed-permanent
# type structurally. A Land-ONLY sacrifice subject is already excluded from
# sacrifice_outlets (CR 701.16), so it stays this lane's own signal.
# #24e P3 parser-substrate: the land-sacrifice detector reads STRUCTURE. Arm 1 keys on
# the cost separator `:` glued to "land"/"land card" (`_word_with_colon`, since norm
# strips the colon). `[^.]*` gaps → `bounded_scan`. Quantity bag (a|one or more|another)
# is shared by arms 2-3. Detection-only.
_LAND_SAC_QTY = comb.alt(
    comb.phrase({"one"}, {"or"}, {"more"}), comb.keyword({"a", "another"})
)


def _word_with_colon(bag: set[str]) -> comb.Parser[str]:
    """Match a word whose normalized form is in ``bag`` AND whose RAW form carries a
    cost-separator ``:`` (which ``norm_word`` strips) — "Sacrifice a land:" / "land
    card:". The colon distinguishes a sacrifice COST from a mere "sacrifice a land"
    body verb, so it must not be folded away. CR 602.1 / 118.3."""

    def go(s: str) -> tuple[str, str] | None:
        r = comb.word().run(s)
        if r is None or comb.norm_word(r[0]) not in bag or ":" not in r[0]:
            return None
        return (comb.norm_word(r[0]), r[1])

    return comb.Parser(go)


_LAND_SACRIFICE_P = comb.alt(
    comb.seq(
        comb.phrase({"sacrifice"}, {"a"}),
        comb.alt(
            _word_with_colon({"land"}),
            comb.seq(comb.keyword({"land"}), _word_with_colon({"card"})),
        ),
    ),
    comb.seq(
        comb.keyword({"whenever"}),
        _LAND_SAC_QTY,
        comb.keyword({"land", "lands"}),
        comb.opt(comb.keyword({"card", "cards"})),
        comb.bounded_scan(comb.phrase({"put"}, {"into"})),
        comb.bounded_scan(comb.keyword({"graveyard"})),
    ),
    comb.seq(
        comb.keyword({"whenever"}),
        comb.keyword({"you"}),
        comb.keyword({"sacrifice"}),
        _LAND_SAC_QTY,
        comb.keyword({"land", "lands"}),
    ),
    comb.phrase({"unless"}, {"you"}, {"sacrifice"}, {"a"}, {"land"}),
)


def _land_sac_trigger_present(card: Card) -> bool:
    """A leaves/dies Trigger whose subject is a Land you control — the structured
    land-to-graveyard payoff the signals arm reads directly (Slogurk, Titania)."""
    return any(
        ab.trigger is not None
        and ab.trigger.event in ("leaves", "dies")
        and ab.trigger.subject is not None
        and "Land" in ab.trigger.subject.card_types
        and ab.trigger.subject.controller == "you"
        for ab in card.all_abilities()
    )


def _land_sac_effect_present(card: Card) -> bool:
    """A YOUR-side land-sacrifice Effect the signals arm already reads (scope not
    each/opp — a symmetric "each player sacrifices a land" does NOT count, so a card
    whose only structured land-sac is symmetric still gets the you-side cost synth —
    Mana Vortex's "counter it unless you sacrifice a land")."""
    return any(
        e.category == "sacrifice"
        and e.subject is not None
        and e.subject.card_types == ("Land",)
        and e.scope not in ("each", "opp")
        for ab in card.all_abilities()
        for e in ab.effects
    )


def _recover_land_sacrifice(card: Card, oracle: str) -> Card:
    """Append a synthetic ``sacrifice`` Effect (subject Land you control) for the
    land sac-OUTLET cost / "whenever you sacrifice a land" / "unless you sacrifice a
    land" bodies phase leaves with the sacrificed Land type only in raw, so the
    land_sacrifice_matters arm reads the sacrificed-permanent type structurally. The
    leaves/dies Land-subject payoff trigger is already structured — no synth for it.
    Append-only; skipped when a land-sac trigger or effect already exists. CR
    701.16."""
    if not card.faces:
        return card
    if _land_sac_trigger_present(card) or _land_sac_effect_present(card):
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    if "land" not in stripped.lower():  # cheap dispatch — every arm names a land.
        return card
    span = _scan_span(stripped, _LAND_SACRIFICE_P)
    if span is None:
        return card
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="sacrifice",
                scope="you",
                subject=Filter(card_types=("Land",), controller="you"),
                raw=span,
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# ── ADR-0027 #24d — cost-REDUCTION residue (SIDECAR v55) ──────────────────────
# phase emits NO cat=="cost_reduction" Effect for a large class of genuine build-
# around reducers — it carries only the static ModifyCost{Reduce} (a spell-class
# discount) and the named `reducenextspellcost` effect, and DROPS WHOLLY:
#   • ability-cost reducers ("Activated abilities of creatures you control cost {2}
#     less to activate" — Agatha, Biomancer's Familiar, Power Artifact; Boast/Equip
#     ability-cost reducers — Dragonkin Berserker, Fervent Champion),
#   • conditional spell reducers ("Those spells cost {G} less to cast" — the Defiler
#     cycle),
#   • donor reducers ("spells that player casts cost {2} less" — Will Kenrith),
#   • named special-cost reducers ("Blitz/Flashback costs you pay cost {N} less" —
#     Henzie, Catalyst Stone), and
#   • granted/quoted reducers ("Spells you cast cost {1} less" on a created token —
#     Tamiyo, Compleated Sage's Notebook).
# These are all CR 601.2f cost reductions (an effect that reduces the total cost to
# cast a spell / activate an ability) the cost_reduction signals arm needs. This
# card-level pass — the _recover_base_pt_set / _recover_opponent_cast_lock precedent
# (phase dropped the WHOLE clause, so synthesize the Effect from the raw oracle) —
# emits one cost_reduction static Effect (subject None, the matched reducer clause as
# raw) so the EXISTING arm reads STRUCTURE and the kept _COST_REDUCER_MIRROR retires.
# CR 601.2f / 118.7.
#
# The arms are the SIX the (already-narrowed, not byte-identical) signals mirror
# carried — each requires a "cost(s) … less" reduction of OTHER spells/abilities and
# structurally excludes "this spell costs" (self-discount) and "… more"/"an
# additional" (increase), so the synthesized raw passes the arm's subject-None screen
# (_COST_SELF_DISCOUNT / _COST_LESS_REDUCER / _COST_INCREASE) and the recovered set is
# exactly the mirror's. Append-only and gated to a body phase left WITHOUT any
# cost_reduction Effect (the 211 cleanly-structured reducers already fire the arm).
# #24e P3 parser-substrate: the six cost-reducer arms read STRUCTURE. A mana token is
# a word whose RAW carries `{…}` (`_MANA_BRACED`, where braces are required) or whose
# NORM is a bare mana run (`_MANA_AMOUNT`, optional braces — norm strips them). `[^.]`
# char-gaps → `bounded_scan` (clause-bounded; the recover runs per period-split clause,
# so the char caps and the clause are near-coextensive). Arm C's `(?<!this )` lookbehind
# is a custom scan that skips a "spell" preceded by "this".
_MANA_BRACE_RE = re.compile(r"\{[wubrgcx0-9]+\}", re.IGNORECASE)
_MANA_RUN_RE = re.compile(r"[wubrgcx0-9]+", re.IGNORECASE)
_MANA_BRACED = comb.Parser(
    lambda s: (
        r
        if (r := comb.word().run(s)) is not None and _MANA_BRACE_RE.match(r[0])
        else None
    )
)
_MANA_AMOUNT = comb.satisfy(lambda w: bool(_MANA_RUN_RE.fullmatch(w)))
_CR_LESS_TO_CAST = comb.phrase({"less"}, {"to"}, {"cast"})


def _cr_arm_c() -> comb.Parser[object]:
    """Arm C: a spell CLASS you cast made cheaper — the regex's `(?<!this )` lookbehind
    becomes a scan that skips a "spell(s)" preceded by "this" (a self-discount), then
    parses "… you cast … cost <amount> … less to cast"."""
    # The "cost <amount>" is one bounded_scan UNIT so it backtracks past a false "cost"
    # lead (Zimone: "… with {X} in its mana cost each turn costs {1} less …" — the first
    # "cost" carries no mana amount; the regex backtracked to "costs {1}", so must we).
    rest = comb.seq(
        comb.bounded_scan(comb.phrase({"you"}, {"cast"})),
        comb.bounded_scan(comb.seq2(comb.keyword({"cost", "costs"}), _MANA_AMOUNT)),
        comb.bounded_scan(_CR_LESS_TO_CAST),
    )

    def go(s: str) -> tuple[object, str] | None:
        prev = None
        cur = s
        while True:
            w = comb.word().run(cur)
            if w is None:
                return None
            nw = comb.norm_word(w[0])
            if nw in {"spell", "spells"} and prev != "this":
                r = rest.run(w[1])
                if r is not None:
                    return r
            prev = nw
            cur = w[1]

    return comb.Parser(go)


_COST_REDUCTION_RECOVER_P = comb.alt(
    # A. ability-cost reducers: "<class of> abilities … cost {N} less to activate".
    comb.scan(
        comb.seq(
            comb.keyword({"abilities"}),
            comb.bounded_scan(comb.keyword({"cost"})),
            comb.bounded_scan(comb.keyword({"less"})),
            comb.bounded_scan(comb.phrase({"to"}, {"activate"})),
        )
    ),
    # B. conditional spell reducer: "those spells cost {C} less" (the Defiler cycle).
    comb.scan(
        comb.seq(
            comb.phrase({"those"}, {"spells"}, {"cost"}),
            _MANA_BRACED,
            comb.bounded_scan(_CR_LESS_TO_CAST),
        )
    ),
    # C. a spell CLASS (NOT "this spell") you cast made cheaper.
    _cr_arm_c(),
    # D. a donor reducer: "spells <a player> casts cost {N} less" (Will Kenrith).
    comb.scan(
        comb.seq(
            comb.keyword({"spells"}),
            comb.alt(
                comb.phrase({"that"}, {"player"}),
                comb.phrase({"those"}, {"players"}),
                comb.phrase({"that"}, {"opponent"}),
                comb.phrase({"each"}, {"player"}),
            ),
            comb.bounded_scan(
                comb.seq(
                    comb.keyword({"cast", "casts"}),
                    comb.keyword({"cost"}),
                    _MANA_BRACED,
                )
            ),
            comb.bounded_scan(_CR_LESS_TO_CAST),
        )
    ),
    # E. a named special cost: "Blitz/Flashback costs you pay cost {N} less".
    comb.scan(
        comb.seq(
            comb.keyword(
                {"blitz", "cycling", "kicker", "flashback", "escape", "ninjutsu"}
            ),
            comb.keyword({"costs"}),
            comb.bounded_scan(comb.seq2(comb.keyword({"cost"}), _MANA_BRACED)),
            comb.bounded_scan(comb.keyword({"less"})),
        )
    ),
    # F. a granted/property-filtered spell class made cheaper, no "you cast".
    comb.scan(
        comb.seq(
            comb.phrase({"spells"}, {"with"}),
            comb.bounded_scan(comb.seq2(comb.keyword({"cost"}), _MANA_AMOUNT)),
            comb.bounded_scan(_CR_LESS_TO_CAST),
        )
    ),
)
# The arm's subject-None screen (mirrored here so the gate skips only a card that
# already FIRES the cost_reduction arm, not one phase left a cost_reduction Effect on
# that the screen rejects — Invasion of the Giants' chapter-III reducer collapses to a
# raw "Chapter 3" Effect that fails the screen, so it must still recover). CR 601.2f.
# The `[^."]` gaps mirror onto bounded_scan with delims='."' (period + double-quote
# only — commas/semicolons are allowed inside the regex char class).
_COST_RED_SELF_P = comb.scan(
    comb.alt(
        comb.phrase({"this"}, {"spell"}, {"costs"}),
        comb.phrase({"this"}, {"ability"}, {"costs"}),
        comb.phrase({"this"}, {"costs"}),
    )
)
_COST_RED_LESS_P = comb.scan(
    comb.seq2(
        comb.keyword({"cost", "costs"}),
        comb.bounded_scan(comb.keyword({"less"}), delims='."'),
    )
)
_COST_RED_MORE_P = comb.alt(
    comb.scan(
        comb.seq2(
            comb.keyword({"cost", "costs"}),
            comb.bounded_scan(
                comb.alt(comb.keyword({"more"}), comb.phrase({"an"}, {"additional"})),
                delims='."',
            ),
        )
    ),
    comb.scan(comb.phrase({"would"}, {"cost"}, {"less"}, {"than"})),
)


def _cost_reduction_fires(e: Effect) -> bool:
    """True iff this cost_reduction Effect would fire the signals arm (a non-None
    subject is trusted; a subject-None effect must carry a genuine "cost(s) … less"
    reduction that is neither a self-discount nor a cost-increase). CR 601.2f."""
    if e.category != "cost_reduction":
        return False
    if e.subject is not None:
        return True
    raw = e.raw or ""
    return (
        _COST_RED_LESS_P.run(raw) is not None
        and _COST_RED_SELF_P.run(raw) is None
        and _COST_RED_MORE_P.run(raw) is None
    )


def _recover_cost_reduction(card: Card, oracle: str) -> Card:
    """Append a synthetic ``cost_reduction`` static Effect (subject None, scope you)
    for the build-around cost reducers phase drops wholly (ability-cost reducers, the
    Defiler conditional, donor / named-special / granted reducers). Append-only and
    gated: a card already carrying a cost_reduction Effect that FIRES the arm (see
    _cost_reduction_fires) is left alone — but a Saga-chapter collapse ("Chapter 3"
    raw) that does not is still recovered. One Effect per card, raw = the first
    matching reducer clause (so the arm's subject-None screen sees a genuine reducer,
    not the whole oracle). CR 601.2f / 118.7."""
    if not card.faces:
        return card
    if any(_cost_reduction_fires(e) for ab in card.all_abilities() for e in ab.effects):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "less" not in text.lower():  # cheap dispatch — every reducer arm needs "less".
        return card
    clause = next(
        (
            cl.strip()
            for cl in re.split(r"[.\n]", text)
            if _COST_REDUCTION_RECOVER_P.run(cl) is not None
        ),
        None,
    )
    if clause is None:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="cost_reduction", scope="you", raw=clause),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24d — CREATURE-copy clone residue (SIDECAR v55) ──────────────────
# phase folds the optional ETB-copy replacement "you may have this creature enter as
# a copy of any creature" (and "becomes a copy of that/target creature") into a
# `choose` / empty node — emitting NO cat=="clone" Effect — for a class of genuine
# CREATURE copies (Spark Double, Stunt Double, Mockingbird, Chameleon Master of
# Disguise, Vesuvan Shapeshifter, Progenitor Mimic, The Mimeoplasm, Essence of the
# Wild, Permeating Mass, Moritte of the Frost). The clone_makers arm reads the COPIED
# type off a `clone` Effect's subject (creature copy → clone_makers; CR 707.2 — the
# copy acquires the original's card type), so a dropped clone Effect = a silent miss.
# This card-level pass — the _recover_base_pt_set precedent (phase dropped the WHOLE
# Effect, so synthesize it from the raw oracle) — emits a `clone` Effect with a
# Creature (or Permanent, for a "copy of a permanent" changeling) subject so the arm
# reads STRUCTURE and the kept CLONE_MATTERS_REGEX mirror retires. CR 707.1 / 707.2.
#
# Append-only and gated to a body phase left WITHOUT any clone Effect: a card phase
# DID structure a copy on (Copy Artifact / Copy Land / Mycosynth Gardens / Thespian's
# Stage — a clone Effect with an Artifact/Land/Enchantment subject) is left alone, so
# the NON-creature copies correctly fire their per-type copy lane (copy_artifact /
# copy_land / copy_enchantment) and drop clone_makers — the over-broad mirror's
# creature-blind firing is the over-fire being shed (CR 707.2: a copy of an artifact
# is an artifact copy, not a creature copy). The veto on a TOKEN-copy ("create a token
# that's a copy" — Mirror Match) rides the existing arm, not here.
# #24e P3 parser-substrate: the creature-copy detector reads STRUCTURE. `[^.\"“”]` gaps
# → bounded_scan with delims='.\"“”' (period + quotes only — the regex allows commas /
# semicolons). `\bcreature` (no trailing boundary) → {creature, creatures}. Arm 5's
# `(?!…\b)` negative lookahead → `_clone_not_next` (a zero-width assert that the next
# word is not an explicit non-creature card type). The copy-of-a-permanent arm doubles
# as the Permanent-subject discriminator. CR 707.1 / 707.2.
_CLONE_DELIMS = '."“”'
_CLONE_CREATURE_W = comb.keyword({"creature", "creatures"})


def _clone_not_next(bag: set[str]) -> comb.Parser[None]:
    """Zero-width negative lookahead (nom ``not``): succeed (consuming nothing) iff the
    NEXT word's normalized form is not in ``bag`` — the regex `(?!(?:…)\\b)`."""

    def go(s: str) -> tuple[None, str] | None:
        w = comb.word().run(s)
        if w is not None and comb.norm_word(w[0]) in bag:
            return None
        return (None, s)

    return comb.Parser(go)


_CLONE_COPY_PERMANENT_P = comb.scan(
    comb.seq(
        comb.phrase({"copy"}, {"of"}),
        comb.opt(comb.keyword({"a", "an", "any", "another", "target", "that"})),
        comb.keyword({"permanent"}),
    )
)
_CLONE_CREATURE_COPY_P = comb.scan(
    comb.alt(
        # "as a copy of … creature".
        comb.seq(
            comb.phrase({"as"}, {"a"}, {"copy"}, {"of"}),
            comb.bounded_scan(_CLONE_CREATURE_W, delims=_CLONE_DELIMS),
        ),
        # "copy of <det> … creature".
        comb.seq(
            comb.phrase({"copy"}, {"of"}),
            comb.keyword({"a", "an", "any", "another", "target", "that", "this"}),
            comb.bounded_scan(_CLONE_CREATURE_W, delims=_CLONE_DELIMS),
        ),
        # "copy of <det?> permanent".
        comb.seq(
            comb.phrase({"copy"}, {"of"}),
            comb.opt(comb.keyword({"a", "an", "any", "another", "target", "that"})),
            comb.keyword({"permanent"}),
        ),
        # "creatures you control enter as a copy".
        comb.phrase(
            {"creatures"}, {"you"}, {"control"}, {"enter"}, {"as"}, {"a"}, {"copy"}
        ),
        # "enter(s) [the battlefield] as | become(s)" a copy of <det?> … card(s).
        comb.seq(
            comb.alt(
                comb.seq(
                    comb.keyword({"enter", "enters"}),
                    comb.opt(comb.phrase({"the"}, {"battlefield"})),
                    comb.keyword({"as"}),
                ),
                comb.keyword({"become", "becomes"}),
            ),
            comb.phrase({"a"}, {"copy"}, {"of"}),
            comb.opt(
                comb.alt(
                    comb.phrase({"one"}, {"of"}, {"those"}),
                    comb.keyword({"a", "an", "the", "that", "any"}),
                )
            ),
            _clone_not_next(
                {
                    "artifact",
                    "land",
                    "enchantment",
                    "instant",
                    "sorcery",
                    "planeswalker",
                }
            ),
            comb.bounded_scan(comb.keyword({"card", "cards"}), delims=_CLONE_DELIMS),
        ),
    )
)


def _recover_clone_creature(card: Card, oracle: str) -> Card:
    """Append a synthetic ``clone`` Effect (Creature subject, or Permanent for a
    "copy of a permanent" changeling) for the creature-copy replacements phase folds
    to a non-clone node. Append-only and gated: a card already carrying ANY clone
    Effect (phase structured the copy — including the non-creature Copy Artifact / Copy
    Land family) is left alone, so only the genuinely-dropped creature copies recover
    and the non-creature copies keep their per-type lane. CR 707.1 / 707.2."""
    if not card.faces:
        return card
    # Skip only when phase ALREADY structured a CREATURE/PERMANENT copy (the
    # clone_makers arm fires off Creature/Permanent in the copied subject). A clone
    # Effect typed to a non-creature permanent (the Copy Artifact / Copy Land family —
    # Artifact/Land/Enchantment subject) does NOT fire clone_makers, so it must still
    # run the creature-copy check: Dermotaxi copies a CREATURE card but phase types its
    # subject "Artifact" (from the "Vehicle artifact" rider), so the gate would skip a
    # creature copy. The creature-copy regex then no-ops on a true non-creature copy
    # ("copy of any artifact") and recovers Dermotaxi's "copy of the exiled [creature]
    # card". An EMPTY-subject clone (Essence of the Wild, Permeating Mass) also runs.
    if any(
        e.category == "clone"
        and e.subject is not None
        and bool({"Creature", "Permanent"} & set(e.subject.card_types))
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "copy" not in text.lower():  # cheap dispatch — every arm needs "copy".
        return card
    if _CLONE_CREATURE_COPY_P.run(text) is None:
        return card
    copied = (
        Filter(card_types=("Permanent",))
        if _CLONE_COPY_PERMANENT_P.run(text) is not None
        else Filter(card_types=("Creature",))
    )
    synth = Ability(
        kind="static",
        effects=(
            Effect(category="clone", scope="any", subject=copied, raw=text.strip()),
        ),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24d — OPPONENT-directed discard residue (SIDECAR v55) ────────────
# phase structures a forced discard as a `discard` Effect but DROPS the discardER
# scope to 'any' whenever the discarding player is ANAPHORIC — "that player discards"
# referring to a structurally-identified opponent it can't resolve. The disconnected
# pieces survive in the IR:
#   A. a damage-CONNECT specter: a combat_damage / deals_damage trigger whose
#      recipient is a PLAYER (recipient=('player',) or a DamageToPlayer subject
#      predicate) + a `discard` Effect on the SAME ability ("whenever ~ deals combat
#      damage to a player, that player discards" — Abyssal/Hypnotic Specter, Chilling
#      Apparition, Cabal Slaver, Larceny, Sword of Feast and Famine). The damaged
#      player is the discardER → an opponent. CR 510.1c.
#   B. a ParentTarget bounce/counter-then-discard: a `bounce` or `counter_spell`
#      Effect preceding the discard in the same ability ("Return target permanent …,
#      then that player discards" — Recoil, Dinrova Horror; "Counter target spell …
#      that player discards" — Frightful Delusion, Compelling Deterrence). The
#      target's controller is the discardER → an opponent. CR 701.9.
#   C. a reveal-hand-then-discard: a `reveal_hand` / `reveal` Effect scoped to an
#      opponent preceding the discard ("Look at target opponent's hand … that player
#      discards" — Mind Warp, Extortion, Collective Brutality, Thrull Surgeon). CR
#      701.9 / 701.18.
#   D. an each/target-OPPONENT discard the raw names but phase scoped 'any' ("each
#      opponent discards" — Words of Waste, Bite of the Black Rose, Bladecoil Serpent).
# For each, append a sibling `discard` Effect scope='opp' so the EXISTING opponent_
# discard arm (which reads a `discard` Effect scope opp/each or subject.controller==
# opp) fires STRUCTURALLY. Append-only and gated to a body phase left WITHOUT an
# opp/each-directed discard (the cleanly-structured forced-opponent discards — Mind
# Rot, Stupor, Dark Deal — already fire the arm). The genuinely-unstructurable tail
# phase leaves no anchor for — "whenever a player discards" PAYOFFS (Confessor, Spirit
# Cairn), the "discarded a card this turn" past-tense payoff (Tinybones), would-draw
# REPLACEMENTS (Chains of Mephistopheles), and granted/quoted grants (Wand of Ith,
# Dementia Sliver) — keeps the NARROWED residue mirror (the spec's upstream-phase gap).
# CR 701.9 / 510.1c / 102.2.
# #24e P2 parser-substrate: the each/target/an-opponent discardER raw tell is a
# `_combinators` scan — `scan(phrase({each/target/an}, {opponent}, {discards}))` —
# WHOLE-WORD ("discards" only, mirroring the deleted regex's no-`?`). Ports to phase-rs
# as nom `tuple((alt(det tags), tag("opponent"), tag("discards")))`. CR 701.9.
_OPP_DISCARD_RAW = comb.scan(
    comb.phrase({"each", "target", "an"}, {"opponent"}, {"discards"})
)


def _opp_discard_raw(text: str) -> bool:
    """``each/target/an opponent discards`` anywhere in ``text`` (whole-word)."""
    return "discards" in text.lower() and _OPP_DISCARD_RAW.run(text) is not None


# The OPPONENT-directed discardER tell — the disconnected discard piece's own text
# names the discarding player as an anaphoric opponent ("that player/opponent
# discards", "its controller discards", "each/target opponent discards"). This is the
# discriminator that keeps the damage-CONNECT specter ("that player discards") IN and
# the combat-damage SELF-LOOT ("you may draw a card, then discard a card" — Looter
# il-Kor, Academy Raider, Wharf Infiltrator) OUT: a self-loot's discard names YOU, not
# "that player", so it never fires the anchor. CR 701.9 vs the loot outlet (CR 701.8a).
# #24e P2 parser-substrate: the OPPONENT-directed discardER tell is a `_combinators`
# scan over four arms (the deleted regex's four alternations) — WHOLE-WORD, so a
# past-tense "that player discarded" (the regex matched "that player discard" as a
# substring of "discarded") is NOT a discard tell here (Tinybones-style past-tense
# payoffs stay on the narrowed residue mirror, per this module's design). `discards?`
# → {discard, discards}. CR 701.9.
_DISCARD_OPP_DIRECTED = comb.scan(
    comb.alt(
        comb.phrase({"that"}, {"player", "opponent"}, {"discard", "discards"}),
        comb.phrase({"its"}, {"controller"}, {"discard", "discards"}),
        comb.phrase({"each", "target", "an"}, {"opponent"}, {"discard", "discards"}),
        comb.phrase({"each"}, {"player"}, {"discard", "discards"}),
    )
)


def _directed_discard(text: str) -> bool:
    """An opponent-directed discardER tell anywhere in ``text`` (whole-word)."""
    return "discard" in text.lower() and _DISCARD_OPP_DIRECTED.run(text) is not None


def _opp_discard_anchor(ab: Ability, card_text: str) -> bool:
    """True iff this ability carries an OPPONENT-directed discard (its own text names
    an anaphoric opponent discardER — NOT a self-loot) whose discarding player is a
    structurally-identified opponent: a damage-to-player trigger, a prior bounce/
    counter target, a prior reveal-opponent-hand, or an each/target-opponent raw. CR
    701.9."""
    tr = ab.trigger
    dmg_to_player = (
        tr is not None
        and tr.event in ("deals_damage", "combat_damage")
        and (
            "player" in tr.recipient
            or (
                tr.subject is not None
                and any(p.startswith("DamageToPlayer") for p in tr.subject.predicates)
            )
        )
    )
    for i, e in enumerate(ab.effects):
        if e.category != "discard":
            continue
        # The discard must be OPPONENT-directed (anaphoric "that player discards"),
        # read from its own raw or — for a modal/empty-raw discard — the card text.
        directed = e.raw or ""
        if not _directed_discard(directed) and not (
            not directed.strip() and _directed_discard(card_text)
        ):
            continue
        prior = ab.effects[:i]
        if dmg_to_player:
            return True
        if any(x.category in ("bounce", "counter_spell") for x in prior):
            return True
        if any(
            x.category in ("reveal_hand", "reveal")
            and (
                x.scope == "opp"
                or (x.subject is not None and x.subject.controller == "opp")
            )
            for x in prior
        ):
            return True
        if _opp_discard_raw(card_text):
            return True
    return False


def _recover_opponent_discard(card: Card, oracle: str) -> Card:
    """Append a sibling ``discard`` Effect scope='opp' to each ability whose discard is
    directed at a structurally-identified opponent (see _opp_discard_anchor), so the
    opponent_discard arm reads STRUCTURE for the damage-connect / bounce-counter /
    reveal-hand / each-opponent buckets phase scoped 'any'. Append-only and gated to a
    body phase left WITHOUT an opp/each-directed discard. CR 701.9 / 510.1c."""
    if not card.faces:
        return card
    if any(
        e.category == "discard"
        and (
            e.scope in ("opp", "each")
            or (e.subject is not None and e.subject.controller == "opp")
        )
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    appended = False
    faces: list[Face] = []
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            if _opp_discard_anchor(ab, text):
                new_abs.append(
                    replace(
                        ab,
                        effects=(
                            *ab.effects,
                            Effect(
                                category="discard",
                                scope="opp",
                                raw="opponent-directed discard (recovered)",
                            ),
                        ),
                    )
                )
                appended = True
            else:
                new_abs.append(ab)
        faces.append(replace(face, abilities=tuple(new_abs)))
    if not appended:
        return card
    return replace(card, faces=tuple(faces))


def _append_marker(card: Card, effect: Effect) -> Card:
    """Append a synthetic static ability carrying one marker ``effect`` to the head
    face — the shared shape the subject-Filter recoveries below use to surface a
    dropped predicate the lane reads off any ability's subject (mirrors
    _recover_devotion_operand). The marker is category="other", so it opens no
    category-gated lane; only the predicate-reading arms see its subject Filter."""
    synth = Ability(kind="static", effects=(effect,))
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# colorless_matters — phase DROPS the "colorless" qualifier off a cast-restriction /
# cost-reduction / counter-target, leaving a subject-less effect (Ghostfire Blade's
# "if it targets a colorless creature" cost_reduction subj=None, Ugin the Ineffable's
# "Colorless spells you cast cost {2} less" cost_reduction subj=None, Consign to
# Memory's "Counter … colorless spell" whose counter_spell subject is a bare Card
# Filter with no color predicate). The discriminator survives only in the raw, so we
# synth a ColorCount:EQ:0 subject Filter the colorless_matters arm
# (_predicate_build_around_lanes) reads structurally. CR 105.2c (a colorless object
# has no color) / 202.2.
# #24e P2 parser-substrate: DETECTION is a `_combinators` word scan —
# ``scan(seq2(keyword({"colorless"}), keyword({creature/spell/permanent + plurals})))``
# — a WHOLE-WORD two-slot read, stricter than the deleted substring regex
# `colorless (?:creature|spell|permanent)` which fired inside larger words ("colorless
# spellbomb" → the regex's "colorless spell" substring). The plural forms are folded in
# (the regex matched "colorless creatures"/"permanents" via its singular substring) so
# the real set holds. Ports to phase-rs as a nom `tuple((tag("colorless"), alt(type
# tags)))`. CR 105.2c.
_COLORLESS_REF = comb.scan(
    comb.seq2(
        comb.keyword({"colorless"}),
        comb.keyword(
            {
                "creature",
                "creatures",
                "spell",
                "spells",
                "permanent",
                "permanents",
            }
        ),
    )
)


def _recover_colorless_subject(card: Card, oracle: str) -> Card:
    """Synth a ColorCount:EQ:0 subject Filter (controller='you') for a card that
    references a colorless creature/spell/permanent but whose effects phase left
    color-blind, so the colorless_matters arm reads the predicate STRUCTURALLY.
    Idempotent (skipped when a real ColorCount:EQ:0 predicate already exists).
    CR 105.2c."""
    if not card.faces:
        return card
    if any(
        isinstance(f, Filter) and "ColorCount:EQ:0" in f.predicates
        for ab in card.all_abilities()
        for f in _ability_subjects(ab)
    ):
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "colorless", _COLORLESS_REF):
        return card
    return _append_marker(
        card,
        Effect(
            category="other",
            subject=Filter(controller="you", predicates=("ColorCount:EQ:0",)),
            raw="colorless reference (recovered)",
        ),
    )


# historic_matters — phase DROPS the "historic" qualifier off a cast-restriction /
# cost-reduction / discard-cost, leaving a subject-less effect (Raff Capashen's "cast
# historic spells as though they had flash" cast_with_keyword subj=None; Sanctum
# Spirit's "Discard a historic card" activation cost phase collapses to cost='discard'
# with no Historic carrier). The discriminator survives only in the raw, so we synth a
# Historic subject Filter the historic_matters arm (``"Historic" in ir_predicates``)
# reads structurally. An object is historic if it is legendary, an artifact, or a Saga
# (CR 700.6). Set-equal to the deleted "\bhistoric\b" word mirror (same anchor over
# the reminder-stripped joined oracle).
# #24e P1 parser-substrate: the DETECTION is a `_combinators` word scan
# (``find_word({"historic"})``), not a regex — it reads the oracle as a word stream
# and matches the whole word "historic" (word-boundary-safe by the tokenizer, not a
# `\b` assertion). Behavior-neutral with the deleted `\bhistoric\b` mirror (find_word's
# normalized whole-word match == the corpus). Ports to phase-rs as a nom `tag` in a
# word context. CR 700.6.
_HISTORIC_REF = comb.find_word({"historic"})


def _recover_historic_subject(card: Card, oracle: str) -> Card:
    """Synth a Historic subject Filter (controller='you') for a card that references a
    historic object but whose effects/cost phase left without the Historic predicate,
    so the historic_matters arm reads it STRUCTURALLY. Idempotent (skipped when a real
    Historic predicate already exists). CR 700.6."""
    if not card.faces:
        return card
    if any(
        isinstance(f, Filter) and "Historic" in f.predicates
        for ab in card.all_abilities()
        for f in _ability_subjects(ab)
    ):
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "historic", _HISTORIC_REF):
        return card
    return _append_marker(
        card,
        Effect(
            category="other",
            subject=Filter(controller="you", predicates=("Historic",)),
            raw="historic reference (recovered)",
        ),
    )


# base_power_matters — a base-power/toughness REFERENCE payoff (CR 613.4b sentence 2:
# "effects that REFER to the base power/toughness of a creature apply in layer 7b") —
# is distinct from a base_pt_set SETTER (sentence 1, "effects that SET power/tough").
# A reference says "creatures you control WITH base power N" (Bess Soul Nourisher's ETB
# count, Zinnia's go-wide scale, Duskana's draw-per, Primo's combat trigger, Rapid
# Augmenter's haste grant, Sword of the Squeak's equip scale) — it SELECTS creatures by
# their base P/T and rewards them; it sets nothing. phase preserves SOME of these as a
# `PtComparison:Power:EQ:N` subject predicate but that predicate is base-BLIND (323 of
# 330 cards carrying it reference CURRENT power — "creatures you control with power 4 or
# greater"), so the lane can't read PtComparison directly without massively over-firing
# to the current-power references. We therefore synth a base-SPECIFIC `BasePtRef` marker
# Filter (controller='you'), anchored on the same base-reference grammar the deleted
# base_pt_set kept word mirror used, so the base_power_matters arm reads the base-only
# predicate STRUCTURALLY. Set-equal to that deleted mirror (`creatures? you control/own
# with base power|toughness` over the reminder-stripped oracle) — the references LEAVE
# base_pt_set (they were an over-fire: set no base P/T) and ENTER base_power_matters.
# The setter verb ("have/has/are/is/becomes base power") is NOT matched, so a genuine
# base_pt_set setter never enters this lane (CR 613.4b set vs refer).
# #24e P1 parser-substrate: DETECTION is a `_combinators` clause scan over the
# six-slot phrase "creature(s) you control/own with base power/toughness" — each slot
# a per-position alternation bag, read as consecutive words. Behavior-neutral with the
# deleted `creatures? you (control|own) with base (power|toughness)` mirror; ports to
# phase-rs as a nom `tuple` of six tags. CR 613.4b (refer, not set).
_BASE_POWER_REF = comb.scan(
    comb.phrase(
        {"creature", "creatures"},
        {"you"},
        {"control", "own"},
        {"with"},
        {"base"},
        {"power", "toughness"},
    )
)


def _recover_base_power_ref(card: Card, oracle: str) -> Card:
    """Synth a base-specific `BasePtRef` subject Filter (controller='you') for a card
    that REFERS to a creature's base power/toughness ("creatures you control with base
    power N") but whose base qualifier phase either drops (Bess, Duskana — left an
    `ev:other` trigger / bare-Creature subject) or preserves only as a base-blind
    PtComparison (Zinnia, Primo, Rapid Augmenter, Sword of the Squeak), so the
    base_power_matters arm reads the base-only predicate STRUCTURALLY. Idempotent
    (skipped when a `BasePtRef` marker already exists). CR 613.4b (refer, not set)."""
    if not card.faces:
        return card
    if any(
        isinstance(f, Filter) and "BasePtRef" in f.predicates
        for ab in card.all_abilities()
        for f in _ability_subjects(ab)
    ):
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "with base", _BASE_POWER_REF):
        return card
    return _append_marker(
        card,
        Effect(
            category="other",
            subject=Filter(controller="you", predicates=("BasePtRef",)),
            raw="base power/toughness reference (recovered)",
        ),
    )


def _ability_subjects(ab: Ability) -> list[Filter]:
    """Every subject Filter an ability exposes (effect subjects, amount subjects,
    trigger subject) — the surface the predicate-reading lane arms scan."""
    subs: list[object] = [e.subject for e in ab.effects]
    subs += [e.amount.subject for e in ab.effects if e.amount is not None]
    if ab.trigger is not None:
        subs.append(ab.trigger.subject)
    return [f for f in subs if isinstance(f, Filter)]


# scaling_pump — a "~ gets +N/+N for each <X>" board-count scaler phase routes through
# a NON-`pump` carrier so the structural scaling_pump arm (cat=='pump' + scaling
# count) misses it: the token-borne grant lands on a `board_count` Effect (Karn Scion
# of Urza / Urza Lord High Artificer's "Construct … gets +1/+1 for each artifact you
# control"), a make_token raw (Vren's "Rat … gets +1/+1 for each other Rat you
# control"), or a single-target `pump_target` Effect with amount=None (Gold Rush's
# "creature gets +2/+2 for each Treasure you control"). We synth a `pump` Effect
# carrying the recovered op='count' operand (the for-each scaling reference the gate
# reads), so the arm fires STRUCTURALLY. The synth subject is left None on purpose: the
# count's go-wide reference lives in the raw (`_is_scaling_count` reads the "for each"
# raw for a subjectless count), and a typed subject would over-couple this pump-only
# recovery to the typed-matters lanes (artifacts_matter / etc. cross-read amount
# subjects). CR 613 (P/T-setting/modifying layer) / 107.3.
# #24e P2 parser-substrate: DETECTION is a `_combinators` scan — `scan(seq2(preceded(
# keyword({"gets"}), <PT word>), phrase({"for"}, {"each","every"})))` — where the P/T
# word is read as a STRUCTURED token (`+N/+N`, signed both sides) by a raw fullmatch,
# and the per-each magnitude N is taken from the normalized form (split on '/'). The
# whole-word read drops a substring over-fire and, because the magnitude class is
# `[0-9x]+` (not the deleted regex's single `[0-9x]`), CORRECTLY captures a multi-digit
# scaler ("gets +10/+10 for each …") the regex missed. The synth raw reconstructs the
# matched fragment (incl. trailing) so `_is_scaling_count`'s "for each" read is
# preserved. Ports to phase-rs as a nom `tuple((tag("gets"), pt_token, tag("for"),
# alt((tag("each"), tag("every")))))`. CR 613.
_PT_GETS_RE = re.compile(r"[+\-][0-9x]+/[+\-][0-9x]+", re.IGNORECASE)


def _pt_after_gets() -> comb.Parser[str]:
    """The signed P/T modification token (`+N/+N`) as one word — the structured operand
    a "gets" pump applies (raw fullmatch keeps the sign the normalizer folds)."""

    def go(s: str) -> tuple[str, str] | None:
        r = comb.word().run(s)
        if r is None or not _PT_GETS_RE.fullmatch(r[0]):
            return None
        return r

    return comb.Parser(go)


_SCALING_PUMP = comb.scan(
    comb.seq2(
        comb.preceded(comb.keyword({"gets"}), _pt_after_gets()),
        comb.phrase({"for"}, {"each", "every"}),
    )
)
_SCALING_FOR_EACH_RAW = re.compile(
    r"\bfor each\b|\bequal to the number of\b", re.IGNORECASE
)
_SCALING_NAMED_OPS = frozenset(
    {"counters", "domain", "devotion", "party", "experience"}
)


def _has_structural_scaling_pump(card: Card) -> bool:
    """True when a real `pump` Effect already carries a scaling count (a named scale
    op, or a count/multiply/toughness op with a subject or a for-each raw) — i.e. the
    structural scaling_pump arm already fires, so no synth is needed (the byte-mirror's
    206-card overlap). Mirrors _deck_forge._signals_ir._is_scaling_count."""
    for ab in card.all_abilities():
        for e in ab.effects:
            if e.category != "pump" or e.amount is None:
                continue
            op = e.amount.op
            if op in _SCALING_NAMED_OPS:
                return True
            if op in ("count", "multiply", "toughness") and (
                e.amount.subject is not None
                or _SCALING_FOR_EACH_RAW.search(e.raw or "")
            ):
                return True
    return False


def _recover_scaling_pump(card: Card, oracle: str) -> Card:
    """Synth a `pump` Effect with the recovered op='count' scaling operand for a card
    whose "gets +N/+N for each <X>" pump phase routed through a board_count / make_token
    / amount=None pump_target carrier, so the scaling_pump arm reads it STRUCTURALLY.
    Skipped when a real scaling pump already exists (the structural arm already fires).
    CR 613."""
    if not card.faces:
        return card
    if _has_structural_scaling_pump(card):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "gets" not in text.lower():
        return card
    res = _SCALING_PUMP.run(text)
    if res is None:
        return card
    (ptword, conn), rest = res
    # Per-each magnitude N from the normalized P/T token ("+10/+10" -> "10/10" -> "10").
    mag = comb.norm_word(ptword).split("/")[0]
    factor = 1 if mag in ("x", "") else int(mag)
    # Reconstruct the matched fragment (incl. the no-period/quote trailing) so the synth
    # raw carries "for each <X>" exactly as the deleted regex's m.group(0) did — the
    # `_is_scaling_count` "for each" read depends on it.
    cut = len(rest)
    for i, ch in enumerate(rest):
        if ch in '.\n"':
            cut = i
            break
    raw = f"gets {ptword} for {conn[1]}{rest[:cut]}"
    return _append_marker(
        card,
        Effect(
            category="pump",
            scope="you",
            amount=Quantity(op="count", factor=factor),
            raw=raw,
        ),
    )


# ── ADR-0027 #24h SUPPLEMENT_RECOVER C2 (subject / anaphora / quoted-trigger) ──
# Three reclassified MED-residue lanes whose kept regex mirror was the SOLE source of
# a real tail phase parses but DROPS the discriminating subject / scope / trigger.
# Each recovery reconstructs the dropped STRUCTURE onto the IR (a face-down subject, a
# resolved opponent controller, a synthesized deals_damage trigger) so the lane's IR
# arm reads structure and the regex mirror retires. Append-only / idempotent; same
# joined-oracle seam as the recoveries above.

# (1) facedown_matters — phase emits a face-down REVEAL / LOOK / TURN-face-up payoff as
#     a generic reveal / topdeck_select / transform / cost_reduction with the FACE-DOWN
#     qualifier DROPPED from the subject (Smoke Teller "look at target face-down
#     creature", Break Open "turn target face-down creature … face up", Panoptic
#     Projektor's "next face-down creature spell … costs less"). Stamp the EXACT marker
#     phase emits for NATIVE face-down subjects (the subtype token "Face-down" — see
#     _signals_ir._is_facedown_subject) onto every effect whose own clause references a
#     face-down permanent / spell or a morph-family mechanic, so the existing
#     facedown_matters effect-subject arm fires. The marker is inert outside the lane
#     ("Face-down" is not a creature subtype, so it can't cross into tribal lanes). CR
#     707.2 / 708.2 / 702.36-37.
# Mirror of the deleted FACEDOWN_MATTERS regex (NARROW — a face-down CREATURE/permanent
# reference, a 2/2-face-down, a TURN-face-up phrasing, or a morph-family keyword). It is
# deliberately NOT a bare "face down": a card EXILED face down (impulse-exile / hideaway
# — Bottled Cloister, Scroll Rack, Gonti) is a hidden-card mechanic, not the morph /
# manifest face-down-PERMANENT lane (CR 708 vs 702.36).
# #24e P3 parser-substrate: the face-down reference detector reads STRUCTURE. The
# `face[- ]?down` hyphen variants fold under norm ("face-down"/"facedown" → "facedown")
# OR split into two words ("face down"); `_FACEDOWN_WORD` covers both. `[^.]*?` gap →
# bounded_scan. Detection-only (the synth subject is fixed). CR 707.2 / 708.2.
_FACEDOWN_WORD = comb.alt(comb.keyword({"facedown"}), comb.phrase({"face"}, {"down"}))
_FACEDOWN_NOUN = comb.keyword({"creature", "creatures", "permanent", "permanents"})
_FACEDOWN_REF_P = comb.scan(
    comb.alt(
        # keyword_bounded so an ability word fused to its cost by an em-dash
        # ("Morph—Discard a card") still matches, like the regex `\bmorph\b`.
        comb.keyword_bounded({"morph", "megamorph", "manifest", "disguise", "cloak"}),
        comb.seq2(_FACEDOWN_WORD, _FACEDOWN_NOUN),
        comb.seq(
            comb.phrase({"as"}, {"a"}),
            comb.regex_word(re.compile(r"2/2")),
            _FACEDOWN_WORD,
        ),
        comb.seq(
            comb.keyword({"turn"}),
            comb.alt(
                comb.keyword({"it", "them"}),
                comb.phrase({"that"}, {"creature"}),
                comb.phrase({"this"}, {"creature"}),
                comb.phrase({"a"}, {"permanent"}, {"you"}, {"control"}),
            ),
            comb.phrase({"face"}, {"up"}),
        ),
        comb.seq(
            comb.phrase({"turn"}, {"target"}),
            comb.bounded_scan(comb.phrase({"face"}, {"up"})),
        ),
        comb.phrase({"turned"}, {"face"}, {"up"}),
    )
)
# A card that already fires facedown_matters STRUCTURALLY (a morph-family MAKER) needs
# no carrier: it bears the keyword, a native "Face-down" subject, or a turn_face_up.
_FACEDOWN_KEYWORDS = frozenset(
    {"morph", "megamorph", "manifest", "disguise", "cloak", "manifest dread"}
)


def _has_native_facedown(card: Card) -> bool:
    for face in card.faces:
        if any(k.lower() in _FACEDOWN_KEYWORDS for k in face.keywords):
            return True
    for ab in card.all_abilities():
        if ab.trigger is not None and (
            ab.trigger.event == "turn_face_up"
            or (
                ab.trigger.subject is not None
                and "Face-down" in ab.trigger.subject.subtypes
            )
        ):
            return True
        for e in ab.effects:
            if e.category == "turn_face_up" or (
                e.subject is not None and "Face-down" in e.subject.subtypes
            ):
                return True
    return False


def _recover_facedown(card: Card, oracle: str) -> Card:
    """Append a synthetic ``facedown_ref`` carrier Effect (subject = the exact
    "Face-down" marker phase emits for native face-down subjects) when the oracle
    references a face-down permanent / spell or a morph-family mechanic, so the existing
    facedown_matters effect-subject arm (``_is_facedown_subject``) reads STRUCTURE. The
    card name is stripped first, so a card merely NAMED "… of Disguise" / "… Made
    Manifest" / "Burning Cloak" — not a face-down payoff — is not swept in by its own
    name (a precision gain over the name-blind regex). A dedicated carrier category +
    subject is used (not a mutation of an existing effect's subject) so no other lane's
    subject-presence assumption is disturbed (e.g. the cost_reduction arm trusts a
    non-None subject — a stamped marker would mis-trust a "morph costs cost more" tax).
    Deduped against the morph-family MAKERS already firing structurally. CR 707.2 /
    708.2."""
    if not card.faces:
        return card
    name = card.name or ""
    text = oracle.replace(name, " ") if name else oracle
    text = re.sub(r"\([^)]*\)", " ", text)
    low = text.lower()
    # cheap dispatch: every arm needs a morph-family word or "face".
    if not any(k in low for k in ("face", "morph", "manifest", "disguise", "cloak")):
        return card
    if _FACEDOWN_REF_P.run(text) is None:
        return card
    if _has_native_facedown(card):
        return card
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="facedown_ref",
                scope="you",
                subject=Filter(subtypes=("Face-down",)),
                raw="face-down reference (recovered)",
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# (2) tap_down — phase leaves an OPPONENT-tap's controller UNRESOLVED: an anaphoric
#     "tap target <perm> that player controls" / "an opponent controls" projects with
#     subject.controller you/any (Citadel Siege, Karazikar, Sentinel, Somnophore,
#     Delirium) or a DROPPED subject (Snaremaster Sprite, Mind Spiral), so the
#     opponent-tapping lane can't read scope. Resolve the anaphor to controller=='opp'
#     on the tap subject (synthesizing the dropped subject from the tapped noun). The
#     "skips their next untap step" tempo-skip with NO tap effect at all (Brine
#     Elemental, Shisato — keeping the opponent's board tapped) is resolved to
#     scope=='opp' on the skip_step effect. A symmetric "each player's … that player
#     controls" tap (Monsoon, Angel's Trumpet) and a SELF untap-skip (Avizoa, Savor the
#     Moment) are both excluded. CR 701.20 / 702.36.
# #24e P3 parser-substrate: the tap-down anaphora reads STRUCTURE. `keyword({"tap"})`
# matches only the standalone word "tap" (norm keeps "untap"/"taps"/"tapped" distinct),
# so the regex `(?<!un)tap\b` lookbehind is satisfied for free. `[^.]*?` gap →
# bounded_scan. `_TAP_NOUN_P` maps the tapped noun to its capitalized singular subject.
_TAP_OPP_NOUN = comb.alt(
    comb.phrase({"an"}, {"opponent"}),
    comb.phrase({"that"}, {"player"}),
    comb.phrase({"that"}, {"opponent"}),
    comb.phrase({"target"}, {"opponent"}),
    comb.phrase({"defending"}, {"player"}),
    comb.phrase({"your"}, {"opponents"}),
    comb.keyword({"opponents"}),
)
_TAP_OPP_CONTROL_P = comb.scan(
    comb.seq2(
        comb.keyword({"tap"}),
        comb.bounded_scan(
            comb.seq2(_TAP_OPP_NOUN, comb.keyword({"control", "controls"}))
        ),
    )
)
# Substring regexes ("each player", "untap step") matched the possessive/plural
# ("each player's", "untap steps"), so accept those in the trailing slot.
_EACH_PLAYER_P = comb.scan(comb.phrase({"each"}, {"player", "players"}))
_SKIP_UNTAP_P = comb.scan(comb.phrase({"untap"}, {"step", "steps"}))
_SKIP_OPP_P = comb.scan(
    comb.seq2(
        comb.alt(
            comb.phrase({"each"}, {"opponent"}),
            comb.phrase({"that"}, {"player"}),
            comb.phrase({"target"}, {"player"}),
            comb.phrase({"target"}, {"opponent"}),
            comb.phrase({"an"}, {"opponent"}),
            comb.phrase({"that"}, {"opponent"}),
            comb.keyword({"opponent", "opponents"}),
        ),
        comb.keyword({"skip", "skips"}),
    )
)
_SKIP_SELF_P = comb.alt(
    comb.scan(comb.phrase({"you"}, {"skip"})),
    comb.scan(
        comb.seq(
            comb.keyword({"your"}),
            comb.opt(comb.keyword({"next"})),
            comb.phrase({"untap"}, {"step"}),
        )
    ),
)
_TAP_NOUN_MAP = {
    "land": "Land",
    "lands": "Land",
    "permanent": "Permanent",
    "permanents": "Permanent",
    "artifact": "Artifact",
    "artifacts": "Artifact",
    "creature": "Creature",
    "creatures": "Creature",
}
_TAP_NOUN_P = comb.scan(comb.satisfy(lambda w: w in _TAP_NOUN_MAP)).map(
    lambda w: _TAP_NOUN_MAP[comb.norm_word(w)]
)


def _tap_subject_opp(subject: Filter | None, clause: str) -> Filter:
    """Set the tap target's controller to 'opp', synthesizing the type subject phase
    dropped (read from the tapped noun — "tap target LAND that player controls")."""
    if subject is None:
        r = _TAP_NOUN_P.run(clause)
        ct = r[0] if r is not None else "Creature"
        return Filter(card_types=(ct,), controller="opp")
    return replace(subject, controller="opp")


def _recover_tap_down(card: Card, oracle: str) -> Card:
    """Resolve the opponent anaphora on tap / skip-untap-step effects so tap_down reads
    STRUCTURE (a tap subject controller=='opp', a skip_step scope=='opp'). Each effect
    reads its OWN clause raw (the full oracle only when phase dropped that raw —
    Delirium, Mind Spiral). Idempotent (a tap already controller=='opp' / a skip already
    scope=='opp' is untouched). CR 701.20."""
    if not card.faces:
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    faces: list[Face] = []
    changed = False
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                clause = re.sub(r"\([^)]*\)", " ", e.raw) if e.raw else text
                if (
                    e.category == "tap"
                    and not (e.subject is not None and e.subject.controller == "opp")
                    and _TAP_OPP_CONTROL_P.run(clause) is not None
                    and _EACH_PLAYER_P.run(clause) is None
                ):
                    new_effs.append(
                        replace(e, subject=_tap_subject_opp(e.subject, clause))
                    )
                    changed = True
                elif (
                    e.category == "skip_step"
                    and e.scope != "opp"
                    and _SKIP_UNTAP_P.run(clause) is not None
                    and _SKIP_OPP_P.run(clause) is not None
                    and _SKIP_SELF_P.run(clause) is None
                ):
                    new_effs.append(replace(e, scope="opp"))
                    changed = True
                else:
                    new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    if not changed:
        return card
    return replace(card, faces=tuple(faces))


# ── ADR-0027 #24i (SIDECAR v58) — SUPPLEMENT_RECOVER D1 ───────────────────────
# (1) hand_disruption — an opponent reveals / you look at an opponent's hand, the
#     hand-disruption build-around tell. phase emits the structure THREE ways the
#     existing scope-gated reveal_hand arm misses, plus drops/folds it on a tail:
#       • a MODAL reveal-opponent-hand ("Choose one — Target opponent reveals their
#         hand", Mardu Charm, Collective Brutality, Auntie's Sentence, Doomfall,
#         Cerebral Confiscation, Shatter Assumptions) — phase keeps a `reveal_hand`
#         Effect whose SUBJECT Filter is controller='opp' but the mode loses the
#         scope, so it lands scope='any' and the arm (which needs scope=='opp')
#         skips it. Recover scope='opp' off the subject controller (bucket A).
#       • a `reveal` (NOT reveal_hand) scope='opp' whose raw says "<player> reveals
#         their hand" (Alhammarret, Psychotic Episode) — phase typed the hand reveal
#         as a generic reveal. Re-categorize to reveal_hand (bucket A).
#       • a `topdeck_select` scope='opp' mis-categorized look-at-an-opponent's-hand
#         peek ("look at an opponent's hand, then choose a card name", Anointed
#         Peacekeeper, Sorcerous Spyglass) — re-categorize to reveal_hand (bucket A).
#     A folded/dropped tail (Thoughtcutter Agent's reveal folded into the lose_life
#     effect, Sen Triplets' / Wandering Eye's "plays with their hand(s) revealed"
#     restriction, Arachne's dropped look-at-hand, The Raven's Warning's Saga-chapter
#     combat-damage hand peek) survives only in the raw oracle: synth a reveal_hand
#     scope='opp' from it (bucket B), guarded so a card already carrying an opp-
#     directed reveal_hand / reveal_hands is untouched. The detect pattern is the
#     deleted hand_disruption mirror byte-for-byte, so the recovered set == the
#     mirror's. CR 402.3 / 701.x.
# #24e P3 parser-substrate: the hand-disruption tells read STRUCTURE. The possessive
# `…'?s?'?` folds under norm ("opponent's" → "opponents"), so the noun slots accept the
# possessive/plural form. `[^.]*` gaps → bounded_scan. `(\w+ )?cards?` → an alt that
# tries "card" directly, else one filler word then "card" (regex backtracking). The
# "their|his or her" possessive-pronoun bag recurs. CR 402.3 / 701.x.
_HD_HIS_THEIR = comb.alt(comb.keyword({"their"}), comb.phrase({"his"}, {"or"}, {"her"}))
_HD_REVEAL_HAND_TEXT_P = comb.scan(
    comb.seq(
        comb.keyword({"reveal", "reveals"}),
        _HD_HIS_THEIR,
        comb.keyword({"hand", "hands"}),
    )
)
_HD_LOOK_HAND_TEXT_P = comb.scan(
    comb.seq2(
        comb.phrase({"look"}, {"at"}),
        comb.bounded_scan(comb.keyword({"hand", "hands"})),
    )
)
# The opponent-directed hand-disruption oracle tell (the deleted mirror, verbatim).
_HD_OPP_HAND_P = comb.scan(
    comb.alt(
        comb.seq(
            comb.phrase({"look"}, {"at"}),
            comb.alt(
                comb.phrase({"target"}, {"player", "players"}),
                comb.phrase({"that"}, {"player", "players"}),
                comb.phrase({"an"}, {"opponent", "opponents"}),
                comb.phrase({"each"}, {"opponent", "opponents"}),
                comb.phrase({"target"}, {"opponent", "opponents"}),
            ),
            comb.keyword({"hand", "hands"}),
        ),
        comb.seq(
            comb.keyword({"play", "plays"}),
            comb.keyword({"with"}),
            _HD_HIS_THEIR,
            comb.keyword({"hand", "hands"}),
            comb.keyword({"revealed"}),
        ),
        comb.seq(
            comb.keyword({"reveal", "reveals"}),
            _HD_HIS_THEIR,
            comb.keyword({"hand", "hands"}),
        ),
        comb.seq(
            comb.keyword({"reveal", "reveals"}),
            comb.alt(
                comb.keyword({"card", "cards"}),
                comb.seq2(comb.word(), comb.keyword({"card", "cards"})),
            ),
            comb.opt(comb.phrase({"at"}, {"random"})),
            comb.keyword({"from"}),
            comb.alt(
                comb.keyword({"their"}),
                comb.phrase({"his"}, {"or"}, {"her"}),
                comb.phrase({"that"}, {"players"}),
            ),
            comb.keyword({"hand"}),
        ),
        comb.seq2(
            comb.keyword({"reveal", "reveals"}),
            comb.bounded_scan(comb.phrase({"until"}, {"you"}, {"say"}, {"stop"})),
        ),
    )
)


def _recover_hand_disruption(card: Card, oracle: str) -> Card:
    """Recover the opponent-hand-reveal structure so the scope-gated reveal_hand arm
    fires: scope='opp' off a modal reveal_hand's opp subject, a generic `reveal` /
    `topdeck_select` opp hand-peek re-categorized to reveal_hand (bucket A), and a
    synth reveal_hand scope='opp' for the folded/dropped tail (bucket B, guarded
    against an existing opp-directed reveal_hand / reveal_hands). CR 402.3 / 701.x."""
    if not card.faces:
        return card

    def has_opp_reveal(c: Card) -> bool:
        return any(
            (e.category == "reveal_hand" and e.scope == "opp")
            or e.category == "reveal_hands"
            for ab in c.all_abilities()
            for e in ab.effects
        )

    changed = False
    faces: list[Face] = []
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                raw = e.raw or ""
                if (
                    e.category == "reveal_hand"
                    and e.scope != "opp"
                    and isinstance(e.subject, Filter)
                    and e.subject.controller == "opp"
                ):
                    new_effs.append(replace(e, scope="opp"))
                    changed = True
                elif e.scope == "opp" and (
                    (
                        e.category == "reveal"
                        and _HD_REVEAL_HAND_TEXT_P.run(raw) is not None
                    )
                    or (
                        e.category == "topdeck_select"
                        and _HD_LOOK_HAND_TEXT_P.run(raw) is not None
                    )
                ):
                    new_effs.append(replace(e, category="reveal_hand"))
                    changed = True
                else:
                    new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    card = replace(card, faces=tuple(faces)) if changed else card

    # bucket B — synth from the raw oracle the folded/dropped tail phase emits no
    # opp-directed reveal node for (append-only; an existing opp reveal short-circuits).
    if not has_opp_reveal(card):
        stripped = re.sub(r"\([^)]*\)", " ", oracle)
        low = stripped.lower()
        if ("reveal" in low or "look at" in low) and _HD_OPP_HAND_P.run(
            stripped
        ) is not None:
            synth = Ability(
                kind="static",
                effects=(
                    Effect(category="reveal_hand", scope="opp", raw=stripped.strip()),
                ),
            )
            head, *rest = card.faces
            card = replace(
                card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
            )
    return card


# (2) keyword_grant_target — a spell/ability grants a keyword to a SINGLE TARGET
#     creature ("target creature gains menace until end of turn"). The structural
#     single_target_grant arm reads phase's clean ParentTarget AddKeyword markers;
#     phase drops the target on a tail it folds into a bare `grant_keyword`
#     (subject=None): a MODAL grant (Adaptive Sporesinger, Appa, Balloon Stand,
#     Ferocification, Retreat to Hagra), a grant QUOTED on an Aura / land / planes-
#     walker ("Enchanted land has '{T}: Target creature gains haste'", Racecourse
#     Fury, Skygames, Footfall Crater, Rowan's Talent), a compound quoted grant
#     (Infuse with Vitality), a Saga-chapter grant (Rediscover the Way), and Chariot
#     of the Sun (routed to base_pt_set). For those the "target creature gains <kw>"
#     survives only in the raw oracle, so synth a single_target_grant Effect (the
#     resolved Creature subject + the SingleTarget predicate, faithful controller +
#     granted keyword in counter_kind) so the arm reads STRUCTURE. The detect pattern
#     is the deleted KEYWORD_GRANT_TARGET mirror byte-for-byte. The split/aftermath
#     BACK-HALF grants (Claim//Fame's "Fame", Onward//Victory's "Victory") are a
#     GENUINE UPSTREAM phase gap — phase emits NO record for a split back face, so the
#     phase-records oracle this recovery reads never carries them; a narrow layout-
#     gated residue in signals keeps those two. CR 700.2 / 702.x.
# #24e P3 parser-substrate: the single-target keyword grant reads STRUCTURE. The value
# threads out (controller-flag, keyword) — controller "you" iff "you control" rode the
# target, keyword folded to its no-space form ("double strike" → "doublestrike"). The
# `gets ±N/±M and gains` arm reads the sign-bearing P/T delta off the raw word (norm
# folds the sign, so `_KGT_PT_DELTA` checks the raw). Iterated via `_iter_spans`
# (the regex finditer). CR 700.2 / 702.x.
_KGT_PT_DELTA_RE = re.compile(r"[+\-][0-9x]/[+\-][0-9x]", re.IGNORECASE)
_KGT_PT_DELTA = comb.Parser(
    lambda s: (
        r
        if (r := comb.word().run(s)) is not None and _KGT_PT_DELTA_RE.match(r[0])
        else None
    )
)
_KGT_VERB = comb.alt(
    comb.keyword({"gain", "gains"}),
    comb.seq(
        comb.keyword({"gets"}),
        _KGT_PT_DELTA,
        comb.keyword({"and"}),
        comb.keyword({"gain", "gains"}),
    ),
)
_KGT_KW = comb.alt(
    comb.value("doublestrike", comb.phrase({"double"}, {"strike"})),
    comb.value("firststrike", comb.phrase({"first"}, {"strike"})),
    comb.keyword(
        {
            "deathtouch",
            "trample",
            "flying",
            "menace",
            "vigilance",
            "lifelink",
            "haste",
            "hexproof",
            "indestructible",
            "protection",
            "reach",
            "ward",
            "shroud",
        }
    ),
)
_KGT_GRANT_P = comb.seq(
    comb.phrase({"target"}, {"creature"}),
    comb.opt(comb.phrase({"you"}, {"control"})),
    _KGT_VERB,
    _KGT_KW,
)
_KGT_SINGLE_TARGET_PRED = "SingleTarget"


def _recover_keyword_grant_target(card: Card, oracle: str) -> Card:
    """Append synthetic ``single_target_grant`` Effects for the single-target keyword
    grants phase folded to a bare grant_keyword (modal / quoted-on-Aura-or-land /
    Saga-chapter) so the keyword_grant_target arm reads STRUCTURE. Append-only: a card
    already carrying a single_target_grant (phase's clean ParentTarget marker) is left
    alone. The split/aftermath back-half grants are out of reach here (no phase record
    for the back face — upstream gap); a signals layout residue keeps them. CR 700.2."""
    if not card.faces:
        return card
    if any(
        e.category == "single_target_grant"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "target creature" not in text.lower():  # cheap dispatch — every match needs it.
        return card
    synth_effs: list[Effect] = []
    seen: set[str] = set()
    for clause, value in _iter_spans(text, _KGT_GRANT_P):
        if clause.lower() in seen:
            continue
        seen.add(clause.lower())
        controller = "you" if value[1] is not None else "any"
        kw = value[3]
        synth_effs.append(
            Effect(
                category="single_target_grant",
                scope=controller,
                subject=Filter(
                    card_types=("Creature",),
                    controller=controller,
                    predicates=(_KGT_SINGLE_TARGET_PRED,),
                ),
                raw=clause.strip(),
                counter_kind=kw,
            )
        )
    if not synth_effs:
        return card
    synth = Ability(kind="static", effects=tuple(synth_effs))
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# ── ADR-0027 #24l (SIDECAR v60) — SUPPLEMENT_RECOVER E1 (low-residue tail) ─────
# (1) extra_land_drop — the YOUR "put a land card from your hand / among the dug-or-
#     cascaded cards onto the battlefield" put phase FOLDS off cat=='cheat_play':
#     phase emits cat=='reanimate' for the cascade-from-exile put (Averna), buries the
#     dig put inside the cat=='exile' / cat=='topdeck_select' effect raw (Aminatou's
#     Augury, Planar Genesis — mis-zoned to:hand), folds it into a draw's raw
#     (Contaminant Grafter), drops the d20-branch put (Journey to the Lost City), or
#     leaves the modal Confluence cheat_play Land controller='any' + EMPTY raw
#     (Riveteers Confluence — the "or graveyard" disjunction defeats phase's YOUR pin).
#     The dropped structure (a YOUR land-into-play put) survives in the joined oracle,
#     so synthesize a canonical cheat_play Effect (Land subject, controller='you') the
#     extra_land_drop arm already reads — the _recover_combat_damage_recipients
#     precedent. The detect pattern is the EXACT deleted signals mirror regex (the
#     source-restricted "you may put … land card from your hand|among them|among those
#     cards|among the exiled cards … onto the battlefield"), so the recovered set is
#     byte-identical to the deleted mirror and the symmetric "each player may put …
#     from their hand" group ramp (Kynaios, Hypergenesis, Tempting Wurm) never matches
#     (it lacks the YOUR "you may put"). The whole mirror retires. CR 305.4 / 720.
# #24e P3 parser-substrate: the YOUR land-into-play put reads STRUCTURE. The optional
# quantity is "a" or "up to <word>"; the source is one of four fixed phrases; the gap
# gap to "onto the battlefield" → bounded_scan. CR 305.4 / 720.
_EXTRA_LAND_DROP_PUT_P = comb.seq(
    comb.phrase({"you"}, {"may"}, {"put"}),
    comb.opt(
        comb.alt(
            comb.keyword({"a"}),
            comb.seq2(comb.phrase({"up"}, {"to"}), comb.word()),
        )
    ),
    comb.keyword({"land", "lands"}),
    comb.keyword({"card", "cards"}),
    comb.keyword({"from"}),
    comb.alt(
        comb.phrase({"your"}, {"hand"}),
        comb.phrase({"among"}, {"them"}),
        comb.phrase({"among"}, {"those"}, {"cards"}),
        comb.phrase({"among"}, {"the"}, {"exiled"}, {"cards"}),
    ),
    comb.bounded_scan(comb.phrase({"onto"}, {"the"}, {"battlefield"})),
)


def _recover_extra_land_drop(card: Card, oracle: str) -> Card:
    """Append a synthetic ``cheat_play`` Effect (Land subject, controller='you') for the
    YOUR land-into-play put phase folds off cat=='cheat_play' — a cascade-from-exile
    reanimate (Averna), a dig-into-play buried in an exile/topdeck_select raw
    (Aminatou's Augury, Planar Genesis), a draw-raw fold (Contaminant Grafter), a
    dropped d20 branch (Journey to the Lost City), or a modal Confluence cheat_play Land
    controller='any' with empty raw (Riveteers). Append-only; skipped when the card
    already carries a cheat_play Land controller='you' put (the shape the arm reads).
    The synthetic Effect carries only zones=('to:battlefield',) so it fires
    extra_land_drop alone (other cheat_play readers gate on from:graveyard/top:you)."""
    if not card.faces:
        return card
    if any(
        e.category == "cheat_play"
        and isinstance(e.subject, Filter)
        and "Land" in e.subject.card_types
        and e.subject.controller == "you"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    if "you may put" not in stripped.lower():  # cheap dispatch — the lead phrase.
        return card
    span = _scan_span(stripped, _EXTRA_LAND_DROP_PUT_P)
    if span is None:
        return card
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="cheat_play",
                scope="you",
                subject=Filter(card_types=("Land",), controller="you"),
                zones=("to:battlefield",),
                raw=span,
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )
