"""Keyword-coverage gaps surfaced by the exhaustive CR 702/701 audit.

Each avenue here closes a confirmed gap where a real deckbuilding archetype keyed on a
keyword ability/action was not surfaced. Every matcher was bulk-validated during the
audit (the "existing avenue catches 0/N" disjointness proofs are pinned as tests). Tests
use synthetic records (no network / bulk), same as the rest of the suite.
"""

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity


def _sig(key, scope="you", subject=""):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def _keys(card):
    return {s.key for s in extract_signals(card)}


# A minimal non-None IR for ADR-0027 keys whose IR source scans the record
# directly (kept word-detector mirror / keyword array).
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _keys_hybrid(card, ir=None):
    return {s.key for s in extract_signals_hybrid(card, ir or _bare_ir())}


def _ir_with(*abilities: Ability, keywords: tuple[str, ...] = ()) -> Card:
    """A Card IR carrying the given abilities/keywords — the structural marker an
    ADR-0027-migrated effect-based key reads (e.g. a `madness` payoff marker)."""
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", keywords=keywords, abilities=tuple(abilities)),),
    )


def _subjects(card, key):
    return {s.subject for s in extract_signals(card) if s.key == key}


# ── Batch A: high-severity wiring fixes ──────────────────────────────────────
class TestNinjaTribal:
    """Ninjutsu commanders (Yuriko/Satoru/Higure) emit ninjutsu_matters but never
    type_matters:Ninja, so the 26-card Ninja tribal payoff axis (lords/equipment/ETB)
    is invisible. Wire ninjutsu -> type_matters:Ninja (CR 702.49)."""

    YURIKO = {
        "name": "Yuriko, the Tiger's Shadow",
        "type_line": "Legendary Creature — Human Ninja",
        "oracle_text": "Commander ninjutsu {U}{B} ({U}{B}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand or the command zone tapped and attacking.)\nWhenever a Ninja you control deals combat damage to a player, reveal the top card of your library and put that card into your hand. Each opponent loses life equal to that card's mana value.",
    }
    SATORU = {
        "name": "Satoru Umezawa",
        "type_line": "Legendary Creature — Human Ninja",
        "oracle_text": "Whenever you activate a ninjutsu ability, look at the top three cards of your library. Put one of them into your hand and the rest on the bottom of your library in any order. This ability triggers only once each turn.\nEach creature card in your hand has ninjutsu {2}{U}{B}.",
    }

    def test_ninjutsu_commander_emits_ninja_subject(self):
        # Today: emits ninjutsu_matters but no Ninja subject. After: type_matters:Ninja.
        # ADR-0027: type_matters migrated → hybrid path.
        def _ninja_subjects(card):
            return {
                s.subject
                for s in extract_signals_hybrid(card, _bare_ir())
                if s.key == "type_matters"
            }

        assert "Ninja" in _ninja_subjects(self.YURIKO)
        assert "Ninja" in _ninja_subjects(self.SATORU)

    def test_ninja_subject_resolves_to_tribal_avenue(self):
        spec = spec_for(_sig("type_matters", "you", "Ninja"))
        assert spec is not None
        assert spec.search == {"card_type": "Ninja"}
        # serves a Ninja-payoff card the old \bninjutsu\b regex missed
        assert serves(
            {
                "name": "Throatseeker",
                "type_line": "Creature — Vampire Ninja",
                "oracle_text": "Unblocked attacking Ninjas you control have lifelink.",
            },
            _sig("type_matters", "you", "Ninja"),
        )

    def test_non_ninja_commander_no_ninja_subject(self):
        elf = {
            "name": "Llanowar Elf Lord",
            "type_line": "Legendary Creature — Elf",
            "oracle_text": "Other Elves you control get +1/+1.",
        }
        assert "Ninja" not in _subjects(elf, "type_matters")


class TestAttackTriggerPayoffs:
    """The existing attack_matters serve only credits haste-grant + token-makers, so it
    catches 40/223 of the "whenever you attack" payoff axis. Widen the serve to surface
    attack-trigger payoffs (Hellrider, Adeline, Shared Animosity) — CR 702.121/508."""

    SIG = _sig("attack_matters", "you")

    def test_attack_trigger_payoffs_served(self):
        for card in (
            {
                "name": "Hellrider",
                "type_line": "Creature — Devil",
                "oracle_text": "Haste\nWhenever a creature you control attacks, this creature deals 1 damage to the player or planeswalker it's attacking.",
            },
            {
                "name": "Shared Animosity",
                "type_line": "Enchantment",
                "oracle_text": "Whenever a creature you control attacks, it gets +1/+0 until end of turn for each other attacking creature that shares a creature type with it.",
            },
            {
                "name": "Adeline, Resplendent Cathar",
                "type_line": "Legendary Creature — Human Knight",
                "oracle_text": "Vigilance\nAdeline's power is equal to the number of creatures you control.\nWhenever you attack, for each opponent, create a 1/1 white Human creature token that's tapped and attacking that player or a planeswalker they control.",
            },
        ):
            assert serves(card, self.SIG), card["name"]

    def test_haste_and_tokens_still_served(self):
        assert serves(
            {
                "name": "Fervor",
                "type_line": "Enchantment",
                "oracle_text": "Creatures you control have haste. (They can attack and {T} as soon as they come under your control.)",
                "keywords": [],
            },
            self.SIG,
        )

    def test_opponent_attack_not_served(self):
        # "whenever a creature attacks YOU" is a defensive trigger, not a payoff.
        assert not serves(
            {
                "name": "Defensive Wall",
                "type_line": "Creature — Wall",
                "oracle_text": "Whenever a creature attacks you, you gain 1 life.",
            },
            self.SIG,
        )


# ── Batch B: structured keyword[] avenues ────────────────────────────────────
class TestMadnessMatters:
    """Madness (CR 702.35) decks discard cards to cast them for their madness cost.
    discard_matters overlaps only 1/61 madness cards, so the payoff axis is uncovered."""

    def test_madness_care_commander_emits_signal(self):
        anje = {
            "name": "Anje Falkenrath",
            "type_line": "Legendary Creature — Vampire",
            "oracle_text": "Haste\n{T}, Discard a card: Draw a card.\nWhenever you discard a card, if it has madness, untap Anje Falkenrath.",
        }
        # ADR-0027: madness_matters migrated to the Card IR — Anje's "if it has
        # madness" payoff rides a `madness` marker (project._narrow_payoff_condition
        # _refs), so it comes through the hybrid, not the pure regex path.
        ir = _ir_with(
            Ability(
                kind="triggered",
                effects=(
                    Effect(category="madness", scope="you", raw="if it has madness"),
                ),
            )
        )
        assert "madness_matters" in _keys_hybrid(anje, ir)
        assert "madness_matters" not in _keys(anje)

    def test_madness_keyword_card_emits_and_serves(self):
        visitor = {
            "name": "Asylum Visitor",
            "type_line": "Creature — Vampire Wizard",
            "oracle_text": "At the beginning of each player's upkeep, if that player has no cards in hand, you draw a card and you lose 1 life.\nMadness {1}{B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)",
            "keywords": ["Madness"],
        }
        # The Scryfall madness keyword opens the lane via _IR_KEYWORD_MAP (hybrid).
        assert "madness_matters" in _keys_hybrid(visitor)
        assert serves(visitor, _sig("madness_matters", "you"))

    def test_non_madness_not_served(self):
        assert not serves(
            {
                "name": "Grizzly Bears",
                "type_line": "Creature — Bear",
                "oracle_text": "",
                "keywords": [],
            },
            _sig("madness_matters", "you"),
        )


class TestSpeedMatters:
    """Aetherdrift Speed (CR 702.179/702.178): the Max-speed payoff axis is unsurfaced;
    lifeloss_matters overlaps 0/40 speed cards."""

    def test_speed_commander_emits(self):
        samut = {
            "name": "Samut, the Driving Force",
            "type_line": "Legendary Creature — Human Warrior Cleric",
            "oracle_text": "First strike, vigilance, haste\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nOther creatures you control get +X/+0, where X is your speed.\nNoncreature spells you cast cost {X} less to cast, where X is your speed.",
            "keywords": ["Start your engines!", "Max speed"],
        }
        # ADR-0027: speed_matters migrated to the IR (kept word mirror) — hybrid path.
        assert "speed_matters" in _keys_hybrid(samut)

    def test_speed_keyword_card_served(self):
        card = {
            "name": "Howlsquad Heavy",
            "type_line": "Creature — Goblin Mercenary",
            "oracle_text": "Start your engines!\nOther Goblins you control have haste.\nAt the beginning of combat on your turn, create a 1/1 red Goblin creature token. That token attacks this combat if able.\nMax speed — {T}: Add {R} for each Goblin you control.",
            "keywords": ["Max speed"],
        }
        assert serves(card, _sig("speed_matters", "you"))


class TestDiscoverMatters:
    """Discover (CR 701.57) — model like cascade: surface discover sources + low-MV
    value spells. cascade_matters serves 0/28; Lara Croft (discovery counter) excluded."""

    def test_discover_card_emits_and_served(self):
        appraiser = {
            "name": "Geological Appraiser",
            "type_line": "Creature — Human Artificer",
            "oracle_text": "When this creature enters, if you cast it, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
            "keywords": ["Discover"],
        }
        # ADR-0027: discover_matters migrated to the Card IR — the discover SOURCES
        # carry the Scryfall `discover` keyword (_IR_KEYWORD_MAP), so it comes
        # through the hybrid, not the pure regex path.
        assert "discover_matters" in _keys_hybrid(appraiser)
        assert "discover_matters" not in _keys(appraiser)
        assert serves(appraiser, _sig("discover_matters", "you"))


class TestForetellMatters:
    """Foretell (CR 702.143) — the payoff/engine axis (Alrund, Ranar, Dream Devourer)
    is unsurfaced; the foretell preset finds keyword-bearers only."""

    def test_foretell_keyword_card_emits_and_served(self):
        doomskar = {
            "name": "Doomskar",
            "type_line": "Sorcery",
            "oracle_text": "Destroy all creatures.\nForetell {1}{W}{W} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)",
            "keywords": ["Foretell"],
        }
        # ADR-0027: foretell_matters migrated to the Card IR — the Scryfall foretell
        # keyword opens the lane via _IR_KEYWORD_MAP (hybrid), not the regex floor.
        assert "foretell_matters" in _keys_hybrid(doomskar)
        assert serves(doomskar, _sig("foretell_matters", "you"))

    def test_foretell_payoff_carer_emits(self):
        alrund = {
            "name": "Alrund, God of the Cosmos",
            "type_line": "Legendary Creature — God",
            "oracle_text": "Alrund gets +1/+1 for each card in your hand and each foretold card you own in exile.",
        }
        # The Foretold predicate on the counted subject Filter opens the lane (the
        # structural payoff bind), not the deleted regex floor.
        ir = _ir_with(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="any",
                        amount=Quantity(
                            op="count",
                            factor=1,
                            subject=Filter(
                                card_types=("Card",),
                                predicates=("Foretold", "Owned", "InZone"),
                            ),
                        ),
                        raw="+1/+1 for each foretold card you own in exile",
                    ),
                ),
            )
        )
        assert "foretell_matters" in _keys_hybrid(alrund, ir)
        assert "foretell_matters" not in _keys(alrund)


class TestUndyingPersistMatters:
    """Undying (702.93) / Persist (702.79) — death-triggered self-return; the recursion
    lives in the keyword, so death_matters/self-recur miss them. Grants surface too."""

    def test_persist_card_emits_and_served(self):
        # ADR-0027: undying_persist_matters migrated to the Card IR — the intrinsic
        # Persist bearer fires from the Scryfall keyword array (_IR_KEYWORD_MAP), so it
        # comes through the hybrid path, not the deleted regex.
        finks = {
            "name": "Kitchen Finks",
            "type_line": "Creature — Ouphe",
            "oracle_text": "When this creature enters, you gain 2 life.\nPersist (When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)",
            "keywords": ["Persist"],
        }
        assert "undying_persist_matters" in _keys_hybrid(finks)
        assert "undying_persist_matters" not in _keys(finks)
        assert serves(finks, _sig("undying_persist_matters", "you"))

    def test_grant_card_emits(self):
        # ADR-0027: the keyword-less GRANTER ("creatures you control … have undying")
        # is recovered as an `undying_persist` conferred-grant marker → the hybrid path.
        mikaeus = {
            "name": "Mikaeus, the Unhallowed",
            "type_line": "Legendary Creature — Zombie Cleric",
            "oracle_text": "Intimidate (This creature can't be blocked except by artifact creatures and/or creatures that share a color with it.)\nWhenever a Human deals damage to you, destroy it.\nOther non-Human creatures you control get +1/+1 and have undying. (When a creature with undying dies, if it had no +1/+1 counters on it, return it to the battlefield under its owner's control with a +1/+1 counter on it.)",
        }
        mikaeus_ir = _ir_with(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="undying_persist",
                        scope="you",
                        raw="other non-Human creatures you control … have undying",
                    ),
                ),
            )
        )
        assert "undying_persist_matters" in _keys_hybrid(mikaeus, mikaeus_ir)
        assert "undying_persist_matters" not in _keys(mikaeus)


# ── Batch C: counter / payoff-regex avenues ──────────────────────────────────
class TestMinusCountersMatter:
    """counters_matter is hard-pinned to +1/+1, so the symmetric -1/-1 axis
    (Wither/Infect/aristocrats — Hapatra, Necroskitter) had no home (CR 122/702.80/702.90)."""

    HAPATRA = {
        "name": "Hapatra, Vizier of Poisons",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": "Whenever Hapatra deals combat damage to a player, you may put a -1/-1 counter on target creature.\nWhenever you put one or more -1/-1 counters on a creature, create a 1/1 green Snake creature token with deathtouch.",
    }

    def test_minus_counter_commander_emits(self):
        # ADR-0027: minus_counters_matter migrated to the IR (place_counter(m1m1) +
        # "-1/-1 counter" kept word mirror) — hybrid path.
        assert "minus_counters_matter" in _keys_hybrid(self.HAPATRA)

    def test_plus_one_commander_does_not_emit_minus(self):
        # The +1/+1-pin is load-bearing: a +1/+1 commander must NOT fire minus_counters.
        ghave = {
            "name": "Plus Counter Lord",
            "type_line": "Legendary Creature — Fungus",
            "oracle_text": "At the beginning of your upkeep, put a +1/+1 counter on each creature you control.",
        }
        assert "minus_counters_matter" not in _keys_hybrid(ghave)

    def test_minus_payoff_served_wither_keyword_served(self):
        sig = _sig("minus_counters_matter", "you")
        assert serves(self.HAPATRA, sig)
        assert serves(
            {
                "name": "Twinblade Slasher",
                "type_line": "Creature — Elf Warrior",
                "oracle_text": "Wither (This deals damage to creatures in the form of -1/-1 counters.)\n{1}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn.",
                "keywords": ["Wither"],
            },
            sig,
        )


class TestCyclingMatters:
    """Cycling (CR 702.29) payoffs use "cycle or discard" wording; discard_matters'
    serve catches 0/32 (it needs a literal "you discard")."""

    DRAKE_HAVEN = {
        "name": "Drake Haven",
        "type_line": "Enchantment",
        "oracle_text": "Whenever you cycle or discard a card, you may pay {1}. If you do, create a 2/2 blue Drake creature token with flying.",
    }

    def test_cycling_payoff_commander_emits(self):
        # ADR-0027: cycling_matters migrated to the Card IR — the "cycle or discard"
        # payoff phase flattens to event='other', recovered as a `cycling_payoff`
        # marker (read via _DOER_EFFECT_KEYS); the regex path no longer produces it.
        ir = _ir_with(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cycling_payoff",
                        scope="you",
                        raw="Whenever you cycle or discard a card",
                    ),
                ),
            )
        )
        assert "cycling_matters" in _keys_hybrid(self.DRAKE_HAVEN, ir)
        assert "cycling_matters" not in _keys(self.DRAKE_HAVEN)

    def test_cycling_payoff_served_not_by_discard_matters(self):
        assert serves(self.DRAKE_HAVEN, _sig("cycling_matters", "you"))
        # disjoint from discard_matters (its serve needs "you discard", not "cycle or discard")
        assert not serves(self.DRAKE_HAVEN, _sig("discard_matters", "you"))


class TestKickedSpellMatters:
    """Kicker (CR 702.33) payoffs trigger on casting a kicked spell; spellcast_matters
    serves 0/10 of them."""

    VERAZOL = {
        "name": "Verazol, the Split Current",
        "type_line": "Legendary Creature — Serpent",
        "oracle_text": "Verazol enters with a +1/+1 counter on it for each mana spent to cast it.\nWhenever you cast a kicked spell, you may remove two +1/+1 counters from Verazol. If you do, copy that spell. You may choose new targets for the copy. (A copy of a permanent spell becomes a token.)",
    }

    def test_kicked_payoff_commander_emits(self):
        # ADR-0027: kicked_spell_matters migrated to the Card IR (a byte-identical
        # _KICKED_SPELL_MIRROR in _IR_KEPT_DETECTORS — the "whenever you cast a kicked
        # spell" payoff phase under-structures; NOT the bare `\bkicked\b` keyword route,
        # which over-fires +171), so it fires via the hybrid path, not pure regex.
        assert "kicked_spell_matters" in _keys_hybrid(self.VERAZOL)
        assert "kicked_spell_matters" not in _keys(self.VERAZOL)

    def test_kicked_payoff_served_not_spellcast(self):
        sig = _sig("kicked_spell_matters", "you")
        assert serves(self.VERAZOL, sig)
        assert not serves(self.VERAZOL, _sig("spellcast_matters", "you"))


class TestColorlessMatters:
    """Devoid/Eldrazi colorless payoffs (anthems/cost-reduction/cast-triggers) keyed on
    "colorless creature/spell/permanent" (CR 702.114) had no avenue; type_matters:Eldrazi
    surfaces by subtype, not the colorless axis."""

    def test_colorless_payoff_commander_emits_and_served(self):
        monument = {
            "name": "Forsaken Monument",
            "type_line": "Legendary Artifact",
            "oracle_text": "Colorless creatures you control get +2/+2.\nWhenever you tap a permanent for {C}, add an additional {C}.\nWhenever you cast a colorless spell, you gain 2 life.",
        }
        # ADR-0027: colorless_matters migrated to the Card IR (the ColorCount:EQ:0
        # subject-Filter predicate + a "colorless (creature|spell|permanent)" kept word
        # mirror), so it comes through the hybrid path, not pure regex.
        assert "colorless_matters" not in _keys(monument)
        assert "colorless_matters" in _keys_hybrid(monument)
        assert serves(monument, _sig("colorless_matters", "you"))

    def test_colorless_hate_counterspell_excluded(self):
        # Ceremonious Rejection is colorless-HATE, not a payoff — must not be served.
        assert not serves(
            {
                "name": "Ceremonious Rejection",
                "type_line": "Instant",
                "oracle_text": "Counter target colorless spell.",
            },
            _sig("colorless_matters", "you"),
        )


class TestExaltedLoneAttacker:
    """Exalted (CR 702.83) rewards attacking ALONE; the attacks-alone payoff/trigger axis
    (Rafiq, Sublime Archangel, Angelic Exaltation) was only loosely under voltron."""

    def test_attacks_alone_commander_emits_and_served(self):
        rafiq = {
            "name": "Rafiq of the Many",
            "type_line": "Legendary Creature — Human Knight",
            "oracle_text": "Exalted (Whenever a creature you control attacks alone, that creature gets +1/+1 until end of turn.)\nWhenever a creature you control attacks alone, it gains double strike until end of turn.",
        }
        # ADR-0027: exalted_lone_attacker migrated to the IR (exalted keyword +
        # "attacks alone|exalted" kept word mirror) — hybrid path.
        assert "exalted_lone_attacker" in _keys_hybrid(rafiq)
        assert serves(rafiq, _sig("exalted_lone_attacker", "you"))


# ── Batch D: spell/cast avenues + augments ───────────────────────────────────
class TestFlashMatters:
    """Flash (CR 702.8) build-arounds: flash-GRANTING enablers (Yeva, Leyline) plus
    opponent-turn payoffs. spellslinger excludes creatures, so it never surfaces a flash
    wantlist (flash creatures + granters)."""

    YEVA = {
        "name": "Yeva, Nature's Herald",
        "type_line": "Legendary Creature — Elf Shaman",
        "oracle_text": "Flash (You may cast this spell any time you could cast an instant.)\nYou may cast green creature spells as though they had flash.",
    }

    def test_flash_enabler_commander_emits_and_served(self):
        # ADR-0027 (q2-D3): flash_matters migrated to the IR — the GRANT half binds via
        # cast_with_keyword{flash} + a kept word mirror for the activated / opponent-
        # turn forms. Yeva's "cast … spells … as though they had flash" rides the kept
        # mirror, so a bare IR fires it on the hybrid path.
        assert "flash_matters" in _keys_hybrid(self.YEVA)
        assert "flash_matters" not in _keys(self.YEVA)
        assert serves(self.YEVA, _sig("flash_matters", "you"))

    def test_flash_creature_served_but_not_spellslinger(self):
        viper = {
            "name": "Ambush Viper",
            "type_line": "Creature — Snake",
            "oracle_text": "Flash\nDeathtouch",
            "keywords": ["Flash"],
        }
        assert serves(viper, _sig("flash_matters", "you"))
        assert not serves(viper, _sig("spellcast_matters", "you"))

    def test_self_only_flash_grant_not_an_enabler_signal(self):
        # ADR-0027 (q2-D3): a one-shot "as though IT had flash" (singular pronoun) is
        # NOT a flash ENABLER — the kept mirror anchors on "as though THEY had flash"
        # (the class grant), so it must not fire on Quicken via the hybrid path either.
        quicken = {
            "name": "Quicken",
            "type_line": "Instant",
            "oracle_text": "The next sorcery spell you cast this turn can be cast as though it had flash. (It can be cast any time you could cast an instant.)\nDraw a card.",
        }
        assert "flash_matters" not in _keys_hybrid(quicken)


class TestTeamEvasionGrant:
    """Team evasion-keyword grants (Sun Quan horsemanship, Iroas menace) — evasion_self
    covers single-attacker/landwalk/team-unblockable but misses the keyword grants."""

    SUN_QUAN = {
        "name": "Sun Quan, Lord of Wu",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": "Creatures you control have horsemanship. (They can't be blocked except by creatures with horsemanship.)",
    }

    def test_team_evasion_grant_emits_and_served(self):
        # ADR-0027: team_evasion_grant migrated to the IR (the generic grant_keyword +
        # a kept word mirror for the subtype/color-scoped grants) — hybrid path.
        assert "team_evasion_grant" in _keys_hybrid(self.SUN_QUAN)
        assert serves(self.SUN_QUAN, _sig("team_evasion_grant", "you"))

    def test_disjoint_from_evasion_self(self):
        assert not serves(self.SUN_QUAN, _sig("evasion_self", "you"))


class TestEnchantmentsCastAugment:
    """enchantments_matter's {card_type:Enchantment} type-serve + old payoff regex miss
    14 plain Creatures that trigger on casting an enchantment (Verduran Enchantress)."""

    def test_enchantment_cast_creature_now_served(self):
        verduran = {
            "name": "Verduran Enchantress",
            "type_line": "Creature — Human Druid",
            "oracle_text": "Whenever you cast an enchantment spell, you may draw a card.",
        }
        assert serves(verduran, _sig("enchantments_matter", "you"))


# ── Batch E: subtype avenues, tribal wiring, low-severity, conflict resolutions ─
class TestSagaMatters:
    """Saga-matters (CR 714/702.155) commanders (Tom Bombadil, Narci) care about chapter
    retriggers / lore counters; enchantments_matter serves Sagas as enchantments but
    catches only 1/14 chapter-retrigger payoffs."""

    LORD = {
        "name": "Test Saga Lord",
        "type_line": "Legendary Creature — Avatar",
        "oracle_text": "Sagas you control have read ahead.\nWhenever you put one or more lore counters on a Saga, draw a card.",
    }

    def test_saga_commander_emits(self):
        # ADR-0027: saga_matters migrated to the Card IR — the "lore counters on a Saga"
        # reference is a `saga` dropped-static marker → the hybrid path, not the regex.
        ir = _ir_with(
            Ability(
                kind="static",
                effects=(Effect(category="saga", scope="you", raw="lore counters"),),
            )
        )
        assert "saga_matters" in _keys_hybrid(self.LORD, ir)
        assert "saga_matters" not in _keys(self.LORD)

    def test_saga_search_is_subtype_and_serves(self):
        spec = spec_for(_sig("saga_matters", "you"))
        assert spec.search == {"card_type": "Saga"}
        assert serves(self.LORD, _sig("saga_matters", "you"))
        # a Saga enabler is served via its subtype
        assert serves(
            {
                "name": "Fall of the Thran",
                "type_line": "Enchantment — Saga",
                "oracle_text": "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Destroy all lands.\nII, III — Each player returns two land cards from their graveyard to the battlefield.",
            },
            _sig("saga_matters", "you"),
        )


class TestLessonsMatter:
    """Lessons (CR 701.48) — typed_spellcast drops "Lesson" (subject validated against
    creature-subtype vocab), so a Lessons commander had no avenue; needs type:Lesson."""

    def test_lesson_commander_emits(self):
        iroh = {
            "name": "Uncle Iroh",
            "type_line": "Legendary Creature — Human Noble Ally",
            "oracle_text": "Firebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\nLesson spells you cast cost {1} less to cast.",
        }
        # ADR-0027: lessons_matter is IR-served from the kept word-detector mirror
        # (\blessons?\b), so it comes through the hybrid path, not pure regex.
        assert "lessons_matter" in _keys_hybrid(iroh)
        assert "lessons_matter" not in _keys(iroh)

    def test_lesson_search_is_subtype_and_serves(self):
        spec = spec_for(_sig("lessons_matter", "you"))
        assert spec.search == {"card_type": "Lesson"}
        assert serves(
            {
                "name": "Environmental Sciences",
                "type_line": "Sorcery — Lesson",
                "oracle_text": "Search your library for a basic land card, reveal it, put it into your hand, then shuffle. You gain 2 life.",
            },
            _sig("lessons_matter", "you"),
        )


class TestPlayFromTopAlreadyCovered:
    """The audit proposed play_from_top_matters, but play_from_top already exists (a
    stale-vocab false gap). Pin that it covers the cited card so we don't re-add it."""

    def test_existing_play_from_top_covers_oracle_of_mul_daya(self):
        # ADR-0027 β: play_from_top migrated to the Card IR — served from the hybrid via
        # the structural STATIC cast_from_zone+from:library arm (project.
        # _top_play_permission_marker over phase's TopOfLibraryCastPermission mode). The
        # serve pool stays oracle-defined, so `serves` is unchanged.
        oracle = {
            "name": "Oracle of Mul Daya",
            "type_line": "Creature — Elf Shaman",
            "oracle_text": "You may play an additional land on each of your turns.\nPlay with the top card of your library revealed.\nYou may play lands from the top of your library.",
        }
        ir = _ir_with(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cast_from_zone",
                        scope="you",
                        zones=("from:library",),
                        raw="You may play lands from the top of your library.",
                    ),
                ),
            )
        )
        assert "play_from_top" in _keys_hybrid(oracle, ir)
        assert serves(oracle, _sig("play_from_top", "you"))


class TestChangelingTribalEnabler:
    """Changelings (CR 702.73a) are every creature type, but they type-line as
    "Shapeshifter", so {card_type: <subtype>} tribal searches miss all 62 of them for
    every tribe. Inject them into the tribal serve."""

    MAULER = {
        "name": "Taurean Mauler",
        "type_line": "Creature — Shapeshifter",
        "oracle_text": "Changeling (This card is every creature type.)\nWhenever an opponent casts a spell, you may put a +1/+1 counter on this creature.",
        "keywords": ["Changeling"],
    }

    def test_changeling_served_by_any_tribe(self):
        assert serves(self.MAULER, _sig("type_matters", "you", "Goblin"))
        assert serves(self.MAULER, _sig("type_matters", "you", "Elf"))

    def test_type_granter_served(self):
        nexus = {
            "name": "Maskwood Nexus",
            "type_line": "Artifact",
            "oracle_text": "Creatures you control are every creature type. The same is true for creature spells you control and creature cards you own that aren't on the battlefield.\n{3}, {T}: Create a 2/2 blue Shapeshifter creature token with changeling. (It is every creature type.)",
        }
        assert serves(nexus, _sig("type_matters", "you", "Zombie"))

    def test_unrelated_creature_not_served_as_tribe(self):
        bear = {
            "name": "Grizzly Bears",
            "type_line": "Creature — Bear",
            "oracle_text": "",
            "keywords": [],
        }
        assert not serves(bear, _sig("type_matters", "you", "Goblin"))


class TestParadoxPayoffs:
    """Paradox (CR 207.2c / 601.2): "cast a spell from anywhere other than your hand"
    payoffs (Vega, Iraxxa). cast_from_exile's serve needs the literal "from exile" and
    misses 16/17 — surface them as a sub-avenue under cast_from_exile."""

    VEGA = {
        "name": "Vega, the Watcher",
        "type_line": "Legendary Creature — Bird Spirit",
        "oracle_text": "Flying\nWhenever you cast a spell from anywhere other than your hand, draw a card.",
    }

    def test_paradox_commander_emits_cast_from_exile(self):
        # ADR-0027: cast_from_exile migrated to the Card IR via a byte-identical kept
        # WORD MIRROR (the CAST_FROM_EXILE_REGEX row in _IR_KEPT_DETECTORS); the regex
        # path no longer emits it, so assert via the hybrid path. The mirror reads the
        # record's reminder-stripped oracle, so a bare non-None IR routes to it.
        assert "cast_from_exile" in _keys_hybrid(self.VEGA)
        assert "cast_from_exile" not in _keys(self.VEGA)

    def test_paradox_subavenue_serves_vega(self):
        spec = spec_for(_sig("cast_from_exile", "you"))
        extra = next((e for e in spec.extras if "Paradox" in e.label), None)
        assert extra is not None
        assert extra.serve.matches(self.VEGA)


class TestTimeCountersWiden:
    """suspend_matters existed but served only `\\bsuspend\\b`. Widen the same avenue to
    the time-counter superstructure (CR 701.56 time travel / 702.63 vanishing / impending
    / As Foretold) rather than adding a duplicate key."""

    AS_FORETOLD = {
        "name": "As Foretold",
        "type_line": "Enchantment",
        "oracle_text": "At the beginning of your upkeep, put a time counter on this enchantment.\nOnce each turn, you may pay {0} rather than pay the mana cost for a spell you cast with mana value X or less, where X is the number of time counters on this enchantment.",
    }
    VANISHING = {
        "name": "Aeon Chronicler",
        "type_line": "Creature — Avatar",
        "oracle_text": "Aeon Chronicler's power and toughness are each equal to the number of cards in your hand.\nSuspend X—{X}{3}{U}. X can't be 0.\nWhenever a time counter is removed from this card while it's exiled, draw a card.",
        "keywords": ["Vanishing", "Suspend"],
    }

    def test_time_counter_card_emits_suspend_matters(self):
        # ADR-0027: suspend_matters migrated to the Card IR (the `suspend` keyword + a
        # kept word mirror widening to the time-counter superstructure), so the
        # time-counter card is served via the hybrid path, not pure regex.
        assert "suspend_matters" in _keys_hybrid(self.AS_FORETOLD)
        assert "suspend_matters" not in _keys(self.AS_FORETOLD)

    def test_vanishing_keyword_served(self):
        assert serves(self.VANISHING, _sig("suspend_matters", "you"))
        assert serves(self.AS_FORETOLD, _sig("suspend_matters", "you"))


# ── Batch F: deferred quick-tweaks (serve/routing widens + 2 thin new avenues) ─
class TestLostLifeThresholdWiden:
    """lifeloss_matters/opponents matched only continuous "loses life" triggers, not the
    past-tense "if an opponent lost life this turn" THRESHOLD (Spectacle/Rakdos payoffs)."""

    def test_opponent_lost_life_threshold_served(self):
        stromkirk = {
            "name": "Stromkirk Bloodthief",
            "type_line": "Creature — Vampire Rogue",
            "oracle_text": "At the beginning of your end step, if an opponent lost life this turn, put a +1/+1 counter on target Vampire you control.",
        }
        assert serves(stromkirk, _sig("lifeloss_matters", "opponents"))

    def test_self_lost_life_not_served(self):
        # "if you lost life this turn" is a self-payoff, not an opponents-drain payoff.
        ludevic = {
            "name": "Self Lifeloss",
            "type_line": "Enchantment",
            "oracle_text": "At the beginning of your upkeep, if you lost life this turn, draw a card.",
        }
        assert not serves(ludevic, _sig("lifeloss_matters", "opponents"))


class TestCasualtyRouting:
    """Casualty (CR 702.153) sacrifices a creature as an additional cost; a casualty
    commander/granter (Anhelo) should surface the sacrifice-fodder avenue."""

    def test_casualty_grant_emits_sacrifice_matters(self):
        # ADR-0027: sacrifice_matters is IR-served. Anhelo's "has casualty 2" grant is
        # keyword-less, so the projection appends a `sacrifice` grant marker (a
        # non-land Permanent subject) the hybrid reads.
        anhelo = {
            "name": "Anhelo, the Painter",
            "type_line": "Legendary Creature — Vampire Assassin",
            "oracle_text": "Deathtouch\nThe first instant or sorcery spell you cast each turn has casualty 2. (As you cast that spell, you may sacrifice a creature with power 2 or greater. When you do, copy the spell and you may choose new targets for the copy.)",
        }
        ir = _ir_with(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="sacrifice",
                        scope="you",
                        subject=Filter(card_types=("Permanent",), controller="you"),
                        raw="granted/dropped sacrifice outlet",
                    ),
                ),
            )
        )
        assert "sacrifice_matters" in _keys_hybrid(anhelo, ir)
        # and the legacy regex path no longer emits it
        assert "sacrifice_matters" not in _keys(anhelo)


class TestStationDetection:
    """Station (CR 702.184) uses charge counters; station commanders fire neither
    counters_matter (+1/+1-gated) nor proliferate_matters — route them to proliferate."""

    def test_station_keyword_emits_proliferate(self):
        # ADR-0027: proliferate_matters migrated to the Card IR; the station
        # keyword now opens the lane via _IR_KEYWORD_MAP (the IR-only keyword
        # path), so assert the hybrid path.
        ship = {
            "name": "Hearthhull, the Worldseed",
            "type_line": "Legendary Artifact — Spacecraft",
            "oracle_text": "Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n2+ | {1}, {T}, Sacrifice a land: Draw two cards. You may play an additional land this turn.\n8+ | Flying, vigilance, haste\nWhenever you sacrifice a land, each opponent loses 2 life.",
            "keywords": ["Station"],
        }
        assert "proliferate_matters" in _keys_hybrid(ship)


class TestSaddleMatters:
    """Saddle / Mount (CR 702.171) — vehicles_matter catches only 1/33 and serves the
    crew/Vehicle pool, not the attacks-while-saddled payoff axis."""

    CALAMITY = {
        "name": "Calamity, Galloping Inferno",
        "type_line": "Legendary Creature — Horse Mount",
        "oracle_text": "Haste\nWhenever Calamity attacks while saddled, choose a nonlegendary creature that saddled it this turn and create a tapped and attacking token that's a copy of it. Sacrifice that token at the beginning of the next end step. Repeat this process once.\nSaddle 1",
        "keywords": ["Saddle", "Haste"],
    }

    def test_saddle_commander_emits_and_served(self):
        # ADR-0027: saddle_matters migrated to the Card IR (the `saddle` keyword now
        # lives on the IR-only path + a `saddle` effect marker), so it comes through
        # the hybrid, not the pure regex path.
        assert "saddle_matters" in _keys_hybrid(self.CALAMITY)
        assert "saddle_matters" not in _keys(self.CALAMITY)
        assert serves(self.CALAMITY, _sig("saddle_matters", "you"))

    def test_saddle_mount_body_served(self):
        mount = {
            "name": "Bulwark Ox",
            "type_line": "Creature — Ox Mount",
            "oracle_text": "Whenever this creature attacks while saddled, put a +1/+1 counter on target creature.\nSacrifice this creature: Creatures you control with counters on them gain hexproof and indestructible until end of turn.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
            "keywords": ["Saddle"],
        }
        assert serves(mount, _sig("saddle_matters", "you"))


class TestSuspectMatters:
    """Suspect (CR 701.60) — crimes_matter's search catches 2/24 suspect cards; the
    suspect enabler pool was otherwise invisible (niche Mardu/Dimir aggro)."""

    NELLY = {
        "name": "Nelly Borca, Impulsive Accuser",
        "type_line": "Legendary Creature — Human Detective",
        "oracle_text": "Vigilance\nWhenever Nelly Borca attacks, suspect target creature. Then goad all suspected creatures. (A suspected creature has menace and can't block.)\nWhenever one or more creatures an opponent controls deal combat damage to one or more of your opponents, you and the controller of those creatures each draw a card.",
    }

    def test_suspect_commander_emits_and_served(self):
        # ADR-0027: suspect_matters migrated to the Card IR — Nelly's "suspect target
        # creature" is phase's `suspect` effect category, read through the hybrid IR
        # path. The serve pool stays oracle-defined (the hand spec).
        ir = Card(
            oracle_id="x",
            name="Nelly Borca, Impulsive Accuser",
            faces=(
                Face(
                    name="Nelly Borca, Impulsive Accuser",
                    abilities=(
                        Ability(
                            kind="triggered",
                            effects=(
                                Effect(
                                    category="suspect",
                                    scope="you",
                                    raw="suspect target creature",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        assert "suspect_matters" in _keys_hybrid(self.NELLY, ir)
        assert "suspect_matters" not in _keys(self.NELLY)
        assert serves(self.NELLY, _sig("suspect_matters", "you"))
