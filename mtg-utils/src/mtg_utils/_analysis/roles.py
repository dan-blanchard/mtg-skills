"""Template roles — what a card DOES for the Command Zone template.

One owner for the per-card role facts every deck surface counts: the four
hard-counted template roles (``ramp`` / ``card_draw`` / ``interaction`` /
``board_wipe``, plus ``lands``) via :func:`role_of`, the ramp read on its own via
:func:`is_ramp` (deck-stats, mana-audit, the ranking floor, and the tuner's cut
side all ask just that), and the Tier-2 advisory :func:`protects` (ADR-0024).

Every role is a VIEW over the signal path — a ``theme_presets`` preset (itself a
view over ``extract_signals``) and, where the compat Card carries a sharper read, the
card's IR. Nothing here hand-rolls a second detector: the bands these roles are
measured against live in ``budgets``; the search that SOURCES a role reads the same
preset the role counts by (ADR-0051).

The text reads are the documented no-coverage degrades: a card the signal path
cannot see (no ``oracle_id``, no phase parse, no sidecar — a synthetic fixture, a
cube pool run with no card-data, a set newer than the phase pin) answers ramp from
``card_classify.ramp_by_text`` and removal (``interaction``) from
``card_classify.removal_reach_by_text``. ``protects`` has no degrade: such a card
is not protection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._analysis._subtypes import CREATURE_SUBTYPES, LAND_SUBTYPES
from mtg_utils._analysis.tree_synthesis.mechanics_misc import OUTLAW_SUBTYPES
from mtg_utils._card_ir.compat_lookup import ir_for
from mtg_utils._card_ir.crosswalk.reads import (
    ObjectFacts,
    mana_ability_gates,
    mana_spell_type_restriction,
    produced_kind,
    tag_of,
)
from mtg_utils._card_ir.trees import object_facts, trees_for
from mtg_utils.card_classify import is_land, ramp_by_text, removal_reach_by_text
from mtg_utils.card_ir import Card
from mtg_utils.theme_presets import get_preset, has_signal_coverage

if TYPE_CHECKING:
    from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode

# Targeted removal + counterspells fold together into one `interaction` role (ADR-0024).
# creature-edict (forced sacrifice — Diabolic Edict, Fleshbag) is removal that bypasses
# hexproof/indestructible, so it counts too.
# `creature-removal` is deliberately EXCLUDED: its removal SPELLS are already matched by
# `removal`, while its Fight/Infect/Wither KEYWORDS tag static combat creatures (CR
# 702.90a infect is a combat ability, not spot removal) — over-counting Infect beaters
# as interaction and then cutting a poison payoff to "trim the over-band role".
#
# Task #86 (the `removal` preset's structural-view flip): pacify auras
# ("Enchanted creature can't attack or block" — Pacifism, Arrest) briefly
# dropped OUT of `interaction` here — the 9-key signal_keys union `removal`
# reads has no lane for "neutralizes a permanent without destroying/
# exiling/countering/bouncing/fighting/-X'ing it" (the task #83/#86 scoping
# pass adjudicated Pacifism/Arrest as structurally `enchantments_matter`,
# not a removal-family effect — correct routing, not a lane bug).
#
# Task #87 restores the credit via the DEDICATED structural concept this
# comment used to flag as out of scope: `pacify-aura`
# (theme_presets.py — signal_keys=("pacify_makers",),
# crosswalk_signals._pacify_makers). Deliberately its OWN preset, not
# folded into `removal`'s signal_keys union — CR 611.2 keeps "neutralizes"
# and "removes" genuinely distinct facts; `removal`'s should_not_match
# pin on Pacifism stays in force.
#
# Damage that only ever reaches a player is not interaction: the player loses life
# (CR 120.3a) and nothing leaves the board — Mogis, Guttersnipe, Sulfuric Vortex are
# the `direct_damage` punisher lane, which the `removal` preset no longer reads. Burn
# that can reach a permanent ("any target", CR 115.4) fires the `removal` lane itself.
_INTERACTION_PRESETS = (
    "removal",
    "counterspell",
    "bounce",
    "creature-edict",
    "pacify-aura",
)


def _matches_preset(card: dict, name: str) -> bool:
    try:
        return get_preset(name).matches(card)
    except KeyError:
        return False


def _matches_any(card: dict, names: Sequence[str]) -> bool:
    return any(_matches_preset(card, name) for name in names)


# Mana whose colors come from the deck itself, so a colorless deck gets none — each
# per its rulings. Arcane Signet / Commander's Sphere: "If your commander is a card
# that has no colors in its color identity, [it] produces no mana. It doesn't produce
# {C}." Mox Amber: "If your legendary creatures and legendary planeswalkers are all
# colorless, you can activate Mox Amber's ability, but you won't add any mana."
# Chrome Mox: if "the exiled card is colorless", it "can't add mana" — and under a
# colorless commander every card the deck can exile is.
_DECK_COLORED_MANA = frozenset(
    {
        "AnyInCommandersColorIdentity",
        "AnyOneColorAmongPermanents",
        "ChoiceAmongExiledColors",
    }
)


# Words phase's spell-type restrictions use (CR 106.6) that aren't a subtype.
_CARD_TYPE_WORDS = frozenset(
    {
        "artifact",
        "battle",
        "creature",
        "enchantment",
        "instant",
        "kindred",
        "land",
        "planeswalker",
        "sorcery",
    }
)
_SUPERTYPE_WORDS = frozenset({"basic", "legendary", "snow", "world"})
# Lowercase subtype vocabulary: a word outside every known list is never condemned.
_SUBTYPE_WORDS = frozenset(t.lower() for t in (*CREATURE_SUBTYPES, *LAND_SUBTYPES))
_OUTLAWS = frozenset(t.lower() for t in OUTLAW_SUBTYPES)


def _restriction_word_admits(word: str, facts: ObjectFacts) -> bool | None:
    """One word of a spell-type restriction against an object; ``None`` for a word
    this read doesn't know."""
    if word.startswith("non") and len(word) > 3:
        inner = _restriction_word_admits(word[3:], facts)
        return None if inner is None else not inner
    if word == "colorless":
        return not facts.colors
    if word == "multicolored":
        return len(facts.colors) >= 2
    if word == "outlaw":  # CR 700.12
        return any(facts.has_subtype(t) for t in _OUTLAWS)
    if word in _CARD_TYPE_WORDS:
        return facts.has_type(word)
    if word in _SUPERTYPE_WORDS:
        return facts.has_supertype(word)
    if word in _SUBTYPE_WORDS:
        return facts.has_subtype(word)
    return None


def _restriction_admits(spell_type: str, facts: ObjectFacts) -> bool:
    """Whether phase's spell-type restriction lets its mana cast the object (CR
    106.6). A list ("Instant, Sorcery, Demon, and Spirit"; "Vampire, Cleric,
    And/or Demon") admits what any entry admits; an entry's words all must match
    ("Colorless Eldrazi"). An entry with a word this read doesn't know admits:
    restricted mana is never condemned on vocabulary alone."""
    text = spell_type.lower()
    for joiner in (" and/or ", " and ", " or "):
        text = text.replace(joiner, ",")
    for entry in (e.split() for e in text.split(",")):
        if not entry:
            continue
        answers = [_restriction_word_admits(w, facts) for w in entry]
        if None in answers or all(answers):
            return True
    return False


# The share of the deck's nonland cards a restricted source must be able to pay for
# to count as ramp when it can't cast a commander (2026-10-05): a third, so the
# deck usually holds something to spend it on.
_RESTRICTED_MANA_SHARE = 1 / 3


@dataclass(frozen=True)
class DeckMana:
    """What a deck can do with the mana a source makes: the deck context that makes
    a mana source live or dead (:func:`is_ramp`'s ``deck_mana``).

    A mana source is dead when the deck can't use what it makes: deck-colored mana
    under a colorless commander, or mana restricted to a spell type that neither a
    commander nor a third of the deck's nonland cards satisfies (The Mightstone and
    Weakstone's artifact-only mana is ramp in an artifact deck, whatever its
    commander).
    """

    #: The commanders' combined color identity; ``None`` without a commander.
    identity: frozenset[str] | None
    commanders: tuple[ObjectFacts, ...]
    #: The deck's nonland cards (commanders included) with their copies.
    spells: tuple[tuple[ObjectFacts, int], ...]
    # oracle_id -> dead-mana reason (or None), and spell type -> whether the deck can
    # spend it, so a card searched, ranked and counted in one pass is read once.
    _dead: dict[str, str | None] = field(
        default_factory=dict, compare=False, repr=False
    )
    _usable: dict[str, bool] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def of(
        cls,
        commanders: Sequence[Mapping | None],
        spells: Sequence[tuple[Mapping, int]] = (),
    ) -> DeckMana:
        """The context for a deck's commander records and its nonland cards."""
        recs = [c for c in commanders if c]
        identity = (
            frozenset(color for c in recs for color in c.get("color_identity") or ())
            if recs
            else None
        )
        # Mana is spent casting them, so each is read as the spell it is (Grist,
        # the Hunger Tide is a creature spell).
        return cls(
            identity=identity,
            commanders=tuple(object_facts(dict(c), zone="elsewhere") for c in recs),
            spells=tuple(
                (object_facts(dict(r), zone="elsewhere"), q) for r, q in spells
            ),
        )

    def dead_mana(self, card: Mapping) -> str | None:
        """Why the card's mana does nothing for this deck, or ``None`` when it's
        usable. Dead only when EVERY mana ability is (Eldrazi Temple's plain {C}
        keeps it live); a card phase hasn't parsed is never condemned."""
        key = card.get("oracle_id") or card.get("name") or ""
        if key not in self._dead:
            self._dead[key] = self._first_dead_reason(card)
        return self._dead[key]

    def _first_dead_reason(self, card: Mapping) -> str | None:
        first: str | None = None
        for tree in trees_for(dict(card)):
            for unit in tree.units:
                for node in unit.iter_typed():
                    if tag_of(node) != "Mana":
                        continue
                    reason = self._dead_reason(node)
                    if reason is None:
                        return None
                    first = first or reason
        return first

    def _dead_reason(self, node: TypedMirrorNode) -> str | None:
        if produced_kind(node) in _DECK_COLORED_MANA and self.identity == frozenset():
            return "makes no mana under a colorless commander"
        spell_type = mana_spell_type_restriction(node)
        if spell_type and not self._can_spend(spell_type):
            return (
                f"its mana can only cast {spell_type.lower()} spells, and neither a "
                "commander nor a third of the deck is one"
            )
        return None

    def _can_spend(self, spell_type: str) -> bool:
        if spell_type not in self._usable:
            total = sum(q for _, q in self.spells)
            usable = sum(
                q for f, q in self.spells if _restriction_admits(spell_type, f)
            )
            self._usable[spell_type] = any(
                _restriction_admits(spell_type, c) for c in self.commanders
            ) or (total > 0 and usable / total >= _RESTRICTED_MANA_SHARE)
        return self._usable[spell_type]


def _ir_draws(ir: Card) -> bool:
    """Does the card's IR carry card advantage for YOU (the structured mirror of
    the ``card-draw`` / ``cantrip`` presets)? Phase projects every "draw a card" to
    ``category="draw"`` with the drawer in ``scope`` — ``you`` (Divination,
    Phyrexian Arena, Rhystic Study) or symmetric ``any`` (Howling Mine). Connive
    (``category="connive"``: "draw a card, then discard") is card advantage too —
    a distinct category the draw-word regex catches only via reminder text. An
    ``opp``-only draw (a giveaway) doesn't fill your card_draw slot.

    More precise than the presets, which match the word "draw" anywhere — including
    an OPPONENT'S draw (Underworld Dreams), a draw PAYOFF ("whenever you draw …" —
    Nadir Kraken), and reminder text — none of which is a draw SOURCE.

    NOT a superset of the ``card-draw`` PRESET, though: this compat-``Card``
    walk only ever tags a whole-ability's DIRECT effect chain ``category="draw"``
    — a ``draw_for_each`` fired from a nested branch (a ``Vote``
    ``per_choice_effect``, a granted ``GrantTrigger``/``CreateDelayedTrigger``
    descent — Truth or Consequences, Blitzball Stadium, Cosima // The
    Omenkeel) never surfaces here at all (task #93 corpus census: 10
    commander-legal cards fire the crosswalk's ``draw_for_each`` key with no
    matching ``_ir_draws`` category — see :func:`role_of`'s own union)."""
    return any(
        (e.category == "draw" and e.scope in ("you", "any")) or e.category == "connive"
        for ab in ir.all_abilities()
        for e in ab.effects
    )


def is_ramp(card: dict, *, deck_mana: DeckMana | None = None) -> bool:
    """Does this NONLAND card accelerate your mana — the template's ``ramp`` role?

    THE ramp answer (ADR-0051): the ``ramp`` preset, a view over the signal path
    (rocks / dorks / rituals / granted mana, land-fetch-to-battlefield, mana
    amplifiers, extra land drops, Treasure makers you keep). A land is never ramp —
    it is the mana base (CR 305), counted by the ``lands`` role and the land band.

    A card the signal path cannot see at all (``has_signal_coverage`` false: no
    ``oracle_id``, no phase parse, no card-data) degrades to
    ``card_classify.ramp_by_text`` — one of the two no-coverage text reads (the
    other is :func:`role_of`'s removal), so a no-sidecar ``deck-stats`` / cube
    goldfish still counts its rocks.

    ``deck_mana`` is the deck context: with it, a source whose mana is dead for this
    deck (:meth:`DeckMana.dead_mana`: Arcane Signet under a colorless commander) is
    not ramp. Without it the answer is the card's alone."""
    if is_land(card):
        return False
    ramp = (
        ramp_by_text(card)
        if not has_signal_coverage(card)
        else _matches_preset(card, "ramp")
    )
    return ramp and (deck_mana is None or deck_mana.dead_mana(card) is None)


def role_of(card: dict, *, deck_mana: DeckMana | None = None) -> set[str]:
    """Hard-counted template roles a card fills (a card may fill several).

    ``lands`` reads the type line; ``ramp`` is :func:`is_ramp` (the ``ramp`` preset,
    with the text degrade for a card the signal path can't see, and ``deck_mana``'s
    dead-mana veto when the deck context is given); ``board_wipe`` is
    :func:`is_board_wipe` (the ``board-wipe`` preset). ``card_draw`` reads the
    candidate's Card IR when available (the ``draw`` category), degrading to the
    curated presets when the card has no IR. ``interaction`` is
    :func:`is_interaction` (its presets). A card phase has no concept trees for (a set
    newer than the phase pin) reads its removal from
    ``card_classify.removal_reach_by_text`` instead — the degrade, and the gate,
    ``twohg_scan``'s removal reach uses — so ``set-scan`` still counts a new set's
    removal.

    ``card_draw`` ALSO unions in the ``card-draw`` PRESET unconditionally
    (task #93) — ``_ir_draws`` alone under-counts: it only tags a whole-
    ability's DIRECT effect chain, so a ``draw_for_each`` reached only via
    a nested branch (Vote's ``per_choice_effect``, a granted
    ``GrantTrigger``/``CreateDelayedTrigger`` descent — Truth or
    Consequences, Master of Ceremonies, Blitzball Stadium, Cosima // The
    Omenkeel) fires the crosswalk key/preset (``card-draw`` unions
    ``card_draw_engine`` + ``draw_for_each`` since task #86) but never
    ``_ir_draws``'s own category walk. Corpus-verified (32,521
    commander-legal cards): 10 cards fire ``draw_for_each`` with no
    matching ``_ir_draws`` hit; this union closes all 10 with no new
    false positive (the preset itself is already the trusted source for
    the no-IR fallback below, unchanged)."""
    roles: set[str] = set()
    ir = ir_for(card)
    if is_land(card):
        roles.add("lands")
    elif is_ramp(card, deck_mana=deck_mana):
        roles.add("ramp")
    draws = (
        (ir is not None and _ir_draws(ir))
        or _matches_preset(card, "card-draw")
        or (ir is None and _matches_preset(card, "cantrip"))
    )
    if draws:
        roles.add("card_draw")
    if is_board_wipe(card):
        roles.add("board_wipe")
    if is_interaction(card):
        roles.add("interaction")
    return roles


def is_board_wipe(card: dict) -> bool:
    """THE board-wipe answer (ADR-0051, like :func:`is_ramp`): the ``board-wipe``
    preset, a view over the signal path — the ``mass_removal`` and
    ``mass_bounce`` keys (destroy, exile, tuck, damage, sacrifice, bounce and
    symmetric shrink sweeps, an overloaded spell's included — CR 702.96a) plus
    a toughness shrink on a population of creatures not limited to yours,
    one-shot or continuous, one-sided or not (the ``population_shrink`` key —
    Massacre Wurm, Elesh Norn, Grand Cenobite). The tuner sources the role by
    the same preset (:data:`ROLE_SEARCH`).

    Why a one-sided shrink counts (the one statement of it; the preset, its
    key and ADR-0051 point here): the template job is clearing the
    opponents' board. Massacre Wurm's -2/-2 to the opponents' creatures does
    that as surely as a one-sided destroy (Plague Wind) or an overloaded bounce
    (Cyclonic Rift), which the other two keys count, and the board-wipe job
    read scores a one-sided sweep above a symmetric one. The ``mass_removal``
    key itself keeps only the symmetric shrink: it is also the sweep half of a
    mass-death turn the death payoffs read, which a one-sided shrink is not.

    No text degrade: a card the signal path can't see is not a board wipe."""
    return _matches_preset(card, "board-wipe")


def is_interaction(card: dict) -> bool:
    """THE interaction answer (ADR-0051, like :func:`is_ramp`): a hit on one of
    ``_INTERACTION_PRESETS``, or — for a card phase has no trees for — the text
    degrade's removal reach. The Tuner sources the role through the same presets
    and this same predicate (:data:`ROLE_SEARCH`), so what a Slot counts and what
    it is offered cannot drift. A graveyard recall is no hit: the lanes behind
    the presets read it as recursion (``bounce_tempo``'s recall gates, CR 402.1
    vs 404.1), so no consumer-side veto is needed."""
    return bool(
        _matches_any(card, _INTERACTION_PRESETS)
        or (not trees_for(card, bulk=card) and removal_reach_by_text(card).removes)
    )


def protects(card: dict) -> bool:
    """Tier-2 (advisory, ADR-0024): does this card protect your board or you?

    THE protection answer (ADR-0051, like :func:`is_ramp`): the
    ``protects-board`` preset, a view over the signal path —
    ``board_protection`` (a protective keyword given to another permanent or to
    you, or a save — regeneration, phasing out, damage prevention — for
    something other than the card itself), ``pillowfort`` (attack taxes, bans and
    limits on attacking you), ``counter_control`` (counterspells answer removal)
    and ``spell_redirect`` (Misdirection, Deflecting Swat — CR 115.7). The
    tuner's protection sourcing reads the same preset.

    A permanent that protects only itself (Dragonlord Ojutai's hexproof, Thrun's
    regeneration) protects nothing else on your board, so it is not protection.

    No text degrade, unlike :func:`is_ramp`: a card the signal path can't see (no
    ``oracle_id``, no phase parse) is not protection — the signal path never
    guesses from text."""
    return _matches_preset(card, "protects-board")


def _conditionally_gated(card: dict) -> bool:
    """Every ability of the card's that adds mana or makes a Treasure may be
    activated only while a condition holds (``crosswalk.mana_ability_gates``: Mox
    Opal wants metalcraft, Mox Jasper a Dragon, Circle of Elders formidable — CR
    602.5). Such a rock reads as ramp but may do nothing in this deck. One ungated
    sibling (Fanatic of Rhonas' {T}: Add {G}) makes the card reliable; a card with
    no such ability (Cultivate, Kamahl's Druidic Vow) has nothing to gate."""
    gates = [g for tree in trees_for(card) for g in mana_ability_gates(tree)]
    return bool(gates) and all(gates)


def is_reliable_ramp(card: dict, *, deck_mana: DeckMana | None = None) -> bool:
    """Ramp the tuner will SOURCE (``ROLE_SEARCH["ramp"]``'s precision pass): a
    genuine producer (:func:`is_ramp` — which already rejects mana an opponent
    receives, like An Offer You Can't Refuse's Treasures, and under ``commander``
    mana the deck can't use) whose ability isn't conditionally gated
    (:func:`_conditionally_gated`).

    Sourcing, not counting, on purpose: the activation gate stays out of
    :func:`is_ramp`, so deck-stats, mana-audit and slot-budgets still count Mox
    Opal in the artifact deck that runs it — there it does ramp. Only a
    suggestion has to be vouched for, and the tuner can't vouch that a
    candidate's condition holds in this deck, so it doesn't suggest a gated rock.
    Which gates count as unreliable (every ``RequiresCondition``, an
    opponent's-turn-only one included) is this module's decision, not a rule."""
    return is_ramp(card, deck_mana=deck_mana) and not _conditionally_gated(card)


#: Each counted role's candidate search, in the ``card_search`` spec shape the
#: tuner pages (ADR-0051): the presets that prefilter it (``preset_names``
#: combine with AND, ``any_preset_names`` with OR) and, where the role is
#: narrower than their hits, a precision pass (``_filter``, called with the
#: deck's ``deck_mana``): the role's own predicate, or for ramp the stricter
#: :func:`is_reliable_ramp`. The tuner reads these as they stand, so what a Slot
#: counts and what it is offered for it cannot drift. ``card_draw`` is sourced
#: by its preset alone: every hit counts, while a draw only the IR walk sees
#: (:func:`_ir_draws`) isn't offered.
ROLE_SEARCH: dict[str, dict] = {
    "ramp": {"preset_names": ("ramp",), "_filter": is_reliable_ramp},
    "card_draw": {"preset_names": ("card-draw",)},
    # ANY of the presets, as the role reads them (passed as ``preset_names``
    # they combined with AND, and the search found nothing: no removal fill or
    # upgrade was sourced from 2026-10-18 to 10-19); the predicate is the
    # role's own answer, so what the search offers and the Slot counts agree.
    "interaction": {
        "any_preset_names": _INTERACTION_PRESETS,
        "_filter": lambda c, **_kw: is_interaction(c),
    },
    "board_wipe": {"preset_names": ("board-wipe",)},
}
