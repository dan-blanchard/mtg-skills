"""Focus metric: lands and Spine-role avenues are not themes; near-dupes collapse."""

from dataclasses import replace

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.metrics import focus
from mtg_utils.testkit import test_card


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


def test_an_emerging_avenue_needs_builders_in_proportion():
    # An emerging direction needs two carers (half the sub's carer floor of four
    # at 100 cards, never one card) and carers a third of its depth — the share
    # a main is held to. One card caring about six proliferators is a payoff.
    label = spec_for(_sig("proliferate_makers")).label

    def run(depth, carers):
        classes = [_cc(f"Prolif {i}", "engine", [label]) for i in range(depth)]
        emitters = {
            ("proliferate_matters", "you", ""): frozenset(
                f"Prolif {i}" for i in range(carers)
            )
        }
        return focus(
            classes,
            deck_size=100,
            deck_signals=[_sig("proliferate_makers")],
            emitters=emitters,
        )

    assert run(6, 0)["emerging"] == []
    one = run(6, 1)
    assert one["emerging"] == []
    assert [(a["label"], a["carers"]) for a in one["fed"]] == [(label, 1)]
    assert one["emerging_carer_floor"] == 2
    # Two carers over five or six feeders build it (Blame Game's Proliferate,
    # 5 deep / 2 carers); two over nine do not (Jace's activated-ability
    # engine, 9 / 2); three over nine do (Animated Army's Landfall, 9 / 3).
    assert [a["label"] for a in run(6, 2)["emerging"]] == [label]
    assert run(9, 2)["emerging"] == []
    assert [a["label"] for a in run(9, 3)["emerging"]] == [label]


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
    # A doer lane emits scope ``any`` where its payoff sibling emits ``you``: a
    # scope the payoff key does not split stays scope-blind.
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


def test_a_scoped_payoff_cares_only_about_its_own_scope():
    # graveyard_matters gives ``you`` and ``opponents`` avenues of their own: a
    # self-mill payoff is a carer of "Your graveyard", never of "Opponents'
    # graveyards" (under Teval both read 43 carers). A scope the key does not
    # split (``each``: Living Death's symmetric return) cares about either.
    yours = spec_for(_sig("graveyard_matters")).label
    theirs = spec_for(_sig("graveyard_matters", scope="opponents")).label
    assert yours != theirs
    classes = [_cc(f"Yard {i}", "engine", [yours]) for i in range(12)]
    classes += [_cc(f"Theirs {i}", "engine", [theirs]) for i in range(6)]
    self_payoffs = {f"Yard {i}" for i in range(10)}
    emitters = {
        ("graveyard_matters", "you", ""): frozenset(self_payoffs),
        ("graveyard_matters", "opponents", ""): frozenset({"Theirs 0", "Theirs 1"}),
        ("graveyard_matters", "each", ""): frozenset({"Theirs 2"}),
    }
    signals = [
        _sig("graveyard_matters"),
        _sig("graveyard_matters", scope="opponents"),
        # The doer sibling opens the same opponents' avenue: its payoff key
        # splits by scope, so the self-mill payoffs stay out of it too.
        _sig("graveyard_makers", scope="opponents"),
    ]
    fr = focus(classes, deck_size=100, deck_signals=signals, emitters=emitters)
    rows = {a["label"]: a for a in fr["viable_avenues"] + fr["emerging"] + fr["fed"]}
    assert set(rows[theirs]["carer_cards"]) == {"Theirs 0", "Theirs 1", "Theirs 2"}
    assert set(rows[yours]["carer_cards"]) == self_payoffs | {"Theirs 2"}


def test_a_token_maker_is_no_carer_of_the_artifacts_avenue():
    """``artifacts_matter|you|token`` marks an artifact-TOKEN maker (Thopters,
    Servos): it feeds the Artifacts avenue's depth but does not care about it, so
    the carer read skips that doer subject even when the deck's signals carry it."""
    label = spec_for(_sig("artifacts_matter")).label
    classes = [_cc(f"Art {i}", "engine", [label]) for i in range(12)]
    payoffs = {"Art 0", "Art 1", "Art 2", "Art 3", "Art 4"}
    makers = {f"Art {i}" for i in range(5, 12)}
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[
            _sig("artifacts_matter"),
            _sig("artifacts_matter", subject="token"),
        ],
        emitters={
            ("artifacts_matter", "you", ""): frozenset(payoffs),
            ("artifacts_matter", "you", "token"): frozenset(makers),
        },
    )
    rows = {a["label"]: a for a in fr["viable_avenues"] + fr["emerging"] + fr["fed"]}
    assert set(rows[label]["carer_cards"]) == payoffs


def test_a_doer_subject_is_one_keys_not_every_keys():
    """``DOER_SUBJECTS`` is ``(key, subject)`` pairs: ``land_destruction|you|destroy``
    is a one-shot doer, but the same subject on ``mass_land_denial`` (Armageddon)
    cares about the avenue it opens."""
    label = spec_for(_sig("mass_land_denial", "each")).label
    classes = [_cc(f"MLD {i}", "engine", [label]) for i in range(12)]
    wipes = {"MLD 0", "MLD 1", "MLD 2", "MLD 3", "MLD 4"}
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("mass_land_denial", "each", "destroy")],
        emitters={("mass_land_denial", "each", "destroy"): frozenset(wipes)},
    )
    rows = {a["label"]: a for a in fr["viable_avenues"] + fr["emerging"] + fr["fed"]}
    assert set(rows[label]["carer_cards"]) == wipes


def test_an_extra_step_avenue_is_cared_about_by_the_triggers_it_repeats():
    """An extra-upkeep maker opens "Extra upkeeps"; the cards that care are the
    upkeep triggers each added upkeep repeats (``upkeep_triggers``), not the
    makers."""
    from mtg_utils._tuner.metrics import _cares_keys

    assert _cares_keys("extra_upkeep") == ("upkeep_triggers",)
    label = spec_for(_sig("extra_upkeep")).label
    classes = [_cc(f"Step {i}", "engine", [label]) for i in range(12)]
    triggers = {"Step 1", "Step 2", "Step 3", "Step 4", "Step 5"}
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("extra_upkeep"), _sig("upkeep_triggers")],
        emitters={
            ("extra_upkeep", "you", ""): frozenset({"Step 0"}),
            ("upkeep_triggers", "you", ""): frozenset(triggers),
        },
    )
    rows = {a["label"]: a for a in fr["viable_avenues"] + fr["emerging"] + fr["fed"]}
    assert set(rows[label]["carer_cards"]) == triggers


def test_a_subject_its_serve_leaves_out_opens_no_avenue():
    """An avenue is opened only by a subject its own serve counts
    (``avenue_spec_for``): impulse draw (``cast_from_exile|you|impulse``) cares
    about no "Cast-from-exile" avenue, while an Equipment's haste grant
    (Lightning Greaves: ``aura_equip_kw_grant|you|haste``) opens the
    Aura/Equipment keyword grant avenue its serve counts it toward."""
    exile = spec_for(_sig("cast_from_exile")).label
    grants = spec_for(_sig("aura_equip_kw_grant")).label
    classes = [_cc(f"Exile {i}", "engine", [exile]) for i in range(12)]
    classes += [_cc(f"Gear {i}", "engine", [grants]) for i in range(12)]
    impulse = {f"Exile {i}" for i in range(12)}
    gear = {f"Gear {i}" for i in range(12)}
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[
            _sig("cast_from_exile", subject="impulse"),
            _sig("aura_equip_kw_grant", subject="haste"),
        ],
        emitters={
            ("cast_from_exile", "you", "impulse"): frozenset(impulse),
            ("aura_equip_kw_grant", "you", "haste"): frozenset(gear),
        },
    )
    rows = {a["label"]: a for a in fr["viable_avenues"] + fr["emerging"] + fr["fed"]}
    assert set(rows[grants]["carer_cards"]) == gear
    assert not rows.get(exile, {}).get("carer_cards")


def _fodder_deck():
    """Multiverse Reforged's shape: Jace holds the polymorph lane (wants_fodder)
    and the polymorphs, caring about token fodder, are every carer of "Token
    generators" too (``_CARES_ALIASES``) — two avenues sharing most of the
    smaller one's members (the token spells feed both) and one carer set, but
    short of the 80 % member fold (8 of the 16 makers)."""
    fodder = spec_for(_sig("wants_fodder")).label
    tokens = spec_for(_sig("token_maker")).label
    polymorphs = {"Jace", "Polymorph 0", "Polymorph 1", "Polymorph 2"}
    classes = [_cc("Jace", "commander", [fodder])]
    classes += [_cc(f"Polymorph {i}", "engine", [fodder]) for i in range(3)]
    classes += [_cc(f"Maker {i}", "engine", [fodder, tokens]) for i in range(8)]
    classes += [_cc(f"Maker {i}", "engine", [tokens]) for i in range(8, 16)]
    signals = [_sig("wants_fodder"), _sig("token_maker")]
    emitters = {
        ("wants_fodder", "you", ""): frozenset(polymorphs),
        ("token_maker", "you", ""): frozenset(f"Maker {i}" for i in range(16)),
    }
    return classes, signals, emitters, fodder, tokens


def test_two_avenues_one_carer_set_are_one_theme():
    classes, signals, emitters, fodder, tokens = _fodder_deck()
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        commander_idents=frozenset({("wants_fodder", "you", "")}),
        emitters=emitters,
    )
    viable = [a["label"] for a in fr["viable_avenues"]]
    assert viable == [fodder]
    assert tokens not in [a["label"] for a in fr["emerging"]]


def test_one_carer_set_over_two_pools_stays_two_avenues():
    # Subject-less tokens anthems care about Soldier makers and Spirit makers
    # alike: the same carers, but no card feeds both tribes — two avenues.
    soldiers = spec_for(_sig("token_maker", subject="Soldier")).label
    spirits = spec_for(_sig("token_maker", subject="Spirit")).label
    assert soldiers != spirits
    anthems = {f"Anthem {i}" for i in range(5)}
    classes = [_cc(f"Soldier {i}", "engine", [soldiers]) for i in range(12)]
    classes += [_cc(f"Spirit {i}", "engine", [spirits]) for i in range(12)]
    classes += [_cc(a, "engine", []) for a in sorted(anthems)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[
            _sig("token_maker", subject="Soldier"),
            _sig("token_maker", subject="Spirit"),
        ],
        emitters={
            ("tokens_matter", "you", ""): frozenset(anthems),
            ("token_maker", "you", "Soldier"): frozenset(
                f"Soldier {i}" for i in range(12)
            ),
            ("token_maker", "you", "Spirit"): frozenset(
                f"Spirit {i}" for i in range(12)
            ),
        },
    )
    rows = {a["label"]: a for a in fr["viable_avenues"]}
    assert set(rows) == {soldiers, spirits}
    assert set(rows[soldiers]["carer_cards"]) == set(rows[spirits]["carer_cards"])


def test_a_held_lane_never_folds_into_an_avenue_it_does_not_hold():
    # The same carer set, with the commander holding the SHALLOW lane at
    # emerging depth: the held lane stays the commander's own, even with a
    # deeper non-held avenue kept above it.
    fodder = spec_for(_sig("wants_fodder")).label
    tokens = spec_for(_sig("token_maker")).label
    carers = {"Jace", "Polymorph 0", "Polymorph 1", "Polymorph 2"}
    classes = [_cc("Jace", "commander", [fodder])]
    classes += [_cc(f"Polymorph {i}", "engine", [fodder]) for i in range(3)]
    # Half the held lane's members are token makers (the carer fold's member
    # floor), short of the 80 % member fold.
    classes += [_cc(f"Maker {i}", "engine", [fodder, tokens]) for i in range(4)]
    classes += [_cc(f"Maker {i}", "engine", [tokens]) for i in range(4, 14)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("wants_fodder"), _sig("token_maker")],
        commander_idents=frozenset({("wants_fodder", "you", "")}),
        emitters={("wants_fodder", "you", ""): frozenset(carers)},
    )
    assert fr["commander_avenues"] == []  # held, but under the sub floor
    assert tokens in [a["label"] for a in fr["viable_avenues"]]
    assert fodder in [a["label"] for a in fr["emerging"]]


def _suit_up_deck(commander: str):
    """Virtue and Valor's shape in miniature: 27 Auras serve both Enchantments
    and Voltron, four creatures serve Voltron alone and ten enchantments
    Enchantments alone, so 27 of Voltron's 31 members (87 %) are Enchantments'."""
    ench = spec_for(_sig("enchantments_matter")).label
    voltron = spec_for(_sig("voltron_matters")).label
    lead = replace(_cc(commander, "commander", []), record=test_card(commander))
    classes = [lead]
    classes += [_cc(f"Aura {i}", "engine", [ench, voltron]) for i in range(27)]
    classes += [_cc(f"Bear {i}", "engine", [voltron]) for i in range(4)]
    classes += [_cc(f"Glyph {i}", "engine", [ench]) for i in range(10)]
    signals = [_sig("enchantments_matter"), _sig("voltron_matters")]
    return classes, signals, ench, voltron


def test_the_suit_up_avenue_never_folds_under_a_creature_commander():
    # Its page holds Equipment, which only a creature can wear (CR 301.5) and
    # an Enchantments page never reaches: under Ellivere it stays a theme.
    classes, signals, ench, voltron = _suit_up_deck("Ellivere of the Wild Court")
    fr = focus(classes, deck_size=100, deck_signals=signals)
    assert [a["label"] for a in fr["viable_avenues"]] == [ench, voltron]


def test_the_suit_up_avenue_folds_under_a_noncreature_commander():
    classes, signals, ench, _voltron = _suit_up_deck("Estrid, the Masked")
    fr = focus(classes, deck_size=100, deck_signals=signals)
    assert [a["label"] for a in fr["viable_avenues"]] == [ench]


def test_the_suit_up_avenue_still_folds_into_its_own_sibling():
    # The attach / tutor read serves the same package: one theme, read twice.
    classes, signals, ench, voltron = _suit_up_deck("Ellivere of the Wild Court")
    makers = spec_for(_sig("voltron_makers")).label
    classes = [
        replace(c, served=(*c.served, makers)) if voltron in c.served else c
        for c in classes
    ]
    fr = focus(classes, deck_size=100, deck_signals=[*signals, _sig("voltron_makers")])
    labels = [a["label"] for a in fr["viable_avenues"]]
    assert labels[0] == ench
    assert len(labels) == 2
    assert labels[1] in (voltron, makers)


def test_two_avenues_sharing_one_carer_stay_apart():
    # Sun Titan is the one card caring about recast AND about ETB value: one
    # shared carer is a single card, not a theme read twice.
    recast = spec_for(_sig("permanent_recast")).label
    engine = spec_for(_sig("landfall")).label
    classes = [_cc(f"Recast {i}", "engine", [recast]) for i in range(12)]
    classes += [_cc(f"Engine {i}", "engine", [engine]) for i in range(12)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("permanent_recast"), _sig("landfall")],
        emitters={
            ("permanent_recast", "you", ""): frozenset(
                {"Both Payoff", "Recast 0", "Recast 1", "Recast 2"}
            ),
            ("landfall", "you", ""): frozenset(
                {"Both Payoff", "Engine 0", "Engine 1", "Engine 2"}
            ),
        },
    )
    assert {a["label"] for a in fr["viable_avenues"]} == {recast, engine}
    # Nor does a lone carer, however exactly the two sets match.
    from mtg_utils._tuner.metrics import _same_carers

    assert not _same_carers({"Both Payoff"}, {"Both Payoff"})
    assert _same_carers(
        {"Both Payoff", "Other Payoff"}, {"Both Payoff", "Other Payoff"}
    )


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


def test_the_lane_carers_are_every_held_lanes_carers():
    # The lane cut tier spares the cards caring about the commander's lanes —
    # ALL of them: Saheeli's Energy carers are not plain feeders because
    # Artifacts happens to rank first.
    classes, signals, emitters, _art, _energy = _two_lane_commander()
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        emitters=emitters,
        commander_idents=frozenset(
            {("artifacts_matter", "you", ""), ("energy_matters", "you", "")}
        ),
    )
    assert set(fr["commander_lane_carers"]) == (
        {"Saheeli"}
        | {f"Art {i}" for i in range(10)}
        | {f"Energy {i}" for i in range(10)}
    )
    # No held lane, no lane carers.
    fr = focus(classes, deck_size=100, deck_signals=signals, emitters=emitters)
    assert fr["commander_lane_carers"] == []


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


def test_the_primary_lane_is_a_held_lane_deep_enough_to_show():
    """Bello: his combat-damage read (4 deep, 4 caring) is never reported below
    the sub floor, so it cannot be the primary; the Animation lane (28 deep, one
    carer — Bello himself) is, and the deck has a main."""
    anim = spec_for(_sig("animate_makers", subject="Artifact")).label
    combat = spec_for(_sig("combat_damage_to_opp", scope="opponents")).label
    classes = [_cc("Bello", "commander", [anim, combat])]
    classes += [_cc(f"Rock {i}", "engine", [anim]) for i in range(28)]
    classes += [_cc(f"Hitter {i}", "engine", [combat]) for i in range(4)]
    signals = [
        _sig("animate_makers", subject="Artifact"),
        _sig("combat_damage_to_opp", scope="opponents"),
    ]
    emitters = {
        ("animate_makers", "you", "Artifact"): frozenset({"Bello"}),
        ("combat_damage_to_opp", "opponents", ""): frozenset(
            {"Bello"} | {f"Hitter {i}" for i in range(3)}
        ),
    }
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=signals,
        emitters=emitters,
        commander_idents=frozenset(
            {
                ("animate_makers", "you", "Artifact"),
                ("combat_damage_to_opp", "opponents", ""),
            }
        ),
    )
    assert fr["viable_avenues"][0]["label"] == anim
    assert fr["viable_avenues"][0]["tier"] == "main"
    assert fr["verdict"] == "FOCUSED"


def test_a_main_whose_builders_mostly_care_about_the_primary_is_a_sub():
    """Quick Draw: twelve cards care about "Your graveyard", seven of them
    Spellslinger carers too — the commander's lane seen through the graveyard,
    a sub beside it, not a second direction. The same twelve with two shared
    carers are a direction of their own."""
    spells = spec_for(_sig("spellcast_matters")).label
    yard = spec_for(_sig("graveyard_matters")).label
    classes = [_cc("Stella", "commander", [spells])]
    classes += [_cc(f"Spell {i}", "engine", [spells]) for i in range(40)]
    classes += [_cc(f"Yard {i}", "engine", [yard]) for i in range(22)]
    signals = [_sig("spellcast_matters"), _sig("graveyard_matters")]
    held = frozenset({("spellcast_matters", "you", "")})

    def run(shared: int):
        yard_carers = {f"Spell {i}" for i in range(shared)} | {
            f"Yard {i}" for i in range(12 - shared)
        }
        emitters = {
            ("spellcast_matters", "you", ""): frozenset(
                {"Stella"} | {f"Spell {i}" for i in range(23)}
            ),
            ("graveyard_matters", "you", ""): frozenset(yard_carers),
        }
        fr = focus(
            classes,
            deck_size=100,
            deck_signals=signals,
            emitters=emitters,
            commander_idents=held,
        )
        return fr["verdict"], {a["label"]: a["tier"] for a in fr["viable_avenues"]}

    verdict, tiers = run(shared=7)
    assert tiers[yard] == "sub"
    assert verdict == "FOCUSED"
    verdict, tiers = run(shared=2)
    assert tiers[yard] == "main"
    assert verdict == "SPREAD-THIN"


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


def test_a_carer_of_a_built_avenue_is_never_fed_only():
    # Deep Clue Sea: a token doubler serves only the fed "Token doubling"
    # avenue, but it cares about the Clue lane the deck built — not dead weight.
    clues = spec_for(_sig("clue_makers")).label
    doubling = spec_for(_sig("token_doubling")).label
    classes = [_cc(f"Clue {i}", "engine", [clues]) for i in range(20)]
    classes += [_cc("Doubler", "engine", [doubling])]
    classes += [_cc(f"Copier {i}", "engine", [doubling]) for i in range(10)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[_sig("clue_makers"), _sig("token_doubling")],
        emitters={
            ("clue_matters", "you", ""): frozenset(f"Clue {i}" for i in range(8)),
            ("token_doubling", "you", ""): frozenset({"Doubler"}),
        },
    )
    assert [a["label"] for a in fr["viable_avenues"]] == [clues]
    assert "Doubler" in next(a for a in fr["viable_avenues"])["carer_cards"]
    assert "Doubler" not in fr["fed_only_cards"]
    assert "Copier 0" in fr["fed_only_cards"]


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


def test_a_land_type_lane_counts_its_lands_and_no_other_lane_does():
    """A land-type lane's feeders ARE lands (Yuma's Deserts): they count toward
    its depth, and toward nothing else — a Desert that also serves Landfall is
    still mana base there."""
    desert = _sig(signal_keys.LAND_TYPE_MATTERS, subject="Desert")
    deserts = spec_for(desert).label
    landfall = spec_for(_sig("landfall")).label
    classes = [_cc("Yuma", "commander", [deserts])]
    classes += [_cc(f"Desert {i}", "land", [deserts, landfall]) for i in range(12)]
    classes += [_cc(f"Payoff {i}", "engine", [deserts]) for i in range(2)]
    fr = focus(
        classes,
        deck_size=100,
        deck_signals=[desert, _sig("landfall")],
        commander_idents=frozenset({(signal_keys.LAND_TYPE_MATTERS, "you", "Desert")}),
        emitters={
            (signal_keys.LAND_TYPE_MATTERS, "you", "Desert"): frozenset(
                {"Yuma", "Payoff 0", "Payoff 1"}
            ),
        },
    )
    rows = {a["label"]: a for a in fr["viable_avenues"]}
    assert rows[deserts]["depth"] == 15
    assert "Desert 0" in rows[deserts]["cards"]
    assert landfall not in rows
    assert fr["commander_avenues"] == [deserts]


def test_the_upgrade_slots_are_off_lane_little_played_and_the_deep_lanes_half():
    """Two upgrade-slot reads (2026-10-19, the 25-precon audit): a card off every
    lane the deck holds — no doer of the commander's lanes, no carer of a built
    theme — ranked past ``UPGRADE_RANK`` (half of those were guide cuts); and,
    once the commander's lane holds ``lane_upgrade_floor`` engine doers, its
    least-played half. A premium card is never a lane slot."""
    cheat = spec_for(_sig("cheat_into_play")).label
    lane = [
        replace(_cc(f"Polymorph {i}", "engine", [cheat]), edhrec_rank=1000 * (i + 1))
        for i in range(14)
    ]
    staple = replace(_cc("Premium Polymorph", "engine", [cheat]), edhrec_rank=50)
    off = [
        replace(
            _cc("Played Removal", "spine", [], roles=["interaction"]), edhrec_rank=500
        ),
        replace(
            _cc("Clunky Removal", "spine", [], roles=["interaction"]),
            edhrec_rank=9000,
        ),
        # A Granter is judged by its grant, never by play-rate (ADR-0040 §4).
        replace(_cc("Granter", "engine", []), edhrec_rank=9000, grant_grade="solid"),
    ]
    classes = [_cc("Jace", "commander", [cheat]), *lane, staple, *off]
    emitters = {
        ("cheat_into_play", "you", ""): frozenset(
            {"Jace", staple.name, "Drawing Polymorph"} | {c.name for c in lane}
        )
    }

    def run(cards):
        return focus(
            cards,
            deck_size=100,
            deck_signals=[_sig("cheat_into_play")],
            commander_idents=frozenset({("cheat_into_play", "you", "")}),
            emitters=emitters,
        )

    fr = run(classes)
    assert fr["upgrade_cards"] == ["Clunky Removal"]
    assert fr["lane_upgrade_cards"] == [f"Polymorph {i}" for i in range(13, 6, -1)]
    # The last upgrade slots: off every lane, inside UPGRADE_RANK but not
    # premium, serving none of the deck's viable avenues (2026-10-24).
    assert fr["popular_upgrade_cards"] == ["Played Removal"]
    # A doer that also fills a template role is a lane slot too (its upgrade
    # keeps the role): the least played of fifteen doers, it leads the half.
    drawer = replace(
        _cc("Drawing Polymorph", "spine", [cheat], roles=["card_draw"]),
        edhrec_rank=99000,
    )
    fr = run([*classes, drawer])
    assert fr["lane_upgrade_cards"][0] == "Drawing Polymorph"
    # Below the floor (eleven doers besides the premium one) the lane is whole.
    assert run([*classes[:12], staple, *off])["lane_upgrade_cards"] == []


def test_tied_lanes_resolve_by_label_not_by_set_order():
    """Two commander lanes equally deep with as many carers: the label breaks
    the tie, so the main theme is the same on every run (Death Toll's "Your
    graveyard" / "Graveyard engine" swapped with the string-hash seed until
    2026-10-19). Reversing the card order changes nothing either."""
    classes, signals, emitters, art, energy = _two_lane_commander()
    held = frozenset({("artifacts_matter", "you", ""), ("energy_matters", "you", "")})
    for cards in (classes, classes[::-1]):
        fr = focus(
            cards,
            deck_size=100,
            deck_signals=signals,
            emitters=emitters,
            commander_idents=held,
        )
        assert fr["viable_avenues"][0]["label"] == max(art, energy)
