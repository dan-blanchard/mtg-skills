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

from mtg_utils._analysis.signal_specs import serves, spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_signals


def _sig(key, scope="you", subject=""):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def _extra(spec, label):
    return next((e for e in spec.extras if e.label == label), None)


# Real cards, read by name from the committed snapshot (ADR-0056).
IMPACT_TREMORS = test_card("Impact Tremors")
PURPHOROS = test_card("Purphoros, God of the Forge")
WARSTORM_SURGE = test_card("Warstorm Surge")
CORPSE_KNIGHT = test_card("Corpse Knight")
RAVENOUS_CHUPACABRA = test_card("Ravenous Chupacabra")
SOLEMN = test_card("Solemn Simulacrum")
SOUL_WARDEN = test_card("Soul Warden")
DOUBLING_SEASON = test_card("Doubling Season")
PARALLEL_LIVES = test_card("Parallel Lives")
MONDRAK = test_card("Mondrak, Glory Dominus")
FURNACE_OF_RATH = test_card("Furnace of Rath")
GRATUITOUS_VIOLENCE = test_card("Gratuitous Violence")
LIGHTNING_BOLT = test_card("Lightning Bolt")


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
        llanowar = test_card("Llanowar Elves")
        assert serves(llanowar, sig) is False


class TestEtbLifegain:
    def test_lifegain_serves_etb_lifegain_triggers(self):
        sig = _sig("lifegain_matters", "you")
        assert serves(SOUL_WARDEN, sig) is True
        authority = test_card("Authority of the Consuls")
        assert serves(authority, sig) is True


class TestBlinkForSelfEtbCommander:
    """A commander whose own value is a one-shot 'When ~ enters, <value>' should open
    the existing blink/flicker avenue (so Ephemerate/Cloudshift get surfaced)."""

    def test_self_etb_value_commander_emits_blink(self):
        # Fblthp, the Lost: a repeated self-ETB-value creature ("When Fblthp
        # enters, draw a card...") opens the blink/flicker avenue via the real IR.
        keys = {s.key for s in test_signals("Fblthp, the Lost")}
        assert "blink_flicker" in keys

    def test_vanilla_etb_does_not_emit_blink(self):
        # Gravedigger / Elvish Visionary have VALUE ETBs → they legitimately want
        # flicker, so they may emit. The true negative is a creature with NO ETB.
        # Grizzly Bears: real card over the committed snapshot.
        assert "blink_flicker" not in {s.key for s in test_signals("Grizzly Bears")}


class TestVoltronCastTrigger:
    """Equipment/Aura commanders whose trigger keys on CASTING an Aura/Equipment spell
    (Sram, Galea, Danitha) didn't emit voltron_matters — the floor detector only had
    attach/equip/equipped anchors. CR 601 cast + CR 301.5/303 Equipment/Aura."""

    def test_cast_equipment_aura_commander_emits_voltron(self):
        # Sram's "cast an Aura, Equipment, or Vehicle spell" is the Equipment/Aura
        # PAYOFF tell — it fires voltron_matters via the real IR.
        assert "voltron_matters" in {
            s.key for s in test_signals("Sram, Senior Edificer")
        }
        # a non-equipment payoff (an Equipment's own singular payload) must NOT open
        # the payoff lane — the broad tell keys on "equipped creatures" (PLURAL), and
        # Bonesplitter (plain "Equipped creature gets +2/+0") is a single-target payload.
        assert "voltron_matters" not in {s.key for s in test_signals("Bonesplitter")}


class TestVoltronServesSram:
    """The voltron SERVE (not just extraction) must credit cast-Equipment/Aura payoffs
    like Sram, so an equipment commander surfaces them as candidates."""

    def test_voltron_serves_cast_equipment_payoff(self):
        sram = test_card("Sram, Senior Edificer")
        assert serves(sram, _sig("voltron_matters", "you")) is True


class TestEtbCommanderSurfacesFlicker:
    """A repeated-ETB commander (creature_etb / permanent_etb) should surface a flicker
    sub-avenue so Ephemerate/Cloudshift/Conjurer's Closet get offered."""

    def test_creature_etb_offers_flicker_subavenue(self):
        for key in ("creature_etb", "permanent_etb"):
            extra = _extra(spec_for(_sig(key, "you")), "Blink / flicker")
            assert extra is not None, key
            assert extra.serve.matches(test_card("Ephemerate"))
            assert not extra.serve.matches(test_card("Murder"))


# ── Deferred fixes now implemented (engine-change batch) ──────────────────────
class TestSelfRecurringFodder:
    """Aristocrats commanders want self-recurring fodder — creatures that return/recast
    THEMSELVES from the graveyard (Bloodghast, Gravecrawler). Name-aware serve so
    Sun-Titan-style reanimation of OTHER cards is excluded (CR 603.6e)."""

    def test_aristocrats_specs_offer_self_recur(self):
        bloodghast = test_card("Bloodghast")
        sun_titan = test_card("Sun Titan")
        for key, scope in (("sacrifice_outlets", "you"), ("death_matters", "any")):
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
        assert extra.serve.matches(test_card("Basilisk Collar"))
        assert not extra.serve.matches(test_card("Swiftfoot Boots"))


class TestProliferateForCounters:
    """A +1/+1 / charge / loyalty counter commander wants proliferate (CR 701.27)."""

    def test_counters_offer_proliferate(self):
        extra = _extra(spec_for(_sig("plus_one_matters", "any")), "Proliferate")
        assert extra is not None
        assert extra.serve.matches(test_card("Flux Channeler"))


class TestDiscardPunishers:
    """A force-opponents-to-discard commander wants discard-PUNISH payoffs (Megrim)."""

    def test_opponent_discard_offers_punishers(self):
        extra = _extra(
            spec_for(_sig("opponent_discard", "opponents")), "Discard punishers"
        )
        assert extra is not None
        assert extra.serve.matches(test_card("Megrim"))
        assert not extra.serve.matches(test_card("Mind Rot"))


class TestPowerMatters:
    """A commander that cares about creature POWER (cost-reduction-by-power, power
    thresholds — Ghalta, Goreclaw, Gargos) is a big-creatures deck; surface high-power
    bodies via the structured power gate (the task's power/toughness dimension)."""

    def test_power_commander_emits_power_matters(self):
        # power_matters is IR-served: the aggregate "total power of creatures you
        # control" (Ghalta) and "creature spells you cast with power N+" (Goreclaw)
        # both fire it via the real IR. Real cards over the (uncommitted) full bulk.
        for n in ("Ghalta, Primal Hunger", "Goreclaw, Terror of Qal Sisma"):
            keys = {s.key for s in test_signals(n)}
            assert "power_matters" in keys, n

    def test_power_matters_serves_big_creatures(self):
        sig = _sig("power_matters", "you")
        big = test_card("Krosan Cloudscraper")
        small = test_card("Llanowar Elves")
        assert serves(big, sig) is True
        assert serves(small, sig) is False


class TestTypedGraveyardRecursion:
    """A commander that recurs a TYPED permanent from the graveyard ('return target
    Vehicle card from your graveyard to the battlefield', Greasefang) is a dedicated
    deck for that type — emit the type's matters signal."""

    def test_greasefang_emits_vehicles_matter(self):
        # Greasefang, Okiba Boss: "return target Vehicle card from your graveyard
        # to the battlefield" is a typed-graveyard-recursion Vehicle arm — fires
        # via the real IR. Real card over the committed snapshot.
        keys = {s.key for s in test_signals("Greasefang, Okiba Boss")}
        assert "vehicles_matter" in keys

    def test_typed_recursion_resolves_creature_subtype(self):
        # Bladewing the Risen: "return target Dragon permanent card from your
        # graveyard to the battlefield" resolves the typed-recursion subject.
        subs = {(s.key, s.subject) for s in test_signals("Bladewing the Risen")}
        assert ("type_matters", "Dragon") in subs

    def test_generic_reanimation_emits_no_bogus_type(self):
        # "return target permanent card …" is plain reanimation, not a typed-
        # recursion deck. Sun Titan: real card over the committed snapshot.
        subs = {s.subject for s in test_signals("Sun Titan") if s.key == "type_matters"}
        assert "Permanent" not in subs
        assert "Creature" not in subs
