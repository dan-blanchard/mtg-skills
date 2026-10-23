"""Phase B lane gaps, evasion slice: ``evasion_self`` fires one subject per
evasion kind (CR 509.1b), island makers read the effects that make lands
Islands (CR 305.7) and the opponent-Island payoffs, and ``arcane_matters``
stops firing on the word "Arcane" in a name (CR 205.3k / 702.47a).

Every card is a real one, read through the production ``extract_signals``
(``mtg_utils.testkit.test_signals``, ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _subjects(name: str, key: str) -> set[str]:
    return {subj for k, _scope, subj in _idents(name) if k == key}


# ── evasion_self: one subject per kind ───────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Slither Blade", "unblockable"),  # printed "can't be blocked"
        ("Aether Figment", "unblockable"),
        ("Whispersilk Cloak", "unblockable"),  # the equipped creature
        ("Rogue's Passage", "unblockable"),  # one target, this turn
        # "Target creature gets +1/+0 and can't be blocked this turn": the
        # conferred def carries no ``affected`` — the Pump's one target.
        ("Distortion Strike", "unblockable"),
        # "During your turn": a creature only attacks on its controller's
        # turn (CR 506.2), so no condition gates the attack.
        ("Bilbo's Ring", "unblockable"),
        ("Trailblazer's Boots", "landwalk"),  # nonbasic landwalk, CR 702.14c
        ("Boggart Brute", "menace"),  # CR 702.111b
        ("Accursed Spirit", "intimidate"),
        ("Grimdancer", "menace"),  # a menace counter on itself, CR 122.1b
        ("Dauthi Embrace", "shadow"),  # target creature gains shadow
        ("Silhana Ledgewalker", "partial"),  # except by creatures with flying
        ("Relic Runner", "conditional"),  # "if you've cast a historic spell"
        ("Goblin Blast-Runner", "conditional"),  # menace "as long as"
    ],
)
def test_evasion_self_subject_is_the_kind(name, kind):
    assert kind in _subjects(name, "evasion_self")


def test_bare_menace_is_not_unblockable():
    # The combat-damage / damage-to-opponent serves pin that a vanilla menace
    # body is not an unblockable enabler (test_signal_specs, Boggart Brute).
    assert _subjects("Boggart Brute", "evasion_self") == {"menace"}


def test_conditional_evasion_carries_no_unconditional_kind():
    assert _subjects("Relic Runner", "evasion_self") == {"conditional"}
    assert _subjects("Goblin Blast-Runner", "evasion_self") == {"conditional"}


def test_team_grants_stay_out():
    # "Creatures you control have horsemanship" is team_evasion_grant's
    # (test_keyword_gaps::TestTeamEvasionGrant::test_disjoint_from_evasion_self).
    assert not _subjects("Sun Quan, Lord of Wu", "evasion_self")
    assert ("team_evasion_grant", "you", "") in _idents("Sun Quan, Lord of Wu")
    # "Other Merfolk have islandwalk" is a tribal grant: island_makers, not
    # evasion_self.
    assert not _subjects("Lord of Atlantis", "evasion_self")


def test_gang_block_limit_is_not_evasion():
    # "Can't be blocked by more than one creature" limits how many block it,
    # not what can (CR 509.1b's evasion restricts WHAT can block).
    assert not _subjects("Stalking Tiger", "evasion_self")


def test_phase_dropped_evasion_keeps_the_unknown_kind():
    # phase drops Dimir Keyrune's "can't be blocked this turn" from the
    # animation, so only the text arm sees it: the kind is unknown ("").
    assert _subjects("Dimir Keyrune", "evasion_self") == {""}


# ── island makers / matters ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["Harbinger of the Seas", "Spreading Seas", "Tide Shaper"],
)
def test_lands_become_islands(name):
    assert ("island_makers", "you", "lands_become_islands") in _idents(name)


def test_islandwalk_granter_keeps_its_ident():
    assert ("island_makers", "you", "") in _idents("Lord of Atlantis")


@pytest.mark.parametrize("name", ["Typhoon", "Tide Shaper"])
def test_opponent_island_payoff_is_island_matters(name):
    # Typhoon: damage per Island each opponent controls; Tide Shaper: +1/+1
    # "as long as an opponent controls an Island" (its ruling: any land with
    # the Island type).
    assert ("island_matters", "you", "") in _idents(name)


def test_own_island_count_is_neither():
    # Spectral Deluge counts the Islands YOU control: a density payoff the
    # Island makers don't feed.
    keys = {k for k, _s, _su in _idents("Spectral Deluge")}
    assert "island_matters" not in keys
    assert "island_makers" not in keys


# ── arcane_matters precision ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Tallowisp",  # Spirit or Arcane cast trigger
        "Glacial Ray",  # Splice onto Arcane
        "Ire of Kaminari",  # Arcane cards in your graveyard (ZoneCardCount)
    ],
)
def test_arcane_payoffs_fire(name):
    assert ("arcane_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Arcane Savant",  # the word is the card's name
        "Zethi, Arcane Blademaster",
        "The Golden Throne",  # "Arcane Life-support" ability name
        "Kitsune Riftwalker",  # protection from Arcane
        "Hisoka's Defiance",  # counters an Arcane spell (CR 701.6a)
        "Psychic Spear",  # takes an Arcane card from a hand
        "Ishi-Ishi, Akki Crackshot",  # an opponent's Arcane spell
        "Fell Beast's Shriek",  # splice onto instant or sorcery
    ],
)
def test_arcane_word_and_hosers_do_not_fire(name):
    assert "arcane_matters" not in {k for k, _s, _su in _idents(name)}
