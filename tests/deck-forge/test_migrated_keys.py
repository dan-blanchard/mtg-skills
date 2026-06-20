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
    # The sacrifice-creatures-for-+1/+1-counters keyword lane (CR 702.82). The IR
    # mirror is the Scryfall "Devour" keyword (Mycoloth, the canonical Devour
    # build-around) read via _IR_KEYWORD_MAP — the structural source that keeps the
    # "Devour Intellect" flavor word and the "Devour in Flames" card name out. Like
    # specialize, devour is read off the Scryfall keyword array, not the IR
    # structure, so a bare non-None IR routes the hybrid to the IR path.
    "devour_matters": (
        {
            "name": "Mycoloth",
            "type_line": "Creature — Fungus",
            "oracle_text": (
                "Devour 2 (As this creature enters, you may sacrifice any number "
                "of creatures. It enters with twice that many +1/+1 counters on "
                "it.)\nAt the beginning of your upkeep, create a 1/1 green "
                "Saproling creature token for each +1/+1 counter on this creature."
            ),
            "keywords": ["Devour"],
        },
        _ir(),
    ),
    # The Blood token-subtype synergy lane (CR 111.10g). The IR mirror is a
    # make_token Effect whose subject Filter carries the Blood subtype (Bloodtithe
    # Harvester, a canonical Blood maker) — the structural maker the lane reads. The
    # sacrifice-payoff and choose-list / granted-ability maker paths are exercised by
    # the dedicated tests below.
    "blood_matters": (
        {
            "name": "Bloodtithe Harvester",
            "type_line": "Creature — Vampire",
            "oracle_text": (
                "When this creature enters, create a Blood token. (It's an "
                'artifact with "{1}, {T}, Discard a card, Sacrifice this token: '
                'Draw a card.")\n{T}, Sacrifice this creature: Target creature '
                "gets -X/-X until end of turn, where X is twice the number of "
                "Blood tokens you control. Activate only as a sorcery."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="make_token",
                        scope="you",
                        subject=Filter(card_types=("Artifact",), subtypes=("Blood",)),
                        raw="create a Blood token",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 tail-supplement batch ───────────────────────────────────────
    # Each pairs a real gap card with the IR marker the supplement appended for it.
    # Boast amplifier (Birgi) — the "can boast twice" static phase drops is recovered
    # as a `boast` dropped-static face marker.
    "boast_matters": (
        {
            "name": "Birgi, God of Storytelling",
            "type_line": "Legendary Creature — God",
            "oracle_text": (
                "Whenever you cast a spell, add {R}. Until end of turn, you don't "
                "lose this mana as steps and phases end.\nCreatures you control can "
                "boast twice during each of your turns rather than once."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(Effect(category="boast", scope="you", raw="can boast twice"),),
            )
        ),
    ),
    # Connive GRANTER (Security Bypass) — phase swallows the quoted "it connives"
    # grant into the Enchant parse; the Scryfall connive keyword lifts it.
    "connive_matters": (
        {
            "name": "Security Bypass",
            "type_line": "Enchantment — Aura",
            "oracle_text": (
                "Enchant creature\nAs long as enchanted creature is attacking "
                "alone, it can't be blocked.\nEnchanted creature has \"Whenever "
                'this creature deals combat damage to a player, it connives."'
            ),
            "keywords": ["Enchant", "Connive"],
        },
        # connive is read off the Scryfall keyword array, so a bare non-None IR
        # routes the hybrid to the IR path.
        _ir(keywords=("Enchant",)),
    ),
    # End-the-turn (Obeka) — phase's end_the_turn effect (the supplement category
    # reconciled to the lane's binding string).
    "end_the_turn": (
        {
            "name": "Obeka, Brute Chronologist",
            "type_line": "Legendary Creature — Ogre Wizard",
            "oracle_text": ("{T}: The player whose turn it is may end the turn."),
        },
        _ir(
            Ability(
                kind="activated",
                cost="tap",
                effects=(
                    Effect(
                        category="end_the_turn",
                        scope="any",
                        raw="The player whose turn it is may end the turn.",
                    ),
                ),
            )
        ),
    ),
    # Exhaust PAYOFF (Pit Automaton) — a delayed exhaust trigger inside an activated
    # ability, recovered by the now-ungated exhaust marker.
    "exhaust_matters": (
        {
            "name": "Pit Automaton",
            "type_line": "Artifact Creature — Construct",
            "oracle_text": (
                "Defender\n{T}: Add {C}{C}. Spend this mana only to activate "
                "abilities.\n{2}, {T}: When you next activate an exhaust ability "
                "that isn't a mana ability this turn, copy it. You may choose new "
                "targets for the copy."
            ),
            "keywords": ["Defender"],
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(
                    Effect(
                        category="exhaust",
                        scope="you",
                        raw="activate an exhaust ability",
                    ),
                ),
            )
        ),
    ),
    # Extra end step (Y'shtola) — the dropped "additional end step" clause recovered
    # as an `extra_end` dropped-static face marker.
    "extra_end_step": (
        {
            "name": "Y'shtola Rhul",
            "type_line": "Legendary Creature — Hyur Cleric",
            "oracle_text": (
                "At the beginning of your end step, exile target creature you "
                "control, then return it to the battlefield under its owner's "
                "control. Then if it's the first end step of the turn, there is an "
                "additional end step after this step."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="extra_end",
                        scope="you",
                        raw="additional end step",
                    ),
                ),
            )
        ),
    ),
    # Madness payoff (Anje) — the "if it has madness" condition recovered as a
    # `madness` payoff marker (distinct from the "has madness" grant).
    "madness_matters": (
        {
            "name": "Anje Falkenrath",
            "type_line": "Legendary Creature — Vampire",
            "oracle_text": (
                "Haste\n{T}, Discard a card: Draw a card.\nWhenever you discard a "
                "card, if it has madness, untap Anje Falkenrath."
            ),
            "keywords": ["Haste"],
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="madness",
                        scope="you",
                        raw="if it has madness",
                    ),
                ),
            )
        ),
    ),
    # Mutate payoff (Pollywog) — keyword-less cast-payoff recovered as a `mutate`
    # marker from "if it has mutate".
    "mutate_matters": (
        {
            "name": "Pollywog Symbiote",
            "type_line": "Creature — Frog",
            "oracle_text": (
                "Each creature spell you cast costs {1} less to cast if it has "
                "mutate.\nWhenever you cast a creature spell, if it has mutate, "
                "draw a card, then discard a card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(category="mutate", scope="you", raw="if it has mutate"),
                ),
            )
        ),
    ),
    # Phasing PAYOFF (The War Doctor) — the event='other' "permanents phase out"
    # payoff recovered as a `phasing` marker.
    "phasing_matters": (
        {
            "name": "The War Doctor",
            "type_line": "Legendary Creature — Time Lord Doctor",
            "oracle_text": (
                "Whenever one or more other permanents phase out and whenever one "
                "or more other cards are put into exile from anywhere, put a time "
                "counter on The War Doctor."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="phasing",
                        scope="you",
                        raw="permanents phase out",
                    ),
                ),
            )
        ),
    ),
    # Trigger-doubling GRANT (The Masamune) — the granted/quoted "triggers an
    # additional time" recovered as a `trigger_doubling` dropped-static face marker.
    "trigger_doubling": (
        {
            "name": "The Masamune",
            "type_line": "Legendary Artifact — Equipment",
            "oracle_text": (
                "As long as equipped creature is attacking, it has first strike "
                'and must be blocked if able.\nEquipped creature has "If a creature '
                "dying causes a triggered ability of this creature or an emblem you "
                'own to trigger, that ability triggers an additional time."\n'
                "Equip {2}"
            ),
            "keywords": ["Equip"],
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="trigger_doubling",
                        scope="you",
                        raw="triggers an additional time",
                    ),
                ),
            )
        ),
    ),
    # Experience SCALER (Atreus) — "for each experience counter you have" stamps
    # op="experience" on the draw operand.
    "experience_matters": (
        {
            "name": "Atreus, Impulsive Son",
            "type_line": "Legendary Creature — God Archer",
            "oracle_text": (
                "Reach\n{3}, {T}: Draw a card for each experience counter you "
                "have, then discard a card. Atreus deals 2 damage to each opponent."
            ),
            "keywords": ["Reach"],
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(
                    Effect(
                        category="draw",
                        scope="you",
                        amount=Quantity(op="experience", factor=1),
                        raw="Draw a card for each experience counter you have",
                    ),
                ),
            )
        ),
    ),
    # Explore (Topography Tracker) — read off the Scryfall explore keyword (the
    # authoritative path covering Map-token / granted-ability explore cards).
    "explore_matters": (
        {
            "name": "Topography Tracker",
            "type_line": "Creature — Elf Scout",
            "oracle_text": (
                "When this creature enters, create a Map token.\nIf a creature you "
                "control would explore, instead it explores, then it explores "
                "again."
            ),
            "keywords": ["Explore"],
        },
        # explore is read off the Scryfall keyword array, so a bare non-None IR
        # routes the hybrid to the IR path.
        _ir(),
    ),
    # Foretell payoff (Niko) — the Foretold predicate on a counted subject Filter.
    "foretell_matters": (
        {
            "name": "Niko Defies Destiny",
            "type_line": "Enchantment — Saga",
            "oracle_text": (
                "I — You gain 2 life for each foretold card you own in exile.\n"
                "II — Add {W}{U}. Spend this mana only to foretell cards or cast "
                "spells that have foretell.\nIII — Return target card with foretell "
                "from your graveyard to your hand."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="gain_life",
                        scope="any",
                        amount=Quantity(
                            op="multiply",
                            factor=2,
                            subject=Filter(
                                card_types=("Card",),
                                predicates=("Foretold", "Owned", "InZone"),
                            ),
                        ),
                        raw="gain 2 life for each foretold card you own in exile",
                    ),
                ),
            )
        ),
    ),
    # Scavenge GRANTER (Varolz) — the graveyard-wide "has scavenge" grant recovered
    # as a `scavenge` dropped-static face marker.
    "scavenge_fuel": (
        {
            "name": "Varolz, the Scar-Striped",
            "type_line": "Legendary Creature — Troll Warrior",
            "oracle_text": (
                "Each creature card in your graveyard has scavenge. The scavenge "
                "cost is equal to its mana cost.\nSacrifice another creature: "
                "Regenerate Varolz, the Scar-Striped."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="scavenge",
                        scope="you",
                        raw="has scavenge",
                    ),
                ),
            )
        ),
    ),
    # Scry-replacement payoff (Kenessos) — the "if you would scry a number of cards"
    # replacement recovered as a `scry_surveil` dropped-static face marker.
    "scry_surveil_matters": (
        {
            "name": "Kenessos, Priest of Thassa",
            "type_line": "Legendary Creature — Triton Wizard",
            "oracle_text": (
                "If you would scry a number of cards, scry that many cards plus "
                "one instead.\n{3}{G/U}: Look at the top card of your library. If "
                "it's a Kraken, Leviathan, Octopus, or Serpent creature card, you "
                "may put it onto the battlefield."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="scry_surveil",
                        scope="you",
                        raw="if you would scry a number of cards",
                    ),
                ),
            )
        ),
    ),
    # Extra beginning phase (Sphinx of the Second Sun) — "an additional beginning
    # phase after this phase" recovered as BOTH an `extra_upkeep` and an `extra_draw`
    # dropped-static face marker (CR 501.1). extra_draw_step fired 0 in the IR before.
    "extra_draw_step": (
        {
            "name": "Sphinx of the Second Sun",
            "type_line": "Creature — Sphinx",
            "oracle_text": (
                "Flying\nAt the beginning of each of your postcombat main phases, "
                "there is an additional beginning phase after this phase. (The "
                "beginning phase includes the untap, upkeep, and draw steps.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="extra_draw",
                        scope="you",
                        raw="additional beginning phase",
                    ),
                ),
            )
        ),
    ),
    "extra_upkeep": (
        {
            "name": "Sphinx of the Second Sun",
            "type_line": "Creature — Sphinx",
            "oracle_text": (
                "Flying\nAt the beginning of each of your postcombat main phases, "
                "there is an additional beginning phase after this phase. (The "
                "beginning phase includes the untap, upkeep, and draw steps.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="extra_upkeep",
                        scope="you",
                        raw="additional beginning phase",
                    ),
                ),
            )
        ),
    ),
    # Modal counter (Ertai Resurrected) — "• Counter target spell, activated ability,
    # or triggered ability" recovered as a `counter_spell` dropped-static face marker
    # (phase keeps only the `choose` header). CR 701.5.
    "counter_control": (
        {
            "name": "Ertai Resurrected",
            "type_line": "Legendary Creature — Phyrexian Human Wizard",
            "oracle_text": (
                "Flash\nWhen Ertai Resurrected enters, choose up to one —\n"
                "• Counter target spell, activated ability, or triggered ability. "
                "Its controller draws a card.\n• Destroy another target creature or "
                "planeswalker. Its controller draws a card."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="counter_spell",
                        scope="any",
                        raw="counter target spell",
                    ),
                ),
            )
        ),
    ),
    # Modal can't-block (Breeches) — "• Target creature can't block this turn"
    # recovered as a `cant_block` dropped-static face marker (phase keeps only the
    # `choose` header). CR 509.
    "cant_block_grant": (
        {
            "name": "Breeches, Eager Pillager",
            "type_line": "Legendary Creature — Goblin Pirate",
            "oracle_text": (
                "First strike\nWhenever a Pirate you control attacks, choose one "
                "that hasn't been chosen this turn —\n• Create a Treasure token.\n"
                "• Target creature can't block this turn.\n• Exile the top card of "
                "your library. You may play it this turn."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cant_block",
                        scope="any",
                        raw="• Target creature can't block",
                    ),
                ),
            )
        ),
    ),
    # Land exchange (Political Trickery) — phase's `gain_control` effect with
    # subject=None whose raw carries the "exchange control of … land" phrase, read by
    # the _LAND_EXCHANGE_RAW fallback (phase never binds the land-typed object).
    "land_exchange": (
        {
            "name": "Political Trickery",
            "type_line": "Sorcery",
            "oracle_text": (
                "Exchange control of target land you control and target land an "
                "opponent controls. (This effect lasts indefinitely.)"
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="gain_control",
                        scope="any",
                        subject=None,
                        raw=(
                            "Exchange control of target land you control and "
                            "target land an opponent controls."
                        ),
                    ),
                ),
            )
        ),
    ),
    # Myriad granter (Legion Loyalty) — "Creatures you control have myriad" carries
    # counter_kind='myriad' on a grant_keyword effect (the granter discriminator;
    # makers ride the keyword array, granters don't).
    "myriad_grant": (
        {
            "name": "Legion Loyalty",
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures you control have myriad. (Whenever a creature with "
                "myriad attacks, for each opponent other than defending player, "
                "you may create a token copy that's tapped and attacking that "
                "player or a planeswalker they control. Exile the tokens at end "
                "of combat.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        counter_kind="myriad",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw="Creatures you control have myriad.",
                    ),
                ),
            )
        ),
    ),
    # Convoke granter (Chief Engineer) — "Artifact spells you cast have convoke"
    # carries counter_kind='convoke' on a cast_with_keyword effect (the keyword-less
    # granter; makers ride the keyword array).
    "convoke_matters": (
        {
            "name": "Chief Engineer",
            "type_line": "Creature — Vedalken Artificer",
            "oracle_text": (
                "Artifact spells you cast have convoke. (Your creatures can help "
                "cast those spells. Each creature you tap while casting an artifact "
                "spell pays for {1} or one mana of that creature's color.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cast_with_keyword",
                        scope="you",
                        counter_kind="convoke",
                        raw="Artifact spells you cast have convoke.",
                    ),
                ),
            )
        ),
    ),
    # Tapped-count payoff (Throne of the God-Pharaoh) — the effect VALUE counts your
    # tapped creatures (a Tapped predicate on amount.subject, controller='you').
    "tapped_matters": (
        {
            "name": "Throne of the God-Pharaoh",
            "type_line": "Legendary Artifact",
            "oracle_text": (
                "At the beginning of your end step, each opponent loses life equal "
                "to the number of tapped creatures you control."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="end_step", scope="you"),
                effects=(
                    Effect(
                        category="lose_life",
                        scope="opp",
                        amount=Quantity(
                            op="count",
                            subject=Filter(
                                card_types=("Creature",),
                                controller="you",
                                predicates=("Tapped",),
                            ),
                        ),
                        raw=(
                            "each opponent loses life equal to the number of "
                            "tapped creatures you control"
                        ),
                    ),
                ),
            )
        ),
    ),
    # Multi-type anthem (Howlpack Resurgence) — a pump over a creature Filter naming
    # 2+ subtypes (a flat subtypes tuple, the phase shape the >=2 guard covers).
    "typed_anthem_multi": (
        {
            "name": "Howlpack Resurgence",
            "type_line": "Enchantment",
            "oracle_text": (
                "Flash\nEach creature you control that's a Wolf or a Werewolf "
                "gets +1/+1 and has trample."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",),
                            subtypes=("Wolf", "Werewolf"),
                            controller="you",
                        ),
                        raw=(
                            "Each creature you control that's a Wolf or a "
                            "Werewolf gets +1/+1 and has trample."
                        ),
                    ),
                ),
            )
        ),
    ),
    # Life doubling (Beacon of Immortality) — "double target player's life total"
    # routes to a `set_life` dropped-static face marker (the lane wants life
    # set/exchange/double; phase's bare `double` category isn't crosswalked).
    "life_total_set": (
        {
            "name": "Beacon of Immortality",
            "type_line": "Instant",
            "oracle_text": (
                "Double target player's life total. Shuffle Beacon of "
                "Immortality into its owner's library."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="set_life",
                        scope="any",
                        raw="Double target player's life total",
                    ),
                ),
            )
        ),
    ),
    # Energy producer (Aether Hub) — phase's `energy` effect category lights the lane.
    "energy_matters": (
        {
            "name": "Aether Hub",
            "type_line": "Land",
            "oracle_text": (
                "When this land enters, you get {E} (an energy counter).\n"
                "{T}: Add {C}.\n{T}, Pay {E}: Add one mana of any color."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="etb", scope="you"),
                effects=(
                    Effect(
                        category="energy",
                        scope="you",
                        raw="you get {E}",
                    ),
                ),
            )
        ),
    ),
    # Rad-counter maker (Nuclear Fallout) — the "rad counter(s)" clause phase mangles is
    # recovered as a `rad_counter` dropped-static face marker (scope opponents).
    "rad_counter_matters": (
        {
            "name": "Nuclear Fallout",
            "type_line": "Sorcery",
            "oracle_text": (
                "Each creature gets twice -X/-X until end of turn. Each player "
                "gets X rad counters."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="rad_counter",
                        scope="opp",
                        raw="rad counters",
                    ),
                ),
            )
        ),
    ),
    # Suspect doer (Case of the Stashed Skeleton) — "suspect it" (the verb buried
    # mid-clause) is recovered as a `suspect` dropped-static face marker.
    "suspect_matters": (
        {
            "name": "Case of the Stashed Skeleton",
            "type_line": "Enchantment — Case",
            "oracle_text": (
                "When this Case enters, create a 2/1 black Skeleton creature "
                "token and suspect it. (It has menace and can't block.)\nTo "
                "solve — You control no suspected Skeletons.\nSolved — {1}{B}, "
                "Sacrifice this Case: Search your library for a card, put it "
                "into your hand, then shuffle."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(Effect(category="suspect", scope="you", raw="suspect"),),
            )
        ),
    ),
    # Venture / dungeon payoff (Gloom Stalker) — the dungeon-completion gate is read off
    # the condition kind 'completedadungeon'.
    "venture_matters": (
        {
            "name": "Gloom Stalker",
            "type_line": "Creature — Dwarf Ranger",
            "oracle_text": (
                "As long as you've completed a dungeon, this creature has "
                "double strike."
            ),
        },
        _ir(
            Ability(
                kind="static",
                condition=Condition(kind="completedadungeon"),
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        raw="this creature has double strike",
                    ),
                ),
            )
        ),
    ),
    # Crime payoff (Oko, the Ringleader) — the condition-form "if you've committed a
    # crime this turn" is recovered as a `crime` dropped-static face marker.
    "crimes_matter": (
        {
            "name": "Oko, the Ringleader",
            "type_line": "Legendary Planeswalker — Oko",
            "oracle_text": (
                "At the beginning of combat on your turn, Oko becomes a copy of "
                "up to one target creature you control until end of turn, except "
                "he has hexproof.\n+1: Draw two cards. If you've committed a "
                "crime this turn, discard a card. Otherwise, discard two cards.\n"
                "−1: Create a 3/3 green Elk creature token."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="crime",
                        scope="you",
                        raw="if you've committed a crime",
                    ),
                ),
            )
        ),
    ),
    # Group mana (Magus of the Vineyard) — a ramp effect whose raw names a
    # non-controller recipient ("that player adds {G}{G}"), read by _GROUP_MANA_RAW
    # (phase has no recipient field, so the discriminator lives in the raw).
    "group_mana": (
        {
            "name": "Magus of the Vineyard",
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "At the beginning of each player's first main phase, that player "
                "adds {G}{G}."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="begin_main", scope="each"),
                effects=(
                    Effect(
                        category="ramp",
                        scope="any",
                        raw="that player adds {G}{G}",
                    ),
                ),
            )
        ),
    ),
    # Low-power payoff (Subira) — a Power:LE predicate on a you-controller Creature
    # Filter (the buff/etb shape's predicate phase drops, rebuilt by _LOW_POWER_REF),
    # read by _predicate_build_around_lanes.
    "low_power_matters": (
        {
            "name": "Subira, Tulzidi Caravanner",
            "type_line": "Legendary Creature — Human Shaman",
            "oracle_text": (
                "Haste\n{1}: Another target creature with power 2 or less can't "
                "be blocked this turn.\n{1}{R}, {T}, Discard your hand: Until end "
                "of turn, whenever a creature you control with power 2 or less "
                "deals combat damage to a player, draw a card."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="tap",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",),
                            controller="you",
                            predicates=("PtComparison:Power:LE:2",),
                        ),
                        raw="creature you control with power 2 or less",
                    ),
                ),
            )
        ),
    ),
    # Conferred pay-life cost (Underworld Connections) — the "Pay 1 life:" inside a
    # granted quoted ability phase drops is recovered as a `life_payment` marker.
    "life_payment_insurance": (
        {
            "name": "Underworld Connections",
            "type_line": "Enchantment — Aura",
            "oracle_text": (
                'Enchant land\nEnchanted land has "{T}, Pay 1 life: Draw a card."'
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="life_payment",
                        scope="you",
                        raw="Pay 1 life:",
                    ),
                ),
            )
        ),
    ),
    # sacrifice_matters ← a you-sacrifice Effect (scope not opp/each, a non-land
    # subject, not a forced-opponent edict). Disciple of Bolas sacs "another
    # creature" — phase emits scope "any" with a Creature subject.
    "sacrifice_matters": (
        {
            "name": "Disciple of Bolas",
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "When this creature enters, sacrifice another creature. You gain "
                "X life and draw X cards, where X is that creature's power."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="sacrifice",
                        scope="any",
                        subject=Filter(card_types=("Creature",), controller="any"),
                        raw="When ~ enters, sacrifice another creature. …",
                    ),
                ),
            )
        ),
    ),
    # lifeloss_matters ← a structured `lose_life` Effect. Gray Merchant drains each
    # opponent (phase emits scope "any" for "each opponent loses N").
    "lifeloss_matters": (
        {
            "name": "Gray Merchant of Asphodel",
            "type_line": "Creature — Zombie",
            "oracle_text": (
                "When this creature enters, each opponent loses X life, where X is "
                "your devotion to black. You gain life equal to the life lost this "
                "way."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="lose_life",
                        scope="any",
                        raw="each opponent loses X life",
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


def test_blood_matters_fires_from_a_sacrifice_effect_subject():
    """Token-subtype sacrifice PAYOFF (effect side): Wedding Security "sacrifice a
    Blood token" — a `sacrifice` Effect whose subject Filter carries the Blood
    subtype opens blood_matters via the IR, not the deleted floor regex."""
    card = {
        "name": "Wedding Security",
        "type_line": "Creature — Human Soldier",
        "oracle_text": (
            "Whenever this creature attacks, you may sacrifice a Blood token. If "
            "you do, put a +1/+1 counter on this creature and draw a card."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="attacks", scope="you"),
            effects=(
                Effect(
                    category="sacrifice",
                    scope="any",
                    subject=Filter(
                        subtypes=("Blood",),
                        controller="you",
                        predicates=("Token",),
                    ),
                    raw="you may sacrifice a Blood token",
                ),
            ),
        )
    )
    assert "blood_matters" not in {s.key for s in extract_signals(card)}
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_matters_fires_from_a_sacrificed_trigger_subject():
    """Token-subtype sacrifice PAYOFF (trigger side): Blood Hypnotist "whenever you
    sacrifice one or more Blood tokens" — a `sacrificed` Trigger whose subject Filter
    carries the Blood subtype opens blood_matters via the IR."""
    card = {
        "name": "Blood Hypnotist",
        "type_line": "Creature — Vampire Wizard",
        "oracle_text": (
            "This creature can't block.\nWhenever you sacrifice one or more Blood "
            "tokens, target creature can't block this turn. This ability triggers "
            "only once each turn."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="sacrificed",
                scope="you",
                subject=Filter(
                    subtypes=("Blood",),
                    controller="you",
                    predicates=("Token",),
                ),
            ),
            effects=(Effect(category="cant_block", scope="any", raw="can't block"),),
        )
    )
    assert "blood_matters" not in {s.key for s in extract_signals(card)}
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_matters_fires_from_a_recovered_choice_list_maker():
    """Token-subtype maker recovery (choice list): Transmutation Font "create your
    choice of a Blood token, a Clue token, or a Food token" — phase drops the choice
    subtypes onto a `choose` effect; project._narrow_token_subtype_makers recovers
    them as make_token markers, so all three lanes fire via the IR."""
    card = {
        "name": "Transmutation Font",
        "type_line": "Artifact",
        "oracle_text": (
            "{T}: Create your choice of a Blood token, a Clue token, or a Food token."
        ),
    }
    ir = _ir(
        Ability(
            kind="activated",
            cost="tap",
            effects=(
                # the recovered make_token markers the projection appends
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Blood",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Clue",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Food",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
            ),
        )
    )
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "blood_matters" in keys
    # the generalized recovery also opens clue/food (these stay floor-served lanes,
    # but the structural maker recovery is general — proves the widening generalized)
    assert "clue_matters" in keys
    assert "food_matters" in keys


def test_blood_matters_fires_from_a_recovered_granted_ability_maker():
    """Token-subtype maker recovery (granted ability): Ceremonial Knife grants the
    equipped creature a quoted "create a Blood token" ability — phase folds it into a
    `pump` carrier raw; the projection recovers the Blood make_token marker, so
    blood_matters fires via the IR."""
    card = {
        "name": "Ceremonial Knife",
        "type_line": "Artifact — Equipment",
        "oracle_text": (
            'Equipped creature gets +1/+0 and has "Whenever this creature deals '
            'combat damage, create a Blood token."\nEquip {2}'
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="any",
                    subject=Filter(
                        card_types=("Creature",), predicates=("EquippedBy",)
                    ),
                    raw='Equipped creature gets +1/+0 and has "Whenever ~ deals '
                    'combat damage, create a Blood token."',
                ),
                # the recovered make_token marker the projection appends
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Blood",), predicates=("Token",)),
                    raw='Equipped creature gets +1/+0 and has "Whenever ~ deals '
                    'combat damage, create a Blood token."',
                ),
            ),
        )
    )
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}
