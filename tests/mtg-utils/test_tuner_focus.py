"""Focus metric: lands and Spine-role avenues are not themes; near-dupes collapse."""

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
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
    from mtg_utils._tuner.issues import Sourcing

    sourcing = Sourcing({"viable_avenues": []}, [], {})
    remedy = sourcing.remedy_for("efficiency", subkind="thin top-end")
    assert remedy is not None
    assert remedy.spec.get("cmc_min") == 6  # asks for a 6+ MV finisher
    # An unhandled curve subkind sources nothing.
    assert sourcing.remedy_for("efficiency", subkind="ok") is None


def test_near_duplicate_avenues_collapse_to_one():
    # The same cards back both labels (one theme described two ways) → one survives.
    classes = [
        _cc(f"Spell {i}", "engine", ["Spellslinger", "Magecraft / spellslinger"])
        for i in range(4)
    ]
    fr = focus(classes, deck_size=10)
    assert len(fr["viable_avenues"]) == 1


def _cheat_sig(source):
    return Signal(
        key="cheat_into_play",
        scope="you",
        subject="",
        text="",
        source=source,
        confidence="high",
    )


def _polymorph_classes():
    """The Jace, Multiverse Architect precon's shape: the cheat avenue's members are
    mostly the bombs the serve credits as its payoff, and every one of those also
    serves the generic big-creatures avenue — 16 of 19 (≥80 %, the commander and
    two polymorphs being the rest), while the deeper big-creatures avenue (22)
    also holds six bodies the cheat serve doesn't credit."""
    cheat = spec_for(_cheat_sig("Jace")).label  # "Cheat into play"
    big = "Big creatures / power matters"
    classes = [_cc("Jace", "commander", [cheat])]
    classes += [_cc(f"Bomb {i}", "engine", [cheat, big]) for i in range(16)]
    classes += [_cc(f"Polymorph {i}", "engine", [cheat]) for i in range(2)]
    classes += [_cc(f"Body {i}", "engine", [big]) for i in range(6)]
    return classes, cheat, big


def test_commander_held_avenue_survives_the_collapse():
    classes, cheat, big = _polymorph_classes()
    # The commander emits the cheat key (``read_deck_signals``' commander_idents),
    # so its avenue is the deck's own axis.
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_cheat_sig("Jace")],
        commander_idents=frozenset({("cheat_into_play", "you", "")}),
    )
    labels = [a["label"] for a in fr["viable_avenues"]]
    assert cheat in labels
    assert big in labels  # the generic lens is not collapsed either (16/22 < 0.8)


def test_avenue_the_commander_does_not_hold_still_collapses():
    classes, cheat, big = _polymorph_classes()
    # Same cards, but only a 99 card emits the cheat key: the ≥80 % rule applies,
    # whatever the Signal's ``source`` says.
    fr = focus(classes, deck_size=100, deck_signals=[_cheat_sig("Jace")])
    labels = [a["label"] for a in fr["viable_avenues"]]
    assert big in labels
    assert cheat not in labels


# ── Fed vs built: an avenue needs cards that CARE, not just cards that feed it ──


def _sig(key, scope="you", subject=""):
    return Signal(
        key=key, scope=scope, subject=subject, text="", source="x", confidence="high"
    )


def _fed_deck():
    """The stock Jace precon's shape in miniature: "Historic" is fed by every
    legendary creature and every rock (32 deep, one card — Jhoira — caring),
    "Combat" has nine attack-trigger cards caring, the commander's own cheat lane
    is held by Jace with seven carers."""
    historic = spec_for(_sig("historic_matters")).label
    combat = spec_for(_sig("attack_matters")).label
    cheat = spec_for(_sig("cheat_into_play")).label
    classes = [_cc("Jace", "commander", [cheat])]
    classes += [_cc(f"Legend {i}", "engine", [historic, combat]) for i in range(12)]
    classes += [
        _cc(f"Rock {i}", "spine", [historic], roles=["ramp"]) for i in range(10)
    ]
    classes += [_cc(f"Bomb {i}", "engine", [cheat, combat]) for i in range(10)]
    classes += [_cc(f"Polymorph {i}", "engine", [cheat]) for i in range(3)]
    signals = [
        _sig("historic_matters"),
        _sig("attack_matters"),
        _sig("cheat_into_play"),
    ]
    emitters = {
        ("historic_matters", "you", ""): frozenset({"Legend 0"}),
        ("attack_matters", "you", ""): frozenset({f"Legend {i}" for i in range(9)}),
        ("cheat_into_play", "you", ""): frozenset(
            {"Jace"}
            | {f"Polymorph {i}" for i in range(3)}
            | {"Bomb 0", "Bomb 1", "Bomb 2"}
        ),
    }
    return classes, signals, emitters, historic, combat, cheat


def test_a_deep_avenue_nobody_cares_about_is_fed_not_built():
    classes, signals, emitters, historic, combat, cheat = _fed_deck()
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        commander_idents=frozenset({("cheat_into_play", "you", "")}),
        emitters=emitters,
    )
    viable = [a["label"] for a in fr["viable_avenues"]]
    fed = {a["label"]: a for a in fr["fed"]}
    assert historic not in viable
    assert historic in fed
    assert fed[historic]["depth"] == 22
    assert fed[historic]["carers"] == 1
    assert fr["carer_floor"] == 4
    # The commander's lane leads (the remedies source adds from viable[0]) and is
    # a main theme whatever its depth; Combat follows on its nine carers.
    assert viable == [cheat, combat]
    assert fr["mains"] == [cheat, combat]
    assert fr["commander_avenues"] == [cheat]
    assert {a["label"]: a["carers"] for a in fr["viable_avenues"]} == {
        cheat: 7,
        combat: 9,
    }


def test_without_an_emitter_read_every_deep_avenue_is_built():
    # A caller with no ``read_deck_signals`` pass (``emitters=None``) keeps the
    # old depth-only behaviour: nothing is demoted to fed.
    classes, signals, _emitters, historic, _combat, _cheat = _fed_deck()
    fr = focus(classes, deck_size=100, deck_signals=signals)
    assert historic in [a["label"] for a in fr["viable_avenues"]]
    assert fr["fed"] == []


def test_a_makers_avenue_is_cared_about_by_its_matters_emitters():
    # Nine cards gain life (they EMIT lifegain_makers) but one card cares
    # (lifegain_matters): the makers avenue is fed, not built.
    makers = spec_for(_sig("lifegain_makers")).label
    classes = [_cc(f"Gainer {i}", "engine", [makers]) for i in range(11)]
    emitters = {
        ("lifegain_makers", "you", ""): frozenset({f"Gainer {i}" for i in range(9)}),
        ("lifegain_matters", "you", ""): frozenset({"Gainer 0"}),
    }
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("lifegain_makers")],
        emitters=emitters,
    )
    assert [a["label"] for a in fr["fed"]] == [makers]
    assert fr["fed"][0]["carers"] == 1


def test_an_emerging_avenue_needs_one_card_that_cares():
    label = spec_for(_sig("proliferate_makers")).label
    classes = [_cc(f"Prolif {i}", "engine", [label]) for i in range(6)]
    nobody = focus(
        classes, deck_size=100, deck_signals=[_sig("proliferate_makers")], emitters={}
    )
    assert label not in [a["label"] for a in nobody["emerging"]]
    somebody = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("proliferate_makers")],
        emitters={("proliferate_matters", "you", ""): frozenset({"Prolif 0"})},
    )
    assert [a["label"] for a in somebody["emerging"]] == [label]


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


def test_a_doer_lane_with_no_payoff_sibling_is_cared_about_by_its_doers():
    # mill_makers has no served mill_matters / wants_mill: the deck milling IS
    # the theme, so its carers are its makers and four of them build it.
    from mtg_utils._tuner.metrics import _cares_keys

    assert _cares_keys("mill_makers") == ("mill_makers",)
    label = spec_for(_sig("mill_makers")).label
    classes = [_cc(f"Mill {i}", "engine", [label]) for i in range(10)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("mill_makers")],
        emitters={
            ("mill_makers", "you", ""): frozenset(
                {"Mill 0", "Mill 1", "Mill 2", "Mill 3"}
            )
        },
    )
    assert [a["label"] for a in fr["viable_avenues"]] == [label]


def test_token_maker_is_cared_about_by_tokens_matter():
    # The one irregular doer / payoff spelling in the manifest.
    from mtg_utils._tuner.metrics import _cares_keys

    assert _cares_keys("token_maker")[0] == "tokens_matter"
    assert _cares_keys("lifegain_makers") == ("lifegain_matters", "wants_lifegain")
    assert _cares_keys("cheat_into_play") == ("cheat_into_play",)


def test_carers_are_read_across_scopes():
    # A doer lane emits scope ``any`` where its payoff sibling emits ``you``: the
    # carer read keys on (key, subject) only.
    makers = spec_for(_sig("lifegain_makers", scope="any")).label
    classes = [_cc(f"Gainer {i}", "engine", [makers]) for i in range(11)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("lifegain_makers", scope="any")],
        emitters={
            ("lifegain_makers", "any", ""): frozenset(
                {f"Gainer {i}" for i in range(9)}
            ),
            ("lifegain_matters", "you", ""): frozenset(
                {"Gainer 0", "Gainer 1", "Gainer 2", "Gainer 3"}
            ),
        },
    )
    assert [a["label"] for a in fr["viable_avenues"]] == [makers]
    assert fr["viable_avenues"][0]["carers"] == 4


def test_an_emerging_depth_avenue_nobody_cares_about_is_reported_fed():
    label = spec_for(_sig("proliferate_makers")).label
    classes = [_cc(f"Prolif {i}", "engine", [label]) for i in range(6)]
    fr = focus(
        classes, deck_size=100, deck_signals=[_sig("proliferate_makers")], emitters={}
    )
    assert fr["emerging"] == []
    assert [(a["label"], a["depth"], a["carers"]) for a in fr["fed"]] == [(label, 6, 0)]


# ── 2026-10-18: carers that are the commander's lane, lands, sibling reads ─────


def _polymorph_precon():
    """The stock Jace precon's shape after the fed/built read: the cheat lane is
    held by Jace and fed by his polymorphs and the power-5+ bombs; five of those
    bombs carry attack triggers (they EMIT attack_matters) beside two real Combat
    cards and two creature lands; Jace's one -3 also emits dig_until, a narrower
    read of the same cards."""
    cheat = spec_for(_sig("cheat_into_play")).label
    combat = spec_for(_sig("attack_matters")).label
    dig = spec_for(_sig("dig_until")).label
    classes = [_cc("Polymorph Cmdr", "commander", [cheat, dig])]
    classes += [_cc(f"Polymorph {i}", "engine", [cheat, dig]) for i in range(5)]
    classes += [_cc(f"Bomb {i}", "engine", [cheat, combat]) for i in range(12)]
    classes += [_cc(f"Attacker {i}", "engine", [combat]) for i in range(10)]
    classes += [_cc(f"Manland {i}", "land", []) for i in range(2)]
    signals = [_sig("cheat_into_play"), _sig("attack_matters"), _sig("dig_until")]
    polymorphs = {f"Polymorph {i}" for i in range(5)}
    emitters = {
        ("cheat_into_play", "you", ""): frozenset({"Polymorph Cmdr"} | polymorphs),
        ("dig_until", "you", ""): frozenset({"Polymorph Cmdr"} | polymorphs),
        ("attack_matters", "you", ""): frozenset(
            {f"Bomb {i}" for i in range(5)}
            | {"Attacker 0", "Attacker 1"}
            | {"Manland 0", "Manland 1"}
        ),
    }
    return classes, signals, emitters, cheat, combat, dig


def test_carers_already_in_the_commanders_lane_do_not_make_a_second_theme():
    classes, signals, emitters, cheat, combat, dig = _polymorph_precon()
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        commander_idents=frozenset(
            {("cheat_into_play", "you", ""), ("dig_until", "you", "")}
        ),
        emitters=emitters,
    )
    # Combat's nine emitters: the five bombs are the cheat lane's payoffs and the
    # two manlands are mana base — two cards built toward Combat on their own.
    fed = {a["label"]: a for a in fr["fed"]}
    assert combat in fed
    assert fed[combat]["carers"] == 2
    assert fed[combat]["carer_cards"] == ["Attacker 0", "Attacker 1"]
    # The held lane keeps every carer (never discounted against itself).
    cheat_row = next(a for a in fr["viable_avenues"] if a["label"] == cheat)
    assert cheat_row["carers"] == 6
    assert cheat_row["tier"] == "main"
    # Jace's -3 is one ability read three ways: the narrower sibling collapses into
    # the broad lane instead of surfacing as its own commander-held avenue.
    assert dig not in [a["label"] for a in fr["viable_avenues"]]
    assert dig not in [a["label"] for a in fr["emerging"]]
    assert fr["commander_avenues"] == [cheat]
    assert fr["verdict"] == "FOCUSED"


def test_a_main_theme_needs_builders_not_just_feeders():
    # Twenty-two artifacts feed "Artifacts" (every rock serves it) and four cards
    # care: enough for a sub-theme, not a main. Six carers clear the floor but
    # not a third of the feeders (still a sub); eight make it a main.
    artifacts = spec_for(_sig("artifacts_matter")).label
    classes = [_cc(f"Rock {i}", "engine", [artifacts]) for i in range(22)]
    sig = [_sig("artifacts_matter")]
    four = {("artifacts_matter", "you", ""): frozenset({f"Rock {i}" for i in range(4)})}
    fr = focus(classes, deck_size=100, deck_signals=sig, emitters=four)
    assert fr["main_carer_floor"] == 6
    assert [(a["label"], a["tier"]) for a in fr["viable_avenues"]] == [
        (artifacts, "sub")
    ]
    six = {("artifacts_matter", "you", ""): frozenset({f"Rock {i}" for i in range(6)})}
    fr = focus(classes, deck_size=100, deck_signals=sig, emitters=six)
    assert [(a["label"], a["tier"]) for a in fr["viable_avenues"]] == [
        (artifacts, "sub")
    ]
    eight = {
        ("artifacts_matter", "you", ""): frozenset({f"Rock {i}" for i in range(8)})
    }
    fr = focus(classes, deck_size=100, deck_signals=sig, emitters=eight)
    assert [(a["label"], a["tier"]) for a in fr["viable_avenues"]] == [
        (artifacts, "main")
    ]
    # A caller with no emitter read keeps the depth-only main tier.
    fr = focus(classes, deck_size=100, deck_signals=sig)
    assert fr["viable_avenues"][0]["tier"] == "main"


def test_a_subjectless_payoff_cares_about_every_subject_of_its_doer():
    # A tokens anthem (tokens_matter, subject "") cares about Mite makers.
    mites = spec_for(_sig("token_maker", subject="Mite")).label
    classes = [_cc(f"Mite maker {i}", "engine", [mites]) for i in range(10)]
    classes += [_cc(f"Anthem {i}", "engine", [mites]) for i in range(4)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("token_maker", subject="Mite")],
        emitters={
            ("token_maker", "you", "Mite"): frozenset(
                {f"Mite maker {i}" for i in range(10)}
            ),
            ("tokens_matter", "you", ""): frozenset({f"Anthem {i}" for i in range(4)}),
        },
    )
    assert [a["label"] for a in fr["viable_avenues"]] == [mites]
    assert fr["viable_avenues"][0]["carer_cards"] == [f"Anthem {i}" for i in range(4)]


def test_board_wipes_are_scaffolding_not_a_theme():
    wipes = spec_for(_sig("mass_removal")).label
    classes = [
        _cc(f"Wipe {i}", "spine", [wipes], roles=["board_wipe"]) for i in range(6)
    ]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("mass_removal")],
        emitters={
            ("mass_removal", "you", ""): frozenset({f"Wipe {i}" for i in range(6)})
        },
    )
    assert fr["viable_avenues"] == []
    assert fr["emerging"] == []


def test_verdict_counts_mains_and_subs_not_viable_avenues():
    def deck(n_mains, n_subs):
        classes, emitters = [], {}
        for m in range(n_mains):
            lbl = f"Main {m}"
            classes += [_cc(f"M{m}-{i}", "engine", [lbl]) for i in range(20)]
            emitters[(f"main{m}", "you", "")] = frozenset(f"M{m}-{i}" for i in range(6))
        for s in range(n_subs):
            lbl = f"Sub {s}"
            classes += [_cc(f"S{s}-{i}", "engine", [lbl]) for i in range(10)]
            emitters[(f"sub{s}", "you", "")] = frozenset(f"S{s}-{i}" for i in range(4))
        return classes, emitters

    # Labels here are synthetic (no spec), so run the legacy emitter-less path for
    # the tiering and read the verdict off mains / subs directly.
    classes, _ = deck(1, 2)
    assert focus(classes, deck_size=100)["verdict"] == "FOCUSED"
    classes, _ = deck(2, 0)
    assert focus(classes, deck_size=100)["verdict"] == "SPREAD-THIN"
    # A clear main with three light subs is focused (a sub is a few cards
    # caring); three subs with NO main is a deck pulled three ways.
    classes, _ = deck(1, 3)
    assert focus(classes, deck_size=100)["verdict"] == "FOCUSED"
    classes, _ = deck(0, 3)
    assert focus(classes, deck_size=100)["verdict"] == "SPREAD-THIN"
    classes, _ = deck(0, 2)
    assert focus(classes, deck_size=100)["verdict"] == "FOCUSED"


def _two_lane_commander():
    """Saheeli, Radiant Creator's shape: the commander emits an artifacts key and
    an energy key, each a built avenue with enough carers for a main."""
    art = spec_for(_sig("artifacts_matter")).label
    energy = spec_for(_sig("energy_matters")).label
    classes = [_cc("Saheeli", "commander", [art, energy])]
    classes += [_cc(f"Art {i}", "engine", [art]) for i in range(20)]
    classes += [_cc(f"Energy {i}", "engine", [energy]) for i in range(20)]
    signals = [_sig("artifacts_matter"), _sig("energy_matters")]
    emitters = {
        ("artifacts_matter", "you", ""): frozenset(
            {"Saheeli"} | {f"Art {i}" for i in range(10)}
        ),
        ("energy_matters", "you", ""): frozenset(
            {"Saheeli"} | {f"Energy {i}" for i in range(10)}
        ),
    }
    return classes, signals, emitters, art, energy


def test_two_commander_held_mains_are_one_direction():
    classes, signals, emitters, art, energy = _two_lane_commander()
    held = frozenset({("artifacts_matter", "you", ""), ("energy_matters", "you", "")})
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        emitters=emitters,
        commander_idents=held,
    )
    tiers = {a["label"]: a["tier"] for a in fr["viable_avenues"]}
    assert tiers[art] == "main"
    assert tiers[energy] == "main"
    assert fr["verdict"] == "FOCUSED"
    # The same two mains, neither held by the commander: two directions.
    fr = focus(classes, deck_size=100, deck_signals=signals, emitters=emitters)
    assert fr["verdict"] == "SPREAD-THIN"


def test_a_main_needs_carers_in_proportion_to_its_feeders():
    """Six cards caring about twenty-two artifacts (the Timey-Wimey precon) is a
    sub-theme beside the main, not a second main."""
    main = spec_for(_sig("suspend_matters")).label
    art = spec_for(_sig("artifacts_matter")).label
    classes = [_cc("Doctor", "commander", [main])]
    classes += [_cc(f"Time {i}", "engine", [main]) for i in range(30)]
    classes += [_cc(f"Art {i}", "engine", [art]) for i in range(22)]
    signals = [_sig("suspend_matters"), _sig("artifacts_matter")]
    emitters = {
        ("suspend_matters", "you", ""): frozenset(
            {"Doctor"} | {f"Time {i}" for i in range(20)}
        ),
        ("artifacts_matter", "you", ""): frozenset({f"Art {i}" for i in range(6)}),
    }
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        emitters=emitters,
        commander_idents=frozenset({("suspend_matters", "you", "")}),
    )
    tiers = {a["label"]: a["tier"] for a in fr["viable_avenues"]}
    assert tiers[main] == "main"
    assert tiers[art] == "sub"
    assert fr["verdict"] == "FOCUSED"


def test_the_primary_lane_is_the_held_lane_most_cards_care_about():
    """Nelly Borca: her attack trigger reads as Combat (deeper) and as Goad (more
    cards care). The primary lane is the one the deck built toward."""
    combat = spec_for(_sig("attack_matters")).label
    goad_sig = _sig("goad_makers", scope="opponents")
    goad = spec_for(goad_sig).label
    classes = [_cc("Nelly", "commander", [combat, goad])]
    classes += [_cc(f"Attacker {i}", "engine", [combat]) for i in range(17)]
    classes += [_cc(f"Goader {i}", "engine", [goad]) for i in range(16)]
    signals = [_sig("attack_matters"), goad_sig]
    emitters = {
        ("attack_matters", "you", ""): frozenset(
            {"Nelly"} | {f"Attacker {i}" for i in range(5)}
        ),
        ("goad_makers", "opponents", ""): frozenset(
            {"Nelly"} | {f"Goader {i}" for i in range(12)}
        ),
    }
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        emitters=emitters,
        commander_idents=frozenset(
            {("attack_matters", "you", ""), ("goad_makers", "opponents", "")}
        ),
    )
    assert fr["viable_avenues"][0]["label"] == goad


def test_an_engine_card_feeding_only_fed_avenues_is_dead_weight():
    classes, signals, emitters, _cheat, _combat, _dig = _polymorph_precon()
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        commander_idents=frozenset({("cheat_into_play", "you", "")}),
        emitters=emitters,
    )
    # The ten attackers serve Combat only, and Combat is fed: they feed nothing the
    # deck built toward, so they count as filler and leave the engine pool.
    attackers = sorted(f"Attacker {i}" for i in range(10))
    assert fr["fed_only_cards"] == attackers
    assert sorted(fr["filler_cards"]) == attackers
    assert fr["filler"] == 10
    assert fr["engine_pool"] == 17  # 5 polymorphs + 12 bombs
    # Filler is never also low-value (it would count twice as dead weight), and
    # the lane's own polymorphs are never low-value; the rankless bombs the
    # lane merely serves stay upgrade targets.
    low = set(fr["low_value_cards"])
    assert not low & set(attackers)
    assert not low & {f"Polymorph {i}" for i in range(5)}
    assert "Bomb 0" in low


def test_nothing_is_fed_only_until_something_is_built():
    # A build in progress: ten cards feeding an avenue nobody cares about yet must
    # not all read as filler for the role fills to cut.
    label = spec_for(_sig("mill_makers")).label
    classes = [_cc(f"Mill {i}", "engine", [label]) for i in range(10)]
    fr = focus(classes, deck_size=100, deck_signals=[_sig("mill_makers")], emitters={})
    assert fr["viable_avenues"] == []
    assert fr["fed_only_cards"] == []
    assert fr["engine_pool"] == 10


def test_a_card_on_the_commanders_lane_is_never_low_value():
    cheat = spec_for(_sig("cheat_into_play")).label
    polymorphs = [
        CardClass(
            name=f"Polymorph {i}",
            bucket="engine",
            roles=(),
            served=(cheat,),
            dual_purpose=False,
            cmc=3.0,
            record={"name": f"Polymorph {i}"},
            edhrec_rank=None,  # a brand-new card: no play-rate at all
        )
        for i in range(12)
    ]
    classes = [_cc("Polymorph Cmdr", "commander", [cheat]), *polymorphs]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("cheat_into_play")],
        commander_idents=frozenset({("cheat_into_play", "you", "")}),
        emitters={
            ("cheat_into_play", "you", ""): frozenset(
                {"Polymorph Cmdr"} | {f"Polymorph {i}" for i in range(12)}
            )
        },
        medium="paper",
    )
    assert fr["low_value_cards"] == []
    assert fr["commander_lane_cards"] == sorted(
        ["Polymorph Cmdr", *(f"Polymorph {i}" for i in range(12))]
    )


def test_the_commanders_spine_ident_opens_no_lane_and_protects_no_card():
    # Jace's +1 draws: card_draw_engine is a Spine avenue. Its emitters
    # (Brainstorm) are not the polymorph lane's cards, so they get no cut
    # protection and no exemption from the carer discount.
    cheat = spec_for(_sig("cheat_into_play")).label
    draw = spec_for(_sig("card_draw_engine")).label
    combat = spec_for(_sig("attack_matters")).label
    classes = [_cc("Polymorph Cmdr", "commander", [cheat, draw])]
    classes += [_cc(f"Polymorph {i}", "engine", [cheat]) for i in range(10)]
    classes += [_cc(f"Bomb {i}", "engine", [cheat, combat]) for i in range(10)]
    classes += [
        _cc(f"Cantrip {i}", "spine", [draw], roles=["card_draw"]) for i in range(5)
    ]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[
            _sig("cheat_into_play"),
            _sig("card_draw_engine"),
            _sig("attack_matters"),
        ],
        commander_idents=frozenset(
            {("cheat_into_play", "you", ""), ("card_draw_engine", "you", "")}
        ),
        emitters={
            ("cheat_into_play", "you", ""): frozenset(
                {"Polymorph Cmdr"} | {f"Polymorph {i}" for i in range(10)}
            ),
            ("card_draw_engine", "you", ""): frozenset(
                {"Polymorph Cmdr", "Bomb 0"} | {f"Cantrip {i}" for i in range(5)}
            ),
            # Six bombs care about attacking; Bomb 0 also draws (Memnarch).
            ("attack_matters", "you", ""): frozenset({f"Bomb {i}" for i in range(6)}),
        },
    )
    assert fr["commander_avenues"] == [cheat]
    assert "Cantrip 0" not in fr["commander_lane_cards"]
    assert "Bomb 0" not in fr["commander_lane_cards"]
    # Every bomb is the cheat lane's payoff: Combat has no carer of its own.
    assert {a["label"]: a["carers"] for a in fr["fed"]} == {combat: 0}


def test_a_collapsed_near_duplicate_avenue_still_counts_as_built():
    # Theme B's members are 90% Theme A's (it collapses into A), but the one
    # card only B serves is on a built theme: not fed-only, not filler.
    classes = [_cc(f"Shared {i}", "engine", ["Theme A", "Theme B"]) for i in range(18)]
    classes += [
        _cc("Only A", "engine", ["Theme A"]),
        _cc("Only B", "engine", ["Theme B"]),
    ]
    emitters = {
        ("a", "you", ""): frozenset({f"Shared {i}" for i in range(6)}),
        ("b", "you", ""): frozenset({f"Shared {i}" for i in range(6)}),
    }
    # Synthetic labels have no spec, so the carer read is the legacy
    # emitter-less path: both avenues built, B collapses into A.
    fr = focus(classes, deck_size=100)
    assert [a["label"] for a in fr["viable_avenues"]] == ["Theme A"]
    assert fr["fed_only_cards"] == []
    assert fr["filler_cards"] == []
    assert emitters  # documents the shape; the legacy path ignores emitters


def test_the_lane_members_are_what_the_held_avenues_serve():
    """Doers emit the held ident; members are every nonland card a held avenue
    serves (Gimbal's rocks) — what a template band is measured against."""
    classes, signals, emitters, _art, _energy = _two_lane_commander()
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        emitters=emitters,
        commander_idents=frozenset({("artifacts_matter", "you", "")}),
    )
    assert set(fr["commander_lane_cards"]) == {"Saheeli"} | {
        f"Art {i}" for i in range(10)
    }
    assert set(fr["commander_lane_members"]) == {"Saheeli"} | {
        f"Art {i}" for i in range(20)
    }
