"""Standalone mechanic (coven, celebration, outlaw, curse, clue, suspend,
known-token) bucket-B synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    ConceptTree,
    counter_kind,
    effect_filter,
    filter_subtypes,
    iter_cost_leaves,
    iter_typed_nodes,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant
from mtg_utils._card_ir.text_idioms import (
    _CRIME_REF,
    _SUSPECT_REF,
    _TOKEN_SUBTYPE_OWN_REF,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._deck_forge._sweep_detectors import CLUE_MATTERS_REGEX

# end_the_turn (CR 724 "(may) end the turn") moved to ADR-0038 shared-grammar
# recovery (mtg_utils._card_ir.clause_grammar's "the player whose turn it is "
# subject peel + "end the turn" verb tag, mtg_utils._card_ir.recovery.
# ALLOWLIST) — Obeka's player-scoped grant is a real Unimplemented EFFECT-role
# node, so re-decoration reaches it; the typed ``effect_concepts
# ("end_the_turn")`` read sees it directly. No marker arm needed.


# evasion_denial (CR 509.1b/702.14 "can be blocked as though it/they didn't
# have [landwalk/those abilities]") moved to ADR-0038 static-token recovery
# (mtg_utils._card_ir.clause_grammar.STATIC_TOKENS +
# mtg_utils._card_ir.recovery.ALLOWLIST) — Staff of the Ages's own static
# parser fails, but the resulting Unimplemented residue is STILL role=effect,
# so re-decoration reaches it there; the typed ``effect_concepts
# ("evasion_denial")`` read sees it directly. No marker arm needed.


# suspect ACTION idiom (CR 701.60a — "instruct a player to suspect a creature"):
# the "suspect it/target/a creature" verb. When it rides a token-creation rider
# ("create a Skeleton and suspect it" — Case of the Stashed Skeleton) phase drops
# the Suspect effect, so the typed ``effect_concepts("suspect")`` read misses it.
# "suspected" (CR 701.60b — the DESIGNATION, a payoff reference) never matches
# (the negative lookahead), keeping the doer/payoff split.
_SUSPECT_ACTION_RE = re.compile(r"\bsuspect\b(?!ed)", re.IGNORECASE)


def _arm_suspect_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``suspect`` maker node for the suspect ACTION phase drops when
    it rides a token creation (Case of the Stashed Skeleton — phase emits NO
    residue node at all, so ADR-0038 re-decoration recovery can't reach it; this
    dropped-rider gap stays a synthesis arm per ADR-0037). Gap-gated on NO typed
    ``Suspect`` effect (Nelly Borca's first-class suspect stays Tier-1). Emits
    the REAL "suspect" concept (ADR-0038 retired the synth_* marker namespace),
    so the ``_suspect_makers`` lane's typed ``effect_concepts("suspect")`` read
    sees it directly, no marker special-case needed."""
    if any(True for _ in tree.effect_concepts("suspect")):
        return None
    if not _SUSPECT_ACTION_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="suspect_makers",
        concept="suspect",
        scope="you",
        subject=(),
        desc="bucket-B suspect (dropped suspect-it action rider)",
    )


# ── coven_matters bucket-B (ADR-0036/0037 Stage 5, batch T1-abilitywords) ──────
# CR 207.2c: coven is an ABILITY WORD — "no special rules meaning and no
# individual entries in the Comprehensive Rules." phase renders the Coven
# condition ("if you control three or more creatures with different powers")
# as a generic ``QuantityCheck``/``ObjectCountDistinct`` shape shared by
# unrelated distinct-count cards (probed and rejected as a lane
# discriminator by the live docstring this fold ports) — there is no typed
# node phase stamps for "coven" specifically, so the word IS the only anchor
# and this arm is the lane's SOLE source (no competing Tier-1 predicate to
# gap-gate against, the evasion_self/theft_makers precedent for an
# unstructurable ability word).
_COVEN_SYNTH_RX = re.compile(r"\bcoven\b", re.IGNORECASE)


def _matches_coven_idiom(oracle: str) -> bool:
    return bool(_COVEN_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_coven_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``coven_matters`` node — CR 207.2c ability word, the
    deleted ``_COVEN_MIRROR`` relocated verbatim (ADR-0036 fold)."""
    if not _matches_coven_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="coven_matters",
        concept="synth_coven_matters",
        scope="you",
        subject=(),
        desc="bucket-B coven ability word (CR 207.2c)",
    )


# ── celebration_matters bucket-B (ADR-0036/0037 Stage 5) ───────────────────────
# CR 207.2c: celebration is an ABILITY WORD — "no special rules meaning and no
# individual entries in the Comprehensive Rules." There is no structured
# rules object for phase to parse (probed: Ash, Party Crasher carries
# "Celebration —" only in strings), so the word IS the lane by CR
# construction — NOT a phase bug — and this arm is the lane's SOLE source
# (no competing Tier-1 predicate, the evasion_self/theft_makers precedent).
_CELEBRATION_SYNTH_RX = re.compile(r"\bcelebration\b", re.IGNORECASE)


def _matches_celebration_idiom(oracle: str) -> bool:
    return bool(_CELEBRATION_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_celebration_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``celebration_matters`` node — CR 207.2c ability word,
    the deleted ``_CELEBRATION_RX`` relocated verbatim (ADR-0036 fold)."""
    if not _matches_celebration_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="celebration_matters",
        concept="synth_celebration_matters",
        scope="you",
        subject=(),
        desc="bucket-B celebration ability word (CR 207.2c)",
    )


# ── outlaw_matters direct/bucket-A/bucket-B (ADR-0036/0037 Stage 5) ────────────
# CR 700.12/700.12a: Assassin/Mercenary/Pirate/Rogue/Warlock are the "outlaw"
# creature-type GROUP. Two structural shapes phase carries for a card that
# names the group: (a) the CR 700.12 five-subtype ``AnyOf`` filter (Olivia,
# At Knifepoint — probed live) and (b) a literal "Outlaw" PSEUDO-subtype
# token phase stamps when the card negates the group ("non-outlaw" — Shoot
# the Sheriff), wrapped in a ``Non``. Both are typed-filter reads, zero
# regex. The residual bucket-B gap is an "Affinity for outlaws" cost
# reducer (Hellspur Brute) that phase drops ENTIRELY — zero units, zero
# typed nodes at all for the whole card — a genuine phase gap with no
# competing structural signal.
OUTLAW_SUBTYPES: frozenset[str] = frozenset(
    {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"}
)


def _tf_names_outlaw_group(tf: object) -> bool:
    """Whether one ``type_filters`` entry names the outlaw PSEUDO-subtype
    token "Outlaw" — directly or under a ``Non`` negation (Shoot the
    Sheriff's "non-outlaw creature"). Recurses ``Non``/``AnyOf`` wrappers."""
    if isinstance(tf, str):
        return tf == "Outlaw"
    if isinstance(tf, MirrorVariant):
        if tf.key == "Subtype":
            return tf.inner == "Outlaw"
        if tf.key == "Non":
            return _tf_names_outlaw_group(tf.inner)
        if tf.key == "AnyOf" and isinstance(tf.inner, list):
            return any(_tf_names_outlaw_group(e) for e in tf.inner)
    return False


def has_structural_outlaw(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed filter naming the outlaw group —
    the CR 700.12 five-subtype ``AnyOf`` (``filter_subtypes`` reads it as a
    flat frozenset subset of :data:`OUTLAW_SUBTYPES`, 2+ members so a lone
    Rogue-tribal reference — Anowon — never qualifies alone) OR the literal
    "Outlaw" pseudo-subtype token (:func:`_tf_names_outlaw_group`, recovers
    the ``Non``-negated "non-outlaw" phrasing no ``filter_subtypes`` call
    surfaces since it deliberately excludes ``Non`` wrappers)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Typed":
                continue
            subs = frozenset(filter_subtypes(n))
            if subs and subs <= OUTLAW_SUBTYPES and len(subs) >= 2:
                return True
            for tf in getattr(n, "type_filters", ()) or ():
                if _tf_names_outlaw_group(tf):
                    return True
    return False


_OUTLAW_SYNTH_RX = re.compile(r"\boutlaws?\b", re.IGNORECASE)


def _matches_outlaw_idiom(oracle: str) -> bool:
    return bool(_OUTLAW_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_outlaw_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``outlaw_matters`` node for the bucket-B residue phase
    drops entirely (Hellspur Brute's "Affinity for outlaws" — zero units)."""
    if has_structural_outlaw(tree):
        return None
    if not _matches_outlaw_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="outlaw_matters",
        concept="synth_outlaw_matters",
        scope="you",
        subject=(),
        desc="bucket-B outlaw group reference (CR 700.12) phase drops",
    )


# ── batch T4-mechanic-kw (ADR-0036/0037 Stage 5): curse_matters bucket-B ─────
# CR 205.3h: curse_matters' two structural arms (a Curse-subtype
# ``valid_card`` trigger watch, a Curse-subtype effect-filter target —
# ``_curse_matters`` in crosswalk_signals.py) miss the remaining bare
# REFERENCE idioms ("curse spells", "curses you cast/control/own",
# "target/each/another/your curse", "curse cards") — no clean structural
# anchor exists for a reference that is neither a trigger watch nor an
# effect target. Relocates the deleted ``_CURSE_MATTERS_MIRROR`` verbatim,
# gap-gated against :func:`has_structural_curse_matters` (the SAME two arms
# the lane tries first, GAP-GATE-ALIGNMENT). Measured byte-identical over
# the commander-legal corpus (4/4 union, 0 drops, 0 adds).
_CURSE_MATTERS_SYNTH_RX = re.compile(
    r"curse spells?|curses? you (?:cast|control|own)"
    r"|(?:\ba|target|each|another|your) curse\b|curse cards?",
    re.IGNORECASE,
)


def has_structural_curse_matters(tree: ConceptTree) -> bool:
    """Whether phase carries a typed Curse-subtype trigger-watch / effect-
    target node — the curse_matters lane's two structural arms (mirrors
    them exactly) — the synth gap-gate."""
    for unit in tree.units:
        vc = getattr(unit.node, "valid_card", None)
        if vc is not None and "Curse" in filter_subtypes(vc):
            return True
        for c in unit.effects:
            filt = effect_filter(c.node)
            if filt is not None and "Curse" in filter_subtypes(filt):
                return True
    return False


def _matches_curse_matters_idiom(oracle: str) -> bool:
    return bool(_CURSE_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_curse_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``curse_matters`` node for the bucket-B Curse-subtype
    reference residue (the deleted ``_CURSE_MATTERS_MIRROR`` relocated,
    gap-gated against :func:`has_structural_curse_matters`)."""
    if has_structural_curse_matters(tree):
        return None
    if not _matches_curse_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="curse_matters",
        concept="synth_curse_matters",
        scope="you",
        subject=(),
        desc="bucket-B Curse-subtype reference residue (CR 205.3h)",
    )


# ── batch T4-mechanic-kw: clue_matters bucket-B tail ─────────────────────────
# CR 111.10f/701.16a: the lane's shared food/clue structural helper
# (``_token_subtype_payoff`` in crosswalk_signals.py) opens on a Sacrifice-
# of-Clue effect/cost or a Sacrificed-mode trigger naming Clue — those two
# arms are reimplemented here (GAP-GATE-ALIGNMENT). The helper's OWN third
# arm (the ``_TOKEN_SUBTYPE_OWN_REF`` text marker) is untouched: it is
# SHARED with food_matters, a lane out of THIS batch's scope, so it is not
# folded today (tracked for when food_matters folds). The residual THIS arm
# covers is the bare "clue"/"investigate" word (modal-vote folds — Tivit;
# delayed triggers; token replacements; becomes-Clue statics — In Too
# Deep) — breadth intentional (the b13 suspend_matters precedent, port
# as-is). Relocates the deleted ``_CLUE_MATTERS_RX`` verbatim. The lane
# itself still tries the FULL shared helper (all three arms) FIRST,
# unchanged, so a card the OWN-REF arm alone covers short-circuits before
# ever reading this synth node — no double-count despite the narrower gate.
# Measured byte-identical over the commander-legal corpus (164/164 union,
# 0 drops, 0 adds).
_CLUE_MATTERS_SYNTH_RX = re.compile(CLUE_MATTERS_REGEX, re.IGNORECASE)


def has_structural_clue_matters(tree: ConceptTree) -> bool:
    """Whether phase carries a typed Sacrifice-of-Clue / Sacrificed-Clue
    node — the two genuinely structural arms the shared food/clue helper
    opens for "Clue" (mirrors them exactly) — the synth gap-gate."""
    for unit in tree.units:
        sac_nodes = [c.node for c in unit.effects if tag_of(c.node) == "Sacrifice"]
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "Sacrifice":
                sac_nodes.append(leaf)
        for node in sac_nodes:
            subs = {s.lower() for s in filter_subtypes(getattr(node, "target", None))}
            if "clue" in subs:
                return True
        if unit.origin == "trigger":
            mode = getattr(unit.node, "mode", None)
            tag = mode if isinstance(mode, str) else tag_of(mode)
            if tag == "Sacrificed":
                vc = getattr(unit.node, "valid_card", None)
                if "clue" in {s.lower() for s in filter_subtypes(vc)}:
                    return True
    return False


def _matches_clue_matters_idiom(oracle: str) -> bool:
    return bool(_CLUE_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_clue_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``clue_matters`` node for the bucket-B bare
    "clue"/"investigate" word residue (the deleted ``_CLUE_MATTERS_RX``
    relocated, gap-gated against :func:`has_structural_clue_matters`)."""
    if has_structural_clue_matters(tree):
        return None
    if not _matches_clue_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="clue_matters",
        concept="synth_clue_matters",
        scope="you",
        subject=(),
        desc='bucket-B bare "clue"/"investigate" residue (CR 111.10f/701.16a)',
    )


# ── arm: token_subtype_own_ref, the SHARED food/clue OWN-REF residual
# (ADR-0036/0037 Stage 5, T9-finalize) ───────────────────────────────────────
# CR 111.10b (Food) / 701.16a+111.10f (Clue): the crosswalk's shared
# ``_token_subtype_payoff`` helper (food_matters + clue_matters) carries a
# THIRD arm — the ``_TOKEN_SUBTYPE_OWN_REF`` marker re-derivation ("Foods
# you control" / "was a Food" / "is a Food") — that phase does not type at
# all (a pure cares-about reference, not an effect). Relocated verbatim as
# a SUBJECT-carrying node (the type_matters precedent): the node carries
# every distinct subtype the OWN-REF idiom names, gated to subtypes this
# FACE does not already make/sacrifice (:func:`_made_sac_token_subtypes` —
# the SAME made/sacd exclusion the lane computes, reimplemented here rather
# than imported to avoid a crosswalk_signals↔tree_synthesis cycle).
def _made_sac_token_subtypes(tree: ConceptTree) -> tuple[set[str], set[str]]:
    """(made, sacd) token subtypes this face structurally creates/spends —
    mirrors the food/clue lane's own made/sacd computation exactly."""
    made: set[str] = set()
    for c in tree.effect_concepts("make_token"):
        types = getattr(c.node, "types", None) or []
        made |= {t.lower() for t in types if isinstance(t, str)}
    if tree.has_effect("investigate"):
        made.add("clue")  # Investigate IS "create a Clue token" (CR 701.16a)
    sacd: set[str] = set()
    for unit in tree.units:
        sac_nodes = [c.node for c in unit.effects if tag_of(c.node) == "Sacrifice"]
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "Sacrifice":
                sac_nodes.append(leaf)
        for node in sac_nodes:
            sacd |= {s.lower() for s in filter_subtypes(getattr(node, "target", None))}
    return made, sacd


def _arm_token_subtype_own_ref(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a SUBJECT-carrying node for the shared food/clue OWN-REF
    cares-about idiom (the deleted ``_TOKEN_SUBTYPE_OWN_REF`` lane-time
    read relocated verbatim)."""
    made, sacd = _made_sac_token_subtypes(tree)
    kept = _REMINDER.sub(" ", tree.oracle or "")
    subjects: set[str] = set()
    for m in _TOKEN_SUBTYPE_OWN_REF.finditer(kept):
        ref = next(g for g in m.groups() if g).lower()
        if ref not in made and ref not in sacd:
            subjects.add(ref)
    if not subjects:
        return None
    return _synthetic_concept(
        arm_id="token_subtype_own_ref",
        concept="synth_token_subtype_own_ref",
        scope="you",
        subject=tuple(sorted(subjects)),
        desc="bucket-B token-subtype own-control/state reference (CR 111.10b/701.16a)",
    )


# ── batch T4-mechanic-kw: suspend_matters bucket-B tail ──────────────────────
# CR 702.62 (+ Vanishing/Impending/"Suspended Animation" time-counter
# siblings, and the Doctor Who "Time Travel" mechanic the mirror's breadth
# also covers — deliberately broad, ported as-is): the ONE structural anchor
# phase carries is a ``PutCounter{counter_type=Time}`` node (CR 122.1),
# which covers explicit time-counter manipulation (Jhoira's Timebug, Fury
# Charm). The residual — reminder-surviving keyword bearers ("Suspend
# 4—{1}{U}", "Impending 4—{2}{W}{W}"), and phase's opaque ``GenericEffect``
# wrap of "exile it with N time counters on it. It gains suspend" (Rory
# Williams, Delay, Epochrasite, Sibylline Soothsayer) — has no further
# structural anchor. Relocates the deleted ``_SUSPEND_MATTERS_MIRROR``
# verbatim, gap-gated against :func:`has_structural_suspend_matters`.
# Measured byte-identical over the commander-legal corpus (143/143 union,
# 0 drops, 0 adds; one PRE-EXISTING self-name-collision quirk — Impending
# Flux, which mentions no time-counter/suspend mechanic at all — is ported
# as-is + LOGGED, the b13 Blue Screen of Death precedent).
_SUSPEND_MATTERS_SYNTH_RX = re.compile(
    r"\bsuspend\b|time counter|time travel|\bvanishing\b|\bimpending\b",
    re.IGNORECASE,
)


def has_structural_suspend_matters(tree: ConceptTree) -> bool:
    """Whether phase carries a ``PutCounter{counter_type=Time}`` node — the
    suspend_matters lane's structural arm (mirrors it exactly) — the synth
    gap-gate."""
    for c in tree.effect_concepts("place_counter"):
        if counter_kind(c.node).lower() == "time":
            return True
    return False


def _matches_suspend_matters_idiom(oracle: str) -> bool:
    return bool(_SUSPEND_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_suspend_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``suspend_matters`` node for the bucket-B time-counter
    bearer/reference residue (the deleted ``_SUSPEND_MATTERS_MIRROR``
    relocated, gap-gated against :func:`has_structural_suspend_matters`)."""
    if has_structural_suspend_matters(tree):
        return None
    if not _matches_suspend_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="suspend_matters",
        concept="synth_suspend_matters",
        scope="you",
        subject=(),
        desc="bucket-B time-counter bearer/reference residue (CR 702.62)",
    )


# ── batch T4-mechanic-kw: crimes_matter bucket-B tail ────────────────────────
# CR 700.13 + glossary "Crime": the lane's structural arm (a raw
# ``CommitCrime`` trigger mode — ``_crimes_matter`` in
# crosswalk_signals.py) already binds the dominant crime-PAYOFF template;
# the residual is the keyword-less CONDITION form ("if/as long as/whenever
# you've committed a crime", "committed a crime this turn") phase has no
# condition kind for. Relocates the deleted ``_CRIME_REF`` search verbatim,
# gap-gated against :func:`has_structural_crimes_matter` (the SAME trigger
# check the lane tries first). Measured byte-identical over the
# commander-legal corpus (27/27 union, 0 drops, 0 adds).
def has_structural_crimes_matter(tree: ConceptTree) -> bool:
    """Whether phase carries a raw ``CommitCrime`` trigger mode — the
    crimes_matter lane's structural arm (mirrors it exactly) — the synth
    gap-gate."""
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        mode = getattr(unit.node, "mode", None)
        tag = mode if isinstance(mode, str) else tag_of(mode)
        if tag == "CommitCrime":
            return True
    return False


def _matches_crimes_matter_idiom(oracle: str) -> bool:
    return bool(_CRIME_REF.search(_REMINDER.sub(" ", oracle or "")))


def _arm_crimes_matter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``crimes_matter`` node for the bucket-B keyword-less
    crime-condition residue (the deleted ``_CRIME_REF`` search relocated,
    gap-gated against :func:`has_structural_crimes_matter`)."""
    if has_structural_crimes_matter(tree):
        return None
    if not _matches_crimes_matter_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="crimes_matter",
        concept="synth_crimes_matter",
        scope="you",
        subject=(),
        desc="bucket-B keyword-less crime-condition residue (CR 700.13)",
    )


# ── batch T4-mechanic-kw: suspect_matters bucket-B (full relocation) ────────
# CR 701.60a/701.60b: "suspected" is a DESIGNATION, not an ability — there is
# no clean structural separation from the suspect VERB (the ported b4
# suspect_makers lane) without reading the carrying UNIT's own raw text
# (Nelly Borca's raw carries BOTH forms and the verb must win — a pure
# structural read, e.g. the ``Suspected`` property, can't discriminate that
# and would over-fire her; LOGGED, not taken, the b13 Blue Screen of Death
# precedent). Relocates the two deleted lane arms verbatim: (a) a native
# ``Suspect`` effect's OWN raw (state-not-verb), (b) the ``_SUSPECT_REF``
# marker re-derivation over the kept oracle when no native Suspect effect
# is present. No competing Tier-1 predicate — SOLE source. Measured
# byte-identical over the commander-legal corpus (7/7 union, 0 drops, 0
# adds).
_SUSPECTED_STATE_SYNTH_RX = re.compile(r"\bsuspected\b", re.IGNORECASE)
_SUSPECT_VERB_SYNTH_RX = re.compile(r"\bsuspects?\b", re.IGNORECASE)


def _matches_suspect_matters_idiom(tree: ConceptTree) -> bool:
    if tree.has_effect("suspect"):
        for unit in tree.units:
            for c in unit.effect_concepts("suspect"):
                raw = c.raw or ""
                if _SUSPECTED_STATE_SYNTH_RX.search(
                    raw
                ) and not _SUSPECT_VERB_SYNTH_RX.search(raw):
                    return True
        return False
    m = _SUSPECT_REF.search(_REMINDER.sub(" ", tree.oracle or ""))
    if m is not None:
        g = m.group(0)
        if _SUSPECTED_STATE_SYNTH_RX.search(g) and not _SUSPECT_VERB_SYNTH_RX.search(g):
            return True
    return False


def _arm_suspect_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``suspect_matters`` node (the deleted two-arm
    ``suspect_matters`` lane body relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_suspect_matters_idiom(tree):
        return None
    return _synthetic_concept(
        arm_id="suspect_matters",
        concept="synth_suspect_matters",
        scope="you",
        subject=(),
        desc="bucket-B suspected-STATE reference (CR 701.60a/701.60b)",
    )


def _arm_known_token_impulse_top_play(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_impulse_top_play`` marker for a Junk known-
    token zero-unit text-only tree (task #95) — "Exile the top card of
    your library. You may play that card this turn" (CR 601.3b/116).
    Gated on ``not tree.units`` — ``_impulse_top_play``'s own structural
    exile_top+cast_from_zone pairing has no unit here to walk at all, so
    the lane reads this marker instead (the ``synth_plus_one_makers``
    marker precedent)."""
    if tree.units:
        return None
    oracle = (tree.oracle or "").lower()
    if "exile the top card of your library" not in oracle:
        return None
    if "you may play that card this turn" not in oracle:
        return None
    return _synthetic_concept(
        arm_id="known_token_impulse_top_play",
        concept="synth_impulse_top_play",
        scope="you",
        subject=(),
        desc="predefined known-token impulse-draw ability (Junk)",
    )


def _arm_known_token_lifeloss_opponents(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_lifeloss_makers_opponents`` marker for a
    Wicked known-token zero-unit text-only tree (task #95) — "When this
    Aura is put into a graveyard from the battlefield, each opponent
    loses 1 life" (CR 119.3). Gated on ``not tree.units`` AND the full
    "Aura ... put into a graveyard ... opponent loses" clause (not the
    bare "each opponent loses" fragment alone, which collides with an
    unrelated death-trigger drain idiom the ``death_matters`` synthesis
    test fixtures also exercise on a zero-unit ``_gap_tree``)."""
    if tree.units:
        return None
    oracle = (tree.oracle or "").lower()
    if "put into a graveyard from the battlefield" not in oracle:
        return None
    if "opponent loses" not in oracle:
        return None
    return _synthetic_concept(
        arm_id="known_token_lifeloss_opponents",
        concept="synth_lifeloss_makers_opponents",
        scope="opponents",
        subject=(),
        desc="predefined known-token opponent life-loss ability (Wicked)",
    )


# ── task #np_roles — the WOE-Role-cycle + single-creator tail arms ─────────
# The deferral closeout for the four Role identities task #95 left unwired
# (Cursed / Royal / Sorcerer; Monster stays adjudicated-out — see the
# ``_ir_lookup`` module comment) plus the wired tail identities (Shard,
# Wizard, Contract, Forest Dryad, Mutavault, Spellgorger Weird — the last
# rides the pre-existing ``_arm_spellcast_matters`` with zero new code).
# Same discipline as the task #95 block above: every arm gates on ``not
# tree.units`` (zero-unit text-only trees only) and matches the FIXED,
# KNOWN token wording (CR 111.10j-r defines each Role's exact text).


def _arm_known_token_single_target_neutralize(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_single_target_neutralize`` marker for a Cursed
    Role known-token zero-unit text-only tree (task #np_roles) — "Enchanted
    creature has base power and toughness 1/1" (CR 111.10j; base-P/T set is
    layer 7b, CR 613.4b). ``_single_target_neutralize``'s own structural
    arm (an ``EnchantedBy``-affected ``SetPower <= 1`` site — Darksteel
    Mutation) has no unit to walk here, so the lane reads this marker
    instead (the ``synth_lifeloss_makers_opponents`` precedent)."""
    if tree.units:
        return None
    oracle = (tree.oracle or "").lower()
    if "enchanted creature has base power and toughness 1/1" not in oracle:
        return None
    return _synthetic_concept(
        arm_id="known_token_single_target_neutralize",
        concept="synth_single_target_neutralize",
        scope="you",
        subject=(),
        desc="predefined known-token base-P/T neutralize (Cursed, CR 111.10j)",
    )


def _arm_known_token_ward_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_protection_grant_suit_up`` marker for a Royal
    Role known-token zero-unit text-only tree (task #np_roles) — "Enchanted
    creature gets +1/+1 and has ward {1}" (CR 111.10m; ward is CR 702.21a,
    a protective keyword). The real durable-Aura analog (Shield of the
    Oversoul) fires ``protection_grant`` through ``_keyword_grant_lanes``'s
    suit-up branch; a zero-unit tree has no AddKeyword mod site to walk, so
    the lane reads this marker instead. Reminder-stripped first: the Royal
    toml text carries ward's own reminder ("... counter it unless that
    player pays {1}"), which must never leak into other matches."""
    if tree.units:
        return None
    oracle = _REMINDER.sub(" ", tree.oracle or "").lower()
    if "enchanted creature gets" not in oracle or "has ward" not in oracle:
        return None
    return _synthetic_concept(
        arm_id="known_token_ward_grant",
        concept="synth_protection_grant_suit_up",
        scope="you",
        subject=(),
        desc="predefined known-token ward suit-up grant (Royal, CR 702.21a)",
    )


_KNOWN_TOKEN_SCRY_RX = re.compile(r"\bscry \d", re.IGNORECASE)


def _arm_known_token_topdeck_scry(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_topdeck_selection`` marker for a zero-unit
    text-only tree whose fixed text performs a Scry (task #np_roles) —
    the Sorcerer Role's granted "Whenever this creature attacks, scry 1"
    (CR 111.10n) and the Shard's "{2}, Sacrifice this enchantment: Scry 1,
    then draw a card". CR 701.22a scry is ALWAYS own-library top curation
    (no other-player variant exists), so a bare "scry N" on a zero-unit
    tree is a safe, owner-unambiguous ``topdeck_selection`` doer — the
    lane's structural ``Scry`` tag read has no unit to walk here.
    Reminder-stripped so a reminder that merely describes a look (the Map
    token's explore text) can never match."""
    if tree.units:
        return None
    if not _KNOWN_TOKEN_SCRY_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="known_token_topdeck_scry",
        concept="synth_topdeck_selection",
        scope="you",
        subject=(),
        desc="predefined known-token scry doer (Sorcerer/Shard, CR 701.22a)",
    )


def _arm_known_token_counter_spell(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``counter_spell`` node for a Wizard known-token
    zero-unit text-only tree (task #np_roles) — Mage's Attendant's "{1},
    Sacrifice this creature: Counter target noncreature spell unless its
    controller pays {1}." (CR 701.6a). Emits the REAL ``counter_spell``
    concept — ``_counter_control``'s only branch
    (``effect_concepts("counter_spell")``) reads it unconditionally, the
    same real-concept precedent as ``_arm_known_token_ramp``. Gated on
    ``not tree.effect_concepts("counter_spell")`` so a future card whose
    own typed Counter node coexists never doubles."""
    if tree.units or tree.effect_concepts("counter_spell"):
        return None
    if "counter target noncreature spell" not in (tree.oracle or "").lower():
        return None
    return _synthetic_concept(
        arm_id="known_token_counter_spell",
        concept="counter_spell",
        scope="you",
        subject=(),
        desc="predefined known-token counterspell (Wizard, CR 701.6a)",
    )


def _arm_known_token_lifeloss_contract(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_lifeloss_makers_opponents`` marker for the
    Contract known-token zero-unit text-only tree (task #np_roles) —
    "Whenever enchanted creature attacks, it gets +2/+0 until end of turn
    if it's attacking one of your opponents. Otherwise, its controller
    loses 2 life." (CR 119.3). The sole creator (Scriv, the Obligator)
    attaches it to "target creature an opponent controls", so the losing
    controller is an opponent — scope "opponents", the Wicked lane-read
    precedent verbatim. Both phrase gates required (the attack trigger AND
    the controller-loss tail) so no unrelated zero-unit text matches."""
    if tree.units:
        return None
    oracle = (tree.oracle or "").lower()
    if "whenever enchanted creature attacks" not in oracle:
        return None
    if "its controller loses" not in oracle:
        return None
    return _synthetic_concept(
        arm_id="known_token_lifeloss_contract",
        concept="synth_lifeloss_makers_opponents",
        scope="opponents",
        subject=(),
        desc="predefined known-token controller life-loss (Contract, CR 119.3)",
    )
