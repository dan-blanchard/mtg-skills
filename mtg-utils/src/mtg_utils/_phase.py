"""Wrapper around the phase-rs MTG rules engine.

Phase is invoked as a subprocess. We pin the upstream tag, build once into
a per-user cache, and shell out for every duel/commander run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

PHASE_TAG = "v0.16.0"
PHASE_REPO = "https://github.com/phase-rs/phase"

# card-data.json is byte-identical across platforms, so the linux server
# tarball is the universal source (avoids windows-.zip / mac-intel branching).
PHASE_SERVER_ASSET = "phase-server-linux-x86_64.tar.gz"
# The single member we want out of that tarball.
_CARD_DATA_MEMBER = "data/card-data.json"


class PhaseNotInstalledError(RuntimeError):
    """Raised when the phase binary cannot be located."""


class PhasePrereqError(RuntimeError):
    """Raised when system prereqs (cargo, git) are missing."""


class PhaseRuntimeError(RuntimeError):
    """Raised when phase exits non-zero. ``stderr`` carries the engine output."""

    def __init__(self, message: str, stderr: str) -> None:
        super().__init__(message)
        self.stderr = stderr


def cache_dir() -> Path:
    """Return the phase cache root: ``$MTG_SKILLS_CACHE_DIR/phase``
    or ``$HOME/.cache/mtg-skills/phase``.
    """
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if base:
        return Path(base) / "phase"
    return Path(os.environ["HOME"]) / ".cache" / "mtg-skills" / "phase"


def _repo_dir() -> Path:
    return cache_dir() / "phase.git"


def _release_dir() -> Path:
    return _repo_dir() / "target" / "release"


def find_binary(name: str) -> Path:
    """Locate a phase binary. Honors ``MTG_SKILLS_PHASE_BIN`` for ai-duel.

    For non-default binaries the env override is treated as the directory
    containing them. When the env override is set, the cache path is NOT
    consulted as a fallback — set the env, you're on your own.
    """
    env_override = os.environ.get("MTG_SKILLS_PHASE_BIN")
    if env_override:
        env_path = Path(env_override)
        if env_path.is_dir():
            candidate = env_path / name
        elif env_path.name == name:
            candidate = env_path
        else:
            candidate = env_path.parent / name
        if candidate.exists():
            return candidate
        raise PhaseNotInstalledError(
            f"Phase binary '{name}' not found at {candidate} "
            f"(resolved from MTG_SKILLS_PHASE_BIN={env_override}).\n"
            f"Run `playtest-install-phase` to build phase {PHASE_TAG}, or "
            f"unset MTG_SKILLS_PHASE_BIN to use the default cache path."
        )

    candidate = _release_dir() / name
    if candidate.exists():
        return candidate

    raise PhaseNotInstalledError(
        f"Phase binary '{name}' not found at {candidate}.\n"
        f"Run `playtest-install-phase` to build phase {PHASE_TAG} (~5-10 min)."
    )


def _ensure_prereqs() -> None:
    """Verify cargo and git are on PATH; raise with a clear message otherwise."""
    for tool in ("cargo", "git"):
        if shutil.which(tool) is None:
            raise PhasePrereqError(
                f"`{tool}` not found on PATH. "
                f"Install prereqs: cargo (rustup.rs) and git."
            )


_DUEL_FILES_MARKER = "// matchup-files patch (mtg-skills)"

# The two functions the patch grafts ahead of ai_duel.rs's `fn run_game(`. Plain
# string (Rust braces are literal here — NOT a Python f-string). Imports it needs
# (PlayerDeckList / DeckList / resolve_deck_list / CardDatabase / AiDifficulty /
# PlayerId / Instant) are all already in ai_duel.rs's `use` block.
_DUEL_FILES_FNS = """\
// matchup-files patch (mtg-skills): load two phase-native deck files into a
// 2-player batch, restoring the v0.1.60 --matchup-files affordance v0.8.0 dropped.
fn read_deck_file(path: &std::path::Path) -> (PlayerDeckList, String) {
    let file = std::fs::File::open(path).unwrap_or_else(|e| {
        eprintln!("failed to open deck {}: {e}", path.display());
        std::process::exit(1);
    });
    let v: serde_json::Value = serde_json::from_reader(file).unwrap_or_else(|e| {
        eprintln!("deck {} is not valid JSON: {e}", path.display());
        std::process::exit(1);
    });
    let label = v["name"].as_str().unwrap_or("deck").to_string();
    let mut main_deck: Vec<String> = Vec::new();
    if let Some(arr) = v["main"].as_array() {
        for e in arr {
            let n = e["name"].as_str().unwrap_or("");
            let c = e["count"].as_u64().unwrap_or(1) as usize;
            for _ in 0..c {
                main_deck.push(n.to_string());
            }
        }
    }
    let commander: Vec<String> = v["commander"]
        .as_array()
        .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
        .unwrap_or_default();
    (
        PlayerDeckList {
            main_deck,
            commander,
            ..Default::default()
        },
        label,
    )
}

fn run_matchup_files(
    db: &CardDatabase,
    a_path: &std::path::Path,
    b_path: &std::path::Path,
    batch: Option<usize>,
    base_seed: u64,
    difficulty: AiDifficulty,
    verbose: bool,
) {
    let (a_list, p0_label) = read_deck_file(a_path);
    let (b_list, p1_label) = read_deck_file(b_path);
    let deck_list = DeckList {
        player: a_list,
        opponent: b_list,
        ..Default::default()
    };
    let payload = resolve_deck_list(db, &deck_list);

    let game_count = batch.unwrap_or(1);
    let mut p0_wins: usize = 0;
    let mut p1_wins: usize = 0;
    let mut draws: usize = 0;
    let mut total_turns: u32 = 0;
    let mut total_duration_ms: u128 = 0;
    for game_idx in 0..game_count {
        let game_seed = base_seed + game_idx as u64;
        let start = Instant::now();
        let (winner, turns) = run_game(&payload, game_seed, difficulty, verbose, true);
        let elapsed = start.elapsed().as_millis();
        match winner {
            Some(PlayerId(0)) => p0_wins += 1,
            Some(_) => p1_wins += 1,
            None => draws += 1,
        }
        total_turns += turns;
        total_duration_ms += elapsed;
    }
    let n = game_count.max(1);
    eprintln!("\\nResults ({game_count} games, seed {base_seed}, matchup-files):");
    eprintln!(
        "  P0 ({p0_label}) wins: {p0_wins:>4} ({:.1}%)",
        p0_wins as f64 / n as f64 * 100.0
    );
    eprintln!(
        "  P1 ({p1_label}) wins: {p1_wins:>4} ({:.1}%)",
        p1_wins as f64 / n as f64 * 100.0
    );
    eprintln!(
        "  Draws/aborted:             {draws:>4} ({:.1}%)",
        draws as f64 / n as f64 * 100.0
    );
    eprintln!("  Avg turns: {:.1}", total_turns as f64 / n as f64);
    eprintln!("  Avg duration: {:.0}ms", total_duration_ms as f64 / n as f64);
}

"""


def _apply_duel_files_patch(repo: Path) -> None:
    """Re-add a ``--matchup-files <a> <b>`` flag to the cloned ai-duel binary.

    v0.8.0 ai-duel resolves BOTH decks from a static built-in matchup registry — it
    dropped the v0.1.60 affordance for two arbitrary deck files, so :func:`run_duel`
    (playtest-match / playtest-gauntlet, 1v1) has no runtime custom-deck path. This
    grafts the flag back: it loads two phase-native deck files
    (``{name, main:[{name,count}], commander?}``), resolves them via the engine's
    ``resolve_deck_list``, and runs the existing 2-player batch (printing the same
    stderr summary the built-in matchups do). A local build-time graft, idempotent,
    with asserted anchors so a phase bump fails loudly rather than mis-patching.
    ADR-0028 consume-not-fork: we still consume the release; this is not a phase PR.
    """
    src = repo / "crates" / "phase-ai" / "src" / "bin" / "ai_duel.rs"
    text = src.read_text()
    if _DUEL_FILES_MARKER in text:
        return  # already patched (idempotent)
    edits = [
        # 1. declare the option holding the two deck-file paths
        (
            'let mut matchup = "red-vs-green".to_string();',
            'let mut matchup = "red-vs-green".to_string();\n'
            "    let mut matchup_files: Option<(PathBuf, PathBuf)> = None;  "
            + _DUEL_FILES_MARKER,
        ),
        # 2. parse the flag (two positional values) ahead of the --suite arm
        (
            '"--suite" => mode = Mode::Suite,',
            '"--matchup-files" => {\n'
            "                let a = args_iter.next().cloned().unwrap_or_default();\n"
            "                let b = args_iter.next().cloned().unwrap_or_default();\n"
            "                matchup_files ="
            " Some((PathBuf::from(a), PathBuf::from(b)));\n"
            "            }\n"
            '            "--suite" => mode = Mode::Suite,',
        ),
        # 3. dispatch to the custom runner before the built-in mode match
        (
            "    match mode {\n",
            "    if let Some((ref a, ref b)) = matchup_files {\n"
            "        run_matchup_files("
            "&db, a, b, batch, base_seed, difficulty, verbose);\n"
            "        return;\n"
            "    }\n\n"
            "    match mode {\n",
        ),
        # 4. the runner + deck-file reader, ahead of run_game
        ("fn run_game(", _DUEL_FILES_FNS + "fn run_game("),
    ]
    for anchor, replacement in edits:
        if text.count(anchor) != 1:
            raise PhaseRuntimeError(
                f"ai-duel matchup-files patch anchor not unique/found: {anchor!r}",
                stderr=(
                    f"phase {PHASE_TAG} source drifted; update _apply_duel_files_patch."
                ),
            )
        text = text.replace(anchor, replacement, 1)
    src.write_text(text)


def install_phase() -> None:
    """Clone + ``cargo build`` the phase playtest binaries (ai-duel/ai-commander).

    Binaries-only: the Card IR pipeline no longer needs this. ``card-data.json``
    now comes from :func:`ensure_card_data` (a release-tarball download), so this
    step is required ONLY to actually playtest (``run_duel`` / ``run_commander``).
    We still place that downloaded card-data at the repo path the full
    ``scripts/setup.sh`` would have generated (``client/public/card-data.json``),
    so the binaries find it — whether they read it at runtime or embed it at
    build time — WITHOUT running the heavy setup.sh / gen-card-data toolchain.
    """
    _ensure_prereqs()
    repo = _repo_dir()
    repo.parent.mkdir(parents=True, exist_ok=True)

    if not repo.exists():
        subprocess.run(
            ["git", "clone", "--depth=1", "--branch", PHASE_TAG, PHASE_REPO, str(repo)],
            check=True,
        )

    # Place the release-tarball card-data where phase expects it, BEFORE the
    # cargo build (covers both a runtime read and a build-time embed).
    repo_card_data = repo / "client" / "public" / "card-data.json"
    repo_card_data.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ensure_card_data(), repo_card_data)

    # Graft the --matchup-files flag back into ai-duel so run_duel (1v1
    # playtest-match / playtest-gauntlet) has a runtime custom-deck path.
    _apply_duel_files_patch(repo)

    subprocess.run(
        ["cargo", "build", "--release", "--bin", "ai-duel", "--bin", "ai-commander"],
        cwd=str(repo),
        check=True,
    )

    version_file = cache_dir() / "version.txt"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    version_file.write_text(head + "\n")


DEFAULT_COVERAGE_THRESHOLD = 0.9


def _card_data_path() -> Path:
    """The tag-versioned card-data cache path :func:`ensure_card_data` writes.

    Keyed by ``PHASE_TAG`` so a tag bump auto-refetches and old tags stay
    cached. Decoupled from the cargo build's repo path — building the Card IR
    sidecar needs only this file, fetched from the release tarball.
    """
    return cache_dir() / "card-data" / f"card-data-{PHASE_TAG}.json"


def ensure_card_data() -> Path:
    """Return a local ``card-data.json`` for ``PHASE_TAG``, downloading if absent.

    Returns the tag-versioned cache path (:func:`_card_data_path`). If that file
    already exists it is returned without any network access. Otherwise the LINUX
    phase-server release tarball for ``PHASE_TAG`` is downloaded, ``data/
    card-data.json`` is extracted from it, and written to the cache path
    atomically. Idempotent. No cargo build / no repo clone required.

    Raises ``RuntimeError`` (naming the URL + tag) on any HTTP or extract error.
    """
    dest = _card_data_path()
    if dest.exists():
        return dest

    url = f"{PHASE_REPO}/releases/download/{PHASE_TAG}/{PHASE_SERVER_ASSET}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    # 1) Stream the asset to a temp file (GitHub asset URLs 302 to a CDN;
    #    urllib follows redirects by default).
    request = urllib.request.Request(url, headers={"User-Agent": "mtg-skills/_phase"})
    tmp_tarball = dest.parent / f".{PHASE_SERVER_ASSET}.tmp"
    try:
        with (
            urllib.request.urlopen(request) as resp,
            tmp_tarball.open("wb") as fh,
        ):
            shutil.copyfileobj(resp, fh)
    except (urllib.error.URLError, OSError) as exc:
        tmp_tarball.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to download phase card-data from {url} (tag {PHASE_TAG}): {exc}"
        ) from exc

    # 2) Extract only data/card-data.json and write it atomically.
    try:
        with tarfile.open(tmp_tarball, "r:gz") as tar:
            member = tar.extractfile(_CARD_DATA_MEMBER)
            if member is None:
                raise RuntimeError(
                    f"'{_CARD_DATA_MEMBER}' missing from {url} (tag {PHASE_TAG})."
                )
            payload = member.read()
    except (tarfile.TarError, KeyError, OSError) as exc:
        raise RuntimeError(
            f"Failed to extract '{_CARD_DATA_MEMBER}' from {url} "
            f"(tag {PHASE_TAG}): {exc}"
        ) from exc
    finally:
        tmp_tarball.unlink(missing_ok=True)

    tmp_dest = dest.with_name(dest.name + ".tmp")
    tmp_dest.write_bytes(payload)
    tmp_dest.replace(dest)
    return dest


@lru_cache(maxsize=1)
def load_supported_card_names() -> frozenset[str]:
    """Load the set of card names phase implements, lowercased for case-insensitive
    matching (cached).

    phase v0.1.60 ships ``card-data.json`` as a flat ``{name: record}`` dict (keys
    are phase-normalized, lowercased); older builds used ``{"cards": [{"name": ...}]}``.
    Handle both. We key off each record's proper-case ``name`` and lowercase it here
    (and lowercase the deck side in ``coverage_report``) so both sides use the same
    ``str.lower()`` — reading ``data.get("cards", [])`` against the flat schema
    returned an empty set, silently marking every card unsupported.
    """
    path = ensure_card_data()
    data = json.loads(path.read_text())
    if isinstance(data, dict) and isinstance(data.get("cards"), list):
        raw = [c.get("name", "") for c in data["cards"]]  # legacy {"cards": [...]}
    elif isinstance(data, dict):
        raw = [  # flat {name: record} — prefer the record's proper name, else the key
            rec["name"] if isinstance(rec, dict) and rec.get("name") else key
            for key, rec in data.items()
        ]
    else:
        raw = [c.get("name", "") for c in data]
    return frozenset(n.lower() for n in raw if n)


def coverage_report(
    card_names: list[str],
    *,
    threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> dict:
    """Classify a deck's phase coverage as full / warn / blocked.

    - ``full`` (100% supported): run silently.
    - ``warn`` (>= threshold but < 100%): run with a warning naming missing.
    - ``blocked`` (< threshold): refuse to run.
    """
    supported = load_supported_card_names()
    requested_set = set(card_names)
    # Compare case-insensitively (supported names are lowercased) but keep the
    # original casing in ``missing`` for the user-facing warning.
    missing = sorted(n for n in requested_set if n.lower() not in supported)
    matched = len(requested_set) - len(missing)
    pct = matched / len(requested_set) if requested_set else 1.0

    if not missing:
        status = "full"
    elif pct >= threshold:
        status = "warn"
    else:
        status = "blocked"

    return {
        "status": status,
        "supported_pct": pct,
        "missing": missing,
        "requested": len(requested_set),
        "supported": matched,
    }


def to_phase_deck(deck: dict, *, label: str) -> dict:
    """Convert our deck JSON into phase's ``{name, format, main, commander}``
    shape.

    If ``deck`` is already in phase shape (``main`` present, no ``cards``
    key), return a shallow copy with the requested ``label``. This lets
    callers pass the phase repo's bundled duel decks directly.
    """
    if "main" in deck and "cards" not in deck:
        # Already phase-native; just relabel and pass through.
        out: dict = {
            "name": label,
            "format": deck.get("format") or "modern",
            "main": list(deck["main"]),
        }
        if "commander" in deck:
            out["commander"] = list(deck["commander"])
        return out

    main_entries: dict[str, int] = {}

    def add(name: str, count: int) -> None:
        main_entries[name] = main_entries.get(name, 0) + count

    for entry in deck.get("commanders") or []:
        add(entry["name"], int(entry.get("quantity", 1)))
    for entry in deck.get("cards") or []:
        add(entry["name"], int(entry.get("quantity", 1)))

    payload: dict = {
        "name": label,
        "format": deck.get("format") or "modern",
        "main": [{"name": n, "count": c} for n, c in main_entries.items()],
    }
    commanders = [e["name"] for e in (deck.get("commanders") or [])]
    if commanders:
        payload["commander"] = commanders
    return payload


def run_duel(
    deck_a_path: Path,
    deck_b_path: Path,
    *,
    games: int,
    seed: int | None,
    format_: str,  # noqa: ARG001 — phase infers format from deck JSON; kept for call-site symmetry
    difficulty: str = "Medium",
    timeout_s: int,
) -> dict:
    """Run an ``ai-duel`` batch and return parsed results.

    Returned dict contains: ``wins_p0``, ``wins_p1``, ``draws``,
    ``avg_turns``, ``avg_duration_ms``, ``games``, ``status`` (``ok`` or
    ``timeout``).

    v0.8.0 model: ``ai-duel <data-root> --matchup-files <a> <b> --batch N`` (the
    ``--matchup-files`` flag is re-grafted by :func:`_apply_duel_files_patch` at
    install — stock v0.8.0 only resolves built-in matchups). The batch summary is
    printed to STDERR (no ``--output`` JSON), so we parse it. ``format_`` is unused
    (phase reads the format from the deck JSON), kept for call-site symmetry.
    """
    binary = find_binary("ai-duel")
    data_root = _binary_data_root()
    if not (data_root / "card-data.json").exists():
        raise PhaseNotInstalledError(
            f"phase card-data.json not found at {data_root / 'card-data.json'}. "
            "Run `playtest-install-phase`.",
        )
    cmd = [
        str(binary),
        str(data_root),
        "--matchup-files",
        str(deck_a_path),
        str(deck_b_path),
        "--batch",
        str(games),
        "--difficulty",
        difficulty,
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    try:
        proc = subprocess.run(
            cmd, check=True, timeout=timeout_s, capture_output=True, text=True
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "wins_p0": 0,
            "wins_p1": 0,
            "draws": 0,
            "games": 0,
            "avg_turns": 0.0,
            "avg_duration_ms": 0,
        }
    except subprocess.CalledProcessError as exc:
        raise PhaseRuntimeError(
            f"phase ai-duel exited with code {exc.returncode}",
            stderr=exc.stderr or "",
        ) from exc

    out = proc.stderr or ""  # ai-duel prints the batch summary to stderr

    def _int(pat: str) -> int:
        m = re.search(pat, out)
        return int(m.group(1)) if m else 0

    def _float(pat: str) -> float:
        m = re.search(pat, out)
        return float(m.group(1)) if m else 0.0

    return {
        "status": "ok",
        "wins_p0": _int(r"P0 \(.*?\) wins:\s*(\d+)"),
        "wins_p1": _int(r"P1 \(.*?\) wins:\s*(\d+)"),
        "draws": _int(r"Draws/aborted:\s*(\d+)"),
        "games": games,
        "avg_turns": _float(r"Avg turns:\s*([\d.]+)"),
        "avg_duration_ms": _int(r"Avg duration:\s*(\d+)ms"),
    }


def _binary_data_root() -> Path:
    """Directory the playtest binaries read ``card-data.json`` from.

    v0.8.0 ``ai-duel``/``ai-commander`` take a positional *data-root* and read
    ``<data-root>/card-data.json``. :func:`install_phase` places phase's card-data
    at ``<repo>/client/public/card-data.json`` (the path the full ``setup.sh``
    would have generated), so that directory is the data-root.
    """
    return _repo_dir() / "client" / "public"


def _phase_deck_to_feed_entry(deck: dict) -> dict:
    """Convert a phase-native deck (:func:`to_phase_deck`) into a commander-feed
    entry (``{name, commander, main}``).

    The feed loader keys each seat's commander off ``commander`` (a name array);
    when it's empty it falls back to treating the deck ``name`` as the commander
    card, so a real commander deck MUST carry ``commander``.
    """
    return {
        "name": deck.get("name", "deck"),
        "commander": list(deck.get("commander") or []),
        "main": list(deck.get("main") or []),
    }


# A finished ai-commander game prints "Winner: P<seat>" (or no winner line on a
# draw/abort) plus "Turns played: N" to stdout — v0.8.0 has no --output JSON.
_WINNER_RE = re.compile(r"Winner:\s*P(\d+)")
_TURNS_RE = re.compile(r"Turns played:\s*(\d+)")


def run_commander(
    deck_paths: list[Path],
    *,
    games: int,
    seed: int | None,
    difficulty: str = "Medium",
    timeout_s: int,
) -> dict:
    """Run ``ai-commander`` for a 4-player FFA. Returns per-seat win counts.

    ``deck_paths`` must have length 4 (phase requires 4 seats). Each is a
    phase-native deck JSON (see :func:`to_phase_deck`) carrying a ``commander``.

    v0.8.0 model: ``ai-commander <data-root> --feed <feed.json>`` plays ONE game
    and prints the result to stdout (no ``--decks``/``--games``/``--output``). We
    synthesize a runtime feed from the four decks and invoke once per game (seed
    bumped per game), aggregating the parsed ``Winner: P<seat>`` lines.
    """
    if len(deck_paths) != 4:
        raise ValueError(
            f"ai-commander requires exactly 4 decks, got {len(deck_paths)}",
        )
    binary = find_binary("ai-commander")
    data_root = _binary_data_root()
    if not (data_root / "card-data.json").exists():
        raise PhaseNotInstalledError(
            f"phase card-data.json not found at {data_root / 'card-data.json'}. "
            "Run `playtest-install-phase`.",
        )
    feed = {
        "decks": [
            _phase_deck_to_feed_entry(json.loads(Path(p).read_text()))
            for p in deck_paths
        ]
    }
    winners = [0, 0, 0, 0]
    draws = 0
    turns_total = 0
    completed = 0
    with tempfile.TemporaryDirectory() as td:
        # An absolute --feed path overrides the data-root join (Rust Path::join
        # with an absolute path replaces the base), so the feed lives off-root.
        feed_path = Path(td) / "feed.json"
        feed_path.write_text(json.dumps(feed))
        for g in range(games):
            cmd = [
                str(binary),
                str(data_root),
                "--feed",
                str(feed_path),
                "--difficulty",
                difficulty,
            ]
            if seed is not None:
                cmd += ["--seed", str(seed + g)]
            try:
                proc = subprocess.run(
                    cmd, check=True, timeout=timeout_s, capture_output=True, text=True
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "timeout",
                    "winners_by_seat": [0, 0, 0, 0],
                    "games": 0,
                    "draws": 0,
                    "avg_turns": 0.0,
                }
            except subprocess.CalledProcessError as exc:
                raise PhaseRuntimeError(
                    f"phase ai-commander exited with code {exc.returncode}",
                    stderr=exc.stderr or "",
                ) from exc
            out = proc.stdout or ""
            m = _WINNER_RE.search(out)
            if m and 0 <= int(m.group(1)) < 4:
                winners[int(m.group(1))] += 1
            else:
                draws += 1  # no winner line → draw / abort
            tm = _TURNS_RE.search(out)
            if tm:
                turns_total += int(tm.group(1))
            completed += 1

    return {
        "status": "ok",
        "winners_by_seat": winners,
        "games": completed,
        "draws": draws,
        "avg_turns": (turns_total / completed) if completed else 0.0,
    }
