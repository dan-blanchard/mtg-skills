"""``_card_ir.misparsed_shapes``: a shape phase misparses, rewritten on the raw record
before strict load."""

from __future__ import annotations

import pytest

from mtg_utils._analysis.roles import is_board_wipe, role_of
from mtg_utils._card_ir.misparsed_shapes import correct_misparsed_shapes
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _effects(rec: dict) -> list[dict]:
    """Each head ability's effect: the face's abilities and its triggers' bodies."""
    bodies = [*(rec.get("abilities") or ()), *(t["execute"] for t in rec["triggers"])]
    return [b["effect"] for b in bodies]


def _keys(name: str) -> set[str]:
    return {s.key for s in test_signals(name)}


@pytest.mark.retirement_canary
def test_self_damage_sweep_canary():
    """Solar Blaze's "Each creature deals damage to itself equal to its power":
    phase types the targeted form's ``DealDamage`` with the target dropped, so it
    heads the ability with a ``ParentTarget`` that names nothing. The stage
    rewrites it to a ``DamageAll`` over every creature."""
    (rec,) = test_phase_records("Solar Blaze")
    (before,) = _effects(rec)
    assert before["type"] == "DealDamage", (
        "misparsed_shapes self-damage sweep: RETIRE-READY — phase types Solar "
        "Blaze's population itself. Delete the sweep row of misparsed_shapes (the "
        "module, once it holds no row) and this canary."
    )
    assert before["target"] == {"type": "ParentTarget"}
    (after,) = _effects(correct_misparsed_shapes(rec))
    assert after["type"] == "DamageAll"
    assert after["target"]["type_filters"] == ["Creature"]
    assert after["amount"] == before["amount"]
    assert after["damage_source"] == "Target"
    assert _effects(rec)[0]["type"] == "DealDamage"  # the input is untouched


@pytest.mark.parametrize("name", ["Solar Blaze", "Wave of Reckoning", "The Akroan War"])
def test_self_damage_sweep_is_a_board_wipe(name):
    """Each creature is dealt damage equal to its power (CR 120.3e) and one whose
    toughness is no greater dies (704.5g). No creature of yours sizes the
    damage, so it is no power-as-damage payoff (``crosswalk.power_is_yours``)."""
    assert "mass_removal" in _keys(name)
    assert "damage_equal_power" not in _keys(name)
    assert is_board_wipe(test_card(name))
    assert "board_wipe" in role_of(test_card(name))


@pytest.mark.parametrize(
    "name",
    [
        "Repentance",  # "Target creature deals damage to itself …": after a target
        "Stuffy Doll",  # "This creature deals 1 damage to itself": a fixed amount
    ],
)
def test_one_creature_damaging_itself_is_no_sweep(name):
    (rec,) = test_phase_records(name)
    assert correct_misparsed_shapes(rec) is rec
    assert "mass_removal" not in _keys(name)


@pytest.mark.retirement_canary
def test_graveyard_arrival_unknown_mode_canary():
    """Disa the Restless's "Whenever a Lhurgoyf permanent card is put into your
    graveyard from anywhere other than the battlefield": phase leaves the trigger
    mode ``Unknown`` with no zone fields. The stage rewrites it to the
    ``ChangesZone`` → Graveyard form of every other "from anywhere" arrival."""
    (rec,) = test_phase_records("Disa the Restless")
    before = rec["triggers"][0]
    assert isinstance(before["mode"], dict), (
        "misparsed_shapes graveyard arrival: RETIRE-READY — phase types Disa the "
        "Restless's Lhurgoyf graveyard trigger. Delete the arrival row of "
        "misparsed_shapes and this canary."
    )
    assert "Unknown" in before["mode"]
    assert before["destination"] is None
    after = correct_misparsed_shapes(rec)["triggers"][0]
    assert after["mode"] == "ChangesZone"
    assert after["destination"] == "Graveyard"
    assert after["origin"] is None  # phase has no "other than the battlefield"
    assert {"Subtype": "Lhurgoyf"} in after["valid_card"]["type_filters"]
    assert after["valid_card"]["properties"] == [{"type": "Owned", "controller": "You"}]
    assert after["execute"] == before["execute"]  # the typed body is kept
    assert isinstance(rec["triggers"][0]["mode"], dict)  # the input is untouched
    assert {"subtype_ref|you|Lhurgoyf"} <= {
        f"{s.key}|{s.scope}|{s.subject}" for s in test_signals("Disa the Restless")
    }


def test_other_unknown_mode_returns_are_not_graveyard_arrivals():
    # "When target creature dies this turn, return that card to the battlefield"
    # (Graceful Reprieve) has the same typed body under an Unknown mode: a death.
    (rec,) = test_phase_records("Graceful Reprieve")
    assert correct_misparsed_shapes(rec) is rec


@pytest.mark.retirement_canary
def test_split_coin_flip_canary():
    """Desperate Gambit's "flip a coin. If you win the flip, … If you lose the
    flip, …": phase types two flips, the first with only its ``win_effect`` and
    its ``sub_ability`` a second with only its ``lose_effect``. The stage moves
    the losing outcome onto the first flip."""
    (rec,) = test_phase_records("Desperate Gambit")
    head = rec["abilities"][0]["sub_ability"]
    flip, second = head["effect"], head["sub_ability"]["effect"]
    assert second["type"] == "FlipCoins", (
        "misparsed_shapes split coin flip: RETIRE-READY — phase types Desperate "
        "Gambit's one flip. Delete the split-flip row of misparsed_shapes and "
        "this canary."
    )
    assert flip["lose_effect"] is None
    assert second["win_effect"] is None
    after = correct_misparsed_shapes(rec)["abilities"][0]["sub_ability"]
    assert after["effect"]["win_effect"] == flip["win_effect"]
    assert after["effect"]["lose_effect"] == second["lose_effect"]
    assert after["sub_ability"] is None
    assert rec["abilities"][0]["sub_ability"]["effect"]["lose_effect"] is None


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "path"),
    [
        # "Flip a coin at the beginning of the next end step. If you lose the
        # flip, sacrifice that creature." — inside the activation's delayed
        # trigger
        ("Goblin Kites", ("abilities", 0, "sub_ability", "effect", "effect")),
        # "flip a coin at end of combat. If you lose the flip, an opponent gains
        # control of ~" — inside the attack trigger's delayed trigger
        ("Fickle Efreet", ("triggers", 0, "execute", "effect", "effect")),
    ],
)
def test_split_delayed_coin_flip_canary(name, path):
    """The delayed form of the split flip: an outcome-less ``FlipCoins`` whose
    ``sub_ability`` is a lose-only one. The stage moves the losing outcome onto
    the first flip."""
    (rec,) = test_phase_records(name)

    def body(r: dict) -> dict:
        node: object = r
        for step in path:
            node = node[step]  # type: ignore[index]
        assert isinstance(node, dict)
        return node

    before = body(rec)
    second = (before.get("sub_ability") or {}).get("effect") or {}
    assert second.get("type") == "FlipCoins", (
        f"misparsed_shapes split coin flip: RETIRE-READY — phase types {name}'s "
        "one delayed flip. Drop the outcome-less form from the split-flip row "
        "and this canary."
    )
    assert before["effect"]["win_effect"] is None
    assert before["effect"]["lose_effect"] is None
    after = body(correct_misparsed_shapes(rec))
    assert after["effect"]["lose_effect"] == second["lose_effect"]
    assert after["sub_ability"] is None


def test_split_delayed_flips_losing_outcome_is_a_drawback():
    """Losing control of the card (Fickle Efreet) is no blocked-creature payoff,
    and no attack payoff either: the trigger's only outcome is a drawback."""
    assert not {"blocked_matters", "attack_matters"} & _keys("Fickle Efreet")
    # a real "attacks or blocks" reward keeps its attack payoff
    assert "attack_matters" in _keys("Elder Gargaroth")


def test_desperate_gambits_losing_prevention_is_no_shield():
    """The losing outcome prevents the damage of the source the winning one
    doubles: a drawback of the gamble, not a prevention shield."""
    keys = _keys("Desperate Gambit")
    assert "damage_doubling" in keys
    assert not {"damage_prevention", "board_protection"} & keys


@pytest.mark.retirement_canary
def test_chosen_card_type_sweep_canary():
    """Season of Gathering's "Choose artifact or enchantment. Destroy all
    permanents of the chosen type": phase reads the choice as a creature type
    over every permanent. The stage writes the sweep over the listed card
    types, and the wipe read then sees no creatures in it."""
    (rec,) = test_phase_records("Season of Gathering")
    body = next(
        b for b in rec["abilities"] if (b.get("effect") or {}).get("type") == "Choose"
    )
    swept = body["sub_ability"]["effect"]["target"]
    assert [p["type"] for p in swept.get("properties") or ()] == [
        "IsChosenCreatureType"
    ], (
        "misparsed_shapes chosen card type: RETIRE-READY — phase types Season "
        "of Gathering's chosen card type. Delete the chosen-card-type row of "
        "misparsed_shapes and this canary."
    )
    after = correct_misparsed_shapes(rec)
    fixed = next(
        b for b in after["abilities"] if (b.get("effect") or {}).get("type") == "Choose"
    )["sub_ability"]["effect"]["target"]
    assert fixed["type"] == "Or"
    assert [f["type_filters"] for f in fixed["filters"]] == [
        ["Artifact"],
        ["Enchantment"],
    ]
    from mtg_utils._analysis.job_quality import board_wipe

    assert board_wipe.features(test_card("Season of Gathering"))["creatures"] == 0.0


@pytest.mark.retirement_canary
def test_draw_and_blight_canary():
    """Sinister Gnarlbark's "draw a card and blight 1": phase leaves it
    unparsed. The stage writes a Draw and a BlightEffect (CR 701.68a)."""
    (rec,) = test_phase_records("Sinister Gnarlbark")
    effect = rec["triggers"][0]["execute"]["effect"]
    assert effect["type"] == "Unimplemented", (
        "misparsed_shapes draw-and-blight: RETIRE-READY — phase types Sinister "
        "Gnarlbark's clause. Delete the draw-and-blight row and this canary."
    )
    fixed = correct_misparsed_shapes(rec)["triggers"][0]["execute"]
    assert fixed["effect"]["type"] == "Draw"
    assert fixed["sub_ability"]["effect"] == {"type": "BlightEffect", "count": 1}


@pytest.mark.retirement_canary
def test_its_controller_manifests_canary():
    """Unwanted Remake's "Its controller manifests dread": phase drops the
    player. The stage writes Fateful Absence's ``ParentObjectTargetController``."""
    (rec,) = test_phase_records("Unwanted Remake")
    sub = rec["abilities"][0]["sub_ability"]
    assert not sub.get("player_scope"), (
        "misparsed_shapes its-controller manifest: RETIRE-READY — phase types "
        "Unwanted Remake's player. Delete the row and this canary."
    )
    fixed = correct_misparsed_shapes(rec)["abilities"][0]["sub_ability"]
    assert fixed["player_scope"] == {"type": "ParentObjectTargetController"}


@pytest.mark.retirement_canary
def test_equipped_attack_canary():
    """Akiri, Fearless Voyager's "attack a player with one or more equipped
    creatures": phase drops the attackers. The stage writes them back."""
    (rec,) = test_phase_records("Akiri, Fearless Voyager")
    trig = next(t for t in rec["triggers"] if t["mode"] == "YouAttack")
    assert not trig.get("valid_card"), (
        "misparsed_shapes equipped attack: RETIRE-READY — phase types Akiri's "
        "attackers. Delete the row and this canary."
    )
    fixed = next(
        t for t in correct_misparsed_shapes(rec)["triggers"] if t["mode"] == "YouAttack"
    )
    assert fixed["valid_card"]["properties"] == [
        {"type": "HasAttachment", "kind": "Equipment"}
    ]


@pytest.mark.retirement_canary
def test_umbra_armor_grant_canary():
    """Umbra Mystic's "Auras attached to permanents you control have umbra
    armor": phase leaves it unparsed. The stage writes the TotemArmor grant."""
    (rec,) = test_phase_records("Umbra Mystic")
    assert any(
        (b.get("effect") or {}).get("type") == "Unimplemented"
        for b in rec.get("abilities") or ()
    ), (
        "misparsed_shapes umbra armor grant: RETIRE-READY — phase types Umbra "
        "Mystic's static. Delete the row and this canary."
    )
    fixed = correct_misparsed_shapes(rec)
    grant = fixed["static_abilities"][-1]
    assert grant["modifications"] == [{"type": "AddKeyword", "keyword": "TotemArmor"}]
    assert not fixed["abilities"]


@pytest.mark.retirement_canary
def test_relative_power_return_canary():
    """Mirko, Obsessive Theorist returns "target creature card with power less
    than ~'s": phase v0.118.0 keeps only InZone Graveyard and Owned You on the
    target. The stage adds the ``PtComparison`` power ``LT`` the source's
    power (Apprentice Sharpshooter's form), so the commander's need reads the
    bound off the tree (2026-11-02)."""
    (rec,) = test_phase_records("Mirko, Obsessive Theorist")

    def target(r):
        (trig,) = [
            t
            for t in r.get("triggers") or ()
            if "power less than" in str(t.get("description") or "")
        ]
        return trig["execute"]["effect"]["target"]

    before = target(rec)["properties"]
    assert not any(p["type"] == "PtComparison" for p in before), (
        "misparsed_shapes relative power return: RETIRE-READY — phase types "
        "Mirko's power bound. Delete the power-return row and this canary."
    )
    after = target(correct_misparsed_shapes(rec))["properties"]
    (bound,) = [p for p in after if p["type"] == "PtComparison"]
    assert bound["comparator"] == "LT"
    assert bound["stat"] == "Power"


@pytest.mark.retirement_canary
def test_countered_exile_instead_canary():
    """Dissipate's "If that spell is countered this way, exile it instead of
    putting it into its owner's graveyard": phase types the exile as a move
    ``origin: Graveyard``. "Instead" makes it a replacement (CR 614.1a), so the
    spell goes from the stack to exile and the stage clears the ``origin``."""
    (rec,) = test_phase_records("Dissipate")
    (body,) = rec["abilities"]
    assert body["effect"]["type"] == "Counter"
    before = (body.get("sub_ability") or {}).get("effect") or {}
    assert before.get("origin") == "Graveyard", (
        "misparsed_shapes countered exile: RETIRE-READY — phase no longer types "
        "Dissipate's exile as a move out of the graveyard. Delete the countered-"
        "exile row of misparsed_shapes and this canary, and check that "
        "crosswalk.diverts_from_graveyard still reads phase's new form."
    )
    assert before["destination"] == "Exile"
    after = correct_misparsed_shapes(rec)["abilities"][0]["sub_ability"]["effect"]
    assert after["origin"] is None
    assert after["destination"] == "Exile"
    assert after["target"] == {"type": "ParentTarget"}
    assert before["origin"] == "Graveyard"  # the input is untouched


@pytest.mark.parametrize("name", ["Dissipate", "Force of Negation", "No More Lies"])
def test_countered_exile_is_no_graveyard_card(name):
    """The graveyard the countered spell is kept out of is no graveyard the card
    plays with: no ``graveyard_matters``, still a counterspell."""
    keys = _keys(name)
    assert "graveyard_matters" not in keys
    assert "counter_control" in keys


def test_countered_exile_keeps_a_real_graveyard_clause():
    """Devious Cover-Up exiles the countered spell instead AND returns cards from
    your graveyard to your library: the second clause still reads."""
    assert ("graveyard_matters", "you") in {
        (s.key, s.scope) for s in test_signals("Devious Cover-Up")
    }


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Goliath Daydreamer", "Gandalf of the Secret Fire"])
def test_cast_trigger_exile_instead_canary(name):
    """Goliath Daydreamer's "exile that card with a dream counter on it instead of
    putting it into your graveyard as it resolves" (Gandalf's, with three time
    counters): phase types the exile of the cast spell as a move ``origin:
    Graveyard``. The stage clears the ``origin`` and keeps the counters."""
    (rec,) = test_phase_records(name)
    cast = next(t for t in rec["triggers"] if t["mode"] == "SpellCast")
    before = cast["execute"]["effect"]
    assert before.get("origin") == "Graveyard", (
        f"misparsed_shapes cast-trigger exile: RETIRE-READY — phase no longer types "
        f"{name}'s exile as a move out of the graveyard. Delete the "
        "SpellCast arm of the spell-exiled-instead row and this canary, and check "
        "that crosswalk.diverts_from_graveyard still reads phase's new form."
    )
    after = next(
        t for t in correct_misparsed_shapes(rec)["triggers"] if t["mode"] == "SpellCast"
    )["execute"]["effect"]
    assert after["origin"] is None
    assert after["destination"] == "Exile"
    assert after["enter_with_counters"] == before["enter_with_counters"]


@pytest.mark.parametrize(
    "name",
    [
        # a cast trigger exiling its spell (corrected)
        "Goliath Daydreamer",
        "Gandalf of the Secret Fire",
        # phase's own ExileResolvingSpellInsteadOfGraveyard
        "Feather, the Redeemed",
        "Lilah, Undefeated Slickshot",
        "River Song's Diary",
        "Rod of Absorption",
        # the mana rider phase parks (the recovery grammar's exile_instead)
        "Forger's Foundry",
        # a replacement of its own discard
        "Dodecapod",
        "Loxodon Smiter",
        "Nullhide Ferox",
        "Obstinate Baloth",
        "Wilt-Leaf Liege",
        # modal: claimed by its mode's description
        "Defabricate",
    ],
)
def test_a_graveyard_the_card_never_reaches_is_no_graveyard_card(name):
    """ "Instead of putting it into … graveyard" names a destination a replacement
    takes the card away from (CR 614.1a): no ``graveyard_matters``."""
    assert "graveyard_matters" not in _keys(name)


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        ("Rest in Peace", "any"),  # any card's move to a graveyard: graveyard hate
        ("Leyline of the Void", "opponents"),
        ("Spellweaver Volute", "you"),  # its cast trigger exiles another object
    ],
)
def test_a_graveyard_replacement_that_is_hate_keeps_its_signal(name, scope):
    assert ("graveyard_matters", scope) in {
        (s.key, s.scope) for s in test_signals(name)
    }


@pytest.mark.parametrize(
    ("name", "diverts"),
    [
        ("Loxodon Smiter", True),  # its own discard, onto the battlefield instead
        ("Goliath Daydreamer", True),  # its cast trigger exiles the spell instead
        ("Rest in Peace", False),  # any card's move to a graveyard: hate
        ("Spellweaver Volute", False),  # its cast trigger exiles another object
    ],
)
def test_diverts_from_graveyard_reads_the_ability(name, diverts):
    from mtg_utils._card_ir.crosswalk import diverts_from_graveyard
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card_ir

    test_card_ir(name)  # seeds the card's trees from the snapshot
    units = [u for t in trees_for(test_card(name)) for u in t.units]
    assert any(diverts_from_graveyard(u) for u in units) is diverts
