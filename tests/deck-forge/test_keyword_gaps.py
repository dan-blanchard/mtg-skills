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


# ── Batch C: counter / payoff-regex avenues ──────────────────────────────────
class TestMinusCountersMatter:
    """counters_matter is hard-pinned to +1/+1, so the symmetric -1/-1 axis
    (Wither/Infect/aristocrats — Hapatra, Necroskitter) had no home (CR 122/702.80/702.90)."""

    HAPATRA = {
        "name": "Hapatra, Vizier of Poisons",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": "Whenever Hapatra, Vizier of Poisons deals combat damage to a creature, you may put a -1/-1 counter on that creature.\nWhenever you put one or more -1/-1 counters on a creature, create a 1/1 black Snake creature token with deathtouch.",
    }

    def test_minus_counter_commander_emits(self):
        assert "minus_counters_matter" in _keys(self.HAPATRA)

    def test_plus_one_commander_does_not_emit_minus(self):
        # The +1/+1-pin is load-bearing: a +1/+1 commander must NOT fire minus_counters.
        ghave = {
            "name": "Plus Counter Lord",
            "type_line": "Legendary Creature — Fungus",
            "oracle_text": "At the beginning of your upkeep, put a +1/+1 counter on each creature you control.",
        }
        assert "minus_counters_matter" not in _keys(ghave)

    def test_minus_payoff_served_wither_keyword_served(self):
        sig = _sig("minus_counters_matter", "you")
        assert serves(self.HAPATRA, sig)
        assert serves(
            {
                "name": "Spinebiter",
                "type_line": "Creature — Insect",
                "oracle_text": "Spinebiter",
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
        assert "cycling_matters" in _keys(self.DRAKE_HAVEN)

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
        "oracle_text": "Whenever you cast a kicked spell, put two +1/+1 counters on Verazol, the Split Current.",
    }

    def test_kicked_payoff_commander_emits(self):
        assert "kicked_spell_matters" in _keys(self.VERAZOL)

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
            "oracle_text": "Colorless creatures you control get +1/+1.\nWhenever a colorless creature you control enters, you gain 2 life.",
        }
        assert "colorless_matters" in _keys(monument)
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
            "type_line": "Legendary Creature — Human Wizard",
            "oracle_text": "Exalted\nWhenever a creature you control attacks alone, that creature gains double strike until end of turn.",
        }
        assert "exalted_lone_attacker" in _keys(rafiq)
        assert serves(rafiq, _sig("exalted_lone_attacker", "you"))


# ── Batch D: spell/cast avenues + augments ───────────────────────────────────
class TestFlashMatters:
    """Flash (CR 702.8) build-arounds: flash-GRANTING enablers (Yeva, Leyline) plus
    opponent-turn payoffs. spellslinger excludes creatures, so it never surfaces a flash
    wantlist (flash creatures + granters)."""

    YEVA = {
        "name": "Yeva, Nature's Herald",
        "type_line": "Legendary Creature — Elf Shaman",
        "oracle_text": "Flash\nYou may cast green creature spells as though they had flash.",
    }

    def test_flash_enabler_commander_emits_and_served(self):
        assert "flash_matters" in _keys(self.YEVA)
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
        quicken = {
            "name": "Quicken",
            "type_line": "Instant",
            "oracle_text": "The next instant or sorcery spell you cast this turn can be cast as though it had flash.\nDraw a card.",
        }
        assert "flash_matters" not in _keys(quicken)


class TestTeamEvasionGrant:
    """Team evasion-keyword grants (Sun Quan horsemanship, Iroas menace) — evasion_self
    covers single-attacker/landwalk/team-unblockable but misses the keyword grants."""

    SUN_QUAN = {
        "name": "Sun Quan, Lord of Wu",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": "Horsemanship\nOther creatures you control have horsemanship.",
    }

    def test_team_evasion_grant_emits_and_served(self):
        assert "team_evasion_grant" in _keys(self.SUN_QUAN)
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
        assert "saga_matters" in _keys(self.LORD)

    def test_saga_search_is_subtype_and_serves(self):
        spec = spec_for(_sig("saga_matters", "you"))
        assert spec.search == {"card_type": "Saga"}
        assert serves(self.LORD, _sig("saga_matters", "you"))
        # a Saga enabler is served via its subtype
        assert serves(
            {
                "name": "Fall of the Thran",
                "type_line": "Enchantment — Saga",
                "oracle_text": "(As this Saga enters and after your draw step, add a lore counter.)",
            },
            _sig("saga_matters", "you"),
        )


class TestLessonsMatter:
    """Lessons (CR 701.48) — typed_spellcast drops "Lesson" (subject validated against
    creature-subtype vocab), so a Lessons commander had no avenue; needs type:Lesson."""

    def test_lesson_commander_emits(self):
        iroh = {
            "name": "Uncle Iroh",
            "type_line": "Legendary Creature — Human",
            "oracle_text": "Lesson spells you cast cost {1} less.\nWhenever you cast a Lesson spell, you gain 2 life.",
        }
        assert "lessons_matter" in _keys(iroh)

    def test_lesson_search_is_subtype_and_serves(self):
        spec = spec_for(_sig("lessons_matter", "you"))
        assert spec.search == {"card_type": "Lesson"}
        assert serves(
            {
                "name": "Environmental Sciences",
                "type_line": "Sorcery — Lesson",
                "oracle_text": "Search your library for a basic land card, reveal it, put it into your hand.",
            },
            _sig("lessons_matter", "you"),
        )


class TestPlayFromTopAlreadyCovered:
    """The audit proposed play_from_top_matters, but play_from_top already exists (a
    stale-vocab false gap). Pin that it covers the cited card so we don't re-add it."""

    def test_existing_play_from_top_covers_oracle_of_mul_daya(self):
        oracle = {
            "name": "Oracle of Mul Daya",
            "type_line": "Creature — Elf Shaman",
            "oracle_text": "Play with the top card of your library revealed.\nYou may play lands from the top of your library.",
        }
        assert "play_from_top" in _keys(oracle)
        assert serves(oracle, _sig("play_from_top", "you"))


class TestChangelingTribalEnabler:
    """Changelings (CR 702.73a) are every creature type, but they type-line as
    "Shapeshifter", so {card_type: <subtype>} tribal searches miss all 62 of them for
    every tribe. Inject them into the tribal serve."""

    MAULER = {
        "name": "Taurean Mauler",
        "type_line": "Creature — Shapeshifter",
        "oracle_text": "Changeling (This card is every creature type.)",
        "keywords": ["Changeling"],
    }

    def test_changeling_served_by_any_tribe(self):
        assert serves(self.MAULER, _sig("type_matters", "you", "Goblin"))
        assert serves(self.MAULER, _sig("type_matters", "you", "Elf"))

    def test_type_granter_served(self):
        nexus = {
            "name": "Maskwood Nexus",
            "type_line": "Artifact",
            "oracle_text": "Creatures you control are every creature type.",
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
        "type_line": "Legendary Creature — Bird",
        "oracle_text": "Whenever you cast a spell from anywhere other than your hand, draw a card.",
    }

    def test_paradox_commander_emits_cast_from_exile(self):
        assert "cast_from_exile" in _keys(self.VEGA)

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
        "oracle_text": "At the beginning of your upkeep, put a time counter on As Foretold.\nOnce each turn, you may pay {0} rather than pay the mana cost for a spell you cast with mana value less than or equal to the number of time counters on As Foretold.",
    }
    VANISHING = {
        "name": "Aeon Chronicler",
        "type_line": "Creature — Avatar",
        "oracle_text": "Vanishing\nSuspend X",
        "keywords": ["Vanishing", "Suspend"],
    }

    def test_time_counter_card_emits_suspend_matters(self):
        assert "suspend_matters" in _keys(self.AS_FORETOLD)

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
            "type_line": "Creature — Vampire",
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
        anhelo = {
            "name": "Anhelo, the Painter",
            "type_line": "Legendary Creature — Vampire",
            "oracle_text": "Deathtouch\nThe first instant or sorcery spell you cast each turn has casualty 2.",
        }
        assert "sacrifice_matters" in _keys(anhelo)


class TestStationDetection:
    """Station (CR 702.184) uses charge counters; station commanders fire neither
    counters_matter (+1/+1-gated) nor proliferate_matters — route them to proliferate."""

    def test_station_keyword_emits_proliferate(self):
        ship = {
            "name": "Hearthhull, the Worldseed",
            "type_line": "Legendary Artifact — Spacecraft",
            "oracle_text": "Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft.)",
            "keywords": ["Station"],
        }
        assert "proliferate_matters" in _keys(ship)


class TestSaddleMatters:
    """Saddle / Mount (CR 702.171) — vehicles_matter catches only 1/33 and serves the
    crew/Vehicle pool, not the attacks-while-saddled payoff axis."""

    CALAMITY = {
        "name": "Calamity, Galloping Inferno",
        "type_line": "Legendary Creature — Phyrexian Horror Mount",
        "oracle_text": "Haste\nWhenever Calamity attacks while saddled, create a tapped and attacking token copy of a creature that saddled it.",
        "keywords": ["Saddle", "Haste"],
    }

    def test_saddle_commander_emits_and_served(self):
        assert "saddle_matters" in _keys(self.CALAMITY)
        assert serves(self.CALAMITY, _sig("saddle_matters", "you"))

    def test_saddle_mount_body_served(self):
        mount = {
            "name": "Stitched Assistant",
            "type_line": "Artifact Creature — Mount",
            "oracle_text": "Saddle 1",
            "keywords": ["Saddle"],
        }
        assert serves(mount, _sig("saddle_matters", "you"))


class TestSuspectMatters:
    """Suspect (CR 701.60) — crimes_matter's search catches 2/24 suspect cards; the
    suspect enabler pool was otherwise invisible (niche Mardu/Dimir aggro)."""

    NELLY = {
        "name": "Nelly Borca, Impulsive Accuser",
        "type_line": "Legendary Creature — Human Detective",
        "oracle_text": "Vigilance\nWhenever Nelly Borca attacks, suspect target creature. Then goad all suspected creatures. (A suspected creature has menace and can't block.)",
    }

    def test_suspect_commander_emits_and_served(self):
        assert "suspect_matters" in _keys(self.NELLY)
        assert serves(self.NELLY, _sig("suspect_matters", "you"))
