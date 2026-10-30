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
from mtg_utils._card_ir.crosswalk import made_keyword_bodies, own_keyword_bodies
from mtg_utils._card_ir.dropped_keywords import PHASE_KEYWORDS, restore_dropped_keywords
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_card_ir, test_phase_records, test_signals


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


def _spells(raw: object, spelled: str) -> bool:
    """Whether a raw keyword is ``spelled`` — bare, or a parameterized one's
    variant key (``{"Ward": <cost>}``)."""
    return raw == spelled or (isinstance(raw, dict) and spelled in raw)


def _types_keyword(name: str, kw: str) -> bool:
    """Whether phase's own records type ``kw`` anywhere: an ``AddKeyword``, a
    token's keywords, a keyword counter."""
    spelled = PHASE_KEYWORDS.get(kw) or kw.title().replace(" ", "")
    for n in _raw_nodes(name):
        if n.get("type") == "AddKeyword" and _spells(n.get("keyword"), spelled):
            return True
        if n.get("type") == "Token" and any(
            _spells(k, spelled) for k in n.get("keywords") or ()
        ):
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
    ("Guardian Zendikon", "defender"),  # "is a 2/6 white Wall creature with defender"
    ("Jodah's Avenger", "shadow"),  # "double strike, protection from red, …, shadow"
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
    ("Wall of Caltrops", "banding"),  # "this creature gains banding until …"
    ("Better Offer", "ward"),  # "perpetually gains ward {1}"
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


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Tromp the Domains", "team_buff|you|trample"),  # your whole team
        ("Tromp the Domains", "team_buff|you|"),
        ("Haldir, Lórien Lieutenant", "team_buff|you|vigilance"),  # your Elves
        ("Stolen Vitality", "keyword_grant_target|you|first strike"),  # a target
    ],
)
def test_partly_read_grant_feeds_the_grant_lanes(name, ident):
    # the pump's own object is the grantee (crosswalk.pump_keyword_grants)
    assert ident in _idents(name)


# ── a Role token's own ability ───────────────────────────────────────────────

_ROLE_DROPS = [
    ("Monstrous Rage", "trample"),  # Monster Role, CR 111.10k
    ("Royal Treatment", "ward"),  # Royal Role, CR 111.10m: "has ward {1}"
]


@pytest.mark.retirement_canary
@pytest.mark.parametrize(("name", "kw"), _ROLE_DROPS)
def test_role_token_ability_dropped_canary(name, kw):
    roles = [
        n
        for n in _raw_nodes(name)
        if n.get("type") == "Token" and "Role" in (n.get("types") or ())
    ]
    assert roles, f"{name}: no Role Token node — re-check the shape"
    assert not any(n.get("static_abilities") for n in roles), _retire(
        name, kw, "dropped_keywords._role_grants"
    )


@pytest.mark.parametrize(("name", "kw"), _ROLE_DROPS)
def test_role_token_ability_restored(name, kw):
    idents = _idents(name)
    assert f"keyword_bodies|you|{kw}" in idents
    # an Aura's grant to the creature it enchants
    assert f"aura_equip_kw_grant|you|{kw}" in idents


def test_restored_ward_keeps_its_cost():
    (rec,) = test_phase_records("Royal Treatment")
    wards = [
        n["keyword"]["Ward"]
        for n in _walk(restore_dropped_keywords(rec))
        if n.get("type") == "AddKeyword" and isinstance(n.get("keyword"), dict)
    ]
    assert wards == [
        {"type": "Mana", "data": {"type": "Cost", "shards": [], "generic": 1}}
    ]


# ── a keyword phase once swallowed into a counter kind ───────────────────────
# Through phase v0.104.0 these typed the keyword as part of a counter kind
# ("flying and with x +1/+1"), read by recovery's ``_swallowed_counter_keywords``;
# v0.118.0 types the keyword, and the read retired. The membership pin stays.


@pytest.mark.parametrize(
    ("name", "kw"),
    [
        ("Dralnu's Pet", "flying"),  # "enters with flying and with X +1/+1 counters"
        ("Printlifter Ooze", "trample"),  # "token with trample. The token enters"
    ],
)
def test_counter_kind_keyword_read(name, kw):
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
        ("Fugitive of the Judoon", "ward"),  # a token's "ward {2}"
        ("Fugitive Codebreaker", "ward"),  # disguise, CR 702.168a
        ("Vannifar, Evolved Enigma", "ward"),  # cloak, CR 701.58a
        ("Jhoira of the Ghitu", "haste"),  # suspends a card from your hand
        ("The Tenth Doctor", "haste"),  # … from the top of your library
        ("Doom's Time Platform", "haste"),  # … from your graveyard
        ("Taigam, Master Opportunist", "haste"),  # … the spell you cast
        ("Guardian Zendikon", "defender"),  # a body it makes (CR 702.3b)
        ("Primal Clay", "defender"),  # itself, a 1/6 Wall
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
        ("Gandalf of the Secret Fire", "haste"),  # suspends instants and sorceries
        ("Unexplained Absence", "ward"),  # the exiled permanent's controller cloaks
        ("Guard Duty", "defender"),  # a grant of defender is a drawback
        ("Stasis Field", "defender"),
        ("Welcome to . . . // Jurassic Park", "defender"),  # opponents' artifacts
        ("Basalt Golem", "defender"),  # the blocker's controller creates the Wall
        ("Aether Web", "shadow"),  # "block creatures with shadow as though …"
    ],
)
def test_no_false_keyword(name, kw):
    assert f"keyword_bodies|you|{kw}" not in _idents(name)


@pytest.mark.parametrize(
    ("name", "subject"),
    [
        ("Kwende, Pride of Femeref", "First strike"),  # two words, CR 702.7
        ("High Alert", "Defender"),  # "can attack as though they didn't have"
        ("Rolling Stones", "Defender"),
        ("Teyo, Aegis Adept", "Defender"),  # a perpetual AddStaticMode
        ("Towering Titan", "Defender"),  # "Sacrifice a creature with defender"
        ("Mystical Teachings", "Flash"),  # a tutor of your library
    ],
)
def test_keyword_tribe_payoffs(name, subject):
    assert f"keyword_tribe|you|{subject}" in _idents(name)


def test_a_creature_letting_itself_attack_is_no_defender_payoff():
    assert "keyword_tribe|you|Defender" not in _idents("Backstreet Bruiser")


def test_copy_pt_override_reads_beside_a_restored_keyword():
    # Mindlink Mech's "except it's 4/3, …, and it has flying": the restored
    # flying sits in the copy's exceptions; the dropped 4/3 is still read
    idents = _idents("Mindlink Mech")
    assert {"keyword_bodies|you|flying", "base_pt_set|any|"} <= idents


def test_conditional_lifelink_is_a_lifegain_plan():
    # Noble Banneret's "this creature and those creatures get +1/+1 and have
    # lifelink", restored, makes it a lifegain source like any lifelink body
    # (CR 702.15b)
    idents = _idents("Noble Banneret")
    assert {"keyword_bodies|you|lifelink", "lifegain_makers|you|"} <= idents


@pytest.mark.parametrize("name", ["Noble Banneret", "Vampire Nighthawk"])
def test_a_lifelink_body_is_a_lifegain_plan_and_a_carrier(name):
    # Lifelink gains life "in addition to the damage's other results" (CR 120.3f),
    # so the body's combat damage still counts toward commander damage (CR
    # 903.10a): its own lifegain doesn't silence the commander-damage fallback.
    # Restored (Banneret) or printed (Nighthawk) alike.
    idents = _idents(name)
    assert {"lifegain_makers|you|", "voltron_matters|you|carrier"} <= idents


def _own_and_made_bodies(name: str) -> tuple[set[str], set[str]]:
    test_card_ir(name)  # seeds the tree memo from the snapshot's phase records
    trees = trees_for(test_card(name))
    own = set().union(*(own_keyword_bodies(t) for t in trees))
    made = set().union(*(made_keyword_bodies(t) for t in trees))
    return own, made


def test_own_keyword_bodies_are_the_cards_own_body():
    # A self-grant is the card's own (Noble Banneret); the lifelink Soldier
    # tokens Emmara makes are bodies it makes, not its own.
    assert "lifelink" in _own_and_made_bodies("Noble Banneret")[0]
    own, made = _own_and_made_bodies("Emmara, Soul of the Accord")
    assert "lifelink" in made
    assert "lifelink" not in own


def test_lifegain_that_is_no_lifelink_body_is_no_carrier():
    # A noncreature lifegain card is no body to suit up.
    idents = _idents("Healing Salve")
    assert "lifegain_makers|you|" in idents
    assert "voltron_matters|you|carrier" not in idents


# ── the grammar over one node's clause ───────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "kws", "flags"),
    [
        ("gain flying and has base toughness 1", {"flying"}, {}),
        (
            "gains your choice of banding, first strike, or trample",
            {"banding", "first strike", "trample"},
            {},
        ),
        (
            "gains your choice of first strike, trample, or rampage 3",
            {"first strike", "trample"},
            {},
        ),
        (
            (
                "gains your choice of double strike, protection from red, "
                "vigilance, or shadow"
            ),
            {"double strike", "vigilance", "shadow"},
            {},
        ),
        (
            (
                "has reach, and can block creatures with shadow as though they "
                "didn't have shadow"
            ),
            {"reach"},
            {},
        ),
        (
            "is a 2/6 white Wall creature with defender",
            {"defender"},
            {"creature_with": "any"},
        ),
        (
            "it becomes your choice of a 3/3 creature or a 1/6 creature with defender",
            {"defender"},
            {"creature_with": "stated", "grants": False},
        ),
        ("enchanted creature has defender", set(), {"grants": False}),
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
