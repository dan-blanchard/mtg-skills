"""Scoped-subject extraction for untap_engine / anthem_static (iter-1 fix).

The iteration-1 precision panel proved the gap with unanimous refuter kills:
Myr Galvanizer (untaps only OTHER Myr) and Merrow Reejerey (whole engine
gated on casting Merfolk) ranked into Krenko / Urza top-20s because their
idents were byte-identical to Thousand-Year Elixir's — ``untap_engine|you|``
with no subject. The lanes now surface the engine's subtype scope in the
ident SUBJECT segment (the ``token_maker|you|Goblin`` convention):

* untap_engine — the untap TARGET filter's single subtype (Myr Galvanizer,
  Arbor Elf's Forest), or, when the target is unscoped, the single subtype
  of a gating trigger's ``valid_card`` filter (Merrow Reejerey: the untap
  only fires per Merfolk cast, so Merfolk IS the engine's rate scope).
  Unscoped engines (Thousand-Year Elixir's "target creature", Seedborn
  Muse's untap-during-each-step static) keep the empty subject.
* anthem_static — the affected group filter's single subtype (Goblin King,
  Crucible of Fire). Core-type-only scopes (Chrome Dome's "artifact
  creatures", Heraldic Banner's chosen color) stay empty: subjects carry
  SUBTYPES only, matching the _subtypes precision-gate vocabulary.

Every case runs the production ``extract_signals_hybrid`` over the REAL
committed-snapshot IR (ADR-0027/0039) — no synthetic trees.
"""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_card_ir, test_signals


def _idents_of(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Myr Galvanizer", "untap_engine|you|Myr"),
        ("Merrow Reejerey", "untap_engine|you|Merfolk"),
        ("Thousand-Year Elixir", "untap_engine|you|"),
        ("Seedborn Muse", "untap_engine|you|"),
    ],
)
def test_untap_engine_subject_scope(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    idents = _idents_of(name)
    assert expected in idents, sorted(i for i in idents if "untap" in i)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Goblin King", "anthem_static|you|Goblin"),
        ("Merrow Reejerey", "anthem_static|you|Merfolk"),
        ("Crucible of Fire", "anthem_static|you|Dragon"),
        ("Glorious Anthem", "anthem_static|you|"),
        ("Heraldic Banner", "anthem_static|you|"),
        ("Eldrazi Monument", "anthem_static|you|"),
    ],
)
def test_anthem_static_subject_scope(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    idents = _idents_of(name)
    assert expected in idents, sorted(i for i in idents if "anthem" in i)


def test_scoped_ident_replaces_unscoped_never_duplicates():
    # A scoped engine must NOT also emit the unscoped ident — one lane, one
    # ident, or the pair gate reads the card as both scoped and universal.
    test_card_ir("Myr Galvanizer")
    assert "untap_engine|you|" not in _idents_of("Myr Galvanizer")
    test_card_ir("Goblin King")
    assert "anthem_static|you|" not in _idents_of("Goblin King")


# ── iteration-1b (v2 panel kills, 2026-07-18) ────────────────────────────────
# Second measured batch: Intruder Alarm ("Whenever a creature enters, untap
# all creatures" — no controller filter, unanimous refuter kills under Urza
# for crediting a symmetric effect as a your-side engine) and the core-type-
# scoped anthems (Chrome Dome "other ARTIFACT creatures", Weaver of Harmony
# "other ENCHANTMENT creatures" — killed under Zaxara, whose Hydras are
# neither).


@pytest.mark.parametrize(
    ("name", "expected_scope"),
    [
        # A mass untap with NO controller filter untaps every player's
        # board — scope "each", so the your-side pair row skips it.
        ("Intruder Alarm", "each"),
        # Controller-filtered mass / static-mode engines stay "you".
        ("Seedborn Muse", "you"),
        # A TARGETED untap is controller-chosen — "you" even with no
        # controller filter on the target ("untap target creature").
        ("Thousand-Year Elixir", "you"),
        # A SELF-scoped untap-during static is your own permanent, not
        # symmetry ("Endbringer untaps during each other player's untap
        # step" — SelfRef affected, no group filter).
        ("Endbringer", "you"),
    ],
)
def test_untap_engine_scope_symmetry(name, expected_scope):
    test_card_ir(name)
    scopes = {s.scope for s in test_signals(name) if s.key == "untap_engine"}
    assert scopes == {expected_scope}, (name, scopes)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # No subtype scope, but a single non-creature CORE type scope —
        # the subject carries it (lowercased, distinct from the
        # capitalized subtype vocabulary).
        ("Chrome Dome", "anthem_static|you|artifact"),
        ("Weaver of Harmony", "anthem_static|you|enchantment"),
        # A plain creature-group anthem stays unscoped.
        ("Eldrazi Monument", "anthem_static|you|"),
    ],
)
def test_anthem_static_core_type_scope(name, expected):
    test_card_ir(name)
    idents = _idents_of(name)
    assert expected in idents, sorted(i for i in idents if "anthem" in i)
