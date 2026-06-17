"""Canonical signal-key constants shared by the detector and the exploitation map.

A signal ``key`` is a contract between ``signals.py`` (which emits ``Signal(key=...)``)
and ``signal_specs.py`` (which maps ``(key, scope)`` to an avenue spec). It used to live
as a bare magic string in both, so a typo on either side was a *silent* no-avenue. These
constants give the cross-file keys a compile-time handle — a typo dies as an
``AttributeError`` at import instead of vanishing — and the key-agreement gate at the
bottom of ``signal_specs.py`` asserts every detector-produced key resolves to a spec.

Each constant's VALUE is exactly the on-the-wire key (``Signal.key`` / ``SPECS`` tuple
key / the SPA's JSON), so this is runtime-identical to the strings it replaces. Leaf
module — stdlib only, no deck-forge imports — so both files import it cycle-free.
"""

from __future__ import annotations

from typing import Final

# Subject-bearing keys: emitted WITH a captured subject and resolved dynamically by
# signal_specs._subject_spec (no static SPECS entry). These are the clearest hand↔hand
# keys — named in both the detectors (signals.py) and the subject dispatch
# (signal_specs.py), so they earn constants.
TYPE_MATTERS: Final = "type_matters"
TOKEN_MAKER: Final = "token_maker"
TYPED_SPELLCAST: Final = "typed_spellcast"
KEYWORD_TRIBE: Final = "keyword_tribe"
# Meld (CR 701.42): the subject is THIS card's own name; the one partner that melds
# with it names this card in its meld text, so the per-subject serve finds exactly it.
MELD_PAIR: Final = "meld_pair"

SUBJECT_KEYS: Final = frozenset(
    {TYPE_MATTERS, TOKEN_MAKER, TYPED_SPELLCAST, KEYWORD_TRIBE, MELD_PAIR}
)
