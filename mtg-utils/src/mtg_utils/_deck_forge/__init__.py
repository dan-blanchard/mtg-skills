"""deck-forge backend internals — the HUB only (state, engine, views, routes,
persistence, images, the agent bridge). The deck-analysis substrate it reads
(signals, lanes, budgets, ranking, …) is ``mtg_utils._analysis`` (ADR-0050).

Mirrors the per-feature package convention used by ``_custom_format`` and
``_stores``. CLI-facing entry lives in ``mtg_utils.deck_forge_server``.
"""
