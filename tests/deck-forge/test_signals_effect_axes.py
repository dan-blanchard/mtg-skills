"""Every ability is an axis to build around — broad effect-axis detectors so a
commander whose ability is ramp / removal / a team buff / a tutor / etc. surfaces
that direction instead of reading as a value-pile.

Real-card pins run the REAL projected Card IR via ``mtg_utils.testkit``
(``test_signals`` = production hybrid over the real Scryfall record + real sidecar IR).
"""

from mtg_utils.testkit import test_signals

# Card names referenced through the real-card helper below. This table feeds the
# `build-card-snapshot` usage scanner (it parses `_REAL_CASES` dict VALUES, which
# also handles apostrophes — unlike the bare `test_card("…")` literal scan). Keep it
# in sync with the names used below; a missing entry fails loud (KeyError) at test
# time, never silently.
_REAL_CASES: dict[str, str] = {
    "Azami, Lady of Scrolls": "Azami, Lady of Scrolls",
    "Azusa, Lost but Seeking": "Azusa, Lost but Seeking",
    "Dark Deal": "Dark Deal",
    "Eladamri, Lord of Leaves": "Eladamri, Lord of Leaves",
    "Gandalf the White": "Gandalf the White",
    "Heartless Pillage": "Heartless Pillage",
    "Ishai, Ojutai Dragonspeaker": "Ishai, Ojutai Dragonspeaker",
    "Sheoldred, the Apocalypse": "Sheoldred, the Apocalypse",
}


# Real-card (key, scope) sets — the production hybrid path, by name.
def _hyb_ks(name):
    return {(s.key, s.scope) for s in test_signals(name)}


def _hyb_keys(name):
    return {s.key for s in test_signals(name)}


# --- ADR-0027 C3 opponent_discard structural arms, on real cards ---
#
# POP1 (Mind Rot — a bare-Player "target player discards" projects the
# opponent_discard structural arm) is already proven by
# tests/deck-forge/test_migrated_keys.py's `_REAL_CASES["opponent_discard"] =
# "Mind Rot"`. POP7 (Megrim — an opponent-scoped Discarded TRIGGER, disjoint
# from discard_matters) is already proven by
# tests/mtg-utils/test_crosswalk.py::test_discard_matters_opponent_watcher_routes_to_opponent_discard.
# Neither is duplicated here.


def test_pop2_typed_opp_subject_controller_opens_opponent_discard():
    """POP2 — "target opponent discards" folds the effect scope to 'any' (Typed target),
    but the opponent lands on subject.controller=='opp' (Heartless Pillage). The
    discard-LOCAL subject.controller read fires opponent_discard. CR 701.9 / 102.2."""
    assert ("opponent_discard", "opponents") in _hyb_ks("Heartless Pillage")


def test_pop4_each_player_discard_opens_opponent_discard_each():
    """POP4 — a symmetric "each player discards" projects scope 'each' (Dark Deal); the
    'each' scope opens opponent_discard at the 'each' label (it hits opponents). CR
    701.9."""
    assert ("opponent_discard", "each") in _hyb_ks("Dark Deal")


# --- widens of existing keys ---------------------------------------------------
#
# landfall (Azusa), land_creatures_matter (Jolrael), attack_matters (Isshin), and
# second_spell_matters (Erayo) are already proven by real-card pins in
# tests/mtg-utils/test_crosswalk.py (same card + key), so those four are not
# duplicated here. Azusa's landfall widen has no other-file duplicate; keep it.


def test_landfall_widened_for_extra_land_drops():
    # Azusa's extra-land STATIC ("play additional lands") has no structural shape
    # phase carries, so it fires from the kept oracle mirror via the real IR.
    assert "landfall" in _hyb_keys("Azusa, Lost but Seeking")


# --- recognizable axes from the one-off tail ----------------------------------


def test_type_matters_other_x_creatures():
    # Eladamri, Lord of Leaves: "Other Elf creatures have forestwalk." (no "you control")
    # — the real IR opens type_matters:Elf.
    got = {(s.key, s.subject) for s in test_signals("Eladamri, Lord of Leaves")}
    assert ("type_matters", "Elf") in got


def test_type_matters_activated_tribal():
    # Azami, Lady of Scrolls: tribal subtype named in an activated cost ("Tap an untapped
    # Wizard you control"). ADR-0027: type_matters via the real IR.
    assert any(
        s.key == "type_matters" and s.subject == "Wizard"
        for s in test_signals("Azami, Lady of Scrolls")
    )


def test_opponent_cast_matters():
    # opponent_cast_matters is IR-served from the cast_spell trigger scope=opp arm.
    # Ishai, Ojutai Dragonspeaker fires it via the real IR.
    assert ("opponent_cast_matters", "opponents") in _hyb_ks(
        "Ishai, Ojutai Dragonspeaker"
    )


def test_legends_matter_for_cast_legendary():
    # legends_matter is IR-served (the HasSupertype:Legendary subject predicate +
    # a kept word mirror for the cast-legendary refs). Gandalf the White's "cast
    # legendary spells as though they had flash" fires it via the real IR.
    assert "legends_matter" in _hyb_keys("Gandalf the White")


# --- opponent library manipulation / draw punishers -----------------------------
#
# opponent_search_matters (River Song) and the "your own scry is not an opponent
# punisher" precision guard (Matoya) are already proven by
# tests/mtg-utils/test_crosswalk.py::test_opponent_search_matters_trigger_modes.
# Neither is duplicated here.


def test_opponent_draw_punisher():
    # opponent_draw_matters is IR-served from a "drawn" trigger scoped to an
    # opponent. Sheoldred, the Apocalypse ("Whenever an opponent draws a card, they lose
    # 2 life") fires it via the real IR.
    assert ("opponent_draw_matters", "opponents") in _hyb_ks(
        "Sheoldred, the Apocalypse"
    )
