"""Combat: attack, evasion, exert, station, base P/T, and tap/untap synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    ConceptTree,
    condition_tags,
    count_operand_filter,
    effect_filter,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    iter_mod_sites,
    iter_typed_nodes,
    mod_keyword_name,
    node_duration,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant
from mtg_utils._card_ir.supplement import (
    _BASE_POWER_REF,
    _anchored,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._deck_forge._sweep_detectors import PUMP_MATTERS_REGEX
from mtg_utils._deck_forge.signal_base import clauses
from mtg_utils._deck_forge.text_reads import _TOUGHNESS_VALUE_MIRROR

# ── attack_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_attack_tapped_matters`` lane fires ``attack_matters`` on these typed
# reads; this stage's gap gate (:func:`_has_structural_attack`) reads the SAME
# predicates so the lane and the synth never disagree on which cards phase
# structuralizes (the gap-gate-alignment invariant — one source, no drift).

# Offensive attack-DECLARATION trigger events (CR 508.1a — the active player
# chooses which of THEIR creatures attack). The compound events phase derives for
# "enters or attacks" / "attacks and isn't blocked" / "whenever you attack with an
# unblocked …" / "when one or more creatures attack". ``attacksorblocks`` and
# ``attackerblocked`` are deliberately EXCLUDED: those bundle self-sacrifice
# DRAWBACKS ("when this attacks or blocks, sacrifice it") and afflict ("becomes
# blocked") that are not attack payoffs — the genuine "whenever ~ attacks or blocks"
# rewards are recovered by the bucket-B synth's whenever-gate instead.
ATTACK_TRIGGER_EVENTS: frozenset[str] = frozenset(
    {
        "attacks",
        "entersorattacks",
        "attackerunblocked",
        "youattackunblocked",
        "attackersdeclared",
    }
)
# Positive Raid CONDITION tags ("if you attacked this turn" — CR 508.1a/508.4). The
# ``condition`` family only; the ``prop`` / ``properties`` filter-predicate family
# ("creatures that DIDN'T attack this turn" — anti-attack durdle) is deliberately
# not read, so a negated non-payoff never opens the lane.
RAID_CONDITION_TAGS: frozenset[str] = frozenset(
    {
        "YouAttackedThisTurn",
        "SourceAttackedThisTurn",
        "YouAttackedWithAtLeast",
        "YouAttackedSourceControllerThisTurn",
    }
)


def has_attack_trigger(tree: ConceptTree) -> bool:
    """A phase-typed offensive attack-declaration trigger (CR 508.1a)."""
    return any(
        unit.origin == "trigger" and unit.trigger_event in ATTACK_TRIGGER_EVENTS
        for unit in tree.units
    )


def attack_raid_condition(tree: ConceptTree) -> bool:
    """A positive Raid state check ("if you attacked this turn" — CR 508.1a)."""
    return bool(condition_tags(tree) & RAID_CONDITION_TAGS)


def has_attacking_you_effect(tree: ConceptTree) -> bool:
    """An effect over YOUR ``Attacking`` creatures ("attacking creatures you
    control get +1/+0"; "for each attacking creature you control" — CR 508.1k).
    The controller gate is load-bearing: "destroy target attacking creature"
    (controller any) is removal, not an aggro payoff.
    """
    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is None or filter_controller(filt) != "You":
                continue
            if "Attacking" in filter_predicates(filt):
                return True
    return False


def _has_structural_attack(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 attack reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural attack
    evidence the lane fires on exists — the SAME three predicates the lane reads
    (:func:`has_attack_trigger` / :func:`attack_raid_condition` /
    :func:`has_attacking_you_effect`), so the gate and the lane never disagree.
    """
    return (
        has_attack_trigger(tree)
        or attack_raid_condition(tree)
        or has_attacking_you_effect(tree)
    )


# ── arm: attack_matters bucket-B (ADR-0036 fold) ──────────────────────────────
# The combat-state payoff over YOUR creatures (CR 508) has a bucket-B tail phase
# emits NO typed attack node for: a "whenever ~ attacks / attacks or blocks" trigger
# left description-only (granted/quoted abilities — "creatures you control have
# 'whenever this creature attacks …'"), the "attacking causes [extra combat
# triggers]" family (Isshin, CR 508.2a/603.2), and the Raid count phase leaves as
# untyped text ("you attacked with two or more creatures this turn" — Windbrisk
# Heights, Minas Tirith). Read PER-CLAUSE (reminder-stripped) so a match is confined
# to ONE clause — the cross-clause false-positive class the mirror carried.
#
# Every family fires ONLY when NO structural attack node is present
# (:func:`_has_structural_attack`) and ONLY for a genuine your-side attack payoff.
# The over-fire VETO sheds, per CR: "attacks alone" / exalted (CR 506.5 / 702.83a —
# a single-attacker voltron condition, not go-wide), the DEFENSIVE "whenever a
# creature attacks you" (CR 508.1a — watches the OPPONENT's declaration, a
# pillowfort trigger), and the "can't attack" restriction (CR 508.1c — a hoser, not
# a payoff). The positive Raid idiom requires past-tense "you attacked" (YOU as the
# attacker), so "didn't attack this turn" and "each opponent who attacked" never
# match.
_ATTACK_ALONE_RX = re.compile(r"attacks? alone|attacking alone", re.IGNORECASE)
_ATTACK_DEFENSIVE_RX = re.compile(
    r"attacks? you\b|attacks a player other than you|creature attacks you"
    r"|attacks you or a planeswalker",
    re.IGNORECASE,
)
_ATTACK_CANT_RX = re.compile(r"can'?t attack", re.IGNORECASE)
_ATTACK_MATTERS_RX = re.compile(r"attacking causes|attacked this turn", re.IGNORECASE)
# YOU as the attacker — the positive Raid idiom (excludes "didn't attack" and the
# defensive "each opponent who attacked").
_ATTACK_RAID_RX = re.compile(r"\byou attacked\b", re.IGNORECASE)


def _matches_attack_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B attack payoff idiom.

    Per-clause: a genuine your-side attack trigger ("whenever ~ attacks"), the
    "attacking causes" / "attacked this turn" idioms, or a positive Raid ("you
    attacked …"), MINUS the over-fire veto (attacks-alone / defensive / can't-attack).
    """
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if (
            _ATTACK_ALONE_RX.search(cl)
            or _ATTACK_DEFENSIVE_RX.search(cl)
            or _ATTACK_CANT_RX.search(cl)
        ):
            continue
        lc = cl.lower()
        if (
            _ATTACK_MATTERS_RX.search(cl)
            or _ATTACK_RAID_RX.search(cl)
            or ("whenever" in lc and "attack" in lc)
        ):
            return True
    return False


def _arm_attack_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``attack_matters`` node for a description-only attack payoff.

    CR 508: fires only when phase carries no typed attack node
    (:func:`_has_structural_attack`) and the oracle carries a genuine your-side
    attack idiom (:func:`_matches_attack_idiom`). Scope "you" (the lane's + serve
    spec's scope for this combat-state payoff).
    """
    if _has_structural_attack(tree):
        return None
    if not _matches_attack_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="attack_matters",
        concept="synth_attack_matters",
        scope="you",
        subject=(),
        desc="bucket-B attack payoff (phase emits no typed attack node)",
    )


# ── evasion_self bucket-B tail (ADR-0036 fold — no shared structural gate) ─────
# evasion_self (CR 509.1b evasion blocking-restriction abilities / 702.14
# landwalk): a card that CARRIES or GRANTS evasion. The six keyword rows
# (menace/fear/intimidate/skulk/horsemanship/shadow) PLUS the five landwalk
# keywords (islandwalk/swampwalk/forestwalk/mountainwalk/plainswalk/landwalk)
# ride the Scryfall keyword-field arm (``_keyword_field_signals_b15`` — a
# bucket-A structural recovery, this fold's own-keyword-field extension);
# flying is DELIBERATELY absent (soft evasion). phase gets NO Tier-1 read for
# the rest — the ``CantBeBlocked`` static tag hangs under activated
# GenericEffects for some cards (Giant Koi), so reading it structurally would
# drift the 1646-row population (the ``_evasion_self`` lane docstring's
# warning) — so this arm is the lane's ONLY source for the text tail and has
# no competing Tier-1 predicate to gap-gate against.
#
# Three idiom families, relocated from the deleted ``_EVASION_SELF_REGEX``:
#
#   * an inherent/granted "can't be blocked" / "unblockable" state (CR
#     509.1b) — fires FLAT (no grant-verb gate): the measured corpus carries
#     zero non-member matches for this phrase.
#   * a granted keyword (menace/fear/intimidate/skulk/horsemanship) or
#     landwalk word in the oracle TEXT — gated PER-CLAUSE to a genuine
#     ACQUISITION (:func:`_evasion_clause_grants`): `gains`/`has`/`have`/
#     `becomes`, a keyword-COUNTER, a `create`/token grant, or the "the same
#     is true for" / "repeat this process for" / "and so on for" / "do the
#     same for" keyword-SHARE continuation idiom (Odric, Kathril,
#     Selective Adaptation, Super-Adaptoid). A bare REFERENCE to an existing
#     creature's keyword is NOT a grant — measured over-fires shed this way:
#     Borrowing the East Wind / Broken Dam / Rolling Earthquake / Trip Wire
#     (horsemanship-hoser removal/damage/tap targeting creatures WITH/WITHOUT
#     the keyword), J. Jonah Jameson + Tentative Connection (a bare "creature
#     you control/a creature with menace" REFERENCE, not a grant), You Come
#     to the Gnoll Camp ("Intimidate Them" is a mode LABEL — its actual
#     effect is "can't block", not the CR 702.13 keyword), and Fear, Fire,
#     Foes! (the card's OWN NAME echoed verbatim in its oracle text — a name
#     collision, not the keyword). A NEGATED acquisition ("didn't have
#     <keyword>" — the evasion-DENIAL idiom: Great Wall / Crevasse / Gosta
#     Dirk / Quagmire / Undertow / Ur-Drago / Deadfall / Lord Magnus, CR
#     702.14 denial, a separate ``_evasion_denial`` lane already covers
#     these) is explicitly excluded by the negator-tail guard — no
#     name-keyed denylist needed. Merfolk Assassin ("Destroy target creature
#     with islandwalk") and Urborg / Mystic Decree ("loses"/"lose" landwalk)
#     are anti-landwalk removal, shed by the same positive-acquisition gate.
_EVASION_LANDWALK_WORD_RX = re.compile(
    r"\b(?:forest|island|mountain|plains|swamp)walk\b", re.IGNORECASE
)
_EVASION_GRANTED_KW_RX = re.compile(
    r"\b(?:horsemanship|menace|fear|intimidate|skulk)\b", re.IGNORECASE
)
_EVASION_CANT_RX = re.compile(r"can't be blocked|\bunblockable\b", re.IGNORECASE)
_EVASION_ACQUIRE_RX = re.compile(
    r"\bgains?\b|\bhave\b|\bhas\b|\bbecomes?\b", re.IGNORECASE
)
# a NEGATED acquisition ("didn't have <keyword>") is the evasion-DENIAL idiom
# (CR 702.14), never a grant — checked as the tail of the text immediately
# preceding the acquisition verb.
_EVASION_NEGATOR_TAIL_RX = re.compile(
    r"\b(?:doesn't|don't|didn't|isn't|aren't|won't|wouldn't|couldn't|"
    r"can't|never|no longer)\s*$",
    re.IGNORECASE,
)
_EVASION_GRANT_CONTINUATION_RX = re.compile(
    r"\bthe same is true for\b|\brepeat this process for\b"
    r"|\band so on for\b|\bdo the same for\b"
    r"|\bfrom among\b|\byour choice of\b",
    re.IGNORECASE,
)
_EVASION_GRANT_OBJECT_RX = re.compile(
    r"\btokens?\b|\bcounters?\b|\bcreate\b", re.IGNORECASE
)
# a BARE ability-declaration line — the pre-templating "Snow swampwalk" /
# "Snow forestwalk" keyword-line form (CR 702.14e) some older cards use
# instead of a "gains"/"has" sentence (Legions of Lim-Dûl, Rime Dryad); the
# clause IS the ability, own possession, not a reference.
_EVASION_BARE_LANDWALK_LINE_RX = re.compile(
    r"^\s*(?:snow\s+)?(?:forest|island|mountain|plains|swamp)walk\s*$",
    re.IGNORECASE,
)
_EVASION_CLAUSE_SPLIT = re.compile(r"[.;\n]")


def _evasion_keyword_occurrences(clause: str) -> list[re.Match[str]]:
    """Every granted-keyword / landwalk-word match in ``clause``, position order."""
    ms = list(_EVASION_GRANTED_KW_RX.finditer(clause))
    ms += list(_EVASION_LANDWALK_WORD_RX.finditer(clause))
    return sorted(ms, key=lambda m: m.start())


def _evasion_comma_segment(clause: str, pos: int, end: int) -> str:
    """The comma-delimited SEGMENT of ``clause`` spanning ``[pos, end)``.

    A "Whenever <condition>, <effect>" template's comma is a hard boundary
    between the trigger condition and its resulting effect (J. Jonah
    Jameson: "a creature you control with menace attacks, create a Treasure
    token" — the created Treasure has nothing to do with the referenced
    menace). Confining the keyword-COUNTER / created-TOKEN check to the
    SAME comma segment as the keyword keeps a sibling effect from leaking a
    false grant onto a bare reference, while a "create ... tokens with
    menace" grant (no comma between "tokens" and "menace") stays intact.
    """
    start = clause.rfind(",", 0, pos) + 1
    stop = clause.find(",", end)
    if stop == -1:
        stop = len(clause)
    return clause[start:stop]


def _evasion_clause_grants(clause: str, occ: list[re.Match[str]]) -> bool:
    """Whether ``clause`` (already known to carry ``occ``, its keyword
    occurrences) GRANTS a keyword evasion ability — a bare landwalk ability-
    declaration line, the keyword-SHARE / keyword-CHOICE continuation idiom
    ("the same is true for" / "from among" / "your choice of", checked
    whole-clause: these idioms span a long keyword list, so the grant verb
    or counter word sits far from any one keyword's position), a keyword
    COUNTER / created-TOKEN carrier (checked in the keyword's OWN comma
    SEGMENT — :func:`_evasion_comma_segment` — not whole-clause, so a
    sibling effect never leaks a false grant onto a bare reference), or a
    non-negated CR 702 acquisition verb (``gains``/``has``/``have``/
    ``becomes``) anywhere in the clause. A bare reference to an existing
    creature's keyword ("target creature with horsemanship") or a NEGATED
    acquisition ("didn't have menace" — evasion-DENIAL) is not a grant."""
    if _EVASION_BARE_LANDWALK_LINE_RX.match(clause):
        return True
    if _EVASION_GRANT_CONTINUATION_RX.search(clause):
        return True
    for m in occ:
        segment = _evasion_comma_segment(clause, m.start(), m.end())
        if _EVASION_GRANT_OBJECT_RX.search(segment):
            return True
    for am in _EVASION_ACQUIRE_RX.finditer(clause):
        pre = clause[: am.start()]
        if not _EVASION_NEGATOR_TAIL_RX.search(pre):
            return True
    return False


def _matches_evasion_self_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B evasion_self
    idiom (CR 509.1b / 702.14) — the deleted ``_EVASION_SELF_REGEX``
    relocated, with the hoser / reference / denial / name-collision tail shed
    per :func:`_evasion_clause_grants`."""
    text = _REMINDER.sub(" ", oracle or "")
    if _EVASION_CANT_RX.search(text):
        return True
    for cl in _EVASION_CLAUSE_SPLIT.split(text):
        occ = _evasion_keyword_occurrences(cl)
        if occ and _evasion_clause_grants(cl, occ):
            return True
    return False


def _arm_evasion_self(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``evasion_self`` node for the bucket-B can't-be-blocked /
    granted-keyword / granted-landwalk tail (CR 509.1b / 702.14).

    phase carries NO Tier-1 structural read for this concept (the
    ``CantBeBlocked`` static tag is deliberately unread — see the module
    docstring above), so this arm is the lane's ONLY source for the text
    tail; there is no competing Tier-1 predicate to gap-gate against. The
    card's OWN Scryfall keyword field rides a separate structural arm
    (``_keyword_field_signals_b15``) — firing here on the same card too is
    harmless, since the lane dedupes identical ``evasion_self`` signals by
    identity (ADR-0036/0037).
    """
    if not _matches_evasion_self_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="evasion_self",
        concept="synth_evasion_self",
        scope="you",
        subject=(),
        desc="bucket-B evasion grant (can't-be-blocked / landwalk / keyword)",
    )


# ── exalted_lone_attacker textual tail, bucket-B (ADR-0036/0037 Stage 5) ───────
# CR 702.83a/702.83b + 506.5 (a creature "attacks alone" if it's the only
# declared attacker). The Scryfall-keyword bearer row already rides Tier-1
# (:func:`_keyword_field_signals_b16`); this arm is ONLY the textual tail —
# a card that GRANTS exalted or pays off "attacks alone" in its own prose
# without carrying the keyword itself (Agents of S.H.I.E.L.D., Emissary of
# Soulfire's exalted counter). **Not** the ``SourceAttackingAlone`` /
# ``AttackingAlone`` / ``BlockingAlone`` / ``CombatAlone`` phase tags —
# probed and REJECTED: those structure a DIFFERENT mechanic family, a
# conditional "can't be blocked as long as it's attacking alone" EVASION
# clause (Dream Prowler, Yuan-Ti Malison, Gutter Shortcut) that is not an
# exalted bonus at all (CR 702.14-adjacent, the evasion_self lane's turf) —
# reading those tags here would be a genuine 4-card over-fire on the
# corpus, so no structural gate exists for this arm; it is the lane's SOLE
# source (the evasion_self/theft_makers no-competing-predicate precedent).
_EXALTED_SYNTH_RX = re.compile(r"attacks alone|\bexalted\b", re.IGNORECASE)


def _matches_exalted_idiom(oracle: str) -> bool:
    return bool(_EXALTED_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_exalted_lone_attacker(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``exalted_lone_attacker`` node for the textual grant /
    payoff tail (the deleted ``_EXALTED_TEXT_RX`` relocated verbatim)."""
    if not _matches_exalted_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="exalted_lone_attacker",
        concept="synth_exalted_lone_attacker",
        scope="you",
        subject=(),
        desc="bucket-B exalted / attacks-alone textual grant (CR 702.83a)",
    )


# ── arm: power_matters bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ─────
# The Tier-1 structural read (crosswalk_signals.py's power_matters /
# low_power_matters lane) reads a FIXED ``PtComparison`` on Power at
# an effect/count-operand/condition site. The genuine residue: the AGGREGATE
# "total/greatest/combined power of creatures you control" scaler (Ghalta, The
# Great Henge, Rishkar's Expertise) and the Formidable ability word (CR 207.2c)
# — phase folds the threshold into an EMPTY-predicate board_count carrier, so no
# typed field distinguishes it from an unrelated empty-predicate count. Probed:
# no structural datum separates them this batch (ADR-0035 backstop already
# established this as the narrow un-structurable tail — 102/102 commander-legal
# reproduce, 0 miss/0 over-fire), so this arm is the residual source, additive
# with the structural Arm B (the caller's ``fire()`` dedups by key). CR 208.
_POWER_AGGREGATE_SYNTH_RX = re.compile(
    r"(?:total|greatest|combined) power of creatures you control"
    r"|creature spells? you cast with power \d+ or (?:greater|more)"
    r"|if you control [^.]*?with power \d+ or (?:greater|more)"
    r"|creature with power \d+ or (?:greater|more) enters"
    r" the battlefield under your control"
    r"|(?:total|greatest) power among (?:other )?creatures you control"
    r"|\bformidable\b",
    re.IGNORECASE,
)


def _matches_power_aggregate_idiom(oracle: str) -> bool:
    return bool(_POWER_AGGREGATE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_power_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``power_matters`` node for the aggregate power-scaler /
    Formidable tail (the deleted ``_POWER_MATTERS_MIRROR`` relocated
    verbatim)."""
    if not _matches_power_aggregate_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="power_matters",
        concept="synth_power_matters",
        scope="you",
        subject=(),
        desc="bucket-B power aggregate scaler / Formidable (CR 208/207.2c)",
    )


# ── batch T5-niche-a: pump_makers (bucket-A widen + bucket-B tail) ──────────
# CR 611.2c: the duration-scoped combat-trick BUFF. Two bucket-A widenings over
# the live effect-role ``Pump``/``PumpAll`` arm PLUS one bucket-B residue arm
# (the deleted ``PUMP_MATTERS_REGEX`` kept-mirror relocated), together closing
# the mirror-only gap from 344 -> 0 cards (measured, commander-legal corpus):
#
# (a) the FIXED positive gate widens to ALSO accept a positive ``toughness``
#     value (not power alone) — a "+0/+3" trick (Affa Guard Hound) is still a
#     genuine buff; checking power only silently dropped every +0/+N card.
# (b) phase frequently renders a temporary team/targeted buff as a
#     ``GenericEffect`` wrapping a nested ``Continuous`` static whose
#     ``modifications`` carry ``AddPower``/``AddToughness`` (Adamant Will,
#     Cavalier of Flame's "Creatures you control get +1/+0…") rather than a
#     top-level ``Pump``/``PumpAll`` effect tag — the SAME mechanic, a
#     different phase shape. Gated the SAME way: the unit (or a nested
#     wrapper) must carry a duration, and a static whose ``affected`` is
#     ``SelfRef`` is the firebreathing/self-buff veto (Clickslither,
#     Crazed Armodon — self_pump's country, not this lane); a
#     ``ParentTarget`` (the ability's own external target — Ajani Steadfast)
#     or a direct ``Typed`` filter (a "creatures you control" mass buff) both
#     count. Positive-value gate mirrors (a).
#
# The residual 77-card tail (X-based dynamic amounts with no raw text to
# ground a "+" check — Kessig Wolf Run's "+X/+0", Liliana of the Dark
# Realms's "+X/+X", Onward's "+X/+0 where X is its power") has no clean
# structural amount read (phase's dynamic ``power``/``toughness`` carries no
# positive/negative tell); relocated verbatim as the bucket-B tail, gap-gated
# against (a)+(b) — genuinely new fires from (a)/(b) all carry an explicit
# "until end of turn"/"end of combat" duration phrase (probed: 0 exceptions
# over the commander-legal corpus), so this stays additive, not a widen-risk.
def _pump_fixed_value(node: object) -> int | None:
    return getattr(node, "value", 0) or 0 if tag_of(node) == "Fixed" else None


def has_structural_pump_makers(tree: ConceptTree) -> bool:
    """A duration-scoped ``Pump``/``PumpAll`` effect with a positive fixed
    power OR toughness (widened from power-only), a "+"-grounded dynamic
    amount, OR a nested ``GenericEffect``/``Continuous``-static
    ``AddPower``/``AddToughness`` grant (the firebreathing self-buff
    excluded via the ``SelfRef``-affected veto)."""
    for unit in tree.units:
        if any(c.concept == "pump" for c in unit.effects):
            dur_unit = any(
                node_duration(n) is not None for n in iter_typed_nodes(unit.node)
            )
            for c in unit.effect_concepts("pump"):
                if not (dur_unit or node_duration(c.node)):
                    continue
                target_tag = tag_of(getattr(c.node, "target", None))
                if unit.kind == "Activated" and target_tag in (None, "SelfRef"):
                    continue  # firebreathing self-pump veto
                p = getattr(c.node, "power", None)
                t = getattr(c.node, "toughness", None)
                raw = c.raw or getattr(unit.node, "description", None) or ""
                pv, tv = _pump_fixed_value(p), _pump_fixed_value(t)
                has_plus = "+" in raw and target_tag != "SelfRef"
                # Power and toughness are gated INDEPENDENTLY (widened from
                # power-only): a Fixed amount decides on its OWN sign, a
                # dynamic/absent amount falls back to the shared "+"-grounded
                # tell — so a dynamic power + Fixed-zero toughness ("+1/+0"
                # scaling, Asari Captain) fires off power alone, and a
                # Fixed-zero power + Fixed toughness ("+0/+3", Affa Guard
                # Hound) fires off toughness alone.
                power_ok = (pv is not None and pv > 0) or (pv is None and has_plus)
                tough_ok = (tv is not None and tv > 0) or (tv is None and has_plus)
                if power_ok or tough_ok:
                    return True
        dur_unit = any(
            node_duration(n) is not None for n in iter_typed_nodes(unit.node)
        )
        if not dur_unit:
            continue
        for node in iter_typed_nodes(unit.node):
            if tag_of(node) != "GenericEffect":
                continue
            for st in getattr(node, "static_abilities", None) or ():
                if tag_of(getattr(st, "affected", None)) == "SelfRef":
                    continue  # firebreathing / self-buff veto
                mods = getattr(st, "modifications", None) or ()
                vals = (
                    getattr(m, "value", None)
                    for m in mods
                    if tag_of(m) in ("AddPower", "AddToughness")
                )
                if any(isinstance(v, int) and v > 0 for v in vals):
                    return True
    return False


_PUMP_MAKERS_SYNTH_RX = re.compile(PUMP_MATTERS_REGEX, re.IGNORECASE)


def _matches_pump_makers_idiom(oracle: str) -> bool:
    return bool(_PUMP_MAKERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_pump_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``pump_makers`` node for the X-based/dynamic-amount
    residue (the deleted ``PUMP_MATTERS_REGEX`` kept-mirror relocated,
    gap-gated against :func:`has_structural_pump_makers` — Kessig Wolf
    Run's "+X/+0", Liliana of the Dark Realms's "+X/+X", no raw text to
    ground a positive/negative dynamic-amount tell)."""
    if has_structural_pump_makers(tree):
        return None
    if not _matches_pump_makers_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="pump_makers",
        concept="synth_pump_makers",
        scope="you",
        subject=(),
        desc="bucket-B dynamic/X-amount combat-trick residue (CR 611.2c)",
    )


# ── batch T7-niche-c: toughness_combat toughness-as-value residual ─────────
# CR 510.1a (assign-combat-damage-equal-to-POWER default the Doran statics
# override) + 613.4c (layer 7c) + 604.3 (CDAs): STRUCTURAL — an
# ``AssignDamageFromToughness`` modification (Doran, Assault Formation) OR a
# Toughness-typed ``amount``/``count`` operand (Angelic Chorus, Loxodon
# Lifechanter). The residual: the toughness-as-VALUE idiom phase folds to a
# fixed/None operand instead of a typed Toughness ref — a token's P/T
# (Geralf, Soul Separator), a pump-X (Tip the Scales, Snowblind), mana/cost =
# toughness (Vhal, The Pride of Hull Clade) — relocates the deleted
# ``_TOUGHNESS_VALUE_MIRROR`` verbatim, gap-gated. Measured over the
# commander-legal corpus: 103 structural + 32 bucket-B, 0 drops, 0 adds.
def has_structural_toughness_combat(tree: ConceptTree) -> bool:
    """Whether an ``AssignDamageFromToughness`` modification exists, or a
    Toughness-typed ``amount``/``count`` ref (``toughness_combat``'s direct
    arm)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "AssignDamageFromToughness":
                return True
            for fname in ("amount", "count"):
                q = getattr(n, fname, None)
                if tag_of(q) != "Ref":
                    continue
                qty = getattr(q, "qty", None)
                qt = tag_of(qty)
                if qt == "Toughness" or (
                    qt == "Aggregate" and getattr(qty, "property", None) == "Toughness"
                ):
                    return True
    return False


def _arm_toughness_combat(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``toughness_combat`` node for the toughness-as-value
    residual (the deleted ``_TOUGHNESS_VALUE_MIRROR`` mirror relocated,
    gap-gated against :func:`has_structural_toughness_combat`)."""
    if has_structural_toughness_combat(tree):
        return None
    if _TOUGHNESS_VALUE_MIRROR.search(_REMINDER.sub(" ", tree.oracle or "")) is None:
        return None
    return _synthetic_concept(
        arm_id="toughness_combat",
        concept="synth_toughness_combat",
        scope="you",
        subject=(),
        desc="bucket-B toughness-as-value residue (CR 604.3)",
    )


# ── batch T7-niche-c: exert_matters Johan residual ──────────────────────────
# CR 701.43a (exert) + 702.20b (vigilance neutralizes exert's won't-untap):
# STRUCTURAL — a mass-vigilance grant onto your generic (no-subtype)
# creature board (Always Watching). The residual: Johan's unique "attacking
# doesn't cause creatures you control to tap this combat" replacement (a
# conditional, once-per-combat vigilance-alike CR 702.20b never structures)
# — the ENTIRE corpus census is the one card. Relocates the deleted
# ``_JOHAN_MIRROR`` verbatim, gap-gated. Measured over the commander-legal
# corpus: 1 card (Johan), no structural overlap, 0 drops, 0 adds.
def has_structural_exert_matters(tree: ConceptTree) -> bool:
    """Whether a mass-vigilance grant exists onto a generic (no-subtype)
    creature-you-control filter (``exert_matters``'s direct arm)."""
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword" or mod_keyword_name(mod) != "Vigilance":
                continue
            affected = getattr(sdef, "affected", None)
            if tag_of(affected) != "Typed":
                continue
            if "Creature" not in filter_core_types(affected):
                continue
            if filter_controller(affected) != "You" or filter_subtypes(affected):
                continue
            return True
    return False


_JOHAN_MIRROR = re.compile(
    r"attacking doesn'?t cause (?:creatures|them)[^.]*to tap", re.IGNORECASE
)


def _arm_exert_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``exert_matters`` node for the Johan-only "attacking
    doesn't cause tapping" residual (the deleted ``_JOHAN_MIRROR`` mirror
    relocated, gap-gated against :func:`has_structural_exert_matters`)."""
    if has_structural_exert_matters(tree):
        return None
    if _JOHAN_MIRROR.search(_REMINDER.sub(" ", tree.oracle or "")) is None:
        return None
    return _synthetic_concept(
        arm_id="exert_matters",
        concept="synth_exert_matters",
        scope="you",
        subject=(),
        desc="bucket-B Johan attacking-doesn't-tap residue (CR 702.20b)",
    )


# ── firebending_matters bucket-B (ADR-0036/0037 Stage 5 T8-misc-sweep) ─────────
# CR 702.189a/b: Firebending is a keyword ability, printed OR granted. Bearers
# (the card's own Scryfall keyword array carries "firebending") route
# structurally in the crosswalk lane itself — never here, this arm never sees
# keywords. A card GRANTING firebending to another permanent WITHOUT bearing it
# structures as a typed ``AddKeyword`` static naming Firebending
# (:func:`has_structural_firebending_grant` — probed live: Fire Nation Cadets/
# Palace/Turret, Iroh Dragon of the West, Sozin's Comet — read directly, zero
# regex). The genuine bucket-B tail is a firebending grant baked into a
# make_token spec's OWN printed body (Fire Nation Attacks/Occupation,
# Firebender Ascension, Cruel Administrator's raid token) — phase never emits
# an AddKeyword for a token's own ability, so the token-creation idiom is the
# sole surviving text dependency. The narrow ``with firebending`` anchor (vs
# the deleted flat ``\bfirebend(?:ing|s)?\b`` mirror) deliberately drops
# Firebending Lesson — that card's own NAME contains "Firebending"
# ("Firebending Lesson deals 2 damage…", no mechanic relevance at all), a
# self-reference the flat mirror mis-fired on (adjudicated over-fire, shed).
_FIREBENDING_GRANT_TOKEN_RX = re.compile(r"with firebending\b", re.IGNORECASE)


def has_structural_firebending_grant(tree: ConceptTree) -> bool:
    """Whether phase carries a typed ``AddKeyword`` static naming Firebending
    — a non-bearer GRANT (Sozin's Comet, Iroh Dragon of the West, Fire Nation
    Cadets/Palace/Turret)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "AddKeyword":
                continue
            kw = getattr(n, "keyword", None)
            if getattr(kw, "key", None) == "Firebending":
                return True
    return False


def _arm_firebending_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``firebending_matters`` node for the bucket-B firebending
    grant baked into a token's own printed body (Fire Nation Attacks/
    Occupation, Firebender Ascension, Cruel Administrator) — phase emits no
    AddKeyword for a make_token spec's own ability."""
    if has_structural_firebending_grant(tree):
        return None
    oracle = _REMINDER.sub(" ", tree.oracle or "")
    if not _FIREBENDING_GRANT_TOKEN_RX.search(oracle):
        return None
    return _synthetic_concept(
        arm_id="firebending_matters",
        concept="synth_firebending_matters",
        scope="you",
        subject=(),
        desc="bucket-B firebending grant baked into a token body (CR 702.189)",
    )


# ── station_matters bucket-B (ADR-0036/0037 Stage 5 T8-misc-sweep) ─────────────
# CR 702.184a/b: a permanent naming Spacecraft/Planet (a removal/count spell
# targeting or referencing the type) structures as a typed ``Typed`` filter
# naming the subtype (:func:`has_structural_station_reference` — Focus Fire,
# Gravkill, Beyond the Quiet, Embrace Oblivion, Invasive Maneuvers, Pulsar
# Squadron Ace, Scrounge for Eternity, Thaumaton Torpedo — 8/9 of the live
# non-bearer "matters" set, probed live). A card CHARGING one (putting charge
# counters on a Spacecraft/Planet target — Drill Too Deep, Systems Override)
# structures as a ``PutCounter`` node with ``counter_type == "charge"``
# co-occurring, in the SAME ability unit, with a ``Typed`` filter naming the
# subtype (:func:`has_structural_station_charge` — Systems Override guards its
# PutCounter behind a sibling ``TargetMatchesFilter`` condition rather than the
# PutCounter's own target, so the read is unit-scoped, not target-nested). The
# genuine bucket-B tail is Tractor Beam's own printed "Enchant creature or
# Spacecraft" restriction — phase drops the Aura's enchant-target subtype
# entirely (widens to bare ``Permanent``), a single-card lane (the free_plot
# Fblthp precedent).
_STATION_SUBTYPES: frozenset[str] = frozenset({"Spacecraft", "Planet"})
_STATION_ENCHANT_GAP_RX = re.compile(
    r"\benchant\b[^.\n]*\b(?:spacecraft|planet)\b", re.IGNORECASE
)


def has_structural_station_reference(tree: ConceptTree) -> bool:
    """Whether phase carries a typed filter naming the Spacecraft/Planet
    subtype anywhere (a removal/count spell payoff)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Typed" and set(filter_subtypes(n)) & _STATION_SUBTYPES:
                return True
    return False


def has_structural_station_charge(tree: ConceptTree) -> bool:
    """Whether ONE ability unit carries both a charge-counter ``PutCounter``
    and a typed filter naming Spacecraft/Planet — unit-scoped so an unrelated
    charge ability elsewhere on the same card never co-fires."""
    for unit in tree.units:
        has_charge = False
        has_subtype = False
        for n in iter_typed_nodes(unit.node):
            t = tag_of(n)
            if t == "PutCounter" and getattr(n, "counter_type", None) == "charge":
                has_charge = True
            elif t == "Typed" and set(filter_subtypes(n)) & _STATION_SUBTYPES:
                has_subtype = True
        if has_charge and has_subtype:
            return True
    return False


def _arm_station_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``station_matters`` node for the bucket-B enchant-target
    gap (Tractor Beam) — phase drops the Aura's own "or Spacecraft"
    restriction entirely."""
    if has_structural_station_reference(tree) or has_structural_station_charge(tree):
        return None
    oracle = _REMINDER.sub(" ", tree.oracle or "")
    if not _STATION_ENCHANT_GAP_RX.search(oracle):
        return None
    return _synthetic_concept(
        arm_id="station_matters",
        concept="synth_station_matters",
        scope="you",
        subject=(),
        desc="bucket-B Aura enchant-target Spacecraft restriction (CR 702.184)",
    )


# ── arm: tap_untap_matters Unknown-mode becomes-(un)tapped tail ────────────────
# The step-7 open tombstone (ADR-0039 task #82): "whenever ~ becomes tapped/
# untapped" (CR 603.2e/701.26) is a trigger MODE phase sometimes can't
# classify — Darksteel Garrison's "fortified land becomes tapped", Grand
# Marshal Macie's "becomes untapped", Roots of Life's "a land of the chosen
# type an opponent controls becomes tapped", Royal Decree's "a Swamp,
# Mountain, black permanent, or red permanent becomes tapped" all fall to the
# untagged ``MirrorVariant(key="Unknown", inner=<raw trigger head clause>)``
# wrapper phase uses when no ``S_triggers.mode`` tag matches, so
# ``_trigger_event`` falls through to ``"other"``. ``mode.inner`` carries the
# EXACT unparsed trigger-head text ("Whenever fortified land becomes tapped"
# — the effect tail is a SEPARATE typed ``execute`` node), so reading it is a
# typed-field read of the trigger's own residue, never a whole-oracle scan —
# corpus-verified (scan1.py, 2026-07-12) to hit ONLY these 4 Unknown-mode
# triggers card-wide (every other "becomes tapped/untapped" occurrence in the
# corpus is either already phase-classified to ``Taps``/``Untaps`` or belongs
# to an unrelated sibling clause the ``mode.inner`` anchor never reaches).
_BECOMES_TAPPED_MODE_RE = re.compile(r"\bbecomes? tapped\b", re.IGNORECASE)
_BECOMES_UNTAPPED_MODE_RE = re.compile(r"\bbecomes? untapped\b", re.IGNORECASE)

_TAP_UNTAP_TRIGGER_EVENTS: frozenset[str] = frozenset({"taps", "untaps", "tapsformana"})


def has_structural_tap_untap_matters(tree: ConceptTree) -> bool:
    """Whether the card already carries a phase-classified becomes-(un)tapped
    trigger (``Taps``/``Untaps``/``TapsForMana`` mode) — the tap_untap_matters
    TYPED gate, shared with :func:`_arm_tap_untap_becomes`'s own gap gate
    below (one source, no drift) so a phase-classified card never doubles."""
    return any(
        u.origin == "trigger" and u.trigger_event in _TAP_UNTAP_TRIGGER_EVENTS
        for u in tree.units
    )


def _arm_tap_untap_becomes(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``taps``/``untaps`` node for the Unknown-mode becomes-
    (un)tapped trigger tail phase leaves at ``event=='other'`` (CR 603.2e:
    "becomes tapped"/"becomes untapped" are named-event triggers; CR
    701.26a/701.26b: tap/untap). Reads ONLY residue that phase itself filed
    UNDER this same Unknown-mode trigger unit — its ``mode.inner`` head
    residue, plus (Royal Decree's "a Swamp, Mountain, black permanent, OR
    RED PERMANENT becomes tapped": the trailing disjunct overflows the mode
    parse entirely and lands as a nested ``other``-concept ``Unimplemented``
    effect node INSIDE the same trigger's own execute chain) that unit's own
    ``effect_concepts("other")`` raws. Never a sibling unit, never the
    whole-card oracle — a card whose becomes-tapped mention lives in an
    UNRELATED ability (Orcish Mine's compound upkeep-trigger clause loss,
    The Caffeinated Runner's granted delayed trigger on an activated
    ability) never fires this arm; those are documented, out-of-scope,
    no-residue gaps a wider whole-card scan would be needed for. Gap-gated
    on :func:`has_structural_tap_untap_matters` so a phase-classified
    ``Taps``/``Untaps``/``TapsForMana`` trigger never doubles. Emits the
    REAL "taps"/"untaps" concept (mirroring the vocabulary
    :func:`_trigger_event`'s ``mode``->event map already uses for those
    tags), so the ``_tap_untap_matters`` lane reads it via one extra
    synthesized-node branch on its existing typed walk — no text re-scan."""
    if has_structural_tap_untap_matters(tree):
        return None
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        mode = getattr(unit.node, "mode", None)
        if not (isinstance(mode, MirrorVariant) and mode.key == "Unknown"):
            continue
        residue = [mode.inner if isinstance(mode.inner, str) else ""]
        residue.extend(c.raw for c in unit.effect_concepts("other") if c.raw)
        text = " ".join(residue)
        if _BECOMES_UNTAPPED_MODE_RE.search(text):
            return _synthetic_concept(
                arm_id="tap_untap_becomes",
                concept="untaps",
                scope="you",
                subject=(),
                desc="Unknown-mode becomes-untapped trigger (CR 701.26b)",
            )
        if _BECOMES_TAPPED_MODE_RE.search(text):
            return _synthetic_concept(
                arm_id="tap_untap_becomes",
                concept="taps",
                scope="you",
                subject=(),
                desc="Unknown-mode becomes-tapped trigger (CR 701.26a)",
            )
    return None


# ── base_pt_set / base_power_matters / creatures_matter — base-P/T grammar
# stragglers (ADR-0039 task #82 grammar sprint) ───────────────────────────
# CR 613.4b: a base-P/T-SET idiom whose clause phase's grammar can't
# structure at all (a "have <subject>'s base power [and toughness] ...
# become <value>" scalar/copy re-assignment, a conditionally-gated "is a(n)
# <Type> with base power and toughness N/N" fixed type-change, or a mass
# "creatures you control have base power and toughness X/X, where X is
# ..." scalar) parks the WHOLE clause as an ``Unimplemented`` residue that
# survives WITH the hook text intact — the SAME whole-clause-drop shape
# ``group_hug_draw``'s Grothama arm bridges. Retired off their
# ``bridge_ledger.py`` rows this session: the raw regex reads move from the
# LANE itself (``bridge_fires``, evaluated at signal-extraction time) into
# this gap-gated tree-BUILD-time stage — ``_base_pt_set`` now reads pure
# structure via ``effect_concepts("base_pt_set")``.
def has_structural_base_pt_set(tree: ConceptTree) -> bool:
    """Cheap corpus-wide presence check: does ANY unit already carry a
    typed base-P/T SET node (``SetPower``/``SetToughness``/``SwitchPT``, or
    an ``Animate`` effect with a non-None ``power``/``toughness`` field)
    anywhere in the tree — the self-retiring gap gate for the three
    ``base_pt_set`` residue arms below (a synthesis arm never doubles a
    clause phase already structures). Deliberately looser than the
    ``_base_pt_set`` lane's own precise sites-loop (no hook-text/subject-
    resolution replay, no off-battlefield gate) — a presence-only check is
    sufficient here because the LANE's own precise gates still decide
    whether a REAL typed node fires the signal; this gate only decides
    whether a NEW synthetic node should exist at all.
    """
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            t = tag_of(n)
            if t in ("SetPower", "SetToughness", "SwitchPT"):
                return True
            if t == "Animate" and (
                getattr(n, "power", None) is not None
                or getattr(n, "toughness", None) is not None
            ):
                return True
    return False


def _base_pt_unimplemented_descs(tree: ConceptTree) -> Iterator[str]:
    """Every ``Unimplemented`` node's description reachable ANYWHERE in the
    tree (mirrors the retired ``bridge_ledger._unimplemented_descs_
    anywhere`` verbatim). NOT scoped to ``unit.effects`` — a base_pt_set
    residue can be nested under a STATIC unit or a granted-ability chain.
    Reading the RESIDUE's own description (not ``tree.oracle``) matters:
    phase NORMALIZES verb conjugation in its ``Unimplemented`` text (Better
    Offer's printed "It perpetually HAS base power and toughness X/X"
    survives in the residue as "HAVE base power and toughness X/X" — the
    infinitive form) — scanning the printed oracle instead would silently
    miss every conjugated ("has"/"is") card the residue's own canonical
    text still matches (corpus-verified regression: an oracle-text-only
    scan drops Better Offer from both base_pt_set and creatures_matter)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented":
                yield getattr(n, "description", "") or ""


_BASE_PT_HAVE_BECOME_SYNTH_RX = re.compile(
    r"\bhave\b.*?\bbase power\b.*?\bbecome\b", re.IGNORECASE
)


def _arm_base_pt_have_become(tree: ConceptTree) -> ConceptNode | None:
    """A "have <subject>'s base power [and toughness] ... become <value>"
    scalar/copy re-assignment (Ambassador Blorpityblorpboop's sticker-power
    scalar, Tanazir Quandrix/Unruly Krasis's "become equal to ~'s power/
    toughness" mass idiom — CR 613.4b) parked as a whole-clause
    ``Unimplemented`` residue. Gap-gated on :func:`has_structural_base_pt_set`
    so a card phase later structures stands this arm down automatically.
    3/31,622 commander-legal (Ambassador Blorpityblorpboop, Tanazir
    Quandrix, Unruly Krasis — the exact former ``base_pt_have_become_
    residue`` bridge census)."""
    if has_structural_base_pt_set(tree):
        return None
    if not any(
        _BASE_PT_HAVE_BECOME_SYNTH_RX.search(d)
        for d in _base_pt_unimplemented_descs(tree)
    ):
        return None
    return _synthetic_concept(
        arm_id="base_pt_have_become",
        concept="base_pt_set",
        scope="any",
        subject=(),
        desc="'have ... base power ... become' scalar/copy re-assignment (CR 613.4b)",
    )


_BASE_PT_IS_A_TYPE_WITH_SYNTH_RX = re.compile(
    r"\bis an? [^.]*\bwith base power and toughness \d+/\d+\b", re.IGNORECASE
)


def _arm_base_pt_is_a_type_with(tree: ConceptTree) -> ConceptNode | None:
    """A conditionally-gated "is a(n) <Type> with base power and toughness
    N/N" fixed type-change (Circle of the Moon Druid's "During your turn,
    ~ is a Bear with base power and toughness 4/2" — CR 613.4b); the
    UNCONDITIONAL sibling shape (Displaced Dinosaurs/Sauron Dino Devotee/
    Ultron) already decomposes into typed SetPower/SetToughness/AddType
    nodes phase emits directly (the ``has_structural_base_pt_set`` gap
    correctly stands THOSE cards down) — this arm covers ONLY the
    conditional-wrapper shape phase's grammar still parks whole. 1/31,622
    commander-legal (Circle of the Moon Druid — the exact former
    ``base_pt_is_a_type_with_residue`` bridge census)."""
    if has_structural_base_pt_set(tree):
        return None
    if not any(
        _BASE_PT_IS_A_TYPE_WITH_SYNTH_RX.search(d)
        for d in _base_pt_unimplemented_descs(tree)
    ):
        return None
    return _synthetic_concept(
        arm_id="base_pt_is_a_type_with",
        concept="base_pt_set",
        scope="any",
        subject=(),
        desc="conditional 'is a(n) ... with base power and toughness N/N' (CR 613.4b)",
    )


_BASE_PT_MASS_WHERE_X_SYNTH_RX = re.compile(
    r"\bhave base power and toughness [A-Za-z]/[A-Za-z]\b", re.IGNORECASE
)


def _arm_base_pt_mass_where_x(tree: ConceptTree) -> ConceptNode | None:
    """A mass "creatures you control have base power and toughness X/X,
    where X is <scalar definition>" idiom (Candlekeep Inspiration's exile/
    graveyard instant-or-sorcery-or-Adventure count — CR 613.4b) parked as
    a whole-clause ``Unimplemented`` residue. Serves BOTH ``base_pt_set``
    (this arm's own concept, read by ``_base_pt_set`` via
    ``effect_concepts``) AND ``creatures_matter`` (a mass team base-P/T
    setter is a go-wide payoff too, CR 613.4b sibling reading — the
    ``_creatures_matter`` lane keys off THIS arm's id specifically via the
    synthesized node's ``arm_id``, never the sibling single-target arms
    above, so it never widens past the go-wide idiom). 1/31,622
    commander-legal (Candlekeep Inspiration — the exact former
    ``base_pt_mass_where_x_residue`` / ``candlekeep_inspiration_mass_
    where_x_creatures_matter`` byte-identical bridge census — one node
    retires both rows)."""
    if has_structural_base_pt_set(tree):
        return None
    if not any(
        _BASE_PT_MASS_WHERE_X_SYNTH_RX.search(d)
        for d in _base_pt_unimplemented_descs(tree)
    ):
        return None
    return _synthetic_concept(
        arm_id="base_pt_mass_where_x",
        concept="base_pt_set",
        scope="any",
        subject=(),
        desc=(
            "mass 'creatures you control have base power and toughness X/X' (CR 613.4b)"
        ),
    )


def has_structural_base_power_ref(tree: ConceptTree) -> bool:
    """Whether a typed ``PtComparison(scope='Base')`` node is reachable
    anywhere in the tree — the SAME typed gate the ``_base_power_matters``
    lane itself reads (CR 613.4b sentence 2)."""
    return any(
        tag_of(n) == "PtComparison" and getattr(n, "scope", None) == "Base"
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


def _arm_base_power_ref_conjunctive(tree: ConceptTree) -> ConceptNode | None:
    """A CONJUNCTIVE "base power and toughness N/N" reference (Duskana, the
    Rage Mother; Bess, Soul Nourisher — CR 613.4b sentence 2) phase's
    clause grammar drops with ZERO trace (no ``PtComparison`` node at
    all) — distinct from the single-stat "base power N" / "base toughness
    N" reference form phase structures directly as a typed node (the
    ``has_structural_base_power_ref`` gap this arm stands down on for
    those 4 siblings — Rapid Augmenter, Sword of the Squeak, Zinnia,
    Valley's Voice, Primo, the Unbounded). Reuses ``supplement.py``'s OWN
    ``_BASE_POWER_REF`` combinator scan verbatim — the SAME six-token
    phrase anchor the retired legacy ``_recover_base_power_ref`` used, so
    the blast radius matches byte-for-byte (6 corpus hits total, 4 already
    structurally covered, 2 left — the exact former ``duskana_bess_base_
    pt_and_toughness_ref`` bridge census)."""
    if has_structural_base_power_ref(tree):
        return None
    oracle = re.sub(r"\([^)]*\)", " ", tree.oracle or "")
    if not _anchored(oracle, "with base", _BASE_POWER_REF):
        return None
    return _synthetic_concept(
        arm_id="base_power_ref_conjunctive",
        concept="base_power_matters",
        scope="you",
        subject=(),
        desc="conjunctive 'with base power and toughness N' reference (CR 613.4b)",
    )
