"""Tests for signal specs: how a signal maps to cards that FEED it.

Headline guard: a card that feeds an *opponents'-graveyard* signal must mill
opponents, not yourself. Self-mill must NOT register as serving it.
"""

from mtg_utils._deck_forge.signal_specs import search_filters, serves, spec_for
from mtg_utils._deck_forge.signals import Signal


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


SELF_MILL = {
    "name": "Self Mill",
    "oracle_text": "Put the top four cards of your library into your graveyard.",
}
OPPONENT_MILL = {
    "name": "Mind Grind",
    "oracle_text": "Each opponent mills four cards.",
}
TOKEN_MAKER = {
    "name": "Token Maker",
    "oracle_text": "Create three 1/1 white Soldier creature tokens.",
}
BURN = {"name": "Bolt", "oracle_text": "Bolt deals 3 damage to any target."}
LIFEGAIN = {"name": "Healer", "oracle_text": "You gain 4 life."}


def test_opponents_graveyard_signal_served_by_opponent_mill_not_self_mill():
    sig = _sig("graveyard_matters", "opponents")
    assert serves(OPPONENT_MILL, sig) is True
    assert serves(SELF_MILL, sig) is False


def test_your_graveyard_signal_served_by_self_mill():
    sig = _sig("graveyard_matters", "you")
    assert serves(SELF_MILL, sig) is True


def test_creature_etb_served_by_token_maker_not_burn():
    sig = _sig("creature_etb", "you")
    assert serves(TOKEN_MAKER, sig) is True
    assert serves(BURN, sig) is False


def test_lifegain_served_by_lifegain_card():
    assert serves(LIFEGAIN, _sig("lifegain_matters", "you")) is True


def test_spec_for_returns_label_and_avenue():
    spec = spec_for(_sig("creature_etb", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue


def test_search_filters_inject_color_identity_and_format():
    filters = search_filters(
        _sig("creature_etb", "you"), color_identity="GW", fmt="commander"
    )
    assert filters["color_identity"] == "GW"
    assert filters["format"] == "commander"
    # carries the spec's discriminating filter (oracle and/or presets)
    assert "oracle" in filters or "preset_names" in filters


def test_unknown_signal_has_no_spec_and_serves_false():
    sig = _sig("totally_unknown_signal", "you")
    assert spec_for(sig) is None
    assert serves(TOKEN_MAKER, sig) is False


# --- reanimator payoff (the Celes case) ----------------------------------------
# The avenue must surface the two enabler families that trigger the payoff:
# reanimation effects (a creature enters from a graveyard) and cast-from-graveyard
# creatures (escape/disturb). Self-mill alone is FUEL, not a reanimator enabler.
REANIMATION_SPELL = {
    "name": "Animate Dead-like",
    "oracle_text": "Return target creature card from your graveyard to the battlefield.",
}
ESCAPE_CREATURE = {
    "name": "Woe Strider-like",
    "type_line": "Creature — Horror",
    "oracle_text": (
        "Sacrifice another creature: Scry 1.\n"
        "Escape—{3}{B}{B}, Exile four other cards from your graveyard."
    ),
    "keywords": ["Escape"],
}
GRAVEYARD_RETURN = {
    "name": "Regrowth",
    "oracle_text": "Return target card from your graveyard to your hand.",
}


def test_reanimator_served_by_reanimation_and_escape():
    sig = _sig("reanimator", "you")
    assert serves(REANIMATION_SPELL, sig) is True
    assert serves(ESCAPE_CREATURE, sig) is True
    # graveyard-return to HAND is not a reanimator enabler (no creature re-enters play)
    assert serves(GRAVEYARD_RETURN, sig) is False
    # pure self-mill is fuel, not an enabler
    assert serves(SELF_MILL, sig) is False


def test_reanimator_spec_searches_with_a_discriminator():
    spec = spec_for(_sig("reanimator", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue
    filters = search_filters(
        _sig("reanimator", "you"), color_identity="BRW", fmt="commander"
    )
    assert "oracle" in filters or "preset_names" in filters


# --- aristocrats death-drain payoff (Blood Artist / Zulaport) -------------------
BLOOD_ARTIST = {
    "name": "Blood Artist",
    "type_line": "Creature — Vampire",
    "oracle_text": (
        "Whenever this creature or another creature dies, target player loses 1 life "
        "and you gain 1 life."
    ),
}
ZULAPORT = {
    "name": "Zulaport Cutthroat",
    "type_line": "Creature — Human Rogue Ally",
    "oracle_text": (
        "Whenever this creature or another creature you control dies, each opponent "
        "loses 1 life and you gain 1 life."
    ),
}


def test_death_drain_served_by_both_aristocrats_and_sacrifice_lanes():
    # The drain payoff must be on-theme for BOTH the death lane and the sacrifice lane
    # (a sac-outlet commander like Yawgmoth opens sacrifice_matters, not death_matters).
    for sig in (_sig("death_matters", "any"), _sig("sacrifice_matters", "you")):
        assert serves(BLOOD_ARTIST, sig) is True
        assert serves(ZULAPORT, sig) is True


def test_sacrifice_lane_does_not_serve_plain_lifegain():
    # A bare lifegain card is not a sacrifice/aristocrats enabler.
    assert serves(LIFEGAIN, _sig("sacrifice_matters", "you")) is False


# --- landfall: payoffs + extra lands + lands-from-graveyard ---------------------
LANDFALL_PAYOFF = {
    "name": "Lotus Cobra",
    "type_line": "Creature — Snake",
    "oracle_text": "Landfall — Whenever a land you control enters, add one mana of any color.",
}
EXTRA_LANDS = {
    "name": "Azusa, Lost but Seeking",
    "type_line": "Creature — Human Monk",
    "oracle_text": "You may play two additional lands on each of your turns.",
}
LANDS_FROM_GRAVE = {
    "name": "Ramunap Excavator",
    "type_line": "Creature — Naga Cleric",
    "oracle_text": "You may play lands from your graveyard.",
}


def test_landfall_serves_payoffs_extra_lands_and_recursion():
    sig = _sig("landfall", "you")
    assert serves(LANDFALL_PAYOFF, sig) is True  # the payoff itself (was uncovered)
    assert serves(EXTRA_LANDS, sig) is True  # extra-land enabler
    assert serves(LANDS_FROM_GRAVE, sig) is True  # land recursion (was uncovered)


def test_landfall_does_not_serve_unrelated_burn():
    assert serves(BURN, _sig("landfall", "you")) is False


# --- land-creatures theme (the Jyoti case) -------------------------------------

LAND_CREATURE_PAYOFF = {
    "name": "Sylvan Advocate",
    "type_line": "Creature — Elf Druid Ally",
    "oracle_text": (
        "Vigilance\nAs long as you control six or more lands, this creature "
        "and land creatures you control get +2/+2."
    ),
}
PLANT_MAKER = {
    "name": "Avenger of Zendikar",
    "type_line": "Creature — Elemental",
    "oracle_text": (
        "When Avenger of Zendikar enters, create a 0/1 green Plant creature "
        "token for each land you control."
    ),
}
CLONE = {
    "name": "Silent Hallcreeper",
    "type_line": "Enchantment Creature — Horror",
    "oracle_text": "This creature becomes a copy of another target creature.",
}
MANLAND = {
    "name": "Mishra's Factory",
    "type_line": "Land",
    "oracle_text": (
        "{T}: Add {C}.\n{1}: Mishra's Factory becomes a 2/2 Assembly-Worker "
        "artifact creature until end of turn. It's still a land."
    ),
}


def test_land_creatures_spec_exists_with_extra_avenues():
    spec = spec_for(_sig("land_creatures_matter", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue
    # The engine offers multiple precise sub-avenues, not one generic search.
    assert spec.extras


def test_land_creatures_serve_is_precise():
    sig = _sig("land_creatures_matter", "you")
    assert serves(LAND_CREATURE_PAYOFF, sig) is True  # references "land creatures"
    assert serves(PLANT_MAKER, sig) is False  # Plant tokens aren't land creatures
    assert serves(CLONE, sig) is False  # a clone is not a land creature


def _avenue_dicts(spec):
    """Engine avenue dicts (main + extras), as build_app emits them."""
    out = [{"label": spec.label, "search": dict(spec.search)}]
    out += [{"label": sa.label, "search": dict(sa.search)} for sa in spec.extras]
    return out


def _sig_sub(key, subject, scope="you"):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def test_subject_spec_built_for_tribal_signal():
    spec = spec_for(_sig_sub("type_matters", "Goblin"))
    assert spec is not None
    assert "Goblin" in spec.label
    assert spec.search.get("card_type") == "Goblin"


def test_subject_spec_serve_matches_subject_reference():
    sig = _sig_sub("type_matters", "Goblin")
    lord = {
        "oracle_text": "Other Goblins you control get +1/+1.",
        "type_line": "Creature — Goblin",
    }
    off = {"oracle_text": "Draw a card.", "type_line": "Sorcery"}
    assert serves(lord, sig) is True
    assert serves(off, sig) is False


def test_token_maker_subject_spec_and_generic_fallback():
    sub = spec_for(_sig_sub("token_maker", "Construct"))
    assert sub is not None
    assert "Construct" in sub.label  # "Construct tokens"
    # searches for cards that CREATE Construct tokens (oracle), not the type line.
    assert "oracle" in sub.search
    assert "card_type" not in sub.search
    generic = spec_for(_sig_sub("token_maker", ""))  # no subject → static spec
    assert generic is not None
    assert "oracle" in generic.search


def test_every_producible_key_resolves_to_a_spec():
    """The readable twin of the import-time key-agreement gate (ADR-0014): every
    subject-less key a detector can emit must resolve to a spec, so a new detector
    without a spec can't silently produce a no-op avenue. DERIVED from the producer
    tables (replaces the old hand-typed list, which was exactly the drift this guards)."""
    from mtg_utils._deck_forge.signals import producible_static_keys

    for key in sorted(producible_static_keys()):
        spec = spec_for(_sig(key, "any"))
        assert spec is not None, key
        assert spec.label, key
        assert spec.search, key


def test_search_filters_for_subject_signal_inject_identity():
    filters = search_filters(
        _sig_sub("type_matters", "Goblin"), color_identity="R", fmt="commander"
    )
    assert filters["card_type"] == "Goblin"
    assert filters["color_identity"] == "R"
    assert filters["format"] == "commander"


def test_land_creature_avenue_searches_exclude_false_positives():
    """The exact bug class the user hit: a Plant-token maker and a clone must not
    be surfaced by ANY land-creature avenue, while a real creature-land is."""
    from mtg_utils._deck_forge.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("land_creatures_matter", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(MANLAND)  # a real creature-land is surfaced by some avenue
    assert not served(PLANT_MAKER)  # Avenger's Plant tokens — surfaced by none
    assert not served(CLONE)  # Silent Hallcreeper clone — surfaced by none


def _subj_sig(key, subject):
    return Signal(key=key, scope="you", subject=subject, text="", source="cmd")


class TestCoinFlipSpec:
    """The coin-flip avenue must fan out a Flip-fixing sub-avenue that surfaces
    Krark's-Thumb-style fixers (otherwise they sink past the package cap)."""

    def test_coin_flip_has_flip_fixing_subavenue(self):
        import re

        spec = spec_for(_sig("coin_flip", "you"))
        assert spec is not None
        assert spec.label == "Coin flips"
        fix = {e.label: e for e in spec.extras}.get("Flip fixing")
        assert fix is not None, "expected a 'Flip fixing' sub-avenue"
        # Krark's Thumb is the canonical fixer — the sub-avenue's search must surface it.
        krark = "If you would flip a coin, instead flip two coins and ignore one."
        assert re.search(fix.search["oracle"], krark, re.IGNORECASE)
        # but a plain flip payoff is NOT a fixer (stays in the main avenue only).
        plain = "Flip a coin. If you win the flip, draw a card."
        assert not re.search(fix.search["oracle"], plain, re.IGNORECASE)
        # the main avenue still recognizes generic flip payoffs.
        assert spec.serve.search(plain)

    def test_flip_fixing_catches_outcome_forcing_fixers(self):
        """Edgar, King of Figaro fixes flips by FORCING THE OUTCOME
        ('those coins come up heads and you win those flips'), not by
        re-flipping. The Krark's-Thumb-shaped regex missed this whole class —
        the sub-avenue (and the parent avenue) must surface it."""
        import re

        spec = spec_for(_sig("coin_flip", "you"))
        fix = {e.label: e for e in spec.extras}["Flip fixing"]
        edgar = (
            "The first time you flip one or more coins each turn, "
            "those coins come up heads and you win those flips."
        )
        # Edgar is a genuine fixer — the sub-avenue search must catch it.
        assert re.search(fix.search["oracle"], edgar, re.IGNORECASE)
        # …and it serves the parent coin-flip avenue (it IS a coin-flip card,
        # phrased "flip one or more coins"/"come up heads", not "flip a coin").
        assert spec.serve.search(edgar)
        # but a plain flip-resolution payoff stays out of the fixer sub-avenue.
        plain = "Flip a coin. If you win the flip, draw a card."
        assert not re.search(fix.search["oracle"], plain, re.IGNORECASE)

    def test_flip_fixing_excludes_conditional_payoffs(self):
        """The e21b7d6 broadening (bare 'come up heads' / 'you win … flip') wrongly
        caught three PAYOFFS that reference a flip result as a CONDITION rather than
        GRANTING/manipulating the flip. A regex can't separate a grant from a condition,
        so the fixer sub-avenue must pin {Krark's Thumb, Edgar} and exclude these three
        (verified against bulk: the precise matcher yields exactly the two real fixers)."""
        import re

        spec = spec_for(_sig("coin_flip", "you"))
        fix = {e.label: e for e in spec.extras}["Flip fixing"]
        rx = re.compile(fix.search["oracle"], re.IGNORECASE)

        # The two REAL fixers — must match (a grant / a re-flip).
        edgar = (
            "The first time you flip one or more coins each turn, those coins come up "
            "heads and you win those flips."
        )
        krark = "If you would flip a coin, instead flip two coins and ignore one."
        assert rx.search(edgar)
        assert rx.search(krark)

        # Three PAYOFFS that merely reference a flip result — must NOT match.
        mana_clash = (
            "You and target opponent each flip a coin. Mana Clash deals 1 damage to "
            "each player whose coin comes up tails. Repeat this process until both "
            "players' coins come up heads on the same flip."
        )
        two_headed_giant = (
            "Whenever this creature attacks, flip two coins. If both coins come up "
            "heads, this creature gains double strike until end of turn. If both coins "
            "come up tails, this creature gains menace until end of turn."
        )
        squees_revenge = (
            "Choose a number. Flip a coin that many times or until you lose a flip, "
            "whichever comes first. If you win all the flips, draw two cards for each "
            "flip."
        )
        assert not rx.search(mana_clash)
        assert not rx.search(two_headed_giant)
        assert not rx.search(squees_revenge)


class TestSpellslingerServe:
    """The canonical false-positive: 'Spellslinger' (spellcast_matters) must NOT be
    served by any value permanent that merely draws a card. A cantrip is specifically
    an Instant or Sorcery that draws (CR 601.2: casting is determined by the card's
    type), prowess marks a payoff (CR 702.108a), and magecraft is an ability word that
    lives only in oracle prose (CR 207.2c). Copies aren't cast (CR 707.10)."""

    SLINGER = _sig("spellcast_matters", "you")

    def test_value_permanent_that_draws_does_not_serve(self):
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever an opponent casts a spell, you may draw a card unless that "
                "player pays {1}."
            ),
        }
        assert serves(rhystic, self.SLINGER) is False

    def test_opponent_cast_drawer_does_not_serve(self):
        # Esper Sentinel: "opponent casts … noncreature spell" — the "you cast" gate
        # must reject it (it's an opponents-cast payoff, not a spellslinger enabler).
        esper = {
            "name": "Esper Sentinel",
            "type_line": "Artifact Creature — Human Soldier",
            "oracle_text": (
                "Whenever an opponent casts their first noncreature spell each turn, "
                "draw a card unless that player pays {X}, where X is this creature's "
                "power."
            ),
            "keywords": [],
        }
        assert serves(esper, self.SLINGER) is False

    def test_equipment_that_draws_does_not_serve(self):
        sword = {
            "name": "Sword of Fire and Ice",
            "type_line": "Artifact — Equipment",
            "oracle_text": (
                "Equipped creature gets +2/+2 and has protection from red and from "
                "blue.\nWhenever equipped creature deals combat damage to a player, "
                "this Equipment deals 2 damage to any target and you draw a card."
            ),
            "keywords": ["Equip"],
        }
        assert serves(sword, self.SLINGER) is False

    def test_coinflip_value_creature_does_not_serve(self):
        # Zndrsplt: draws on a won coin flip, never on YOUR cast — the canonical FP.
        zndrsplt = {
            "name": "Zndrsplt, Eye of Wisdom",
            "type_line": "Legendary Creature — Homunculus",
            "oracle_text": (
                "At the beginning of combat on your turn, flip a coin until you lose "
                "a flip.\nWhenever a player wins a coin flip, draw a card."
            ),
            "keywords": ["Partner"],
        }
        assert serves(zndrsplt, self.SLINGER) is False

    def test_instant_cantrip_serves(self):
        opt = {
            "name": "Opt",
            "type_line": "Instant",
            "oracle_text": "Scry 1.\nDraw a card.",
        }
        assert serves(opt, self.SLINGER) is True

    def test_prowess_creature_serves_via_keyword(self):
        swiftspear = {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "oracle_text": "Haste\nProwess",
            "keywords": ["Prowess", "Haste"],
        }
        assert serves(swiftspear, self.SLINGER) is True

    def test_cast_trigger_payoff_serves_via_oracle(self):
        # Young Pyromancer: a payoff with NO prowess keyword and not itself an
        # instant/sorcery — caught by the "whenever you cast an instant or sorcery"
        # oracle branch.
        pyromancer = {
            "name": "Young Pyromancer",
            "type_line": "Creature — Human Shaman",
            "oracle_text": (
                "Whenever you cast an instant or sorcery spell, create a 1/1 red "
                "Elemental creature token."
            ),
            "keywords": [],
        }
        assert serves(pyromancer, self.SLINGER) is True

    def test_magecraft_payoff_serves_via_oracle(self):
        storm_kiln = {
            "name": "Storm-Kiln Artist",
            "type_line": "Creature — Dwarf Shaman",
            "oracle_text": (
                "This creature gets +1/+0 for each artifact you control.\nMagecraft — "
                "Whenever you cast or copy an instant or sorcery spell, create a "
                "Treasure token."
            ),
            "keywords": ["Treasure", "Magecraft"],
        }
        assert serves(storm_kiln, self.SLINGER) is True

    def test_avenue_classifies_by_structured_serve_not_draw(self):
        """The avenue-credit path (ranking._avenue_matchers) must apply the SAME
        precise predicate the spec serves on — so exploring the Spellslinger avenue
        credits a real cantrip (matched by TYPE, whose oracle says only 'draw a card')
        and a prowess creature (matched by KEYWORD), but NOT a value permanent."""
        from mtg_utils._deck_forge.ranking import score_candidate

        spec = spec_for(self.SLINGER)
        avenue = {
            "label": spec.label,
            "search": dict(spec.search),
            "serve": spec.serve.as_dict(),
        }

        def served(card):
            return set(
                score_candidate(card, active_signals=[], avenues=[avenue])["served"]
            )

        opt = {
            "name": "Opt",
            "type_line": "Instant",
            "oracle_text": "Scry 1.\nDraw a card.",
        }
        swiftspear = {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "oracle_text": "Haste\nProwess",
            "keywords": ["Prowess"],
        }
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent casts a spell, you may draw a card.",
        }
        assert "Spellslinger" in served(opt)  # by type
        assert "Spellslinger" in served(swiftspear)  # by keyword
        assert "Spellslinger" not in served(rhystic)  # value permanent excluded


class TestMagecraftServe:
    """magecraft_matters is the same spellslinger archetype (CR 207.2c: magecraft's
    reminder is 'whenever you cast or copy an instant or sorcery spell'). Its matcher
    must be as precise as Spellslinger's — no bare 'draw a card' search, no bare
    'instant or sorcery' serve branch that credits counterspell-shelters/value lands."""

    MAGE = _sig("magecraft_matters", "you")

    def test_protective_land_does_not_serve(self):
        # Boseiju mentions "instant or sorcery" but only to protect a spell — not a
        # spellslinger payoff. The old bare 'instant or sorcery' serve branch caught it.
        boseiju = {
            "name": "Boseiju, Who Shelters All",
            "type_line": "Legendary Land",
            "oracle_text": (
                "Boseiju enters tapped.\n{T}, Pay 2 life: Add {C}. If that mana is "
                "spent on an instant or sorcery spell, that spell can't be countered."
            ),
            "keywords": [],
        }
        assert serves(boseiju, self.MAGE) is False

    def test_cast_trigger_payoff_serves(self):
        murmuring = {
            "name": "Murmuring Mystic",
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "Whenever you cast an instant or sorcery spell, create a 1/1 blue Bird "
                "Illusion creature token with flying."
            ),
            "keywords": [],
        }
        assert serves(murmuring, self.MAGE) is True

    def test_instant_serves_by_type(self):
        opt = {
            "name": "Opt",
            "type_line": "Instant",
            "oracle_text": "Scry 1.\nDraw a card.",
        }
        assert serves(opt, self.MAGE) is True

    def test_avenue_does_not_credit_value_permanent(self):
        from mtg_utils._deck_forge.ranking import score_candidate

        spec = spec_for(self.MAGE)
        avenue = engine_avenue(spec)
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent casts a spell, you may draw a card.",
        }
        served = set(
            score_candidate(rhystic, active_signals=[], avenues=[avenue])["served"]
        )
        assert spec.label not in served


def engine_avenue(spec):
    """An engine-emitted avenue dict for a spec (main avenue, with structured serve)."""
    from mtg_utils._deck_forge.engine import avenue_with_serve

    return avenue_with_serve(
        {"label": spec.label, "search": dict(spec.search)}, spec.serve
    )


class TestSecondSpellSearch:
    """second_spell_matters' serve is precise, but its SEARCH carried the same bare
    'draw a card' branch — so the avenue credited value permanents. The search must
    surface second-spell / storm payoffs, not every drawer."""

    SIG = _sig("second_spell_matters", "you")

    def test_avenue_excludes_value_permanent(self):
        from mtg_utils._deck_forge.ranking import score_candidate

        spec = spec_for(self.SIG)
        avenue = engine_avenue(spec)
        rhystic = {
            "name": "Rhystic Study",
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent casts a spell, you may draw a card.",
        }
        served = set(
            score_candidate(rhystic, active_signals=[], avenues=[avenue])["served"]
        )
        assert spec.label not in served

    def test_serve_matches_a_real_second_spell_payoff(self):
        payoff = {
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "Whenever you cast your second spell each turn, draw a card."
            ),
        }
        assert serves(payoff, self.SIG) is True


class TestSubjectSpecs:
    """Subject-bearing avenues must match their label and stay distinct from payoffs."""

    def test_token_maker_finds_token_makers_not_the_tribe(self):
        spec = spec_for(_subj_sig("token_maker", "Dryad"))
        assert spec.label == "Dryad tokens"
        # a card that CREATES Dryad tokens serves it…
        assert spec.serve.search("Create a 1/1 green Dryad creature token.")
        # …a plain Dryad creature (no token creation) does NOT.
        assert not spec.serve.search("Dryad — this creature has reach.")
        # the search targets token creation, not the type line.
        assert "oracle" in spec.search
        assert "card_type" not in spec.search

    def test_token_maker_payoffs_are_a_distinct_sub_avenue(self):
        spec = spec_for(_subj_sig("token_maker", "Dryad"))
        extra_labels = [e.label for e in spec.extras]
        # The tribe-token payoffs come first; the flood deck also gets the audit-added
        # token-doubler and creature-ETB-payoff sub-avenues (EDHREC gap fix).
        assert extra_labels[0] == "Dryad payoffs"
        assert "Token doublers" in extra_labels
        assert "Creature-ETB payoffs" in extra_labels
        # the main avenue blurb must NOT also claim to cover payoffs (the old confusion).
        assert "payoff" not in spec.avenue.lower()

    def test_tribal_finds_the_creatures_payoffs_finds_the_lords(self):
        spec = spec_for(_subj_sig("type_matters", "Elemental"))
        assert spec.label == "Elemental tribal"
        assert spec.search == {"card_type": "Elemental"}  # the creatures
        payoff = spec.extras[0]
        assert payoff.label == "Elemental payoffs"
        assert "you control" in payoff.search["oracle"]  # the lords/anthems


class TestStructuredServeFixes:
    """Audit-driven precision fixes that convert imprecise oracle regexes to the
    proper structured characteristic (type / keyword / count gate). Each pins a
    measured false-positive AND a false-negative against real cards."""

    def test_card_draw_engine_rejects_one_shot_cantrips(self):
        """card_draw_engine's serve `draw \\w+ cards?` let \\w+ eat 'draw a card',
        so ~753 one-shot cantrips were mislabeled an 'engine'. A recurring/bulk gate
        keeps Phyrexian Arena (recurring) and Blue Sun's Zenith (X cards) but drops a
        one-shot instant draw (Remand) and a death-triggered single draw (Solemn)."""
        sig = _sig("card_draw_engine", "you")
        phyrexian_arena = {
            "type_line": "Enchantment",
            "oracle_text": "At the beginning of your upkeep, you draw a card and you lose 1 life.",
        }
        blue_suns = {
            "type_line": "Instant",
            "oracle_text": "Draw X cards. Put Blue Sun's Zenith into its owner's library third from the top.",
        }
        remand = {
            "type_line": "Instant",
            "oracle_text": "Counter target spell. If that spell is countered this way, put it into its owner's hand instead. Draw a card.",
        }
        solemn = {
            "type_line": "Artifact Creature — Golem",
            "oracle_text": "When this creature dies, you may draw a card.",
        }
        assert serves(phyrexian_arena, sig) is True
        assert serves(blue_suns, sig) is True
        assert serves(remand, sig) is False
        assert serves(solemn, sig) is False

    def test_lifegain_uses_lifelink_keyword_not_the_bare_word(self):
        """lifegain's serve matched the bare word 'lifelink' anywhere in oracle text,
        so Crystalline Giant (which only lists lifelink among random counters) served.
        Gate on the keywords[] field instead; a card that GRANTS lifelink to the team
        still serves via an oracle grant-branch."""
        sig = _sig("lifegain_matters", "you")
        soul_warden = {
            "type_line": "Creature — Human Cleric",
            "oracle_text": "Whenever another creature enters, you gain 1 life.",
            "keywords": [],
        }
        baneslayer = {
            "type_line": "Creature — Angel",
            "oracle_text": "Flying, first strike, lifelink, protection from Demons and from Dragons",
            "keywords": ["Flying", "First strike", "Lifelink"],
        }
        whip = {
            "type_line": "Legendary Enchantment Artifact",
            "oracle_text": "Creatures you control have lifelink.",
            "keywords": [],
        }
        crystalline_giant = {
            "type_line": "Artifact Creature — Giant",
            "oracle_text": (
                "At the beginning of combat on your turn, choose a kind of counter at "
                "random that this creature doesn't have on it from among flying, first "
                "strike, deathtouch, hexproof, lifelink, menace, reach, trample, and "
                "vigilance, then put a counter of that kind on this creature."
            ),
            "keywords": [],
        }
        assert serves(soul_warden, sig) is True  # gains life
        assert serves(baneslayer, sig) is True  # lifelink keyword
        assert serves(whip, sig) is True  # grants lifelink to the team
        assert serves(crystalline_giant, sig) is False  # bare word in a counter list

    def test_dash_avenue_keys_on_equipment_type_and_dash_keyword(self):
        """dash_matters' serve had `whenever[^.]*attacks` and a bare `\\bequipment\\b`
        that matched any creature mentioning equipment/attacks (~1104). The avenue is
        Equipment-for-a-dasher: gate on the Equipment TYPE and the dash KEYWORD."""
        sig = _sig("dash_matters", "you")
        skullclamp = {
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +1/-1.\nWhenever equipped creature dies, draw two cards.\nEquip {1}",
            "keywords": ["Equip"],
        }
        mangara = {
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": "Lifelink\nWhenever an opponent attacks with creatures, draw a card.",
            "keywords": ["Lifelink"],
        }
        elder_gargaroth = {
            "type_line": "Creature — Beast",
            "oracle_text": "Vigilance, reach, trample\nWhenever this creature attacks or blocks, choose one.",
            "keywords": ["Vigilance", "Reach", "Trample"],
        }
        assert serves(skullclamp, sig) is True  # Equipment type
        assert serves(mangara, sig) is False  # not equipment, no dash
        assert serves(elder_gargaroth, sig) is False  # "attacks" no longer triggers

    def test_creature_etb_opponents_matches_punisher_not_bloodthirst(self):
        """creature_etb/opponents' serve `opponent.*creature.*enters` required
        opponent BEFORE creature, so it matched Bloodthirst ('an opponent was dealt
        damage … this creature enters') and MISSED the real punisher ('a creature an
        opponent controls enters'). A near-total inversion."""
        sig = _sig("creature_etb", "opponents")
        suture_priest = {
            "type_line": "Creature — Phyrexian Cleric",
            "oracle_text": (
                "Whenever another creature you control enters, you may gain 1 life.\n"
                "Whenever a creature an opponent controls enters, you may have that "
                "player lose 1 life."
            ),
        }
        authority = {
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures your opponents control enter tapped.\nWhenever a creature "
                "an opponent controls enters, you gain 1 life."
            ),
        }
        bloodthirst = {
            "type_line": "Creature — Vampire Warrior",
            "oracle_text": (
                "Bloodthirst 2 (If an opponent was dealt damage this turn, this "
                "creature enters with two +1/+1 counters on it.)"
            ),
        }
        assert serves(suture_priest, sig) is True
        assert serves(authority, sig) is True
        assert serves(bloodthirst, sig) is False

    def test_drain_avenue_serves_blood_artist(self):
        """lifeloss_matters/opponents (the 'Drain' avenue) required the literal word
        'opponent' next to 'loses', so it MISSED the keystone aristocrats drains that
        read 'target player loses N life' (Blood Artist, Zulaport Cutthroat)."""
        sig = _sig("lifeloss_matters", "opponents")
        blood_artist = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.",
        }
        zulaport = {
            "type_line": "Creature — Human Cleric",
            "oracle_text": "Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life.",
        }
        assert serves(blood_artist, sig) is True
        assert serves(zulaport, sig) is True


class TestStructuredServeFixes2:
    """Second batch of audit-driven precision fixes (all SPECS-level serve)."""

    def test_aristocrats_serve_requires_creature_token_not_treasure(self):
        """sacrifice/death serves keyed on `create .*token`, which is type-blind: it
        served every Treasure/Clue/Food maker (~428 in WBR). Require the literal
        'creature token' so only real sacrifice fodder qualifies."""
        sac = _sig("sacrifice_matters", "you")
        death = _sig("death_matters", "any")
        bitterblossom = {
            "type_line": "Kindred Enchantment — Faerie",
            "oracle_text": "At the beginning of your upkeep, you lose 1 life and create a 1/1 black Faerie Rogue creature token with flying.",
        }
        viscera_seer = {
            "type_line": "Creature — Vampire Wizard",
            "oracle_text": "Sacrifice a creature: Scry 1.",
        }
        blood_artist = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.",
        }
        smothering_tithe = {
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent draws a card, that player may pay {2}. If the player doesn't, you create a Treasure token.",
        }
        tireless_tracker = {
            "type_line": "Creature — Human Scout",
            "oracle_text": "Whenever a land you control enters, investigate. Create a Clue token.",
        }
        assert serves(bitterblossom, sac) is True  # makes creature-token fodder
        assert serves(viscera_seer, sac) is True  # sac outlet
        assert serves(blood_artist, death) is True  # dies trigger
        assert serves(smothering_tithe, sac) is False  # Treasure, not creature token
        assert serves(smothering_tithe, death) is False
        assert serves(tireless_tracker, death) is False  # Clue, not creature token

    def test_landfall_serve_is_land_anchored(self):
        """landfall's bare `onto the battlefield` branch matched any cheat-into-play /
        reanimation. Anchor it to 'land card … onto the battlefield'."""
        sig = _sig("landfall", "you")
        cultivate = {
            "type_line": "Sorcery",
            "oracle_text": "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
        }
        azusa = {
            "type_line": "Legendary Creature — Human Monk",
            "oracle_text": "You may play two additional lands on each of your turns.",
        }
        sneak_attack = {
            "type_line": "Enchantment",
            "oracle_text": "{R}: You may put a creature card from your hand onto the battlefield. That creature gains haste. Sacrifice the creature at the beginning of the next end step.",
        }
        reanimate = {
            "type_line": "Sorcery",
            "oracle_text": "Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to that card's mana value.",
        }
        assert serves(cultivate, sig) is True
        assert serves(azusa, sig) is True
        assert serves(sneak_attack, sig) is False
        assert serves(reanimate, sig) is False

    def test_stax_serve_requires_restriction_not_bare_your_opponents(self):
        """stax/opponents had a bare `your opponents` alternative that matched any card
        naming opponents (Edric's draw trigger, Telepathy's hand reveal). Serve the
        actual tax/restriction shapes; this also recovers symmetric taxes (Thalia)."""
        sig = _sig("stax_taxes", "opponents")
        drannith = {
            "type_line": "Creature — Human Wizard",
            "oracle_text": "Your opponents can't cast spells from anywhere other than their hands.",
        }
        thalia = {
            "type_line": "Legendary Creature — Human Soldier",
            "oracle_text": "First strike\nNoncreature spells cost {1} more to cast.",
        }
        edric = {
            "type_line": "Legendary Creature — Elf Advisor",
            "oracle_text": "Whenever a creature deals combat damage to one of your opponents, its controller may draw a card.",
        }
        telepathy = {
            "type_line": "Enchantment",
            "oracle_text": "Your opponents play with their hands revealed.",
        }
        assert serves(drannith, sig) is True  # opponents can't
        assert serves(thalia, sig) is True  # noncreature cost more
        assert serves(edric, sig) is False  # names opponents, but is a draw payoff
        assert serves(telepathy, sig) is False  # names opponents, but is hand reveal

    def test_evasion_self_excludes_menace_reminder(self):
        """evasion_self's bare `can't be blocked` matched the menace/flying REMINDER
        text 'can't be blocked except by …'. Exclude the 'except' form; keep true
        unblockable and landwalk."""
        sig = _sig("evasion_self", "you")
        invisible_stalker = {
            "type_line": "Creature — Human Rogue",
            "oracle_text": "Hexproof (This creature can't be the target of spells or abilities your opponents control.)\nThis creature can't be blocked.",
            "keywords": ["Hexproof"],
        }
        sengir = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Flying (This creature can't be blocked except by creatures with flying or reach.)\nWhenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.",
            "keywords": ["Flying"],
        }
        assert serves(invisible_stalker, sig) is True
        assert serves(sengir, sig) is False


class TestStructuredServeFixes3:
    """Combat-damage connect avenues: drop the bare `\\bmenace\\b` word (matched every
    menace creature + reminder text) and the `can't be blocked` reminder form. Serve
    the payoff trigger + true-unblockable enablers, not every vanilla evasive body."""

    def test_combat_damage_opponents_drops_bare_menace(self):
        sig = _sig("combat_damage_matters", "opponents")
        edric = {
            "type_line": "Legendary Creature — Elf Advisor",
            "oracle_text": "Whenever a creature deals combat damage to one of your opponents, its controller may draw a card.",
            "keywords": [],
        }
        coastal_piracy = {
            "type_line": "Enchantment",
            "oracle_text": "Whenever a creature you control deals combat damage to an opponent, you may draw a card.",
            "keywords": [],
        }
        invisible_stalker = {
            "type_line": "Creature — Human Rogue",
            "oracle_text": "Hexproof\nThis creature can't be blocked.",
            "keywords": ["Hexproof"],
        }
        vanilla_menace = {
            "type_line": "Creature — Orc Warrior",
            "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)",
            "keywords": ["Menace"],
        }
        sengir = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Flying (This creature can't be blocked except by creatures with flying or reach.)",
            "keywords": ["Flying"],
        }
        assert serves(edric, sig) is True  # payoff trigger
        assert serves(coastal_piracy, sig) is True  # payoff trigger
        assert serves(invisible_stalker, sig) is True  # true unblockable enabler
        assert serves(vanilla_menace, sig) is False  # bare menace word/reminder
        assert serves(sengir, sig) is False  # vanilla flier, reminder "except"

    def test_damage_to_opp_drops_bare_menace(self):
        sig = _sig("damage_to_opp_matters", "opponents")
        niv = {
            "type_line": "Legendary Creature — Dragon Avatar",
            "oracle_text": "Flying\nWhenever a source you control deals noncombat damage to an opponent, you draw that many cards.",
            "keywords": ["Flying"],
        }
        vanilla_menace = {
            "type_line": "Creature — Orc Warrior",
            "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)",
            "keywords": ["Menace"],
        }
        assert serves(niv, sig) is True  # noncombat-damage-to-opponent payoff
        assert serves(vanilla_menace, sig) is False


class TestSweepDetectorFixes:
    """Mined sweep-detector regexes whose open-ended alternations over-fire."""

    def test_self_counter_grow_is_self_only_not_distribution(self):
        """The `put … +1/+1 counter on [A-Z][a-z]+` branch matched any capitalized
        word after 'on' — so distributors (counter on target Knight / on target
        creature for each Elf) read as SELF-growth (~1072 FP). Self-growth only."""
        sig = _sig("self_counter_grow", "you")
        walking_ballista = {
            "type_line": "Artifact Creature — Construct",
            "oracle_text": "This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.",
        }
        venerable_knight = {
            "type_line": "Creature — Human Knight",
            "oracle_text": "When this creature dies, put a +1/+1 counter on target Knight you control.",
        }
        immaculate = {
            "type_line": "Creature — Elf Shaman",
            "oracle_text": "{T}: Put a +1/+1 counter on target creature for each Elf you control.",
        }
        assert serves(walking_ballista, sig) is True
        assert serves(venerable_knight, sig) is False
        assert serves(immaculate, sig) is False

    def test_facedown_requires_morph_vocab_not_bare_face_down(self):
        """The bare `face-down|face down` and `is turned face up` branches matched
        impulse/hideaway exile ('exile one face down'). Require the morph/manifest
        vocabulary or the 'face-down creature(s)' payoff noun (~212 FP)."""
        sig = _sig("facedown_matters", "you")
        secret_plans = {
            "type_line": "Enchantment",
            "oracle_text": "Face-down creatures you control get +0/+1.\nWhenever a permanent you control is turned face up, draw a card.",
        }
        morph_creature = {
            "type_line": "Creature — Beast",
            "oracle_text": "Morph {2}{G} (You may cast this card face down as a 2/2 creature for {3}.)",
            "keywords": ["Morph"],
        }
        gonti = {
            "type_line": "Legendary Creature — Aetherborn Rogue",
            "oracle_text": "Deathtouch\nWhen Gonti enters, look at the top four cards of target opponent's library, exile one of them face down, then put the rest on the bottom.",
            "keywords": ["Deathtouch"],
        }
        spinerock = {
            "type_line": "Land",
            "oracle_text": "Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom.)",
            "keywords": ["Hideaway"],
        }
        assert serves(secret_plans, sig) is True  # face-down creatures payoff
        assert serves(morph_creature, sig) is True  # morph vocab
        assert serves(gonti, sig) is False  # impulse exile "face down"
        assert serves(spinerock, sig) is False  # hideaway exile "face down"


class TestStructuredServeExtension:
    """fp=0 HIGH findings the audit flagged as RECALL failures: the serve named only
    the payoffs and could not express the structured enablers. Now type/keyword/cmc/
    devotion-pip dimensions recover them — the heart of the 'use the structured field'
    thesis. Each pins recovered enablers (+) and confirms non-members stay out (-)."""

    def test_superfriends_serves_planeswalkers_and_proliferate(self):
        sig = _sig("superfriends_matters", "you")
        karn = {
            "type_line": "Legendary Planeswalker — Karn",
            "oracle_text": "...",
            "keywords": [],
        }
        atraxa = {
            "type_line": "Legendary Creature — Phyrexian Angel Horror",
            "oracle_text": "Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate.",
            "keywords": [
                "Flying",
                "Vigilance",
                "Deathtouch",
                "Lifelink",
                "Proliferate",
            ],
        }
        bolt = {
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "keywords": [],
        }
        assert serves(karn, sig) is True  # planeswalker type
        assert serves(atraxa, sig) is True  # proliferate keyword
        assert serves(bolt, sig) is False

    def test_modified_serves_equipment_auras_and_counters(self):
        sig = _sig("modified_matters", "you")
        glitters = {
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature gets +1/+1 for each artifact and enchantment you control.",
        }
        hardened_scales = {
            "type_line": "Enchantment",
            "oracle_text": "If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.",
        }
        equipment = {
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +1/+1.\nEquip {1}",
            "keywords": ["Equip"],
        }
        sol_ring = {"type_line": "Artifact", "oracle_text": "{T}: Add {C}{C}."}
        assert serves(glitters, sig) is True  # Aura type
        assert serves(equipment, sig) is True  # Equipment type
        assert serves(hardened_scales, sig) is True  # +1/+1 counter oracle
        assert serves(sol_ring, sig) is False

    def test_voltron_serves_buff_auras_but_not_control_auras(self):
        sig = _sig("voltron_matters", "you")
        skullclamp = {
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +1/-1.\nEquip {1}",
            "keywords": ["Equip"],
        }
        flight = {
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature has flying.",
        }
        pacifism = {
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature can't attack or block.",
        }
        sol_ring = {"type_line": "Artifact", "oracle_text": "{T}: Add {C}{C}."}
        assert serves(skullclamp, sig) is True  # Equipment
        assert serves(flight, sig) is True  # buff Aura
        assert serves(pacifism, sig) is False  # control Aura — vetoed
        assert serves(sol_ring, sig) is False

    def test_devotion_serves_heavy_pip_permanents_via_structured_pips(self):
        sig = _sig("devotion_matters", "you")
        gray_merchant = {
            "type_line": "Creature — Zombie",
            "mana_cost": "{3}{B}{B}",
            "cmc": 5.0,
            "oracle_text": "When this creature enters, each opponent loses life equal to your devotion to black.",
        }
        heavy_pip_vanilla = {
            "type_line": "Creature — Elemental",
            "mana_cost": "{2}{R}{R}",
            "cmc": 4.0,
            "oracle_text": "Trample",
        }
        llanowar = {
            "type_line": "Creature — Elf Druid",
            "mana_cost": "{G}",
            "cmc": 1.0,
            "oracle_text": "{T}: Add {G}.",
        }
        bolt = {
            "type_line": "Instant",
            "mana_cost": "{R}",
            "cmc": 1.0,
            "oracle_text": "deals 3 damage to any target.",
        }
        sol_ring = {
            "type_line": "Artifact",
            "mana_cost": "{1}",
            "cmc": 1.0,
            "oracle_text": "{T}: Add {C}{C}.",
        }
        assert serves(gray_merchant, sig) is True  # devotion oracle + 2 black pips
        assert serves(heavy_pip_vanilla, sig) is True  # 2 red pips, a permanent
        assert serves(llanowar, sig) is False  # only 1 pip
        assert serves(bolt, sig) is False  # 2 pips but an instant (not a permanent)
        assert serves(sol_ring, sig) is False  # colorless

    def test_cost_reduction_serves_x_spells_and_expensive_bombs(self):
        sig = _sig("cost_reduction", "you")
        torment = {
            "type_line": "Sorcery",
            "mana_cost": "{X}{B}{B}",
            "cmc": 2.0,
            "oracle_text": "Each opponent loses life and discards a card for each {X}.",
        }
        emrakul = {
            "type_line": "Legendary Creature — Eldrazi",
            "mana_cost": "{15}",
            "cmc": 15.0,
            "oracle_text": "...",
        }
        disdainful = {
            "type_line": "Instant",
            "mana_cost": "{1}{U}",
            "cmc": 2.0,
            "oracle_text": "Counter target spell with mana value 4 or greater.",
        }
        sun_titan = {
            "type_line": "Creature — Giant",
            "mana_cost": "{4}{W}{W}",
            "cmc": 6.0,
            "oracle_text": "...",
        }
        assert serves(torment, sig) is True  # X spell
        assert serves(emrakul, sig) is True  # expensive bomb (cmc>=7)
        assert serves(disdainful, sig) is False  # "mana value 4" no longer matches
        assert serves(sun_titan, sig) is False  # cmc 6 below the bomb threshold

    def test_removal_serves_burn_to_any_target(self):
        sig = _sig("removal_matters", "you")
        bolt = {
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        }
        murder = {"type_line": "Instant", "oracle_text": "Destroy target creature."}
        sol_ring = {"type_line": "Artifact", "oracle_text": "{T}: Add {C}{C}."}
        assert serves(bolt, sig) is True  # damage to any target
        assert serves(murder, sig) is True
        assert serves(sol_ring, sig) is False

    def test_counter_control_extraction_allows_adjective_gap(self):
        from mtg_utils._deck_forge.signals import extract_signals

        essence_scatter = {
            "name": "Essence Scatter",
            "type_line": "Instant",
            "oracle_text": "Counter target creature spell.",
        }
        keys = {s.key for s in extract_signals(essence_scatter)}
        assert "counter_control" in keys


class TestStructuredServeFixes4:
    """Batch 4: remaining HIGH precision fixes."""

    def test_mana_amplifier_drops_fixing_keeps_doublers(self):
        """`add .* mana of any` captured fixing (Birds, City of Brass), not
        amplification. Serve the doublers/triplers ('tap … for mana … add/produces
        twice') + X-spell payoffs."""
        sig = _sig("mana_amplifier", "you")
        mirari = {
            "type_line": "Enchantment",
            "oracle_text": "Creatures you control get +1/+1.\nWhenever you tap a land for mana, add one mana of any type that land produced.",
        }
        reflection = {
            "type_line": "Enchantment",
            "oracle_text": "If you tap a permanent for mana, it produces twice as much of that mana instead.",
        }
        birds = {
            "type_line": "Creature — Bird",
            "oracle_text": "Flying\n{T}: Add one mana of any color.",
            "keywords": ["Flying"],
        }
        signet = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Add one mana of any color.",
        }
        assert serves(mirari, sig) is True
        assert serves(reflection, sig) is True
        assert serves(birds, sig) is False
        assert serves(signet, sig) is False

    def test_attack_serves_haste_keyword_and_grants_not_bare_word(self):
        sig = _sig("attack_matters", "you")
        fervor = {
            "type_line": "Enchantment",
            "oracle_text": "Creatures you control have haste.",
            "keywords": [],
        }
        haste_beater = {
            "type_line": "Creature — Goblin",
            "oracle_text": "Haste",
            "keywords": ["Haste"],
        }
        krenko = {
            "type_line": "Legendary Creature — Goblin",
            "oracle_text": "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
            "keywords": [],
        }
        loses_haste = {
            "type_line": "Instant",
            "oracle_text": "Target creature loses haste until end of turn.",
            "keywords": [],
        }
        sol_ring = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}{C}.",
            "keywords": [],
        }
        assert serves(fervor, sig) is True  # grants haste to team
        assert serves(haste_beater, sig) is True  # Haste keyword
        assert serves(krenko, sig) is True  # creature-token maker
        assert serves(loses_haste, sig) is False  # bare word "haste" (removes it)
        assert serves(sol_ring, sig) is False

    def test_play_from_top_drops_bare_reveal(self):
        """`reveal the top card of your library` is a peek (Coiling Oracle), not
        play-from-top. Keep the play/cast-from-top forms."""
        sig = _sig("play_from_top", "you")
        future_sight = {
            "type_line": "Enchantment",
            "oracle_text": "Play with the top card of your library revealed.\nYou may play lands and cast spells from the top of your library.",
        }
        coiling_oracle = {
            "type_line": "Creature — Snake Elf",
            "oracle_text": "When this creature enters, reveal the top card of your library. If it's a land card, put it onto the battlefield.",
        }
        assert serves(future_sight, sig) is True
        assert serves(coiling_oracle, sig) is False

    def test_pump_matters_drops_minus_bonuses(self):
        """pump's `[+\\-]` matched -X/-X shrink (that's debuff_matters). Positive only."""
        sig = _sig("pump_matters", "you")
        giant_growth = {
            "type_line": "Instant",
            "oracle_text": "Target creature gets +3/+3 until end of turn.",
        }
        festering_goblin = {
            "type_line": "Creature — Zombie Goblin",
            "oracle_text": "When this creature dies, target creature gets -1/-1 until end of turn.",
        }
        assert serves(giant_growth, sig) is True
        assert serves(festering_goblin, sig) is False

    def test_crimes_avenue_excludes_counterspells(self):
        """crimes SEARCH `target.*spell` credited every counterspell. Drop it."""
        from mtg_utils._deck_forge.ranking import score_candidate

        spec = spec_for(_sig("crimes_matter", "you"))
        avenue = {"label": spec.label, "search": dict(spec.search)}
        counterspell = {"type_line": "Instant", "oracle_text": "Counter target spell."}
        murder = {"type_line": "Instant", "oracle_text": "Destroy target creature."}
        served_cs = set(
            score_candidate(counterspell, active_signals=[], avenues=[avenue])["served"]
        )
        served_m = set(
            score_candidate(murder, active_signals=[], avenues=[avenue])["served"]
        )
        assert spec.label not in served_cs  # counterspell is not a crime enabler
        assert spec.label in served_m  # targeted removal is


class TestMediumServeFixes:
    """MEDIUM findings: recall recoveries via type/keyword/produced_mana, plus serve
    tightenings that drop a bad branch. Each pins the audit's +/- fixtures."""

    def _ck(self, key, scope, plus, minus):
        sig = _sig(key, scope)
        for card in plus:
            assert serves(card, sig) is True, (key, card.get("name"))
        for card in minus:
            assert serves(card, sig) is False, (key, card.get("name"))

    def test_historic_serves_legendary_artifact_saga_types(self):
        self._ck(
            "historic_matters",
            "you",
            [
                {
                    "name": "Sol Ring",
                    "type_line": "Artifact",
                    "oracle_text": "{T}: Add {C}{C}.",
                },
                {
                    "name": "The Eldest Reborn",
                    "type_line": "Enchantment — Saga",
                    "oracle_text": "...",
                },
                {
                    "name": "Urza",
                    "type_line": "Legendary Creature — Human Artificer",
                    "oracle_text": "...",
                },
            ],
            [
                {
                    "name": "Llanowar Elves",
                    "type_line": "Creature — Elf Druid",
                    "oracle_text": "{T}: Add {G}.",
                }
            ],
        )

    def test_legends_serves_legendary_type(self):
        self._ck(
            "legends_matter",
            "you",
            [
                {
                    "name": "Jodah",
                    "type_line": "Legendary Creature — Human Wizard",
                    "oracle_text": "...",
                }
            ],
            [{"name": "Island", "type_line": "Basic Land — Island", "oracle_text": ""}],
        )

    def test_party_serves_party_classes_not_bare_word(self):
        self._ck(
            "party_matters",
            "you",
            [
                {
                    "name": "Archpriest",
                    "type_line": "Creature — Human Cleric",
                    "oracle_text": "...",
                },
                {
                    "name": "Tazri",
                    "type_line": "Legendary Creature — Human Warrior",
                    "oracle_text": "Your party...",
                },
            ],
            [
                {
                    "name": "Tavern",
                    "type_line": "Sorcery",
                    "oracle_text": "You meet in a tavern. The party gathers.",
                }
            ],
        )

    def test_ramp_serves_via_produced_mana(self):
        self._ck(
            "ramp_matters",
            "you",
            [
                {
                    "name": "Birds",
                    "type_line": "Creature — Bird",
                    "oracle_text": "Flying\n{T}: Add one mana of any color.",
                    "produced_mana": ["W", "U", "B", "R", "G"],
                },
                {
                    "name": "Sol Ring",
                    "type_line": "Artifact",
                    "oracle_text": "{T}: Add {C}{C}.",
                    "produced_mana": ["C"],
                },
                {
                    "name": "Cultivate",
                    "type_line": "Sorcery",
                    "oracle_text": "Search your library for up to two basic land cards.",
                },
            ],
            [
                {
                    "name": "Bolt",
                    "type_line": "Instant",
                    "oracle_text": "deals 3 damage to any target.",
                }
            ],
        )

    def test_opponent_draw_drops_gift_effects(self):
        self._ck(
            "opponent_draw_matters",
            "opponents",
            [
                {
                    "name": "Bowmasters",
                    "type_line": "Creature — Orc Archer",
                    "oracle_text": "Whenever an opponent draws a card except the first one they draw in each of their draw steps, this creature deals 1 damage to any target.",
                }
            ],
            [
                {
                    "name": "Master of the Feast",
                    "type_line": "Creature — Demon",
                    "oracle_text": "Flying\nAt the beginning of your end step, each opponent draws a card.",
                }
            ],
        )

    def test_tokens_matter_anchors_token_enters(self):
        self._ck(
            "tokens_matter",
            "you",
            [
                {
                    "name": "Cathars Crusade",
                    "type_line": "Enchantment",
                    "oracle_text": "Whenever a creature you control enters, put a +1/+1 counter on each creature you control.\nTokens you control...",
                }
            ],
            [
                {
                    "name": "Darksteel Splicer",
                    "type_line": "Creature",
                    "oracle_text": "Whenever a nontoken creature you control enters, it becomes an artifact.",
                }
            ],
        )

    def test_exile_removal_excludes_blink(self):
        self._ck(
            "exile_removal",
            "you",
            [
                {
                    "name": "Swords",
                    "type_line": "Instant",
                    "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
                }
            ],
            [
                {
                    "name": "Ephemerate",
                    "type_line": "Instant",
                    "oracle_text": "Exile target creature you control, then return it to the battlefield under its owner's control.",
                }
            ],
        )

    def test_bounce_tempo_constrains_object(self):
        self._ck(
            "bounce_tempo",
            "you",
            [
                {
                    "name": "Boomerang",
                    "type_line": "Instant",
                    "oracle_text": "Return target permanent to its owner's hand.",
                }
            ],
            [
                {
                    "name": "Reprieve",
                    "type_line": "Instant",
                    "oracle_text": "Return target spell to its owner's hand. Its owner may play it again this turn.",
                }
            ],
        )

    def test_count_anthem_drops_self_scaling_branch(self):
        self._ck(
            "count_anthem",
            "you",
            [
                {
                    "name": "Intangible Virtue",
                    "type_line": "Enchantment",
                    "oracle_text": "Creatures you control get +1/+1 for each artifact you control.",
                }
            ],
            [
                {
                    "name": "Storm-Kiln Artist",
                    "type_line": "Creature — Dwarf Shaman",
                    "oracle_text": "Storm-Kiln Artist gets +1/+0 for each artifact you control.",
                }
            ],
        )

    def test_lifeloss_self_drops_painlands(self):
        self._ck(
            "lifeloss_matters",
            "you",
            [
                {
                    "name": "K'rrik",
                    "type_line": "Legendary Creature — Phyrexian Horror",
                    "oracle_text": "Whenever you lose life, ...\nBlack spells you cast cost {2} less and {2} life more.",
                }
            ],
            [
                {
                    "name": "Blood Crypt",
                    "type_line": "Land — Swamp Mountain",
                    "oracle_text": "As this land enters, you may pay 2 life. If you don't, it enters tapped.\n{T}: Add {B} or {R}.",
                }
            ],
        )

    def test_permanent_etb_recovers_etb_engines(self):
        self._ck(
            "permanent_etb",
            "you",
            [
                {
                    "name": "Panharmonicon",
                    "type_line": "Artifact",
                    "oracle_text": "If an artifact or creature entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
                }
            ],
            [],
        )

    def test_gain_control_requires_you_as_controller(self):
        self._ck(
            "gain_control",
            "you",
            [
                {
                    "name": "Control Magic",
                    "type_line": "Enchantment — Aura",
                    "oracle_text": "Enchant creature\nYou control enchanted creature.",
                }
            ],
            [
                {
                    "name": "Sky Swallower",
                    "type_line": "Creature — Leviathan",
                    "oracle_text": "When this creature enters, target opponent gains control of all other permanents you control.",
                }
            ],
        )


class TestMediumServeFixes2:
    """MEDIUM batch 7b: more serve recall/precision fixes."""

    def _ck(self, key, scope, plus, minus):
        sig = _sig(key, scope)
        for card in plus:
            assert serves(card, sig) is True, (key, card.get("name"))
        for card in minus:
            assert serves(card, sig) is False, (key, card.get("name"))

    def test_opponents_graveyard_recovers_hate_payoffs(self):
        self._ck(
            "graveyard_matters",
            "opponents",
            [
                {
                    "name": "Bojuka Bog",
                    "oracle_text": "Bojuka Bog enters tapped.\nWhen this land enters, exile target player's graveyard.\n{T}: Add {B}.",
                },
                {
                    "name": "Ruin Crab",
                    "oracle_text": "Landfall — Whenever a land you control enters, each opponent mills three cards.",
                },
            ],
            [
                {
                    "name": "Stitcher's Supplier",
                    "oracle_text": "When this creature enters or dies, mill three cards.",
                }
            ],
        )

    def test_opponent_search_requires_opponent_subject(self):
        self._ck(
            "opponent_search_matters",
            "opponents",
            [
                {
                    "name": "Aven Mindcensor",
                    "oracle_text": "Flash\nFlying\nIf an opponent would search a library, that player searches the top four cards of that library instead.",
                }
            ],
            [
                {
                    "name": "Path to Exile",
                    "oracle_text": "Exile target creature. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle.",
                }
            ],
        )

    def test_group_draw_each_drops_self_only_additional(self):
        self._ck(
            "card_draw_engine",
            "each",
            [
                {
                    "name": "Howling Mine",
                    "oracle_text": "At the beginning of each player's draw step, that player draws an additional card if Howling Mine is untapped.",
                }
            ],
            [
                {
                    "name": "Heightened Awareness",
                    "oracle_text": "When Heightened Awareness enters, draw a card.\nAt the beginning of your draw step, you may draw an additional card.",
                }
            ],
        )

    def test_cast_from_exile_is_payoffs_not_impulse(self):
        # Cast-from-exile is now the PAYOFF lane (rewards for casting from exile).
        # A rebound self-cast (Consuming Vapors) isn't an engine; and a pure impulse
        # enabler (Light Up the Stage) belongs to the separate impulse_top_play avenue,
        # not here.
        self._ck(
            "cast_from_exile",
            "you",
            [
                {
                    "name": "Exile Payoff",
                    "oracle_text": "Whenever you cast a spell from exile, draw a card.",
                }
            ],
            [
                {
                    "name": "Consuming Vapors",
                    "oracle_text": "Each player sacrifices a creature, then you gain life equal to the number of creatures that died this way.\nRebound",
                },
                {
                    "name": "Light Up the Stage",
                    "oracle_text": "Exile the top two cards of your library. Until the end of your next turn, you may play those cards.",
                },
            ],
        )

    def test_doubling_splits_token_and_counter_doublers(self):
        self._ck(
            "doubling_matters",
            "you",
            [
                {
                    "name": "Parallel Lives",
                    "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.",
                },
                {
                    "name": "Doubling Season",
                    "oracle_text": "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead. If an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on it instead.",
                },
            ],
            [
                {
                    "name": "Mycoloth",
                    "oracle_text": "Devour 2\nAt the beginning of your upkeep, create a 1/1 green Saproling creature token for each +1/+1 counter on this creature.",
                }
            ],
        )


class TestSweepHandSpecs:
    """Sweep keys that need a STRUCTURED serve (keyword/veto) the auto-registered
    oracle-only serve can't carry — given a hand-written SPECS override."""

    def test_excess_damage_serves_trample_bodies(self):
        sig = _sig("excess_damage", "you")
        pelakka = {
            "type_line": "Creature — Wurm",
            "oracle_text": "Trample\nWhen this creature enters, you gain 7 life.",
            "keywords": ["Trample"],
        }
        payoff = {
            "type_line": "Enchantment — Saga",
            "oracle_text": "If a creature you control would deal excess damage to a creature, deal that excess damage to its controller instead.",
        }
        vanilla = {"type_line": "Creature — Bear", "oracle_text": "", "keywords": []}
        assert serves(pelakka, sig) is True  # trample keyword
        assert serves(payoff, sig) is True  # excess damage payoff
        assert serves(vanilla, sig) is False

    def test_anthem_static_excludes_until_end_of_turn(self):
        sig = _sig("anthem_static", "you")
        glorious = {
            "type_line": "Enchantment",
            "oracle_text": "Creatures you control get +1/+1.",
        }
        overcome = {
            "type_line": "Sorcery",
            "oracle_text": "Creatures you control get +2/+2 and gain trample until end of turn.",
        }
        assert serves(glorious, sig) is True  # static anthem
        assert serves(overcome, sig) is False  # one-shot pump (until end of turn)

    def test_ltb_matters_excludes_o_ring_removal(self):
        sig = _sig("ltb_matters", "you")
        nikara = {
            "type_line": "Legendary Creature — Snake Cleric",
            "oracle_text": "Whenever another creature you control leaves the battlefield, target player loses 1 life and you gain 1 life.",
        }
        banishing = {
            "type_line": "Enchantment",
            "oracle_text": "When Banishing Light enters, exile target nonland permanent an opponent controls until Banishing Light leaves the battlefield.",
        }
        assert serves(nikara, sig) is True  # LTB payoff
        assert serves(banishing, sig) is False  # O-Ring exile-until-leaves


class TestMediumBatch8:
    """MEDIUM batch 8: sweep-regex surgeries + extraction/scope fixes."""

    def test_big_hand_excludes_stax_hand_size_refs(self):
        sig = _sig("big_hand_matters", "you")
        no_max = {
            "type_line": "Creature",
            "oracle_text": "You have no maximum hand size.",
        }
        ensnaring = {
            "type_line": "Artifact",
            "oracle_text": "Creatures with power greater than the number of cards in your hand can't attack.",
        }
        assert serves(no_max, sig) is True
        assert serves(ensnaring, sig) is False

    def test_counter_manipulation_requires_plus_one_counters(self):
        sig = _sig("counter_manipulation", "you")
        hex_parasite = {
            "type_line": "Artifact Creature — Insect",
            "oracle_text": "{X}, {T}: Remove X +1/+1 counters or X loyalty counters from target permanent.",
        }
        mana_bloom = {
            "type_line": "Enchantment",
            "oracle_text": "At the beginning of your upkeep, remove a charge counter from this enchantment. If you can't, sacrifice it.",
        }
        assert serves(hex_parasite, sig) is True
        assert serves(mana_bloom, sig) is False

    def test_life_total_set_drops_symmetric_damage_branch(self):
        sig = _sig("life_total_set", "any")
        mirror = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Exchange your life total with target opponent's life total.",
        }
        price = {
            "type_line": "Sorcery",
            "oracle_text": "Price of Progress deals damage to each player equal to twice the number of nonbasic lands that player controls.",
        }
        assert serves(mirror, sig) is True
        assert serves(price, sig) is False

    def test_creature_cast_trigger_recovers_you_cast(self):
        from mtg_utils._deck_forge.signals import extract_signals

        beast_whisperer = {
            "name": "Beast Whisperer",
            "type_line": "Creature — Elf Shaman",
            "oracle_text": "Whenever you cast a creature spell, draw a card.",
        }
        keys = {s.key for s in extract_signals(beast_whisperer)}
        assert "creature_cast_trigger" in keys

    def test_win_lose_game_self_win_not_mislabeled_opponents(self):
        from mtg_utils._deck_forge.signals import extract_signals

        felidar = {
            "name": "Felidar Sovereign",
            "type_line": "Creature — Cat Beast",
            "oracle_text": "Vigilance, lifelink\nAt the beginning of your upkeep, if you have 40 or more life, you win the game.",
        }
        sigs = [s for s in extract_signals(felidar) if s.key == "win_lose_game"]
        assert sigs and all(s.scope != "opponents" for s in sigs)


class TestMediumBatch9:
    def test_counter_distribute_is_board_wide_only(self):
        sig = _sig("counter_distribute", "you")
        cathars = {
            "type_line": "Enchantment",
            "oracle_text": "Whenever a creature you control enters, put a +1/+1 counter on each creature you control.",
        }
        venerable = {
            "type_line": "Creature — Human Knight",
            "oracle_text": "When this creature dies, put a +1/+1 counter on target Knight you control.",
        }
        assert serves(cathars, sig) is True
        assert serves(venerable, sig) is False

    def test_keyword_tribe_requires_payoff_anchor(self):
        from mtg_utils._deck_forge.signals import extract_signals, signal_keys

        praetors = {
            "name": "Hand of the Praetors",
            "type_line": "Creature — Phyrexian",
            "oracle_text": "Infect\nOther creatures with infect you control get +1/+0.\nWhenever you cast an Infect spell, ...",
        }
        whiptongue = {
            "name": "Whiptongue Hydra",
            "type_line": "Creature — Hydra",
            "oracle_text": "Reach\nWhen this creature enters, destroy all creatures with flying.",
        }
        praetor_kw = {
            s.subject
            for s in extract_signals(praetors)
            if s.key == signal_keys.KEYWORD_TRIBE
        }
        whip_kw = {
            s.subject
            for s in extract_signals(whiptongue)
            if s.key == signal_keys.KEYWORD_TRIBE
        }
        assert "Infect" in praetor_kw  # a real keyword-tribe anthem
        assert "Flying" not in whip_kw  # "destroy all creatures with flying" is removal


def test_play_from_top_is_its_own_avenue_and_excludes_look_at_top():
    """Play-from-top-of-library (Future Sight) is its own avenue — it casts from the
    LIBRARY, not exile, so it's neither impulse nor cast-from-exile. The serve requires a
    play/cast verb so look/scry/mill ("look at ... from the top", Stargaze) don't match.
    """
    top = _sig("play_from_top")
    cfe = _sig("cast_from_exile")
    stargaze = {
        "name": "Stargaze",
        "type_line": "Sorcery",
        "oracle_text": (
            "Look at twice X cards from the top of your library. Put X cards from "
            "among them into your hand and the rest into your graveyard. You lose X life."
        ),
    }
    future_sight = {
        "name": "Future Sight",
        "type_line": "Enchantment",
        "oracle_text": (
            "Play with the top card of your library revealed. You may play lands and "
            "cast spells from the top of your library."
        ),
    }
    # Future Sight serves play_from_top, NOT cast-from-exile (different zone).
    assert serves(future_sight, top)
    assert not serves(future_sight, cfe)
    # A look-at-top effect serves neither.
    assert not serves(stargaze, top)
    assert not serves(stargaze, cfe)
