"""Iteration-3 recast-loop lanes (mining-2 synthesis, lane-gap batch).

The v2-panel mining sweep's biggest un-priced miss cluster: one-shot ETB
value permanents under commanders that repeatably re-deliver them
(Muldrotha's 13-card cluster, Meren's re-arm trio, Chulane's bounce
package). Enters triggers fire on EVERY entry (CR 603.6a), so the pair is
(one-shot clause) x (recasts per game).

* self_etb_payload — a self-ETB trigger whose payload is a VALUE concept
  (destroy / draw / sacrifice / damage / discard / mill / tutor / exile):
  Shriekmaw, Mulldrifter, Fleshbag Marauder. Wider than wants_cloning's
  clone-worthy gate (has_self_etb_value), which stays untouched.

Every case runs the production ``extract_signals_hybrid`` over the REAL
committed-snapshot IR (ADR-0027/0039) — no synthetic trees.
"""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_card_ir, test_signals


def _idents_of(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Shriekmaw", True),  # ETB destroy (the removal half v1 missed)
        ("Ravenous Chupacabra", True),  # ETB destroy
        ("Reclamation Sage", True),  # ETB artifact/enchantment destroy
        ("Mulldrifter", True),  # ETB draw
        ("Fleshbag Marauder", True),  # ETB edict sacrifice
        ("Acidic Slime", True),  # ETB destroy
        ("Grizzly Bears", False),  # no ETB trigger at all
        ("Impact Tremors", False),  # ETB OBSERVER, not a self-ETB carrier
    ],
)
def test_self_etb_payload_emission(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    assert ("self_etb_payload|you|" in _idents_of(name)) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Arm 1: graveyard-cast permission static.
        ("Muldrotha, the Gravetide", True),
        # Arm 2: reanimation trigger (graveyard target -> battlefield).
        ("Meren of Clan Nel Toth", True),
        ("Sun Titan", True),
        # Arm 3: activated self-bounce toward replay.
        ("Chulane, Teller of Tales", True),
        # Not recast engines.
        ("Krenko, Mob Boss", False),
        ("Talrand, Sky Summoner", False),
    ],
)
def test_permanent_recast_emission(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    assert ("permanent_recast|you|" in _idents_of(name)) is expected


def test_recast_row_fires_and_gates():
    from mtg_utils._deck_forge.pair_reads import build_pair_context, pair_score
    from mtg_utils.testkit import test_card

    def ctx(commander):
        test_card_ir(commander)
        return build_pair_context([test_card(commander)], [])

    # Shriekmaw x Muldrotha: the loop the mining sweep named first.
    test_card_ir("Shriekmaw")
    _s, rows = pair_score(test_card("Shriekmaw"), ctx("Muldrotha, the Gravetide"))
    assert any(r["pair"] == "etb_value_x_recast_commander" for r in rows), rows
    # Mulldrifter x Meren: reanimation arm.
    test_card_ir("Mulldrifter")
    _s2, rows2 = pair_score(test_card("Mulldrifter"), ctx("Meren of Clan Nel Toth"))
    assert any(r["pair"] == "etb_value_x_recast_commander" for r in rows2), rows2
    # No recast anchor -> no row.
    _s3, rows3 = pair_score(test_card("Shriekmaw"), ctx("Krenko, Mob Boss"))
    assert not any(r["pair"] == "etb_value_x_recast_commander" for r in rows3), rows3


# ── iteration-4: own-target spells (Feather's miss file) ─────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ephemerate", True),  # "target creature you control"
        ("Feat of Resistance", True),
        ("Fall of the Hammer", True),  # first target is your own creature
        ("Murder", False),  # any-target removal
        # 4b widening: a beneficial targeted pump is own-directed in
        # practice (the strict arm alone left Feather's top-250 flat).
        ("Infuriate", True),
        ("Defiant Strike", True),
        ("Shock", False),  # targeted damage, not a pump
    ],
)
def test_own_target_spell_emission(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    assert ("own_target_spell|you|" in _idents_of(name)) is expected


def test_own_target_row_fires_and_gates():
    from mtg_utils._deck_forge.pair_reads import build_pair_context, pair_score
    from mtg_utils.testkit import test_card

    test_card_ir("Feather, the Redeemed")
    ctx = build_pair_context([test_card("Feather, the Redeemed")], [])
    test_card_ir("Ephemerate")
    _s, rows = pair_score(test_card("Ephemerate"), ctx)
    assert any(r["pair"] == "own_target_spell_x_rebate_commander" for r in rows), rows
    test_card_ir("Krenko, Mob Boss")
    ctx2 = build_pair_context([test_card("Krenko, Mob Boss")], [])
    _s2, rows2 = pair_score(test_card("Ephemerate"), ctx2)
    assert not any(r["pair"] == "own_target_spell_x_rebate_commander" for r in rows2), (
        rows2
    )
