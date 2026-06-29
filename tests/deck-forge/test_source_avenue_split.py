"""ADR-0026: a fused payoff/source spec splits into a payoff avenue (oracle) plus a
Source avenue (the pieces, fetched by card_type) — the static-membership analogue of
the tribal bodies/payoffs/enablers split."""

from mtg_utils._deck_forge import _ir_lookup, engine
from mtg_utils._deck_forge.signal_specs import Serve, source_split
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import test_card, test_card_ir

# ADR-0027 (voltron migration — the LAST key): voltron_matters is served only from the
# Card IR now, so the engine must resolve Sram's IR (the structural Aura/Equipment cast
# trigger _detect_voltron_payoff_ir reads) for the voltron avenue to surface. Real
# Scryfall record + real projected IR from the committed snapshot (#25).
SRAM = test_card("Sram, Senior Edificer")
_SRAM_IR = test_card_ir("Sram, Senior Edificer")
_SRAM_OID = SRAM["oracle_id"]
INDEX = {SRAM["name"]: SRAM}


def _state():
    session = DeckSession("commander")
    session.add(SRAM["name"], 1, zone="commanders")
    return ForgeState(by_name=INDEX, search_fn=lambda **_: [], session=session)


def _by_label(avs):
    return {a["label"]: a for a in avs}


def test_voltron_fans_into_payoff_and_source_avenues(monkeypatch):
    monkeypatch.setattr(_ir_lookup, "_index", lambda: {_SRAM_OID: _SRAM_IR})
    avs = _by_label(engine.avenues(_state(), [SRAM]))
    # The payoff avenue (the _matters lane) stays, now oracle-only — no type fetch.
    payoff = avs["Voltron / equipment & auras"]
    assert "card_type" not in payoff["search"]
    assert "oracle" in payoff["search"]
    # A distinct Source avenue surfaces the pieces, fetched by an OR of card types.
    source = avs["Auras & Equipment"]
    assert source["search"]["card_type"] == ("aura", "equipment")
    # The source serve credits the types; the payoff serve no longer does.
    assert set(source["serve"]["types"]) == {"aura", "equipment"}
    assert not payoff.get("serve", {}).get("types")


def test_source_split_skips_specs_without_a_payoff_oracle():
    # A pure type-membership serve (no oracle) is already a single source-ish lane;
    # it must not be split (nothing to put in a payoff avenue).
    class _FakeSpec:
        serve = Serve(types=frozenset({"artifact"}))  # no oracle
        search = {"card_type": "Artifact"}
        label = "x"
        avenue = "x"
        extras = ()

    assert source_split(_FakeSpec()) is None


def test_card_type_or_is_backward_compatible_with_string():
    # The card_search change: a tuple OR-matches; a bare string is unchanged.
    from mtg_utils.card_search import _matches_filters

    aura = {"type_line": "Enchantment — Aura", "legalities": {"commander": "legal"}}
    equip = {"type_line": "Artifact — Equipment", "legalities": {"commander": "legal"}}
    base = {
        "allowed_colors": None,
        "oracle_re": None,
        "name_substr": None,
        "cmc_min": None,
        "cmc_max": None,
        "price_min": None,
        "price_max": None,
    }
    assert _matches_filters(aura, type_lower=("aura", "equipment"), **base)
    assert _matches_filters(equip, type_lower=("aura", "equipment"), **base)
    assert _matches_filters(aura, type_lower="aura", **base)
    assert not _matches_filters(aura, type_lower="equipment", **base)
