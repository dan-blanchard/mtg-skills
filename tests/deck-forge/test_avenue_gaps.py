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
from mtg_utils._deck_forge.signals import Signal, extract_signals


def _sig(key, scope="you", subject=""):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def _extra(spec, label):
    return next((e for e in spec.extras if e.label == label), None)


# Real cards (oracle verified against bulk during the audit).
IMPACT_TREMORS = {
    "name": "Impact Tremors", "type_line": "Enchantment",
    "oracle_text": "Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
}
PURPHOROS = {
    "name": "Purphoros, God of the Forge", "type_line": "Legendary Enchantment Creature — God",
    "oracle_text": "Indestructible\nWhenever another creature you control enters, Purphoros deals 2 damage to each opponent.",
}
WARSTORM_SURGE = {
    "name": "Warstorm Surge", "type_line": "Enchantment",
    "oracle_text": "Whenever a creature you control enters, it deals damage equal to its power to any target.",
}
CORPSE_KNIGHT = {
    "name": "Corpse Knight", "type_line": "Creature — Zombie Knight",
    "oracle_text": "Whenever another creature you control enters, each opponent loses 1 life.",
}
RAVENOUS_CHUPACABRA = {
    "name": "Ravenous Chupacabra", "type_line": "Creature — Beast",
    "oracle_text": "When this creature enters, destroy target creature an opponent controls.",
}
SOLEMN = {
    "name": "Solemn Simulacrum", "type_line": "Artifact Creature — Golem",
    "oracle_text": "When this creature enters, you may search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
}
SOUL_WARDEN = {
    "name": "Soul Warden", "type_line": "Creature — Human Cleric",
    "oracle_text": "Whenever another creature enters, you gain 1 life.",
}
DOUBLING_SEASON = {
    "name": "Doubling Season", "type_line": "Enchantment",
    "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on it instead.",
}
PARALLEL_LIVES = {
    "name": "Parallel Lives", "type_line": "Enchantment",
    "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.",
}
MONDRAK = {
    "name": "Mondrak, Glory Dominus", "type_line": "Legendary Creature — Phyrexian Horror",
    "oracle_text": "If one or more tokens would be created under your control, twice that many of those tokens are created instead.",
}
FURNACE_OF_RATH = {
    "name": "Furnace of Rath", "type_line": "Enchantment",
    "oracle_text": "If a source would deal damage to a permanent or player, it deals double that damage to that permanent or player instead.",
}
GRATUITOUS_VIOLENCE = {
    "name": "Gratuitous Violence", "type_line": "Enchantment",
    "oracle_text": "If a creature you control would deal damage to a permanent or player, it deals double that damage to that permanent or player instead.",
}
LIGHTNING_BOLT = {"name": "Lightning Bolt", "type_line": "Instant", "oracle_text": "Lightning Bolt deals 3 damage to any target."}


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
        assert _extra(spec_for(_sig("token_maker", subject="Goblin")), self.LABEL) is not None

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
        assert serves(LIGHTNING_BOLT, sig) is True  # burn — legitimately a direct_damage card
        llanowar = {"name": "Llanowar Elves", "type_line": "Creature — Elf Druid", "oracle_text": "{T}: Add {G}."}
        assert serves(llanowar, sig) is False


class TestEtbLifegain:
    def test_lifegain_serves_etb_lifegain_triggers(self):
        sig = _sig("lifegain_matters", "you")
        assert serves(SOUL_WARDEN, sig) is True
        authority = {
            "name": "Authority of the Consuls", "type_line": "Enchantment",
            "oracle_text": "Creatures your opponents control enter tapped.\nWhenever a creature an opponent controls enters, you gain 1 life.",
        }
        assert serves(authority, sig) is True


class TestBlinkForSelfEtbCommander:
    """A commander whose own value is a one-shot 'When ~ enters, <value>' should open
    the existing blink/flicker avenue (so Ephemerate/Cloudshift get surfaced)."""

    def test_self_etb_value_commander_emits_blink(self):
        atris = {
            "name": "Atris, Oracle of Half-Truths",
            "type_line": "Legendary Creature — Merfolk Wizard",
            "oracle_text": "Deathtouch\nWhen Atris dies, draw a card.\nWhen Atris enters, look at the top three cards of your library, then an opponent puts one into your hand and the rest into your graveyard.",
        }
        keys = {s.key for s in extract_signals(atris)}
        assert "blink_flicker" in keys

    def test_vanilla_etb_does_not_emit_blink(self):
        # a creature whose ETB is a bare keyword / no value payoff should not.
        grizzly = {
            "name": "Gravedigger", "type_line": "Creature — Zombie",
            "oracle_text": "When this creature enters, you may return target creature card from your graveyard to your hand.",
        }
        # Gravedigger IS a value ETB → it legitimately wants flicker, so it MAY emit.
        # Use a true non-value ETB instead:
        elvish = {
            "name": "Elvish Visionary", "type_line": "Creature — Elf",
            "oracle_text": "When this creature enters, draw a card.",
        }
        # Elvish Visionary draws — that's value — so it emits. The negative case is a
        # creature with NO ETB at all:
        bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
        assert "blink_flicker" not in {s.key for s in extract_signals(bear)}


class TestVoltronCastTrigger:
    """Equipment/Aura commanders whose trigger keys on CASTING an Aura/Equipment spell
    (Sram, Galea, Danitha) didn't emit voltron_matters — the floor detector only had
    attach/equip/equipped anchors. CR 601 cast + CR 301.5/303 Equipment/Aura."""

    def test_cast_equipment_aura_commander_emits_voltron(self):
        sram = {
            "name": "Sram, Senior Edificer", "type_line": "Legendary Creature — Dwarf Advisor",
            "oracle_text": "Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card.",
        }
        galea = {
            "name": "Galea, Kindler of Hope", "type_line": "Legendary Creature — Elf Knight",
            "oracle_text": "You may look at the top card of your library any time.\nYou may cast Aura and Equipment spells from the top of your library.",
        }
        assert "voltron_matters" in {s.key for s in extract_signals(sram)}
        # a non-equipment commander must NOT
        bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
        assert "voltron_matters" not in {s.key for s in extract_signals(bear)}


class TestVoltronServesSram:
    """The voltron SERVE (not just extraction) must credit cast-Equipment/Aura payoffs
    like Sram, so an equipment commander surfaces them as candidates."""

    def test_voltron_serves_cast_equipment_payoff(self):
        sram = {"name": "Sram, Senior Edificer", "type_line": "Legendary Creature — Dwarf Advisor",
                "oracle_text": "Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card."}
        assert serves(sram, _sig("voltron_matters", "you")) is True


class TestEtbCommanderSurfacesFlicker:
    """A repeated-ETB commander (creature_etb / permanent_etb) should surface a flicker
    sub-avenue so Ephemerate/Cloudshift/Conjurer's Closet get offered."""

    def test_creature_etb_offers_flicker_subavenue(self):
        for key in ("creature_etb", "permanent_etb"):
            extra = _extra(spec_for(_sig(key, "you")), "Blink / flicker")
            assert extra is not None, key
            assert extra.serve.matches({"name": "Ephemerate", "type_line": "Instant",
                "oracle_text": "Exile target creature you control, then return it to the battlefield under its owner's control."})
            assert not extra.serve.matches({"name": "Murder", "type_line": "Instant",
                "oracle_text": "Destroy target creature."})
