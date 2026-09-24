"""bump-phase-pin (ADR-0049): the pure pieces, and the orchestration as a dry run
over a fake repo with fake subprocess / HTTP seams."""

from __future__ import annotations

import json
import pickle
import subprocess
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from mtg_utils import _phase, phase_bump
from mtg_utils.phase_bump import (
    STEPS,
    BumpContext,
    KeyDiff,
    graduation_rows,
    impostor_census,
    parse_effect_enum,
    render_variants,
    render_zero_instance,
    rewrite_between_markers,
    rewrite_pin,
    run,
    signal_diff,
)

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


def test_rewrite_pin_counts_occurrences():
    text, n = rewrite_pin('PHASE_TAG = "v0.66.0"  # v0.66.0', "v0.66.0", "v0.70.0")
    assert n == 2
    assert text == 'PHASE_TAG = "v0.70.0"  # v0.70.0'


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


# ── the orchestration, dry-run over a fake repo ────────────────────────────────


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "mtg-utils/src/mtg_utils/_card_ir/mirror").mkdir(parents=True)
    (repo / "tests/fixtures").mkdir(parents=True)
    (repo / "tests/mtg-utils").mkdir(parents=True)
    (repo / phase_bump.PIN_FILE).write_text('PHASE_TAG = "v0.66.0"\n')
    (repo / "CLAUDE.md").write_text("pin (currently v0.66.0) and again v0.66.0\n")
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
        if module == "pytest":
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
    assert "v0.66.0" not in (repo / "CLAUDE.md").read_text()
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
        "pytest",
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
    assert [c[2] for c in calls] == ["pytest"]


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
    assert any("already copied" in n for n in ctx.notes)


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
