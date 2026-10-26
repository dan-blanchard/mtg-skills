"""The keywords phase drops from a body (backlog (o), the keyword tribe).

Each misread shape is read where it belongs: a static def's or a copy's grant
left out of its modifications and a keyword misread as a subtype are restored
on the raw records before strict load (``_card_ir.dropped_keywords``); a
residue's grant, token or keyword counter and a grant phase reads only part of
are recorded on the recovery stage's ``ConceptNode.body_keywords``. Each shape
has a ``retirement_canary`` over the raw phase records (it fails RETIRE-READY
once phase types the keyword itself) and the ``keyword_bodies`` ident the fix
reads, proven on the real cards. The keyword abilities that confer one (dash's
haste, CR 702.109a) are our own reads and need no canary.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from mtg_utils._card_ir.clause_grammar import keyword_grants
from mtg_utils._card_ir.dropped_keywords import PHASE_KEYWORDS, restore_dropped_keywords
from mtg_utils.testkit import test_phase_records, test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def _walk(node: object) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _raw_nodes(name: str) -> list[dict]:
    return [n for rec in test_phase_records(name) for n in _walk(rec)]


def _types_keyword(name: str, kw: str) -> bool:
    """Whether phase's own records type ``kw`` anywhere: an ``AddKeyword``, a
    token's keywords, a keyword counter."""
    spelled = PHASE_KEYWORDS[kw]
    for n in _raw_nodes(name):
        if n.get("type") == "AddKeyword" and n.get("keyword") == spelled:
            return True
        if spelled in (n.get("keywords") or ()) and n.get("type") == "Token":
            return True
        if n.get("type") == "PutCounter" and n.get("counter_type") in (spelled, kw):
            return True
    return False


def _retire(name: str, kw: str, fix: str) -> str:
    return (
        f"{name}: RETIRE-READY — phase now types its {kw}. Drop {name} from this "
        f"canary; once no card is left, delete {fix}."
    )


# ── a static def's grant left out of its modifications ───────────────────────

_STATIC_DROPS = [
    ("Chariot of the Sun", "flying"),  # "gain flying and has base toughness 1"
    ("Valkyrie's Call", "flying"),  # "has flying and is an Angel" as AddSubtype
    ("Tek", "flying"),  # an Unrecognized condition holds "has flying as long as …"
    ("Tek", "trample"),
    ("Tribal Golem", "haste"),  # "has trample as long as …, haste as long as …"
    ("Harmonious Emergence", "vigilance"),  # "a 4/5 … creature with vigilance"
    ("Argivian Avenger", "flying"),  # "your choice of flying, vigilance, …"
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize(("name", "kw"), _STATIC_DROPS)
def test_static_grant_dropped_canary(name, kw):
    assert not _types_keyword(name, kw), _retire(
        name, kw, "dropped_keywords._grants' Continuous-def arm"
    )


@pytest.mark.parametrize(("name", "kw"), _STATIC_DROPS)
def test_static_grant_restored(name, kw):
    assert f"keyword_bodies|you|{kw}" in _idents(name)


def test_restored_grant_feeds_the_team_lanes():
    # the restored AddKeyword is phase's own shape, so every keyword lane reads it
    assert "keyword_grant_target|you|flying" in _idents("Chariot of the Sun")


@pytest.mark.parametrize(
    "name",
    [
        "Akroma, Vision of Ixidor",  # "+1/+1 if it has flying": a condition
        "Solid Footing",  # "As long as enchanted creature has vigilance"
        "Archetype of Imagination",  # "lose flying and can't have or gain flying"
        "Lunarch Mantle",  # a quoted ability's "~ gains flying"
        "Dragonfire Blade",  # "hexproof from monocolored", typed as such
    ],
)
def test_no_grant_restored_where_none_is_dropped(name):
    for rec in test_phase_records(name):
        assert restore_dropped_keywords(rec) is rec


def test_restoring_copies_the_record():
    (rec,) = test_phase_records("Chariot of the Sun")
    restored = restore_dropped_keywords(rec)
    assert restored is not rec
    assert not any(n.get("keyword") == "Flying" for n in _walk(rec))
    assert any(n.get("keyword") == "Flying" for n in _walk(restored))


# ── a copy's keyword left out of its exceptions ──────────────────────────────

_COPY_DROPS = [
    ("Irenicus's Vile Duplication", "flying"),  # "except the token has flying"
    ("March from Velis Vel", "haste"),  # "becomes a copy … and gains haste"
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize(("name", "kw"), _COPY_DROPS)
def test_copy_grant_dropped_canary(name, kw):
    assert not _types_keyword(name, kw), _retire(
        name, kw, "dropped_keywords._grants' copy arm"
    )


@pytest.mark.parametrize(("name", "kw"), _COPY_DROPS)
def test_copy_grant_restored(name, kw):
    assert f"keyword_bodies|you|{kw}" in _idents(name)


# ── a keyword misread as a subtype ───────────────────────────────────────────
# (its canary is test_theme_page_reads.test_stray_grant_subtype_canary)


def test_keyword_subtype_read_as_the_keyword():
    idents = _idents("Will of the Temur")
    assert "keyword_bodies|you|flying" in idents
    assert "subtype_ref|any|Flying" not in idents


# ── a residue's grant, token or keyword counter ──────────────────────────────

_RESIDUES = [
    (
        "Notorious Throng",
        "flying",
    ),  # "Create X 1/1 … Faerie Rogue … tokens with flying"
    ("Reaper of Night // Harvest Fear", "flying"),  # "it gains flying until …"
    ("Genku, Future Shaper", "vigilance"),  # "• 2/2 white Fox with vigilance"
    ("Inventive Wingsmith", "flying"),  # "put a flying counter on it"
    ("Mardu Thunderkite", "lifelink"),  # "your choice of menace, lifelink, or haste"
    ("Rushblade Commander", "haste"),  # a failed static "… have haste"
    ("Blitzwing, Cruel Tormentor // Blitzwing, Adaptive Assailant", "flying"),
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize(("name", "kw"), _RESIDUES)
def test_residue_keyword_canary(name, kw):
    parked = [
        n.get("description") or ""
        for n in _raw_nodes(name)
        if n.get("type") == "Unimplemented"
    ]
    retire = _retire(name, kw, "recovery.residue_body_keywords")
    assert any(kw in d.lower() for d in parked), retire
    assert not _types_keyword(name, kw), retire


@pytest.mark.parametrize(("name", "kw"), _RESIDUES)
def test_residue_keyword_read(name, kw):
    assert f"keyword_bodies|you|{kw}" in _idents(name)


# ── a grant phase reads only part of ─────────────────────────────────────────

_PARTLY_READ = [
    ("Tromp the Domains", "trample"),  # a bare PumpAll for "gain trample and get"
    ("Haldir, Lórien Lieutenant", "vigilance"),
    ("Stolen Vitality", "first strike"),  # "Otherwise, it gains first strike"
    ("Indominus Rex, Alpha", "deathtouch"),  # "The same is true for …"
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize(("name", "kw"), _PARTLY_READ)
def test_partly_read_grant_canary(name, kw):
    assert not _types_keyword(name, kw), _retire(
        name, kw, "recovery._partly_read_grant"
    )


@pytest.mark.parametrize(("name", "kw"), _PARTLY_READ)
def test_partly_read_grant_read(name, kw):
    assert f"keyword_bodies|you|{kw}" in _idents(name)


# ── our reads: what phase types and keyword_bodies didn't read ──────────────


@pytest.mark.parametrize(
    ("name", "kw"),
    [
        ("Generator Servant", "haste"),  # the spell its mana is spent on
        ("Dack's Duplicate", "haste"),  # a copy "except it has haste"
        ("Alesha's Vanguard", "haste"),  # dash, CR 702.109a
        ("Deep-Sea Kraken", "haste"),  # a creature's suspend, CR 702.62a
        ("Epochrasite", "haste"),  # suspending itself
        ("Rush of Ice", "haste"),  # awaken, CR 702.113a
        ("Toph, the Blind Bandit", "haste"),  # earthbend, CR 701.66a
        ("Domri, Chaos Bringer", "haste"),  # a granted riot, CR 702.136a
        ("Afterlife Insurance", "flying"),  # a granted afterlife, CR 702.135a
        ("Frantic Scapegoat", "menace"),  # suspect, CR 701.60c
        ("Greymond, Avacyn's Stalwart", "lifelink"),  # a choice made as it enters
        ("Dragonfire Blade", "hexproof"),  # hexproof from, CR 702.11d
    ],
)
def test_keyword_bodies_reads(name, kw):
    assert f"keyword_bodies|you|{kw}" in _idents(name)


@pytest.mark.parametrize(
    ("name", "kw"),
    [
        ("Ancestral Vision", "haste"),  # a sorcery's suspend: no creature spell
        ("Delay", "haste"),  # suspends another player's spell
        ("Flying Drone", "flying"),  # "if another creature with flying entered"
        ("Siani, Eye of the Storm", "flying"),  # "X is the number of … with flying"
        ("Hunted Troll", "flying"),  # target opponent creates the Faeries
        ("Walking Sponge", "flying"),  # "loses your choice of flying, …"
    ],
)
def test_no_false_keyword(name, kw):
    assert f"keyword_bodies|you|{kw}" not in _idents(name)


# ── the grammar over one node's clause ───────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "kws", "flags"),
    [
        ("gain flying and has base toughness 1", {"flying"}, {}),
        (
            "gains your choice of banding, first strike, or trample",
            {"first strike", "trample"},
            {},
        ),
        (
            (
                "~ has trample as long as you control a Beast, haste as long as you "
                "control a Goblin"
            ),
            {"trample", "haste"},
            {},
        ),
        ("get +1/+1 if it has flying", set(), {}),
        ("Creatures you control that have flying get +1/+1", set(), {}),
        ("can't have or gain flying", set(), {}),
        ('has "{1}: ~ gains flying until end of turn"', set(), {}),
        ("has hexproof from monocolored", set(), {}),
        (
            "Enchanted land is a 4/4 Elemental creature with reach",
            {"reach"},
            {"creature_with": "any"},
        ),
        (
            "can't be attacked except by creatures with flying",
            set(),
            {"creature_with": "stated"},
        ),
        ("1/2 blue Moonfolk with flying", {"flying"}, {"tokens": True}),
        ("doesn't have a flying counter on it", set(), {"counters": True}),
        (
            "put a +1/+1 counter and a lifelink counter on it",
            {"lifelink"},
            {"counters": True},
        ),
    ],
)
def test_keyword_grants(text, kws, flags):
    assert keyword_grants(text, **flags) == kws
