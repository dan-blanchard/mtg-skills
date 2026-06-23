"""EDHREC-audit-driven avenue improvements.

Derived from sweeping every commander-/brawl-legal commander's EDHREC top-synergy
cards and finding patterns our avenue rules failed to surface (each verified against
the real bulk + CR, not memory). See the audit findings for the full table.

Patterns implemented here:
  1. Creature/permanent-ETB PAYOFFS (deal damage / drain / gain life when a creature
     enters) for flood/aristocrats commanders — CR 603.6 zone-change triggers.
  2. Token DOUBLERS for token-flood commanders (CR 616 replacement effects).
  3. Damage DOUBLERS for direct-damage commanders (CR 701.10g replacement effects).
  4. ETB lifegain triggers folded into the lifegain serve.
  5. Self-ETB-value commanders surface the existing blink/flicker avenue (extraction).
"""

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Card, Face


def _sig(key, scope="you", subject=""):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def _bare_ir() -> Card:
    """A minimal non-None Card IR — routes extract_signals_hybrid through the IR path
    so a migrated key whose IR source scans the record (a kept word mirror) fires."""
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _extra(spec, label):
    return next((e for e in spec.extras if e.label == label), None)


# Real cards (oracle verified against bulk during the audit).
IMPACT_TREMORS = {
    "name": "Impact Tremors",
    "type_line": "Enchantment",
    "oracle_text": "Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
}
PURPHOROS = {
    "name": "Purphoros, God of the Forge",
    "type_line": "Legendary Enchantment Creature — God",
    "oracle_text": "Indestructible\nAs long as your devotion to red is less than five, Purphoros isn't a creature.\nWhenever another creature you control enters, Purphoros deals 2 damage to each opponent.\n{2}{R}: Creatures you control get +1/+0 until end of turn.",
}
WARSTORM_SURGE = {
    "name": "Warstorm Surge",
    "type_line": "Enchantment",
    "oracle_text": "Whenever a creature you control enters, it deals damage equal to its power to any target.",
}
CORPSE_KNIGHT = {
    "name": "Corpse Knight",
    "type_line": "Creature — Zombie Knight",
    "oracle_text": "Whenever another creature you control enters, each opponent loses 1 life.",
}
RAVENOUS_CHUPACABRA = {
    "name": "Ravenous Chupacabra",
    "type_line": "Creature — Beast Horror",
    "oracle_text": "When this creature enters, destroy target creature an opponent controls.",
}
SOLEMN = {
    "name": "Solemn Simulacrum",
    "type_line": "Artifact Creature — Golem",
    "oracle_text": "When this creature enters, you may search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.\nWhen this creature dies, you may draw a card.",
}
SOUL_WARDEN = {
    "name": "Soul Warden",
    "type_line": "Creature — Human Cleric",
    "oracle_text": "Whenever another creature enters, you gain 1 life.",
}
DOUBLING_SEASON = {
    "name": "Doubling Season",
    "type_line": "Enchantment",
    "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.",
}
PARALLEL_LIVES = {
    "name": "Parallel Lives",
    "type_line": "Enchantment",
    "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.",
}
MONDRAK = {
    "name": "Mondrak, Glory Dominus",
    "type_line": "Legendary Creature — Phyrexian Horror",
    "oracle_text": "If one or more tokens would be created under your control, twice that many of those tokens are created instead.\n{1}{W/P}{W/P}, Sacrifice two other artifacts and/or creatures: Put an indestructible counter on Mondrak. ({W/P} can be paid with either {W} or 2 life.)",
}
FURNACE_OF_RATH = {
    "name": "Furnace of Rath",
    "type_line": "Enchantment",
    "oracle_text": "If a source would deal damage to a permanent or player, it deals double that damage to that permanent or player instead.",
}
GRATUITOUS_VIOLENCE = {
    "name": "Gratuitous Violence",
    "type_line": "Enchantment",
    "oracle_text": "If a creature you control would deal damage to a permanent or player, it deals double that damage instead.",
}
LIGHTNING_BOLT = {
    "name": "Lightning Bolt",
    "type_line": "Instant",
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
}


class TestCreatureEtbPayoffs:
    """Flood/aristocrats commanders (token_maker / tokens_matter / creatures_matter /
    creature_etb) should surface creature-ETB PAYOFFS — Impact Tremors / Purphoros —
    which no avenue surfaced (the flood serves credit token MAKERS, not the payoffs)."""

    LABEL = "Creature-ETB payoffs"

    def _payoff_extra(self, key, subject=""):
        spec = spec_for(_sig(key, "you", subject))
        return _extra(spec, self.LABEL)

    def test_flood_specs_offer_etb_payoff_subavenue(self):
        for key in ("creatures_matter", "creature_etb", "tokens_matter", "token_maker"):
            assert self._payoff_extra(key) is not None, key
        # the token-maker SUBJECT spec (Krenko -> token_maker:Goblin) too
        assert self._payoff_extra("token_maker", subject="Goblin") is not None

    def test_etb_payoff_serve_matches_payoffs_not_value_etbs(self):
        extra = self._payoff_extra("creatures_matter")
        assert extra.serve is not None
        for card in (IMPACT_TREMORS, PURPHOROS, WARSTORM_SURGE, CORPSE_KNIGHT):
            assert extra.serve.matches(card), card["name"]
        for card in (RAVENOUS_CHUPACABRA, SOLEMN, SOUL_WARDEN):
            assert not extra.serve.matches(card), card["name"]


class TestTokenDoublers:
    LABEL = "Token doublers"

    def test_token_specs_offer_doubler_subavenue(self):
        for key in ("tokens_matter", "token_maker"):
            assert _extra(spec_for(_sig(key)), self.LABEL) is not None, key
        assert (
            _extra(spec_for(_sig("token_maker", subject="Goblin")), self.LABEL)
            is not None
        )

    def test_token_doubler_serve(self):
        extra = _extra(spec_for(_sig("tokens_matter")), self.LABEL)
        for card in (DOUBLING_SEASON, PARALLEL_LIVES, MONDRAK):
            assert extra.serve.matches(card), card["name"]
        assert not extra.serve.matches(IMPACT_TREMORS)


class TestDamageDoublers:
    def test_direct_damage_serves_doublers(self):
        # The doublers (Furnace, Gratuitous Violence) carry ONLY the replacement clause,
        # no "deals N damage" — so they did not serve before this fix. (Lightning Bolt
        # correctly serves either way: it IS burn.)
        sig = _sig("direct_damage", "you")
        assert serves(FURNACE_OF_RATH, sig) is True
        assert serves(GRATUITOUS_VIOLENCE, sig) is True
        assert (
            serves(LIGHTNING_BOLT, sig) is True
        )  # burn — legitimately a direct_damage card
        llanowar = {
            "name": "Llanowar Elves",
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
        }
        assert serves(llanowar, sig) is False


class TestEtbLifegain:
    def test_lifegain_serves_etb_lifegain_triggers(self):
        sig = _sig("lifegain_matters", "you")
        assert serves(SOUL_WARDEN, sig) is True
        authority = {
            "name": "Authority of the Consuls",
            "type_line": "Enchantment",
            "oracle_text": "Creatures your opponents control enter tapped.\nWhenever a creature an opponent controls enters, you gain 1 life.",
        }
        assert serves(authority, sig) is True


class TestBlinkForSelfEtbCommander:
    """A commander whose own value is a one-shot 'When ~ enters, <value>' should open
    the existing blink/flicker avenue (so Ephemerate/Cloudshift get surfaced)."""

    def test_self_etb_value_commander_emits_blink(self):
        fblthp = {
            "name": "Fblthp, the Lost",
            "type_line": "Legendary Creature — Homunculus",
            "oracle_text": "When Fblthp enters, draw a card. If it entered from your library or was cast from your library, draw two cards instead.\nWhen Fblthp becomes the target of a spell, shuffle Fblthp into its owner's library.",
        }
        # ADR-0027 v34: blink_flicker migrated to the Card IR — the self-ETB-value
        # avenue opener was re-homed to the IR membership block; use the hybrid path
        # with include_membership.
        keys = {
            s.key
            for s in extract_signals_hybrid(fblthp, _bare_ir(), include_membership=True)
        }
        assert "blink_flicker" in keys

    def test_vanilla_etb_does_not_emit_blink(self):
        # Gravedigger / Elvish Visionary have VALUE ETBs → they legitimately want
        # flicker, so they may emit. The true negative is a creature with NO ETB.
        bear = {
            "name": "Grizzly Bears",
            "type_line": "Creature — Bear",
            "oracle_text": "",
        }
        assert "blink_flicker" not in {s.key for s in extract_signals(bear)}


class TestVoltronCastTrigger:
    """Equipment/Aura commanders whose trigger keys on CASTING an Aura/Equipment spell
    (Sram, Galea, Danitha) didn't emit voltron_matters — the floor detector only had
    attach/equip/equipped anchors. CR 601 cast + CR 301.5/303 Equipment/Aura."""

    def test_cast_equipment_aura_commander_emits_voltron(self):
        sram = {
            "name": "Sram, Senior Edificer",
            "type_line": "Legendary Creature — Dwarf Advisor",
            "oracle_text": "Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card.",
        }
        assert "voltron_matters" in {s.key for s in extract_signals(sram)}
        # a non-equipment commander must NOT
        bear = {
            "name": "Grizzly Bears",
            "type_line": "Creature — Bear",
            "oracle_text": "",
        }
        assert "voltron_matters" not in {s.key for s in extract_signals(bear)}


class TestVoltronServesSram:
    """The voltron SERVE (not just extraction) must credit cast-Equipment/Aura payoffs
    like Sram, so an equipment commander surfaces them as candidates."""

    def test_voltron_serves_cast_equipment_payoff(self):
        sram = {
            "name": "Sram, Senior Edificer",
            "type_line": "Legendary Creature — Dwarf Advisor",
            "oracle_text": "Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card.",
        }
        assert serves(sram, _sig("voltron_matters", "you")) is True


class TestEtbCommanderSurfacesFlicker:
    """A repeated-ETB commander (creature_etb / permanent_etb) should surface a flicker
    sub-avenue so Ephemerate/Cloudshift/Conjurer's Closet get offered."""

    def test_creature_etb_offers_flicker_subavenue(self):
        for key in ("creature_etb", "permanent_etb"):
            extra = _extra(spec_for(_sig(key, "you")), "Blink / flicker")
            assert extra is not None, key
            assert extra.serve.matches(
                {
                    "name": "Ephemerate",
                    "type_line": "Instant",
                    "oracle_text": "Exile target creature you control, then return it to the battlefield under its owner's control.\nRebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)",
                }
            )
            assert not extra.serve.matches(
                {
                    "name": "Murder",
                    "type_line": "Instant",
                    "oracle_text": "Destroy target creature.",
                }
            )


# ── Deferred fixes now implemented (engine-change batch) ──────────────────────
class TestSelfRecurringFodder:
    """Aristocrats commanders want self-recurring fodder — creatures that return/recast
    THEMSELVES from the graveyard (Bloodghast, Gravecrawler). Name-aware serve so
    Sun-Titan-style reanimation of OTHER cards is excluded (CR 603.6e)."""

    def test_aristocrats_specs_offer_self_recur(self):
        bloodghast = {
            "name": "Bloodghast",
            "type_line": "Creature — Vampire Spirit",
            "oracle_text": "This creature can't block.\nThis creature has haste as long as an opponent has 10 or less life.\nLandfall — Whenever a land you control enters, you may return this card from your graveyard to the battlefield.",
        }
        sun_titan = {
            "name": "Sun Titan",
            "type_line": "Creature — Giant",
            "oracle_text": "Vigilance\nWhenever this creature enters or attacks, you may return target permanent card with mana value 3 or less from your graveyard to the battlefield.",
        }
        for key, scope in (("sacrifice_matters", "you"), ("death_matters", "any")):
            extra = _extra(spec_for(_sig(key, scope)), "Self-recurring fodder")
            assert extra is not None, key
            assert extra.serve.matches(bloodghast)
            assert not extra.serve.matches(sun_titan)


class TestDeathtouchGear:
    """A direct-damage / pinger commander wants deathtouch-granting gear (Basilisk
    Collar) — deathtouch + 1 damage kills anything (CR 702.2b)."""

    def test_direct_damage_offers_deathtouch_enablers(self):
        extra = _extra(spec_for(_sig("direct_damage", "you")), "Deathtouch enablers")
        assert extra is not None
        assert extra.serve.matches(
            {
                "name": "Basilisk Collar",
                "type_line": "Artifact — Equipment",
                "oracle_text": "Equipped creature has deathtouch and lifelink. (Any amount of damage it deals to a creature is enough to destroy it. Damage dealt by this creature also causes you to gain that much life.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
            }
        )
        assert not extra.serve.matches(
            {
                "name": "Swiftfoot Boots",
                "type_line": "Artifact — Equipment",
                "oracle_text": "Equipped creature has hexproof and haste. (It can't be the target of spells or abilities your opponents control. It can attack and {T} no matter when it came under your control.)\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
            }
        )


class TestProliferateForCounters:
    """A +1/+1 / charge / loyalty counter commander wants proliferate (CR 701.27)."""

    def test_counters_offer_proliferate(self):
        extra = _extra(spec_for(_sig("plus_one_matters", "any")), "Proliferate")
        assert extra is not None
        assert extra.serve.matches(
            {
                "name": "Flux Channeler",
                "type_line": "Creature — Human Wizard",
                "oracle_text": "Whenever you cast a noncreature spell, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)",
                "keywords": ["Proliferate"],
            }
        )


class TestDiscardPunishers:
    """A force-opponents-to-discard commander wants discard-PUNISH payoffs (Megrim)."""

    def test_opponent_discard_offers_punishers(self):
        extra = _extra(
            spec_for(_sig("opponent_discard", "opponents")), "Discard punishers"
        )
        assert extra is not None
        assert extra.serve.matches(
            {
                "name": "Megrim",
                "type_line": "Enchantment",
                "oracle_text": "Whenever an opponent discards a card, this enchantment deals 2 damage to that player.",
            }
        )
        assert not extra.serve.matches(
            {
                "name": "Mind Rot",
                "type_line": "Sorcery",
                "oracle_text": "Target player discards two cards.",
            }
        )


class TestPowerMatters:
    """A commander that cares about creature POWER (cost-reduction-by-power, power
    thresholds — Ghalta, Goreclaw, Gargos) is a big-creatures deck; surface high-power
    bodies via the structured power gate (the task's power/toughness dimension)."""

    def test_power_commander_emits_power_matters(self):
        for n, ot in [
            (
                "Ghalta, Primal Hunger",
                "This spell costs {X} less to cast, where X is the total power of creatures you control.",
            ),
            (
                "Goreclaw, Terror of Qal Sisma",
                "Creature spells you cast with power 4 or greater cost {2} less to cast.",
            ),
        ]:
            # ADR-0027: power_matters migrated to the Card IR — the aggregate "total
            # power of creatures you control" (Ghalta) and "creature spells you cast with
            # power N+" (Goreclaw) forms phase folds into an empty-predicate board_count,
            # recovered by the byte-identical _POWER_MATTERS_MIRROR. The regex path no
            # longer emits it, so assert via the hybrid (IR) path.
            keys = {
                s.key
                for s in extract_signals_hybrid(
                    {
                        "name": n,
                        "type_line": "Legendary Creature — Dinosaur",
                        "oracle_text": ot,
                    },
                    _bare_ir(),
                )
            }
            assert "power_matters" in keys, n

    def test_power_matters_serves_big_creatures(self):
        sig = _sig("power_matters", "you")
        big = {
            "name": "Krosan Cloudscraper",
            "type_line": "Creature — Beast Mutant",
            "oracle_text": "At the beginning of your upkeep, sacrifice this creature unless you pay {G}{G}.\nMorph {7}{G}{G} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)",
            "power": "13",
            "cmc": 8.0,
        }
        small = {
            "name": "Llanowar Elves",
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
            "power": "1",
            "cmc": 1.0,
        }
        assert serves(big, sig) is True
        assert serves(small, sig) is False


class TestTypedGraveyardRecursion:
    """A commander that recurs a TYPED permanent from the graveyard ('return target
    Vehicle card from your graveyard to the battlefield', Greasefang) is a dedicated
    deck for that type — emit the type's matters signal."""

    def test_greasefang_emits_vehicles_matter(self):
        greasefang = {
            "name": "Greasefang, Okiba Boss",
            "type_line": "Legendary Creature — Rat Pilot",
            "oracle_text": "At the beginning of combat on your turn, return target Vehicle card from your graveyard to the battlefield. It gains haste. Return it to its owner's hand at the beginning of your next end step.",
        }
        # ADR-0027: vehicles_matter migrated to the Card IR; the typed-graveyard-
        # recursion Vehicle arm is re-supplied per-clause in extract_signals_ir, so it
        # fires through the hybrid path (not the pure regex path).
        keys = {s.key for s in extract_signals_hybrid(greasefang, _bare_ir())}
        assert "vehicles_matter" in keys

    def test_typed_recursion_resolves_creature_subtype(self):
        dragon_recur = {
            "name": "Test Dragonlord",
            "type_line": "Legendary Creature — Dragon",
            "oracle_text": "Whenever this creature attacks, return target Dragon card from your graveyard to the battlefield.",
        }
        subs = {(s.key, s.subject) for s in extract_signals(dragon_recur)}
        assert ("type_matters", "Dragon") in subs

    def test_generic_reanimation_emits_no_bogus_type(self):
        # "return target creature card …" is plain reanimation, not a typed-recursion deck.
        sun_titan = {
            "name": "Sun Titan",
            "type_line": "Creature — Giant",
            "oracle_text": "Vigilance\nWhenever this creature enters or attacks, you may return target permanent card with mana value 3 or less from your graveyard to the battlefield.",
        }
        subs = {
            s.subject for s in extract_signals(sun_titan) if s.key == "type_matters"
        }
        assert "Permanent" not in subs
        assert "Creature" not in subs
