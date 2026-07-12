"""Card IR pipeline internals: strict-load phase-rs's parse into the typed
mirror substrate, overlay it into concept trees (the ADR-0035 crosswalk), emit
the compat ``Card``, and build/load the crosswalk cache sidecar. (The legacy
``project.py`` regex projection died in ADR-0039 step 7.)

The public schema lives in ``mtg_utils.card_ir``; these modules are private
machinery (like ``_phase`` / ``_sidecar``). Nothing here may import
``_deck_forge.signals`` — the dependency points the other way (signals read
the IR / the concept trees), so a back-edge would create an import cycle.
"""
