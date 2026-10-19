"""Phase gaps behind the counter / token / discard / energy / foretell / Food /
Treasure lanes (the resources slice of the phase-gap pass).

phase v0.104.0 parks each clause below as an ``Unimplemented`` residue, or drops
it outright. Each is filled one way, and each way retires itself:

* **Recovery** (ADR-0038) — the residue is re-decorated through an allowlisted
  grammar token, and the shared reads (``keyword_action_events``,
  ``keyword_counter_placements``, ``keyword_resource_events``) read the token
  (``recovered_by``): connive, amass and investigate off a ``where_x_binding``
  residue's sentence (``TokenRule.from_binding_sentence``), devour, gaining and
  paying {E}, and foretell.
* **A lane arm over a recovered reading** — Jetmir's Fixer's Treasure-spent
  condition (``treasure_matters``).
* **A lane arm over a keyword parameter** — Tomik, Wielder of Law's affinity for
  planeswalkers (``ConceptTree.card_keyword_types``; the repo dropped it, not
  phase, so no canary).
* **A bridge row** (ADR-0048) — Osteomancer Adept's dropped forage cost
  (``forage_cast_permission_cost_dropped``; ``test_bridge_ledger`` runs its
  convergence check).

Every recovery and lane arm has a ``retirement_canary`` below: it reads the raw
phase record and fails RETIRE-READY once phase parses the clause.
"""

from __future__ import annotations

import pytest

from mtg_utils._analysis.bridge_ledger import BRIDGES
from mtg_utils._card_ir.clause_grammar import parse_clause, scan_clause, static_token
from mtg_utils._card_ir.crosswalk import (
    keyword_action_events,
    keyword_counter_placements,
    keyword_resource_events,
    keyword_token_creations,
    tag_of,
)
from mtg_utils._card_ir.recovery import ALLOWLIST
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def _trees(name: str):
    return trees_for(test_card(name))


def _recovered(name: str) -> dict[str, list]:
    """``recovered_by`` token -> the recovered effect nodes on ``name``."""
    out: dict[str, list] = {}
    for t in _trees(name):
        for unit in t.units:
            for c in unit.effects:
                if c.recovered_by:
                    out.setdefault(c.recovered_by, []).append(c)
    return out


def _residues(name: str) -> list[tuple[str, str]]:
    """``(phase residue name, description)`` for every ``Unimplemented`` node in
    ``name``'s raw phase records."""
    out: list[tuple[str, str]] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if o.get("type") == "Unimplemented":
                out.append((o.get("name") or "", o.get("description") or ""))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for rec in test_phase_records(name):
        walk(rec)
    return out


def _residue_text(name: str, residue: str) -> str:
    """The description of ``name``'s one ``residue``-named residue."""
    (text,) = [d for n, d in _residues(name) if n == residue]
    return text


def _raw_tags(name: str) -> set[str]:
    tags: set[str] = set()

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if isinstance(o.get("type"), str):
                tags.add(o["type"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for rec in test_phase_records(name):
        walk(rec)
    return tags


# ── keyword actions off a where-X binding: connive, amass, investigate ────────


def test_mask_of_the_schemer_connives():
    """CR 701.50a: the conniving permanent's controller draws, discards, and puts
    a +1/+1 counter on it for a nonland discard — the connive / discard / +1/+1
    reads a typed ``Connive`` node feeds (Raffine's Informant)."""
    (c,) = _recovered("Mask of the Schemer")["connive"]
    assert c.concept == "connive"
    assert tag_of(c.node) == "Unimplemented"  # phase's node, re-decorated in place
    events = [
        e for t in _trees("Mask of the Schemer") for e in keyword_action_events(t)
    ]
    assert [(e.tag, e.yours) for e in events] == [("Connive", True)]
    assert {
        "connive_makers|you|",
        "discard_makers|you|",
        "plus_one_makers|you|",
    } <= _idents("Mask of the Schemer")


def test_fall_of_cair_andros_amasses():
    """CR 701.47a: amass creates a 0/0 Army when you control none and puts +1/+1
    counters on it."""
    assert [c.concept for c in _recovered("Fall of Cair Andros")["amass"]] == ["amass"]
    assert {
        c for t in _trees("Fall of Cair Andros") for c in keyword_token_creations(t)
    } == {("Amass", "Army")}
    assert {"plus_one_makers|you|", "token_maker|you|Army", "amass_makers|you|"} <= (
        _idents("Fall of Cair Andros")
    )


def test_officious_interrogation_investigates():
    """CR 701.16a: "Investigate" means "Create a Clue token"."""
    (c,) = _recovered("Officious Interrogation")["investigate"]
    assert c.concept == "investigate"
    assert "clue_makers|you|" in _idents("Officious Interrogation")


def test_binding_sentence_reads_only_flagged_tokens():
    """The binding's sentence recovers only a ``from_binding_sentence`` row:
    Erestor of the Council's "You scry X, where X is …" names an allowlisted verb
    (scry) without the flag, so its binding stays a residue."""
    sentence = "You scry X, where X is the number of opponents"
    assert (parse_clause(sentence) or scan_clause(sentence)) == "scry"
    assert not ALLOWLIST["scry"].from_binding_sentence
    assert "scry" not in _recovered("Erestor of the Council")


def test_foul_renewal_binding_recovers_as_a_debuff():
    """Foul Renewal's "Target creature gets -X/-X until end of turn, where X is …"
    — the ``debuff`` row reads its binding's sentence too (CR 613.4c)."""
    assert ALLOWLIST["debuff"].from_binding_sentence
    assert "debuff" in _recovered("Foul Renewal")


def test_commence_the_endgame_amass_stays_on_the_keyword_fallback():
    """Commence the Endgame's "then amass Zombies X" is folded into the Draw node's
    description — no residue for recovery to read (a dropped clause), so it keeps
    the Scryfall keyword-array fallback (``amass_makers``) and the canary in
    ``tests/deck-forge/test_serve_idents_token_makers.py``."""
    assert "amass" not in _recovered("Commence the Endgame")
    assert not any(n == "where_x_binding" for n, _ in _residues("Commence the Endgame"))
    assert "amass_makers|you|" in _idents("Commence the Endgame")


# ── devour ────────────────────────────────────────────────────────────────────


def test_thromok_devours():
    """CR 702.82a: "Devour N" means "… This permanent enters with N +1/+1 counters
    on it for each creature sacrificed this way"."""
    assert parse_clause("Devour X, where X is the number of creatures") == "devour"
    assert [c.concept for c in _recovered("Thromok the Insatiable")["devour"]] == [
        "devour"
    ]
    assert ("devour", "P1P1") in {
        p
        for t in _trees("Thromok the Insatiable")
        for p in keyword_counter_placements(t)
    }
    assert {"plus_one_makers|you|", "has_devour|you|", "sacrifice_outlets|you|"} <= (
        _idents("Thromok the Insatiable")
    )


# ── energy ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["Overclocked Electromancer", "Robobrain War Mind", "The Motherlode, Excavator"],
)
def test_getting_energy_is_an_energy_maker(name):
    """CR 107.14: {E} is one energy counter; "you get X {E}" / "an amount of {E}
    equal to …" makes energy."""
    assert [c.concept for c in _recovered(name)["gain_energy"]] == ["gain_energy"]
    assert "energy_makers|you|" in _idents(name)


@pytest.mark.parametrize(
    ("name", "residue"),
    [
        ("Reiterating Bolt", "unrecognized_clause_head"),
        ("Salvation Colossus", "unknown"),
        ("Izzet Generatorium", "unparsed_condition"),
    ],
)
def test_paying_energy_is_energy_matters(name, residue):
    """CR 107.14: "To pay {E}, a player removes one energy counter from
    themselves" — a cost paid in {E} wants the makers (replicate CR 702.56a,
    unearth 702.84a, Izzet Generatorium's paid-{E} activation condition)."""
    assert static_token(_residue_text(name, residue)) == "energy_payment"
    assert [c.concept for c in _recovered(name)["energy_payment"]] == ["pay_energy"]
    assert ("energy", "matters") in {
        (e.resource, e.side) for t in _trees(name) for e in keyword_resource_events(t)
    }
    assert "energy_matters|you|" in _idents(name)


def test_energy_replacement_is_not_a_maker():
    """Izzet Generatorium's "If you would get one or more {E}, you get that many
    plus one {E} instead" rewards the makers; the seam refuses the replacement,
    so the card is energy_matters (its paid-{E} condition), never a maker."""
    assert "gain_energy" not in _recovered("Izzet Generatorium")
    assert "energy_makers|you|" not in _idents("Izzet Generatorium")


def test_energy_payment_names_energy():
    """Grammar machinery: a payment counts only when it names {E}."""
    assert static_token("Pay {2}: Draw a card") is None
    assert static_token("you may pay {E}{E}") == "energy_payment"


# ── foretell ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["Ethereal Valkyrie", "Karfell Harbinger", "Ranar the Ever-Watchful"],
)
def test_foretell_residues_are_foretell_makers(name):
    """CR 702.143a: foretell — Valkyrie's "Its foretell cost is …" (the card it
    exiles becomes foretold), Karfell's foretell-only mana, Ranar's "costs {0} to
    foretell". Each recovers as a foretell decorated like a cast from exile."""
    (c,) = _recovered(name)["foretell"]
    assert c.concept == "cast_from_zone"
    assert "foretell_makers|you|" in _idents(name)


# ── Treasure: Jetmir's Fixer ──────────────────────────────────────────────────


def test_jetmirs_fixer_cares_about_treasure_mana():
    """Jetmir's Fixer's "If mana from a Treasure was spent to activate this
    ability, put a +1/+1 counter on ~ instead": the residue's recovered reading
    names the Treasure."""
    (c,) = _recovered("Jetmir's Fixer")["place_counter"]
    assert "Treasure" in c.reading
    assert "treasure_matters|you|" in _idents("Jetmir's Fixer")


# ── Superfriends: Tomik's affinity for planeswalkers ─────────────────────────


def test_affinity_for_planeswalkers_is_a_superfriends_payoff():
    """CR 702.41a: "Affinity for [text]" means "This spell costs {1} less to cast
    for each [text] you control" — Tomik wants planeswalkers on your board; an
    affinity for artifacts (Frogmite) says nothing about planeswalkers."""
    (tomik,) = _trees("Tomik, Wielder of Law")
    assert ("Affinity", ("Planeswalker",)) in tomik.card_keyword_types
    assert "superfriends_matters|you|" in _idents("Tomik, Wielder of Law")
    (frogmite,) = _trees("Frogmite")
    assert frogmite.card_keyword_types == (("Affinity", ("Artifact",)),)
    assert "superfriends_matters|you|" not in _idents("Frogmite")


# ── Food: Osteomancer Adept (a bridge row) ────────────────────────────────────


def test_osteomancer_adept_forages_via_its_bridge():
    """CR 701.61a: to forage is to exile three cards from your graveyard or
    sacrifice a Food — a Food payoff. phase drops the cost; the bridge serves it,
    and stands down on a card whose forage parses (a Food sacrifice)."""
    bridge = BRIDGES["forage_cast_permission_cost_dropped"]
    assert any(bridge.fires(t) for t in _trees("Osteomancer Adept"))
    assert not any(bridge.gap(t) for t in _trees("Treetop Sentries"))
    assert "food_matters|you|" in _idents("Osteomancer Adept")


# ── retirement canaries ───────────────────────────────────────────────────────

_PARKED = [
    # (card, phase residue name, the recovered token that reads it, the typed tag
    #  phase would emit for the clause — None where the residue is the only
    #  evidence — and what to delete once phase parses it)
    ("Mask of the Schemer", "where_x_binding", "connive", "Connive", "connive"),
    ("Fall of Cair Andros", "where_x_binding", "amass", "Amass", "amass"),
    (
        "Officious Interrogation",
        "where_x_binding",
        "investigate",
        "Investigate",
        "investigate",
    ),
    ("Thromok the Insatiable", "unknown", "devour", None, "devour"),
    (
        "Overclocked Electromancer",
        "unparsed_quantity",
        "gain_energy",
        "GainEnergy",
        "gain_energy",
    ),
    (
        "Robobrain War Mind",
        "unparsed_verb_arguments",
        "gain_energy",
        "GainEnergy",
        "gain_energy",
    ),
    (
        "The Motherlode, Excavator",
        "unparsed_verb_arguments",
        "gain_energy",
        "GainEnergy",
        "gain_energy",
    ),
    (
        "Reiterating Bolt",
        "unrecognized_clause_head",
        "energy_payment",
        "PayEnergy",
        "energy_payment",
    ),
    ("Salvation Colossus", "unknown", "energy_payment", "PayEnergy", "energy_payment"),
    (
        "Izzet Generatorium",
        "unparsed_condition",
        "energy_payment",
        None,
        "energy_payment",
    ),
    ("Ethereal Valkyrie", "unrecognized_clause_head", "foretell", None, "foretell"),
    ("Karfell Harbinger", "unparsed_verb_arguments", "foretell", None, "foretell"),
    ("Ranar the Ever-Watchful", "static_structure", "foretell", None, "foretell"),
    (
        "Jetmir's Fixer",
        "instead_condition",
        "place_counter",
        "ManaSpentToCast",
        "the recovered-reading arm of lanes.mana_and_wipes._resource_token_matters",
    ),
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "residue", "token", "tag", "workaround"),
    _PARKED,
    ids=[p[0] for p in _PARKED],
)
def test_resource_clause_still_parked_canary(name, residue, token, tag, workaround):
    """phase v0.104.0 parks each clause as the named residue, the recovery token
    reads it, and phase emits no typed node for it. Once phase parses the clause
    (the residue goes, or the typed node arrives), the workaround is spare: the
    allowlist row and its ``crosswalk.reads._RECOVERED_TOKEN_READS`` entry, if no
    other card still needs them."""
    retire = f"{name}: RETIRE-READY — phase now parses its {residue} clause; delete {workaround}"
    assert any(n == residue for n, _ in _residues(name)), retire
    assert token in _recovered(name), retire
    assert tag is None or tag not in _raw_tags(name), retire
