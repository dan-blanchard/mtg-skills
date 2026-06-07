"""Keyword-coverage gaps surfaced by the exhaustive CR 702/701 audit.

Each avenue here closes a confirmed gap where a real deckbuilding archetype keyed on a
keyword ability/action was not surfaced. Every matcher was bulk-validated during the
audit (the "existing avenue catches 0/N" disjointness proofs are pinned as tests). Tests
use synthetic records (no network / bulk), same as the rest of the suite.
"""

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import Signal, extract_signals


def _sig(key, scope="you", subject=""):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def _keys(card):
    return {s.key for s in extract_signals(card)}


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
        "oracle_text": "Commander ninjutsu {U}{B}\nWhenever a Ninja you control deals combat damage to a player, reveal the top card of your library and put it into your hand. Each opponent loses life equal to that card's mana value.",
    }
    SATORU = {
        "name": "Satoru Umezawa",
        "type_line": "Legendary Creature — Human Ninja",
        "oracle_text": "Each creature card in your hand has ninjutsu {1}{U}{B}.\nWhenever a creature you control deals combat damage to a player, you may draw a card.",
    }

    def test_ninjutsu_commander_emits_ninja_subject(self):
        # Today: emits ninjutsu_matters but no Ninja subject. After: type_matters:Ninja.
        assert "Ninja" in _subjects(self.YURIKO, "type_matters")
        assert "Ninja" in _subjects(self.SATORU, "type_matters")

    def test_ninja_subject_resolves_to_tribal_avenue(self):
        spec = spec_for(_sig("type_matters", "you", "Ninja"))
        assert spec is not None
        assert spec.search == {"card_type": "Ninja"}
        # serves a Ninja-payoff card the old \bninjutsu\b regex missed
        assert serves(
            {
                "name": "Throatseeker",
                "type_line": "Creature — Rat Ninja",
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
                "oracle_text": "Haste\nWhenever a creature you control attacks, Hellrider deals 1 damage to the player or planeswalker it's attacking.",
            },
            {
                "name": "Shared Animosity",
                "type_line": "Enchantment",
                "oracle_text": "Whenever a creature you control attacks, it gets +1/+0 until end of turn for each other attacking creature that shares a creature type with it.",
            },
            {
                "name": "Adeline, Resplendent Cathar",
                "type_line": "Legendary Creature — Human Soldier",
                "oracle_text": "Whenever you attack, for each opponent, create a 1/1 white Human creature token.",
            },
        ):
            assert serves(card, self.SIG), card["name"]

    def test_haste_and_tokens_still_served(self):
        assert serves(
            {
                "name": "Fervor",
                "type_line": "Enchantment",
                "oracle_text": "Creatures you control have haste.",
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
            "oracle_text": "Haste\n{T}, Discard a card: Draw a card. Then if the discarded card has madness, untap Anje Falkenrath.",
        }
        assert "madness_matters" in _keys(anje)

    def test_madness_keyword_card_emits_and_serves(self):
        visitor = {
            "name": "Asylum Visitor",
            "type_line": "Creature — Vampire Wizard",
            "oracle_text": "Madness {B}",
            "keywords": ["Madness"],
        }
        assert "madness_matters" in _keys(visitor)
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
            "type_line": "Legendary Creature — Human",
            "oracle_text": "Start your engines!\nMax speed — Whenever you attack, exile the top card of your library.",
            "keywords": ["Start your engines!", "Max speed"],
        }
        assert "speed_matters" in _keys(samut)

    def test_speed_keyword_card_served(self):
        card = {
            "name": "Howlsquad Heavy",
            "type_line": "Creature — Goblin",
            "oracle_text": "Max speed — Other Goblins you control cost {1} less.",
            "keywords": ["Max speed"],
        }
        assert serves(card, _sig("speed_matters", "you"))


class TestDiscoverMatters:
    """Discover (CR 701.57) — model like cascade: surface discover sources + low-MV
    value spells. cascade_matters serves 0/28; Lara Croft (discovery counter) excluded."""

    def test_discover_card_emits_and_served(self):
        appraiser = {
            "name": "Geological Appraiser",
            "type_line": "Creature — Human",
            "oracle_text": "When this creature enters, discover 3.",
            "keywords": ["Discover"],
        }
        assert "discover_matters" in _keys(appraiser)
        assert serves(appraiser, _sig("discover_matters", "you"))


class TestForetellMatters:
    """Foretell (CR 702.143) — the payoff/engine axis (Alrund, Ranar, Dream Devourer)
    is unsurfaced; the foretell preset finds keyword-bearers only."""

    def test_foretell_keyword_card_emits_and_served(self):
        doomskar = {
            "name": "Doomskar",
            "type_line": "Sorcery",
            "oracle_text": "Foretell {1}{W}{W}\nDestroy all creatures.",
            "keywords": ["Foretell"],
        }
        assert "foretell_matters" in _keys(doomskar)
        assert serves(doomskar, _sig("foretell_matters", "you"))

    def test_foretell_payoff_carer_emits(self):
        alrund = {
            "name": "Alrund, God of the Cosmos",
            "type_line": "Legendary Creature — God",
            "oracle_text": "Alrund gets +1/+1 for each card in your hand and each foretold card you own in exile.",
        }
        assert "foretell_matters" in _keys(alrund)


class TestUndyingPersistMatters:
    """Undying (702.93) / Persist (702.79) — death-triggered self-return; the recursion
    lives in the keyword, so death_matters/self-recur miss them. Grants surface too."""

    def test_persist_card_emits_and_served(self):
        finks = {
            "name": "Kitchen Finks",
            "type_line": "Creature — Ouphe",
            "oracle_text": "When this creature enters, you gain 2 life.\nPersist",
            "keywords": ["Persist"],
        }
        assert "undying_persist_matters" in _keys(finks)
        assert serves(finks, _sig("undying_persist_matters", "you"))

    def test_grant_card_emits(self):
        mikaeus = {
            "name": "Mikaeus, the Unhallowed",
            "type_line": "Legendary Creature — Zombie",
            "oracle_text": "Other non-Human creatures you control get +1/+1 and have undying.",
        }
        assert "undying_persist_matters" in _keys(mikaeus)
