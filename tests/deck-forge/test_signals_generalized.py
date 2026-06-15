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


def test_blink_flicker_exile_other_target_then_return():
    # "exile up to one OTHER target [permanent] ... return it/that card to the
    # battlefield" is a blink engine (CR — leaves then re-enters); the cross-sentence
    # detector's optional group only had "another/one", so "one other" slipped past
    # and these read as plain exile_removal. Real cards, full oracle text.
    ennis = {
        "name": "Ennis, Debate Moderator",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": (
            "When Ennis enters, exile up to one other target creature you control. "
            "Return that card to the battlefield under its owner's control at the "
            "beginning of the next end step.\n"
            "At the beginning of your end step, if one or more cards were put into "
            "exile this turn, put a +1/+1 counter on Ennis."
        ),
    }
    koya = {
        "name": "Koya, Death from Above",
        "type_line": "Legendary Creature — Mutant Ninja Bird",
        "oracle_text": (
            "Flying\n"
            "When Koya enters, exile up to one other target creature. At the "
            "beginning of the next end step, you may pay {3}{B}. If you don't, "
            "return that card to the battlefield under its owner's control."
        ),
    }
    phelia = {
        "name": "Phelia, Exuberant Shepherd",
        "type_line": "Legendary Creature — Dog",
        "oracle_text": (
            "Flash\n"
            "Whenever Phelia attacks, exile up to one other target nonland "
            "permanent. At the beginning of the next end step, return that card to "
            "the battlefield under its owner's control. If it entered under your "
            "control, put a +1/+1 counter on Phelia."
        ),
    }
    assert "blink_flicker" in _keys(ennis)
    assert "blink_flicker" in _keys(koya)
    assert "blink_flicker" in _keys(phelia)


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


def test_populate_opens_token_copy_matters():
    # Populate (CR 702.95) IS "create a token that's a copy of a creature token you
    # control" — a token-copy mechanic — so a populate commander opens token_copy_matters
    # (the serve already credited populate; the detector missed the keyword).
    ghired = {
        "name": "Ghired, Conclave Exile",
        "type_line": "Legendary Creature — Human Shaman",
        "oracle_text": (
            "When Ghired enters, create a 4/4 green Rhino creature token with "
            "trample.\nWhenever Ghired attacks, populate. The token enters tapped "
            "and attacking. (To populate, create a token that's a copy of a creature "
            "token you control.)"
        ),
    }
    trostani = {
        "name": "Trostani, Selesnya's Voice",
        "type_line": "Legendary Creature — Dryad",
        "oracle_text": (
            "Whenever another creature you control enters, you gain life equal to "
            "that creature's toughness.\n"
            "{1}{G}{W}, {T}: Populate. (Create a token that's a copy of a creature "
            "token you control.)"
        ),
    }
    assert "token_copy_matters" in _keys(ghired)
    assert "token_copy_matters" in _keys(trostani)


def test_self_death_payoff_opens_for_own_death_trigger():
    # A commander whose OWN "when ~ dies, <value>" is the engine opens self_death_payoff
    # (distinct from aristocrats death_matters — that keys on ANY creature dying). Real
    # cards, full oracle text.
    kokusho = {
        "name": "Kokusho, the Evening Star",
        "type_line": "Legendary Creature — Dragon Spirit",
        "oracle_text": (
            "Flying\n"
            "When Kokusho dies, each opponent loses 5 life. You gain life equal to "
            "the life lost this way."
        ),
    }
    junji = {
        "name": "Junji, the Midnight Sky",
        "type_line": "Legendary Creature — Dragon Spirit",
        "oracle_text": (
            "Flying, menace\n"
            "When Junji dies, choose one —\n"
            "• Each opponent discards two cards and loses 2 life.\n"
            "• Put target non-Dragon creature card from a graveyard onto the "
            "battlefield under your control. You lose 2 life."
        ),
    }
    assert "self_death_payoff" in _keys(kokusho)
    assert "self_death_payoff" in _keys(junji)
    # Over-fire guard: aristocrats (OTHER creatures dying) is NOT a self-death payoff.
    blood_artist = {
        "name": "Blood Artist",
        "type_line": "Creature — Vampire",
        "oracle_text": (
            "Whenever Blood Artist or another creature dies, target player loses 1 "
            "life and you gain 1 life."
        ),
    }
    assert "self_death_payoff" not in _keys(blood_artist)


def test_creature_etb_opens_on_delayed_had_enter_payoff():
    # Ephara rewards creatures entering via a DELAYED check ("at the beginning of
    # upkeep, if you had a creature enter ... last turn, draw") — no "when/whenever"
    # trigger word, so the ETB detector's trigger-word gate missed it. It's an
    # ETB-payoff commander (wants ETB creatures / blink / token makers).
    ephara = {
        "name": "Ephara, God of the Polis",
        "type_line": "Legendary Enchantment Creature — God",
        "oracle_text": (
            "Indestructible\n"
            "As long as your devotion to white and blue is less than seven, Ephara "
            "isn't a creature.\n"
            "At the beginning of each upkeep, if you had another creature enter the "
            "battlefield under your control last turn, draw a card."
        ),
    }
    assert "creature_etb" in _keys(ephara)


def test_artifacts_matter_opens_for_artifact_tutor():
    # Arcum Dagsson tutors artifacts ("search ... for a noncreature artifact card, put
    # it onto the battlefield") and sacs artifact creatures — an artifact commander —
    # but the detector wanted the "artifacts you control" possessive, so it missed him.
    # artifacts_matter already serves artifacts by type, so opening it covers his fodder.
    arcum = {
        "name": "Arcum Dagsson",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": (
            "{T}: Target artifact creature's controller sacrifices it. That player "
            "may search their library for a noncreature artifact card, put it onto "
            "the battlefield, then shuffle."
        ),
    }
    assert "artifacts_matter" in _keys(arcum)
    # Over-fire guard: a generic creature-tutor is not an artifact commander.
    diabolic_tutor = {
        "name": "Tutor Test",
        "type_line": "Legendary Creature — Wizard",
        "oracle_text": "When this creature enters, search your library for a creature card, reveal it, put it into your hand, then shuffle.",
    }
    assert "artifacts_matter" not in _keys(diabolic_tutor)


def test_creature_recursion_opens_and_self_sac_creatures_serve_it():
    # Creature-recursion commanders (return/put a creature card from your graveyard:
    # Hua Tuo, Adun, Othelm) loop SELF-SACRIFICING creatures — the sac is the
    # activation (repeatable value) AND fuels the graveyard for re-recursion, no
    # separate outlet needed (Spore Frog). Real cards, full oracle.
    hua_tuo = {
        "name": "Hua Tuo, Honored Physician",
        "type_line": "Legendary Creature — Human Advisor",
        "oracle_text": (
            "{T}: Put target creature card from your graveyard on top of your "
            "library. Activate only during your turn, before attackers are declared."
        ),
    }
    assert "creature_recursion" in _keys(hua_tuo)
    # Serve: self-sacrificing creatures are the loop fuel.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    spore_frog = {
        "name": "Spore Frog",
        "type_line": "Creature — Frog",
        "oracle_text": "Sacrifice this creature: Prevent all combat damage that would be dealt this turn.",
    }
    assert lane_covers(spore_frog, "creature_recursion") is True
    # Over-fire guard: a vanilla creature is not loop fuel.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert lane_covers(bear, "creature_recursion") is False


def test_self_etb_value_matches_whenever_and_plural_enter():
    # A self-ETB-value commander wants blink + ETB-trigger doublers (Panharmonicon).
    # The detector used "\bwhen " (missing "WHENEVER ~ enters" — Roxanne) and "enters"
    # (missing plural "enter"). Real card, full oracle.
    roxanne = {
        "name": "Roxanne, Starfall Savant",
        "type_line": "Legendary Creature — Cat Druid",
        "oracle_text": (
            "Whenever Roxanne enters or attacks, create a tapped colorless artifact "
            'token named Meteorite with "When this token enters, it deals 2 damage '
            'to any target" and "{T}: Add one mana of any color."\n'
            "Whenever you tap an artifact token for mana, add one mana of any type "
            "that artifact token produced."
        ),
    }
    assert "blink_flicker" in _keys(roxanne)


def test_self_etb_value_resolves_short_name_not_just_first_token():
    # The self-reference in oracle is the name BEFORE the comma (the short name), which
    # may be hyphenated, two-named, or multi-word — not the bare first token. The
    # detector keyed only on the first token immediately before "enters", so
    # "When Spider-Byte enters" / "When Donnie & April enter" / "When Black Cat enters"
    # all missed (the first token is followed by more name, not " enters"). A self-ETB
    # commander wants blink + ETB-trigger doublers (Panharmonicon). Real cards.
    spider_byte = {
        "name": "Spider-Byte, Web Warden",
        "type_line": "Legendary Creature — Spider",
        "oracle_text": (
            "When Spider-Byte enters, return up to one target nonland permanent to "
            "its owner's hand."
        ),
    }
    donnie_april = {
        "name": "Donnie & April, Adorkable Duo",
        "type_line": "Legendary Creature — Mutant Turtle",
        "oracle_text": (
            "When Donnie & April enter, choose one or both. Each mode must target a "
            "different player.\n• Target player draws two cards.\n• Target player "
            "returns an artifact, instant, or sorcery card from their graveyard to "
            "their hand."
        ),
    }
    black_cat = {
        "name": "Black Cat, Cunning Thief",
        "type_line": "Legendary Creature — Cat",
        "oracle_text": (
            "When Black Cat enters, look at the top nine cards of target opponent's "
            "library, exile two of them face down, then put the rest on the bottom of "
            "their library in a random order."
        ),
    }
    assert "blink_flicker" in _keys(spider_byte)
    assert "blink_flicker" in _keys(donnie_april)
    assert "blink_flicker" in _keys(black_cat)


def test_self_dies_value_resolves_short_name_for_clone():
    # A high-CMC commander with a self DIES trigger is worth cloning — a token copy
    # re-fires the trigger when the copy dies. The clone detector keyed on the first
    # name token before "dies", so "When The Scarab God dies" missed ("The" is an
    # article, "Scarab" is followed by " God", not " dies"). Real cards, cmc>=5, no ETB
    # (so the clone signal comes from the DIES path, not the ETB path).
    scarab = {
        "name": "The Scarab God",
        "type_line": "Legendary Creature — God",
        "cmc": 5.0,
        "oracle_text": (
            "At the beginning of your upkeep, each opponent loses X life and you scry "
            "X, where X is the number of Zombies you control.\n"
            "{2}{U}{B}: Exile target creature card from a graveyard. Create a token "
            "that's a copy of it, except it's a 4/4 black Zombie.\n"
            "When The Scarab God dies, return it to its owner's hand at the beginning "
            "of the next end step."
        ),
    }
    locust = {
        "name": "The Locust God",
        "type_line": "Legendary Creature — God",
        "cmc": 6.0,
        "oracle_text": (
            "Flying\nWhenever you draw a card, create a 1/1 blue and red Insect "
            "creature token with flying and haste.\n{2}{U}{R}: Draw a card, then "
            "discard a card.\nWhen The Locust God dies, return it to its owner's hand "
            "at the beginning of the next end step."
        ),
    }
    assert "clone_matters" in _keys(scarab)
    assert "clone_matters" in _keys(locust)


def test_self_counter_accumulator_opens_counters_matter():
    # A commander that puts +1/+1 counters on ITSELF and cares about its COUNT
    # (Sab-Sunen — "number of counters on it") is a +1/+1-counters commander; it should
    # open counters_matter (counter sources/proliferate). The 2-condition check
    # (accumulates AND cares about count) excludes incidental self-counter creatures
    # (Thraximundar gets a counter but doesn't care about the count).
    sab_sunen = {
        "name": "Sab-Sunen, Luxa Embodied",
        "type_line": "Legendary Creature — God",
        "oracle_text": (
            "Reach, trample, indestructible\n"
            "Sab-Sunen can't attack or block unless it has an even number of counters "
            "on it. (Zero is even.)\n"
            "At the beginning of your first main phase, put a +1/+1 counter on "
            "Sab-Sunen. Then if it has an odd number of counters on it, draw two cards."
        ),
    }
    assert "counters_matter" in _keys(sab_sunen)
    # Over-fire guard (generic fixture): accumulates a counter but no count-caring.
    incidental = {
        "name": "Incidental Counter Attacker",
        "type_line": "Legendary Creature — Zombie",
        "oracle_text": (
            "Whenever a player sacrifices a creature, you may put a +1/+1 counter on "
            "this creature."
        ),
    }
    assert "counters_matter" not in _keys(incidental)


def test_role_token_makers_open_enchantments_matter():
    # Role tokens are Aura ENCHANTMENTS (CR), so a commander that makes them (Gylwain,
    # Ellivere) is an enchantment commander — it wants enchantment-count payoffs
    # (Sanctum Weaver) and Aura payoffs. The detector keyed on "enchantment"/"aura"
    # and missed the word "Role".
    gylwain = {
        "name": "Gylwain, Casting Director",
        "type_line": "Legendary Creature — Elf Druid",
        "oracle_text": (
            "Whenever Gylwain or another nontoken creature you control enters, "
            "choose one —\n"
            "• Create a Royal Role token attached to that creature.\n"
            "• Create a Sorcerer Role token attached to that creature.\n"
            "• Create a Monster Role token attached to that creature."
        ),
    }
    assert "enchantments_matter" in _keys(gylwain)
    # Over-fire guard: a plain creature-token maker is not an enchantment deck.
    krenko = {
        "name": "Token Maker",
        "type_line": "Legendary Creature — Goblin",
        "oracle_text": "{T}: Create a 1/1 red Goblin creature token.",
    }
    assert "enchantments_matter" not in _keys(krenko)
