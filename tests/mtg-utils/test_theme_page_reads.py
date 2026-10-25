"""The lane reads the pattern-free theme pages serve on (backlog item (o),
2026-10-25): each sub-avenue that dropped its oracle pattern pages by these
idents. Real cards only (ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def _cases(*rows: tuple[str, str, bool]):
    return pytest.mark.parametrize(("name", "ident", "has"), rows)


# ── counters ────────────────────────────────────────────────────────────────


@_cases(
    # a doubler of every counter kind over permanents reaches loyalty (CR 122.6)
    ("Doubling Season", "counter_doubling|you|loyalty", True),
    ("Gilder Bairn", "counter_doubling|you|loyalty", True),
    ("Hardened Scales", "counter_doubling|you|loyalty", False),  # +1/+1 only
    ("Hardened Scales", "counter_doubling|you|", True),
    # a one-shot doubler an ability grants
    ("Evolution Vat", "counter_doubling|you|", True),
    ("Level Up", "counter_doubling|you|", True),
    # removes counters and puts twice that many on itself: a mover
    ("Galloping Lizrog", "counter_doubling|you|", False),
)
def test_counter_doublers(name, ident, has):
    assert (ident in _idents(name)) is has


# ── tokens and copies ───────────────────────────────────────────────────────


@_cases(
    # an effect's token doubler for a turn, with the token owner named
    ("Kaya, Geist Hunter", "token_doubling|you|", True),
    # squad's enters trigger copies the card (CR 702.157a)
    ("Ruthless Radrat", "token_copy_makers|you|self", True),
    ("Ruthless Radrat", "self_etb_payload|you|", True),
    # a copier of creature spells makes token creatures (CR 707.10f)
    ("Double Major", "spell_copy_makers|you|creature", True),
    ("Volo, Guide to Monsters", "spell_copy_makers|you|creature", True),
    ("Reflections of Littjara", "spell_copy_makers|you|creature", True),
    ("Hatchery Sliver", "spell_copy_makers|you|creature", True),
    ("Twincast", "spell_copy_makers|you|creature", False),
    # a creature token an opponent creates
    ("Hunted Horror", "donate_makers|you|token", True),
    ("Phelddagrif", "donate_makers|you|token", True),  # an activation's
    ("Parting Gust", "donate_makers|you|token", False),  # a gift
)
def test_tokens_and_copies(name, ident, has):
    assert (ident in _idents(name)) is has


# ── sacrifice, death, enters ────────────────────────────────────────────────


@_cases(
    # the grant a Sliver gives itself among the Slivers
    ("Basal Sliver", "sacrifice_outlets|you|self", True),
    ("Mortarpod", "sacrifice_outlets|you|self", False),  # its germ's, not its own
    # soulshift the card gives itself (CR 702.46a)
    ("Kodama of the Center Tree", "self_death_payoff|you|", True),
    # a self-ETB value: a granted one, a "this or another" watcher, exploit
    ("Harmonic Sliver", "self_etb_payload|you|", True),
    ("Cephalid Sage", "self_etb_payload|you|", True),
    ("Angelic Sell-Sword", "self_etb_payload|you|", True),
    ("Silumgar Butcher", "self_etb_payload|you|", True),
    ("Henry Wu, InGen Geneticist", "self_etb_payload|you|", True),
    ("Adaptive Armorer", "self_etb_payload|you|", True),  # a spellbook draft
    ("Candlekeep Sage", "self_etb_payload|you|", False),  # its commander's
    ("Soul Warden", "self_etb_payload|you|", False),  # another creature entering
    # a creature card from your hand or graveyard (an InAnyZone choice)
    ("Swift Warkite", "permanent_recast|you|reanimate", True),
    # web-slinging's cost returns a tapped creature you control (CR 702.188a)
    ("Spider-Man, Web-Slinger", "permanent_recast|you|replay", True),
    ("Peter Parker // Amazing Spider-Man", "permanent_recast|you|replay", True),
)
def test_sacrifice_death_and_enters(name, ident, has):
    assert (ident in _idents(name)) is has


# ── combat, protection, burn ────────────────────────────────────────────────


@_cases(
    # a protective keyword given to a group of your permanents
    ("Heroic Intervention", "board_protection|you|indestructible", True),
    ("Heroic Intervention", "board_protection|you|hexproof", True),
    ("Darksteel Forge", "board_protection|you|indestructible", True),
    ("Divine Resilience", "board_protection|you|indestructible", False),  # targets
    ("Swiftfoot Boots", "board_protection|you|hexproof", False),  # one creature
    # burn that hits each opponent, a token's or a grant's included
    ("Boltwave", "direct_damage|you|each_opponent", True),
    ("Cornered by Black Mages", "direct_damage|you|each_opponent", True),
    ("Lightning Bolt", "direct_damage|you|each_opponent", False),
    # an attack compulsion on creatures beyond your own
    ("Warmonger Hellkite", "forced_attack|any|others", True),
    ("Alluring Siren", "forced_attack|any|others", True),
    ("Juggernaut", "forced_attack|any|others", False),  # itself
    ("Goblin Rabblemaster", "forced_attack|any|others", False),  # your Goblins
    # the one-shot team pump
    ("Banners Raised", "team_buff|you|pump", True),
    ("Wild Beastmaster", "team_buff|you|pump", True),
    ("Battle Frenzy", "team_buff|you|pump", False),  # green creatures only
    # the attacking part of the team, a P/T raise or a keyword (CR 508.1k)
    ("Jazal Goldmane", "team_buff|you|attackers", True),
    ("Waystone's Guidance", "team_buff|you|attackers", True),
    ("Neyali, Suns' Vanguard", "team_buff|you|attackers", True),
    ("Tourach's Gate", "team_buff|you|attackers", False),  # +2/-1: mixed
    # the team's base P/T set, an emblem's included
    ("Biomass Mutation", "team_buff|you|base_pt", True),
    ("The Capitoline Triad", "team_buff|you|base_pt", True),
    ("Creeperhulk", "team_buff|you|base_pt", False),  # one target
    # an anthem over your tokens, one the card gives its commander included
    ("Inspiring Leader", "team_buff|you|tokens", True),
    ("Intangible Virtue", "team_buff|you|tokens", True),
    # a keyword the team gains from a choice
    ("Angelic Skirmisher", "team_buff|you|keyword", True),
    # an enters trigger that gives other Equipment a free attach
    ("Hammer of Nazahn", "voltron_makers|you|", True),
    ("Sigarda's Aid", "voltron_makers|you|", True),
    ("Foot Chopper", "voltron_makers|you|", False),  # attaches only itself
)
def test_combat_protection_and_burn(name, ident, has):
    assert (ident in _idents(name)) is has


# ── engines and payoffs ─────────────────────────────────────────────────────


@_cases(
    # activations sooner (CR 302.6) or cheaper
    ("Thousand-Year Elixir", "activated_ability|you|enabler", True),
    ("Training Grounds", "activated_ability|you|enabler", True),
    ("Heartstone", "activated_ability|you|enabler", True),
    ("Power Artifact", "activated_ability|you|enabler", True),
    ("Suppression Field", "activated_ability|you|enabler", False),  # a tax
    # untap every land you control
    ("Wilderness Reclamation", "mana_amplifier|you|untap_lands", True),
    ("Seedborn Muse", "mana_amplifier|you|untap_lands", True),
    ("Mana Reflection", "mana_amplifier|you|untap_lands", False),
    # a payoff on an opponent's discard
    ("Megrim", "opponent_discard|opponents|punish", True),
    ("Tinybones, Pocket Nuisance", "opponent_discard|opponents|punish", True),
    ("Mind Rot", "opponent_discard|opponents|punish", False),  # the attack
    ("Bone Miser", "opponent_discard|opponents|punish", False),  # yours
    ("Basking Rootwalla", "opponent_discard|opponents|punish", False),  # madness
    # an enters-caused trigger doubler
    ("Panharmonicon", "trigger_doubling|you|enters", True),
    ("Gandalf the White", "trigger_doubling|you|enters", True),
    ("Teysa Karlov", "trigger_doubling|you|enters", False),  # dying
    # a creature-spell discount
    ("Herald's Horn", "cost_reduction|you|creature", True),
    ("Krosan Drover", "cost_reduction|you|creature", True),
    ("Geist of Saint Thalia", "cost_reduction|you|creature", False),
    # cast-from-exile payoffs and paradox (CR 207.2c)
    ("Wild-Magic Sorcerer", "cast_from_exile|you|payoff", True),
    ("Party Thrasher", "cast_from_exile|you|payoff", True),
    ("Charred Foyer // Warped Space", "cast_from_exile|you|payoff", True),
    ("Vega, the Watcher", "cast_from_exile|you|paradox", True),
    ("Spider-Man 2099", "cast_from_exile|you|paradox", True),
    ("Act on Impulse", "cast_from_exile|you|payoff", False),  # the enabler
)
def test_engines_and_payoffs(name, ident, has):
    assert (ident in _idents(name)) is has
