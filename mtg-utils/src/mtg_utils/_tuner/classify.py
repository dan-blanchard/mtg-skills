"""Per-card Spine / Engine / Filler classification (the tuner's shared substrate).

The tri-partition (deck-forge CONTEXT.md): every nonland, non-commander card is
**Spine** (mandatory scaffolding — ramp / draw / interaction / wipes), **Engine**
(serves an avenue), or **Filler** (serves no avenue here). Lands and commanders are
their own buckets. No new matchers: Spine roles come from ``budgets.role_of`` and
avenue-serving from ``ranking.score_candidate``/``serves`` — both bottoming out in
``theme_presets`` (ADR-0023).
"""

from __future__ import annotations

from dataclasses import dataclass

from mtg_utils._deck_forge.budgets import protects, role_of
from mtg_utils._deck_forge.ranking import score_candidate
from mtg_utils.card_classify import is_land
from mtg_utils.hydrated_deck import HydratedDeck

# The hard-counted Spine roles; ``lands`` is its own bucket (the curve gate's domain).
_SPINE_ROLES = frozenset({"ramp", "card_draw", "interaction", "board_wipe"})

# Card-quality signal (the ONE place the tuner leans on EDHREC popularity, by explicit
# user direction — ADR-0009 still bars it from the Find ranker). Scryfall's edhrec_rank
# is a global play-rate rank (lower = more played); absent ≈ unplayed. A card
# ranked worse than this floor in a themed deck is "fringe": it nominally feeds a broad
# avenue but almost nobody runs it, so it's an upgrade target. Calibrated against the
# benchmark — vanilla beaters sit >23k/None while real theme cards are <8k.
FRINGE_RANK = 15000


def is_fringe(rank: int | None, *, medium: str = "paper") -> bool:
    """True when a card is barely-played (an upgrade candidate within its theme).

    EDHREC is a paper-EDH population (ADR-0040 §4): a null rank on a digital
    deck is a population artifact (Arena-only cards can never appear there) —
    no data, never condemning. On paper, absence genuinely means unplayed."""
    if rank is None:
        return medium != "digital"
    return rank > FRINGE_RANK


@dataclass(frozen=True)
class CardClass:
    """One deck card's classification, used by every downstream metric."""

    name: str
    bucket: str  # "commander" | "land" | "spine" | "engine" | "filler"
    roles: tuple[str, ...]  # template roles filled (sorted)
    served: tuple[str, ...]  # avenue labels this card serves (deduped)
    dual_purpose: bool  # Spine AND serves an avenue (a "win-win" card)
    cmc: float
    record: dict
    edhrec_rank: int | None = None  # play-rate rank; lower=more played, None=unplayed
    # ADR-0040 §2 (task #97): the card's Granter grade ("premium"/"solid"/
    # "weak" via the ability-quality table; None = not a Granter). The
    # low-value reads condemn a Granter by GRADE, never by playrate.
    grant_grade: str | None = None
    # ADR-0040 §5 (task #100): grants a closer-grade ability (team double
    # strike) — ONE closer regardless of recipient count.
    grant_closer: bool = False


# The repeatable-draw commander keys that arm the hellbent anti-synergy
# predicate (ADR-0040 §2: a "no cards in hand"-gated grant under a
# draw-engine commander never turns on — Sliver Weftwinder draws per ETB).
_DRAW_ENGINE_KEYS = frozenset({"card_draw_engine", "draw_for_each"})


def _commander_draws(hd: HydratedDeck, commander_names: set[str]) -> bool:
    from mtg_utils.theme_presets import _signal_keys_for

    return any(
        _signal_keys_for(rec) & _DRAW_ENGINE_KEYS
        for rec in hd.records
        if rec.get("name") in commander_names
    )


def classify_deck(
    hd: HydratedDeck, deck_signals: list, commander_names: set[str]
) -> list[CardClass]:
    """Classify every distinct deck card (all zones, one record per name).

    ``served`` is the set of avenue labels the card feeds — the same
    ``score_candidate`` machinery the Find ranker uses, so a card's tuner
    classification can never drift from how the rest of deck-forge scores it.
    """
    from mtg_utils._deck_forge.signals import grant_payloads_for
    from mtg_utils._tuner.ability_quality import grant_grade, has_closer_grant

    draw_engine = _commander_draws(hd, commander_names)
    out: list[CardClass] = []
    for rec in hd.records:
        name = rec.get("name", "")
        roles = role_of(rec)
        served = tuple(score_candidate(rec, active_signals=deck_signals)["served"])
        if name in commander_names:
            bucket = "commander"
        elif is_land(rec):
            bucket = "land"
        elif roles & _SPINE_ROLES:
            bucket = "spine"
        elif protects(rec):
            # Protection is conditional Spine (Tier-2), never filler — and this MUST be
            # checked before `served`: a protection card that also serves an avenue
            # (Heroic Intervention serves "Grant protection") would otherwise bucket
            # engine and be cut by the stranded pass while the deck reads short on it.
            bucket = "spine"
        elif served:
            bucket = "engine"
        else:
            bucket = "filler"
        grade: str | None = None
        closer = False
        if bucket not in ("commander", "land"):
            payloads = grant_payloads_for(rec)
            grade = grant_grade(payloads, draw_engine_commander=draw_engine)
            closer = has_closer_grant(payloads)
        out.append(
            CardClass(
                name=name,
                bucket=bucket,
                roles=tuple(sorted(roles)),
                served=served,
                dual_purpose=(bucket == "spine" and bool(served)),
                cmc=float(rec.get("cmc", 0.0) or 0.0),
                record=rec,
                edhrec_rank=rec.get("edhrec_rank"),
                grant_grade=grade,
                grant_closer=closer,
            )
        )
    return out
