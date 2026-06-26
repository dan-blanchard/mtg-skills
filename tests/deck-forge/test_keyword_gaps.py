"""Keyword-coverage gaps surfaced by the exhaustive CR 702/701 audit.

Each avenue here closes a confirmed gap where a real deckbuilding archetype keyed on a
keyword ability/action was not surfaced. Every matcher was bulk-validated during the
audit (the "existing avenue catches 0/N" disjointness proofs are pinned as tests).

Tests run the REAL projected Card IR for each named commander/payoff via
``mtg_utils.testkit`` (``test_signals`` = production ``extract_signals_hybrid`` over the
real Scryfall record + real sidecar IR; ``test_card`` = the real minimal record). A
handful of pins use a thin synthetic builder where the assertion is a placeholder /
logic probe (a made-up "<Type> Lord", a forced negative, a future-shape pin) with no
real card to look up.
"""

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face
from mtg_utils.testkit import test_card, test_signals

# Card names referenced through the real-card helpers above. This table feeds the
# `build-card-snapshot` usage scanner (it parses `_REAL_CASES` dict VALUES, which
# also handles apostrophes — unlike the bare `test_card("…")` literal scan). Keep it
# in sync with the names used below; a missing entry fails loud (KeyError) at test
# time, never silently.
_REAL_CASES: dict[str, str] = {
    "Adeline, Resplendent Cathar": "Adeline, Resplendent Cathar",
    "Aeon Chronicler": "Aeon Chronicler",
    "Alrund, God of the Cosmos": "Alrund, God of the Cosmos",
    "Ambush Viper": "Ambush Viper",
    "Anhelo, the Painter": "Anhelo, the Painter",
    "Anje Falkenrath": "Anje Falkenrath",
    "As Foretold": "As Foretold",
    "Asylum Visitor": "Asylum Visitor",
    "Bulwark Ox": "Bulwark Ox",
    "Calamity, Galloping Inferno": "Calamity, Galloping Inferno",
    "Ceremonious Rejection": "Ceremonious Rejection",
    "Doomskar": "Doomskar",
    "Drake Haven": "Drake Haven",
    "Environmental Sciences": "Environmental Sciences",
    "Fall of the Thran": "Fall of the Thran",
    "Fervor": "Fervor",
    "Forsaken Monument": "Forsaken Monument",
    "Geological Appraiser": "Geological Appraiser",
    "Hapatra, Vizier of Poisons": "Hapatra, Vizier of Poisons",
    "Hearthhull, the Worldseed": "Hearthhull, the Worldseed",
    "Hellrider": "Hellrider",
    "Howlsquad Heavy": "Howlsquad Heavy",
    "Kitchen Finks": "Kitchen Finks",
    "Maskwood Nexus": "Maskwood Nexus",
    "Mikaeus, the Unhallowed": "Mikaeus, the Unhallowed",
    "Nelly Borca, Impulsive Accuser": "Nelly Borca, Impulsive Accuser",
    "Oracle of Mul Daya": "Oracle of Mul Daya",
    "Quicken": "Quicken",
    "Rafiq of the Many": "Rafiq of the Many",
    "Samut, the Driving Force": "Samut, the Driving Force",
    "Satoru Umezawa": "Satoru Umezawa",
    "Shared Animosity": "Shared Animosity",
    "Stromkirk Bloodthief": "Stromkirk Bloodthief",
    "Sun Quan, Lord of Wu": "Sun Quan, Lord of Wu",
    "Taurean Mauler": "Taurean Mauler",
    "Throatseeker": "Throatseeker",
    "Twinblade Slasher": "Twinblade Slasher",
    "Uncle Iroh": "Uncle Iroh",
    "Vega, the Watcher": "Vega, the Watcher",
    "Verazol, the Split Current": "Verazol, the Split Current",
    "Verduran Enchantress": "Verduran Enchantress",
    "Yeva, Nature's Herald": "Yeva, Nature's Herald",
    "Yuriko, the Tiger's Shadow": "Yuriko, the Tiger's Shadow",
}


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
    """A synthetic Card IR carrying the given abilities/keywords — used only by the
    placeholder/logic-probe pins below (no real card to look up)."""
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", keywords=keywords, abilities=tuple(abilities)),),
    )


def _subjects(card, key):
    return {s.subject for s in extract_signals(card) if s.key == key}


# Real-card signal keysets (production hybrid path) / regex-only path, by card name.
def _hyb(name):
    return {s.key for s in test_signals(name)}


def _reg(name):
    return {s.key for s in extract_signals(test_card(name))}


# ── Batch A: high-severity wiring fixes ──────────────────────────────────────
class TestNinjaTribal:
    """Ninjutsu commanders (Yuriko/Satoru/Higure) emit ninjutsu_matters but never
    type_matters:Ninja, so the 26-card Ninja tribal payoff axis (lords/equipment/ETB)
    is invisible. Wire ninjutsu -> type_matters:Ninja (CR 702.49)."""

    def test_ninjutsu_commander_emits_ninja_subject(self):
        # Real IR: a ninjutsu commander projects type_matters:Ninja (ADR-0027 hybrid).
        def _ninja_subjects(name):
            return {s.subject for s in test_signals(name) if s.key == "type_matters"}

        assert "Ninja" in _ninja_subjects("Yuriko, the Tiger's Shadow")
        assert "Ninja" in _ninja_subjects("Satoru Umezawa")

    def test_ninja_subject_resolves_to_tribal_avenue(self):
        spec = spec_for(_sig("type_matters", "you", "Ninja"))
        assert spec is not None
        assert spec.search == {"card_type": "Ninja"}
        # serves a Ninja-payoff card the old \bninjutsu\b regex missed
        assert serves(test_card("Throatseeker"), _sig("type_matters", "you", "Ninja"))

    def test_non_ninja_commander_no_ninja_subject(self):
        # Placeholder lord — no real card; a logic probe that a non-Ninja tribal lord
        # does not leak a Ninja subject.
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
        for name in ("Hellrider", "Shared Animosity", "Adeline, Resplendent Cathar"):
            assert serves(test_card(name), self.SIG), name

    def test_haste_and_tokens_still_served(self):
        assert serves(test_card("Fervor"), self.SIG)

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
        # Anje Falkenrath's "if it has madness" payoff fires madness_matters on the real
        # IR (the structural madness payoff marker), not the deleted regex path.
        assert "madness_matters" in _hyb("Anje Falkenrath")
        assert "madness_matters" not in _reg("Anje Falkenrath")

    def test_madness_keyword_card_emits_and_serves(self):
        # The Scryfall madness keyword (Asylum Visitor) opens the lane via the IR.
        assert "madness_matters" in _hyb("Asylum Visitor")
        assert serves(test_card("Asylum Visitor"), _sig("madness_matters", "you"))

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
        # Samut, the Driving Force — speed_matters via the real IR (ADR-0027 hybrid).
        assert "speed_matters" in _hyb("Samut, the Driving Force")

    def test_speed_keyword_card_served(self):
        assert serves(test_card("Howlsquad Heavy"), _sig("speed_matters", "you"))


class TestDiscoverMatters:
    """Discover (CR 701.57) — model like cascade: surface discover sources + low-MV
    value spells. cascade_matters serves 0/28; Lara Croft (discovery counter) excluded."""

    def test_discover_card_emits_and_served(self):
        # Geological Appraiser carries the Scryfall discover keyword → IR opens the lane.
        assert "discover_matters" in _hyb("Geological Appraiser")
        assert "discover_matters" not in _reg("Geological Appraiser")
        assert serves(
            test_card("Geological Appraiser"), _sig("discover_matters", "you")
        )


class TestForetellMatters:
    """Foretell (CR 702.143) — the payoff/engine axis (Alrund, Ranar, Dream Devourer)
    is unsurfaced; the foretell preset finds keyword-bearers only."""

    def test_foretell_keyword_card_emits_and_served(self):
        # Doomskar carries the Scryfall foretell keyword → IR opens the lane.
        assert "foretell_matters" in _hyb("Doomskar")
        assert serves(test_card("Doomskar"), _sig("foretell_matters", "you"))

    def test_foretell_payoff_carer_emits(self):
        # Alrund, God of the Cosmos counts "each foretold card you own in exile" — the
        # Foretold predicate on the counted subject opens the lane via the real IR, not
        # the deleted regex floor.
        assert "foretell_matters" in _hyb("Alrund, God of the Cosmos")
        assert "foretell_matters" not in _reg("Alrund, God of the Cosmos")


class TestUndyingPersistMatters:
    """Undying (702.93) / Persist (702.79) — death-triggered self-return; the recursion
    lives in the keyword, so death_matters/self-recur miss them. Grants surface too."""

    def test_persist_card_emits_and_served(self):
        # Kitchen Finks — the intrinsic Persist bearer fires from the Scryfall keyword
        # array via the real IR, not the deleted regex.
        assert "undying_persist_matters" in _hyb("Kitchen Finks")
        assert "undying_persist_matters" not in _reg("Kitchen Finks")
        assert serves(
            test_card("Kitchen Finks"), _sig("undying_persist_matters", "you")
        )

    def test_grant_card_emits(self):
        # Mikaeus, the Unhallowed is the keyword-less GRANTER ("other non-Human creatures
        # … have undying") — recovered as a conferred-grant marker on the real IR.
        assert "undying_persist_matters" in _hyb("Mikaeus, the Unhallowed")
        assert "undying_persist_matters" not in _reg("Mikaeus, the Unhallowed")


# ── Batch C: counter / payoff-regex avenues ──────────────────────────────────
class TestMinusCountersMatter:
    """plus_one_matters is hard-pinned to +1/+1, so the symmetric -1/-1 axis
    (Wither/Infect/aristocrats — Hapatra, Necroskitter) had no home (CR 122/702.80/702.90)."""

    def test_minus_counter_commander_emits(self):
        # Hapatra, Vizier of Poisons — place_counter(-1/-1) on the real IR.
        assert "minus_counters_matter" in _hyb("Hapatra, Vizier of Poisons")

    def test_plus_one_commander_does_not_emit_minus(self):
        # Placeholder lord — the +1/+1-pin is load-bearing: a +1/+1 commander must NOT
        # fire minus_counters.
        ghave = {
            "name": "Plus Counter Lord",
            "type_line": "Legendary Creature — Fungus",
            "oracle_text": "At the beginning of your upkeep, put a +1/+1 counter on each creature you control.",
        }
        assert "minus_counters_matter" not in _keys_hybrid(ghave)

    def test_minus_payoff_served_wither_keyword_served(self):
        sig = _sig("minus_counters_matter", "you")
        assert serves(test_card("Hapatra, Vizier of Poisons"), sig)
        # Twinblade Slasher's Wither keyword is the canonical -1/-1 source.
        assert serves(test_card("Twinblade Slasher"), sig)


class TestCyclingMatters:
    """Cycling (CR 702.29) payoffs use "cycle or discard" wording; discard_matters'
    serve catches 0/32 (it needs a literal "you discard")."""

    def test_cycling_payoff_commander_emits(self):
        # Drake Haven's "Whenever you cycle or discard a card" payoff fires cycling_matters
        # on the real IR (the cycling_payoff marker), not the deleted regex path.
        assert "cycling_matters" in _hyb("Drake Haven")
        assert "cycling_matters" not in _reg("Drake Haven")

    def test_cycling_payoff_served_not_by_discard_matters(self):
        assert serves(test_card("Drake Haven"), _sig("cycling_matters", "you"))
        # disjoint from discard_matters (its serve needs "you discard", not "cycle or discard")
        assert not serves(test_card("Drake Haven"), _sig("discard_matters", "you"))


class TestKickedSpellMatters:
    """Kicker (CR 702.33) payoffs trigger on casting a kicked spell; spellcast_matters
    serves 0/10 of them."""

    def test_kicked_payoff_commander_emits(self):
        # Verazol, the Split Current's "whenever you cast a kicked spell" payoff fires
        # kicked_spell_matters on the real IR, not the deleted regex path.
        assert "kicked_spell_matters" in _hyb("Verazol, the Split Current")
        assert "kicked_spell_matters" not in _reg("Verazol, the Split Current")

    def test_kicked_payoff_served_not_spellcast(self):
        sig = _sig("kicked_spell_matters", "you")
        assert serves(test_card("Verazol, the Split Current"), sig)
        assert not serves(
            test_card("Verazol, the Split Current"), _sig("spellcast_matters", "you")
        )


class TestColorlessMatters:
    """Devoid/Eldrazi colorless payoffs (anthems/cost-reduction/cast-triggers) keyed on
    "colorless creature/spell/permanent" (CR 702.114) had no avenue; type_matters:Eldrazi
    surfaces by subtype, not the colorless axis."""

    def test_colorless_payoff_commander_emits_and_served(self):
        # Forsaken Monument — the ColorCount:EQ:0 subject predicate opens colorless_matters
        # on the real IR, not the deleted regex path.
        assert "colorless_matters" not in _reg("Forsaken Monument")
        assert "colorless_matters" in _hyb("Forsaken Monument")
        assert serves(test_card("Forsaken Monument"), _sig("colorless_matters", "you"))

    def test_colorless_hate_counterspell_excluded(self):
        # Ceremonious Rejection is colorless-HATE, not a payoff — must not be served.
        assert not serves(
            test_card("Ceremonious Rejection"), _sig("colorless_matters", "you")
        )


class TestExaltedLoneAttacker:
    """Exalted (CR 702.83) rewards attacking ALONE; the attacks-alone payoff/trigger axis
    (Rafiq, Sublime Archangel, Angelic Exaltation) was only loosely under voltron."""

    def test_attacks_alone_commander_emits_and_served(self):
        # Rafiq of the Many — exalted keyword + "attacks alone" payoff on the real IR.
        assert "exalted_lone_attacker" in _hyb("Rafiq of the Many")
        assert serves(
            test_card("Rafiq of the Many"), _sig("exalted_lone_attacker", "you")
        )


# ── Batch D: spell/cast avenues + augments ───────────────────────────────────
class TestFlashMatters:
    """Flash (CR 702.8) build-arounds: flash-GRANTING enablers (Yeva, Leyline) plus
    opponent-turn payoffs. spellslinger excludes creatures, so it never surfaces a flash
    wantlist (flash creatures + granters)."""

    def test_flash_enabler_commander_emits_and_served(self):
        # Yeva, Nature's Herald grants flash to a class ("green creature spells … as
        # though they had flash") — fires flash_matters on the real IR, not the regex.
        assert "flash_matters" in _hyb("Yeva, Nature's Herald")
        assert "flash_matters" not in _reg("Yeva, Nature's Herald")
        assert serves(test_card("Yeva, Nature's Herald"), _sig("flash_matters", "you"))

    def test_flash_creature_served_but_not_spellslinger(self):
        assert serves(test_card("Ambush Viper"), _sig("flash_matters", "you"))
        assert not serves(test_card("Ambush Viper"), _sig("spellcast_matters", "you"))

    def test_self_only_flash_grant_not_an_enabler_signal(self):
        # Quicken's one-shot "as though IT had flash" (singular pronoun) is NOT a flash
        # ENABLER — the real IR opens flash_grant but not the flash_matters enabler lane.
        assert "flash_matters" not in _hyb("Quicken")


class TestTeamEvasionGrant:
    """Team evasion-keyword grants (Sun Quan horsemanship, Iroas menace) — evasion_self
    covers single-attacker/landwalk/team-unblockable but misses the keyword grants."""

    def test_team_evasion_grant_emits_and_served(self):
        # Sun Quan, Lord of Wu grants horsemanship to the team — fires team_evasion_grant
        # on the real IR.
        assert "team_evasion_grant" in _hyb("Sun Quan, Lord of Wu")
        assert serves(
            test_card("Sun Quan, Lord of Wu"), _sig("team_evasion_grant", "you")
        )

    def test_disjoint_from_evasion_self(self):
        assert not serves(
            test_card("Sun Quan, Lord of Wu"), _sig("evasion_self", "you")
        )


class TestEnchantmentsCastAugment:
    """enchantments_matter's {card_type:Enchantment} type-serve + old payoff regex miss
    14 plain Creatures that trigger on casting an enchantment (Verduran Enchantress)."""

    def test_enchantment_cast_creature_now_served(self):
        assert serves(
            test_card("Verduran Enchantress"), _sig("enchantments_matter", "you")
        )


# ── Batch E: subtype avenues, tribal wiring, low-severity, conflict resolutions ─
class TestSagaMatters:
    """Saga-matters (CR 714/702.155) commanders (Tom Bombadil, Narci) care about chapter
    retriggers / lore counters; enchantments_matter serves Sagas as enchantments but
    catches only 1/14 chapter-retrigger payoffs."""

    # Placeholder lord — a generic "lore counters on a Saga" payoff with no clean
    # single real card; pins the dropped-static `saga` marker → lane wiring.
    LORD = {
        "name": "Test Saga Lord",
        "type_line": "Legendary Creature — Avatar",
        "oracle_text": "Sagas you control have read ahead.\nWhenever you put one or more lore counters on a Saga, draw a card.",
    }

    def test_saga_commander_emits(self):
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
        # a real Saga enabler is served via its subtype
        assert serves(test_card("Fall of the Thran"), _sig("saga_matters", "you"))


class TestLessonsMatter:
    """Lessons (CR 701.48) — typed_spellcast drops "Lesson" (subject validated against
    creature-subtype vocab), so a Lessons commander had no avenue; needs type:Lesson."""

    def test_lesson_commander_emits(self):
        # Uncle Iroh — "Lesson spells you cast cost {1} less" opens lessons_matter on the
        # real IR (the kept word-detector mirror), not the deleted regex path.
        assert "lessons_matter" in _hyb("Uncle Iroh")
        assert "lessons_matter" not in _reg("Uncle Iroh")

    def test_lesson_search_is_subtype_and_serves(self):
        spec = spec_for(_sig("lessons_matter", "you"))
        assert spec.search == {"card_type": "Lesson"}
        assert serves(
            test_card("Environmental Sciences"), _sig("lessons_matter", "you")
        )


class TestPlayFromTopAlreadyCovered:
    """The audit proposed play_from_top_matters, but play_from_top already exists (a
    stale-vocab false gap). Pin that it covers the cited card so we don't re-add it."""

    def test_existing_play_from_top_covers_oracle_of_mul_daya(self):
        # Oracle of Mul Daya — the structural STATIC cast_from_zone+from:library arm on
        # the real IR opens play_from_top. The serve pool stays oracle-defined.
        assert "play_from_top" in _hyb("Oracle of Mul Daya")
        assert serves(test_card("Oracle of Mul Daya"), _sig("play_from_top", "you"))


class TestChangelingTribalEnabler:
    """Changelings (CR 702.73a) are every creature type, but they type-line as
    "Shapeshifter", so {card_type: <subtype>} tribal searches miss all 62 of them for
    every tribe. Inject them into the tribal serve."""

    def test_changeling_served_by_any_tribe(self):
        # Taurean Mauler carries the Changeling keyword.
        assert serves(
            test_card("Taurean Mauler"), _sig("type_matters", "you", "Goblin")
        )
        assert serves(test_card("Taurean Mauler"), _sig("type_matters", "you", "Elf"))

    def test_type_granter_served(self):
        # Maskwood Nexus makes your creatures every type.
        assert serves(
            test_card("Maskwood Nexus"), _sig("type_matters", "you", "Zombie")
        )

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

    def test_paradox_commander_emits_cast_from_exile(self):
        # Vega, the Watcher's "cast a spell from anywhere other than your hand" payoff
        # fires cast_from_exile on the real IR (the kept word mirror), not the regex.
        assert "cast_from_exile" in _hyb("Vega, the Watcher")
        assert "cast_from_exile" not in _reg("Vega, the Watcher")

    def test_paradox_subavenue_serves_vega(self):
        spec = spec_for(_sig("cast_from_exile", "you"))
        extra = next((e for e in spec.extras if "Paradox" in e.label), None)
        assert extra is not None
        assert extra.serve.matches(test_card("Vega, the Watcher"))


class TestTimeCountersWiden:
    """suspend_matters existed but served only `\\bsuspend\\b`. Widen the same avenue to
    the time-counter superstructure (CR 701.56 time travel / 702.63 vanishing / impending
    / As Foretold) rather than adding a duplicate key."""

    def test_time_counter_card_emits_suspend_matters(self):
        # As Foretold puts time counters on itself — the time-counter superstructure opens
        # suspend_matters on the real IR (the kept word mirror), not the deleted regex.
        assert "suspend_matters" in _hyb("As Foretold")
        assert "suspend_matters" not in _reg("As Foretold")

    def test_vanishing_keyword_served(self):
        # Aeon Chronicler carries Vanishing + Suspend.
        assert serves(test_card("Aeon Chronicler"), _sig("suspend_matters", "you"))
        assert serves(test_card("As Foretold"), _sig("suspend_matters", "you"))


# ── Batch F: deferred quick-tweaks (serve/routing widens + 2 thin new avenues) ─
class TestLostLifeThresholdWiden:
    """lifeloss_matters/opponents matched only continuous "loses life" triggers, not the
    past-tense "if an opponent lost life this turn" THRESHOLD (Spectacle/Rakdos payoffs)."""

    def test_opponent_lost_life_threshold_served(self):
        # Stromkirk Bloodthief — "if an opponent lost life this turn" threshold payoff.
        assert serves(
            test_card("Stromkirk Bloodthief"), _sig("lifeloss_matters", "opponents")
        )

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
        # Anhelo, the Painter's "has casualty 2" grant is keyword-less; the projection
        # appends a `sacrifice` grant marker the real IR reads → sacrifice_matters.
        assert "sacrifice_matters" in _hyb("Anhelo, the Painter")
        # and the legacy regex path no longer emits it
        assert "sacrifice_matters" not in _reg("Anhelo, the Painter")


class TestStationDetection:
    """Station (CR 702.184) uses charge counters; station commanders fire neither
    plus_one_matters (+1/+1-gated) nor proliferate_matters — route them to proliferate."""

    def test_station_keyword_emits_proliferate(self):
        # Hearthhull, the Worldseed carries the Scryfall station keyword → the real IR
        # opens proliferate_matters.
        assert "proliferate_matters" in _hyb("Hearthhull, the Worldseed")


class TestSaddleMatters:
    """Saddle / Mount (CR 702.171) — vehicles_matter catches only 1/33 and serves the
    crew/Vehicle pool, not the attacks-while-saddled payoff axis."""

    def test_saddle_commander_emits_and_served(self):
        # Calamity, Galloping Inferno carries Saddle + the attacks-while-saddled payoff.
        assert "saddle_matters" in _hyb("Calamity, Galloping Inferno")
        assert "saddle_matters" not in _reg("Calamity, Galloping Inferno")
        assert serves(
            test_card("Calamity, Galloping Inferno"), _sig("saddle_matters", "you")
        )

    def test_saddle_mount_body_served(self):
        assert serves(test_card("Bulwark Ox"), _sig("saddle_matters", "you"))


class TestSuspectMatters:
    """Suspect (CR 701.60) — crimes_matter's search catches 2/24 suspect cards; the
    suspect enabler pool was otherwise invisible (niche Mardu/Dimir aggro)."""

    def test_suspect_commander_emits_and_served(self):
        # Nelly Borca's "suspect target creature" is phase's `suspect` effect category,
        # read through the real IR. The serve pool stays oracle-defined.
        assert "suspect_matters" in _hyb("Nelly Borca, Impulsive Accuser")
        assert "suspect_matters" not in _reg("Nelly Borca, Impulsive Accuser")
        assert serves(
            test_card("Nelly Borca, Impulsive Accuser"), _sig("suspect_matters", "you")
        )
