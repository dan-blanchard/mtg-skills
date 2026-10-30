"""Phase gaps behind the damage-redirect / removal / debuff / counter lanes.

Phase v0.104.0 parks some clauses as ``Unimplemented`` residues and drops others
whole. The residue-carried ones recover (ADR-0038): a redirect ("all damage that
would be dealt to X is dealt to Y instead", CR 614.9) and a counter bonus ("that
many plus one", CR 122.1) through ``clause_grammar.REPLACEMENT_TOKENS``, a -X/-X
shrink phase's static parser failed on (CR 613.4c) through the ``debuff`` static
row, and a burn "to you and any target" through the ``damage`` row. A tap's fresh
target phase stamps ``ParentTarget`` is an overlay decoration
(``fresh_tap_target``: the ``TARGET_OBJECT`` subject mark). The dropped clauses are bridge-ledger rows, whose own
convergence tests (``test_bridge_ledger``) retire them; here only the idents they
serve are pinned.

Each recovery and correction has a ``retirement_canary`` over the raw phase record:
it fails RETIRE-READY once phase parses the clause.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace

import pytest

from mtg_utils._card_ir.crosswalk import OTHER, ConceptNode, tag_of
from mtg_utils._card_ir.recovery import OTHER_PLAYER, TARGET_OBJECT, recover_concepts
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_card_ir, test_phase_records, test_signals
from mtg_utils.twohg_scan import classify_card


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def _recovered(name: str, token: str) -> list[ConceptNode]:
    test_card_ir(name)  # seeds the trees from the snapshot's phase records
    return [
        c
        for t in trees_for(test_card(name))
        for c in t.iter_concepts()
        if c.recovered_by == token
    ]


def _walk(node: object) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _residues(name: str) -> list[str]:
    """The descriptions of the raw phase record's ``Unimplemented`` nodes."""
    return [
        n.get("description") or ""
        for rec in test_phase_records(name)
        for n in _walk(rec)
        if n.get("type") == "Unimplemented"
    ]


def _parked(name: str, words: str) -> bool:
    return any(words in r.lower() for r in _residues(name))


# ── damage_redirect: CR 614.9 redirection effects parked as residues ──────────

_REDIRECTS = [
    "Kjeldoran Royal Guard",  # damage to you → this creature (unparsed_replacement)
    "Shimian Night Stalker",
    "Oracle's Attendants",  # damage to target creature → this creature
    "Karona's Zealot",  # damage to it → target creature
    "Ascent of the Worthy",  # damage to creatures you control → the chosen one
    "Kor Chant",  # unrecognized_clause_head, cut before "instead"
    "Kor Dirge",
    "Sivvi's Valor",  # damage to target creature → you
    "Turn the Tables",  # combat damage to you → target attacking creature
    "Blood of the Martyr",  # "you may have that damage dealt to you"
    "Glarecaster",  # "that damage is dealt to any target instead" (ARM B too)
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    "name",
    [
        *_REDIRECTS,
        "Treacherous Link",
        "Megatron, Tyrant // Megatron, Destructive Force",
    ],
)
def test_redirect_is_still_a_residue_canary(name):
    assert _parked(name, "would be dealt"), (
        f"{name}: RETIRE-READY — phase now types the redirect. Drop {name} from "
        "this canary; once no card is left, delete the damage_redirect row of "
        "clause_grammar.REPLACEMENT_TOKENS, its recovery.ALLOWLIST entry and "
        "_damage_redirect's ARM D."
    )


@pytest.mark.parametrize("name", _REDIRECTS)
def test_recovered_redirect_serves_damage_redirect(name):
    assert _recovered(name, "damage_redirect")
    assert "damage_redirect|you|" in _idents(name)


@pytest.mark.parametrize(
    "name", ["Treacherous Link", "Megatron, Tyrant // Megatron, Destructive Force"]
)
def test_redirect_onto_a_controller_shields_nothing(name):
    """Treacherous Link's curse and Megatron's excess damage move the damage onto
    a creature's controller: a punisher, not a redirect shielding you
    (``reads.redirects_damage_from_you`` draws the same line)."""
    (node,) = _recovered(name, "damage_redirect")
    assert OTHER_PLAYER in node.reading
    assert "damage_redirect|you|" not in _idents(name)


@pytest.mark.parametrize("name", ["Turn the Tables", "Karona's Zealot", "Kor Chant"])
def test_a_redirect_is_never_removal(name):
    """A redirect onto a target creature deals no damage of its own: no burn
    lane reads it, and the 2HG scan sees no removal reach."""
    assert not {"removal|you|", "direct_damage|you|"} & _idents(name)
    assert classify_card(test_card(name)) is None


def _residue_node(raw: str) -> ConceptNode:
    """Kjeldoran Royal Guard's residue node, undecorated, reading ``raw``."""
    (c,) = _recovered("Kjeldoran Royal Guard", "damage_redirect")
    return replace(c, concept=OTHER, recovered_by="", subject=(), clause=(), raw=raw)


_REDIRECT = "All damage that would be dealt to you this turn is dealt to target "
_REDIRECT += "creature instead"
_BONUS = "if you would put one or more +1/+1 counters on a creature you control, "
_BONUS += "put that many plus one +1/+1 counters on it instead"


@pytest.mark.parametrize(
    ("raw", "tokens"),
    [
        (f"Draw a card. {_REDIRECT}", ["draw", "damage_redirect"]),
        (f"{_REDIRECT}. Draw a card", ["damage_redirect", "draw"]),
        (f"Destroy target artifact. {_BONUS}", ["destroy", "counter_bonus"]),
        (_BONUS, ["counter_bonus"]),
    ],
)
def test_a_replacement_idiom_is_its_own_sentences_reading(raw, tokens):
    """A replacement idiom reads over its own sentence: a compound residue keeps
    its instruction and gains the idiom as a later one, in either order, and a
    clause that is only the idiom never reads its inner verb ("put … counters")."""
    out = recover_concepts((_residue_node(raw),))
    assert [c.recovered_by for c in out] == tokens


# ── counter_bonus: "that many plus one" parked as a residue ───────────────────


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Prairie Dog", "Zabaz, the Glimmerwasp"])
def test_counter_bonus_is_still_a_residue_canary(name):
    assert _parked(name, "that many plus one"), (
        f"{name}: RETIRE-READY — phase now types the AddCounter replacement. Drop "
        f"{name}; once none is left, delete the counter_bonus row of "
        "clause_grammar.REPLACEMENT_TOKENS, its recovery.ALLOWLIST entry and the "
        "counter_bonus arm of triggers_damage's replacement lane."
    )


@pytest.mark.parametrize("name", ["Prairie Dog", "Zabaz, the Glimmerwasp"])
def test_counter_bonus_serves_counter_replace_bonus(name):
    assert _recovered(name, "counter_bonus")
    assert {"counter_replace_bonus|you|", "counter_doubling|you|"} <= _idents(name)


@pytest.mark.parametrize("name", ["Winding Constrictor", "Izzet Generatorium"])
def test_a_players_counter_bonus_is_not_a_counter_placement(name):
    """ "If you would get one or more counters / {E}" adds to a player, not to a
    permanent: the counter_bonus idiom never reads it."""
    assert not _recovered(name, "counter_bonus")


# ── debuff: a -X/-X its parsers failed on, a -1/-1 counter on a target ────────

_DEBUFF_STATICS = [
    "Death's Approach",
    "Disturbing Conversion",
    "Nuclear Fallout",
    "Sewer Plague",  # "perpetually gets -2/-2" (off-format; its ledger row retired)
]
_SHRINK = re.compile(r"-(?:\d+|x)/-(?:\d+|x)\b", re.IGNORECASE)


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", _DEBUFF_STATICS)
def test_shrink_is_still_a_residue_canary(name):
    assert any(_SHRINK.search(r) for r in _residues(name)), (
        f"{name}: RETIRE-READY — phase now types the shrink. Drop {name}; once "
        "none is left, delete the debuff row of clause_grammar.STATIC_TOKENS, its "
        "recovery.ALLOWLIST entry and _debuff_makers' recovered-debuff read."
    )


@pytest.mark.parametrize("name", _DEBUFF_STATICS)
def test_recovered_shrink_serves_debuff_makers(name):
    assert _recovered(name, "debuff")
    assert "debuff_makers|any|" in _idents(name)


def test_foul_renewal_shrink_recovers_from_its_binding_sentence():
    """Foul Renewal's -X/-X survives only as its "where X is …" binding; the
    ``debuff`` row reads the binding's sentence (``from_binding_sentence``)."""
    assert _recovered("Foul Renewal", "debuff")
    assert "debuff_makers|any|" in _idents("Foul Renewal")


@pytest.mark.retirement_canary
def test_attempted_murder_counters_are_still_a_residue_canary():
    assert _parked("Attempted Murder", "-1/-1 counters on that creature"), (
        "Attempted Murder: RETIRE-READY — phase now types the -1/-1 PutCounter. "
        "Delete graveyard_lifeloss._recovered_minus_counter_on_target."
    )


def test_minus_counters_on_the_chosen_target_are_a_debuff():
    assert "debuff_makers|any|" in _idents("Attempted Murder")


def test_minus_counter_on_the_card_itself_is_a_drawback():
    """Matopi Golem's "put a -1/-1 counter on it" shrinks itself."""
    assert _recovered("Matopi Golem", "place_counter")
    assert "debuff_makers|any|" not in _idents("Matopi Golem")


# ── damage: a burn "to you and any target" ────────────────────────────────────


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("Ian the Reckless", "to you and any target"),
        ("Volcano Hellion", "to you and target creature"),
    ],
)
def test_you_and_target_burn_is_still_a_residue_canary(name, words):
    assert _parked(name, words), (
        f"{name}: RETIRE-READY — phase now types the burn. Drop {name}; once none "
        "is left, delete recovery's 'you and' object_verb override of the damage "
        "row."
    )


@pytest.mark.parametrize("name", ["Ian the Reckless", "Volcano Hellion"])
def test_you_and_target_burn_is_removal(name):
    (node,) = _recovered(name, "damage")
    assert TARGET_OBJECT in node.reading
    assert "removal|you|" in _idents(name)


def test_a_recovered_burn_answers_the_types_it_names():
    """The 2HG scan's removal reach: Volcano Hellion's "target creature" never
    reaches a planeswalker; Ian the Reckless's "any target" does (CR 115.4)."""
    assert classify_card(test_card("Volcano Hellion"))["removal_reach"]["walkers"] is (
        False
    )
    assert classify_card(test_card("Ian the Reckless"))["removal_reach"]["walkers"]


# ── fresh_tap_target: "tap target creature …" typed as a back-reference ───────

_FRESH_TAPS = [
    "Stunning Shot",
    "Mind Spiral",
    "Snaremaster Sprite",
    # Seasoned Cryomancer left at phase v0.118.0: its reflexive tap is parked
    # whole (zone_change_reflexive_unbound_referent).
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", _FRESH_TAPS)
def test_fresh_tap_target_is_still_a_back_reference_canary(name):
    taps = [
        n
        for rec in test_phase_records(name)
        for n in _walk(rec)
        if n.get("type") == "SetTapState"
    ]
    assert any((t.get("target") or {}).get("type") == "ParentTarget" for t in taps), (
        f"{name}: RETIRE-READY — phase now types the tap's own target. Drop {name}; "
        "once none is left, delete overlay_corrections._arm_fresh_tap_target and "
        "the tapper lane's ParentTarget + TARGET_OBJECT read."
    )


@pytest.mark.parametrize("name", _FRESH_TAPS)
def test_fresh_tap_target_is_a_tapper(name):
    test_card_ir(name)
    assert any(
        tag_of(c.node) == "SetTapState" and TARGET_OBJECT in c.subject
        for t in trees_for(test_card(name))
        for c in t.iter_concepts()
    )
    assert "tapper_engine|any|" in _idents(name)


# ── bridge-ledger rows: the idents each dropped clause serves ─────────────────


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Cragganwick Cremator", "removal|you|"),
        ("Flames of the Blood Hand", "removal|you|"),
        ("Kaboom!", "removal|you|"),
        ("Unstable Footing", "removal|you|"),
        ("Insult // Injury", "removal|you|"),
        ("Tetsuo, Imperial Champion", "removal|you|"),
        ("Mob Verdict", "mass_removal|you|"),
        ("Chandra's Flame Wave", "mass_removal|you|"),
        ("Chandra, Flame's Fury", "mass_removal|you|"),
        ("Path of Mettle // Metzali, Tower of Triumph", "mass_removal|you|"),
        ("Decimator Beetle", "debuff_makers|any|"),
        ("Zealous Persecution", "debuff_makers|any|"),
        ("Heir of the Ancient Fang", "modified_matters|you|"),
        ("Lethal Exploit", "modified_matters|you|"),
        ("Lethal Throwdown", "modified_matters|you|"),
        ("Lion Umbra", "modified_matters|you|"),
        ("Ian the Reckless", "modified_matters|you|"),
        ("Elspeth Resplendent", "shield_counter_makers|you|"),
        ("Undercover Operative", "shield_counter_makers|you|"),
    ],
)
def test_dropped_clause_bridge_serves(name, ident):
    assert ident in _idents(name)


def test_kaboom_and_flames_still_serve_direct_damage():
    """Their ``direct_damage`` rows still fire beside the new ``removal`` row."""
    for name in ("Kaboom!", "Flames of the Blood Hand", "Insult // Injury"):
        assert "direct_damage|you|" in _idents(name), name
