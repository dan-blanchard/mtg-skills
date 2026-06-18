"""Card IR pipeline internals: project phase-rs's parse → the Card IR, fill its
gaps from oracle text, build/load the cache sidecar, and diff IR-derived signals
against the regex path.

The public schema lives in ``mtg_utils.card_ir``; these modules are private
machinery (like ``_phase`` / ``_sidecar``). Nothing here may import
``_deck_forge.signals`` — the dependency points the other way (signals will read
the IR in Milestone A2), so a back-edge would create an import cycle.
"""
