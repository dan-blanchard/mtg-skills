"""Signal specs — SPECS assembly, subject-spec builder, and the public API.

Merges the ``SPECS_1``..``SPECS_4`` chunks (in original order — load-bearing for
``spec_for``'s fallback search) into ``SPECS``, then carries everything the
original flat ``signal_specs.py`` defined after the SPECS dict literal: the
subject-bearing dynamic spec builder, the payoff/source avenue split (ADR-0026),
the public ``spec_for`` / ``serves`` / ``search_filters`` API, and the
import-time key-agreement gate (ADR-0014).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._sweep_detectors import (
    SWEEP_DETECTORS,
    SWEEP_LABELS,
)

from ._shared import (
    _CHOSEN_TYPE_IDENTS,
    _ETB_PAYOFF_EXTRA,
    _GOWIDE_ANTHEM_EXTRA,
    _IC,
    _TOKEN_ARISTOCRAT_EXTRA,
    _TOKEN_DOUBLER_EXTRA,
    Serve,
    SignalSpec,
    SubAvenue,
    _spec,
)
from .data_1 import SPECS_1
from .data_2 import SPECS_2
from .data_3 import SPECS_3
from .data_4 import SPECS_4

if TYPE_CHECKING:
    from mtg_utils._deck_forge.signals import Signal

SPECS: dict[tuple[str, str], SignalSpec] = {
    **SPECS_1,
    **SPECS_2,
    **SPECS_3,
    **SPECS_4,
}


# Subject-bearing signal keys: their spec is built dynamically from the captured
# subject (a Goblin lord and a Sliver lord must not share one static spec).
_SUBJECT_KEYS = signal_keys.SUBJECT_KEYS
# Two distinct sub-avenues are always offered for a subject: the *cards* (the tribe
# members, or the token-makers) and the *payoffs* (lords/anthems that reward a board of
# them). Keeping them clearly separate — and never folding "payoffs" into the cards
# avenue's blurb — is what stops "X tribal" / "X payoffs" reading as the same thing.
_SUBJECT_TEMPLATES = {
    signal_keys.TYPE_MATTERS: (
        "{s} tribal",
        "{s} creatures (and changelings) — the bodies that make up the tribe",
    ),
    signal_keys.TYPED_SPELLCAST: (
        "{s} spells",
        "{s} spells to cast and chain",
    ),
    # task B-2: a tribe-count damage finisher (Scourge of Valkas) wants the
    # tribe's BODIES — the count is the burn spell's size (CR 608.2h).
    signal_keys.DAMAGE_FOR_EACH: (
        "{s} count damage",
        "more {s} bodies to raise the count — the tribe is the burn spell",
    ),
}


# Type-GRANT phrasing (B1). _GRANT_VETO (broad) drops any type-grant from the payoff
# lane. _ENABLER_GRANT (tight) requires a GROUP subject ("creatures you control ... are
# the chosen type"), so board-wide granters (Xenograft, Arcane Adaptation, Maskwood
# Nexus, Leyline of Transformation) count as enablers, but a lone CHANGELING ("this card
# is every creature type") does not — it's a tribe member, surfaced by the bodies lane.
_GRANT_VETO = r"(?:is|are) (?:the chosen type|every creature type)"
_ENABLER_GRANT = (
    r"(?:creature|permanent)s? you control[^.]*?"
    r"(?:is|are) (?:the chosen type|every creature type)"
)


def _payoff_extra(subj: str, esc: str) -> SubAvenue:
    # Lords/anthems that REWARD a board of {subj}s. Positive shapes:
    #   - the tribe's own lords ("{subj}s you control"),
    #   - "shares a creature type" pumps (Shared Animosity, Coat of Arms) — any tribe,
    #   - OPEN type-of-choice payoffs ("choose a creature type" then reward it:
    #     Vanquisher's Banner, Door of Destinies) — work for ANY tribe,
    #   - RESTRICTED type-of-choice payoffs that name an explicit list ("choose Elf,
    #     Goblin, …") — credited ONLY when THIS subject is named (so Dawn-Blessed
    #     Pennant counts for Goblin/Elf, never an unlisted tribe like Scarecrow).
    # not_oracle drops type-GRANTERS ("are the chosen type") — enablers, not payoffs.
    positive = (
        rf"{esc}s? you control"
        r"|shares (?:a|at least one) creature type"
        r"|choose a (?:creature|kindred) type"
        rf"|choose\b[^.]*\b{esc}s?\b"
    )
    return SubAvenue(
        f"{subj} payoffs",
        f"lords and anthems that reward a board of {subj}s, plus type-agnostic tribal "
        "payoffs (Coat of Arms, Door of Destinies) that work for any chosen tribe",
        {"oracle": positive},
        serve=Serve(
            oracle=re.compile(positive, _IC),
            # task B-1: the structural successor to the choose-a-type text
            # arm above. Today the text arm supersets it (every chooser's
            # oracle says "choose a creature type" somewhere) but it also
            # credits PUNISHER choosers (Engineered Plague) — retire the text
            # arm onto this ident once the one-shot chooser classes (Distant
            # Melody, Cavern of Souls) get structural arms of their own.
            signal_idents=_CHOSEN_TYPE_IDENTS,
            not_oracle=re.compile(_GRANT_VETO, _IC),
        ),
    )


_TYPE_CHANGER_KEYS = frozenset(
    {
        signal_keys.TYPE_CHANGERS,
        signal_keys.TYPE_CHANGERS_ALL_ZONES,
        signal_keys.TYPE_CHANGERS_GRAVEYARD,
    }
)


def _type_changer_idents(tribe_subjects: tuple[str, ...]) -> frozenset[str]:
    """The type_changers idents that grow a tribe (task #96): the open subjects
    ("" chosen / "all" every type) always count; a fixed-subtype changer counts
    only for ITS tribe(s). Scopes you+each (Kudo's "other creatures" grows your
    side too); all three zone-reach keys (a graveyard-only changer still feeds
    graveyard-facing tribal payoffs)."""
    subjects = {"", "all"} | {s.capitalize() for s in tribe_subjects}
    return frozenset(
        f"{key}|{scope}|{subj}"
        for key in _TYPE_CHANGER_KEYS
        for scope in ("you", "each")
        for subj in subjects
    )


def _enabler_extra(subj: str) -> SubAvenue:
    # Type-changers (Xenograft, Arcane Adaptation) turn OTHER creatures into {subj}s, so
    # the tribe grows and your {subj} payoffs hit more bodies. A distinct lane: an
    # enabler is NOT a payoff or a tribe member (B1). The open grant ("the chosen
    # type") is subject-agnostic, so it credits every {subj} lane. The serve ALSO
    # carries the structural type_changers idents (task #96): the oracle regex only
    # knows the chosen/every-type wordings, so a fixed-subtype changer (Hivestone,
    # "are Slivers in addition to their other creature types") was invisible on
    # this sub-avenue — hidden from the Find surface's enabler browsing.
    return SubAvenue(
        f"{subj} enablers",
        f"cards that make your other creatures {subj}s (type-changers like Xenograft), "
        f"growing the tribe so your {subj} lords and payoffs reach more of the board",
        {"oracle": _ENABLER_GRANT},
        serve=Serve(
            oracle=re.compile(_ENABLER_GRANT, _IC),
            signal_idents=_type_changer_idents((subj,)),
        ),
    )


# Tribal SYNONYM-GROUPS: creature types that share one tribal identity because no card
# rewards any member ALONE — they are always named together. The "sea monster" group is
# the canonical case (Quest for Ula's Temple, Slinn Voda, Whelming Wave, Kenessos all
# enumerate "Kraken, Leviathan, Octopus, and Serpent"), so a commander of any one type
# (Lorthos = Octopus, Tromokratis = Kraken, Koma = Serpent) wants the whole group. ONLY
# groups whose members have NO standalone tribe belong here: Angel/Demon/Dragon and
# Vampire/Werewolf/Zombie are deliberately EXCLUDED — each is a real solo tribe (Lyra
# Angels, Edgar vampires), so grouping them would over-fire a mono-tribe commander.
_TRIBAL_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"kraken", "leviathan", "octopus", "serpent"}),
)


def _tribal_group(subj: str) -> frozenset[str] | None:
    sl = subj.lower()
    for grp in _TRIBAL_GROUPS:
        if sl in grp:
            return grp
    return None


def _subject_spec(signal: Signal) -> SignalSpec:
    """Build a spec for a subject-bearing signal by interpolating the subject."""
    subj = signal.subject
    esc = re.escape(subj)
    # keyword-tribe: the subject is an ability keyword (Flying), not a creature type —
    # find creatures that HAVE the keyword (oracle), not a type-line match.
    if signal.key == signal_keys.KEYWORD_TRIBE:
        return SignalSpec(
            label=f"{subj} matters",
            avenue=f"creatures with {subj} plus anthems and payoffs that reward them",
            search={"oracle": rf"\b{esc.lower()}\b"},
            serve=Serve(oracle=re.compile(rf"\b{esc}\b", _IC)),
        )
    # meld: the subject is THIS commander's own name. Its single meld partner names it
    # ("(Melds with <name>.)" on the back piece, "a creature named <name>" on the front
    # piece, CR 701.42), so serve exactly that one partner — not every meld half.
    if signal.key == signal_keys.MELD_PAIR:
        partner_re = rf"(?:melds with|creature named) {esc}"
        return SignalSpec(
            label=f"Meld partner of {subj}",
            avenue=(
                f"the specific card that melds with {subj} (plus tutors/recursion to "
                "assemble the pair)"
            ),
            search={"oracle": partner_re},
            serve=Serve(oracle=re.compile(partner_re, _IC)),
        )
    # type_changers (task #96, ADR-0040): a mass creature-type changer's own
    # spec. Subject "" (chosen) / "all" (every type) is subject-agnostic — one
    # "Type changers" label, so the three zone-reach keys and both open
    # subjects collapse to a single avenue downstream (focus dedupes by
    # label). A fixed subtype ("Sliver") reuses the tribal extras' enabler
    # label so Hivestone's own signal and the Sliver-tribal enabler
    # sub-avenue read as one lane.
    if signal.key in _TYPE_CHANGER_KEYS:
        label = "Type changers" if subj in ("", "all") else f"{subj} enablers"
        return SignalSpec(
            label=label,
            avenue=(
                "cards that mass-change creature types (Xenograft, Maskwood "
                "Nexus) so tribal payoffs reach more of the board"
            ),
            search={"oracle": _ENABLER_GRANT},
            serve=Serve(
                oracle=re.compile(_ENABLER_GRANT, _IC),
                signal_idents=_type_changer_idents(
                    () if subj in ("", "all") else (subj,)
                ),
            ),
        )
    # token-maker: the deck CREATES {s} tokens, so find cards that *make* them (not the
    # tribe — searching the type line surfaced {s} creatures that don't make tokens).
    if signal.key == signal_keys.TOKEN_MAKER:
        token_re = rf"create\b[^.]*\b{esc}\b[^.]*token"
        # A token-maker commander (Krenko → token_maker:Goblin) is a flood deck: offer
        # the creature-ETB payoffs and token doublers alongside the tribe-token payoffs.
        return SignalSpec(
            label=f"{subj} tokens",
            avenue=f"cards that create {subj} tokens to go wide",
            search={"oracle": token_re},
            serve=Serve(oracle=re.compile(token_re, _IC)),
            extras=(
                _payoff_extra(subj, esc),
                _TOKEN_DOUBLER_EXTRA,
                _ETB_PAYOFF_EXTRA,
                _GOWIDE_ANTHEM_EXTRA,
                _TOKEN_ARISTOCRAT_EXTRA,
            ),
        )
    # tribal (type_matters) / typed spellcast: the cards themselves (type-line match),
    # plus a distinct "{s} payoffs" sub-avenue for the lords/anthems that reward them.
    label_t, avenue_t = _SUBJECT_TEMPLATES.get(signal.key, ("{s}", "{s} synergies"))
    # Changelings (CR 702.73a) are every creature type, so they count for EVERY tribe —
    # but they type-line as "Shapeshifter", so the {card_type: subj} search misses every
    # one. Fold them (the keyword bearers + the "is/are every creature type" granters)
    # into the type-tribal serve so a Goblin/Elf/Zombie deck credits its changelings.
    is_type_tribal = signal.key in (
        signal_keys.TYPE_MATTERS,
        # task B-2: a "{s} count damage" lane is tribal-bodies-semantics too —
        # every body (and changeling, and type-changer) raises the count.
        signal_keys.DAMAGE_FOR_EACH,
    )
    # Synonym-GROUP tribes (sea monsters): a member type's serve covers the WHOLE group,
    # by type-line AND by the group-naming payoff oracle (Whelming Wave). card_search's
    # card_type is single-token-only (no OR), so each OTHER member gets its own search
    # sub-avenue to pull its bodies; the widened serve credits them all.
    group = _tribal_group(subj) if is_type_tribal else None
    members = sorted(group) if group else [subj.lower()]
    type_alt = "|".join(re.escape(m) for m in members)
    # Bodies serve: the tribe's own members (type-line) PLUS changelings ("is/are every
    # creature type", CR 702.73a — a changeling IS a member of every tribe). NOT the
    # type-GRANTERS ("is/are the chosen type"): Xenograft & co. don't BECOME a member,
    # they turn your OTHER creatures into the tribe — surfaced by the separate enabler
    # sub-avenue (_enabler_extra), never counted as a body or payoff (B1).
    serve_oracle = rf"\b(?:{type_alt})s?\b" + (
        r"|(?:is|are) every creature type" if is_type_tribal else ""
    )
    group_extras: tuple[SubAvenue, ...] = ()
    if group:
        group_extras = tuple(
            SubAvenue(
                f"{m.capitalize()}s",
                f"{m.capitalize()} bodies in the {subj} group",
                {"card_type": m},
                serve=Serve(types=frozenset({m})),
            )
            for m in members
            if m != subj.lower()
        )
    return SignalSpec(
        label=label_t.format(s=subj),
        avenue=avenue_t.format(s=subj),
        search={"card_type": subj},
        serve=Serve(
            oracle=re.compile(serve_oracle, _IC),
            # A creature IS a member of its own tribe (CR 205.3) — match by TYPE-LINE,
            # not only the oracle "Xs you control" payoff phrasing. Without this,
            # vanilla / oracle-silent members (Dread Shade, Llanowar Elves) were
            # dropped — fatal for lord-less tribes (Shade/Kraken/Yeti read 0/10).
            types=frozenset(members) if is_type_tribal else frozenset(),
            keywords=frozenset({"changeling"}) if is_type_tribal else frozenset(),
            # Structural enabler arm (task #96, ADR-0040): a mass type-changer
            # SERVES the tribe it grows (Leyline of Transformation under a
            # Sliver commander — the benchmark's falsely-filler build-around),
            # by its own emitted type_changers idents. Bodies-by-type-line
            # above are unchanged: B1 still keeps granters out of the body
            # oracle; this arm credits them at the serve level instead.
            # Wildcard chosen-type payoffs serve EVERY tribe (task B-1):
            # Herald's Horn credits a Sliver deck exactly as a Goblin deck —
            # but ONLY on the type_matters lane (verified-review F4): a
            # "{s} count damage" bodies lane must not credit cost reducers
            # and anthems that add zero bodies to the ObjectCount it reads.
            # Type-CHANGERS stay on both tribal-bodies lanes: Maskwood Nexus
            # genuinely raises the count.
            signal_idents=(
                _type_changer_idents(tuple(members)) if is_type_tribal else frozenset()
            )
            | (
                _CHOSEN_TYPE_IDENTS
                if signal.key == signal_keys.TYPE_MATTERS
                else frozenset()
            ),
        ),
        extras=(
            _payoff_extra(subj, esc),
            # Type-changers (Xenograft) are enablers, not payoffs/members — a distinct
            # lane, only for true tribes (type_matters), not typed-spellcast (B1).
            *((_enabler_extra(subj),) if is_type_tribal else ()),
            *group_extras,
        ),
    )


# Auto-register an avenue for every exhaustively-mined sweep key that doesn't
# already have a hand-written spec (the same-key widens reuse their existing spec).
def _humanize(key: str) -> str:
    base = key.replace("_matters", "").replace("_", " ").strip()
    return (base[:1].upper() + base[1:]) if base else key


_SPECCED_KEYS = {k for (k, _scope) in SPECS}
for _d in SWEEP_DETECTORS:
    if _d["key"] in _SPECCED_KEYS:
        continue  # hand-written spec already covers this axis
    _ident = (_d["key"], _d["scope"])
    if _ident in SPECS:
        continue
    _polished = SWEEP_LABELS.get(_d["key"])
    if _polished:
        _label, _avenue = _polished
    else:
        _label = _humanize(_d["key"])
        _avenue = f"support and payoffs for the {_label.lower()} axis"
    SPECS[_ident] = _spec(_label, _avenue, {"oracle": _d["regex"]}, _d["regex"])


# ── ADR-0026: payoff/source avenue split ──────────────────────────────────────
# A `<mechanic>_matters` serve fuses an oracle PAYOFF pattern with a type/keyword
# SOURCE (the cards that ARE the thing). These are the source-role dimensions whose
# cards form a browsable pool — CR-verified gear/membership, NOT property/payoff
# keywords. Excluded by design: prowess (CR 702.108, a payoff), exalted (702.83,
# payoff), proliferate (701.34, an enabler), and modifier keywords
# (haste/indestructible/trample/the evasion set) that describe a property, not a pool.
SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "equipment",
        "aura",  # voltron — CR 702.6 (equip) / 702.5 (enchant)
        "artifact",
        "enchantment",  # artifacts / enchantments matter
        "planeswalker",  # superfriends
        "legendary",
        "snow",
        "saga",
        "arcane",
        "lesson",
        "eldrazi",
        "instant",
        "sorcery",  # spellslinger fuel (prowess stays on the payoff side)
        "rogue",
        "wizard",
        "warrior",
        "cleric",  # party members
        "assassin",
        "pirate",
        "warlock",
        "mercenary",  # outlaws
    }
)
SOURCE_KEYWORDS: frozenset[str] = frozenset({"reconfigure"})  # CR 702.151 — it is gear

_SOURCE_TYPE_LABELS = {
    "aura": "Auras",
    "equipment": "Equipment",
    "artifact": "Artifacts",
    "enchantment": "Enchantments",
    "planeswalker": "Planeswalkers",
    "saga": "Sagas",
    "instant": "Instants",
    "sorcery": "Sorceries",
    "legendary": "Legendaries",
    "snow": "Snow permanents",
    "arcane": "Arcane spells",
    "lesson": "Lessons",
    "eldrazi": "Eldrazi",
}


def source_split(spec: SignalSpec) -> tuple[Serve, dict] | None:
    """ADR-0026: if a payoff spec's serve carries a membership-source TYPE, return the
    (source_serve, source_search) for a derived Source avenue — the cards that ARE the
    thing the payoff wants. None when there's no source type or no payoff oracle (a
    pure-membership spec is already a single source-ish lane; don't split it). The
    caller strips the same dims from the payoff avenue (see ``payoff_serve``)."""
    srv = spec.serve
    if srv.oracle is None:
        return None
    st = srv.types & SOURCE_TYPES
    if not st:
        return None
    sk = srv.keywords & SOURCE_KEYWORDS  # rides along (reconfigure cards are Equipment)
    source_serve = Serve(types=st, keywords=sk, not_oracle=srv.not_oracle)
    return source_serve, {"card_type": tuple(sorted(st))}


def payoff_serve(spec: SignalSpec) -> Serve:
    """The payoff avenue's serve once source dims are split out (ADR-0026): the oracle
    payoff + any non-source types/keywords (e.g. prowess stays), minus the source
    type/keyword the Source avenue now owns."""
    srv = spec.serve
    return replace(
        srv,
        types=srv.types - SOURCE_TYPES,
        keywords=srv.keywords - SOURCE_KEYWORDS,
    )


def _pluralize(t: str) -> str:
    # -y → -ies (mercenary → mercenaries), else +s; explicit labels win first.
    if t in _SOURCE_TYPE_LABELS:
        return _SOURCE_TYPE_LABELS[t]
    base = t.title()
    return base[:-1] + "ies" if base.endswith("y") else base + "s"


def source_label(source_types: frozenset[str]) -> str:
    """A human label for a Source avenue from its types ("Auras & Equipment")."""
    return " & ".join(_pluralize(t) for t in sorted(source_types))


def payoff_search(search: dict, serve: Serve) -> dict:
    """The payoff avenue's pool fetch (ADR-0026): drop the type/preset fetch (that
    pulled the source pool) and fall back to the serve's oracle payoff pattern, so the
    payoff lane surfaces payoffs (Sram, equip-cost reducers) not vanilla gear."""
    drop = ("card_type", "preset_names", "presets")
    out = {k: v for k, v in search.items() if k not in drop}
    if "oracle" not in out and serve.oracle is not None:
        out["oracle"] = serve.oracle.pattern
    return out


def spec_for(signal: Signal) -> SignalSpec | None:
    """Resolve a spec. Subject-bearing signals build a per-subject spec; otherwise
    exact (key, scope) → (key, any) → first entry by key."""
    # type_changers' "" subject is a VALUE ("the chosen type" — Xenograft),
    # not subject-absence, so those keys dispatch dynamic even when empty.
    if signal.key in _SUBJECT_KEYS and (
        signal.subject or signal.key in _TYPE_CHANGER_KEYS
    ):
        return _subject_spec(signal)
    exact = SPECS.get((signal.key, signal.scope))
    if exact is not None:
        return exact
    any_scope = SPECS.get((signal.key, "any"))
    if any_scope is not None:
        return any_scope
    return next((spec for (key, _), spec in SPECS.items() if key == signal.key), None)


def serves(card: dict, signal: Signal) -> bool:
    """True if ``card`` feeds ``signal`` (scope-aware), on any structured/oracle
    dimension of the spec's precise ``Serve`` predicate — no longer oracle-only."""
    spec = spec_for(signal)
    if spec is None:
        return False
    return spec.serve.matches(card)


def search_filters(signal: Signal, *, color_identity: str, fmt: str) -> dict:
    """Build ``card_search`` kwargs to find cards that feed ``signal`` in-identity."""
    spec = spec_for(signal)
    base = dict(spec.search) if spec else {}
    base["color_identity"] = color_identity
    base["format"] = fmt
    return base


def _assert_every_producible_key_resolves() -> None:
    """Key-agreement gate (ADR-0014). Every subject-less key a detector can produce
    must resolve to a spec. A detector key with no spec used to be a silent no-avenue
    (extraction worked, ``spec_for`` returned None, the avenue was dropped); now it
    fails loudly at import — which ``app.py`` / ``ranking.py`` / every test trigger
    transitively. ``signals`` is imported lazily to keep the module import order
    one-way (signals never imports signal_specs)."""
    from mtg_utils._deck_forge.signals import Signal, producible_static_keys

    orphans = sorted(
        key
        for key in producible_static_keys()
        if spec_for(Signal(key=key, scope="any", subject="", text="", source=""))
        is None
    )
    if orphans:
        msg = (
            f"signal keys produced by a detector but resolved by no spec: {orphans} — "
            "add a SPECS entry (or sweep row), or exclude a subject key."
        )
        raise AssertionError(msg)


_assert_every_producible_key_resolves()
