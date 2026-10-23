"""Serve-ident pins for the data_2 specs converted off their oracle regex
(docs/plans/serve-idents-and-avenue-support.md, Pass A, 2026-10-18; the third
pass, 2026-10-20).

Each converted spec serves on the lanes' own structural idents instead of an
oracle regex. Per spec: the regex arm is gone, the ident is on the serve, a real
card on theme serves, a card the regex MISSED now serves, and a card the regex
wrongly served no longer does (where such cards exist).
"""

import pytest

from mtg_utils._analysis.signal_specs import serve_from_dict, spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name* (ADR-0056), with its crosswalk trees
    memo seeded first — so a serve's structural ``signal_idents`` arm reads the
    card's real idents in CI exactly as it does locally (no phase cache)."""
    test_card_ir(name)
    return test_card(name)


def _lane_covers(card, sig):
    """True if a card is surfaced by the lane via its main serve OR any sub-avenue —
    mirroring how the engine renders an avenue plus its extras."""
    spec = spec_for(sig)
    if spec is None:
        return False
    if spec.serve.matches(card):
        return True
    return any(
        (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in spec.extras
    )


# key, scope, ident, served (both arms), gained (regex missed), dropped (regex
# wrongly served). ``gained`` / ``dropped`` are None where the idents reproduce
# the regex exactly.
_CASES = [
    (
        "combat_damage_to_creature",
        "any",
        "combat_damage_to_creature|any|",
        "Serpentine Basilisk",
        None,
        None,
    ),
    (
        "party_matters",
        "you",
        "party_matters|you|",
        "Synchronized Spellcraft",
        None,
        "Champions from Beyond",
    ),
    ("monarch_makers", "you", "monarch_makers|you|", "Keeper of Keys", None, None),
    ("monarch_matters", "you", "monarch_matters|you|", "Keeper of Keys", None, None),
    (
        "devotion_matters",
        "you",
        "devotion_matters|you|",
        "Erebos, God of the Dead",
        "Heartlash Cinder",
        None,
    ),
    (
        "unspent_mana",
        "you",
        "unspent_mana|you|",
        "Kruphix, God of Horizons",
        None,
        None,
    ),
    (
        "void_warp_matters",
        "you",
        "void_warp_makers|you|",
        "Starfield Vocalist",
        "Astelli Reclaimer",
        None,
    ),
    ("void_warp_makers", "you", "void_warp_makers|you|", "Timeline Culler", None, None),
    ("dig_until", "you", "dig_until|you|", "Avenging Druid", "Sweet-Gum Recluse", None),
    (
        "draw_for_each",
        "you",
        "draw_for_each|you|",
        "Accumulated Knowledge",
        "Be'lakor, the Dark Master",
        "Deadly Cover-Up",
    ),
    (
        "celebration_matters",
        "you",
        "celebration_matters|you|",
        "Grand Ball Guest",
        None,
        None,
    ),
    (
        "initiative_makers",
        "you",
        "initiative_makers|you|",
        "Aarakocra Sneak",
        None,
        None,
    ),
    (
        "initiative_matters",
        "you",
        "initiative_matters|you|",
        "Aarakocra Sneak",
        None,
        None,
    ),
    (
        "ring_matters",
        "you",
        "ring_tempters|you|",
        "Call of the Ring",
        "Boromir, Warden of the Tower",
        "Lord of the Nazgûl",
    ),
    (
        "ring_tempters",
        "you",
        "ring_matters|you|",
        "Call of the Ring",
        "Sauron, the Necromancer",
        None,
    ),
    ("historic_matters", "you", "historic_matters|you|", "Curator's Ward", None, None),
    (
        "experience_makers",
        "you",
        "experience_makers|you|",
        "Daxos the Returned",
        None,
        None,
    ),
    (
        "experience_matters",
        "you",
        "experience_matters|you|",
        "Daxos the Returned",
        None,
        None,
    ),
    (
        "poison_makers",
        "opponents",
        "poison_makers|opponents|",
        "Bilious Skulldweller",
        None,
        None,
    ),
    (
        "poison_matters",
        "opponents",
        "poison_matters|opponents|",
        "Bilious Skulldweller",
        None,
        None,
    ),
    ("has_mutate", "you", "has_mutate|you|", "Gemrazer", None, None),
    (
        "clue_matters",
        "you",
        "clue_makers|you|",
        "Bygone Bishop",
        "Tangletrove Kelp",
        None,
    ),
    (
        "clue_makers",
        "you",
        "clue_matters|you|",
        "Bygone Bishop",
        "Tangletrove Kelp",
        None,
    ),
    ("blood_makers", "you", "blood_makers|you|", "Bloodtithe Harvester", None, None),
    ("blood_matters", "you", "blood_matters|you|", "Bloodtithe Harvester", None, None),
    ("daynight_makers", "you", "daynight_makers|you|", "Brimstone Vandal", None, None),
    (
        "daynight_matters",
        "you",
        "daynight_matters|you|",
        "Brimstone Vandal",
        None,
        None,
    ),
    ("coven_matters", "you", "coven_matters|you|", "Augur of Autumn", None, None),
    (
        "second_spell_matters",
        "you",
        "second_spell_matters|you|",
        "Cori-Steel Cutter",
        "Ledger Shredder",
        None,
    ),
    # Third pass (2026-10-20).
    (
        "direct_damage",
        "you",
        "direct_damage|you|",
        "Ankh of Mishra",
        "Anathemancer",
        "Abrade",
    ),
    (
        "superfriends_matters",
        "you",
        "superfriends_matters|you|",
        "Ajani Goldmane",
        "Historian of Zhalfir",
        "Ever-Watching Threshold",
    ),
    (
        "cost_reduction",
        "you",
        "cost_reduction|you|*",
        "Baral, Chief of Compliance",
        "Baral, Chief of Compliance",
        "Storm of Souls",
    ),
    (
        "play_from_top",
        "you",
        "play_from_top|you|",
        "Future Sight",
        "The Lunar Whale",
        "Maelstrom Nexus",
    ),
    ("cantrip", "you", "cantrip|you|", "Preordain", None, "Agent Venom"),
    (
        "land_sacrifice_matters",
        "you",
        "land_sacrifice_makers|you|",
        "Zuran Orb",
        "Harrow",
        None,
    ),
    (
        "land_sacrifice_makers",
        "you",
        "land_sacrifice_matters|you|",
        "Zuran Orb",
        "Harrow",
        None,
    ),
    (
        "counter_doubling",
        "you",
        "plus_one_makers|you|",
        "Bloodspore Thrinax",
        "Hardened Scales",
        None,
    ),
    (
        "topdeck_selection",
        "you",
        "topdeck_selection|you|",
        "Aminatou's Augury",
        "Dissolve",
        "Thrumming Stone",
    ),
    (
        "mana_amplifier",
        "you",
        "mana_amplifier|you|",
        "Mana Reflection",
        "Mana Flare",
        "Blast Zone",
    ),
    (
        "exile_matters",
        "you",
        "exile_matters|you|",
        "Cosmogoyf",
        "Kaya, Spirits' Justice",
        None,
    ),
    (
        "theft_protection",
        "you",
        "gain_control|you|",
        "Empress Galina",
        "Control Magic",
        None,
    ),
    (
        "legends_matter",
        "you",
        "legends_matter|you|",
        "Aang, the Last Airbender",
        "Loyal Retainers",
        "Ironwill Forger",
    ),
    (
        "group_mana",
        "each",
        "group_mana|each|",
        "Magus of the Vineyard",
        "Mana Flare",
        None,
    ),
]


@pytest.mark.parametrize(
    ("key", "scope", "ident", "served", "gained", "dropped"),
    _CASES,
    ids=[f"{c[0]}|{c[1]}" for c in _CASES],
)
def test_serve_is_the_lanes_idents(key, scope, ident, served, gained, dropped):
    spec = spec_for(_sig(key, scope))
    assert spec.serve.oracle is None
    assert ident in spec.serve.signal_idents
    assert spec.serve.matches(_card(served)) is True
    if gained is not None:
        assert spec.serve.matches(_card(gained)) is True
    if dropped is not None:
        assert _lane_covers(_card(dropped), _sig(key, scope)) is False
    # Over-fire guard: a vanilla creature feeds none of these avenues.
    assert spec.serve.matches(_card("Grizzly Bears")) is False


def test_combat_damage_to_opp_serves_idents_and_cipher():
    # The sweep spec drops its serve regex for the lanes' idents; the regex stays
    # on the search side. The regex missed the "one of your opponents" payoffs
    # (Edric). Cipher grants the same combat-damage-to-a-player trigger
    # (CR 702.99a), which the regex reached only through reminder text: the
    # keyword dimension keeps Last Thoughts on the serve.
    spec = spec_for(_sig("combat_damage_to_opp", "opponents"))
    assert spec.serve.oracle is None
    assert spec.search["oracle"]
    assert "combat_damage_to_opp|opponents|" in spec.serve.signal_idents
    assert "cipher" in spec.serve.keywords
    assert spec.serve.matches(_card("Ninja of the Deep Hours")) is True
    assert spec.serve.matches(_card("Edric, Spymaster of Trest")) is True
    assert spec.serve.matches(_card("Last Thoughts")) is True
    assert spec.serve.matches(_card("Grizzly Bears")) is False


@pytest.mark.parametrize("key", ["discard_makers", "discard_matters", "discard_outlet"])
def test_discard_serve_reads_costs_connive_and_blood(key):
    spec = spec_for(_sig(key))
    assert spec.serve.oracle is None
    assert spec.search["oracle"]
    serve = spec.serve
    # Outlets, a discard cost you pay (CR 701.9a), random included (CR 701.9b:
    # a payoff fires whichever card goes), and the payoffs.
    for name in (
        "Fauna Shaman",
        "Lion's Eye Diamond",
        "Burning Inquiry",
        "Amok",
        "Bone Miser",
        "Glint-Horn Buccaneer",
    ):
        assert serve.matches(_card(name)), name
    # The regex missed these: connive printed without its reminder text (CR
    # 701.50a), a "whenever you cycle or discard" payoff, and a granted connive.
    assert serve.matches(_card("Baron Helmut Zemo"))
    assert serve.matches(_card("Drake Haven"))
    assert serve.matches(_card("Security Bypass"))
    # A Blood token rummages (CR 111.10g); the regex read only its reminder text.
    assert serve.matches(_card("Blood Servitor"))
    # The opponents discard (opponent_discard); the regex served "discard two".
    assert not serve.matches(_card("Skull Rend"))
    assert not serve.matches(_card("Mind Rot"))
    # Cycling's "Discard this card" is the cycling lanes' read.
    assert not serve.matches(_card("Krosan Tusker"))
    assert not serve.matches(_card("Grizzly Bears"))


def test_low_power_serve_reads_the_cast_from_the_top_permission():
    spec = spec_for(_sig("low_power_matters"))
    assert spec.serve.oracle is None
    assert "low_power_matters|you|" in spec.serve.signal_idents
    # The lane reads the power ceiling on a cast-from-the-top permission, the
    # regex's "creature spell with power N or less" arm.
    assert spec.serve.matches(_card("Assemble the Players"))
    # A low-power reanimator the regex missed.
    assert spec.serve.matches(_card("Reveillark"))
    assert not spec.serve.matches(_card("Vizier of the Menagerie"))


def test_modified_serve_is_the_payoffs_and_the_counter_package():
    spec = spec_for(_sig("modified_matters"))
    assert spec.serve.oracle is None
    assert {"modified_matters|you|", "plus_one_makers|you|"} <= (
        spec.serve.signal_idents
    )
    # A modified payoff the lane missed until it read the gating condition.
    assert spec.serve.matches(_card("Kami's Flare"))
    # Every counter is a modification (CR 700.9): proliferate feeds the avenue.
    assert spec.serve.matches(_card("Atraxa, Praetors' Voice"))
    # Equipment and Auras still serve by type.
    assert spec.serve.matches(_card("Glowcap Lantern"))
    # The regex served a hoser off "+1/+1 counters".
    assert not spec.serve.matches(_card("Blightbeetle"))


def test_x_spell_serves_read_the_printed_cost():
    # big_mana (the X-spell sinks) and mana_amplifier serve the X-spells by their
    # printed mana cost, as xspell_matters reads them: the sink is the {X} you
    # pay. The "deals X damage" regex served X set by a count, not by mana.
    big = spec_for(_sig("big_mana"))
    assert big.serve.oracle is None
    assert big.serve.mana_cost is not None
    assert big.serve.matches(_card("Comet Storm"))
    # An X-spell that deals no damage (the regex missed it).
    assert big.serve.matches(_card("Torment of Hailfire"))
    # X is the cards in that player's hand minus four — no mana sink.
    assert not big.serve.matches(_card("Black Vise"))
    assert not big.serve.matches(_card("Grizzly Bears"))
    amp = spec_for(_sig("mana_amplifier"))
    assert amp.serve.matches(_card("Torment of Hailfire"))


def test_cost_reduction_storm_is_a_keyword_sub_avenue():
    # The serve regex was ``\bstorm\b`` (cards named Storm included); storm
    # (CR 702.40a) is adjacency the discount chains into, read off the keyword in
    # its own sub-avenue.
    sig = _sig("cost_reduction")
    spec = spec_for(sig)
    assert spec.serve.oracle is None
    assert not spec.serve.matches(_card("Grapeshot"))
    assert _lane_covers(_card("Grapeshot"), sig)
    # A card named Storm without the keyword feeds neither.
    assert not _lane_covers(_card("Storm of Souls"), sig)


def test_self_lifeloss_serves_idents_including_life_lost_this_turn():
    # Self life-loss serves on the lanes' idents alone: the payers and losers, the
    # pay-life insurance and the life-total swaps. The lane reads "the life you've
    # lost this turn" itself, so the old regex bridge is gone.
    for key in ("lifeloss_matters", "lifeloss_makers"):
        serve = spec_for(_sig(key)).serve
        assert serve.oracle is None
        assert {"lifeloss_makers|you|", "life_payment_insurance|you|"} <= (
            serve.signal_idents
        )
        assert serve.matches(_card("Axis of Mortality")), key
        # "Lose life equal to its mana value" — the regex read only "N life".
        assert serve.matches(_card("Dark Confidant")), key
        assert serve.matches(_card("Children of Korlis")), key
        # An opponent drain: the old "gain life equal to the life lost" arm.
        assert not serve.matches(_card("Exsanguinate")), key
        assert not serve.matches(_card("Grizzly Bears")), key


def test_flying_granters_are_a_sub_avenue():
    # Evasive attackers serve the fliers (the keyword); the flying granters are
    # adjacency, their regex moved verbatim into a sub-avenue.
    sig = _sig("nonhuman_attackers")
    spec = spec_for(sig)
    assert spec.serve.oracle is None
    assert spec.serve.matches(_card("Aerial Responder"))
    assert not spec.serve.matches(_card("Akroma's Memorial"))
    assert _lane_covers(_card("Akroma's Memorial"), sig)
    assert not _lane_covers(_card("Grizzly Bears"), sig)
    # The sub-avenue serves the grant lanes' flying idents, not the regex.
    (granters,) = spec.extras
    assert granters.serve.oracle is None
    assert "keyword_grant_target|you|flying" in granters.serve.signal_idents


# Phase C (2026-10-22): the specs the Phase B lane fixes freed.
# key, scope, ident the serve must carry, served card, dropped (or None).
_PHASE_C = [
    ("voting_makers", "each", "voting_makers|each|", "Capital Punishment"),
    ("voting_matters", "each", "voting_matters|each|", "Grudge Keeper"),
    ("domain_matters", "you", "domain_matters|you|", "Prismatic Omen"),
    ("cast_from_exile", "you", "cast_from_exile|you|", "Hostage Taker"),
    (
        "lifeloss_matters",
        "opponents",
        "lifeloss_makers|opponents|",
        "Gray Merchant of Asphodel",
    ),
    (
        "lifeloss_makers",
        "opponents",
        "lifeloss_matters|opponents|",
        "Gray Merchant of Asphodel",
    ),
    ("land_sacrifice_makers", "you", "land_sacrifice_makers|each|", "Tremble"),
    ("lands_matter", "you", "landfall|you|", "Rampant Growth"),
    ("tapped_matters", "you", "tapped_matters|you|", "Throne of the God-Pharaoh"),
    (
        "card_draw_engine",
        "each",
        "group_hug_draw|each|",
        "Nekusar, the Mindrazer",
    ),
    ("theft_makers", "opponents", "theft_makers|opponents|", "Hostage Taker"),
    ("wants_theft", "opponents", "theft_makers|opponents|", "Hostage Taker"),
    ("one_punch", "you", "keyword_grant_target|you|infect", "Tainted Strike"),
    (
        "combat_damage_matters",
        "opponents",
        "evasion_self|you|unblockable",
        "Invisible Stalker",
    ),
]


@pytest.mark.parametrize(
    ("key", "scope", "ident", "served"),
    _PHASE_C,
    ids=[f"{c[0]}|{c[1]}" for c in _PHASE_C],
)
def test_phase_c_serve_is_idents(key, scope, ident, served):
    spec = spec_for(_sig(key, scope))
    assert spec.serve.oracle is None
    assert ident in spec.serve.signal_idents
    assert spec.serve.matches(_card(served)) is True
    assert spec.serve.matches(_card("Grizzly Bears")) is False


def test_cast_from_exile_keeps_keywords_and_adds_warp():
    serve = spec_for(_sig("cast_from_exile")).serve
    assert {"plot", "suspend", "foretell", "rebound", "warp"} <= serve.keywords
