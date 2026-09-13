"""bump-phase-pin (ADR-0049): the pure pieces, and the orchestration as a dry run
over a fake repo with fake subprocess / HTTP seams."""

from __future__ import annotations

import json
import pickle
import subprocess
from pathlib import Path

import pytest

from mtg_utils import _phase, phase_bump
from mtg_utils.phase_bump import (
    STEPS,
    BumpContext,
    KeyDiff,
    graduation_rows,
    impostor_census,
    parse_effect_enum,
    regen_crosswalk_fixture,
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


def test_regen_crosswalk_fixture_swaps_records_by_oid_and_name_and_reports_holes():
    fixture = {
        "phase_tag": "v0.66.0",
        "cards": {
            "Sol Ring": _rec("Sol Ring", "oid-ring", "old text"),
            "Gone Card": _rec("Gone Card", "oid-gone", "old"),
        },
        "scryfall_keywords": {"Sol Ring": []},
        "text_only_faces": {"X // Y": {"_text_only_face": {}, "_oracle_id": "o"}},
    }
    card_data = {
        "sol ring": _rec("Sol Ring", "oid-ring", "new text", abilities=[1]),
        "impostor": _rec("Gone Card", "oid-other", "wrong card"),  # oid mismatch
    }
    out, missing = regen_crosswalk_fixture(fixture, card_data, "v0.70.0")
    assert out["phase_tag"] == "v0.70.0"
    assert out["cards"]["Sol Ring"]["oracle_text"] == "new text"
    assert out["cards"]["Gone Card"]["oracle_text"] == "old"  # kept, not dropped
    assert missing == ["Gone Card"]
    assert out["scryfall_keywords"] == fixture["scryfall_keywords"]
    assert out["text_only_faces"] == fixture["text_only_faces"]


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
    names = {"o1": "Sol Ring", "o2": "Mana Vault"}
    diff = signal_diff(old, new, names)
    assert diff == [
        KeyDiff(key="ramp", lost=("Sol Ring",), gained=()),
        KeyDiff(key="lifegain", lost=(), gained=("Sol Ring",)),
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
    (repo / phase_bump.CROSSWALK_FIXTURE).write_text(
        json.dumps(
            {
                "phase_tag": "v0.66.0",
                "cards": {"Sol Ring": _rec("Sol Ring", "oid-ring", "old")},
                "scryfall_keywords": {},
                "text_only_faces": {},
            }
        )
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
                "sol ring": _rec("Sol Ring", "oid-ring", "New text.", abilities=[]),
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
                    "name": "Sol Ring",
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
    # step 5: fixture re-resolved
    fx = json.loads((repo / phase_bump.CROSSWALK_FIXTURE).read_text())
    assert fx["phase_tag"] == "v0.70.0"
    assert fx["cards"]["Sol Ring"]["oracle_text"] == "New text."
    # step 7: builders ran in order, old index copied aside
    modules = [c[2] for c in calls]
    assert modules == [
        "mtg_utils.card_ir_substrate_build",
        "mtg_utils.build_card_snapshot",
        "mtg_utils.card_ir_crosswalk_build",
        "mtg_utils.signals_index_build",
        "pytest",
    ]
    assert (tmp_path / "report" / "signals-v0.66.0.pkl").exists()
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
    run(ctx, from_step=9, echo=lambda _s: None)
    assert (repo / phase_bump.PIN_FILE).read_text() == 'PHASE_TAG = "v0.66.0"\n'
    assert [c[2] for c in calls] == ["pytest"]
