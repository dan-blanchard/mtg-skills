"""commander_multipliers: the deck cards that multiply a commander, read off phase's
trees — the tuner's cut protection (ADR-0029). Each expectation follows the card's
oracle text and rulings (CR 603.2d additional triggers, CR 707.10 copied abilities)."""

import pytest

from mtg_utils._analysis.multipliers import (
    Commander,
    ZoneGrant,
    commander_multipliers,
    multiplier_reasons,
    zone_grant,
)
from mtg_utils._card_ir.crosswalk.reads import filter_admits, filter_subtypes
from mtg_utils._card_ir.trees import object_facts, trees_for
from mtg_utils.testkit import test_card

OMNATH = test_card("Omnath, Locus of the Void")  # a landfall trigger only
KRENKO = test_card("Krenko, Mob Boss")  # a non-mana activated ability only
ISAMARU = test_card("Isamaru, Hound of Konda")  # no abilities
EDGAR = test_card("Edgar Markov")  # an attack trigger
THRANDUIL = test_card("Thranduil, the Elvenking")
GRIST = test_card("Grist, the Hunger Tide")  # a planeswalker on the battlefield
KOZILEK = test_card("Kozilek, the Great Distortion")  # a cast trigger
URZA = test_card("Urza, Lord High Artificer")  # its own enters trigger


def test_trigger_doublers_reach_a_landfall_commander():
    """Omnath's landfall is a land entering. Ancient Greenwarden (a land entering) and
    Yarok (its ruling: any permanent entering) double it; Panharmonicon (an artifact
    or creature entering) doesn't."""
    cards = [
        test_card("Ancient Greenwarden"),
        test_card("Yarok, the Desecrated"),
        test_card("Panharmonicon"),
    ]
    assert set(commander_multipliers(cards, [OMNATH])) == {
        "Ancient Greenwarden",
        "Yarok, the Desecrated",
    }


def test_any_cause_doublers_check_the_affected_filter():
    """Roaming Throne (another creature of the chosen type) and Echoes of Eternity
    (another colorless permanent) both reach a colorless creature commander."""
    cards = [
        test_card("Roaming Throne"),
        test_card("Echoes of Eternity"),
        test_card("Mind Stone"),
    ]
    assert set(commander_multipliers(cards, [OMNATH])) == {
        "Roaming Throne",
        "Echoes of Eternity",
    }


def test_an_attack_doubler_needs_an_attack_trigger():
    """Isshin's ruling: only triggers directly related to attacking."""
    isshin = test_card("Isshin, Two Heavens as One")
    assert set(commander_multipliers([isshin], [EDGAR])) == {
        "Isshin, Two Heavens as One"
    }
    assert commander_multipliers([isshin], [KRENKO]) == {}


def test_ability_copiers_copy_only_their_kind():
    """Strionic Resonator copies a triggered ability, Rings of Brighthearth a non-mana
    activated one, Lithoform Engine either (and a permanent spell)."""
    strionic = test_card("Strionic Resonator")
    rings = test_card("Rings of Brighthearth")
    lithoform = test_card("Lithoform Engine")
    assert set(commander_multipliers([strionic, rings, lithoform], [KRENKO])) == {
        "Rings of Brighthearth",
        "Lithoform Engine",
    }
    assert set(commander_multipliers([strionic, rings, lithoform], [OMNATH])) == {
        "Strionic Resonator",
        "Lithoform Engine",
    }
    # Lithoform's last ability copies any permanent spell: a vanilla commander too.
    assert commander_multipliers([strionic, rings, lithoform], [ISAMARU]) == {
        "Lithoform Engine": "copies Isamaru, Hound of Konda as it's cast"
    }


def test_copies_check_the_copy_target():
    """Helm of the Host copies the equipped creature (its token "isn't legendary");
    Kiki-Jiki only a nonlegendary creature, never a legendary commander."""
    cards = [test_card("Helm of the Host"), test_card("Kiki-Jiki, Mirror Breaker")]
    assert commander_multipliers(cards, [ISAMARU]) == {
        "Helm of the Host": "copies Isamaru, Hound of Konda"
    }


def test_copies_of_a_creature_never_reach_a_planeswalker_commander():
    """Mirror March and Delina copy a creature, Helm and Illusionist's Bracers what
    they equip; Grist is a planeswalker on the battlefield. Spark Double copies "a
    creature or planeswalker you control"."""
    cards = [
        test_card("Mirror March"),
        test_card("Delina, Wild Mage"),
        test_card("Helm of the Host"),
        test_card("Illusionist's Bracers"),
        test_card("Spark Double"),
    ]
    assert set(commander_multipliers(cards, [GRIST])) == {"Spark Double"}
    assert set(commander_multipliers(cards, [KRENKO])) == {
        "Mirror March",
        "Delina, Wild Mage",
        "Helm of the Host",
        "Illusionist's Bracers",
        "Spark Double",
    }


def test_copies_that_exclude_a_legendary_commander():
    """Cytoshape picks a nonlegendary creature, Brudiclad copies a token, Twincast an
    instant or sorcery spell."""
    cards = [
        test_card("Cytoshape"),
        test_card("Brudiclad, Telchor Engineer"),
        test_card("Twincast"),
    ]
    assert commander_multipliers(cards, [KRENKO]) == {}


def test_a_creature_spell_copy_copies_the_commander_as_its_cast():
    assert commander_multipliers([test_card("Double Major")], [KRENKO]) == {
        "Double Major": "copies Krenko, Mob Boss as it's cast"
    }


def test_a_cast_trigger_is_doubled_only_by_a_spell_doubler():
    """Kozilek's "When you cast this spell" functions on the stack. Echoes of
    Eternity reaches colorless spells; Roaming Throne and Annie Joins Up only
    permanents (CR 109.2)."""
    cards = [
        test_card("Echoes of Eternity"),
        test_card("Roaming Throne"),
        test_card("Annie Joins Up"),
    ]
    assert set(commander_multipliers(cards, [KOZILEK])) == {"Echoes of Eternity"}


def test_panharmonicon_reaches_a_creature_commanders_own_enters_trigger():
    """Its ruling: it applies to a permanent's own enters trigger when that
    permanent is an artifact or creature."""
    assert set(commander_multipliers([test_card("Panharmonicon")], [URZA])) == {
        "Panharmonicon"
    }


def test_zone_granted_toolbox_card():
    out = commander_multipliers([test_card("Priest of Titania")], [THRANDUIL])
    assert out == {
        "Priest of Titania": (
            "Thranduil, the Elvenking uses its activated abilities from the graveyard"
        )
    }


@pytest.mark.parametrize("name", ["Mirror Entity", "Chameleon Colossus"])
def test_a_changeling_is_an_elf_card_in_the_graveyard(name):
    """Changeling is every creature type, in every zone (CR 702.73a, 604.3)."""
    assert set(commander_multipliers([test_card(name)], [THRANDUIL])) == {name}


def test_zone_grant_reads_type_and_zone():
    assert zone_grant(THRANDUIL) == ZoneGrant("Elf", "graveyard")
    assert zone_grant(KRENKO) is None


def test_copies_of_a_noncreature_or_an_opponents_permanent():
    """Astral Dragon copies a noncreature permanent; Venser, Fervent Forger's
    token copies are of a permanent an opponent controls."""
    cards = [test_card("Astral Dragon"), test_card("Venser, Fervent Forger")]
    assert commander_multipliers(cards, [KRENKO]) == {}


def test_reasons_list_every_way_by_kind():
    """Lithoform Engine copies an activated or triggered ability and a permanent
    spell: two kinds, each with its ability as the clause."""
    reasons = multiplier_reasons(test_card("Lithoform Engine"), Commander(KRENKO))
    assert [(r.kind, r.family) for r in reasons] == [
        ("copy_activated_or_triggered", "ability"),
        ("copy_commander_spell", "copy"),
    ]
    assert reasons[1].clause == "{4}, {T}: Copy target permanent spell you control."


def test_a_copy_of_the_creature_that_entered_can_copy_the_commander():
    """Flameshadow Conjuring and Molten Echoes copy "that creature" — the nontoken
    creature whose entering triggered them, the commander included (choose its
    type for Molten Echoes); the legendary token copy still enters, so its enters
    triggers fire before the legend rule (CR 704.5j) removes one."""
    cards = [test_card("Flameshadow Conjuring"), test_card("Molten Echoes")]
    assert set(commander_multipliers(cards, [URZA])) == {
        "Flameshadow Conjuring",
        "Molten Echoes",
    }


def test_copies_the_commander_never_reaches():
    """Nacatl War-Pride copies itself ("copies of it"); Chef's Kiss takes a spell
    that targets, and a creature spell has no targets (CR 115.1a/b); Kaervek, the
    Punisher copies a black card in your graveyard; Ominous Lockbox an opponent's
    spell; Gandalf, Westward Voyager a spell of mana value 5 or more."""
    cards = [
        test_card("Nacatl War-Pride"),
        test_card("Chef's Kiss"),
        test_card("Kaervek, the Punisher"),
        test_card("Ominous Lockbox"),  # copies a spell an opponent casts
        test_card("Gandalf, Westward Voyager"),  # mana value 5 or greater; Krenko 4
    ]
    assert commander_multipliers(cards, [KRENKO]) == {}


def test_copies_of_cards_to_cast_never_copy_the_commander():
    """Zethi copies exiled instant cards and Arcane Savant a card exiled before the
    game, to cast the copies (CR 707.12) — never the commander spell."""
    cards = [test_card("Zethi, Arcane Blademaster"), test_card("Arcane Savant")]
    assert commander_multipliers(cards, [KRENKO]) == {}


def test_a_cast_trigger_copy_needs_the_commanders_cast():
    """Ulalek copies spells when you cast an Eldrazi spell (Kozilek is one);
    Verazol copies a kicked spell, and only a spell with kicker can be kicked
    (CR 702.33a — Josu Vess)."""
    ulalek = test_card("Ulalek, Fused Atrocity")
    verazol = test_card("Verazol, the Split Current")
    assert set(commander_multipliers([ulalek, verazol], [KOZILEK])) == {
        "Ulalek, Fused Atrocity"
    }
    assert set(
        commander_multipliers([ulalek, verazol], [test_card("Josu Vess, Lich Knight")])
    ) == {"Verazol, the Split Current"}
    assert commander_multipliers([ulalek, verazol], [KRENKO]) == {}


def test_becoming_a_copy_of_a_legend_needs_a_legend_rule_bypass():
    """A permanent that becomes a copy of a legendary commander takes its
    supertype (CR 707.2), and the legend rule then keeps only one (CR 704.5j —
    Mirage Mirror's ruling); becoming a copy isn't entering. Entering as a copy
    (Clone, CR 707.5) still enters. A nonlegendary object (Wood Elves) can be
    copied by Mirage Mirror for real."""
    mirror = test_card("Mirage Mirror")
    clone = test_card("Clone")
    assert set(commander_multipliers([mirror, clone], [KRENKO])) == {"Clone"}
    assert set(commander_multipliers([mirror], [test_card("Wood Elves")])) == {
        "Mirage Mirror"
    }


def test_a_delayed_or_loyalty_copy_reaches_its_commander():
    """The Clone Saga's chapter II copies the next creature spell you cast ("except
    it isn't legendary"); Rowan's Talent copies the loyalty abilities of the
    planeswalker it enchants (CR 606.1: loyalty abilities are activated)."""
    saga = test_card("The Clone Saga")
    talent = test_card("Rowan's Talent")
    assert set(commander_multipliers([saga, talent], [KRENKO])) == {"The Clone Saga"}
    assert set(commander_multipliers([talent], [GRIST])) == {"Rowan's Talent"}


def test_a_changeling_is_every_creature_type_but_no_equipment():
    """CR 702.73a: "This object is every creature type" — creature types only
    (CR 205.3m), so Stoneforge Mystic's "Equipment card" doesn't describe Bloodline
    Pretender, an artifact creature changeling."""
    facts = object_facts(test_card("Bloodline Pretender"))
    assert facts.has_subtype("Elf")
    assert facts.has_subtype("Time Lord")
    assert not facts.has_subtype("Equipment")
    assert not facts.has_subtype("Forest")
    equipment = next(
        n
        for tree in trees_for(test_card("Stoneforge Mystic"))
        for n in tree.iter_typed()
        if "Equipment" in filter_subtypes(n)
    )
    assert filter_admits(equipment, facts) is False


def test_commander_never_protects_itself():
    assert commander_multipliers([OMNATH], [OMNATH]) == {}
