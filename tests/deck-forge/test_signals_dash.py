"""Dash → Equipment: a rules-grounded synergy from the Dash *keyword* (oracle), not a
bare stats heuristic. Dash returns the creature to hand each end step (CR 702.109a);
Equipment unattaches but stays on the battlefield (CR 301.5c), while Auras go to the
graveyard (CR 704.5m) and +1/+1 counters are lost — so Equipment is the resilient buff
for a recurring haste attacker (Zurgo, Ragavan, Kolaghan). The spec points at
Equipment specifically, NOT generic voltron (Auras are anti-synergistic with Dash).
"""

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Card, Face

# ADR-0027: dash_matters migrated to the Card IR (it now rides the Scryfall `Dash`
# keyword array via _IR_KEYWORD_MAP['dash'], not the regex _DIRECT_KEYWORD_SIGNALS
# path), so the firing tests read the production dispatcher extract_signals_hybrid.
# A bare non-None IR routes the hybrid to the IR path; the Batch-K keyword loop reads
# the record's card['keywords'], so a vanilla IR suffices (mirrors test_migrated_keys).
_BARE_IR = Card(oracle_id="x", name="X", faces=(Face(name="X"),))


def _keys(card):
    return {s.key for s in extract_signals_hybrid(card, _BARE_IR)}


ZURGO = {
    "name": "Zurgo Bellstriker",
    "type_line": "Legendary Creature — Orc Warrior",
    "oracle_text": "Zurgo can't block creatures with power 2 or greater.\nDash {1}{R} (You may cast this spell for its dash cost. If you do, it gains haste, and it's returned from the battlefield to its owner's hand at the beginning of the next end step.)",
    "keywords": ["Dash"],
}


def test_dash_keyword_fires_dash_matters():
    assert "dash_matters" in _keys(ZURGO)


def test_dash_regex_path_no_longer_emits_dash_matters():
    # ADR-0027: the migrated key must leave the legacy regex path entirely.
    assert "dash_matters" not in {s.key for s in extract_signals(ZURGO)}


def test_dash_scope_is_you():
    sig = next(
        s for s in extract_signals_hybrid(ZURGO, _BARE_IR) if s.key == "dash_matters"
    )
    assert sig.scope == "you"


def test_no_dash_keyword_no_signal():
    assert "dash_matters" not in _keys(
        {"name": "X", "oracle_text": "Flying", "keywords": ["Flying"]}
    )


def test_dash_spec_targets_equipment_not_auras():
    sig = Signal("dash_matters", "you", "", "", "Zurgo Bellstriker")
    assert spec_for(sig) is not None
    # Equipment serves it (persists across the Dash bounce)…
    assert serves({"oracle_text": "Equipped creature gets +2/+2. Equip {2}"}, sig)
    # …an Aura does NOT (it dies when Zurgo returns to hand, CR 704.5m).
    assert not serves(
        {"oracle_text": "Enchant creature. Enchanted creature gets +2/+2."}, sig
    )
