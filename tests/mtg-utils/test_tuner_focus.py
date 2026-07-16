"""Focus metric: lands and Spine-role avenues are not themes; near-dupes collapse."""

from mtg_utils._deck_forge import signal_keys
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


def _tribal_sig(subject, source="x"):
    return Signal(
        key=signal_keys.TYPE_MATTERS,
        scope="you",
        subject=subject,
        text="",
        source=source,
        confidence="high",
    )


def test_emerging_tribal_theme_requires_a_payoff_subject():
    # ADR-0040 companion: an emerging TRIBAL avenue needs >=1 non-commander payoff
    # card naming the tribe, or changelings (every creature type) manufacture an
    # emerging flag for every tribe at once (the "Bird tribal" phantom). deck_size
    # 100 -> emerging floor 5, sub floor 10; depth 7 lands squarely in the band.
    goblin_sig = _tribal_sig("Goblin", "Goblin Warchief")
    bird_sig = _tribal_sig("Bird", "Changeling A")
    goblin_label = spec_for(goblin_sig).label  # "Goblin tribal"
    bird_label = spec_for(bird_sig).label  # "Bird tribal"
    classes = [_cc(f"Goblin{i}", "engine", [goblin_label]) for i in range(7)] + [
        _cc(f"Bird{i}", "engine", [bird_label]) for i in range(7)
    ]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[goblin_sig, bird_sig],
        tribal_payoff_subjects=frozenset({"Goblin"}),
    )
    emerging_labels = {e["label"] for e in fr["emerging"]}
    assert goblin_label in emerging_labels  # backed by a real payoff subject
    assert bird_label not in emerging_labels  # no payoff — the phantom is gated


def test_emerging_gate_leaves_nontribal_themes_alone():
    # A non-tribal emerging theme carries no type_matters ident at all, so it can
    # never be found in the label->subject map the gate builds from deck_signals —
    # the gate is a no-op for it even with an empty payoff set.
    classes = [_cc(f"P{i}", "engine", ["Proliferate"]) for i in range(7)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[],
        tribal_payoff_subjects=frozenset(),
    )
    assert [e["label"] for e in fr["emerging"]] == ["Proliferate"]


def test_emerging_tribal_gate_off_by_default():
    # Omitting tribal_payoff_subjects preserves the pre-ADR-0040 behavior: every
    # emerging tribal avenue surfaces regardless of payoff backing.
    goblin_sig = _tribal_sig("Goblin", "Goblin Warchief")
    bird_sig = _tribal_sig("Bird", "Changeling A")
    goblin_label = spec_for(goblin_sig).label
    bird_label = spec_for(bird_sig).label
    classes = [_cc(f"Goblin{i}", "engine", [goblin_label]) for i in range(7)] + [
        _cc(f"Bird{i}", "engine", [bird_label]) for i in range(7)
    ]
    fr = focus(classes, deck_size=100, deck_signals=[goblin_sig, bird_sig])
    emerging_labels = {e["label"] for e in fr["emerging"]}
    assert goblin_label in emerging_labels
    assert bird_label in emerging_labels


def test_granter_low_value_reads_quality_not_playrate():
    # ADR-0040 §2/§4 (task #97): a Granter is condemned by granted-ability
    # QUALITY alone — a premium/solid Granter with a null rank never lands in
    # low_value_cards (playrate breaks ties, never condemns); a weak Granter
    # does regardless of rank. Non-Granters keep the playrate read.
    def cc(name, grade):
        c = _cc(name, "engine", ["Slivers"])
        return CardClass(
            name=c.name,
            bucket=c.bucket,
            roles=c.roles,
            served=c.served,
            dual_purpose=c.dual_purpose,
            cmc=c.cmc,
            record=c.record,
            grant_grade=grade,
        )

    classes = [
        cc("Premium Granter", "premium"),
        cc("Solid Granter", "solid"),
        cc("Weak Granter", "weak"),
        cc("Plain Body", None),
    ]
    fr = focus(classes, deck_size=10)
    assert set(fr["low_value_cards"]) == {"Weak Granter", "Plain Body"}
