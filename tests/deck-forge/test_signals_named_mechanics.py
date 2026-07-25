"""Tests for the sweep survivors + the named-mechanic long tail.

Rare named mechanics (monarch, energy, the Ring, voting, …) are exactly the novel
build-arounds the tool should surface, and they're precise named anchors so they
stay clean. Each is a real archetype getting its own avenue.

ADR-0039 task #80 step 6 retired the regex engine (``_signals_regex.py``) and the
projected-IR engine (``_signals_ir.py``); every test here now asserts against the
production ``extract_signals`` path via the ``testkit`` real-card fixtures.
Most of this file's original synthetic-fixture coverage is now a duplicate of
``tests/deck-forge/test_signal_keys_real_cards.py``'s ``_REAL_CASES`` table (one
real card per migrated key) and ``tests/mtg-utils/test_crosswalk.py``'s per-key
structural/precision suites — see the deletion notes in the repointing report.
What survives here are the real-card scenarios that exercise a DISTINCT arm or a
multi-signal co-occurrence not already captured by those tables.
"""

from mtg_utils.testkit import test_signals


def _real(name):
    """(key, scope) set over the REAL Scryfall record + REAL projected IR (snapshot)."""
    return {(s.key, s.scope) for s in test_signals(name)}


def test_devotion_and_historic_are_ir_served():
    # historic_matters (CR 700.6) reads STRUCTURE — supplement
    # `_recover_historic_subject` synthesizes the Historic subject Filter for the
    # historic cast-restriction phase drops (Raff Capashen's "cast historic spells as
    # though they had flash"). Distinct arm from
    # test_signal_keys_real_cards.py's own historic_matters representative
    # (Jhoira's Familiar); this is the cast-restriction form, not the cost-borne one.
    assert ("historic_matters", "you") in _real("Raff Capashen, Ship's Mage")


def test_24g_colorless_historic_scaling_read_structure():
    # Three MED-residue lanes read recovered structure off the IR; asserted over
    # real projected IR (test_signals) across DISTINCT structural arms per key —
    # not the single representative card each key's _REAL_CASES entry proves.
    # colorless_matters (CR 105.2c) — _recover_colorless_subject synthesizes a
    # ColorCount:EQ:0 subject Filter for the dropped "colorless" qualifier, across
    # three independent anchors (equip cost-reduce / cast-reduce / counter-target):
    assert ("colorless_matters", "you") in _real("Ghostfire Blade")  # equip cost-reduce
    assert ("colorless_matters", "you") in _real("Ugin, the Ineffable")  # cast-reduce
    assert ("colorless_matters", "you") in _real("Consign to Memory")  # counter-target
    # historic_matters (CR 700.6) — the cost-borne case (Sanctum Spirit's "Discard a
    # historic card" activation cost phase collapses to cost='discard'):
    assert ("historic_matters", "you") in _real("Sanctum Spirit")
    # scaling_pump (CR 613) — _recover_scaling_pump synthesizes a pump Effect with the
    # op='count' operand for the "gets +N/+N for each <X>" scaler phase routes through a
    # board_count / make_token / amount=None pump_target carrier — two distinct routes:
    assert ("scaling_pump", "you") in _real("Karn, Scion of Urza")  # board_count token
    assert ("scaling_pump", "you") in _real("Gold Rush")  # amount=None pump_target
    # Moira Brown's recovered counter-scaler also opens any_counter_matters (the shared
    # recovery legitimately helps the neighbor lane — CR 122.1):
    moira = _real("Moira Brown, Guide Author")
    assert ("scaling_pump", "you") in moira
    assert ("any_counter_matters", "you") in moira


def test_exile_matters_zone_scaler_arm():
    # exile_matters (CR 406) reads STRUCTURE — the `in:exile` zone the supplement
    # stamps on the standing-in-exile P/T scaler ("cards you own in exile" —
    # Cosmogoyf) phase left zoneless. Distinct arm from
    # test_signal_keys_real_cards.py's own exile_matters representative (Mairsil,
    # the Pretender's cast-from-the-exile-pile engine); this is the zone-scaler form.
    assert ("exile_matters", "you") in _real("Cosmogoyf")


def test_kitsa_gets_three_avenues():
    # Real Kitsa, Otterball Elite (snapshot): prowess -> spellslinger, the loot outlet ->
    # discard, and "Copy target instant or sorcery" -> spell_copy, all three firing
    # together off one card (a multi-signal co-occurrence, not just per-key presence).
    keys = {s.key for s in test_signals("Kitsa, Otterball Elite")}
    assert "spellcast_matters" in keys  # prowess -> spellslinger
    assert "discard_makers" in keys  # loot outlet (the MAKER arm, ADR-0034)
    assert "spell_copy_makers" in keys  # copy spells
