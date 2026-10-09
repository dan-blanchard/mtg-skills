"""CLI: rank candidate cards by synergy with a deck (D).

A thin wrapper over ``_analysis.ranking.rank_candidates``: it extracts the deck's
signals (commander lanes) and scores each candidate by how many of those lanes it serves
(synergy), then price, then curve — the transparent multi-axis score, NOT EDHREC
popularity. Lets deck-wizard order additions deterministically, not by agent guess.

    deck-rank <deck.json> <candidates.json> [--limit N] [--json]
        [--medium paper|digital] [--meta auto|off|<archetype>]

``candidates.json`` is a list of Scryfall records — e.g. the output of
``card-search --json`` (which already projects oracle_text / type_line / keywords).

On a digital build with a tunable meta archetype in the arena-meta cache (ADR-0059,
the gate ``deck-tune --meta`` reads through), the archetype's card share breaks
synergy ties, before price.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils._analysis.pair_reads import build_pair_context
from mtg_utils._analysis.ranking import rank_candidates
from mtg_utils._analysis.signals import ranked_signals_and_payoffs
from mtg_utils._tuner import metrics
from mtg_utils._tuner.classify import classify_deck
from mtg_utils.card_classify import type_line_has
from mtg_utils.deck import split_type_line
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option
from mtg_utils.formats import resolve_deck_medium
from mtg_utils.hydrated_deck import HydratedDeck

_ZONES = ("commanders", "cards", "sideboard")


def _ensure_ir() -> None:
    """Best-effort Card IR sidecar build so a fresh deck-wizard run is IR-native
    (ADR-0027 A4). Called BEFORE the first ``ir_for`` (in ``rank_deck_signals`` /
    ``rank_candidates``) so the memoized index isn't poisoned with ``None``.
    Non-fatal — a build failure degrades to the regex path."""
    import sys

    from mtg_utils._deck_forge.production import ensure_card_ir

    try:
        ensure_card_ir()
    except (OSError, ValueError) as exc:  # corrupt/locked phase data → degrade
        print(
            f"deck-rank: Card IR unavailable ({exc}); using regex path.",
            file=sys.stderr,
        )


def _focus_sets(
    hd: HydratedDeck,
    signals: list,
    commander_names: set,
    payoff_subjects: frozenset[str],
) -> dict:
    """The deck's avenue prominence (viable/emerging/stranded), so the ranker scores
    DEPTH in the deck's real themes — the same deck-relative weighting the tuner uses
    (couples to ``_tuner`` for the focus metric; deck-rank is the deck-wizard CLI that
    feeds Step 6, so it wants the tuner's notion of theme prominence).
    ``payoff_subjects`` (the task-#101 emerging-tribal gate) comes from the caller's
    single ``ranked_signals_and_payoffs`` pass — never re-extracted here."""
    classes = classify_deck(hd, signals, commander_names, deck_mana=hd.deck_mana)
    deck_size = hd.format.deck_size
    foc = metrics.focus(
        classes,
        deck_size=deck_size,
        deck_signals=signals,
        tribal_payoff_subjects=payoff_subjects,
    )
    return {
        "viable": {a["label"] for a in foc["viable_avenues"]},
        "emerging": {a["label"] for a in foc.get("emerging", [])},
        "stranded": set(foc.get("stranded_avenues") or []),
    }


def _deck_tribes(hd: HydratedDeck) -> frozenset[str]:
    """The creature subtypes the deck fields, so a payoff gated on a tribe the deck
    lacks is discounted (deck-relative)."""
    return frozenset(
        st.lower()
        for rec in hd.deck_records()
        if type_line_has((rec.get("type_line") or "").lower(), "creature")
        for st in split_type_line(rec.get("type_line", ""))[1]
    )


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@click.argument("candidates_json", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
@click.option("--limit", default=25, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
@click.option(
    "--medium",
    "medium",
    type=click.Choice(["paper", "digital"]),
    default=None,
    help="Deck medium; default: the deck JSON's medium, else the format's. Only a "
    "digital build reads the Arena meta (--meta).",
)
@click.option(
    "--meta",
    "meta",
    default="auto",
    show_default=True,
    help="A digital build's Arena meta archetype (ADR-0059), read from the "
    "arena-meta cache, whose card share breaks synergy ties: 'auto' matches the "
    "deck, 'off' skips it, anything else names the archetype.",
)
def main(
    deck_json: Path,
    candidates_json: Path,
    bulk_data: Path | None,
    *,
    limit: int,
    as_json: bool,
    medium: str | None,
    meta: str,
) -> None:
    """Rank CANDIDATES_JSON by synergy with DECK_JSON."""
    _ensure_ir()  # build the sidecar on first run, BEFORE the first ir_for
    hd = acquire_for_cli(deck_json, bulk_data)
    meta_ctx = None
    if meta != "off":
        from mtg_utils._arena_meta.untapped import cached_deck_context

        meta_ctx, note = cached_deck_context(
            hd,
            resolve_deck_medium(hd.format, hd.deck, medium),
            archetype=None if meta == "auto" else meta,
        )
        if note:
            click.echo(note, err=True)
    commander_names = {c["name"] for c in hd.commanders}
    signals, payoff_subjects = ranked_signals_and_payoffs(
        hd.deck_records(), commander_names
    )
    candidates = json.loads(Path(candidates_json).read_text(encoding="utf-8"))
    if not isinstance(candidates, list) or not all(
        isinstance(c, dict) for c in candidates
    ):
        raise click.ClickException(
            "candidates must be a JSON list of card records (e.g. card-search --json)."
        )
    in_deck = {e["name"] for z in _ZONES for e in (hd.deck.get(z) or [])}
    pool = [c for c in candidates if c.get("name") not in in_deck]
    ranked = rank_candidates(
        pool,
        active_signals=signals,
        focus_sets=_focus_sets(hd, signals, commander_names, payoff_subjects),
        deck_tribes=_deck_tribes(hd),
        # Pair reads (ADR-0042): commander idents + deck ident density.
        # Rate stays NEUTRAL by default (no index built): the v1 formula
        # classes measured slightly NEGATIVE on aggregate study recall
        # (every variant <= baseline, 2026-07-16 four-way eval), so the
        # multiplier is opt-in via rank_candidates(rate_index=...) until a
        # formula v2 validates — see ADR-0042's measured-outcome note.
        pair_ctx=build_pair_context(
            [hd.by_name.get(n) or {} for n in commander_names],
            list(hd.deck_records()),
        ),
        deck_mana=hd.deck_mana,
        meta_share=meta_ctx.share if meta_ctx is not None else None,
    )[: max(1, limit)]
    if as_json:
        out = [
            {
                "name": r["card"].get("name", ""),
                "synergy_fit": r["score"]["synergy_fit"],
                "served": r["score"]["served"],
                "price": r["score"]["price"],
                "cmc": r["score"]["cmc"],
                **(
                    {"meta_share": r["score"]["meta_share"]}
                    if "meta_share" in r["score"]
                    else {}
                ),
            }
            for r in ranked
        ]
        click.echo(json.dumps(out, indent=2))
        return
    for r in ranked:
        score, card = r["score"], r["card"]
        price = f"${score['price']:.2f}" if score["price"] is not None else "—"
        served = ", ".join(score["served"][:4]) or "—"
        name = card.get("name", "")
        share = f"  meta {score['meta_share']:.0%}" if "meta_share" in score else ""
        click.echo(
            f"{score['synergy_fit']:>2}✦  {name:30.30}  {price:>7}  {served}{share}"
        )
