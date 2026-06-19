"""Durable invariant for the ADR-0027 regex→Card-IR strangler.

For EVERY key in ``MIGRATED_KEYS``, the migration must be real and complete:

  * ``extract_signals`` (the legacy regex path) must NO LONGER emit the key — its
    oracle-regex production (``_DETECTORS`` / ``_HAND_FLOOR`` / ``SWEEP_DETECTORS``
    rows + any ``add()``) is deleted.
  * ``extract_signals_hybrid(card, ir)`` (the production dispatcher) DOES emit it,
    served from the Card IR path (``extract_signals_ir``).

Each case is a real card (full oracle_text + type_line, never trimmed/fabricated)
paired with a hand-built IR that mirrors the structural source the IR path reads
for that key — so the proof holds without a phase dependency or the on-disk
sidecar. A new migration batch adds one ``(key, card, ir)`` row here; the
parametrization then guards it forever.
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.signals import (
    MIGRATED_KEYS,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import (
    Ability,
    Card,
    Condition,
    Effect,
    Face,
    Filter,
    Quantity,
    Trigger,
)


def _ir(*abilities: Ability, keywords: tuple[str, ...] = ()) -> Card:
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", keywords=keywords, abilities=tuple(abilities)),),
    )


# One representative real card per migrated key, paired with the IR that mirrors
# the structural source the IR path reads:
#   ki_counter_matters  ← Effect(place_counter, counter_kind="ki")  [_COUNTER_KIND_KEYS]
#   seek_matters        ← Effect(category="seek")                   [_DOER_EFFECT_KEYS]
#   specialize_matters  ← Scryfall "Specialize" keyword             [_IR_KEYWORD_MAP]
_CASES: dict[str, tuple[dict, Card]] = {
    "ki_counter_matters": (
        {
            "name": "Skullmane Baku",
            "type_line": "Creature — Spirit",
            "oracle_text": (
                "Whenever you cast a Spirit or Arcane spell, you may put a ki "
                "counter on this creature.\n{1}, {T}, Remove X ki counters from "
                "this creature: Target creature gets -X/-X until end of turn."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="place_counter",
                        counter_kind="ki",
                        scope="you",
                        raw="put a ki counter on ~",
                    ),
                ),
            )
        ),
    ),
    "seek_matters": (
        {
            "name": "Adherent's Heirloom",
            "type_line": "Artifact",
            "oracle_text": (
                "When this artifact enters, seek a creature card of the most "
                "prevalent creature type in your library.\n{T}: Add one mana of "
                "any color. Spend this mana only to cast a creature spell."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="seek",
                        scope="you",
                        raw="seek a creature card",
                    ),
                ),
            )
        ),
    ),
    "specialize_matters": (
        {
            "name": "Alora, Rogue Companion",
            "type_line": "Legendary Creature — Halfling Rogue",
            "oracle_text": (
                "Specialize {2}\nWhenever you attack, up to one target attacking "
                "creature can't be blocked this turn. At the beginning of the next "
                "end step, return that creature to its owner's hand."
            ),
            "keywords": ["Specialize"],
        },
        # specialize is read off the Scryfall keyword array, not the IR structure,
        # so a bare non-None IR is enough to route the hybrid to the IR path.
        _ir(),
    ),
    # Group "bending" — detected by the kept word-detector mirror
    # (_IR_KEPT_DETECTORS), which scans the oracle text directly, so any non-None
    # IR routes the hybrid to the IR path.
    "airbend_matters": (
        {
            "name": "Airbender Ascension",
            "type_line": "Enchantment",
            "oracle_text": (
                "When this enchantment enters, airbend up to one target creature.\n"
                "Whenever a creature you control enters, put a quest counter on "
                "this enchantment.\nAt the beginning of your end step, if this "
                "enchantment has four or more quest counters on it, exile up to one "
                "target creature you control, then return it to the battlefield "
                "under its owner's control."
            ),
        },
        _ir(),
    ),
    "earthbend_matters": (
        {
            "name": "Earthen Ally",
            "type_line": "Creature — Human Soldier Ally",
            "oracle_text": (
                "This creature gets +1/+0 for each color among Allies you "
                "control.\n{2}{W}{U}{B}{R}{G}: Earthbend 5. (Target land you "
                "control becomes a 0/0 creature with haste that's still a land. "
                "Put five +1/+1 counters on it. When it dies or is exiled, return "
                "it to the battlefield tapped.)"
            ),
        },
        _ir(),
    ),
    "waterbend_matters": (
        {
            "name": "Spirit Water Revival",
            "type_line": "Sorcery",
            "oracle_text": (
                "As an additional cost to cast this spell, you may waterbend {6}. "
                "(While paying a waterbend cost, you can tap your artifacts and "
                "creatures to help. Each one pays for {1}.)\nDraw two cards. If "
                "this spell's additional cost was paid, instead shuffle your "
                "graveyard into your library, draw seven cards, and you have no "
                "maximum hand size for the rest of the game.\nExile Spirit Water "
                "Revival."
            ),
        },
        _ir(),
    ),
    "firebending_matters": (
        {
            "name": "Fire Lord Azula",
            "type_line": "Legendary Creature — Human Noble",
            "oracle_text": (
                "Firebending 2 (Whenever this creature attacks, add {R}{R}. This "
                "mana lasts until end of combat.)\nWhenever you cast a spell while "
                "Fire Lord Azula is attacking, copy that spell. You may choose new "
                "targets for the copy. (A copy of a permanent spell becomes a "
                "token.)"
            ),
        },
        _ir(),
    ),
    # Group "set-mechanics" — celebration / coven / outlaw / snow / lessons detect
    # from the kept word-detector mirror (_IR_KEPT_DETECTORS, scans oracle text);
    # enlist / companion read the Scryfall keyword array. All route on any non-None
    # IR.
    "celebration_matters": (
        {
            "name": "Tuinvale Guide",
            "type_line": "Creature — Faerie Scout",
            "oracle_text": (
                "Flying\nCelebration — This creature gets +1/+0 and has lifelink "
                "as long as two or more nonland permanents entered the battlefield "
                "under your control this turn."
            ),
            "keywords": ["Flying", "Celebration"],
        },
        _ir(),
    ),
    "coven_matters": (
        {
            "name": "Leinore, Autumn Sovereign",
            "type_line": "Legendary Creature — Human Noble",
            "oracle_text": (
                "Coven — At the beginning of combat on your turn, put a +1/+1 "
                "counter on up to one target creature you control. Then if you "
                "control three or more creatures with different powers, draw a card."
            ),
            "keywords": ["Coven"],
        },
        _ir(),
    ),
    "outlaw_matters": (
        {
            "name": "Laughing Jasper Flint",
            "type_line": "Legendary Creature — Lizard Rogue",
            "oracle_text": (
                "Creatures you control but don't own are Mercenaries in addition "
                "to their other types.\nAt the beginning of your upkeep, exile the "
                "top X cards of target opponent's library, where X is the number of "
                "outlaws you control. Until end of turn, you may cast spells from "
                "among those cards, and mana of any type can be spent to cast those "
                "spells."
            ),
        },
        _ir(),
    ),
    "snow_matters": (
        {
            "name": "Diamond Faerie",
            "type_line": "Snow Creature — Faerie",
            "oracle_text": (
                "Flying\n{1}{S}: Snow creatures you control get +1/+1 until end of "
                "turn. ({S} can be paid with one mana from a snow source.)"
            ),
            "keywords": ["Flying"],
        },
        _ir(),
    ),
    "lessons_matter": (
        {
            "name": "Sokka, Bold Boomeranger",
            "type_line": "Legendary Creature — Human Warrior Ally",
            "oracle_text": (
                "When Sokka enters, discard up to two cards, then draw that many "
                "cards.\nWhenever you cast an artifact or Lesson spell, put a "
                "+1/+1 counter on Sokka."
            ),
        },
        _ir(),
    ),
    "enlist_matters": (
        {
            "name": "Benalish Faithbonder",
            "type_line": "Creature — Human Cleric",
            "oracle_text": (
                "Vigilance\nEnlist (As this creature attacks, you may tap a "
                "nonattacking creature you control without summoning sickness. When "
                "you do, add its power to this creature's until end of turn.)"
            ),
            "keywords": ["Vigilance", "Enlist"],
        },
        # enlist is read off the Scryfall keyword array, so a bare non-None IR
        # routes the hybrid to the IR path.
        _ir(),
    ),
    "companion_keyword": (
        {
            "name": "Lutri, the Spellchaser",
            "type_line": "Legendary Creature — Elemental Otter",
            "oracle_text": (
                "Companion — Each nonland card in your starting deck has a "
                "different name. (If this card is your chosen companion, you may "
                "put it into your hand from outside the game for {3} as a "
                "sorcery.)\nFlash\nWhen Lutri enters, if you cast it, copy target "
                "instant or sorcery spell you control. You may choose new targets "
                "for the copy."
            ),
            "keywords": ["Companion", "Flash"],
        },
        # companion is read off the Scryfall keyword array → bare non-None IR.
        _ir(),
    ),
    # Group "structural" — backed by a STRUCTURED IR shape (effect category /
    # grant subject / trigger event+scope), except facedown + voting which use the
    # kept word-detector mirror (oracle scan → bare IR).
    "token_doubling": (
        {
            "name": "Parallel Lives",
            "type_line": "Enchantment",
            "oracle_text": (
                "If an effect would create one or more tokens under your control, "
                "it creates twice that many of those tokens instead."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="token_doubling",
                        scope="you",
                        raw="creates twice that many tokens",
                    ),
                ),
            )
        ),
    ),
    "counter_move": (
        {
            "name": "Scrounging Bandar",
            "type_line": "Creature — Cat Monkey",
            "oracle_text": (
                "This creature enters with two +1/+1 counters on it.\nAt the "
                "beginning of your upkeep, you may move any number of +1/+1 "
                "counters from this creature onto another target creature."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="counter_move",
                        scope="you",
                        raw="move +1/+1 counters from ~ onto another creature",
                    ),
                ),
            )
        ),
    ),
    "all_creatures_kw_grant": (
        {
            "name": "Angel's Trumpet",
            "type_line": "Artifact",
            "oracle_text": (
                "All creatures have vigilance.\nAt the beginning of each player's "
                "end step, tap all untapped creatures that player controls that "
                "didn't attack this turn. This artifact deals damage to the player "
                "equal to the number of creatures tapped this way."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        counter_kind="vigilance",
                        subject=Filter(card_types=("Creature",), controller="any"),
                    ),
                ),
            )
        ),
    ),
    "nonhuman_attackers": (
        {
            "name": "Winota, Joiner of Forces",
            "type_line": "Legendary Creature — Human Warrior",
            "oracle_text": (
                "Whenever a non-Human creature you control attacks, look at the "
                "top six cards of your library. You may put a Human creature card "
                "from among them onto the battlefield tapped and attacking. It "
                "gains indestructible until end of turn. Put the rest of the cards "
                "on the bottom of your library in a random order."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="attacks",
                    subject=Filter(
                        card_types=("Creature",),
                        controller="you",
                        predicates=("NotSubtype:Human",),
                    ),
                ),
            )
        ),
    ),
    "opponent_draw_matters": (
        {
            "name": "Underworld Dreams",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever an opponent draws a card, this enchantment deals 1 "
                "damage to that player."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="drawn", scope="opp"),
            )
        ),
    ),
    # facedown + voting detect from the kept word-detector mirror, which scans the
    # oracle text directly, so any non-None IR routes the hybrid to the IR path.
    "facedown_matters": (
        {
            "name": "Etrata, Deadly Fugitive",
            "type_line": "Legendary Creature — Vampire Assassin",
            "oracle_text": (
                'Deathtouch\nFace-down creatures you control have "{2}{U}{B}: Turn '
                "this creature face up. If you can't, exile it, then you may cast "
                'the exiled card without paying its mana cost."\nWhenever an '
                "Assassin you control deals combat damage to an opponent, cloak "
                "the top card of that player's library."
            ),
        },
        _ir(),
    ),
    "voting_matters": (
        {
            "name": "Capital Punishment",
            "type_line": "Sorcery",
            "oracle_text": (
                "Council's dilemma — Starting with you, each player votes for "
                "death or taxes. Each opponent sacrifices a creature of their "
                "choice for each death vote and discards a card for each taxes "
                "vote."
            ),
        },
        _ir(),
    ),
    # ADR-0027 restriction-narrow batch. monarch ← Condition(ismonarch) on the
    # ability (the "if you're the monarch" gate phase keeps as a condition, lifted
    # in extract_signals_ir); saddle ← a `saddle` marker effect (project's
    # _narrow_mechanic_refs appends it for a "becomes saddled" grant phase folded
    # into a restriction carrier); soulbond ← a `soulbond` marker effect (appended
    # for a "paired with a creature with soulbond" reference on a non-keyword card).
    "monarch_matters": (
        {
            "name": "Throne Warden",
            "type_line": "Creature — Human Soldier",
            "oracle_text": (
                "At the beginning of your end step, if you're the monarch, put a "
                "+1/+1 counter on this creature."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="end_step"),
                condition=Condition(kind="ismonarch"),
                effects=(
                    Effect(
                        category="place_counter",
                        counter_kind="p1p1",
                        raw="put a +1/+1 counter on ~",
                    ),
                ),
            )
        ),
    ),
    "saddle_matters": (
        {
            "name": "Guidelight Matrix",
            "type_line": "Artifact",
            "oracle_text": (
                "When this artifact enters, draw a card.\n{2}, {T}: Target Mount "
                "you control becomes saddled until end of turn. Activate only as a "
                "sorcery.\n{2}, {T}: Target Vehicle you control becomes an artifact "
                "creature until end of turn."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(
                    Effect(
                        category="saddle",
                        scope="you",
                        raw="Target Mount you control becomes saddled",
                    ),
                ),
            )
        ),
    ),
    "soulbond_matters": (
        {
            "name": "Flowering Lumberknot",
            "type_line": "Creature — Plant",
            "oracle_text": (
                "This creature can't attack or block unless it's paired with a "
                "creature with soulbond."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="soulbond",
                        scope="you",
                        raw="paired with a creature with soulbond",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 trigger-other raw-marker batch. Each tail card is a PAYOFF trigger
    # phase flattened to Trigger(event="other") — the consequence is a typed effect,
    # the trigger condition survives only in the effect raw, and
    # project._narrow_trigger_other_refs appends a precise marker effect read via
    # _DOER_EFFECT_KEYS. coin_flip ← "Whenever you win a coin flip" (Chance
    # Encounter); discover ← "Whenever you discover, discover again" (Curator);
    # ninjutsu ← "Whenever you activate a ninjutsu ability" (Satoru); ring ←
    # "Whenever the Ring tempts you" (Faramir).
    "coin_flip": (
        {
            "name": "Chance Encounter",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever you win a coin flip, put a luck counter on this "
                "enchantment.\nAt the beginning of your upkeep, if this enchantment "
                "has ten or more luck counters on it, you win the game."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="coin_flip",
                        scope="you",
                        raw="Whenever you win a coin flip, put a luck counter on ~.",
                    ),
                ),
            )
        ),
    ),
    "discover_matters": (
        {
            "name": "Curator of Sun's Creation",
            "type_line": "Creature — Human Artificer",
            "oracle_text": (
                "Whenever you discover, discover again for the same value. This "
                "ability triggers only once each turn."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="discover",
                        scope="you",
                        raw="Whenever you discover, discover again for the same value.",
                    ),
                ),
            )
        ),
    ),
    "ninjutsu_matters": (
        {
            "name": "Satoru Umezawa",
            "type_line": "Legendary Creature — Human Ninja",
            "oracle_text": (
                "Whenever you activate a ninjutsu ability, look at the top three "
                "cards of your library. Put one of them into your hand and the rest "
                "on the bottom of your library in any order. This ability triggers "
                "only once each turn.\nEach creature card in your hand has ninjutsu "
                "{2}{U}{B}. ({2}{U}{B}, Return an unblocked attacker you control to "
                "hand: Put this card onto the battlefield from your hand tapped and "
                "attacking.)"
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="ninjutsu",
                        scope="you",
                        raw=(
                            "Whenever you activate a ninjutsu ability, look at the "
                            "top three cards of your library."
                        ),
                    ),
                ),
            )
        ),
    ),
    "ring_matters": (
        {
            "name": "Faramir, Field Commander",
            "type_line": "Legendary Creature — Human Soldier",
            "oracle_text": (
                "At the beginning of your end step, if a creature died under your "
                "control this turn, draw a card.\nWhenever the Ring tempts you, if "
                "you chose a creature other than Faramir, Field Commander as your "
                "Ring-bearer, create a 1/1 white Human Soldier creature token."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="ring_tempt",
                        scope="you",
                        raw=(
                            "Whenever the Ring tempts you, if you chose a creature "
                            "other than ~ as your Ring-bearer, create a token."
                        ),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 conferred-keyword re-parse batch. Each tail card GRANTS a keyword/
    # ability to a CLASS of objects — phase folds the grant into a carrier and the
    # granted keyword survives only in raw, so project._narrow_conferred_keyword_refs
    # appends a precise marker effect read by extract_signals_ir. affinity ←
    # "spells you cast have affinity for artifacts" (Tezzeret); damage_reflect ← the
    # quoted reflection grant 'Slivers you control have "Whenever ~ is dealt damage,
    # ~ deals that much damage to ..."' (Spiteful Sliver); evasion_denial ← the
    # generic-landwalk umbrella (Staff of the Ages).
    "affinity_type": (
        {
            "name": "Tezzeret, Master of the Bridge",
            "type_line": "Legendary Planeswalker — Tezzeret",
            "oracle_text": (
                "Creature and planeswalker spells you cast have affinity for "
                "artifacts. (They cost {1} less to cast for each artifact you "
                "control.)\n+2: Tezzeret deals X damage to each opponent, where X "
                "is the number of artifacts you control. You gain X life.\n−3: "
                "Return target artifact card from your graveyard to your hand.\n"
                "−8: Exile the top ten cards of your library. Put all artifact "
                "cards from among them onto the battlefield."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="affinity",
                        scope="you",
                        raw=(
                            "Creature and planeswalker spells you cast have "
                            "affinity for artifacts."
                        ),
                    ),
                ),
            )
        ),
    ),
    "damage_reflect": (
        {
            "name": "Spiteful Sliver",
            "type_line": "Creature — Sliver",
            "oracle_text": (
                'Sliver creatures you control have "Whenever this creature is '
                "dealt damage, it deals that much damage to target player or "
                'planeswalker."'
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="damage_reflect",
                        scope="you",
                        raw=(
                            'Sliver creatures you control have "Whenever this '
                            "creature is dealt damage, it deals that much damage "
                            "to target player or planeswalker"
                        ),
                    ),
                ),
            )
        ),
    ),
    "evasion_denial": (
        {
            "name": "Staff of the Ages",
            "type_line": "Artifact",
            "oracle_text": (
                "Creatures with landwalk abilities can be blocked as though they "
                "didn't have those abilities."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="evasion_denial",
                        scope="opp",
                        raw=(
                            "Creatures with landwalk abilities can be blocked as "
                            "though they didn't have those abilities."
                        ),
                    ),
                ),
            )
        ),
    ),
    # The go-wide scaling lane. The IR mirrors a board_count marker — a count operand
    # over the GENERIC creature board (Crusader's P/T == number of creatures you
    # control), the headline source the structured projection now recovers.
    "creatures_matter": (
        {
            "name": "Crusader of Odric",
            "type_line": "Creature — Human Soldier",
            "oracle_text": (
                "Crusader of Odric's power and toughness are each equal to the "
                "number of creatures you control."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="board_count",
                        scope="you",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        amount=Quantity(
                            op="count",
                            subject=Filter(card_types=("Creature",), controller="you"),
                        ),
                        raw="equal to the number of creatures you control",
                    ),
                ),
            )
        ),
    ),
}


def test_every_migrated_key_has_a_case():
    """No migrated key may be left unproven: the case table must cover the manifest."""
    assert set(_CASES) == set(MIGRATED_KEYS), (
        "every key in MIGRATED_KEYS needs a representative (card, ir) case here"
    )


@pytest.mark.parametrize("key", sorted(MIGRATED_KEYS))
def test_migrated_key_left_regex_and_is_ir_served(key):
    """Regex path drops the key; the hybrid (IR) path serves it."""
    card, ir = _CASES[key]
    regex_keys = {s.key for s in extract_signals(card)}
    hybrid_keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert key not in regex_keys, f"{key} still emitted by the legacy regex path"
    assert key in hybrid_keys, f"{key} not served by the hybrid IR path"


def test_creatures_matter_mass_grant_fires_via_ir():
    """A MASS keyword grant to the generic creature board (Champion of Lambholt's
    CantBeBlockedBy) → creatures_matter via the IR grant_keyword arm, not regex."""
    card = {
        "name": "Champion of Lambholt",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": (
            "Creatures with power less than this creature's power can't block "
            "creatures you control.\nWhenever another creature you control enters, "
            "put a +1/+1 counter on this creature."
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="grant_keyword",
                    scope="you",
                    subject=Filter(card_types=("Creature",), controller="you"),
                    counter_kind="unblockable",
                    raw="creatures you control can't be blocked",
                ),
            ),
        )
    )
    assert "creatures_matter" not in {s.key for s in extract_signals(card)}
    assert "creatures_matter" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_creatures_matter_does_not_fire_on_a_subtype_lord():
    """The over-fire boundary: a SUBTYPE lord ("Goblin creatures you control get
    +1/+1") is tribal (type_matters, CR 205.3), NOT the generic go-wide lane — its
    IR pump subject carries the Goblin subtype, so the generic-set gate rejects it."""
    card = {
        "name": "Goblin King",
        "type_line": "Creature — Goblin",
        "oracle_text": (
            "Other Goblin creatures you control get +1/+1 and have mountainwalk."
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="you",
                    subject=Filter(
                        card_types=("Creature",),
                        subtypes=("Goblin",),
                        controller="you",
                    ),
                    raw="Other Goblin creatures you control get +1/+1",
                ),
            ),
        )
    )
    assert "creatures_matter" not in {s.key for s in extract_signals_hybrid(card, ir)}
