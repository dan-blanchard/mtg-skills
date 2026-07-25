"""Dash → Equipment: a rules-grounded synergy from the Dash *keyword* (oracle), not a
bare stats heuristic. Dash returns the creature to hand each end step (CR 702.109a);
Equipment unattaches but stays on the battlefield (CR 301.5c), while Auras go to the
graveyard (CR 704.5m) and +1/+1 counters are lost — so Equipment is the resilient buff
for a recurring haste attacker (Zurgo, Ragavan, Kolaghan). The spec points at
Equipment specifically, NOT generic voltron (Auras are anti-synergistic with Dash).

Key-presence (has_dash fires off the keyword / leaves the deleted regex path) is
proven for the same card by tests/deck-forge/test_migrated_keys.py's _REAL_CASES
table ("has_dash": "Zurgo Bellstriker") via test_migrated_key_left_regex_and_is_ir_served.
This file keeps only the scope assertion and the spec-targeting behavior, which
that parametrized test doesn't cover.
"""

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._deck_forge.signals import Signal
from mtg_utils.testkit import test_signals


def test_dash_scope_is_you():
    sig = next(s for s in test_signals("Zurgo Bellstriker") if s.key == "has_dash")
    assert sig.scope == "you"


def test_no_dash_keyword_no_signal():
    assert "has_dash" not in {s.key for s in test_signals("Grizzly Bears")}


def test_dash_spec_targets_equipment_not_auras():
    sig = Signal("has_dash", "you", "", "", "Zurgo Bellstriker")
    assert spec_for(sig) is not None
    # Equipment serves it (persists across the Dash bounce)…
    assert serves({"oracle_text": "Equipped creature gets +2/+2. Equip {2}"}, sig)
    # …an Aura does NOT (it dies when Zurgo returns to hand, CR 704.5m).
    assert not serves(
        {"oracle_text": "Enchant creature. Enchanted creature gets +2/+2."}, sig
    )
