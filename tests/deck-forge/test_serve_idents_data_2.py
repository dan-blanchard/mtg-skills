"""Serve-ident pins for the data_2 specs converted off their oracle regex
(docs/plans/serve-idents-and-avenue-support.md, Pass A, 2026-10-18).

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
