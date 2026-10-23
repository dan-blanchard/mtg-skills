"""The three diagnostic metrics + the Tier-2 flags.

Efficiency (Shape-aware curve/tempo — NOT per-card power, ADR-0009), Template deviation
(over the shared ``slot_budgets`` bands), and Focus (Engine-card concentration over the
deck's signal-derived avenues). Win-cons and protection are Shape-scaled advisory flags
(ADR-0024). Every readout is transparent (matching deck-forge's gate style); none is an
opaque score. ``_tuner.issues.top_issues`` ranks the findings by severity — the single
ordering the swap engine acts on (deck-forge CONTEXT.md, "Tune").
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis.lanes import TOKEN_SUBTYPE_PAYOFF_KEYS
from mtg_utils._analysis.roles import protects
from mtg_utils._analysis.signal_specs import SPECS, avenue_spec_for, spec_scope_for
from mtg_utils._card_ir.crosswalk import (
    ends_the_game,
    is_evasive_body,
    reach_amount,
    static_def_adds_power,
    team_buff_sites,
    unbound_x_reach,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils._tuner.calibration import COMMANDER, Calibration
from mtg_utils._tuner.classify import CardClass, is_premium, is_upgrade_target
from mtg_utils.card_classify import card_pt_int, has_evasion, is_creature
from mtg_utils.formats import Game
from mtg_utils.theme_presets import get_preset

if TYPE_CHECKING:
    from mtg_utils._analysis.signals import Signal
    from mtg_utils._card_ir.crosswalk import ConceptTree

# Signal keys that mirror a hard-counted Spine role (ramp / draw / interaction). Not
# themes, so focus excludes their avenues: a "Ramp / big mana" avenue full of mana rocks
# and lands is scaffolding, not a lane the deck is built around. The interaction family
# has SIBLING removal lanes (exile removal, until-leaves exile, counterspells) that are
# equally scaffolding — excluding only "removal" let them masquerade as themes (e.g.
# "Exile removal under-supported theme" for a deck just running Swords / Path).
_SPINE_AVENUE_KEYS = frozenset(
    {
        "ramp",
        "card_draw_engine",
        "removal",
        "exile_removal",
        "exile_until_leaves",
        "counter_control",
        # Board wipes are the counted ``board_wipe`` Spine row; five of them read
        # as an emerging "Board wipes" theme to commit to or cut (2026-10-18).
        "mass_removal",
    }
)

# Shape → (lo, hi) nonland average-MV band; ~4.0 is the soft ceiling (waived when the
# deck cheats costs). Centred ~3.0 per the verified research.
_AVG_BANDS = {
    "aggro": (1.8, 2.8),
    "midrange": (2.5, 3.5),
    "control": (2.8, 3.8),
    "combo": (2.0, 3.2),
}
_AVG_CEILING = 4.0

# The Game every band below is calibrated at: the 40-life Commander pod (CR 103.4c),
# where 21 commander damage wins (CR 903.10a). ``win_conditions`` scales from it to the
# Game the deck actually plays (``Format.game``).
CALIBRATION_GAME = Game(
    medium="paper", life=40, multiplayer=True, commander_damage=True
)
_CALIBRATION_LIFE = CALIBRATION_GAME.life

# The dedicated-closer bands (ADR-0024; floor ~3, archetype-scaled) live on the
# family's ``Calibration`` at CALIBRATION_GAME. Both bounds scale with starting life
# (``_life_scaled``): at 25 life one-on-one, ordinary threats close games and fewer
# dedicated closers are wanted.
# An evasive body reads as a closer from this power at _CALIBRATION_LIFE (~7 swings);
# the threshold scales with life so a 4-power flyer counts at 25 (~6 swings) but not
# at 40.
_EVASIVE_CLOSER_POWER = 6
_EVASIVE_CLOSER_POWER_FLOOR = 3
# A fixed-amount burn / drain is a closer when one resolution takes at least this share
# of starting life: 5 at _CALIBRATION_LIFE, 4 at 30, 3 at 25 or 20.
_BURN_CLOSER_FRACTION = 0.12

# Reach — burn / drain that ends a game — is ONE scope table x ONE amount read
# (``crosswalk.reads.reach_amount`` over the card's trees). Group scope ("each
# opponent") counts at any table; single-target scope counts only one-on-one, where
# "any target" is the finisher "each opponent" is at a pod. A SCALING amount (X, a
# devotion, a count, a loss repeated X times) is always a closer. A FIXED amount is a
# closer when one resolution takes ``_BURN_CLOSER_FRACTION`` of starting life in
# group scope, or the WHOLE starting life in single-target scope (Aetherflux
# Reservoir's 50 is a one-on-one closer; a bolt is removal, never a closer, even at
# 25 life). A symmetric "each player" sweep (Earthquake) is neither scope.


def _matches(card: dict, preset: str) -> bool:
    try:
        return get_preset(preset).matches(card)
    except KeyError:
        return False


def _life_scaled(value: int, life: int, *, floor: int) -> int:
    """``value`` (calibrated at ``_CALIBRATION_LIFE``) scaled to ``life``, rounded the
    same way ``Calibration.scaled`` rounds deck-size scaling (Python's round), never
    below ``floor``."""
    return max(floor, round(value * life / _CALIBRATION_LIFE))


def _reach_closes(trees: Sequence[ConceptTree], *, game: Game) -> bool:
    """Burn / drain that closes ``game`` (see the reach table above): each effect's
    scope paired with the fixed amount that closes from that scope."""
    group_limit = math.ceil(game.life * _BURN_CLOSER_FRACTION)
    for tree in trees:
        unbound = unbound_x_reach(tree)  # an X phase parked (its amount scales)
        if unbound == "group" or (unbound == "single" and not game.multiplayer):
            return True
        for unit in tree.units:
            for node in unit.iter_typed():
                reach = reach_amount(unit.node, node)
                if reach is None:
                    continue
                scope, amount = reach
                if scope == "single" and game.multiplayer:
                    continue
                limit = group_limit if scope == "group" else game.life
                if amount is None or amount >= limit:
                    return True
    return False


def _one_shot_team_pump(trees: Sequence[ConceptTree]) -> bool:
    """A one-shot team pump that swings for the win — Overrun, Craterhoof Behemoth,
    Triumph of the Hordes: the ``team_buff`` lane's keyword grant to your team, from
    a spell, trigger or activation, that also gives the team +N power. A static
    anthem (Akroma's Memorial, Always Watching, Glorious Anthem) is board presence,
    and a one-shot grant with no pump (Azorius Charm's lifelink, Crash Through's
    trample) is a trick, not a closer."""
    return any(
        unit.origin != "static" and static_def_adds_power(sdef)
        for tree in trees
        for unit, sdef in team_buff_sites(tree)
    )


def _voltron_pieces(classes: Sequence[CardClass]) -> list[str]:
    """The equipment / aura cards a voltron plan is made of — walked once per tune, in
    ``win_conditions``, which keeps the list for the density test, the protected set,
    and the ``voltron`` flag ``protection`` reuses."""
    return sorted(
        c.name
        for c in classes
        if _matches(c.record, "equip") or _matches(c.record, "auras")
    )


def _is_voltron(pieces: Sequence[str], deck_size: int, cal: Calibration) -> bool:
    """Equip/aura density that reads as a voltron plan (shared by the protection
    advisory and the closer count); never outside a family with the read."""
    if cal.voltron_pieces is None:
        return False
    return len(pieces) >= cal.scaled(cal.voltron_pieces, deck_size)


def _slots(cards: Sequence[CardClass]) -> int:
    """How many deck SLOTS a set of classes fills — copies, not names (a 60-card
    deck of 4-ofs holds ~15 distinct nonland names; every floor counts slots)."""
    return sum(c.quantity for c in cards)


# ── Efficiency ────────────────────────────────────────────────────────────────


def efficiency(
    classes: Sequence[CardClass],
    *,
    shape: str,
    avg_cmc: float,
    deck_size: int,
    cal: Calibration = COMMANDER,
) -> dict:
    nonland = [c for c in classes if c.bucket not in ("land", "commander")]
    ramp_classes = [c for c in classes if "ramp" in c.roles]
    low_classes = [c for c in nonland if c.cmc <= 2.0]
    top_classes = [c for c in nonland if c.cmc >= 6.0]
    ramp_cards = [c.name for c in ramp_classes]
    low_cards = [c.name for c in low_classes]
    top_cards = [c.name for c in top_classes]
    ramp, low, top = _slots(ramp_classes), _slots(low_classes), _slots(top_classes)
    cheats = _slots([c for c in classes if _matches(c.record, "reanimate")]) >= 2

    lo, hi = _AVG_BANDS.get(shape, _AVG_BANDS["midrange"])
    if (avg_cmc > _AVG_CEILING and not cheats) or avg_cmc > hi + 0.3:
        avg_status = "top_heavy"
    else:
        avg_status = "ok"

    ramp_want: int | None
    if cal.ramp_want is None:
        # Ramp is not an axis for this family (a Burn deck at zero ramp is fine).
        ramp_want, ramp_status = None, "n/a"
    else:
        low_w, mid_w, high_w = cal.ramp_want
        ramp_want = high_w if avg_cmc >= 3.3 else (low_w if avg_cmc <= 2.6 else mid_w)
        ramp_want = cal.scaled(ramp_want, deck_size)
        ramp_status = "low" if ramp < ramp_want - 2 else "ok"

    front_want = cal.scaled(
        cal.front_want.get(shape, cal.front_want[cal.default_shape]), deck_size
    )
    front_status = "thin" if low < round(front_want * 0.7) else "ok"

    top_lo = cal.scaled(cal.top_end[0], deck_size)
    top_hi = cal.scaled(cal.top_end[1], deck_size)
    if top < top_lo:
        top_status = "thin"
    elif top > top_hi:
        top_status = "clogged"
    else:
        top_status = "ok"

    if avg_status == "top_heavy":
        verdict = "top-heavy"
    elif top_status == "clogged":
        verdict = "top-end clogged"
    elif top_status == "thin":
        verdict = "thin top-end"
    elif front_status == "thin":
        verdict = "thin early game"
    else:
        verdict = "ok"

    return {
        "verdict": verdict,
        "avg_mv": {"value": round(avg_cmc, 2), "band": [lo, hi], "status": avg_status},
        "ramp": {
            "have": ramp,
            "want": ramp_want,
            "status": ramp_status,
            "cards": ramp_cards,
        },
        "front_load": {
            "have": low,
            "want": front_want,
            "status": front_status,
            "cards": low_cards,
        },
        "top_end": {
            "have": top,
            "want": [top_lo, top_hi],
            "status": top_status,
            "cards": top_cards,
        },
        "cost_cheat_waiver": cheats,
    }


# ── Focus ─────────────────────────────────────────────────────────────────────


# Doer lanes cared about beyond (or instead of) their ``<x>_matters`` /
# ``wants_<x>`` sibling (ADR-0034's naming): key -> the extra payoff keys,
# checked against the manifest. Every token doer — the creature-token maker
# and each predefined-token maker (Treasure, Clue, Food, Blood: CR 111.10) —
# is cared about by a subject-less tokens payoff and a token doubler (Adrix
# and Nev, Esix beside Deep Clue Sea's twenty Clue makers, 2026-10-18). A
# polymorph (``wants_fodder``: Jace's -3, Mass Polymorph) cares about
# creature-token makers too — the tokens are what it transforms.
_TOKEN_PAYOFF_KEYS = ("tokens_matter", "token_doubling")
# "Activated-ability engine" is served as the cost reducers, untappers and
# haste-for-abilities that power an activated ability (its spec); a card that
# merely HAS one (``activated_ability``) is the payoff target, not a builder —
# eleven such cards made it Abzan Armor's main over its forty-two-deep
# toughness lane, and two made the Jace precon's phantom emerging theme
# (2026-10-18). The untap engines are the cards that care.
_CARES_ALIASES: dict[str, tuple[str, ...]] = {
    "token_maker": (*_TOKEN_PAYOFF_KEYS, "wants_fodder"),
    **{f"{kind}_makers": _TOKEN_PAYOFF_KEYS for kind in TOKEN_SUBTYPE_PAYOFF_KEYS},
    "activated_ability": ("untap_engine",),
    # an extra step is cared about by the triggers it repeats
    **{maker: (payoff,) for maker, payoff in signal_keys.STEP_TRIGGER_KEYS.items()},
}


def _cares_keys(key: str) -> tuple[str, ...]:
    """The keys whose emitters CARE about an avenue opened by ``key``.

    A ``<x>_makers`` (doer) lane is fed by its makers, but the cards that care are
    the payoff side: ``<x>_matters`` and ``wants_<x>`` (a card whose own identity
    wants the mechanic done to it), plus its ``_CARES_ALIASES``, whichever the
    lanes serve. A doer lane with no served payoff (mill, edict, clone, theft, …)
    is cared about by its doers — the deck doing the thing is the theme. Every
    other key cares about itself."""
    candidates = _CARES_ALIASES.get(key, ())
    if key.endswith("_makers"):
        base = key[: -len("_makers")]
        candidates = (f"{base}_matters", f"wants_{base}", *candidates)
    if not candidates:
        return (key,)
    from mtg_utils._analysis.lanes import SERVED_SIGNAL_KEYS

    payoffs = tuple(k for k in candidates if k in SERVED_SIGNAL_KEYS)
    return payoffs or (key,)


def _scopes_apart(ckey: str, emitter_scope: str, avenue_scope: str) -> bool:
    """True when the cared-about key ``ckey`` gives both scopes avenues of their
    own (``SPECS`` holds an entry for each): a ``graveyard_matters|you`` payoff
    is "Your graveyard", and never cares about "Opponents' graveyards". A scope
    the key does not split (a doer's ``any`` / ``each``) stays scope-blind."""
    return (
        emitter_scope != avenue_scope
        and (ckey, emitter_scope) in SPECS
        and (ckey, avenue_scope) in SPECS
    )


# The carer-set overlap at which two avenues are one theme read twice. A Jaccard
# share, not containment: a two-carer sub whose carers also care about a 20-carer
# main is a narrower direction of its own, not the main read again.
_SAME_CARERS_SHARE = 0.9
# ...and the share of the SMALLER avenue's members the two must also have in
# common. One carer set can reward two pools no card feeds both of: subject-less
# tokens anthems care about Soldier makers and Spirit makers alike, and the two
# tribes are still two avenues. Polymorph fodder and Token generators share ten
# of the smaller's eleven members; a majority is the floor (a single shared
# card — a maker of both kinds — is not one pool).
_SAME_CARERS_MEMBER_SHARE = 0.5


def _same_carers(a: set[str], b: set[str]) -> bool:
    """Two avenues one set of cards cares about: at least two carers each and a
    Jaccard overlap of ``_SAME_CARERS_SHARE``. Below ten carers that is the same
    set exactly (the four polymorph cards caring about both "Polymorph fodder" and
    "Token generators"); a 40-carer theme tolerates a stray. One shared carer
    (Sun Titan alone) is never a fold."""
    if len(a) < 2 or len(b) < 2:
        return False
    return len(a & b) / len(a | b) >= _SAME_CARERS_SHARE


def focus(
    classes: Sequence[CardClass],
    *,
    deck_size: int,
    deck_signals: Sequence = (),
    commander_idents: frozenset[tuple[str, str, str]] = frozenset(),
    emitters: Mapping[tuple[str, str, str], frozenset[str]] | None = None,
    medium: str = "paper",
    tribal_payoff_subjects: frozenset[str] | None = None,
    cal: Calibration = COMMANDER,
    playrate_condemns: bool | None = None,
) -> dict:
    # Each deck signal's avenue, resolved once (``avenue_spec_for``: a per-subject
    # spec for a subject key's signal, and no avenue for a subject the key's own
    # serve leaves out; four passes below read it).
    resolved = [(sig, spec) for sig in deck_signals if (spec := avenue_spec_for(sig))]

    def labels_where(pred: Callable[[Signal], bool]) -> set[str]:
        return {spec.label for sig, spec in resolved if pred(sig)}

    # Avenues that are really Spine roles (ramp/draw/removal) are not themes — exclude
    # them so the deck's mana base + scaffolding can't masquerade as its main lane.
    excluded = labels_where(lambda sig: sig.key in _SPINE_AVENUE_KEYS)

    def themes(card: CardClass) -> list[str]:
        return [lbl for lbl in card.served if lbl not in excluded]

    nonland = [c for c in classes if c.bucket not in ("land", "commander")]
    engine = [c for c in classes if c.bucket == "engine"]

    # Depth counts NONLAND supporters only (a land is mana base, never theme support) of
    # genuine theme avenues — engine cards + dual-purpose Spine cards that feed a theme.
    # Names are listed once; depth counts slots (copies). The one exception is an
    # avenue whose serve says its lands feed it (``Serve.lands_feed`` — the
    # land-type lane: the Deserts a Desert payoff counts); a land feeds that
    # avenue and no other.
    land_lanes = {spec.label for _sig, spec in resolved if spec.serve.lands_feed}
    members: dict[str, list[str]] = {}
    depth: dict[str, int] = {}
    for c in classes:
        for label in themes(c):
            if c.bucket == "land" and label not in land_lanes:
                continue
            members.setdefault(label, []).append(c.name)
            depth[label] = depth.get(label, 0) + c.quantity

    # Two-tier viability (research: 1 main + 1 *sub*-theme; a sub is shallower than the
    # main, so it gets a lower floor — not the same bar as the main).
    main_floor = max(1, cal.scaled(cal.focus_main, deck_size))
    sub_floor = max(1, cal.scaled(cal.focus_sub, deck_size))
    # The cards that CARE about each avenue (its "carers"): those emitting its key,
    # read off the payoff side of the lane (a ``<x>_makers`` avenue is fed by the
    # makers, but the cards that care about it are the ``<x>_matters`` emitters —
    # nine cards in the Jace precon gain life, and only Niv-Mizzet cares).
    # ``None`` (a caller with no ``read_deck_signals`` pass: the older focus
    # tests) skips the gate: every deep avenue is built.
    # An avenue the COMMANDER itself holds (``commander_idents``: the idents the
    # commander emits, read record-level by ``read_deck_signals`` so a transform
    # commander's faces and a folded object count) is the deck's own axis. It is
    # never fed and never collapsed into a generic avenue whose members happen to
    # be the same cards: a serve that credits the lane's PAYOFFS as on-theme
    # (cheat_into_play credits every power-5+ body) can make the lane's avenue
    # ≥80 % the bombs it cheats in, and "Big creatures / power matters" (the same
    # bombs, plus a few more) then swallowed it — the Jace, Multiverse Architect
    # polymorph precon read SPREAD-THIN over Historic / Cantrips / Combat with its
    # engine unnamed (2026-10-17). Held avenues DO collapse into one another: a
    # commander's one ability emits sibling lanes (Jace's -3 is cheat_into_play,
    # dig_until and topdeck_selection at once), and the narrower reads are the
    # same cards as the broad one.
    # (A held SPINE ident — Jace's +1 draw — is scaffolding like any other:
    # it opens no lane, and its emitters (Brainstorm) are not the lane's cards.)
    held_idents = {
        (sig.key, sig.scope, sig.subject): spec.label
        for sig, spec in resolved
        if (sig.key, sig.scope, sig.subject) in commander_idents
        and spec.label not in excluded
    }
    commander_held = set(held_idents.values())
    member_sets = {lbl: frozenset(names) for lbl, names in members.items()}
    land_names = {c.name for c in classes if c.bucket == "land"}

    def folds(lbl: str, kept: Sequence[str], same: Callable[[str, str], bool]) -> bool:
        """``lbl`` is a kept avenue read again (``same``): against any kept
        avenue for an ordinary one, only the commander's other lanes for a lane
        the commander holds."""
        if lbl in commander_held:
            kept = [k for k in kept if k in commander_held]
        return any(same(lbl, k) for k in kept)

    def same_members(lbl: str, k: str) -> bool:
        """≥80 % of ``lbl``'s members are ``k``'s."""
        s = member_sets.get(lbl, frozenset())
        return bool(s) and len(s & member_sets[k]) / len(s) >= 0.8

    # The commander's own lanes, collapsed among themselves (deepest first: one
    # ability's sibling reads share the same cards, and the broad read is the
    # lane). The PRIMARY lane among them is chosen below, once the carers are
    # known. The commander's lanes are a set, so the label breaks a depth tie:
    # set order made Death Toll's "Your graveyard" / "Graveyard engine" (one
    # lane, equally deep) swap from run to run. Every later ordering walks
    # this list or the deck's ranked signals, both deterministic.
    held_kept: list[str] = []
    for lbl in sorted(
        commander_held, key=lambda lbl: (depth.get(lbl, 0), lbl), reverse=True
    ):
        if not folds(lbl, held_kept, same_members):
            held_kept.append(lbl)
    commander_members: set[str] = set()
    for lbl in held_kept:
        commander_members.update(member_sets.get(lbl, ()))
    # The cards that DO what the commander's lanes do (emit an ident of a lane
    # that survived the collapse) — the polymorphs beside Jace, not the bombs
    # the serve credits as their payoffs, and not the scry cards a collapsed
    # sibling read (topdeck_selection) would have swept in.
    lane_doers: set[str] = set()
    for ident, lbl in held_idents.items():
        if lbl in held_kept and emitters is not None:
            lane_doers.update(emitters.get(ident, ()))
    lane_doers -= land_names

    # The cards that CARE about each avenue (its "carers"): those emitting its
    # key, read off the payoff side of the lane (a ``<x>_makers`` avenue is fed
    # by the makers, but the cards that care about it are the ``<x>_matters``
    # emitters — nine cards in the Jace precon gain life, and only Niv-Mizzet
    # cares). The read ignores scope where the payoff key does not split by it
    # (a doer lane emits ``any`` / ``each`` where its payoff sibling emits
    # ``you``); a key whose specs give ``you`` and ``opponents`` avenues of
    # their own (graveyard_matters, lifeloss_matters, creature_etb) credits an
    # emitter to its own scope's avenue alone — under Teval every self-mill
    # payoff read as a carer of "Opponents' graveyards" too, 43 of them
    # (``_scopes_apart``). Carers never count lands (a creature land's attack
    # trigger is mana base that happens to attack, not a card built toward
    # Combat). A payoff with no subject cares about every subject of its doer
    # key (a tokens anthem cares about Mite makers and Soldier makers alike).
    # ``None`` (a caller with no ``read_deck_signals`` pass: the older focus
    # tests) skips the gate: every deep avenue is built.
    cares: dict[str, set[str]] = {}
    if emitters is not None:
        by_key_subject: dict[tuple[str, str], dict[str, set[str]]] = {}
        for (ekey, escope, esubject), names in emitters.items():
            by_key_subject.setdefault((ekey, esubject), {}).setdefault(
                escope, set()
            ).update(names)
        for sig, spec in resolved:
            bucket = cares.setdefault(spec.label, set())
            avenue_scope = spec_scope_for(sig.key, sig.scope) or sig.scope
            for ckey in _cares_keys(sig.key):
                subjects = (
                    (sig.subject, "")
                    if sig.subject
                    and (sig.key, sig.subject) not in signal_keys.DOER_SUBJECTS
                    else ("",)
                )
                for subject in subjects:
                    for escope, names in by_key_subject.get(
                        (ckey, subject), {}
                    ).items():
                        if not _scopes_apart(ckey, escope, avenue_scope):
                            bucket.update(names)
            bucket.difference_update(land_names)

    def own_carers(lbl: str) -> set[str]:
        """The cards that care about ``lbl`` on their own account. A carer the
        commander's lane serves as a PAYOFF (a member of a held avenue that does
        not itself emit the held ident) is the commander's lane seen through a
        sibling key — the power-5+ bombs Jace cheats in carry attack triggers
        and spell triggers, which read as nine cards building toward Combat and
        a Spellslinger main — so it is discounted here. A card that DOES what
        the lane does (a polymorph wanting fodder) and a card the lane does not
        account for (Dreadhorde Invasion, Windcrag Siege) still count. The held
        avenues themselves keep every carer."""
        carers = cares.get(lbl, set())
        if lbl in commander_held:
            return carers
        return {
            n for n in carers if not (n in commander_members and n not in lane_doers)
        }

    carers = {lbl: own_carers(lbl) for lbl in cares}
    carer_floor = max(1, cal.scaled(cal.focus_carers, deck_size))
    main_carer_floor = max(carer_floor, cal.scaled(cal.focus_main_carers, deck_size))

    def care_count(lbl: str) -> int:
        return len(carers.get(lbl, ()))

    def one_theme(lbl: str, k: str) -> bool:
        """``lbl`` is ``k`` read again: ≥80 % its members, or the same cards
        caring about both (``_same_carers``) over largely the same members
        (``_SAME_CARERS_MEMBER_SHARE``). The polymorphs care about "Polymorph
        fodder" and "Token generators" alike (``_CARES_ALIASES``), and under
        Jace the two read as two subs with one carer set (Multiverse Reforged,
        2026-10-18)."""
        if same_members(lbl, k):
            return True
        mine, theirs = member_sets.get(lbl, frozenset()), member_sets[k]
        smaller = min(len(mine), len(theirs))
        return (
            smaller > 0
            and len(mine & theirs) / smaller >= _SAME_CARERS_MEMBER_SHARE
            and _same_carers(carers.get(lbl, set()), carers.get(k, set()))
        )

    # The commander's PRIMARY lane: of its own lanes, the one the most cards
    # care about, then the deepest. Depth alone picked "Combat" (17 deep, 12
    # caring) over "Goad & politics" (16 deep, 16 caring) under Nelly Borca,
    # whose attack trigger is how she goads (Blame Game precon, 2026-10-18).
    # Only a held lane deep enough to be shown can be the primary: Bello's
    # "Combat damage to opponents" (4 deep, 4 caring) outranked his Animation
    # lane (28 deep, 1 caring) and, below the sub floor, was never reported — so
    # the deck had no main at all (Animated Army precon, 2026-10-18).
    showable = [lbl for lbl in held_kept if depth.get(lbl, 0) >= sub_floor]
    primary = (
        max(showable or held_kept, key=lambda lbl: (care_count(lbl), depth.get(lbl, 0)))
        if held_kept
        else None
    )

    def built(lbl: str, floor: int, *, in_proportion: bool = False) -> bool:
        """Deep in feeders AND enough cards care (or the commander does). On the
        stock Jace precon "Historic" was 32 deep — every legendary creature and
        every rock serves it — with one card caring (Jhoira), and read as the
        main theme while the polymorph engine read as a sub (2026-10-17).
        ``in_proportion`` also holds the carers to ``focus_main_carer_share``
        of the depth."""
        if emitters is None or lbl in commander_held:
            return True
        care = care_count(lbl)
        return care >= floor and (
            not in_proportion or care >= cal.focus_main_carer_share * depth[lbl]
        )

    def rank_key(lbl: str) -> tuple[bool, bool, int, int]:
        """The commander's own lanes first (the issue remedies source adds from
        the first viable avenue), the primary at their head, then the deepest —
        then by how many cards care, then by depth."""
        if lbl in commander_held:
            return (True, lbl == primary, depth[lbl], care_count(lbl))
        return (False, False, care_count(lbl), depth[lbl])

    # Built avenues rank by ``rank_key``; a fed avenue (deep, but nobody built
    # toward it) is reported apart and shapes nothing.
    candidates: list[str] = []
    fed: list[str] = []
    for lbl, d in depth.items():
        if d >= sub_floor:
            (candidates if built(lbl, carer_floor) else fed).append(lbl)
    candidates.sort(key=rank_key, reverse=True)
    # Every avenue somebody built toward, collapsed near-duplicates included (a
    # card on the Magecraft side of a Spellslinger / Magecraft pair is still
    # on a built theme): what the fed-only re-bucket below measures against.
    built_labels = set(candidates)
    # Collapse near-duplicate avenues that are really one theme: drop an avenue
    # ≥80% covered by one already kept, or cared about by the same cards — a
    # higher-ranked one, which since the commander-held / carers ordering above
    # need not be the deeper one (e.g. Spellslinger / Magecraft).
    viable: list[str] = []
    for lbl in candidates:
        if not folds(lbl, viable, one_theme):
            viable.append(lbl)

    # The commander's primary lane is a main theme by definition, whatever its
    # depth. Any other main needs depth AND builders: a broad serve (every
    # artifact, every instant) is deep in any deck, so without the carer bar
    # "Artifacts" read as a main theme on sixteen rocks (2026-10-18). Builders
    # are also measured against the feeders (``focus_main_carer_share``).
    # A main the commander does not hold is a direction of its own only when its
    # builders are its own: when at least half of them also care about the
    # primary lane it is the primary seen through another key, a sub beside it.
    # Quick Draw's spells-in-the-graveyard payoffs (22 deep, 12 caring, seven of
    # them Spellslinger carers) read as a second main and the precon as
    # SPREAD-THIN once surveil and flashback reached the graveyard serve
    # (2026-10-18). Half is this read's own line, not a rule.
    primary_carers = carers.get(primary, set()) if primary else set()

    def leans_on_primary(lbl: str) -> bool:
        own = carers.get(lbl, set())
        return bool(own) and len(own & primary_carers) * 2 >= len(own)

    def is_main(lbl: str) -> bool:
        if lbl == primary:
            return True
        care = care_count(lbl)
        builders = emitters is None or (
            care >= main_carer_floor and care >= cal.focus_main_carer_share * depth[lbl]
        )
        return (
            depth[lbl] >= main_floor
            and builders
            and (lbl in commander_held or not leans_on_primary(lbl))
        )

    mains: list[str] = []
    subs: list[str] = []
    for lbl in viable:
        (mains if is_main(lbl) else subs).append(lbl)

    # Emerging themes: a real-but-under-supported direction (emerging floor ≤ depth <
    # sub floor) the deck started but didn't commit to — flagged "commit more or cut"
    # rather than dropped as noise. Deduped against the viable themes (a subset of a
    # real theme is not its own emerging theme).
    #
    # ADR-0040 companion (task #101): an emerging TRIBAL avenue additionally needs a
    # non-commander payoff card naming the tribe, or changelings (every creature
    # type — signal_specs._subject_spec folds them into every subject's Serve) SERVE
    # every tribal avenue that's open at all, manufacturing an emerging flag for
    # tribes nobody built toward (the "Bird tribal" phantom on a changeling-heavy
    # deck). Built from ``resolved`` (label -> subject, via ``avenue_spec_for`` — the
    # same per-subject dynamic label the avenue itself carries); viable avenues are
    # untouched (already past a much higher floor) and non-tribal labels never
    # appear in this map, so the gate is a no-op for them.
    tribal_subject_of_label: dict[str, str] = {}
    if tribal_payoff_subjects is not None:
        for sig, spec in resolved:
            if sig.key == signal_keys.TYPE_MATTERS and sig.subject:
                tribal_subject_of_label[spec.label] = sig.subject

    emerging_floor = max(1, cal.scaled(cal.focus_emerging, deck_size))
    # An emerging direction needs builders the way a main does, at its own
    # scale: at least two carers (half the sub's carer floor, never one card)
    # AND carers a ``focus_main_carer_share`` of its depth. One card caring
    # about nine feeders is a payoff, not a direction — Sun Titan beside nine
    # permanents read as a "Permanent recast engine" (Blame Game), Niv-Mizzet
    # and Proteus Staff beside nine activated abilities as an engine (Multiverse
    # Reforged, 2026-10-18). Below it the avenue is fed at emerging depth.
    emerging_carer_floor = max(2, math.ceil(carer_floor / 2))
    emerging: list[str] = []
    for lbl in sorted(depth, key=rank_key, reverse=True):
        if not emerging_floor <= depth[lbl] < sub_floor:
            continue
        if not built(lbl, emerging_carer_floor, in_proportion=True):
            fed.append(lbl)
            continue
        built_labels.add(lbl)
        if folds(lbl, viable + emerging, one_theme):
            continue
        subj = tribal_subject_of_label.get(lbl)
        if (
            subj is not None
            and tribal_payoff_subjects is not None
            and subj not in tribal_payoff_subjects
        ):
            continue
        emerging.append(lbl)

    # An Engine card whose every avenue is fed (or stranded below the emerging
    # floor) feeds nothing the deck built toward: it is dead weight here — a
    # legendary 3-drop in a polymorph deck "serves" Historic — and classification
    # ran before focus knew which avenues are built, so the re-bucket happens
    # here (``tune`` re-buckets the classes by ``fed_only_cards``). Lands and the
    # commander are never engine; a Spine card keeps its role.
    # Only once something IS built: a deck with no viable avenue yet (a build in
    # progress) has nothing to measure "not built toward" against, and its
    # theme cards must not all read as filler for the role fills to cut.
    # A card that CARES about a built avenue is building toward it, whatever
    # it serves: Adrix and Nev and Esix serve only "Token doubling" (fed), and
    # double the Clues the deck's main lane makes (Deep Clue Sea, 2026-10-18).
    built_carers: set[str] = set().union(
        *(carers.get(lbl, set()) for lbl in built_labels)
    )
    fed_only_classes = (
        [
            c
            for c in engine
            if not built_labels.intersection(themes(c)) and c.name not in built_carers
        ]
        if viable
        else []
    )
    fed_only_names = {c.name for c in fed_only_classes}
    engine_built = [c for c in engine if c.name not in fed_only_names]
    engine_pool = _slots(engine_built)

    top2 = set(viable[:2])
    in_top2 = _slots([c for c in engine_built if top2.intersection(themes(c))])
    top2_share = round(in_top2 / engine_pool, 2) if engine_pool else 0.0

    filler_classes = [c for c in nonland if c.bucket == "filler"] + fed_only_classes
    filler_cards = [c.name for c in filler_classes]
    filler = _slots(filler_classes)
    filler_rate = round(filler / max(1, _slots(nonland)), 2)

    # Low-value Engine cards (``CardClass.low_value``) — the vanilla beater that
    # "counts" as creature support in a go-wide deck — surfaced as upgrade targets.
    # Play-rate condemns only where it means something (a paper-EDH population),
    # and never a card that does what the commander's lane does: play-rate is a
    # population's verdict on a card in general, not on a polymorph piece under
    # a polymorph commander (the precon's new Identity Echo has no rank at all).
    # A payoff the lane merely serves (a weak flip) stays an upgrade target.
    # tune passes Calibration.playrate_condemns; without it, the family's.
    condemns = (
        cal.playrate_meaningful if playrate_condemns is None else playrate_condemns
    )
    low_value_classes = [
        c
        for c in nonland
        if c.name not in fed_only_names
        and c.name not in lane_doers
        and c.low_value(medium=medium, playrate=condemns)
    ]
    low_value_cards = [c.name for c in low_value_classes]
    # Cards the upgrade read leaves alone: cut by an earlier tier (fed-only,
    # low-value), or on a lane (a doer of the commander's, a carer of a built
    # theme).
    elsewhere = fed_only_names | set(low_value_cards) | lane_doers | built_carers
    # The upgrade slots: a card off every lane the deck holds — no doer of the
    # commander's lanes, no carer of a built theme — that few decks play
    # (``classify.UPGRADE_RANK``). The guides' commonest move (2026-10-19):
    # the precon's off-lane removal, draw, ramp and good-stuff traded for the
    # staple that does the same job. Filler and low-value cards are cut by
    # their own tiers first; a meta-read deck has its own share read; a
    # Granter is judged by its grant, never by play-rate (ADR-0040 §4).
    upgrade_cards = (
        sorted(
            c.name
            for c in nonland
            if c.bucket in ("spine", "engine")
            and c.meta_share is None
            and c.grant_grade is None
            and c.name not in elsewhere
            and is_upgrade_target(c.edhrec_rank, medium=medium)
        )
        if condemns
        else []
    )
    # The deep lane's upgrade slots: once the commander's lanes hold
    # ``lane_upgrade_floor`` engine doers, their least-played half. Measured
    # against the upgrade guides' cuts inside the 25 precons' lanes (906 lane
    # cards, 222 guide cuts, 2026-10-18): a member that does NOT itself care
    # about the lane (an artifact that is just an artifact under an Artifacts
    # main; in a tribal lane every member is a carer, so there the order is
    # play-rate alone) before one that does, then least played, puts a guide
    # cut in the top five 48% of the time; the same half ordered
    # costlier-first managed 30%, and no function read (one-shot vs
    # repeatable, body for its cost, in-deck synergy depth, how many lanes a
    # card touches) moved the rate off the 25% base at all. A premium card is
    # never one. The lane's carers are the union over every held lane. A doer
    # that also fills a template role is in the pool too (its upgrade keeps the
    # role): at fourteen swaps that reached nine more guide cuts (139 vs 130 of
    # 404) at the same precision, where taking two-thirds of the engine doers
    # instead of half reached none (2026-10-19).
    lane_carers = set().union(*(carers.get(lbl, set()) for lbl in held_kept))
    lane_pool = [
        c
        for c in nonland
        if c.bucket in ("engine", "spine")
        and c.name not in fed_only_names
        and c.name in lane_doers
        and c.grant_grade is None
        and not (cal.playrate_meaningful and is_premium(c.edhrec_rank))
    ]
    lane_upgrade_cards: list[str] = []
    if len(lane_pool) >= cal.scaled(cal.lane_upgrade_floor, deck_size):
        lane_pool.sort(key=lambda c: (c.name in lane_carers, c.least_played_key))
        lane_upgrade_cards = [c.name for c in lane_pool[: len(lane_pool) // 2]]

    engine_labels = {lbl for c in engine_built for lbl in themes(c)}
    stranded = sorted(lbl for lbl in engine_labels if 1 <= depth.get(lbl, 0) <= 2)

    spine_led_floor = max(1, cal.scaled(cal.spine_led, deck_size))
    # Main directions competing for the engine slots: the commander's own lanes
    # count as ONE direction however many it holds (Saheeli, Radiant Creator
    # holds Artifacts and Energy; that is her design, not a deck pulled two
    # ways), every other main is a direction of its own.
    competing = len(set(mains) - commander_held) + bool(
        commander_held.intersection(mains)
    )
    if engine_pool < spine_led_floor:
        verdict = "SPINE-LED"
    elif competing >= 2 or (not mains and len(subs) >= 3):
        # Two directions competing, or a crowd of sub-themes with no main among
        # them. One main with light subs is focused, however many: a sub is by
        # definition a few cards caring, and nine of 25 precons read SPREAD-THIN
        # on "a main plus three subs" with a 27-43-carer main (2026-10-18).
        verdict = "SPREAD-THIN"
    elif viable:
        verdict = "FOCUSED"  # 1 main (+ subs), or 1-2 subs
    else:
        # A substantial engine pool that coheres into no theme at all is scattered.
        verdict = "SPREAD-THIN"

    def avenue_row(lbl: str) -> dict:
        return {
            "label": lbl,
            "depth": depth[lbl],
            "carers": care_count(lbl),
            "carer_cards": sorted(carers.get(lbl, ())),
            "cards": members[lbl],
        }

    return {
        "verdict": verdict,
        "engine_pool": engine_pool,
        "viable_avenues": [
            {**avenue_row(lbl), "tier": "main" if is_main(lbl) else "sub"}
            for lbl in viable
        ],
        "mains": mains,
        "subs": subs,
        "emerging": [avenue_row(lbl) for lbl in emerging],
        # Deep in feeders, short of cards that care: reported so the reader sees
        # "32 cards are historic", shaping no verdict, cut or fit read. Deepest
        # first.
        "fed": [
            avenue_row(lbl)
            for lbl in sorted(fed, key=lambda lbl: depth[lbl], reverse=True)
        ],
        # The viable avenues the commander itself holds (its own lanes), in rank
        # order: the issue remedies deepen these before any emerging direction.
        "commander_avenues": [lbl for lbl in viable if lbl in commander_held],
        # Engine cards that feed only fed / stranded avenues — dead weight here;
        # ``tune`` re-buckets them as filler so the cut ranking sees them.
        "fed_only_cards": sorted(fed_only_names),
        # The nonland cards doing what the commander's lanes do — what the cut
        # ranking protects as the commander's own pieces.
        "commander_lane_cards": sorted(lane_doers),
        # The cards that CARE about the commander's lanes (the union of carers
        # over every held lane that survived the collapse) — what the lane cut
        # tier spares, cutting the lane's plain feeders first (``swaps``).
        "commander_lane_carers": sorted(lane_carers),
        # The nonland cards the commander's lanes SERVE (members of a held
        # avenue: every artifact under Gimbal, every Clue under Morska) — what
        # a template band is measured against before it trims (``tune``).
        "commander_lane_members": sorted(commander_members - land_names),
        "carer_floor": carer_floor,
        "main_carer_floor": main_carer_floor,
        "emerging_carer_floor": emerging_carer_floor,
        "main_floor": main_floor,
        "sub_floor": sub_floor,
        "top2_concentration": top2_share,
        "filler": filler,
        "filler_rate": filler_rate,
        "filler_cards": filler_cards,
        "low_value": _slots(low_value_classes),
        "low_value_cards": low_value_cards,
        "upgrade_cards": upgrade_cards,
        # The deep lane's least-played half, in cut order (feeders first).
        "lane_upgrade_cards": lane_upgrade_cards,
        "stranded_avenues": stranded,
        "_depth": depth,
    }


# ── Template deviation (over the shared slot_budgets) ───────────────────────────


def template_deviation(budgets: dict) -> dict:
    """The hard-counted rows drive the verdict and the issues; an ``advisory`` row
    (a fact about the deck — a creature count) is reported beside them, never as a
    deviation to fix (CONTEXT: Template deviation)."""
    # A ``lane_row`` (the commander's lane counted as a template row — ``tune``)
    # stays in ``over``: the deck IS off-template there, as a Grant-covered
    # short row is; the issue it raises is advisory and sources nothing.
    counted = {r: b for r, b in budgets.items() if not b.get("advisory")}
    short = {r: b for r, b in counted.items() if b["deviation"] < 0}
    over = {r: b for r, b in counted.items() if b["deviation"] > 0}
    advisory = {
        r: b for r, b in budgets.items() if b.get("advisory") and b["deviation"] != 0
    }
    return {
        "verdict": "on-template" if not short and not over else "off-template",
        "short": short,
        "over": over,
        "advisory": advisory,
        "budgets": budgets,
    }


# ── Tier-2 advisory flags ──────────────────────────────────────────────────────


def is_wincon_card(card: dict, *, game: Game = CALIBRATION_GAME) -> bool:
    """Heuristic finisher read over the card's trees (every face), relative to
    ``game``: its starting life sets the evasive-body and fixed-reach thresholds,
    and one opponent admits single-target reach (the same finisher "each opponent"
    is at a pod). A closer is a card that wins or makes another player lose
    (``reads.ends_the_game`` — not Pact of Negation's self-loss), an extra combat
    (the ``extra_combats`` key), a one-shot team pump, reach that closes, or a big
    evasive body (an evasion keyword, landwalk among them — CR 702.14c — or a
    blocking restriction on itself, CR 509.1b)."""
    trees = trees_for(card)
    if any(ends_the_game(tree) for tree in trees):
        return True
    if _matches(card, "extra-combats") or _one_shot_team_pump(trees):
        return True
    if _reach_closes(trees, game=game):
        return True
    power_floor = _life_scaled(
        _EVASIVE_CLOSER_POWER, game.life, floor=_EVASIVE_CLOSER_POWER_FLOOR
    )
    if is_creature(card) and card_pt_int(card) >= power_floor:
        return has_evasion(card) or any(is_evasive_body(tree) for tree in trees)
    return False


def win_conditions(
    classes: Sequence[CardClass],
    *,
    shape: str,
    combo_count: int,
    deck_size: int = 100,
    game: Game = CALIBRATION_GAME,
    cal: Calibration = COMMANDER,
) -> dict:
    """Dedicated closers vs the Shape's band (ADR-0024 advisory), read against the
    ``Game`` the deck plays (``Format.game``). A voltron plan (equip/aura density) is
    one closer only where 21 commander damage wins (CR 903.10a, Commander's extra
    loss rule; Brawl games do not use it, CR 903.12h); elsewhere it must deal the
    whole starting life and is surfaced as ``voltron_needs_real_damage``."""
    # ADR-0040 §5 (task #100): a Granter granting a closer-grade ability
    # (team double strike) is ONE closer — the record heuristic alone missed
    # keyword grants, reading the benchmark deck "2 closers" while it held
    # team double strike twice.
    closers = {
        c.name: c
        for c in classes
        if is_wincon_card(c.record, game=game) or c.grant_closer
    }
    cards = sorted(closers)
    pieces = _voltron_pieces(classes)
    voltron = _is_voltron(pieces, deck_size, cal)
    voltron_closer = voltron and game.commander_damage
    count = _slots(list(closers.values())) + combo_count + (1 if voltron_closer else 0)
    lo, hi = cal.wincon_target.get(shape, cal.wincon_target[cal.default_shape])
    lo = _life_scaled(lo, game.life, floor=2)
    # The band keeps at least one card of width, so a low-life control/combo band
    # never collapses to "wants 2-2".
    hi = max(lo + 1, _life_scaled(hi, game.life, floor=2))
    return {
        "count": count,
        "from_combos": combo_count,
        "cards": cards,  # the heuristic finisher cards (combos add to count, not names)
        "target": [lo, hi],
        "status": "low" if count < lo else "ok",
        "life": game.life,
        "multiplayer": game.multiplayer,
        # The one voltron read (equip/aura density); ``protection`` takes it from here
        # rather than walking the pieces again.
        "voltron": voltron,
        # The commander-damage plan counted as one closer (CR 903.10a applies), and
        # the pieces it is made of — what the cut-protection floor keeps.
        "voltron_commander_damage": voltron_closer,
        "voltron_cards": pieces if voltron_closer else [],
        # A voltron plan with no 21-damage rule: it has to deal the whole life total.
        "voltron_needs_real_damage": voltron and not game.commander_damage,
    }


def protection(
    classes: Sequence[CardClass],
    *,
    shape: str,
    deck_size: int,
    voltron: bool,
    cal: Calibration = COMMANDER,
) -> dict:
    """Protection wants vs the Shape (ADR-0024 advisory). ``voltron`` is the read
    ``win_conditions`` already made (``wins["voltron"]``) — the one voltron walk."""
    protecting = [c for c in classes if protects(c.record)]
    cards = [c.name for c in protecting]
    wants = shape in ("combo", "control") or voltron
    target = cal.scaled(cal.protection_target, deck_size) if wants else 0
    return {
        "count": _slots(protecting),
        "cards": cards,
        "target": target,
        "wants_protection": wants,
        "status": "low" if wants and _slots(protecting) < target else "ok",
    }


# ── Commander fit ──────────────────────────────────────────────────────────────


def commander_fit(classes: Sequence[CardClass], focus_result: dict) -> dict:
    commanders = [c for c in classes if c.bucket == "commander"]
    viable = {a["label"] for a in focus_result["viable_avenues"]}
    served = {lbl for c in commanders for lbl in c.served}
    served_viable = sorted(served & viable)
    fit = round(len(served_viable) / len(viable), 2) if viable else 1.0
    # Only meaningful once the deck has ≥2 viable avenues; a single-avenue deck can't be
    # "built for a different commander" on this signal. A commander whose OWN lane
    # is a viable avenue (``commander_avenues``) is never a misfit, however many
    # side themes the deck carries beside it: the Jace precon read "serves 1/4
    # viable avenues — may be built for a different commander" with its polymorph
    # lane first on the list (2026-10-18).
    held = focus_result.get("commander_avenues") or []
    misfit = len(viable) >= 2 and fit < 0.5 and not held
    return {
        "fit": fit,
        "serves_viable": served_viable,
        "viable_count": len(viable),
        "misfit": misfit,
    }
