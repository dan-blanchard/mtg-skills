"""The lane reads the pattern-free theme pages serve on (backlog item (o),
2026-10-25): each sub-avenue that dropped its oracle pattern pages by these
idents. Real cards only (ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import spared_types
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_phase_records, test_signals


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


# ── the second pass: sub-avenues that dropped their pattern ─────────────────


@_cases(
    # a body that blocks more than one attacker — the soak blocker
    ("Palace Guard", "extra_blockers|you|any", True),
    ("Brave the Sands", "extra_blockers|you|", True),
    ("Night Market Guard", "extra_blockers|you|", True),
    ("Night Market Guard", "extra_blockers|you|any", False),  # one more only
    # a token of yours leaving drains (Nadier's Nightblade)
    ("Nadier's Nightblade", "tokens_matter|you|drain", True),
    ("Anointed Procession", "tokens_matter|you|drain", False),
    # an activation that makes a token and drains in one resolution
    ("Rotwidow Pack", "tokens_matter|you|drain", True),
    # two or more creature tokens at once
    ("Siege-Gang Commander", "mass_token_makers|you|", True),
    ("Battle Screech", "mass_token_makers|you|", True),
    ("Dragon Roost", "mass_token_makers|you|", False),  # one at a time
    # a copier of triggered abilities (CR 707.10)
    ("Strionic Resonator", "ability_copy|you|triggered", True),
    ("Rings of Brighthearth", "ability_copy|you|triggered", False),  # activated
    # a payoff on an opponent's empty or small hand (CR 402.1)
    ("Rackling", "opponent_discard|opponents|empty_hand", True),
    ("Mind Rot", "opponent_discard|opponents|empty_hand", False),
    # symmetric mana: every player's land taps (CR 106.12a), every player's ramp
    ("Mana Flare", "group_mana|each|land_tap", True),
    ("Veteran Explorer", "group_mana|each|ramp", True),
    ("Kami of the Crescent Moon", "group_mana|each|ramp", False),  # cards
)
def test_bodies_tokens_and_symmetry(name, ident, has):
    assert (ident in _idents(name)) is has


@_cases(
    # a pump on one chosen creature (CR 115.1a), never a team pump
    ("Brute Force", "pump_makers|you|target", True),
    ("Charge", "pump_makers|you|target", False),
    # a quoted ability one target gains
    ("Retraction Helix", "keyword_grant_target|you|ability", True),
    ("Giant Growth", "keyword_grant_target|you|ability", False),
    # damage dealt again (Hydra Omnivore), life lost again (Wound Reflection)
    ("Hydra Omnivore", "damage_doubling|you|repeat", True),
    ("Wound Reflection", "damage_doubling|you|life_loss", True),
    ("Fiery Emancipation", "damage_doubling|you|repeat", False),  # a doubler
    # a fight-shaped bite: damage equal to power to a creature (CR 208.1)
    ("Ambuscade", "damage_equal_power|you|creature", True),
    # a creature of yours entering burns or drains
    ("Impact Tremors", "creature_etb|you|punish", True),
    ("Trespasser's Curse", "creature_etb|you|punish", False),  # theirs entering
    ("Soul Warden", "creature_etb|you|punish", False),  # a life gain
    # a land of yours returned to untap (Quirion Ranger)
    ("Quirion Ranger", "land_return_untap|you|", True),
    ("Simic Growth Chamber", "land_return_untap|you|", False),
    # an untap ability a card hands others: a trigger's "untap it", a {Q} cost
    # (CR 107.6)
    ("Dionus, Elvish Archdruid", "untap_engine|you|Elf", True),
    ("Umbral Mantle", "untap_engine|you|", True),
)
def test_combat_and_damage_reads(name, ident, has):
    assert (ident in _idents(name)) is has


@_cases(
    # the card hurts its controller (CR 701.21a / 119.3 / 701.17a / 104.3)
    ("Demonic Taskmaster", "self_drawback|you|harm", True),
    ("Bitterblossom", "self_drawback|you|harm", True),
    ("Phage the Untouchable", "self_drawback|you|harm", True),
    ("Tolarian Serpent", "self_drawback|you|harm", True),  # mills seven a turn
    ("Splinterfright", "self_drawback|you|harm", False),  # it reads the mill
    ("Ob Nixilis, Unshackled", "self_drawback|you|harm", False),  # theirs
    ("Phyrexian Arena", "self_drawback|you|harm", False),  # pays for a draw
    # the card holds itself back (CR 508.1c, CR 702.24a)
    ("Sea Serpent", "self_drawback|you|restriction", True),
    ("Aboroth", "self_drawback|you|restriction", True),
    # a filter naming a subtype (CR 205.3), on either side or yours
    ("Goblin Grenade", "subtype_ref|you|Goblin", True),
    ("Opportunistic Dragon", "subtype_ref|any|Human", True),
    ("Opportunistic Dragon", "subtype_ref|you|Human", False),  # an opponent's
    ("Coat of Arms", "subtype_ref|you|shared", True),
    # a keyword put on bodies of yours: a grant, a token's, a counter (CR 122.1b)
    ("Jump", "keyword_bodies|you|flying", True),
    ("Battle Screech", "keyword_bodies|you|flying", True),
    ("Agent's Toolkit", "keyword_bodies|you|flying", True),
    ("Plummet", "keyword_bodies|you|flying", False),
    # a meld card names its partner (CR 701.42a)
    ("Gisela, the Broken Blade", "meld_pair|you|Bruna, the Fading Light", True),
    # embalm's token is a Zombie (CR 702.128a)
    ("Aven Initiate", "token_maker|you|Zombie", True),
)
def test_drawbacks_subtypes_and_keywords(name, ident, has):
    assert (ident in _idents(name)) is has


# ── the tribe pages' last pass: the references the pattern alone paged ───────


@_cases(
    # a keyword's creature-type parameter (CR 702.48a offering)
    ("Patron of the Akki", "subtype_ref|you|Goblin", True),
    # a behold or reveal cost, additional or buying flash (CR 701.4a)
    ("Champion of the Weird", "subtype_ref|you|Goblin", True),
    ("Dragonlord's Prerogative", "subtype_ref|you|Dragon", True),
    ("Molten Exhale", "subtype_ref|you|Dragon", True),
    # a casting condition (CR 601.3)
    ("Feast of Blood", "subtype_ref|you|Vampire", True),
    # mana spendable only on the type's spells (CR 106.6)
    ("Crucible of the Spirit Dragon", "subtype_ref|you|Dragon", True),
    # a mass effect that spares the type (CR 115.10), not a target restriction
    ("Eyeblight Massacre", "subtype_ref|you|Elf", True),
    ("Call to the Grave", "subtype_ref|you|Zombie", True),
    ("Victim of Night", "subtype_ref|you|Zombie", False),
    ("Anowon, the Ruin Sage", "subtype_ref|you|Vampire", True),
    # a mass pump and a sacrifice only you make spare nothing
    ("Return of the Wildspeaker", "subtype_ref|any|Human", False),
    ("Archdemon of Unx", "subtype_ref|any|Zombie", False),
    # a dig names its type by the cards it keeps (its "the rest" spares
    # nothing: test_spared_types)
    ("Goblin Ringleader", "subtype_ref|you|Goblin", True),
    # a misread grant's stray words are no subtype
    ("Will of the Temur", "subtype_ref|you|Flying", False),
    ("Will of the Temur", "subtype_ref|any|Dragon", True),
    # a type the card grants pages the main page only: the enabler, no payoff
    ("Will of the Temur", "subtype_ref|you|Dragon", False),
)
def test_tribe_references(name, ident, has):
    assert (ident in _idents(name)) is has


@_cases(
    # a count of the chosen type, a cost, a damage doubler, a reveal to hand
    ("Caller of the Hunt", "chosen_type_matters|you|", True),
    ("Doom Cannon", "chosen_type_matters|you|", True),
    ("Collective Inferno", "chosen_type_matters|you|", True),
    ("Bloodline Shaman", "chosen_type_matters|you|", True),
    # a sweep that spares the chosen type
    ("Kindred Dominance", "chosen_type_matters|you|", True),
    # a prevention against the type and a -1/-1 to an opponent's are no payoff
    ("Circle of Solace", "chosen_type_matters|you|", False),
    ("Plague Engineer", "chosen_type_matters|you|", False),
    # a token of a type chosen from a printed list
    ("Sarpadian Empires, Vol. VII", "token_maker|you|Goblin", True),
)
def test_chosen_type_payoffs_and_tokens(name, ident, has):
    assert (ident in _idents(name)) is has


@_cases(
    # a keyword counter a creature enters with or gets at random (CR 122.1b)
    ("Ascent of the Worthy", "keyword_bodies|you|flying", True),
    ("Crystalline Giant", "keyword_bodies|you|flying", True),
    # a token copy with the keyword, a replacement's added token
    ("Haunting Imitation", "keyword_bodies|you|flying", True),
    ("Stridehangar Automaton", "keyword_bodies|you|flying", True),
    # a keyword chosen for itself, an Alchemy perpetual grant
    ("Gabriel Angelfire", "keyword_bodies|you|flying", True),
    ("Second Little Pig", "keyword_bodies|you|flying", True),
    # a crewed Vehicle token becomes a creature (CR 702.122a)
    ("Lita, Mechanical Engineer", "keyword_bodies|you|flying", True),
    # "each player other than target player" includes its caster (its ruling:
    # the targeted player is the only one who gets no Dragon) — a ledger row
    ("Death by Dragons", "keyword_bodies|you|flying", True),
    # another player's token
    ("Hunted Troll", "keyword_bodies|you|flying", False),
)
def test_keyword_bodies_followed(name, ident, has):
    assert (ident in _idents(name)) is has


@pytest.mark.parametrize(
    ("name", "subtype", "has"),
    [
        ("Goblin Ringleader", "", False),  # "the rest on the bottom" moves no permanent
        ("Archdemon of Unx", "", False),  # a sacrifice only you make
        ("Return of the Wildspeaker", "", False),  # a mass pump rewards the others
        ("Anowon, the Ruin Sage", "Vampire", True),  # each player's edict
        ("Eyeblight Massacre", "Elf", True),  # a mass shrink
    ],
)
def test_spared_types(name, subtype, has):
    (tree, *_) = trees_for(test_card(name))
    spared = spared_types(tree).subtypes
    assert bool(spared) is has
    if has:
        assert subtype in spared


def _effect_nodes(name: str, tag: str) -> list[dict]:
    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == tag:
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    return [n for rec in test_phase_records(name) for n in walk(rec)]


@pytest.mark.retirement_canary
def test_chosen_token_type_canary():
    """Retirement canary for ``crosswalk.made_token_subtypes``' ``"chosen"``
    arm: phase v0.104.0 types no "of the chosen color and type" on Sarpadian
    Empires, Vol. VII's token, so the read joins it to the card's printed-list
    choice."""
    (token,) = _effect_nodes("Sarpadian Empires, Vol. VII", "Token")
    assert token.get("types") == ["Creature"], (
        "made_token_subtypes: RETIRE-READY — phase types Sarpadian Empires' token "
        "now. Drop the 'chosen' arm (and this canary) if the token reads its type."
    )
    assert "token_maker|you|Goblin" in _idents("Sarpadian Empires, Vol. VII")


@pytest.mark.retirement_canary
def test_stray_grant_subtype_canary():
    """Retirement canary for ``crosswalk.reads._SUBTYPE_WORDS``' gate on a
    granted subtype: phase v0.104.0 reads Will of the Temur's "except it's a 4/4
    Dragon creature with flying" as the subtypes ``With`` and ``Flying``."""
    subs = {n.get("subtype") for n in _effect_nodes("Will of the Temur", "AddSubtype")}
    assert "Flying" in subs, (
        "_SUBTYPE_WORDS: RETIRE-READY for Will of the Temur — phase no longer "
        "reads its keyword as a subtype. Retire dropped_keywords."
        "_misread_subtype_lists once no card is left, and check whether the gate "
        "still guards a card."
    )
    assert "subtype_ref|any|Flying" not in _idents("Will of the Temur")
