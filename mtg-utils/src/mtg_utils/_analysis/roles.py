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

The one text read is the documented no-coverage degrade: a card the signal path
cannot see (no ``oracle_id``, no phase parse, no sidecar — a synthetic fixture, a
cube pool run with no card-data) answers ramp from
``card_classify.ramp_by_text``. ``protects`` has no degrade: such a card is not
protection.
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
    mana_spell_type_restriction,
    produced_kind,
    tag_of,
)
from mtg_utils._card_ir.trees import object_facts, trees_for
from mtg_utils.card_classify import is_land, ramp_by_text
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
        return bool({t.lower() for t in facts.subtypes} & _OUTLAWS)
    if word in _CARD_TYPE_WORDS:
        return word in {t.lower() for t in facts.types}
    if word in _SUPERTYPE_WORDS:
        return word in {t.lower() for t in facts.supertypes}
    if word in _SUBTYPE_WORDS:
        return word in {t.lower() for t in facts.subtypes}
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
        return cls(
            identity=identity,
            commanders=tuple(object_facts(dict(c)) for c in recs),
            spells=tuple((object_facts(dict(r)), q) for r, q in spells),
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


# Mass-removal effect categories phase tags with the counter_kind="all" mass marker
# (DestroyAll / DamageAll / BounceAll — Wrath, Blasphemous Act, Evacuation).
_MASS_REMOVAL_CATS = frozenset({"destroy", "damage", "bounce"})


def _ir_board_wipe(ir: Card) -> bool:
    """Does the card's IR carry a creature/permanent BOARD WIPE — the structured mirror
    of the ``board-wipe`` preset? phase parses single-vs-mass and the projection keeps
    it as ``counter_kind="all"`` on a DestroyAll / DamageAll / BounceAll (a single
    Destroy does not). Three gates keep it to genuine sweepers:
      - subject is Creature / Permanent (not "destroy all LANDS" = mass land denial,
        not "all ARTIFACTS" = Bane of Progress);
      - controller != "you" (a "return all creatures YOU CONTROL" self-bounce, Denizen
        of the Deep, is a drawback; symmetric "any" / one-sided "opp" are kept);
      - no graveyard zone ("return all creature cards FROM YOUR GRAVEYARD" recursion,
        Lychguard, is not removal).

    A mass ``-X/-X`` shrink (Toxic Deluge, Drown in Sorrow) is read via the SIDECAR-v74
    ``Effect.toughness`` companion: a mass ``pump`` whose toughness factor is negative
    can kill, where a harmless power-only "-2/-0" (toughness factor 0) and a "+X/+X"
    anthem (factor > 0) are excluded. A SINGLE-target shrink is ``pump_target`` (not the
    mass ``pump``). Covers both a mass-shrink SPELL (Toxic Deluge) and a STATIC
    mass-debuff anthem (Elesh Norn's opponents' -2/-2 — SIDECAR v75)."""
    for ab in ir.all_abilities():
        for e in ab.effects:
            subj = e.subject
            if (
                subj is None
                or subj.controller == "you"
                or not ("Creature" in subj.card_types or "Permanent" in subj.card_types)
                or any("graveyard" in z for z in e.zones)
            ):
                continue
            if e.category in _MASS_REMOVAL_CATS and e.counter_kind == "all":
                return True
            tuf = e.toughness
            if e.category == "pump" and tuf is not None and tuf.factor < 0:
                return True
    return False


# Effect categories that ARE a real answer (so a card carrying one is not pure graveyard
# recursion). topdeck_stack is a tuck ("put target X on top of its owner's library" —
# Rootrunner, or graveyard hate); the rest are removal / counters / edict / pacify.
_IR_REAL_ANSWER_CATS = frozenset(
    {
        "destroy",
        "damage",
        "counter_spell",
        "exile",
        "restriction",
        "sacrifice",
        "topdeck_stack",
    }
)


def _ir_recursion_only(ir: Card) -> bool:
    """True iff the card's ONLY interaction-shaped effect is GRAVEYARD RECURSION — a
    bounce that returns a card from a graveyard, with no real answer alongside it.

    Such a card (Pharika's Mender, Pulse of Murasa, Neva — "return target creature OR
    enchantment card from your graveyard to your hand") is value/recursion, NOT removal;
    the ``removal`` / ``bounce`` presets misfire on the "X or Y card from graveyard"
    form their ``(?!\\s+card\\b)`` anchor can't exclude (the "card" doesn't immediately
    follow the first noun). The structural read vetoes those.

    A battlefield bounce (``in:battlefield`` target, or a bounce with no graveyard
    zone), a targeted ``-X/-X`` shrink (``pump_target`` with negative toughness), a
    tuck, or any destroy/damage/counter/exile/edict/pacify effect means the card has a
    REAL answer → NOT recursion-only (returns False). The veto only fires when a
    graveyard bounce is the SOLE interaction-shaped effect, so a card with no graveyard
    bounce can never be vetoed (``saw_gy_bounce`` stays False). Requires the SIDECAR-v76
    per-effect graveyard zones (before v76 a sibling's "from graveyard" bled onto
    battlefield bounces, which would have made answers like Aether Helix look
    recursion-only)."""
    saw_gy_bounce = False
    for ab in ir.all_abilities():
        for e in ab.effects:
            cat = e.category
            if cat == "bounce":
                if "in:battlefield" in e.zones:
                    return False  # targets a battlefield permanent — a real bounce
                if any("graveyard" in z for z in e.zones):
                    saw_gy_bounce = True
                else:
                    return False  # a non-graveyard bounce is a real tempo answer
            elif cat in _IR_REAL_ANSWER_CATS:
                return False
            elif (
                cat == "pump_target"
                and e.toughness is not None
                and e.toughness.factor < 0
            ):
                return False  # a targeted -X/-X shrink is removal
    return saw_gy_bounce


def is_ramp(card: dict, *, deck_mana: DeckMana | None = None) -> bool:
    """Does this NONLAND card accelerate your mana — the template's ``ramp`` role?

    THE ramp answer (ADR-0051): the ``ramp`` preset, a view over the signal path
    (rocks / dorks / rituals / granted mana, land-fetch-to-battlefield, mana
    amplifiers, extra land drops, Treasure makers you keep). A land is never ramp —
    it is the mana base (CR 305), counted by the ``lands`` role and the land band.

    A card the signal path cannot see at all (``has_signal_coverage`` false: no
    ``oracle_id``, no phase parse, no card-data) degrades to
    ``card_classify.ramp_by_text`` — the ONE surviving text read, so a no-sidecar
    ``deck-stats`` / cube goldfish still counts its rocks.

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
    dead-mana veto when the deck context is given). ``card_draw`` and
    ``board_wipe`` read the candidate's Card IR when available (the ``draw`` category;
    the ``counter_kind="all"`` mass-removal marker), degrading to the curated presets
    when the card has no IR. The regex preset ALSO runs for ``board_wipe``: it still
    owns the ``-X/-X`` mass shrink the projection can't yet express (see
    ``_ir_board_wipe``). ``interaction`` stays on its presets for the positive match
    (the IR's ``destroy`` / ``restriction`` categories don't encode the pacify-vs-self
    and edict boundaries), but a structural VETO drops a preset hit the IR shows is pure
    graveyard recursion (``_ir_recursion_only`` — "return X or Y card from your
    graveyard", which the preset's ``card`` anchor misses).

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
    if (ir is not None and _ir_board_wipe(ir)) or _matches_preset(card, "board-wipe"):
        roles.add("board_wipe")
    if _matches_any(card, _INTERACTION_PRESETS) and not (
        ir is not None and _ir_recursion_only(ir)
    ):
        roles.add("interaction")
    return roles


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
