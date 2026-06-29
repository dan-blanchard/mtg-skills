"""The target-bracket constraint gate (ADR-0030).

Compares a deck's bracket-defining elements against a CHOSEN target bracket's
official WotC allowances and reports violations. Distinct from
``deck_stats.detect_bracket``, which infers the deck's NATURAL bracket from the
same signals; this gate measures the deck against a target the builder picked.
"""

from mtg_utils._tuner.bracket import bracket_gate


def _gc(name):
    return {"name": name, "game_changer": True, "oracle_text": "", "type_line": "X"}


def _mld(name):
    return {"name": name, "oracle_text": "Destroy all lands.", "type_line": "Sorcery"}


def _plain(name):
    return {"name": name, "oracle_text": "Draw a card.", "type_line": "Sorcery"}


def _extra_turn(name):
    return {
        "name": name,
        "oracle_text": "Take an extra turn after this one.",
        "type_line": "Sorcery",
    }


def test_winter_orb_untap_lock_is_mass_land_denial():
    # Winter Orb is the canonical untap-lock mass land denial the detector comment
    # explicitly names, but the regex only matched "lands don't untap", missing the
    # "can't untap more than one land" templating — so a Winter Orb deck could PASS a
    # deterministic FAIL axis at bracket 2.
    winter_orb = {
        "name": "Winter Orb",
        "type_line": "Artifact",
        "oracle_text": (
            "As long as Winter Orb is untapped, players can't untap more than one land "
            "during their untap steps."
        ),
    }
    result = bracket_gate([winter_orb, _plain("x")], target_bracket=2)
    mld = [v for v in result["violations"] if v["axis"] == "mass_land_denial"]
    assert mld
    assert mld[0]["severity"] == "FAIL"
    assert "Winter Orb" in mld[0]["cards"]


def test_loses_the_game_two_card_combo_fails_below_bracket_three():
    # A 2-card "each opponent loses the game" kill is an infinite/game-ending combo, but
    # _is_infinite only matched "infinite"/"win the game", missing the loss-side feature.
    combos = {
        "combos": [
            {
                "cards": ["Piece A", "Piece B"],
                "result": ["Each opponent loses the game"],
            }
        ]
    }
    result = bracket_gate([_plain("a"), _plain("b")], target_bracket=2, combos=combos)
    two = [v for v in result["violations"] if v["axis"] == "two_card_combo"]
    assert two
    assert two[0]["severity"] == "FAIL"


def test_multi_extra_turn_card_detected_at_exhibition():
    # Time Stretch ("Take two extra turns after this one") is an extra-turn card, but the
    # regex only matched "an extra turn" — so a B1 deck could PASS holding it.
    time_stretch = {
        "name": "Time Stretch",
        "type_line": "Sorcery",
        "oracle_text": "Take two extra turns after this one.",
    }
    result = bracket_gate([time_stretch, _plain("x")], target_bracket=1)
    ext = [v for v in result["violations"] if v["axis"] == "extra_turns"]
    assert ext
    assert ext[0]["severity"] == "FAIL"
    assert "Time Stretch" in ext[0]["cards"]


class TestGameChangersAxis:
    def test_game_changer_over_core_ceiling_fails(self):
        # Bracket 2 (Core) allows 0 Game Changers; one present is a FAIL naming it.
        result = bracket_gate([_gc("Smothering Tithe"), _plain("x")], target_bracket=2)
        assert result["pass"] is False
        gc = [v for v in result["violations"] if v["axis"] == "game_changers"]
        assert len(gc) == 1
        assert gc[0]["severity"] == "FAIL"
        assert "Smothering Tithe" in gc[0]["cards"]

    def test_clean_core_deck_passes(self):
        result = bracket_gate([_plain("a"), _plain("b")], target_bracket=2)
        assert result["pass"] is True
        assert result["violations"] == []

    def test_three_game_changers_pass_at_upgraded(self):
        # Bracket 3 (Upgraded) allows up to 3 Game Changers.
        result = bracket_gate([_gc(f"G{i}") for i in range(3)], target_bracket=3)
        assert result["pass"] is True

    def test_fourth_game_changer_fails_at_upgraded(self):
        result = bracket_gate([_gc(f"G{i}") for i in range(4)], target_bracket=3)
        gc = [v for v in result["violations"] if v["axis"] == "game_changers"]
        assert gc
        assert gc[0]["severity"] == "FAIL"
        # Only the excess over the ceiling is named.
        assert len(gc[0]["cards"]) == 1


class TestMassLandDenialAxis:
    def test_mass_land_denial_fails_below_bracket_four(self):
        result = bracket_gate([_mld("Armageddon"), _plain("x")], target_bracket=3)
        mld = [v for v in result["violations"] if v["axis"] == "mass_land_denial"]
        assert mld
        assert mld[0]["severity"] == "FAIL"
        assert "Armageddon" in mld[0]["cards"]


class TestExtraTurnsAxis:
    def test_extra_turn_fails_at_exhibition(self):
        # Bracket 1 disallows extra-turn cards entirely.
        result = bracket_gate([_extra_turn("Time Warp"), _plain("x")], target_bracket=1)
        ext = [v for v in result["violations"] if v["axis"] == "extra_turns"]
        assert ext
        assert ext[0]["severity"] == "FAIL"
        assert "Time Warp" in ext[0]["cards"]

    def test_single_extra_turn_passes_at_core(self):
        # Bracket 2 allows extra-turn cards in low quantity — one is fine.
        result = bracket_gate([_extra_turn("Time Warp"), _plain("x")], target_bracket=2)
        assert not [v for v in result["violations"] if v["axis"] == "extra_turns"]

    def test_multiple_extra_turns_warn_at_core(self):
        # Several extra-turn cards is the "not low quantity / chained" risk → WARN.
        loaded = [_extra_turn("Time Warp"), _extra_turn("Temporal Manipulation")]
        result = bracket_gate(loaded, target_bracket=2)
        ext = [v for v in result["violations"] if v["axis"] == "extra_turns"]
        assert ext
        assert ext[0]["severity"] == "WARN"
        # A WARN is advisory — it surfaces but does not fail the gate.
        assert result["pass"] is True


def _card(name, cmc):
    return {"name": name, "cmc": cmc, "oracle_text": "", "type_line": "Creature"}


class TestTwoCardComboAxis:
    def test_two_card_infinite_combo_fails_below_upgraded(self):
        # Brackets 1-2 disallow intentional two-card infinite combos entirely.
        combos = {
            "combos": [
                {
                    "cards": ["Kiki-Jiki", "Restoration Angel"],
                    "result": "Infinite tokens",
                }
            ]
        }
        result = bracket_gate([_plain("x")], target_bracket=2, combos=combos)
        c = [v for v in result["violations"] if v["axis"] == "two_card_combo"]
        assert c
        assert c[0]["severity"] == "FAIL"
        assert "Kiki-Jiki" in c[0]["cards"]

    def test_cheap_combo_warns_at_upgraded(self):
        # Bracket 3 permits a two-card combo only if it isn't cheap-and-early.
        records = [_card("A", 2), _card("B", 3)]  # combined MV 5 → cheap
        combos = {"combos": [{"cards": ["A", "B"], "result": "Infinite mana"}]}
        result = bracket_gate(records, target_bracket=3, combos=combos)
        c = [v for v in result["violations"] if v["axis"] == "two_card_combo"]
        assert c
        assert c[0]["severity"] == "WARN"
        assert result["pass"] is True  # WARN is advisory

    def test_expensive_combo_allowed_at_upgraded(self):
        records = [_card("A", 5), _card("B", 6)]  # combined MV 11 → late-game, fine
        combos = {"combos": [{"cards": ["A", "B"], "result": "Infinite mana"}]}
        result = bracket_gate(records, target_bracket=3, combos=combos)
        assert not [v for v in result["violations"] if v["axis"] == "two_card_combo"]

    def test_no_combos_argument_is_safe(self):
        result = bracket_gate([_plain("a")], target_bracket=2, combos=None)
        assert not [v for v in result["violations"] if v["axis"] == "two_card_combo"]

    def test_three_card_combo_not_flagged(self):
        combos = {"combos": [{"cards": ["A", "B", "C"], "result": "Infinite"}]}
        result = bracket_gate([_plain("a")], target_bracket=2, combos=combos)
        assert not [v for v in result["violations"] if v["axis"] == "two_card_combo"]

    def test_list_shaped_result_is_handled(self):
        # combo_search emits `result` as a LIST of feature strings (the real
        # Commander Spellbook shape), not a string. bracket_gate must not crash
        # and must still detect the infinite outcome.
        combos = {
            "combos": [
                {
                    "cards": ["A", "B"],
                    "result": ["Infinite colorless mana", "Infinite storm count"],
                }
            ]
        }
        result = bracket_gate(
            [_card("A", 2), _card("B", 2)], target_bracket=2, combos=combos
        )
        c = [v for v in result["violations"] if v["axis"] == "two_card_combo"]
        assert c
        assert c[0]["severity"] == "FAIL"


class TestUnconstrainedBrackets:
    def test_optimized_short_circuits_to_pass(self):
        # Bracket 4 is banned-list only — Game Changers + mass land denial are fine.
        loaded = [_gc(f"G{i}") for i in range(6)] + [_mld("Armageddon")]
        result = bracket_gate(loaded, target_bracket=4)
        assert result["pass"] is True
        assert result["violations"] == []

    def test_cedh_short_circuits_to_pass(self):
        result = bracket_gate([_gc("Mana Crypt"), _mld("Armageddon")], target_bracket=5)
        assert result["pass"] is True
