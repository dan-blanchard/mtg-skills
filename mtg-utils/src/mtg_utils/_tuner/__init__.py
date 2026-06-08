"""The deterministic deck tuner — a skill-agnostic evaluator + budgeted swap proposer.

It takes a ``HydratedDeck`` plus an injected ``search_fn`` (and optional ``combos_fn``),
never a ``ForgeState`` or any browser type, so deck-forge (consumer #1, via
``POST /api/tune``) and deck-wizard (planned consumer #2) share one engine
(ADR-0023). It names cards (the Deterministic core may; only the Session-agent may
not — ADR-0009) and adds no new card-matching: buckets come from ``budgets.role_of``
(Spine) and ``ranking.score_candidate`` (Engine), both bottoming out in
``theme_presets``.

Three layers (deck-forge CONTEXT.md, "Tune"): diagnose, cut candidates, budgeted swaps.
"""

from __future__ import annotations

from mtg_utils._tuner.tune import TuneParams, tune

__all__ = ["TuneParams", "tune"]
