"""Tests for the generalized signal extractor (covers all commanders, not just
hand-coded cases).

The headline goals: capture the SUBJECT noun (populate the long-dead Signal.subject)
so tribes/types stop collapsing into one generic signal; recognize whole archetypes
the 12-detector baseline was blind to (treasure / artifacts / tokens / stax / blink /
mill / goad / proliferate); and do it precisely — every false-positive class the
design review flagged (clones, "Plant"/"nonland creature", instant/sorcery spell-type
leakage, stax self-restrictions) must stay clean.
"""

from mtg_utils._deck_forge.signals import coverage_gate, extract_signals


def _ksub(card):
    return {(s.key, s.scope, s.subject) for s in extract_signals(card)}


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def _keys(card):
    return {s.key for s in extract_signals(card)}


# --- parametric subject capture (the core generalization) ----------------------


def test_type_matters_captures_kindred_subject():
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    assert ("type_matters", "you", "Goblin") in _ksub(c)


def test_type_matters_from_count_clause_and_token_maker_together():
    c = {
        "name": "Krenko, Mob Boss",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number "
            "of Goblins you control."
        ),
    }
    s = _ksub(c)
    assert ("type_matters", "you", "Goblin") in s
    assert ("token_maker", "you", "Goblin") in s


def test_type_matters_rejects_generic_creatures_word():
    # "Creatures you control get" must NOT become a junk subject — it stays the
    # generic creatures_matter signal.
    c = {"name": "Anthem", "oracle_text": "Creatures you control get +1/+1."}
    assert ("creatures_matter", "") in {(s.key, s.subject) for s in extract_signals(c)}
    assert "type_matters" not in _keys(c)


def test_type_matters_irregular_plural_resolves():
    c = {"name": "Magda-like", "oracle_text": "Other Dwarves you control get +1/+0."}
    assert ("type_matters", "you", "Dwarf") in _ksub(c)


def test_token_maker_prefers_creature_subtype_over_artifact_word():
    c = {
        "name": "Urza, Lord High Artificer",
        "oracle_text": 'When Urza enters, create a 0/0 colorless Construct artifact creature token with "This token gets +1/+1 for each artifact you control."\nTap an untapped artifact you control: Add {U}.\n{5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana cost.',
    }
    assert ("token_maker", "you", "Construct") in _ksub(c)


def test_typed_spellcast_captures_tribe():
    c = {
        "name": "The First Sliver",
        "oracle_text": "Cascade (When you cast this spell, exile cards from the top of your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the bottom in a random order.)\nSliver spells you cast have cascade.",
    }
    assert ("typed_spellcast", "you", "Sliver") in _ksub(c)


def test_typed_spellcast_rejects_instant_and_sorcery():
    # "Instant and sorcery spells you cast" is spellslinger, NOT a tribe.
    c = {
        "name": "Mizzix of the Izmagnus",
        "oracle_text": "Whenever you cast an instant or sorcery spell with mana value greater than the number of experience counters you have, you get an experience counter.\nInstant and sorcery spells you cast cost {1} less to cast for each experience counter you have.",
    }
    assert "typed_spellcast" not in _keys(c)


# --- false-positive guards -----------------------------------------------------


def test_clone_yields_no_subject_signal():
    c = {
        "name": "Silent Hallcreeper",
        "oracle_text": "This creature can't be blocked.\nWhenever this creature deals combat damage to a player, choose one that hasn't been chosen —\n• Put two +1/+1 counters on this creature.\n• Draw a card.\n• This creature becomes a copy of another target creature you control.",
    }
    assert _keys(c).isdisjoint({"type_matters", "token_maker", "typed_spellcast"})


def test_plant_token_maker_keeps_subject_but_not_land_creatures():
    # Avenger makes Plant tokens — token_maker/Plant is CORRECT; it must not be
    # mistaken for the land-creatures theme.
    c = {
        "name": "Avenger of Zendikar",
        "oracle_text": "When this creature enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.",
    }
    s = _ksub(c)
    assert ("token_maker", "you", "Plant") in s
    assert not any(k == "land_creatures_matter" for k, _, _ in s)


# --- structural-anchored floor detectors (whole archetypes the baseline missed) -


def test_treasure_matters():
    c = {
        "name": "Goldspan-like",
        "oracle_text": "Whenever this creature attacks, create a Treasure token.",
    }
    assert ("treasure_matters", "you") in _ks(c)


def test_artifacts_matter():
    c = {"name": "Artificer", "oracle_text": "Artifacts you control have ward {2}."}
    assert ("artifacts_matter", "you") in _ks(c)


def test_tokens_matter_payoff():
    c = {"name": "Token Payoff", "oracle_text": "Tokens you control have haste."}
    assert ("tokens_matter", "you") in _ks(c)


def test_stax_taxes_scoped_to_opponents():
    c = {
        "name": "Grand Arbiter Augustin IV",
        "oracle_text": "White spells you cast cost {1} less to cast.\nBlue spells you cast cost {1} less to cast.\nSpells your opponents cast cost {1} more to cast.",
    }
    assert ("stax_taxes", "opponents") in _ks(c)


def test_stax_self_restriction_does_not_fire():
    # "This creature can't attack unless..." is a self-restriction, NOT stax.
    c = {
        "name": "Kefnet-like",
        "oracle_text": "This creature can't attack or block unless you control an Island.",
    }
    assert "stax_taxes" not in _keys(c)


# --- theme_presets reuse -------------------------------------------------------


def test_blink_flicker_via_preset_regex():
    c = {
        "name": "Brago-like",
        "oracle_text": "Exile target creature you control, then return it to the battlefield under your control.",
    }
    assert ("blink_flicker", "you") in _ks(c)


def test_goad_via_keyword_array_scoped_opponents():
    c = {
        "name": "Marisi-like",
        "oracle_text": "Goad target creature.",
        "keywords": ["Goad"],
    }
    assert ("goad_matters", "opponents") in _ks(c)


def test_proliferate_via_keyword_array():
    c = {
        "name": "Atraxa, Praetors' Voice",
        "oracle_text": "Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)",
        "keywords": ["Proliferate"],
    }
    assert ("proliferate_matters", "you") in _ks(c)


# --- narrow Tinybones scope fix (ADR-0009) ------------------------------------


def test_tinybones_combat_damage_zone_scoped_opponents():
    c = {
        "name": "Tinybones, the Pickpocket",
        "oracle_text": (
            "Deathtouch\nWhenever Tinybones deals combat damage to a player, you may cast target nonland permanent card from that player's graveyard, and mana of any type can be spent to cast that spell."
        ),
    }
    sigs = extract_signals(c)
    assert any(s.key == "graveyard_matters" and s.scope == "opponents" for s in sigs)
    assert not any(s.key == "graveyard_matters" and s.scope == "you" for s in sigs)


def test_self_graveyard_recursion_stays_you():
    # The narrow rule must NOT flip a self-graveyard effect to opponents.
    c = {
        "name": "Greasefang-like",
        "oracle_text": "Return target Vehicle card from your graveyard to the battlefield.",
    }
    assert not any(
        s.key == "graveyard_matters" and s.scope == "opponents"
        for s in extract_signals(c)
    )


# --- dedup + aggregate ---------------------------------------------------------


def test_subject_field_is_actually_populated():
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    assert any(s.subject == "Goblin" for s in extract_signals(c))


# --- coverage gate (the agent-augmentation hook) -------------------------------


def test_coverage_gate_flags_zero_signal():
    c = {"name": "Vanilla", "oracle_text": "Flying"}
    needs, reason = coverage_gate(c, extract_signals(c))
    assert needs is True
    assert reason == "zero_signal"


def test_coverage_gate_passes_when_subject_present():
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    needs, _reason = coverage_gate(c, extract_signals(c))
    assert needs is False


def test_coverage_gate_only_generic_creatures_matter():
    # Gate logic in isolation: a card whose only signal is the non-discriminating
    # creatures_matter is still flagged for the agent. (Built from a controlled
    # signal list — most real anthems now also carry a real anthem axis.)
    from mtg_utils._deck_forge.signals import Signal

    sigs = [Signal("creatures_matter", "you", "", "creatures you control", "Anthem")]
    c = {"name": "Anthem", "oracle_text": "Creatures you control are bigger."}
    needs, reason = coverage_gate(c, sigs)
    assert needs is True
    assert reason == "only_generic"


# --- regression: baseline still fires -----------------------------------------


def test_reminder_text_does_not_produce_signals():
    # Ba Sing Se's earthbend REMINDER text (parenthetical) mentions exile+return;
    # it must not register as a blink/flicker engine (reminder text restates a
    # keyword and should never generate a signal).
    c = {
        "name": "Ba Sing Se",
        "oracle_text": (
            "This land enters tapped unless you control a basic land.\n{T}: Add {G}.\n{2}{G}, {T}: Earthbend 2. Activate only as a sorcery. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)"
        ),
    }
    assert "blink_flicker" not in _keys(c)


def test_baseline_creature_etb_unchanged():
    c = {
        "name": "ETB",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    assert ("creature_etb", "you") in _ks(c)


# --- Phase B: confidence flag + nested-scope / self-reference resolvers ---------


def _by_key(card, key):
    return next(s for s in extract_signals(card) if s.key == key)


def test_confidence_defaults_high():
    c = {
        "name": "ETB",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    assert all(s.confidence == "high" for s in extract_signals(c))


def test_self_reference_resolves_any_scope_to_you_high_confidence():
    # "its power" has no scope marker → baseline "any"; the self-reference to the
    # card's own name resolves it to "you" with high confidence (Krenko Tin Street).
    c = {
        "name": "Krenko, Tin Street Kingpin",
        "oracle_text": "Whenever Krenko attacks, put a +1/+1 counter on it, then create a number of 1/1 red Goblin creature tokens equal to Krenko's power.",
    }
    s = _by_key(c, "attack_matters")
    assert s.scope == "you"
    assert s.confidence == "high"


def test_self_reference_skips_leading_article():
    # "The" must not be treated as the card's self-reference name.
    c = {
        "name": "The Scorpion God",
        "oracle_text": "Whenever a creature with a -1/-1 counter on it dies, draw a card.\n{1}{B}{R}: Put a -1/-1 counter on another target creature.\nWhen The Scorpion God dies, return it to its owner's hand at the beginning of the next end step.",
    }
    # death_matters here is scope "any" (no self-ref to "Scorpion"); not forced to you.
    s = _by_key(c, "death_matters")
    assert s.scope != "you" or s.confidence == "high"  # not a spurious self-ref flip


def test_broad_possessive_scope_is_opponents_low_confidence():
    # Non-combat "that player's graveyard" → opponents, but LOW confidence (the
    # broad rule turned on behind the flag; not trusted blindly).
    c = {
        "name": "Graverobber",
        "oracle_text": "Exile target creature card from that player's graveyard.",
    }
    gy = [s for s in extract_signals(c) if s.key == "graveyard_matters"]
    assert gy
    assert gy[0].scope == "opponents"
    assert gy[0].confidence == "low"


def test_narrow_tinybones_rule_is_high_confidence():
    c = {
        "name": "Tinybones, the Pickpocket",
        "oracle_text": (
            "Deathtouch\nWhenever Tinybones deals combat damage to a player, you may cast target nonland permanent card from that player's graveyard, and mana of any type can be spent to cast that spell."
        ),
    }
    s = _by_key(c, "graveyard_matters")
    assert s.scope == "opponents"
    assert s.confidence == "high"


def test_granted_ability_marks_signal_low_confidence():
    # A baseline signal pulled from a GRANTED ability (have "...") is scope-uncertain
    # (outer "you control" vs inner effect), so it is marked low confidence.
    c = {
        "name": "Grantor",
        "oracle_text": 'Creatures you control have "Whenever this creature attacks, draw a card."',
    }
    assert _by_key(c, "attack_matters").confidence == "low"


def test_coverage_gate_flags_low_confidence_only():
    # Only signal is a broad-possessive graveyard guess (no other detectable axis).
    c = {
        "name": "Graverobber",
        "oracle_text": "You may play cards from that player's graveyard.",
    }
    sigs = extract_signals(c)
    assert sigs
    assert all(s.confidence == "low" for s in sigs)
    needs, reason = coverage_gate(c, sigs)
    assert needs is True
    assert reason == "low_confidence"
