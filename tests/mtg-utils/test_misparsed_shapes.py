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
    creatures": phase leaves the trigger's mode ``Unknown``. The stage writes
    the attack and its attackers back."""
    (rec,) = test_phase_records("Akiri, Fearless Voyager")
    parked = [t for t in rec["triggers"] if isinstance(t["mode"], dict)]
    assert parked, (
        "misparsed_shapes equipped attack: RETIRE-READY — phase types Akiri's "
        "attack trigger. Delete the row and this canary if it names the "
        "attackers on valid_card; else narrow the row back to a YouAttack mode."
    )
    fixed = next(
        t for t in correct_misparsed_shapes(rec)["triggers"] if t["mode"] == "YouAttack"
    )
    assert fixed["valid_card"]["properties"] == [
        {"type": "HasAttachment", "kind": "Equipment"}
    ]
    assert ("voltron_matters", "you") in {
        (s.key, s.scope) for s in test_signals("Akiri, Fearless Voyager")
    }


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        (
            "Whenever you attack a player with one or more equipped creatures",
            "Equipment",
        ),
        # synthetic: the Aura form, and two lines that are other events
        ("Whenever you attack with one or more enchanted creatures", "Aura"),
        ("Whenever you attack with one or more Zombies", None),
        ("Whenever you attack with one or more equipped creatures and a Knight", None),
    ],
)
def test_attached_attackers_grammar(line, kind):
    from mtg_utils._card_ir.clause_grammar import attached_attackers_kind

    assert attached_attackers_kind(line) == kind


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
        "Mystic's static. Once no parked line reads as a grant, delete the "
        "parked-grant row, clause_grammar.subtype_keyword_grant (and _SUBTYPE) "
        "and this canary; keep the umbra armor keyword in GRANT_KEYWORDS."
    )
    fixed = correct_misparsed_shapes(rec)
    grant = fixed["static_abilities"][-1]
    assert grant["modifications"] == [{"type": "AddKeyword", "keyword": "TotemArmor"}]
    assert grant["affected"] == {
        "type": "Typed",
        "type_filters": [{"Subtype": "Aura"}],
        "controller": "You",
        "properties": [],
    }
    assert grant["description"] == rec["abilities"][0]["effect"]["description"]
    assert not fixed["abilities"]


@pytest.mark.parametrize(
    "line",
    [
        # synthetic lines: a grantee that isn't yours alone, and grants beside
        # a pump, which the rewrite would drop
        "Wizards your team controls have flying.",
        "Enchanted creatures each get +1/+1 and have hexproof.",
        "Equipment you control have hexproof and get +1/+1.",
    ],
)
def test_only_a_bare_grant_to_your_subtype_is_rebuilt(line):
    from mtg_utils._card_ir.clause_grammar import subtype_keyword_grant

    assert subtype_keyword_grant(line) is None


def test_a_parked_grant_reads_its_subtype_and_keywords():
    from mtg_utils._card_ir.clause_grammar import subtype_keyword_grant

    line = (
        "Static pattern matched but line failed static parser: "
        "Auras attached to permanents you control have umbra armor."
    )
    assert subtype_keyword_grant(line) == ("Aura", frozenset({"totem armor"}))
    assert subtype_keyword_grant("Equipment you control have hexproof.") == (
        "Equipment",
        frozenset({"hexproof"}),
    )


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


# ── A pump phase parks ──────────────────────────────────────────────────────────


def _at(rec: dict, path: tuple) -> dict:
    node: object = rec
    for step in path:
        node = node[step]  # type: ignore[index]
    assert isinstance(node, dict)
    return node


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "path", "tag", "target"),
    [
        # (card, where the residue sits, the typed pump's tag, its target)
        ("Freelance Muscle", ("triggers", 0, "execute"), "Pump", {"type": "SelfRef"}),
        (
            "Bronze Cudgels",
            ("abilities", 0),
            "PumpAll",
            {
                "type": "Typed",
                "type_filters": ["Creature"],
                "controller": None,
                "properties": [{"type": "EquippedBy"}],
            },
        ),
        (
            "General Tazri",
            ("abilities", 0),
            "PumpAll",
            {
                "type": "Typed",
                "type_filters": ["Creature", {"Subtype": "Ally"}],
                "controller": "You",
                "properties": [],
            },
        ),
        (
            "Huntmaster Liger",
            ("triggers", 0, "execute"),
            "PumpAll",
            {
                "type": "Typed",
                "type_filters": ["Creature"],
                "controller": "You",
                "properties": [{"type": "Another"}],
            },
        ),
        ("Keldon Battlewagon", ("abilities", 0), "Pump", {"type": "SelfRef"}),
        (
            "Pack Attack",
            ("abilities", 0),
            "PumpAll",
            {
                "type": "Typed",
                "type_filters": ["Creature"],
                "controller": None,
                "properties": [{"type": "Attacking"}],
            },
        ),
        (
            "Razorfield Ripper",
            ("triggers", 0, "execute", "sub_ability"),
            "Pump",
            {"type": "TriggeringSource"},
        ),
        (
            "Velukan Dragon",
            ("triggers", 0, "execute", "sub_ability"),
            "Pump",
            {"type": "SelfRef"},
        ),
        # "Tap an untapped red creature you control other than ~: ~ gets +X/+0"
        ("Impelled Giant", ("abilities", 0), "Pump", {"type": "SelfRef"}),
        # the back face: "… Return that card to your hand. ~ gets +X/+0 until
        # end of turn, where X is the mana value of that card."
        (
            "The Kami War // O-Kagachi Made Manifest",
            ("triggers", 0, "execute", "sub_ability", "sub_ability"),
            "Pump",
            {"type": "SelfRef"},
        ),
        # a clause parked whole that is the pump itself, after "Untap all
        # creatures you control"
        (
            "Gideon, Martial Paragon",
            ("abilities", 0, "sub_ability"),
            "PumpAll",
            {"type": "TrackedSet", "id": 0},
        ),
    ],
    ids=lambda case: case if isinstance(case, str) else "",
)
def test_parked_pump_canary(name, path, tag, target):
    """A pump phase parks: by an X it can't bind, only the binding is left
    ("it gets +X/+X until end of turn, where X is …"); after a mass effect, the
    whole clause ("Those creatures get +1/+1 until end of turn"). The stage
    writes the pump back as the node phase types for those words elsewhere, and
    the face still loads."""
    face = name.split(" // ")[-1]  # the pump's face: the last one named
    (rec,) = (r for r in test_phase_records(name) if r["name"] == face)
    parked = _at(rec, path)["effect"]
    assert parked.get("type") == "Unimplemented", (
        f"misparsed_shapes parked pump: RETIRE-READY — phase types {name}'s "
        "pump. Once no residue reads as a pump, delete the row, "
        "clause_grammar.parked_pump and this canary."
    )
    body = _at(correct_misparsed_shapes(rec), path)
    assert body["effect"]["type"] == tag
    assert body["effect"]["target"] == target
    x_sized = parked.get("name") == "where_x_binding"
    assert body["effect"]["power"] == (
        {"type": "Variable", "value": "X"} if x_sized else {"type": "Fixed", "value": 1}
    )
    assert body["duration"] == "UntilEndOfTurn"
    assert test_signals(name), f"{name} builds no tree after the rewrite"


def test_a_where_x_pump_reads_as_the_pump_it_is():
    """The rewritten pumps reach the lanes a typed pump reaches, with no lane
    taught the residue: a team pump, a self pump, a combat buff."""

    def idents(name):
        return {(s.key, s.scope, s.subject) for s in test_signals(name)}

    assert ("pump_makers", "you", "") in idents("General Tazri")
    assert ("pump_makers", "you", "") in idents("Huntmaster Liger")
    assert ("team_buff", "you", "pump") in idents("Huntmaster Liger")
    assert ("self_pump", "you", "") in idents("Keldon Battlewagon")
    assert ("voltron_makers", "you", "pump") in idents("Bronze Cudgels")
    assert ("combat_buff_engine", "you", "") in idents("Razorfield Ripper")


def test_only_a_pumps_own_residue_is_rewritten():
    """The row reads two residues: the binding of a pump's X and the "those
    creatures get" rider after a mass untap. A whole trigger parked under
    another name is left alone, however much its last words read as a pump."""
    whole = "Whenever ~ attacks, creatures you control get +1/+0 until end of turn."
    rec = {
        "name": "Zzyx Test Bannerman",
        "abilities": [
            {
                "effect": {
                    "type": "Unimplemented",
                    "name": "static_structure",
                    "description": whole,
                },
                "description": whole,
            }
        ],
    }
    assert correct_misparsed_shapes(rec) is rec


def test_it_after_a_targeted_effect_is_not_guessed():
    """ "It" after an effect that names an object may be that object, which phase
    writes ``ParentTarget``; after "you get {E}" it is the trigger's own source
    (Razorfield Ripper, in the canary). The first is left a residue."""
    text = "where X is the number of cards in your hand"
    rec = {
        "name": "Zzyx Test Goader",
        "triggers": [
            {
                "mode": "Attacks",
                "valid_card": {"type": "SelfRef"},
                "description": (
                    "Whenever ~ attacks, tap target creature, then it gets +X/+0 "
                    f"until end of turn, {text}."
                ),
                "execute": {
                    "effect": {
                        "type": "SetTapState",
                        "target": {"type": "Typed", "type_filters": ["Creature"]},
                    },
                    "sub_ability": {
                        "effect": {
                            "type": "Unimplemented",
                            "name": "where_x_binding",
                            "description": text,
                        }
                    },
                },
            }
        ],
    }
    assert correct_misparsed_shapes(rec) is rec


_MUSCLE = (
    "Whenever ~ attacks or blocks, it gets +X/+X until end of turn, where X is the "
    "greatest power and/or toughness among other creatures you control."
)
_CUDGELS = (
    "{2}: Until end of turn, equipped creature gets +X/+0, where X is the number "
    "of times this ability has resolved this turn."
)
_VELUKAN = (
    "Whenever ~ attacks or blocks, roll a six-sided die. ~ gets +X/+0 until end of "
    "turn, where X is the result minus 1."
)
_RIPPER = (
    "Whenever ~ or equipped creature attacks, you get {E} , then it gets +X/+X "
    "until end of turn, where X is the amount of {E} you have."
)


@pytest.mark.parametrize(
    ("line", "recipient", "amounts"),
    [
        (_MUSCLE, "it", ("+X", "+X")),
        (_CUDGELS, "attached", ("+X", "+0")),
        (_VELUKAN, "self", ("+X", "+0")),
        (_RIPPER, "it", ("+X", "+X")),
        ("Those creatures get +1/+1 until end of turn", "those", ("+1", "+1")),
    ],
)
def test_parked_pump_grammar(line, recipient, amounts):
    from mtg_utils._card_ir.clause_grammar import parked_pump

    pump = parked_pump(line)
    assert pump is not None
    assert pump.subject.recipient == recipient
    assert (pump.power, pump.toughness) == amounts
    assert pump.until_end_of_turn


@pytest.mark.parametrize(
    "line",
    [
        # a pump that also grants: more than a pump
        "it gets +2/+0 and gains haste until end of turn",
        # a subject the grammar doesn't read
        "Target creature gets -X/-X until end of turn, where X is its toughness",
        # a condition on the pump: the condition is what phase parked
        "if your team controls another Warrior, ~ gets +1/+1 until end of turn",
        # no pump at all
        "Whenever ~ attacks, it connives X, where X is the amount of damage",
    ],
)
def test_parked_pump_grammar_reads_a_bare_pump_only(line):
    from mtg_utils._card_ir.clause_grammar import parked_pump

    assert parked_pump(line) is None
