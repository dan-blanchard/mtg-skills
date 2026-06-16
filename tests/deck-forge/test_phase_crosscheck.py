"""Tests for the phase-rs ↔ deck-forge detector cross-check harness.

phase-rs is not installed in CI, so the phase-side fixtures here are hand-built
to mirror phase v0.1.19's serialized ``card-data.json`` shape (a flattened
``CardFace``):

  * ``abilities[].effect.type``     = Effect discriminant (serde ``tag="type"``,
                                      PascalCase variant name, e.g. ``"Token"``)
  * ``triggers[].mode``             = TriggerMode (bare PascalCase string)
  * ``triggers[].execute``          = nested AbilityDefinition (its own effect)
  * ``static_abilities[].mode``     = StaticMode (``"Flying"`` for unit variants,
                                      ``{"ReduceCost": {...}}`` for data variants)
  * ``keywords``                    = list of keyword strings
  * ``scryfall_oracle_id``          = the join key to our Scryfall bulk
  * ``parse_warnings``              = non-empty when phase's parse was incomplete

The deck-forge-side card fixtures carry REAL oracle text so ``extract_signals``
fires for real (per the repo's real-card-props testing rule).
"""

import json

from mtg_utils._deck_forge import phase_crosscheck as pc

# ── phase_tags: project a phase face record to normalized mechanic tags ───────


def test_phase_tags_collects_effect_kind_from_ability():
    record = {
        "name": "Elvish Mystic",
        "oracle_text": "{T}: Add {G}.",
        "abilities": [{"kind": "Mana", "effect": {"type": "Mana", "value": {}}}],
    }
    assert "effect:mana" in pc.phase_tags(record)


def test_phase_tags_collects_trigger_mode_and_nested_effect():
    record = {
        "name": "Attack Token Maker",
        "triggers": [
            {
                "mode": "Attacks",
                "execute": {"kind": "Token", "effect": {"type": "Token", "value": {}}},
            }
        ],
    }
    tags = pc.phase_tags(record)
    assert "trigger:attacks" in tags
    assert "effect:token" in tags


def test_phase_tags_static_unit_and_data_variants():
    record = {
        "static_abilities": [
            {"mode": "Flying"},
            {"mode": {"ReduceCost": {"amount": 1}}},
        ],
    }
    tags = pc.phase_tags(record)
    assert "static:flying" in tags
    assert "static:reducecost" in tags


def test_phase_tags_keywords():
    tags = pc.phase_tags({"keywords": ["Flying", "Trample"]})
    assert "kw:flying" in tags
    assert "kw:trample" in tags


def test_phase_tags_drops_structural_keys_and_subtype_noise():
    # A cost field named "mana" must NOT become effect:mana (key collision with
    # the Mana EffectKind), and target-filter subtype/type strings must not leak.
    record = {
        "abilities": [
            {
                "kind": "Activated",
                "effect": {"type": "Draw", "value": {"amount": 2}},
                "cost": {"mana": "{2}"},
            }
        ],
        "triggers": [
            {"mode": "Drawn", "valid_card": {"subtype": "Goblin", "type": "Creature"}}
        ],
    }
    tags = pc.phase_tags(record)
    assert "effect:draw" in tags
    assert "trigger:drawn" in tags
    assert "effect:mana" not in tags  # the "mana" cost KEY must not leak
    assert not any(t.endswith((":goblin", ":creature")) for t in tags)


# ── classify_card: three-way verdict per crosswalk lane ───────────────────────


def test_classify_both_when_detector_and_phase_agree():
    crosswalk = {"token_maker": frozenset({"effect:token"})}
    out = pc.classify_card({"token_maker"}, {"effect:token"}, crosswalk)
    assert out == {"token_maker": pc.BOTH}


def test_classify_detector_only_when_phase_silent():
    crosswalk = {"token_maker": frozenset({"effect:token"})}
    out = pc.classify_card({"token_maker"}, set(), crosswalk)
    assert out == {"token_maker": pc.DETECTOR_ONLY}


def test_classify_phase_only_when_detector_silent():
    crosswalk = {"lifegain_matters": frozenset({"trigger:lifegained"})}
    out = pc.classify_card(set(), {"trigger:lifegained"}, crosswalk)
    assert out == {"lifegain_matters": pc.PHASE_ONLY}


def test_classify_omits_lanes_neither_side_touches():
    crosswalk = {"token_maker": frozenset({"effect:token"})}
    assert pc.classify_card(set(), set(), crosswalk) == {}


# ── crosscheck_corpus: join by oracle_id, tally, surface gaps ─────────────────


def test_corpus_joins_by_oracle_id_and_tallies_both():
    # Real card: Adeline fires token_maker; phase record makes a Token on attack.
    card = {
        "name": "Adeline, Resplendent Cathar",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "Vigilance\nWhenever you attack, for each opponent, create a 1/1 white "
            "Human creature token that's tapped and attacking that player or a "
            "planeswalker they control.\nAdeline, Resplendent Cathar's power is "
            "equal to the number of creatures you control."
        ),
        "oracle_id": "oid-adeline",
    }
    phase_index = {
        "oid-adeline": {
            "name": "Adeline, Resplendent Cathar",
            "scryfall_oracle_id": "oid-adeline",
            "triggers": [
                {
                    "mode": "YouAttack",
                    "execute": {"effect": {"type": "Token", "value": {}}},
                }
            ],
        }
    }
    crosswalk = {"token_maker": frozenset({"effect:token"})}
    report = pc.crosscheck_corpus([card], phase_index, crosswalk=crosswalk)
    assert report["joined"] == 1
    assert report["lanes"]["token_maker"]["both"] == 1
    assert (
        "Adeline, Resplendent Cathar"
        in report["lanes"]["token_maker"]["examples"]["both"]
    )


def test_corpus_skips_card_without_oracle_id_or_phase_record():
    cards = [
        {"name": "No OID", "oracle_text": "Draw a card."},
        {"name": "Not In Phase", "oracle_text": "Draw a card.", "oracle_id": "x"},
    ]
    report = pc.crosscheck_corpus(cards, {}, crosswalk={})
    assert report["joined"] == 0
    assert report["skipped"]["no_oracle_id"] == 1
    assert report["skipped"]["not_in_phase"] == 1


def test_corpus_excludes_low_confidence_phase_parses_when_asked():
    card = {"name": "C", "oracle_text": "Draw a card.", "oracle_id": "oid-c"}
    phase_index = {
        "oid-c": {"scryfall_oracle_id": "oid-c", "parse_warnings": ["unparsed clause"]}
    }
    report = pc.crosscheck_corpus(
        [card], phase_index, crosswalk={}, include_low_confidence=False
    )
    assert report["joined"] == 0
    assert report["skipped"]["low_confidence"] == 1


def test_corpus_surfaces_unmapped_phase_tags():
    card = {"name": "C", "oracle_text": "Draw a card.", "oracle_id": "oid-c"}
    phase_index = {
        "oid-c": {
            "scryfall_oracle_id": "oid-c",
            "abilities": [{"effect": {"type": "Surveil", "value": {}}}],
        }
    }
    report = pc.crosscheck_corpus([card], phase_index, crosswalk={})
    assert report["unmapped_phase_tags"].get("effect:surveil") == 1


# ── render_report + load_cards + main (CLI driver) ────────────────────────────


def test_render_report_shows_lane_verdicts_and_join_stats():
    report = {
        "lanes": {
            "token_maker": {
                "both": 3,
                "detector_only": 1,
                "phase_only": 2,
                "examples": {"phase_only": ["Foo", "Bar"]},
            }
        },
        "joined": 6,
        "skipped": {"no_oracle_id": 0, "not_in_phase": 1, "low_confidence": 0},
        "unmapped_detector_lanes": {"some_lane": 4},
        "unmapped_phase_tags": {"effect:surveil": 2},
    }
    md = pc.render_report(report)
    assert "token_maker" in md
    assert "6" in md  # joined count
    assert "phase_only" in md or "PHASE_ONLY" in md.upper()
    assert "Foo" in md  # an example name is surfaced


def test_load_cards_flattens_parsed_deck_shape(tmp_path):
    deck = {
        "commanders": [{"name": "Cmd", "oracle_text": "x", "oracle_id": "1"}],
        "cards": [{"name": "Spell", "oracle_text": "y", "oracle_id": "2"}],
        "sideboard": [],
    }
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(deck))
    cards = pc.load_cards(path)
    names = {c["name"] for c in cards}
    assert names == {"Cmd", "Spell"}


def test_load_cards_accepts_plain_list(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text(json.dumps([{"name": "A"}, {"name": "B"}]))
    assert {c["name"] for c in pc.load_cards(path)} == {"A", "B"}


def test_main_runs_end_to_end_and_writes_markdown(tmp_path, capsys):
    cards = [
        {
            "name": "Token Guy",
            "oracle_text": "When Token Guy enters, create a 1/1 white Soldier creature token.",
            "oracle_id": "oid-1",
        }
    ]
    phase = {
        "tokenguy": {
            "scryfall_oracle_id": "oid-1",
            "abilities": [{"effect": {"type": "Token", "value": {}}}],
        }
    }
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps(cards))
    phase_path = tmp_path / "card-data.json"
    phase_path.write_text(json.dumps(phase))

    rc = pc.main([str(cards_path), "--phase-data", str(phase_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "token_maker" in out
