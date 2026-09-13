"""The deck-analysis substrate (ADR-0050): signals, lanes, specs, bridges, synthesis,
the membership floor, role budgets, candidate ranking, rate, staples.

Everything here is a pure function of card records and concept trees — no hub state,
no browser type, no FastAPI. Two consumers read it as peers: deck-forge's hub
(``_deck_forge``: engine / views / app over a ``ForgeState``) and the deterministic
tuner (``_tuner``, ADR-0023) that deck-forge's ``/api/tune`` and deck-wizard's
``deck-tune`` both call. ADR-0023 deferred graduating this layer out of ``_deck_forge``
until deck-wizard adopted the tuner (ADR-0029); this package is that graduation.
"""
