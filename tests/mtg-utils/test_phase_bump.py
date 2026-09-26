"""bump-phase-pin (ADR-0049): the pure pieces, and the orchestration as a dry run
over a fake repo with fake subprocess / HTTP seams."""

from __future__ import annotations

import json
import pickle
import subprocess
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from mtg_utils import _phase, phase_bump
from mtg_utils.phase_bump import (
    STEPS,
    BridgeReach,
    BumpContext,
    CardFacts,
    KeyDiff,
    LossBucket,
    ReportData,
    bridge_reach,
    card_facts,
    classify_loss,
    dead_bridges,
    dead_impostor_rows,
    gain_needs_check,
    graduation_rows,
    impostor_census,
    narrow_gap_breadth,
    parse_effect_enum,
    pinned_by,
    render_bridge_reach,
    render_census,
    render_gains_to_check,
    render_graduation,
    render_needs_verdict,
    render_report,
    render_signal_diff,
    render_variants,
    render_zero_instance,
    rewrite_between_markers,
    rewrite_pin,
    run,
    signal_diff,
    triage,
    wide_gaps,
)

PINNED = LossBucket.PINNED
DROPPED_UPSTREAM = LossBucket.DROPPED_UPSTREAM
VARIANT_CHURN = LossBucket.VARIANT_CHURN
NEEDS_VERDICT = LossBucket.NEEDS_VERDICT

ABILITY_RS = """
pub enum EffectTarget { Single, All }

/// The effect enum.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum Effect {
    // a comment with { braces } inside
    StartYourEngines,
    #[serde(rename_all = "camelCase")]
    DealDamage { amount: Qty, target: Target },
    Draw(u32),
    /// doc { comment }
    Token {
        name: String,
        count: Option<Qty>,
    },
    Unimplemented { name: String, description: String }
}

pub enum Other { A, B }
"""


def test_parse_effect_enum_reads_names_in_order_past_attributes_and_comments():
    assert parse_effect_enum(ABILITY_RS) == (
        "StartYourEngines",
        "DealDamage",
        "Draw",
        "Token",
        "Unimplemented",
    )


def test_parse_effect_enum_matches_the_committed_roster_shape():
    # The committed variants module is itself the generated form of a real
    # ability.rs; the renderer + marker rewrite must round-trip it exactly.
    from mtg_utils._card_ir.mirror import variants

    text = Path(variants.__file__).read_text(encoding="utf-8")
    roster = phase_bump.parse_effect_enum_from_variants(text)
    assert roster == variants.EFFECT_VARIANTS
    rewritten = rewrite_between_markers(
        text,
        phase_bump.VARIANTS_BEGIN,
        phase_bump.VARIANTS_END,
        render_variants(roster),
    )
    assert rewritten == text
    rewritten = rewrite_between_markers(
        text,
        phase_bump.ZERO_BEGIN,
        phase_bump.ZERO_END,
        render_zero_instance(variants.ZERO_INSTANCE_EFFECTS),
    )
    assert rewritten == text


def test_rewrite_pin_rewrites_every_live_site():
    text = (
        'PHASE_TAG: str = "v0.66.0"  # rewritten by `bump-phase-pin`\n'
        'assert _phase.PHASE_TAG == "v0.66.0"\n'
        "pin (currently v0.66.0, governing …) and (currently `v0.66.0`).\n"
    )
    rewritten, n = rewrite_pin(text, "v0.66.0", "v0.70.0")
    assert n == 4
    assert "v0.66.0" not in rewritten


def test_rewrite_pin_keeps_dated_history_mentions():
    """A mention of the old tag that is NOT a live pin site is history
    ("the v0.66.0 pin bump found …") and survives the bump — the blanket
    replace this rule replaced rewrote such comments into falsehoods."""
    history = "# the v0.66.0 pin bump found the cache still at v0.45.0\n"
    text = 'PHASE_TAG: str = "v0.66.0"\n' + history
    rewritten, n = rewrite_pin(text, "v0.66.0", "v0.70.0")
    assert n == 1
    assert rewritten == 'PHASE_TAG: str = "v0.70.0"\n' + history


def test_rewrite_pin_never_matches_a_longer_tag():
    text = 'PHASE_TAG: str = "v0.66.01"\n(currently v0.66.0.)'
    rewritten, n = rewrite_pin(text, "v0.66.0", "v0.70.0")
    assert n == 1
    assert rewritten == 'PHASE_TAG: str = "v0.66.01"\n(currently v0.70.0.)'


def _rec(name, oid, text, **extra):
    return {"name": name, "scryfall_oracle_id": oid, "oracle_text": text, **extra}


def test_impostor_census_flags_text_that_matches_no_bulk_face():
    bulk = [
        {"oracle_id": "oid-a", "name": "Card A", "oracle_text": "Draw a card."},
        {
            "oracle_id": "oid-dfc",
            "name": "Front // Back",
            "card_faces": [
                {"oracle_text": "Front text."},
                {"oracle_text": "Back text."},
            ],
        },
    ]
    card_data = [
        _rec("Card A", "oid-a", "Draw  a card."),  # whitespace/case drift: fine
        _rec("Back", "oid-dfc", "Back text."),  # a face: fine
        _rec("Card A", "oid-a", "Discard a card, then draw two cards."),  # impostor
        _rec("Unknown", "oid-zzz", "whatever"),  # not in bulk: not flagged
    ]
    rows = impostor_census(card_data, bulk)
    assert [(r.oracle_id, r.record_text) for r in rows] == [
        ("oid-a", "Discard a card, then draw two cards.")
    ]
    assert rows[0].bulk_names == ("Card A",)


def test_impostor_census_names_the_card_whose_text_a_record_carries():
    """A flagged record whose text IS another oracle_id's face text is a likely
    impostor (the Fast // Furious mis-join), sorted first and naming that card;
    a text no card carries is errata drift."""
    bulk = [
        {"oracle_id": "oid-legal", "name": "Test Blade", "oracle_text": "Draw two."},
        {
            "oracle_id": "oid-play",
            "name": "Test Blade // Test Sheath",
            "card_faces": [{"oracle_text": "Haste."}, {"oracle_text": "Trample."}],
        },
        {"oracle_id": "oid-drift", "name": "Test Relic", "oracle_text": "Old words."},
    ]
    card_data = [
        _rec("Test Relic", "oid-drift", "New words."),  # retemplated: drift
        _rec("Test Blade", "oid-legal", "Haste."),  # another card's face text
    ]
    rows = impostor_census(card_data, bulk)
    assert [r.record_name for r in rows] == ["Test Blade", "Test Relic"]
    assert rows[0].likely_impostor
    assert rows[0].needs_decision
    assert rows[0].text_owners == ("Test Blade // Test Sheath (oid-play)",)
    assert not rows[1].likely_impostor


def test_impostor_census_marks_an_already_recorded_impostor():
    """A row already in _IMPOSTOR_RECORDS needs no decision: it sorts after a new
    likely impostor and says so, instead of re-asking every bump."""
    bulk = [
        {"oracle_id": "oid-legal", "name": "Test Blade", "oracle_text": "Draw two."},
        {"oracle_id": "oid-play", "name": "Test Sheath", "oracle_text": "Haste."},
        {"oracle_id": "oid-relic", "name": "Test Relic", "oracle_text": "Draw one."},
    ]
    card_data = [
        _rec("Test Blade", "oid-legal", "Haste."),  # known impostor
        _rec("Test Relic", "oid-relic", "Draw two."),  # new impostor
    ]
    rows = impostor_census(card_data, bulk, {("oid-legal", "Haste.")})
    assert [r.record_name for r in rows] == ["Test Relic", "Test Blade"]
    assert rows[0].needs_decision
    assert rows[1].already_recorded
    assert rows[1].likely_impostor
    assert not rows[1].needs_decision
    text = "\n".join(render_census(rows, ()))
    assert "2 LIKELY IMPOSTOR (1 already recorded)" in text
    assert "already in `_IMPOSTOR_RECORDS` — no decision needed" in text


def test_dead_impostor_rows_reads_the_raw_records():
    card_data = {
        "a": _rec("Test Blade", "oid-legal", "Haste."),
        "b": _rec("Test Relic", "oid-drift", "New words."),
    }
    live = ("oid-legal", "Haste.")
    dead = ("oid-play", "Draw two.")  # the join flipped: no record carries it
    assert dead_impostor_rows(card_data, {live, dead}) == (dead,)


def _facts(oids, *, old: bool, new: bool) -> CardFacts:
    return CardFacts(oracle_ids=oids, in_old_card_data=old, in_new_card_data=new)


def test_card_facts_aggregates_every_oracle_id_under_a_name():
    names = {"o1": "Test Relic", "o2": "Test Variant", "o3": "Test Variant"}
    facts = card_facts(names, {"o1", "o2"}, {"o2"})
    assert facts["Test Relic"] == _facts(("o1",), old=True, new=False)
    assert facts["Test Variant"] == _facts(("o2", "o3"), old=True, new=True)


def test_classify_loss_buckets_in_priority_order():
    pins = {"Test Blade": ("tests/x.py",), "Back Half": ("tests/y.py",)}
    single = _facts(("o1",), old=True, new=True)
    gone = _facts(("o1",), old=True, new=False)
    variants = _facts(("o1", "o2"), old=True, new=True)
    # a pin wins over every other fact, and a face name pins the whole card
    assert classify_loss("Test Blade", gone, pins) == PINNED
    assert classify_loss("Front Half // Back Half", single, pins) == PINNED
    assert pinned_by("Front Half // Back Half", pins) == ("tests/y.py",)
    assert classify_loss("Test Relic", gone, pins) == DROPPED_UPSTREAM
    # variant churn only when the signal MOVED: the name also gained the key
    assert classify_loss("Test Relic", variants, pins, {"Test Relic"}) == VARIANT_CHURN
    assert classify_loss("Test Relic", variants, pins) == NEEDS_VERDICT
    # a single card losing and gaining one key is a scope change, not churn
    assert classify_loss("Test Relic", single, pins, {"Test Relic"}) == NEEDS_VERDICT
    assert classify_loss("Test Relic", None, pins) == NEEDS_VERDICT


def test_gain_needs_check_on_every_card_parsed_at_both_tags():
    n = "Test Relic"
    assert gain_needs_check(n, _facts(("o1",), old=True, new=True))
    newly = _facts(("o1",), old=False, new=True)
    assert not gain_needs_check(n, newly)
    variants = _facts(("o1", "o2"), old=True, new=True)
    assert not gain_needs_check(n, variants, {n})  # moved between variants
    assert gain_needs_check(n, variants)  # a variant gain nothing lost: check it
    assert not gain_needs_check(n, None)


class _Tree:
    def __init__(self, name: str, *, residue: bool, says: bool) -> None:
        self.name, self.residue, self.says = name, residue, says


class _Row:
    def __init__(self, gap, match) -> None:
        self.gap, self.match = gap, match


def test_bridge_reach_counts_fires_and_gap_only_cards():
    trees = [
        _Tree("Test Pin", residue=True, says=True),
        _Tree("Test Near Miss", residue=True, says=False),
        _Tree("Test Plain", residue=False, says=False),
    ]
    rows = {
        "narrow_row": _Row(lambda t: t.residue, lambda t: t.says),
        "dead_row": _Row(lambda t: t.residue, lambda _t: False),
    }
    reach = bridge_reach(rows, trees)
    assert reach == [
        BridgeReach("narrow_row", 1, 2, ("Test Near Miss",)),
        BridgeReach("dead_row", 0, 2, ("Test Pin", "Test Near Miss")),
    ]
    assert dead_bridges(reach) == ("dead_row",)


def test_narrow_gap_breadth_skips_absence_gaps():
    """A gap true on most of the corpus gates on the ABSENCE of a structure: its
    breadth is by design and never listed; a narrow residue gap is."""
    narrow = BridgeReach("narrow_row", 1, 3, ("Test Near Miss",))
    universal = BridgeReach("absence_row", 1, 90, ("Test Plain",))
    exact = BridgeReach("exact_row", 2, 2, ())
    assert narrow_gap_breadth([universal, exact, narrow], corpus=100) == [narrow]
    # a wide (absence-read) gap is never sampled but always summarised
    assert wide_gaps([universal, exact, narrow], corpus=100) == [universal]
    lines = render_bridge_reach([universal, exact, narrow], 100)
    assert "  - absence_row: gap 90, fires 1" in lines


def test_render_report_asks_for_a_verdict_on_every_unexplained_loss():
    facts = {
        "Test Relic": _facts(("o1",), old=True, new=True),
        "A-Test Relic": _facts(("o2",), old=True, new=False),
        "Test Blade": _facts(("o3",), old=True, new=True),
    }
    text = render_report(
        ReportData(
            old_tag="v0.1.0",
            new_tag="v0.2.0",
            variants_before=1,
            variants_after=1,
            diff=(
                KeyDiff(
                    "ramp",
                    lost=("A-Test Relic", "Test Blade", "Test Relic"),
                    gained=("Test Relic",),
                ),
            ),
            residue_backed={"ramp": ("Test Relic",)},
            dead_impostors=(("oid-x", "Old text."),),
            facts=facts,
            pins={"Test Blade": ("tests/x.py",)},
            reach=(BridgeReach("dead_row", 0, 0, ()),),
            corpus=10,
        )
    )
    assert "- lost (dropped upstream): 1" in text
    assert "A-Test Relic" not in text.split("## Needs a verdict")[1]
    verdicts = text.split("## Needs a verdict")[1].split("## Gains to check")[0]
    assert f"- [{PINNED.label}] ramp: Test Blade" in verdicts
    assert f"- [{NEEDS_VERDICT.label}, residue-backed] ramp: Test Relic" in verdicts
    assert "- ramp: Test Relic" in text.split("## Gains to check")[1]
    assert "DEAD `_IMPOSTOR_RECORDS` row: `oid-x`" in text
    assert "- DEAD — fires on no card: dead_row" in text


def test_triage_classifies_each_card_once_per_key():
    facts = {
        "Test Variant": _facts(("o1", "o2"), old=True, new=True),
        "Test Lone Variant": _facts(("o3", "o4"), old=True, new=True),
    }
    [t] = triage(
        [
            KeyDiff(
                "ramp",
                lost=("Test Lone Variant", "Test Variant"),
                gained=("Test Variant",),
            )
        ],
        {},
        facts,
        {},
    )
    assert t.collapsed[VARIANT_CHURN] == ("Test Variant",)
    assert [v.card for v in t.verdicts] == ["Test Lone Variant"]
    assert t.gains == (("Test Variant", False),)


def test_section_renderers_say_none_when_empty():
    assert render_census((), ())[1:] == [
        "- none flagged",
        "- every `_IMPOSTOR_RECORDS` row still matches a record",
    ]
    assert render_needs_verdict([])[-1] == "- none"
    assert render_gains_to_check([])[-1] == "- none"
    assert render_graduation(())[-1].startswith("- none")
    assert render_bridge_reach((), 0) == []
    assert render_signal_diff([])[1].startswith("- 0 losses / 0 gains")


def test_signal_diff_is_per_key_over_shared_oracle_ids():
    old = {"o1": ("ramp|you|", "draw|you|"), "o2": ("ramp|you|",), "gone": ("x|you|",)}
    new = {
        "o1": ("draw|you|", "lifegain|you|"),
        "o2": ("ramp|you|",),
        "new": ("y|you|",),
    }
    names = {"o1": "Test Relic", "o2": "Mana Vault"}
    diff = signal_diff(old, new, names)
    assert diff == [
        KeyDiff(key="ramp", lost=("Test Relic",), gained=()),
        KeyDiff(key="lifegain", lost=(), gained=("Test Relic",)),
    ]


def test_graduation_rows_reads_retire_ready_bridge_ids():
    out = """
FAILED tests/x.py::test_bridge_still_needed_and_serving[zuko_modal:Zuko] - AssertionError: zuko_modal_unconditional_paylife: RETIRE-READY — the typed
AssertionError: withercrown_unless_lose_life: RETIRE-READY — the typed substrate
E   other_bridge: pattern rot — the gap still holds
"""
    assert graduation_rows(out) == (
        "withercrown_unless_lose_life",
        "zuko_modal_unconditional_paylife",
    )


def test_graduation_rows_reads_a_retirement_canary_name():
    """A canary names its workaround, not a bridge id — the leading underscore
    and the ``AssertionError:`` prefix must not truncate or shift the name."""
    out = (
        "FAILED tests/mtg-utils/test_crosswalk.py::test_generator_servant_split_"
        "rider_canary - AssertionError: _grants_only_to_self: RETIRE-READY — phase\n"
        "E       AssertionError: _grants_only_to_self: RETIRE-READY — phase no\n"
    )
    assert graduation_rows(out) == ("_grants_only_to_self",)


def test_the_canary_marker_selects_the_generator_servant_canary():
    """The marker the graduation step selects by is registered and applied — a
    renamed marker would silently select nothing and hide every canary."""
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(root / phase_bump.CANARY_TESTS),
            "-m",
            phase_bump.CANARY_MARKER,
            "--collect-only",
            "-q",
            "--strict-markers",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "test_generator_servant_split_rider_canary" in proc.stdout, proc.stdout


# ── the orchestration, dry-run over a fake repo ────────────────────────────────


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "mtg-utils/src/mtg_utils/_card_ir/mirror").mkdir(parents=True)
    (repo / "tests/fixtures").mkdir(parents=True)
    (repo / "tests/mtg-utils").mkdir(parents=True)
    (repo / phase_bump.PIN_FILE).write_text('PHASE_TAG = "v0.66.0"\n')
    (repo / "CLAUDE.md").write_text(
        "pin (currently v0.66.0); the v0.66.0 bump found a stale cache\n"
    )
    (repo / "tests/mtg-utils/test_phase_wrapper.py").write_text(
        'assert _phase.PHASE_TAG == "v0.66.0"\n'
    )
    (repo / phase_bump.VARIANTS_FILE).write_text(
        "# header\n"
        f"{phase_bump.VARIANTS_BEGIN}\n"
        'EFFECT_VARIANTS: tuple[str, ...] = (\n    "Old",\n)\n'
        f"{phase_bump.VARIANTS_END}\n\n"
        f"{phase_bump.ZERO_BEGIN}\n"
        'ZERO_INSTANCE_EFFECTS: frozenset[str] = frozenset(\n    {\n        "Old",\n    }\n)\n'
        f"{phase_bump.ZERO_END}\n"
    )
    (repo / phase_bump.BRIDGE_LEDGER_TEST).write_text("")
    return repo


def test_dry_run_executes_every_step_in_order_and_writes_the_report(
    tmp_path, monkeypatch
):
    repo = _fake_repo(tmp_path)
    card_data = tmp_path / "card-data-v0.70.0.json"
    card_data.write_text(
        json.dumps(
            {
                "test relic": _rec("Test Relic", "oid-ring", "New text.", abilities=[]),
                "fake": _rec("Fast", "oid-ring", "Wrong card text."),  # impostor
            }
        )
    )
    bulk = tmp_path / "bulk.json"  # a Scryfall-shaped list, not an MTGJSON file
    bulk.write_text(
        json.dumps(
            [
                {
                    "oracle_id": "oid-ring",
                    "name": "Test Relic",
                    "oracle_text": "New text.",
                    "layout": "normal",
                }
            ]
        )
    )
    pkl = bulk.with_name(bulk.name + ".signals.pkl")
    pkl.write_bytes(pickle.dumps({"version": 1, "index": {"oid-ring": ("ramp|you|",)}}))
    population = repo / phase_bump.POPULATION_FIXTURE

    calls: list[list[str]] = []

    def runner(argv):
        calls.append(list(argv))
        module = argv[2] if len(argv) > 2 else ""
        if module == "mtg_utils.card_ir_substrate_build":
            population.write_text(
                json.dumps({"population": {"StartYourEngines": 3, "Draw": 0}})
            )
        if module == "mtg_utils.signals_index_build":
            pkl.write_bytes(
                pickle.dumps({"version": 1, "index": {"oid-ring": ("draw|you|",)}})
            )
        stdout = ""
        if module == "pytest" and "-m" in argv[3:]:  # the retirement canaries
            stdout = (
                "FAILED tests/mtg-utils/test_crosswalk.py::test_x_canary - "
                "AssertionError: _grants_only_to_self: RETIRE-READY — phase no\n"
            )
        elif module == "pytest":  # the ledger file
            stdout = "E  degavolver_kicker_paylife_regen: RETIRE-READY — the typed\n"
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return ABILITY_RS.encode()

    monkeypatch.setattr(_phase, "PHASE_TAG", "v0.66.0")
    ctx = BumpContext(
        repo=repo,
        old_tag="v0.66.0",
        new_tag="v0.70.0",
        report_dir=tmp_path / "report",
        runner=runner,
        fetch=fetch,
        card_data_path=lambda: card_data,
        bulk_path=bulk,
    )
    echoed: list[str] = []
    report = run(ctx, echo=echoed.append)

    assert [e.split("] ", 1)[1] for e in echoed] == [name for name, _ in STEPS]
    # step 1: every pin mention rewritten, and this process's own pin moved
    assert (repo / phase_bump.PIN_FILE).read_text() == 'PHASE_TAG = "v0.70.0"\n'
    # …only at the live sites: the dated history mention survives
    assert (repo / "CLAUDE.md").read_text() == (
        "pin (currently v0.70.0); the v0.66.0 bump found a stale cache\n"
    )
    assert _phase.PHASE_TAG == "v0.70.0"
    # step 2: roster from ability.rs at the new tag
    assert fetched == [f"{phase_bump.PHASE_RAW}/v0.70.0/{phase_bump.ABILITY_RS}"]
    variants = (repo / phase_bump.VARIANTS_FILE).read_text()
    assert '"DealDamage",\n' in variants
    assert '"Old"' not in variants
    # step 4: zero-instance from the population zeros (Draw has 0; unseen = 0)
    assert '"Draw",\n' in variants.split(phase_bump.ZERO_BEGIN)[1]
    assert '"StartYourEngines"' not in variants.split(phase_bump.ZERO_BEGIN)[1]
    # step 6: builders ran in order, old index copied aside
    modules = [c[2] for c in calls]
    assert modules == [
        "mtg_utils.card_ir_substrate_build",
        "mtg_utils.build_card_snapshot",
        "mtg_utils.card_ir_crosswalk_build",
        "mtg_utils.signals_index_build",
        "pytest",  # step 8: the ledger file
        "pytest",  # step 8: the retirement canaries
    ]
    assert (tmp_path / "report" / "signals-v0.66.0.pkl").exists()
    # the old tag is recorded before step 1 rewrites the pin, for --from-step
    assert phase_bump.resume_old_tag(tmp_path / "report") == "v0.66.0"
    # the report carries the census, the diff and the graduation list
    text = report.read_text()
    assert "Wrong card text." in text
    assert "### ramp  (lost 1, gained 0)" in text
    assert "### draw  (lost 0, gained 1)" in text
    assert "- degavolver_kicker_paylife_regen" in text
    # step 8 runs the ledger file, then the marker-selected canaries, and both
    # runs' RETIRE-READY names land in the graduation list
    pytest_runs = [c for c in calls if c[1:3] == ["-m", "pytest"]]
    assert pytest_runs[-2][-1] == str(repo / phase_bump.BRIDGE_LEDGER_TEST)
    assert pytest_runs[-1][-3:] == [
        str(repo / phase_bump.CANARY_TESTS),
        "-m",
        phase_bump.CANARY_MARKER,
    ]
    assert "- _grants_only_to_self" in text
    # the triage sections: every loss bucketed, the reach pass over the corpus
    assert "## Needs a verdict" in text
    assert "## Gains to check" in text
    assert "## Bridge reach" in text
    # the fake card-data carries none of the real table's rows: each reads DEAD
    assert "DEAD `_IMPOSTOR_RECORDS` row" in text


def test_from_step_skips_earlier_steps(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(_phase, "PHASE_TAG", "v0.66.0")
    calls: list[list[str]] = []
    ctx = BumpContext(
        repo=repo,
        old_tag="v0.66.0",
        new_tag="v0.70.0",
        report_dir=tmp_path / "report",
        runner=lambda argv: (
            calls.append(list(argv)),
            subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
        )[1],
        fetch=lambda _url: pytest.fail("step 2 must not run"),
        card_data_path=lambda: pytest.fail("step 3 must not run"),
        bulk_path=None,
    )
    run(ctx, from_step=8, echo=lambda _s: None)
    assert (repo / phase_bump.PIN_FILE).read_text() == 'PHASE_TAG = "v0.66.0"\n'
    assert [c[2] for c in calls] == ["pytest", "pytest"]  # ledger + canaries


def test_rebuild_resume_keeps_the_first_runs_pre_bump_index(tmp_path):
    # --from-step 6 after a failure: the on-disk index is already rebuilt, so the
    # copy the first run took must survive or the signal diff compares new to new.
    repo = _fake_repo(tmp_path)
    bulk = tmp_path / "bulk.json"
    bulk.write_text("[]")
    pkl = bulk.with_name(bulk.name + ".signals.pkl")
    pkl.write_bytes(pickle.dumps({"version": 1, "index": {"oid": ("draw|you|",)}}))
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    old_copy = report_dir / "signals-v0.66.0.pkl"
    old_copy.write_bytes(pickle.dumps({"version": 1, "index": {"oid": ("ramp|you|",)}}))
    ctx = BumpContext(
        repo=repo,
        old_tag="v0.66.0",
        new_tag="v0.70.0",
        report_dir=report_dir,
        runner=lambda argv: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
        fetch=lambda _url: b"",
        card_data_path=lambda: tmp_path / "unused",
        bulk_path=bulk,
    )
    phase_bump.step_rebuild(ctx)
    assert pickle.loads(old_copy.read_bytes())["index"] == {"oid": ("ramp|you|",)}
    assert any("already copied" in n for n in ctx.report.notes)


def test_resume_old_tag_without_a_marker_is_an_actionable_error(tmp_path):
    with pytest.raises(click.ClickException, match="no interrupted bump to resume"):
        phase_bump.resume_old_tag(tmp_path / "report")
    (tmp_path / "report").mkdir()
    (tmp_path / "report" / phase_bump.OLD_TAG_MARKER).write_text("\n")
    with pytest.raises(click.ClickException, match="is empty"):
        phase_bump.resume_old_tag(tmp_path / "report")


def test_main_resumes_from_the_marker_not_the_rewritten_pin(tmp_path, monkeypatch):
    # After step 1 the on-disk pin IS the new tag; a resumed process must not take
    # it as the old tag (the signal diff would compare the new index to itself).
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / phase_bump.OLD_TAG_MARKER).write_text("v0.66.0\n")
    monkeypatch.setattr(_phase, "PHASE_TAG", "v0.70.0")
    monkeypatch.setattr(phase_bump, "_default_report_dir", lambda _tag: report_dir)
    monkeypatch.setattr(phase_bump, "_repo_root", lambda: tmp_path)
    seen: dict[str, str] = {}

    def fake_run(ctx, *, from_step, echo):  # noqa: ARG001 — the seam's shape
        seen.update(old=ctx.old_tag, new=ctx.new_tag)
        return report_dir / "report.md"

    monkeypatch.setattr(phase_bump, "run", fake_run)
    result = CliRunner().invoke(phase_bump.main, ["v0.70.0", "--from-step", "8"])
    assert result.exit_code == 0, result.output
    assert seen == {"old": "v0.66.0", "new": "v0.70.0"}


def test_main_refuses_a_bump_to_the_current_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(_phase, "PHASE_TAG", "v0.66.0")
    monkeypatch.setattr(phase_bump, "_default_report_dir", lambda _tag: tmp_path)
    result = CliRunner().invoke(phase_bump.main, ["v0.66.0"])
    assert result.exit_code != 0
    assert "already v0.66.0" in result.output
