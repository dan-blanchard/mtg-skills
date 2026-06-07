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
        assert extra_labels == ["Dryad payoffs"]
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
