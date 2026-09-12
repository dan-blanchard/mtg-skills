"""The three diagnostic metrics + the Tier-2 flags + the severity-ranked Top issues.

Efficiency (Shape-aware curve/tempo — NOT per-card power, ADR-0009), Template deviation
(over the shared ``slot_budgets`` bands), and Focus (Engine-card concentration over the
deck's signal-derived avenues). Win-cons and protection are Shape-scaled advisory flags
(ADR-0024). Every readout is transparent (matching deck-forge's gate style); none is an
opaque score. ``top_issues`` ranks the findings by severity and is the single
ordering the swap engine acts on (deck-forge CONTEXT.md, "Tune").
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._ir_lookup import ir_for
from mtg_utils._deck_forge.budgets import protects
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._tuner.classify import CardClass, is_fringe
from mtg_utils.card_classify import card_pt_int, is_creature
from mtg_utils.card_ir import Card
from mtg_utils.formats import Game
from mtg_utils.theme_presets import get_preset

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

# Shape → desired front-load (cmc<=2 nonland) and ramp, per 100 cards.
_FRONT_WANT = {"aggro": 18, "midrange": 14, "control": 10, "combo": 12}

# The Game every band below is calibrated at: the 40-life Commander pod (CR 103.4c),
# where 21 commander damage wins (CR 903.10a). ``win_conditions`` scales from it to the
# Game the deck actually plays (``Format.game``).
_CALIBRATION_GAME = Game(
    medium="paper", life=40, multiplayer=True, commander_damage=True
)
_CALIBRATION_LIFE = _CALIBRATION_GAME.life

# Shape → (min, max) dedicated closers (ADR-0024; floor ~3, archetype-scaled) at
# _CALIBRATION_GAME. Both bounds scale with starting life (``_life_scaled``): at 25 life
# one-on-one, ordinary threats close games and fewer dedicated closers are wanted.
_WINCON_TARGET = {
    "aggro": (4, 6),
    "midrange": (3, 6),
    "control": (2, 4),
    "combo": (2, 3),
}
# An evasive body reads as a closer from this power at _CALIBRATION_LIFE (~7 swings);
# the threshold scales with life so a 4-power flyer counts at 25 (~6 swings) but not
# at 40.
_EVASIVE_CLOSER_POWER = 6
_EVASIVE_CLOSER_POWER_FLOOR = 3
# A fixed-amount burn / drain is a closer when one resolution takes at least this share
# of starting life: 5 at _CALIBRATION_LIFE, 4 at 30, 3 at 25 or 20.
_BURN_CLOSER_FRACTION = 0.12

# Heuristic finisher oracle patterns (labeled heuristic; combos are the precise source).
_WINCON_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        # Guard "can't win" — Platinum Angel ("your opponents can't win the game") is
        # self-protection, not a finisher.
        r"(?<!can't )(?<!cannot )wins? the game",
        # Opponent-scoped: a real alt-win makes an OPPONENT lose (CR 104.3e). The bare
        # r"loses? the game" matched self-loss DRAWBACKS (Pact of Negation "you lose the
        # game") and self-protection (Platinum Angel "you can't lose the game").
        r"(?:each opponent|target (?:player|opponent)|that player) loses? the game",
        r"an additional combat phase",
        r"extra combat",
        r"infinite",
        # Burn / drain reach (scaling or fixed, group or single-target) is read by
        # ``_reach_closes`` against the Game, not here.
        r"creatures you control get \+\d",
    )
]
# Reach — burn / drain that ends a game — is ONE scope table x ONE amount read. Group
# scope ("each opponent") counts at any table; single-target scope counts only
# one-on-one, where "any target" is the finisher "each opponent" is at a pod. A
# SCALING amount (X, "equal to …") is always a closer. A FIXED amount is a closer when
# one resolution takes ``_BURN_CLOSER_FRACTION`` of starting life in group scope, or
# the WHOLE starting life in single-target scope (Aetherflux Reservoir's 50 is a
# one-on-one closer; a bolt is removal, never a closer, even at 25 life).
_GROUP_SCOPE = r"each opponent"
_SINGLE_SCOPE = r"any target|target (?:player|opponent)"
# ``{scope}`` is substituted with str.replace, not str.format, so a regex quantifier
# such as ``{1,2}`` can join a template without colliding with the placeholder.
_REACH_TEMPLATES = (
    r"deals? (?P<amount>\d+|x) damage to (?:{scope})",
    r"deals? damage to (?:{scope}) equal to",
    r"(?:{scope}) loses? (?P<amount>\d+|x) life",
    r"(?:{scope}) loses? life equal to",
)


def _reach_patterns(scope: str) -> list[re.Pattern[str]]:
    return [
        re.compile(t.replace("{scope}", scope), re.IGNORECASE) for t in _REACH_TEMPLATES
    ]


_GROUP_REACH = _reach_patterns(_GROUP_SCOPE)
_SINGLE_REACH = _reach_patterns(_SINGLE_SCOPE)
_EVASION = ("flying", "menace", "trample", "can't be blocked", "shadow", "fear")


def _matches(card: dict, preset: str) -> bool:
    try:
        return get_preset(preset).matches(card)
    except KeyError:
        return False


def _scaled(value: int, deck_size: int) -> int:
    return round(value * deck_size / 100)


def _life_scaled(value: int, life: int, *, floor: int) -> int:
    """``value`` (calibrated at ``_CALIBRATION_LIFE``) scaled to ``life``, rounded the
    same way ``_scaled`` rounds deck-size scaling (Python's round), never below
    ``floor``."""
    return max(floor, round(value * life / _CALIBRATION_LIFE))


def _reach_closes(text: str, *, game: Game) -> bool:
    """Burn / drain that closes ``game`` (see the reach table above): each scope's
    patterns paired with the fixed amount that closes from that scope."""
    scopes = [(_GROUP_REACH, math.ceil(game.life * _BURN_CLOSER_FRACTION))]
    if not game.multiplayer:
        scopes.append((_SINGLE_REACH, game.life))
    for patterns, fixed_limit in scopes:
        for pat in patterns:
            for m in pat.finditer(text):
                amount = m.groupdict().get("amount")
                scaling = amount is None or amount.lower() == "x"
                if scaling or int(amount) >= fixed_limit:
                    return True
    return False


def _voltron_pieces(classes: Sequence[CardClass]) -> list[str]:
    """The equipment / aura cards a voltron plan is made of — walked once per tune, in
    ``win_conditions``, which keeps the list for the density test, the protected set,
    and the ``voltron`` flag ``protection`` reuses."""
    return sorted(
        c.name
        for c in classes
        if _matches(c.record, "equip") or _matches(c.record, "auras")
    )


def _is_voltron(pieces: Sequence[str], deck_size: int) -> bool:
    """Equip/aura density that reads as a voltron plan (shared by the protection
    advisory and the closer count)."""
    return len(pieces) >= _scaled(4, deck_size)


# ── Efficiency ────────────────────────────────────────────────────────────────


def efficiency(
    classes: Sequence[CardClass], *, shape: str, avg_cmc: float, deck_size: int
) -> dict:
    nonland = [c for c in classes if c.bucket not in ("land", "commander")]
    ramp_cards = [c.name for c in classes if "ramp" in c.roles]
    low_cards = [c.name for c in nonland if c.cmc <= 2.0]
    top_cards = [c.name for c in nonland if c.cmc >= 6.0]
    ramp, low, top = len(ramp_cards), len(low_cards), len(top_cards)
    cheats = sum(1 for c in classes if _matches(c.record, "reanimate")) >= 2

    lo, hi = _AVG_BANDS.get(shape, _AVG_BANDS["midrange"])
    if (avg_cmc > _AVG_CEILING and not cheats) or avg_cmc > hi + 0.3:
        avg_status = "top_heavy"
    else:
        avg_status = "ok"

    ramp_want = 12 if avg_cmc >= 3.3 else (9 if avg_cmc <= 2.6 else 10)
    ramp_want = _scaled(ramp_want, deck_size)
    ramp_status = "low" if ramp < ramp_want - 2 else "ok"

    front_want = _scaled(_FRONT_WANT.get(shape, 14), deck_size)
    front_status = "thin" if low < round(front_want * 0.7) else "ok"

    top_lo, top_hi = _scaled(2, deck_size), _scaled(8, deck_size)
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


def focus(
    classes: Sequence[CardClass],
    *,
    deck_size: int,
    deck_signals: Sequence = (),
    medium: str = "paper",
    tribal_payoff_subjects: frozenset[str] | None = None,
) -> dict:
    # Avenues that are really Spine roles (ramp/draw/removal) are not themes — exclude
    # them so the deck's mana base + scaffolding can't masquerade as its main lane.
    excluded = {
        spec.label
        for sig in deck_signals
        if sig.key in _SPINE_AVENUE_KEYS and (spec := spec_for(sig)) is not None
    }

    def themes(card: CardClass) -> list[str]:
        return [lbl for lbl in card.served if lbl not in excluded]

    nonland = [c for c in classes if c.bucket not in ("land", "commander")]
    engine = [c for c in classes if c.bucket == "engine"]
    engine_pool = len(engine)

    # Depth counts NONLAND supporters only (a land is mana base, never theme support) of
    # genuine theme avenues — engine cards + dual-purpose Spine cards that feed a theme.
    members: dict[str, list[str]] = {}
    for c in classes:
        if c.bucket == "land":
            continue
        for label in themes(c):
            members.setdefault(label, []).append(c.name)
    depth = {lbl: len(names) for lbl, names in members.items()}

    # Two-tier viability (research: 1 main + 1 *sub*-theme; a sub is shallower than the
    # main, so it gets a lower floor — not the same bar as the main).
    main_floor = max(1, _scaled(20, deck_size))
    sub_floor = max(1, _scaled(10, deck_size))
    candidates = sorted(
        (lbl for lbl, d in depth.items() if d >= sub_floor),
        key=lambda lbl: depth[lbl],
        reverse=True,
    )
    # Collapse near-duplicate avenues that are really one theme: drop a shallower avenue
    # ≥80% covered by a deeper one already kept (e.g. Spellslinger / Magecraft).
    viable: list[str] = []
    for lbl in candidates:
        s = set(members[lbl])
        if any(len(s & set(members[k])) / len(s) >= 0.8 for k in viable):
            continue
        viable.append(lbl)
    mains = [lbl for lbl in viable if depth[lbl] >= main_floor]
    subs = [lbl for lbl in viable if depth[lbl] < main_floor]

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
    # deck). Built from ``deck_signals`` (label -> subject, via ``spec_for`` — the
    # same per-subject dynamic label the avenue itself carries); viable avenues are
    # untouched (already past a much higher floor) and non-tribal labels never
    # appear in this map, so the gate is a no-op for them.
    tribal_subject_of_label: dict[str, str] = {}
    if tribal_payoff_subjects is not None:
        for sig in deck_signals:
            if sig.key != signal_keys.TYPE_MATTERS or not sig.subject:
                continue
            spec = spec_for(sig)
            if spec is not None:
                tribal_subject_of_label[spec.label] = sig.subject

    emerging_floor = max(1, _scaled(5, deck_size))
    emerging: list[str] = []
    for lbl in sorted(depth, key=lambda x: depth[x], reverse=True):
        if not emerging_floor <= depth[lbl] < sub_floor:
            continue
        s = set(members[lbl])
        if any(len(s & set(members[k])) / len(s) >= 0.8 for k in viable + emerging):
            continue
        subj = tribal_subject_of_label.get(lbl)
        if (
            subj is not None
            and tribal_payoff_subjects is not None
            and subj not in tribal_payoff_subjects
        ):
            continue
        emerging.append(lbl)

    top2 = viable[:2]
    in_top2 = sum(1 for c in engine if set(top2).intersection(themes(c)))
    top2_share = round(in_top2 / engine_pool, 2) if engine_pool else 0.0

    filler_cards = [c.name for c in nonland if c.bucket == "filler"]
    filler = len(filler_cards)
    filler_rate = round(filler / max(1, len(nonland)), 2)

    # Low-value: an Engine card that feeds a theme but is barely played (fringe
    # edhrec_rank) — the vanilla beater that "counts" as creature support in a go-wide
    # deck. Dead weight the bucket test alone misses, surfaced as an upgrade target (the
    # one EDHREC-popularity lean, by user direction).
    # A Granter is condemned by granted-ability QUALITY alone (ADR-0040 §2:
    # weak grade — Enduring Sliver's outlast), never by playrate; a
    # non-Granter keeps the play-rate read (§4, medium-aware).
    low_value_cards = [
        c.name
        for c in nonland
        if c.bucket == "engine"
        and (
            c.grant_grade == "weak"
            if c.grant_grade is not None
            else is_fringe(c.edhrec_rank, medium=medium)
        )
    ]

    engine_labels = {lbl for c in engine for lbl in themes(c)}
    stranded = sorted(lbl for lbl in engine_labels if 1 <= depth.get(lbl, 0) <= 2)

    spine_led_floor = max(1, _scaled(8, deck_size))
    if engine_pool < spine_led_floor:
        verdict = "SPINE-LED"
    elif len(viable) >= 3:
        # More than a main + a sub — too many directions competing for the engine slots.
        verdict = "SPREAD-THIN"
    elif viable:
        verdict = "FOCUSED"  # 1 main, or 1 main + 1 sub — the research ideal
    else:
        # A substantial engine pool that coheres into no theme at all is scattered.
        verdict = "SPREAD-THIN"

    return {
        "verdict": verdict,
        "engine_pool": engine_pool,
        "viable_avenues": [
            {
                "label": lbl,
                "depth": depth[lbl],
                "cards": members[lbl],
                "tier": "main" if depth[lbl] >= main_floor else "sub",
            }
            for lbl in viable
        ],
        "mains": mains,
        "subs": subs,
        "emerging": [
            {"label": lbl, "depth": depth[lbl], "cards": members[lbl]}
            for lbl in emerging
        ],
        "main_floor": main_floor,
        "sub_floor": sub_floor,
        "top2_concentration": top2_share,
        "filler": filler,
        "filler_rate": filler_rate,
        "filler_cards": filler_cards,
        "low_value": len(low_value_cards),
        "low_value_cards": low_value_cards,
        "stranded_avenues": stranded,
        "_depth": depth,
    }


# ── Template deviation (over the shared slot_budgets) ───────────────────────────


def template_deviation(budgets: dict) -> dict:
    short = {r: b for r, b in budgets.items() if b["deviation"] < 0}
    over = {r: b for r, b in budgets.items() if b["deviation"] > 0}
    return {
        "verdict": "on-template" if not short and not over else "off-template",
        "short": short,
        "over": over,
        "budgets": budgets,
    }


# ── Tier-2 advisory flags ──────────────────────────────────────────────────────


def _ir_wincon(ir: Card) -> bool:
    """Structural alt-win read. A ``cat=win_game`` (you win: Felidar, Thassa's Oracle),
    or a ``cat=lose_game`` with scope != "you" that forces another player to lose (Door
    to Nothingness). A ``cat=lose_game`` scope "you" is a self-loss DRAWBACK (Pact of
    Negation), never a closer (CR 104.3e): the IR makes the self-vs-opponent split the
    regex approximates with a subject guard.

    A scaling group-drain stays on the regex: ``lose_life`` projects scope="any" for
    every drain (Exsanguinate AND Blood Artist), so a structural read can't separate an
    opponent finisher from a 1-life drip; only ``amount.op`` carries the scaling."""
    return any(
        e.category == "win_game" or (e.category == "lose_game" and e.scope != "you")
        for ab in ir.all_abilities()
        for e in ab.effects
    )


def _is_wincon_card(card: dict, *, game: Game = _CALIBRATION_GAME) -> bool:
    """Heuristic finisher read, relative to ``game``: its starting life sets the
    evasive-body and fixed-reach thresholds, and one opponent admits single-target
    reach (the same finisher "each opponent" is at a pod)."""
    ir = ir_for(card)
    if ir is not None and _ir_wincon(ir):
        return True
    text = card.get("oracle_text") or ""
    if any(p.search(text) for p in _WINCON_PATTERNS):
        return True
    if _reach_closes(text, game=game):
        return True
    power_floor = _life_scaled(
        _EVASIVE_CLOSER_POWER, game.life, floor=_EVASIVE_CLOSER_POWER_FLOOR
    )
    if is_creature(card) and card_pt_int(card) >= power_floor:
        low = text.lower()
        return any(e in low for e in _EVASION)
    return False


def win_conditions(
    classes: Sequence[CardClass],
    *,
    shape: str,
    combo_count: int,
    deck_size: int = 100,
    game: Game = _CALIBRATION_GAME,
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
    cards = sorted(
        {
            c.name
            for c in classes
            if _is_wincon_card(c.record, game=game) or c.grant_closer
        }
    )
    pieces = _voltron_pieces(classes)
    voltron = _is_voltron(pieces, deck_size)
    voltron_closer = voltron and game.commander_damage
    count = len(cards) + combo_count + (1 if voltron_closer else 0)
    lo, hi = _WINCON_TARGET.get(shape, (3, 6))
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
    classes: Sequence[CardClass], *, shape: str, deck_size: int, voltron: bool
) -> dict:
    """Protection wants vs the Shape (ADR-0024 advisory). ``voltron`` is the read
    ``win_conditions`` already made (``wins["voltron"]``) — the one voltron walk."""
    cards = [c.name for c in classes if protects(c.record)]
    wants = shape in ("combo", "control") or voltron
    target = _scaled(5, deck_size) if wants else 0
    return {
        "count": len(cards),
        "cards": cards,
        "target": target,
        "wants_protection": wants,
        "status": "low" if wants and len(cards) < target else "ok",
    }


# ── Commander fit ──────────────────────────────────────────────────────────────


def commander_fit(classes: Sequence[CardClass], focus_result: dict) -> dict:
    commanders = [c for c in classes if c.bucket == "commander"]
    viable = {a["label"] for a in focus_result["viable_avenues"]}
    served = {lbl for c in commanders for lbl in c.served}
    served_viable = sorted(served & viable)
    fit = round(len(served_viable) / len(viable), 2) if viable else 1.0
    # Only meaningful once the deck has ≥2 viable avenues; a single-avenue deck can't be
    # "built for a different commander" on this signal.
    misfit = len(viable) >= 2 and fit < 0.5
    return {
        "fit": fit,
        "serves_viable": served_viable,
        "viable_count": len(viable),
        "misfit": misfit,
    }


# ── Top issues (the severity-ranked ordering the swap engine acts on) ───────────


def top_issues(
    *,
    efficiency_r: dict,
    focus_r: dict,
    template_r: dict,
    wincons_r: dict,
    protection_r: dict,
    commander_r: dict,
) -> list[dict]:
    """Rank findings by severity. Each issue carries a ``kind`` the swap engine maps
    to a cut/add action; ``commander_misfit`` is advisory only (no swap fixes it)."""
    issues: list[dict] = []

    for role, b in template_r["short"].items():
        deficit = -b["deviation"]
        # ADR-0040 §1: a grant-covered role (the commander's own ability GRANTS
        # this role's resource to every recipient body — deck-forge CONTEXT.md
        # "Grant-covered role") keeps its literal shortfall message but downgrades
        # to advisory: swaps.py's _spec_for_issue reads ``grant_covered`` and sources
        # no add for it; ``advisory`` itself is a marker carried for consumers —
        # nothing in the engine reads it. Never suppressed — the deficit/message are
        # unchanged.
        covered = bool(b.get("grant_covered"))
        message = (
            f"{role.replace('_', ' ')} short by {deficit} "
            f"({b['current']}/{b['min']}-{b['max']})"
        )
        if covered:
            by = b.get("grant_covered_by", "")
            message += f" — covered by {by}'s ability grant"
        issues.append(
            {
                "kind": "role_short",
                "role": role,
                "severity": deficit,
                "advisory": covered,
                "grant_covered": covered,
                "message": message,
            }
        )
    for role, b in template_r["over"].items():
        issues.append(
            {
                "kind": "role_over",
                "role": role,
                "severity": b["deviation"],
                "message": f"{role.replace('_', ' ')} over by {b['deviation']} "
                f"({b['current']}/{b['min']}-{b['max']})",
            }
        )

    # Dead weight: cards that serve no avenue AND fill no template role. Swapping a
    # do-nothing card for an on-theme / role card is almost always the highest-value
    # move, so it ranks above template trims — but only when there's somewhere
    # productive to redeploy (a viable theme to deepen or a short Spine role to fill);
    # with no target it's advisory, not a swap (the swap engine has nothing better to
    # add). A couple of off-theme good-stuff cards is normal, so a small tolerance
    # keeps this from churning a healthy deck.
    # Dead weight = do-nothing fillers PLUS barely-played fringe theme cards (the
    # upgrade targets the bucket test alone misses, e.g. a vanilla beater in a go-wide
    # deck). Both are replaced with stronger on-theme/role cards.
    dead = focus_r.get("filler", 0) + focus_r.get("low_value", 0)
    # ADR-0040 §1 (Fix 4): a grant-covered short role isn't a real redeploy
    # target — the commander's own grant already covers it — so it must not
    # count toward has_target any more than it sources an actual add
    # (_dead_weight_spec below applies the same gate).
    has_target = bool(focus_r.get("viable_avenues")) or any(
        not b.get("grant_covered") for b in template_r["short"].values()
    )
    filler_tol = 2
    if dead > filler_tol and has_target:
        excess = dead - filler_tol
        issues.append(
            {
                "kind": "dead_weight",
                # Ranks above theme-refocus (spread_thin) and template trims: replacing
                # a do-nothing card with an on-theme/role card is higher-value and only
                # ever cuts filler, so it should consume the swap budget before any pass
                # that risks churning a functional card.
                "severity": 7 + min(excess, 3),
                "count": excess,
                "message": f"{dead} cards are dead weight (no avenue/role, or barely "
                "played) — replace with stronger on-theme cards",
            }
        )

    for e in focus_r.get("emerging", []):
        issues.append(
            {
                "kind": "under_supported_theme",
                "label": e["label"],
                "severity": 2,
                "message": f"{e['label']} ({e['depth']}) is an under-supported theme — "
                "commit more or cut it",
            }
        )

    if focus_r["verdict"] == "SPREAD-THIN":
        issues.append(
            {
                "kind": "spread_thin",
                "severity": 4 + len(focus_r["stranded_avenues"]),
                "message": f"spread thin — {len(focus_r['viable_avenues'])} viable "
                f"avenues, {focus_r['filler']} filler",
            }
        )

    if wincons_r["status"] == "low":
        issues.append(
            {
                "kind": "wincon_short",
                "severity": 3 + (wincons_r["target"][0] - wincons_r["count"]),
                "message": f"≈{wincons_r['count']} closers — "
                f"usually wants {wincons_r['target'][0]}-{wincons_r['target'][1]}",
            }
        )
    if wincons_r.get("voltron_needs_real_damage"):
        # Advisory only (no swap fixes a plan): the equip/aura density reads as
        # voltron, but this game has no 21-commander-damage rule (CR 903.10a is
        # Commander's extra loss rule; Brawl games don't use it, CR 903.12h), so the
        # plan closes only by dealing the whole starting life. ``advisory`` is a
        # marker carried for consumers (nothing in the engine reads it); swaps skips
        # this kind because _spec_for_issue has no branch for it. Severity ranks how
        # much the builder should change course — 2 here (read your closers
        # differently) vs 5 for commander_misfit (you may have the wrong commander).
        issues.append(
            {
                "kind": "voltron_no_commander_damage",
                "severity": 2,
                "advisory": True,
                "message": f"voltron plan, but no commander-damage rule in this game — "
                f"it must deal the full {wincons_r.get('life')} life; count real "
                "evasion and reach as the closers",
            }
        )

    if protection_r["status"] == "low":
        issues.append(
            {
                "kind": "protection_short",
                "severity": 2 + (protection_r["target"] - protection_r["count"]),
                "message": f"{protection_r['count']} protection — "
                f"this Shape usually wants ~{protection_r['target']}",
            }
        )

    if efficiency_r["verdict"] != "ok":
        issues.append(
            {
                "kind": "efficiency",
                "subkind": efficiency_r["verdict"],
                "severity": 3,
                "message": f"curve: {efficiency_r['verdict']}",
            }
        )

    if commander_r["misfit"]:
        # Advisory marker (no swap fixes a commander; swaps skips the kind because
        # _spec_for_issue has no branch for it); severity 5 because it questions the
        # whole build, where the voltron advisory above (2) only re-reads the closers.
        issues.append(
            {
                "kind": "commander_misfit",
                "severity": 5,
                "advisory": True,
                "message": "commander serves "
                f"{len(commander_r['serves_viable'])}/{commander_r['viable_count']} "
                "viable avenues — the deck may be built for a different commander",
            }
        )

    issues.sort(key=lambda i: i["severity"], reverse=True)
    return issues
