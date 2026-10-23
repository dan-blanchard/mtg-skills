"""The token-maker family's serve specs on the lanes' idents (docs/plans/serve-
idents-and-avenue-support.md §2, the ``token_maker|you|*`` row).

``token_maker`` reads the keyword actions that create a creature token
(``crosswalk.keyword_token_creations``): amass's Army (CR 701.47a: "If you
don't control an Army creature, create a 0/0 black [subtype] Army creature
token"), endure's Spirit (701.63a: "that permanent's controller creates an N/N
white Spirit creature token unless they put N +1/+1 counters on that
permanent") and populate's copy (701.36a: "choose a creature token you control
and create a token that's a copy of that creature token"). With them read, the
six specs that served off ``create … creature token`` ride the wildcard.
"""

import pytest

from mtg_utils._analysis.signal_specs import Serve, spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._card_ir.crosswalk import keyword_token_creations
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record (ADR-0056); ``test_card`` seeds its trees."""
    return test_card(name)


def _ident_serve(key: str, scope: str, *idents: str) -> Serve:
    spec = spec_for(_sig(key, scope))
    assert spec is not None
    assert spec.serve.oracle is None
    for ident in idents:
        assert ident in spec.serve.signal_idents, ident
    return spec.serve


def _token_idents(name: str) -> set[str]:
    return {
        f"{s.key}|{s.scope}|{s.subject}"
        for s in test_signals(name)
        if s.key == "token_maker"
    }


def _creations(name: str) -> set[tuple[str, str]]:
    return {c for t in trees_for(test_card(name)) for c in keyword_token_creations(t)}


# ── the read and the lane ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "creation", "ident"),
    [
        ("Lazotep Plating", ("Amass", "Army"), "token_maker|you|Army"),
        ("Fortress Kin-Guard", ("Endure", "Spirit"), "token_maker|you|Spirit"),
        ("Rootborn Defenses", ("Populate", ""), "token_maker|you|"),
    ],
)
def test_keyword_action_token_makers(name, creation, ident):
    assert creation in _creations(name)
    assert ident in _token_idents(name)


def test_plain_token_maker_still_fires():
    assert _creations("Raise the Alarm") == set()
    assert _token_idents("Raise the Alarm") == {"token_maker|you|Soldier"}


def test_army_reference_is_not_a_token_maker():
    """Grond only asks whether you control an Army; it makes none."""
    assert _creations("Grond, the Gatebreaker") == set()
    assert not _token_idents("Grond, the Gatebreaker")


def test_trostani_discordant_makes_soldiers():
    assert _token_idents("Trostani Discordant") == {"token_maker|you|Soldier"}


def test_opponent_side_tokens_are_not_yours():
    """CR 111.2: the player who creates a token owns and controls it. "Each
    opponent creates …" (an opponent wrapper over a Controller-relative Token)
    is not your token. "Its controller creates …" after an effect that answers
    a permanent (Beast Within's destroy) is the answered player's consolation:
    the lane reads it "opponents", a directed gift it never emits, like an
    opponent-owned target. After exiling a graveyard card (Pharika) it is
    whoever's card you chose, yours included: "any"."""
    assert not _token_idents("Slaughter Specialist")
    assert not _token_idents("Beast Within")
    assert _token_idents("Pharika, God of Affliction") == {"token_maker|any|Snake"}


@pytest.mark.retirement_canary
def test_commence_the_endgame_amass_dropped_canary():
    """phase v0.104.0 folds "then amass Zombies X" into the Draw node's
    description with no ``Amass`` node, so token_maker misses it and the serves
    keep ``amass_makers|you|`` (its keyword-array fallback) in
    ``_TOKEN_MAKER_IDENTS``. Once phase emits the node, the fallback is spare."""
    assert not _creations("Commence the Endgame"), (
        "Commence the Endgame: RETIRE-READY — phase now emits its Amass node"
    )


# ── the serves ────────────────────────────────────────────────────────────────


def test_token_maker_serve_reads_the_keyword_actions():
    serve = _ident_serve(
        "token_maker", "you", "token_maker|you|*", "tokens_matter|you|"
    )
    for name in ("Lazotep Plating", "Fortress Kin-Guard", "Rootborn Defenses"):
        assert serve.matches(_card(name)), name
    assert serve.matches(_card("Raise the Alarm"))
    assert serve.matches(_card("Trostani Discordant"))
    assert not serve.matches(_card("Beast Within"))
    # Token anthems are token payoffs (the regex's second arm).
    assert serve.matches(_card("Intangible Virtue"))
    # The amass clause phase drops reaches the serve through amass_makers.
    assert serve.matches(_card("Commence the Endgame"))
    assert not serve.matches(_card("Wildgrowth Walker"))
    assert not serve.matches(_card("Grond, the Gatebreaker"))
    assert not serve.matches(_card("Slaughter Specialist"))


def test_token_doubling_serve_reads_makers_and_doublers():
    serve = _ident_serve(
        "token_doubling", "you", "token_maker|you|*", "token_doubling|you|"
    )
    assert serve.matches(_card("Doubling Season"))
    assert serve.matches(_card("Parallel Lives"))
    assert serve.matches(_card("Rootborn Defenses"))
    assert not serve.matches(_card("Wildgrowth Walker"))


def test_edict_serve_reads_edicts_and_token_makers():
    serve = _ident_serve(
        "edict_makers",
        "each",
        "token_maker|you|*",
        "edict_makers|each|",
        "edict_makers|opponents|",
    )
    assert serve.matches(_card("Grave Pact"))
    assert serve.matches(_card("Smallpox"))
    assert serve.matches(_card("Fortress Kin-Guard"))
    assert not serve.matches(_card("Slaughter Specialist"))


def test_creatures_matter_serve_reads_the_go_wide_lanes():
    serve = _ident_serve(
        "creatures_matter",
        "you",
        "token_maker|you|*",
        "team_buff|you|",
        "tokens_matter|you|",
        "creatures_matter|you|",
    )
    assert serve.matches(_card("Intangible Virtue"))
    assert serve.matches(_card("Lazotep Plating"))
    # The board-power finisher (the regex's "costs {X} less … power" arm).
    assert serve.matches(_card("Ghalta, Primal Hunger"))
    # A tribe's own grant is the tribal avenue's, not the generic go-wide one.
    assert not serve.matches(_card("Sentinel Sliver"))
    spec = spec_for(_sig("creatures_matter"))
    assert "Creature cost reducers" in {e.label for e in spec.extras}


@pytest.mark.parametrize(
    ("key", "scope"), [("creature_etb", "you"), ("damage_for_each", "any")]
)
def test_creatures_entering_serves(key, scope):
    serve = _ident_serve(
        key, scope, "token_maker|you|*", "cheat_into_play|you|Creature"
    )
    assert serve.matches(_card("Fortress Kin-Guard"))
    assert serve.matches(_card("Rootborn Defenses"))
    assert not serve.matches(_card("Slaughter Specialist"))


def test_creature_etb_serves_reanimation_on_the_main_serve():
    """creature_recursion|you|battlefield separates a reanimation spell from a
    return to hand, so creature_etb serves Reanimate on the main serve and no
    longer carries a Reanimation sub-avenue."""
    spec = spec_for(_sig("creature_etb"))
    assert not [e for e in spec.extras if e.label == "Reanimation"]
    assert spec.serve.matches(_card("Reanimate"))
    assert not spec.serve.matches(_card("Raise Dead"))
