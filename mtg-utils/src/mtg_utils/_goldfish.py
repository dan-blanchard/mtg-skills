"""The goldfish model: a pure-Python solo deck simulator.

One seeded run draws London-mulligan opening hands, plays a land a turn, greedy-casts
in ascending mana value, and records lands in play, casts and color screw per turn
(:func:`_simulate_game`); :func:`_run_goldfish` aggregates N games. The mana model
counts lands plus every cast nonland permanent with a non-empty ``produced_mana``, and
resolves land-search effects through ``card_classify.land_fetch_profile``.

:func:`goldfish_envelope` is the one result-builder: ``playtest-goldfish`` and
deck-forge's goldfish handoff both call it, so the panel and the command report the
same results, coverage and warnings (ADR-0069).
"""

from __future__ import annotations

import random
import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from mtg_utils._playtest_common import envelope
from mtg_utils.card_classify import (
    color_sources,
    count_color_pips,
    is_land,
    land_fetch_profile,
)

if TYPE_CHECKING:
    from mtg_utils.hydrated_deck import HydratedDeck

GOLDFISH_VERSION = "goldfish v1"

# Colors a source can pay a pip with. Defined here (above its first use) so the
# fetch fallback and the produced_mana filter cannot drift apart.
_MANA_COLORS = frozenset("WUBRG")


def _build_indexed_deck(hydrated: list[dict]) -> list[int]:
    """Return a list of integer indices (0..N-1), one per card slot."""
    return list(range(len(hydrated)))


def _card_pips(card: dict) -> dict[str, int]:
    """Count colored pips per color for a card.

    Transform / modal-DFC layouts carry no top-level ``mana_cost`` (Scryfall puts
    it on ``card_faces`` while top-level ``cmc`` reflects the front face), so fall
    back to the front face's cost — otherwise those cards register zero pips and
    color-screw under-reports for MDFC-heavy pools.
    """
    mana = card.get("mana_cost") or ""
    if not mana and card.get("card_faces"):
        mana = card["card_faces"][0].get("mana_cost") or ""
    return count_color_pips(mana)


def _deck_basic_colors(hydrated: list[dict]) -> frozenset[str]:
    """Colors of the basic lands actually in this deck.

    A generic "search for a basic land" can only find what the deck contains, so
    this bounds what such a fetch may produce. Deck-scoped, hence here rather than
    in card_classify — ``color_sources`` answers the card-only question and
    collapses a generic search to ``{"any"}``.
    """
    colors: set[str] = set()
    for card in hydrated:
        type_line = (card.get("type_line") or "").lower()
        if "basic" not in type_line or "land" not in type_line:
            continue
        colors.update(c for c in color_sources(card) if c in _MANA_COLORS)
    return frozenset(colors)


def _unresolved_fetch_warnings(hydrated: list[dict]) -> list[str]:
    """Warn when the deck's fixing is invisible to the mana model.

    A generic "search for a basic land" resolves against the deck's OWN basics, so
    a deck with none (an all-nonbasic manabase running Fabled Passage / Prismatic
    Vista) silently falls back to producing nothing — restoring the inverted
    "more fixing → more reported screw" ranking with no signal. Say so out loud
    rather than reporting a confident wrong number.
    """
    if _deck_basic_colors(hydrated):
        return []
    blind = sorted(
        {
            card.get("name", "?")
            for card in hydrated
            if not [c for c in (card.get("produced_mana") or []) if c in _MANA_COLORS]
            and (fetch := land_fetch_profile(card, deck_basic_colors=frozenset()))
            is not None
            and not fetch.colors
        }
    )
    if not blind:
        return []
    return [
        (
            "color-screw may be overstated: the deck runs no basic lands, so "
            f"generic land-fetch effects resolve to no colors ({', '.join(blind)})"
        )
    ]


def _land_produces(card: dict, deck_basic_colors: frozenset[str]) -> list[str]:
    """Color identity a land can tap for, this turn, on its own.

    Prefers ``produced_mana``; falls back to a self-sacrificing fetch, which
    ``produced_mana`` never reports. A fetch that only puts the land into *hand*
    yields nothing now, so it is excluded — matching the nonland path.

    ``deck_basic_colors`` is required, not defaulted: it carries the whole
    correctness of the fetch fallback, and a caller that omitted it would silently
    restore the inverted color-screw ranking this exists to fix.
    """
    direct = [c for c in (card.get("produced_mana") or []) if c in _MANA_COLORS]
    if direct:
        return direct
    fetch = land_fetch_profile(card, deck_basic_colors=deck_basic_colors)
    if fetch is None or not fetch.to_battlefield:
        return []
    return sorted(fetch.colors)


_ADD_PATTERN = re.compile(r"\bAdd\b((?:\s*\{[^}]+\})+)")


def _mana_ability_profile(card: dict) -> tuple[int, frozenset[str]] | None:
    """Rough mana profile for a nonland permanent: ``(amount, color_options)``.

    Keyed off Scryfall's ``produced_mana``, so it intentionally captures both
    true tap-for-mana rocks/dorks (Sol Ring, Birds, Signet) AND mana-token
    makers (Treasure/Gold/Eldrazi-Spawn generators like Pitiless Plunderer or
    Awakening Zone — Scryfall populates their ``produced_mana`` from the token's
    ability). Token makers are approximated as a steady ~1-mana/turn source
    rather than simulating their creation triggers and one-shot sacrifice — a
    deliberate rough proxy that avoids modeling deaths/attacks/upkeep/sacrifice.

    ``color_options`` = colors it can make (empty = colorless / generic only).
    ``amount`` = mana per turn. Returns ``None`` if ``produced_mana`` is empty.
    Lands are handled separately via :func:`_land_produces`.
    """
    produced = card.get("produced_mana") or []
    if not produced:
        return None
    colors = frozenset(c for c in produced if c in _MANA_COLORS)
    # Amount = mana symbols in an explicit "Add {..}" oracle clause; default 1.
    # So a five-color produced_mana (e.g. [W,U,B,R,G]) is ONE mana/turn of any
    # color, NOT five — only literal symbols like Sol Ring's "{C}{C}" exceed 1.
    amount = 1
    for clause in _ADD_PATTERN.finditer(card.get("oracle_text") or ""):
        amount = max(amount, clause.group(1).count("{"))
    return amount, colors


def _is_permanent(card: dict) -> bool:
    """Does this card stay on the battlefield (so a mana ability is repeatable)?"""
    type_line = (card.get("type_line") or "").lower()
    return any(
        kind in type_line
        for kind in ("artifact", "creature", "enchantment", "planeswalker", "battle")
    )


def _match_pips(pips: dict[str, int], sources: list[set[str]]) -> dict[int, int] | None:
    """Match each colored pip to a distinct mana source that can produce it.

    Bipartite matching (Kuhn's algorithm) between pip-slots and mana sources;
    each source's set lists the colors it can tap for (empty = generic only). A
    multicolor source can fill a pip of any color it makes, but only one pip.
    Returns ``{slot_index: source_index}`` for a full matching, else ``None``.
    """
    slots = [color for color, count in pips.items() for _ in range(count)]
    if len(slots) > len(sources):
        return None
    source_to_slot: dict[int, int] = {}

    def _augment(slot_idx: int, visited: set[int]) -> bool:
        for si, options in enumerate(sources):
            if slots[slot_idx] in options and si not in visited:
                visited.add(si)
                if si not in source_to_slot or _augment(source_to_slot[si], visited):
                    source_to_slot[si] = slot_idx
                    return True
        return False

    for slot_idx in range(len(slots)):
        if not _augment(slot_idx, set()):
            return None
    return {slot: src for src, slot in source_to_slot.items()}


def _pips_coverable(pips: dict[str, int], sources: list[set[str]]) -> bool:
    """Can the colored pips be produced by the given mana sources?"""
    return _match_pips(pips, sources) is not None


def _pay(card: dict, sources: list[set[str]]) -> bool:
    """If the card is castable from ``sources``, spend the mana and return True.

    Mutates ``sources`` in place, removing the spent ones. Each source is one
    mana whose set lists the colors it can tap for (empty = generic only).
    """
    cmc = int(card.get("cmc") or 0)  # Scryfall stores cmc as a float (4.0)
    if len(sources) < cmc:
        return False
    pips = _card_pips(card)
    match = _match_pips(pips, sources)
    if match is None:
        return False
    used = set(match.values())  # sources spent on colored pips
    generic_needed = cmc - sum(pips.values())
    spare = [si for si in range(len(sources)) if si not in used]
    if len(spare) < generic_needed:
        return False
    used.update(spare[:generic_needed])
    for si in sorted(used, reverse=True):
        sources.pop(si)
    return True


def _is_color_screwed(card: dict, sources: list[set[str]]) -> bool:
    """True color screw: enough total mana for the card but not the right colors.

    Returns ``False`` when the card simply costs more than the available mana —
    that's a curve / mana-count issue, not color screw.
    """
    cmc = int(card.get("cmc") or 0)  # Scryfall stores cmc as a float (4.0)
    if len(sources) < cmc:
        return False
    return not _pips_coverable(_card_pips(card), sources)


def _keep_hand(hand: list[dict]) -> bool:
    """London mulligan keep heuristic.

    Keep iff: 2 <= lands <= 5 AND hand has at least one nonland with cmc <= 3.
    Returns ``True`` to keep, ``False`` to mulligan.
    """
    lands = sum(1 for c in hand if is_land(c))
    if lands < 2 or lands > 5:
        return False
    return any(not is_land(c) and c.get("cmc", 0) <= 3 for c in hand)


def _simulate_game(
    hydrated: list[dict],
    *,
    max_turns: int,
    rng: random.Random,
    starting_hand: list[int] | None = None,
    deck_basic_colors: frozenset[str] | None = None,
) -> dict:
    """Simulate one game: returns per-turn lands/casts/mana metrics + flags.

    If ``starting_hand`` is provided, those indices are the opening hand and
    the remaining deck order is determined by ``rng``. Otherwise a fresh
    7-card hand is drawn from the top of an ``rng``-shuffled library
    (used by tests that don't go through the mulligan path).

    Mana model: counts lands + every cast nonland permanent with a non-empty
    Scryfall ``produced_mana`` (rocks tap the turn they enter, dorks the turn
    after). Because it keys off ``produced_mana``, it also counts mana-token
    makers (Treasure/Gold/Eldrazi-Spawn generators), approximating them as a
    rough ~1-mana/turn source rather than simulating their creation triggers
    (deaths/attacks/upkeep) and one-shot sacrifice — see _mana_ability_profile.
    Token ramp is thus captured roughly, not precisely.

    Land search is modeled separately, since ``produced_mana`` is empty for every
    such effect: a fetch land produces the deck's own basic colors (see
    ``_land_produces``) and an enters-triggered fetcher moves a land from library
    to battlefield (see ``_resolve_land_fetch``), both delayed a turn by an
    "enters tapped" clause. Activation-gated fetches are not credited.

    Play/draw: the goldfish is always modeled on the draw — it draws a card on
    every turn including turn 1. (Changing that would shift curve/screw output and
    is a deliberate decision, not made here.)
    """
    indices = _build_indexed_deck(hydrated)
    rng.shuffle(indices)
    if starting_hand is None:
        library = list(indices)
        hand: list[int] = [library.pop() for _ in range(7)]
    else:
        kept = set(starting_hand)
        library = [i for i in indices if i not in kept]
        hand = list(starting_hand)

    # A deck constant. _run_goldfish hoists it so 1000 games don't each rescan
    # the decklist; the fallback keeps direct callers (tests) ergonomic.
    # Bind a non-optional local: the closures below capture this, and a
    # captured name keeps its declared `| None` type inside the closure body
    # no matter what the enclosing scope narrowed it to.
    basic_colors: frozenset[str] = (
        _deck_basic_colors(hydrated) if deck_basic_colors is None else deck_basic_colors
    )

    lands_in_play: list[int] = []  # indices of lands in play
    lands_in_play_by_turn: dict[int, int] = {}
    casts_by_turn: dict[int, int] = defaultdict(int)
    # Mana rocks/dorks on the battlefield; each remembers the turn it was cast
    # so dorks (creatures) respect summoning sickness.
    mana_permanents: list[dict] = []
    # First turn each land can actually tap for mana. A land that sacrifices
    # itself for a *tapped* basic, or one fetched onto the battlefield tapped, is
    # only a source from the following turn.
    land_ready_turn: dict[int, int] = {}
    color_screwed = False

    def _land_ready_on_entry(index: int, turn: int) -> int:
        """The turn a land played/fetched on ``turn`` first produces mana."""
        card = hydrated[index]
        if [c for c in (card.get("produced_mana") or []) if c in _MANA_COLORS]:
            return turn
        fetch = land_fetch_profile(card, deck_basic_colors=basic_colors)
        return turn + 1 if fetch and fetch.enters_tapped else turn

    def _resolve_land_fetch(card: dict, turn: int, sources: list[set[str]]) -> None:
        """Move a searched-up land from library to battlefield, if the card does that.

        Only ETB fetches (Wood Elves, Sakura-Tribe Elder) are credited. A fetch
        behind an activation cost — Knight of the Reliquary's ``{T}, Sacrifice a
        Forest``, Burnished Hart's ``{3}, {T}, Sacrifice`` — is skipped because the
        cost is real and unmodeled, so crediting free mana is the worse error.

        Note the cost is the whole reason, NOT summoning sickness: CR 302.6 scopes
        that rule to *creatures*, so Burnished Hart (an artifact) could legally tap
        the turn it enters. Only the creature cases are also summoning-sick.

        The land is *moved*, not conjured: it leaves ``library`` and joins
        ``lands_in_play``, so mean-lands-by-turn agrees with the mana actually
        spent and the deck cannot both fetch and later draw the same land.
        """
        fetch = land_fetch_profile(card, deck_basic_colors=basic_colors)
        if fetch is None or not fetch.to_battlefield or not fetch.on_etb:
            return
        ready = turn + 1 if fetch.enters_tapped else turn
        for _ in range(fetch.count):  # Explosive Vegetation / Krosan Verge find two
            target = next(
                (
                    li
                    for li in library
                    if is_land(hydrated[li])
                    and set(_land_produces(hydrated[li], basic_colors)) & fetch.colors
                ),
                None,
            )
            if target is None:  # no matching land left to find
                return
            library.remove(target)
            lands_in_play.append(target)
            land_ready_turn[target] = ready
            if ready <= turn:
                sources.append(set(_land_produces(hydrated[target], basic_colors)))

    def _sources_available(current_turn: int) -> list[set[str]]:
        """One entry per mana point available this turn (lands + rocks + dorks)."""
        sources = [
            set(_land_produces(hydrated[li], basic_colors))
            for li in lands_in_play
            if land_ready_turn.get(li, 0) <= current_turn
        ]
        for perm in mana_permanents:
            # Rocks (non-creature) tap the turn they enter; dorks (creatures)
            # are summoning-sick and tap from the following turn.
            if not perm["is_creature"] or perm["cast_turn"] < current_turn:
                sources.extend(set(perm["colors"]) for _ in range(perm["amount"]))
        return sources

    for turn in range(1, max_turns + 1):
        if library:
            hand.append(library.pop())

        # Play one land if possible.
        land_in_hand = next((i for i in hand if is_land(hydrated[i])), None)
        if land_in_hand is not None:
            hand.remove(land_in_hand)
            lands_in_play.append(land_in_hand)
            land_ready_turn[land_in_hand] = _land_ready_on_entry(land_in_hand, turn)
        lands_in_play_by_turn[turn] = len(lands_in_play)

        # Greedy-cast in ascending CMC, re-evaluating after each cast since a
        # mana rock can produce mana the same turn it resolves.
        sources = _sources_available(turn)
        while True:
            nonland_hand = sorted(
                (i for i in hand if not is_land(hydrated[i])),
                key=lambda i: hydrated[i].get("cmc") or 0,
            )
            for ci in nonland_hand:
                if not _pay(hydrated[ci], sources):
                    continue
                hand.remove(ci)
                casts_by_turn[turn] += 1
                profile = _mana_ability_profile(hydrated[ci])
                if profile is not None and _is_permanent(hydrated[ci]):
                    amount, colors = profile
                    is_creature = (
                        "creature" in (hydrated[ci].get("type_line") or "").lower()
                    )
                    mana_permanents.append(
                        {
                            "cast_turn": turn,
                            "amount": amount,
                            "colors": colors,
                            "is_creature": is_creature,
                        }
                    )
                    if not is_creature:  # a rock taps immediately
                        sources.extend(set(colors) for _ in range(amount))
                else:
                    _resolve_land_fetch(hydrated[ci], turn, sources)
                break  # re-sort and re-evaluate with the updated mana
            else:
                break  # nothing castable remained this pass

        # Color-screw check: with >=2 lands, do we hold a nonland we have enough
        # TOTAL mana for (lands + tappable rocks/dorks) but can't produce the
        # COLORS of? That isolates true color screw from merely-too-expensive
        # cards, which are a curve / mana-count issue.
        if len(lands_in_play) >= 2 and not color_screwed:
            full_sources = _sources_available(turn)
            if any(
                not is_land(hydrated[i])
                and _is_color_screwed(hydrated[i], full_sources)
                for i in hand
            ):
                color_screwed = True

    return {
        "turns_played": max_turns,
        "lands_in_play_by_turn": lands_in_play_by_turn,
        "casts_by_turn": dict(casts_by_turn),
        "color_screwed": color_screwed,
    }


def _aggregate_goldfish(games: list[dict], *, mulligans: dict[str, int]) -> dict:
    """Aggregate per-game results into mean / rate metrics."""
    n = len(games)
    if n == 0:
        return {"games": 0}

    mean_lands: dict[str, float] = {}
    if games:
        max_turn = max(g["turns_played"] for g in games)
        for t in range(1, max_turn + 1):
            mean_lands[str(t)] = (
                sum(g["lands_in_play_by_turn"].get(t, 0) for g in games) / n
            )

    casts_by_turn_total: dict[str, float] = {}
    if games:
        all_turns: set[int] = set()
        for g in games:
            all_turns.update(g["casts_by_turn"].keys())
        for t in all_turns:
            casts_by_turn_total[str(t)] = (
                sum(g["casts_by_turn"].get(t, 0) for g in games) / n
            )

    color_screw = sum(1 for g in games if g["color_screwed"]) / n

    total_hands = sum(mulligans.values())
    mull_rate = {
        k: (v / total_hands if total_hands else 0.0) for k, v in mulligans.items()
    }

    return {
        "games": n,
        "mean_lands_by_turn": mean_lands,
        "mean_casts_by_turn": casts_by_turn_total,
        "color_screw_rate": color_screw,
        "mulligan_rate": mull_rate,
    }


def _run_goldfish(
    hydrated: list[dict], *, games: int, max_turns: int, base_seed: int
) -> dict:
    """Run N goldfish games and return aggregate metrics."""
    rng = random.Random(base_seed)
    results: list[dict] = []
    mulligans: dict[str, int] = {"7": 0, "6": 0, "5": 0, "4": 0}
    # Deck constant — computed once rather than rescanning the decklist per game.
    deck_basic_colors = _deck_basic_colors(hydrated)

    for _ in range(games):
        # London mulligan: try 7, 6, 5, 4. Stop on first keep.
        kept_at = 7
        kept_indices: list[int] = []
        for hand_size in (7, 6, 5, 4):
            sub_rng = random.Random(rng.random())
            indices = _build_indexed_deck(hydrated)
            sub_rng.shuffle(indices)
            hand_idx = indices[:hand_size]
            hand = [hydrated[i] for i in hand_idx]
            if _keep_hand(hand) or hand_size == 4:
                kept_at = hand_size
                kept_indices = hand_idx
                break
        mulligans[str(kept_at)] = mulligans.get(str(kept_at), 0) + 1

        game_rng = random.Random(rng.random())
        results.append(
            _simulate_game(
                hydrated,
                max_turns=max_turns,
                rng=game_rng,
                starting_hand=kept_indices,
                deck_basic_colors=deck_basic_colors,
            )
        )

    return _aggregate_goldfish(results, mulligans=mulligans)


def goldfish_envelope(hd: HydratedDeck, *, games: int, turns: int, seed: int) -> dict:
    """Goldfish a hydrated deck: the schema-v1 envelope ``playtest-goldfish`` writes.

    Runs :func:`_run_goldfish` over the commanders and main deck (the sideboard is
    never drawn) and wraps it: ``card_coverage`` counts the copies asked for, the
    records simulated and the main-deck names no record joined; ``warnings`` say how
    many names were dropped and whether the deck's fixing is invisible to the mana
    model (:func:`_unresolved_fetch_warnings`). Only the simulation is timed.
    """
    deck = hd.deck
    deck_hydrated = hd.expanded(zones=("commanders", "cards"))
    missing = sorted(
        n for n in hd.missing if any(e["name"] == n for e in hd.commanders + hd.cards)
    )

    start = time.perf_counter()
    results = _run_goldfish(
        deck_hydrated,
        games=games,
        max_turns=turns,
        base_seed=seed,
    )
    elapsed = time.perf_counter() - start

    return envelope(
        mode="goldfish",
        engine="goldfish",
        engine_version=GOLDFISH_VERSION,
        seed=seed,
        format_=deck.get("format"),
        card_coverage={
            "requested": sum(
                int(e.get("quantity", 1))
                for e in (deck.get("cards") or []) + (deck.get("commanders") or [])
            ),
            "supported": len(deck_hydrated),
            "missing": missing,
        },
        results=results,
        warnings=(
            ([f"{len(missing)} cards not in hydrated cache"] if missing else [])
            + _unresolved_fetch_warnings(deck_hydrated)
        ),
        duration_s=elapsed,
    )
