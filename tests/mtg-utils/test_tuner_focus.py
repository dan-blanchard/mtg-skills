"""Focus metric: lands and Spine-role avenues are not themes; near-dupes collapse."""

from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import Signal
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.metrics import focus


def _cc(name, bucket, served, roles=()):
    return CardClass(
        name=name,
        bucket=bucket,
        roles=tuple(roles),
        served=tuple(served),
        dual_purpose=(bucket == "spine" and bool(served)),
        cmc=2.0,
        record={"name": name},
    )


def test_lands_and_spine_avenues_are_not_themes():
    ramp_sig = Signal(
        key="ramp",
        scope="you",
        subject="",
        text="",
        source="Sol Ring",
        confidence="high",
    )
    ramp_label = spec_for(ramp_sig).label  # "Ramp / big mana"
    classes = [
        _cc("Command Tower", "land", [ramp_label]),
        _cc("Hallowed Fountain", "land", [ramp_label]),
        _cc("Sol Ring", "spine", [ramp_label], roles=["ramp"]),
        _cc("Token Maker A", "engine", ["Tokens"]),
        _cc("Token Maker B", "engine", ["Tokens"]),
        _cc("Token Maker C", "engine", ["Tokens"]),
    ]
    # deck_size 10 → viability floor 2, so 3 token-makers clears it.
    fr = focus(classes, deck_size=10, deck_signals=[ramp_sig])
    labels = {a["label"] for a in fr["viable_avenues"]}
    assert ramp_label not in labels  # a Spine-role avenue is scaffolding, not a theme
    assert "Tokens" in labels
    # No land ever appears as theme support.
    for a in fr["viable_avenues"]:
        assert "Command Tower" not in a["cards"]
        assert "Hallowed Fountain" not in a["cards"]


def test_two_tier_main_and_sub_themes():
    # A sub-theme is shallower than the main and must not be held to the main's floor.
    # deck_size 100 → main floor 20, sub floor 10.
    classes = (
        [_cc(f"A{i}", "engine", ["Theme A"]) for i in range(20)]
        + [_cc(f"B{i}", "engine", ["Theme B"]) for i in range(12)]
        + [_cc(f"C{i}", "engine", ["Theme C"]) for i in range(5)]
    )
    fr = focus(classes, deck_size=100)
    by = {a["label"]: a for a in fr["viable_avenues"]}
    assert by["Theme A"]["tier"] == "main"  # depth 20 ≥ main floor
    assert by["Theme B"]["tier"] == "sub"  # depth 12: sub floor ≤ d < main floor
    assert "Theme C" not in by  # depth 5 < sub floor → dropped, not a theme
    assert fr["verdict"] == "FOCUSED"  # one main + one sub = the research ideal


def test_emerging_theme_surfaces_below_the_sub_floor():
    # deck_size 100 → main floor 20, sub floor 10, emerging floor 5. An under-supported
    # theme (5 ≤ depth < 10) is surfaced as emerging, not dropped as noise.
    classes = (
        [_cc(f"M{i}", "engine", ["Main"]) for i in range(22)]
        + [_cc(f"P{i}", "engine", ["Proliferate"]) for i in range(7)]
        + [_cc(f"N{i}", "engine", ["Noise"]) for i in range(3)]
    )
    fr = focus(classes, deck_size=100)
    assert [a["label"] for a in fr["viable_avenues"]] == ["Main"]
    assert [e["label"] for e in fr["emerging"]] == ["Proliferate"]
    assert "Noise" not in {
        e["label"] for e in fr["emerging"]
    }  # depth 3 < emerging floor


def test_efficiency_thin_top_end_is_actionable():
    # A curve issue (thin top-end) must source an add at the missing CMC band — scoped to
    # the deck's main theme — not be silently advisory.
    from mtg_utils._tuner.swaps import _spec_for_issue

    issue = {"kind": "efficiency", "subkind": "thin top-end"}
    spec = _spec_for_issue(issue, {"viable_avenues": []}, [])
    assert spec is not None
    assert spec.get("cmc_min") == 6  # asks for a 6+ MV finisher
    # An unhandled curve subkind stays advisory.
    assert _spec_for_issue({"kind": "efficiency", "subkind": "ok"}, {}, []) is None


def test_near_duplicate_avenues_collapse_to_one():
    # The same cards back both labels (one theme described two ways) → one survives.
    classes = [
        _cc(f"Spell {i}", "engine", ["Spellslinger", "Magecraft / spellslinger"])
        for i in range(4)
    ]
    fr = focus(classes, deck_size=10)
    assert len(fr["viable_avenues"]) == 1


def test_removal_family_avenues_are_not_themes():
    # Exile-based removal and counterspells are scaffolding (they answer the board),
    # never a "commit or cut" theme — but _SPINE_AVENUE_KEYS excluded only "removal", so
    # sibling removal lanes leaked into focus: Light-Paws got "Exile removal (5) is an
    # under-supported theme" for running Swords / Path to Exile.
    exile_sig = Signal(
        key="exile_removal",
        scope="you",
        subject="",
        text="",
        source="x",
        confidence="high",
    )
    counter_sig = Signal(
        key="counter_control",
        scope="you",
        subject="",
        text="",
        source="x",
        confidence="high",
    )
    exile_label = spec_for(exile_sig).label  # "Exile removal"
    counter_label = spec_for(counter_sig).label  # "Counterspells / control"
    classes = [
        _cc("Swords to Plowshares", "spine", [exile_label], roles=["interaction"]),
        _cc("Path to Exile", "spine", [exile_label], roles=["interaction"]),
        _cc("Counterspell", "spine", [counter_label], roles=["interaction"]),
        _cc("Aura A", "engine", ["Voltron / equipment & auras"]),
        _cc("Aura B", "engine", ["Voltron / equipment & auras"]),
        _cc("Aura C", "engine", ["Voltron / equipment & auras"]),
    ]
    fr = focus(classes, deck_size=10, deck_signals=[exile_sig, counter_sig])
    labels = {a["label"] for a in fr["viable_avenues"]}
    labels |= {a["label"] for a in fr["emerging"]}
    assert exile_label not in labels  # scaffolding, not a theme
    assert counter_label not in labels
    assert "Voltron / equipment & auras" in {a["label"] for a in fr["viable_avenues"]}


def test_null_rank_low_value_read_is_medium_aware():
    # ADR-0040 §4 (task #99): the _cc helper leaves edhrec_rank=None — on a
    # paper deck that is fringe-evidence (genuinely unplayed), on a digital
    # deck it is no-data (EDHREC has no Arena population) and cannot land a
    # card in low_value_cards.
    classes = [
        _cc("Token Maker A", "engine", ["Tokens"]),
        _cc("Token Maker B", "engine", ["Tokens"]),
    ]
    paper = focus(classes, deck_size=10, medium="paper")
    digital = focus(classes, deck_size=10, medium="digital")
    assert set(paper["low_value_cards"]) == {"Token Maker A", "Token Maker B"}
    assert digital["low_value_cards"] == []
