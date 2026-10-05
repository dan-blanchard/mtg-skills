"""commander_multipliers: the deck cards that multiply a commander, read off phase's
trees — the tuner's cut protection (ADR-0029). Each expectation follows the card's
oracle text and rulings (CR 603.2d additional triggers, CR 707.10 copied abilities)."""

import pytest

from mtg_utils._analysis.multipliers import ZONE_GRANT_RESIDUE, commander_multipliers
from mtg_utils._card_ir.trees import trees_for
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


def test_commander_never_protects_itself():
    assert commander_multipliers([OMNATH], [OMNATH]) == {}


@pytest.mark.retirement_canary
def test_thranduil_zone_grant_is_still_a_residue_canary():
    """Retirement canary for the zone-grant text arm in
    ``_analysis.multipliers._zone_grant_reason``. Phase v0.94.0 parks Thranduil's
    "has all activated abilities of all Elf cards in your graveyard" as an
    Unimplemented residue; once it parses, read the grant off the tree instead."""
    residues = [r for tree in trees_for(THRANDUIL) for r in tree.residues()]
    assert any(ZONE_GRANT_RESIDUE in r for r in residues), (
        "multipliers._zone_grant_reason: RETIRE-READY — phase now parses "
        "Thranduil's zone grant. Read it off the tree, then delete the text arm "
        "and this canary."
    )
