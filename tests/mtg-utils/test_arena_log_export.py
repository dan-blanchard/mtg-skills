"""``arena-log-export`` (ADR-0067): synthetic logs with fictional identifiers, a
fake scrubber (no Rust), a fake signal report over ``arena-crosscheck``'s own log
reader (no card data). No real log, no network, no cargo."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from mtg_utils import arena_log_export
from mtg_utils._arena_corpus import corpus as corpus_mod
from mtg_utils._arena_corpus import inherited, naming, redact, scrub, verify
from mtg_utils._arena_corpus.corpus import (
    MANIFEST,
    CommitRefusedError,
    State,
    load_pool,
    save_pool,
)
from mtg_utils._arena_corpus.export import Exporter, export, find_sessions, render
from mtg_utils._arena_corpus.redact import PLACEHOLDER, second_pass
from mtg_utils._arena_corpus.verify import (
    MachineFacts,
    check_fields,
    check_patterns,
    check_terms,
    harvest,
    load_denylist,
    mask,
)
from mtg_utils._arena_crosscheck.log import read_logs

ACCOUNT = "zorblaxuser"  # the archive's account folder (a fictional macOS user)
ME = "Quuxington#24680"  # the login line's handle
NAME = "Quuxington"  # name fields carry the name alone, as Arena's do
OPPONENT = "Fennimore Vex"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaWN0aW9uYWwifQ.c2lnbmF0dXJlZmFrZQ"
OPAQUE = "QX7RT2KD9WLM4BZP8HNC3FJV6Y"  # an account-id-shaped 26-character token
STEAM = "76561190000000042"
MACHINE = MachineFacts(users=(ACCOUNT, "Shared"), hosts=("Glimmerwick-Laptop",))
NOREPLY_ADDR = "12345+fictional@users.noreply.github.com"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _game(match: str) -> str:
    state = {"gameInfo": {"matchID": match, "gameNumber": 1}, "turnInfo": {}}
    event = {"greToClientEvent": {"greToClientMessages": [{"gameStateMessage": state}]}}
    return "[UnityCrossThreadLogger]3/4/2026 7:06:00 PM: Match to X: " + json.dumps(
        event
    )


def _room(event_id: str) -> str:
    room = {
        "matchGameRoomStateChangedEvent": {
            "gameRoomInfo": {
                "gameRoomConfig": {
                    "reservedPlayers": [
                        {
                            "userId": "USERIDFAKE0001",
                            "playerName": NAME,
                            "eventId": event_id,
                        },
                        {
                            "userId": "USERIDFAKE0002",
                            "playerName": OPPONENT,
                            "eventId": event_id,
                        },
                    ]
                }
            }
        }
    }
    return "[UnityCrossThreadLogger]3/4/2026 7:05:59 PM: Match to X: " + json.dumps(
        room
    )


def raw_log(*, startup: str | None = "3/4/2026 7:05:09 PM", events=("Ladder",)) -> str:
    lines = []
    if startup:
        lines.append(f"Startup Timestamp: {startup}")
    lines += [
        f"[Subsystems] Discovering subsystems at path /Users/{ACCOUNT}/Arena/Data",
        f"SteamInternal_SetMinidumpSteamID:  Caching Steam ID:  {STEAM} [API loaded no]",
        f"[Accounts - Login] Logged in successfully. Display Name: {ME}",
        json.dumps(
            {
                "authenticateResponse": {
                    "clientId": "CLIENTFAKE77",
                    "sessionId": "SESSIONFAKE-4242-abcd",
                    "screenName": NAME,
                    "accountId": "ACCTFAKE-9876-5432",
                    "personaId": "PERSONAFAKE-1234",
                    "token": JWT,
                    "email": "quux.ington@example.invalid",
                    "relay": "203.0.113.77",
                    "lan": "192.168.1.20",
                    "Bo": "x",
                },
                "opaque": f"id {OPAQUE} end",
            }
        ),
    ]
    for i, event in enumerate(events):
        lines += [_room(f"{event}_20260301"), _game(f"match-{i}")]
    return "\n".join(lines) + "\n"


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_STAND_INS = {"8": "-0000-4000-8000-000000000000", "9": "-0000-4000-9000-000000000000"}


def _stand_ins(text: str) -> str:
    """Deck and course ids to numbered stand-ins, deck names to Deck-<8hex>."""
    ids: dict[str, str] = {}
    for key, uuid in re.findall(rf'"((?:Deck|Course)Id)":\s*"({_UUID})"', text):
        tail = _STAND_INS["9" if key.startswith("Course") else "8"]
        if not uuid.endswith(tuple(_STAND_INS.values())) and uuid not in ids:
            ids[uuid] = f"{len(ids) + 1:08x}{tail}"
    for uuid, stand_in in ids.items():
        text = text.replace(uuid, stand_in)
    return re.sub(
        r'("DeckId":\s*"([0-9a-f]{8})[^"]*",\s*"Name":\s*")[^"]*', r"\1Deck-\2", text
    )


_FAKE_RULES = {
    "tokens": (r"\b(Token:|Bearer)\s*\S+", r"\1 <redacted>"),
    "match-prefix": (
        r"Match to [A-Z0-9]{20,}:|\b[A-Z0-9]{20,} to Match:",
        "<redacted>:",
    ),
    "names": (r'"(screenName|playerName)":\s*"[^"]+"', r'"\1": "<redacted>"'),
    "ids": (
        r'"(clientId|sessionId|userId|accountId|personaId|token)":\s*"[^"]+"',
        r'"\1": "<redacted>"',
    ),
    "paths": (r"(?:/Users/|/home/|C:\\Users\\)[^/\\\s\"]+(?=[/\\])", "<user-path>"),
    "hardware": (
        r"(?m)^(\s*(?:Renderer:|preferred device:|Using device|deviceModel)) .+",
        r"\1 <redacted>",
    ),
    "emails": (r"[\w.+-]+@[\w.-]+\.\w{2,}", "<email-redacted>"),
    "ipv6": (
        r"\b[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*::[0-9a-f:]*[0-9a-f]\b",
        "<ip-redacted>",
    ),
    "ips": (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<ip-redacted>"),
    "opaque": (r"\b[A-Z0-9]{26}\b", "<redacted>"),
}


def fake_scrub(text: str, *, drop: str | None = None) -> str:
    """A small model of the Manasight scrubber, good enough to pass its self-test
    (it never sees the login line's plain-text name or the Steam ID, as the real
    one doesn't)."""
    if drop != "decks":
        text = _stand_ins(text)
    for name, (pattern, repl) in _FAKE_RULES.items():
        if name != drop:
            text = re.sub(pattern, repl, text)
    return text


def report_of(path: Path) -> dict:
    """A stand-in signal report: the games ``arena-crosscheck``'s reader sees."""
    _res, _trig, games = read_logs([path])
    return {"games": len(games), "ids": games, "resolutions": [], "triggers": []}


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus-clone"
    (root / "corpus").mkdir(parents=True)
    (root / MANIFEST).write_text(
        'corpus_tag = "fake-v1"\n\n[[files]]\n'
        'filename      = "session_2026-01-01_0000.log"\n'
        f'sha256        = "{"0" * 64}"\n'
        "size_bytes    = 1\n"
        'date_captured = "2026-01-01"\n'
    )
    return root


def _archive(tmp_path: Path, *logs: tuple[str, str]) -> Path:
    archive = tmp_path / "archive"
    (archive / ACCOUNT).mkdir(parents=True)
    for name, text in logs:
        (archive / ACCOUNT / name).write_bytes(gzip.compress(text.encode()))
    return archive


def _exporter(tmp_path: Path, scrubber=fake_scrub, **kw) -> Exporter:
    work = tmp_path / "private" / "work"
    work.mkdir(parents=True, exist_ok=True)
    kw.setdefault("signal_report", report_of)
    kw.setdefault("machine", MACHINE)
    return Exporter(scrubber, work, **kw)


def _run(tmp_path, corpus, archive, scrubber=fake_scrub, **kw):
    state = State.load(tmp_path / "private" / "exported.json")
    exporter = _exporter(tmp_path, scrubber, denylist=kw.pop("denylist", ()))
    return export(find_sessions(archive), exporter, corpus, state, **kw), state


ONE = ("20260304T210000-0123456789abcdef.log.gz", raw_log())


# --- the second pass ---------------------------------------------------------


def test_the_login_line_is_kept_with_only_the_name_redacted():
    text, counts = second_pass(
        f"x\nfoo Logged in successfully. Display Name: {ME}\ny\n"
    )
    assert text == f"x\nfoo Logged in successfully. Display Name: {PLACEHOLDER}\ny\n"
    assert sum(counts.values()) == 1


def test_a_handle_anywhere_and_the_steam_id_are_redacted():
    text, _ = second_pass(
        f"a {ME} b; Caching Steam ID:  {STEAM} [API]; again {STEAM}; {OPPONENT}#13579"
    )
    assert ME not in text
    assert STEAM not in text
    assert "Fennimore" not in text  # a name with a space goes whole
    assert text.count(PLACEHOLDER) == 4


# --- the checks -------------------------------------------------------------


def test_the_harvest_reads_every_identifier_class():
    h = harvest(raw_log(), MACHINE)
    kinds = {(t.kind, t.value) for t in h.terms}
    for expected in [
        ("display-name", ME),
        ("name-field", NAME),
        ("name-field", OPPONENT),
        ("id-field", "CLIENTFAKE77"),
        ("id-field", "SESSIONFAKE-4242-abcd"),
        ("id-field", "ACCTFAKE-9876-5432"),
        ("id-field", "PERSONAFAKE-1234"),
        ("id-field", "USERIDFAKE0001"),
        ("token-field", JWT),
        ("email", "quux.ington@example.invalid"),
        ("ip", "203.0.113.77"),
        ("home-user", ACCOUNT),
        ("steam-line", STEAM),
        ("opaque-token", OPAQUE),
        ("host-name", "Glimmerwick-Laptop"),
    ]:
        assert expected in kinds, expected
    assert not any(t.value == "192.168.1.20" for t in h.terms)  # private address
    assert any("'Shared'" in s for s in h.skipped)  # a system folder, listed


def test_a_short_name_is_searched_only_as_a_json_value_or_a_free_text_word():
    h = harvest('"playerName": "Bo"', MachineFacts())
    assert [(t.value, t.quoted) for t in h.terms] == [("Bo", True)]
    assert "searched only as an exact JSON string" in h.skipped[0]
    assert check_terms('{"name":"Bo"}', h.terms, "harvest")
    assert check_terms("GG Bo, well played", h.terms, "harvest")  # a free-text line
    assert not check_terms('{"k": "Bonus"} Bob', h.terms, "harvest")


def test_names_under_six_are_words_and_longer_ones_match_anywhere():
    terms = harvest('"screenName": "Quix" "playerName": "Glimmerwick"').terms
    assert check_terms("hello QUIX.", terms, "harvest")
    assert not check_terms("Quixotic", terms, "harvest")  # 4-5: a whole word only
    assert check_terms("deck GlimmerwickAggro", terms, "harvest")  # 6+: anywhere


@pytest.mark.parametrize(
    ("value", "left"),
    [
        ("Grimbo's", "Grimbo"),  # an apostrophe leaves a piece
        ("The Very Big Bad Wolf", "Wolf"),  # a long name leaves its words
        ("Ren\\u00e9e Quixotl", "Quixotl"),  # an escaped name, its decoded pieces
    ],
)
def test_every_piece_of_a_name_is_searched(value, left):
    h = harvest(f'{{"playerName": "{value}"}}')
    assert check_terms(f"x {left} y", h.terms, "harvest")


def test_short_pieces_are_counted():
    h = harvest('{"playerName": "The Big Bad Wolfgang"}')
    assert h.short == 3  # The, Big, Bad


def test_the_generic_patterns_catch_every_shape():
    text = (
        "Zed_99#12345 a@b.example "
        + JWT
        + r" /Users/someone/x C:\\Users\\someone\\y /home/someone/z "
        + STEAM
    )
    kinds = {f.kind for f in check_patterns(text)}
    assert kinds == {
        "discriminator",
        "email",
        "jwt",
        "mac-home",
        "windows-home",
        "linux-home",
        "steam-id",
    }
    assert not check_patterns("<user-path>/Library <redacted> <email-redacted>")


def test_a_name_field_that_is_not_the_placeholder_fails():
    assert check_fields(r'{"playerName": "<redacted>", "screenName": ""}') == []
    found = check_fields(r"\"ScreenName\":\"Somebody\"")
    assert [(f.kind, f.value) for f in found] == [("name-field", "Somebody")]


def test_mask_shows_two_characters_and_the_length():
    assert mask(ME) == "Qu…(16)"


def test_the_denylist_file(tmp_path):
    path = tmp_path / "denylist.txt"
    path.write_text("#hashtagname\n\nAunt Petunia\n")
    terms = load_denylist(path)
    assert [t.value for t in terms] == ["#hashtagname", "Aunt Petunia"]
    assert check_terms("hi aunt petunia!", terms, "user-denylist")
    assert load_denylist(tmp_path / "missing.txt") == []


# --- each table row is load-bearing -------------------------------------------
#
# Each fixture is caught by its row alone: with the row the check finds it, with
# that one row removed nothing does. A row that stops pulling its weight fails here.

PATTERN_CASES = {
    "discriminator": "tag #54321 end",
    "email": "write g.f@example.invalid now",
    "jwt": "tok eyJhbGc.eyJzdWI.sig",
    "mac-home": "open file:///Users/gfitzw/Library",
    "windows-home": r"Z:\home\gfitzw\.wine",
    "linux-home": "/home/gfitzw/.config",
    "encoded-home": "open %2FUsers%2Fgfitzw",
    "tilde-home": "cache ~gfitzw/Library",
    "volume": "/Volumes/Gerald SSD/x",
    "steam-id": "id 76561190000000042",
    "steam-id3": "id [U:1:12345678]",
    "steam-id2": "id STEAM_0:1:6172839",
    "ipv6": "from 2001:db8:85a3::8a2e:370:7334",
    "bearer": "authorization: bearer abcDEF123456",
    "mdns-host": "host gfitzw-macbook.local",
}
FIELD_CASES = {
    "name-field": '{"opponentName":"Quixotl"}',
    "opponent-name": '{"opponent":{"name":"Quixotl"}}',
    "id-field": '{"accountKey":"qwertyuiopasdfghjklzxcvb12"}',
    "token-field": '{"refresh_token":"wonderfulsunshine"}',
    "deck-id": '{"DeckId":"1b2c3d4e-5f60-4111-8222-123456789abc"}',
    "uuid-key": '{"1b2c3d4e-5f60-4111-8222-123456789abc": 3}',
    "deck-name": (
        '{"DeckId":"00000001-0000-4000-8000-000000000000","Name":"Family Night"}'
    ),
    "deck-description": '{"Description":"for my kids"}',
    "hardware": "Using device Fictional GPU 9000",
}
#: raw text, then the scrubbed text that leaks what only that harvester reads
HARVEST_CASES = {
    "name-field": ('{"playerName":"Quixotl"}', "gg Quixotl"),
    "opponent-name": ('{"opponent":{"name":"Quixotl"}}', "gg Quixotl"),
    "display-name": ("Display Name: Zephyr Quill", "hi Zephyr Quill"),
    "handle": ("vs Quixotl#12345", "gg Quixotl"),
    "id-field": ('{"accountId":"ACCTFAKE-9876"}', "x ACCTFAKE-9876"),
    "token-field": ('{"refresh_token":"wonderfulsunshine"}', "x wonderfulsunshine"),
    "steam-line": ("Caching Steam ID:  12345678", "id 12345678"),
    "steam-id": ("x 76561190000000042", "id 76561190000000042"),
    "email": ("a.b@example.invalid", "a.b@example.invalid"),
    "ip": ("relay 203.0.113.77", "relay 203.0.113.77"),
    "home-user": ("/Users/gfitzwil/Library", "x gfitzwil y"),
    "home-user-line": ("cwd /Users/Gerald Fitzwilliam", "x Fitzwilliam"),
    "jwt": ("tok eyJhbGc.eyJzdWI.sig", "tok eyJhbGc.eyJzdWI.sig"),
    "opaque-token": ("id QX7RT2KD9WLM4BZP8HNC3FJV6Y", "QX7RT2KD9WLM4BZP8HNC3FJV6Y"),
}
#: the scrubbed text each second-pass row must fix (raw, scrubbed)
RULE_CASES = [
    ("Logged in. Display Name: Zephyr Quill", None),
    ("Caching Steam ID:  12345678", None),
    ("pid 76561190000000042", None),
    ("vs Zorblax\u2605#54321 joined", None),
    (r"cwd C:\Users\Gerald Fitzwilliam", "cwd <user-path> Fitzwilliam"),
    ("authorization: bearer abcDEF123456", None),
]


def _without(rows, kind):
    kept = tuple(r for r in rows if r.kind != kind)
    assert len(kept) == len(rows) - 1, kind
    return kept


def test_every_row_has_a_case():
    assert set(PATTERN_CASES) == {r.kind for r in verify.PATTERNS}
    assert set(FIELD_CASES) == {r.kind for r in verify.FIELD_ROWS}
    assert set(HARVEST_CASES) == {r.kind for r in verify.HARVESTERS}
    assert len(RULE_CASES) == len(redact.RULES)


@pytest.mark.parametrize("kind", sorted(PATTERN_CASES))
def test_each_pattern_row_alone_catches_its_case(kind):
    text = PATTERN_CASES[kind]
    assert [f.kind for f in check_patterns(text)] == [kind]
    assert check_patterns(text, _without(verify.PATTERNS, kind)) == []
    assert check_fields(text) == []


@pytest.mark.parametrize("kind", sorted(FIELD_CASES))
def test_each_field_row_alone_catches_its_case(kind):
    text = FIELD_CASES[kind]
    assert [f.kind for f in check_fields(text)] == [kind]
    assert check_fields(text, _without(verify.FIELD_ROWS, kind)) == []
    assert check_patterns(text) == []


@pytest.mark.parametrize("kind", sorted(HARVEST_CASES))
def test_each_harvester_alone_catches_its_case(kind):
    raw, final = HARVEST_CASES[kind]
    assert check_terms(final, harvest(raw).terms, "harvest")
    rest = _without(verify.HARVESTERS, kind)
    assert check_terms(final, harvest(raw, harvesters=rest).terms, "harvest") == []


def _all_findings(raw: str, final: str) -> list:
    return (
        check_terms(final, harvest(raw).terms, "harvest")
        + check_patterns(final)
        + check_fields(final)
    )


@pytest.mark.parametrize("index", range(len(RULE_CASES)))
def test_each_second_pass_row_alone_fixes_its_case(index, monkeypatch):
    raw, scrubbed = RULE_CASES[index]
    scrubbed = scrubbed or raw
    assert _all_findings(raw, second_pass(scrubbed)[0]) == []
    rest = tuple(r for i, r in enumerate(redact.RULES) if i != index)
    monkeypatch.setattr(redact, "RULES", rest)
    assert _all_findings(raw, second_pass(scrubbed)[0])


# --- the scrubber is not trusted ------------------------------------------------


def test_a_do_nothing_scrubber_fails_every_class(tmp_path):
    body = (
        "Startup Timestamp: 1/2/2026 3:04:05 PM\n"
        "Using device Fictional GPU 9000 Ultra\n"
        "deviceModel FictionBook17,3\n"
        '<== {"Summaries":[{"DeckId":"1b2c3d4e-0000-4111-8222-123456789abc",'
        '"Name":"Quixotl Family Night","Description":"for my kids"}]}\n'
        '{"CourseId":"9b2c3d4e-0000-4111-8222-123456789abc"}\n'
        "connected from 2001:db8:85a3::8a2e:370:7334\n"
    )
    archive = _archive(tmp_path, ("20260102T150405-00000000000000aa.log.gz", body))
    (session,) = find_sessions(archive)
    v = _exporter(tmp_path, lambda t: t, signal_report=None).process(session, set())
    assert not v.ok
    kinds = {f.kind for f in v.findings}
    assert {"hardware", "deck-id", "deck-name", "deck-description", "ipv6"} <= kinds
    assert v.staged is None


def test_the_self_test_rejects_a_scrubber_that_does_nothing():
    verify.self_test(fake_scrub)  # the model scrubber passes
    with pytest.raises(verify.SelfTestError, match="self-test"):
        verify.self_test(lambda t: t)
    with pytest.raises(verify.SelfTestError, match="hardware"):
        verify.self_test(lambda t: fake_scrub(t, drop="hardware"))


def test_a_binary_unlike_the_installed_one_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(scrub.shutil, "which", lambda _tool: "/usr/bin/cargo")

    def run(cmd, *, check):
        assert check
        root = Path(cmd[cmd.index("--root") + 1])
        (root / "bin").mkdir(parents=True)
        (root / "bin" / "scrub").write_text("built")

    binary = scrub.install_scrub(run)
    assert binary.with_name("scrub.sha256").is_file()
    assert scrub.is_pinned(binary)
    binary.write_text("tampered")
    assert not scrub.is_pinned(binary)
    with pytest.raises(scrub.ScrubError, match="sha256"):
        scrub.find_scrub()
    assert scrub.find_scrub(binary) == binary  # an explicit --scrub-bin is allowed


# --- the pooled harvest ---------------------------------------------------------


def test_a_name_from_one_session_is_caught_in_another(tmp_path, corpus):
    first = ("20260304T210000-0000000000000001.log.gz", raw_log())
    second = (
        "20260305T210000-0000000000000002.log.gz",
        raw_log(startup="3/5/2026 7:05:09 PM", events=()) + "rematch vs Wobblethorpe\n",
    )
    first = (first[0], first[1] + '{"playerName": "Wobblethorpe"}\n')
    out, _ = _run(tmp_path, corpus, _archive(tmp_path, first, second), dry_run=True)
    assert [v.ok for v in out.verdicts] == [True, False]
    assert [str(f) for f in out.verdicts[1].findings] == [
        f"harvest/name-field {mask('Wobblethorpe')}"
    ]


def test_the_pool_outlives_the_run(tmp_path, corpus, monkeypatch, capsys):
    monkeypatch.setattr(MachineFacts, "read", staticmethod(lambda: MACHINE))
    args = [
        "--corpus",
        str(corpus),
        "--skip-signal-check",
        "--scrub-bin",
        str(_fake_scrub_bin(tmp_path)),
        "--private-dir",
        str(tmp_path / "private"),
    ]
    first = ("20260304T210000-0000000000000001.log.gz", raw_log())
    one = tmp_path / "one"
    (one / ACCOUNT).mkdir(parents=True)
    (one / ACCOUNT / first[0]).write_bytes(
        gzip.compress((first[1] + '{"playerName": "Wobblethorpe"}\n').encode())
    )
    assert arena_log_export.main([*args, "--archive", str(one)]) == 0
    pool = load_pool(tmp_path / "private")
    assert any(t.value == "Wobblethorpe" for t in pool)
    assert (tmp_path / "private" / "harvest.json").stat().st_mode & 0o077 == 0
    later = tmp_path / "later"
    (later / ACCOUNT).mkdir(parents=True)
    (later / ACCOUNT / "20260306T210000-0000000000000003.log.gz").write_bytes(
        gzip.compress(b"Startup Timestamp: 3/6/2026 7:05:09 PM\nvs Wobblethorpe\n")
    )
    assert arena_log_export.main([*args, "--archive", str(later), "--dry-run"]) == 1
    assert f"harvest/name-field {mask('Wobblethorpe')}" in capsys.readouterr().out


# --- the private folder ---------------------------------------------------------


def test_a_private_dir_inside_the_corpus_clone_is_refused(corpus):
    with pytest.raises(SystemExit):
        arena_log_export.main(
            ["--corpus", str(corpus), "--private-dir", str(corpus / "private")]
        )
    assert not (corpus / "private").exists()


def test_the_denylist_in_use_is_named(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(MachineFacts, "read", staticmethod(MachineFacts))
    private = tmp_path / "p"
    private.mkdir()
    (private / "denylist.txt").write_text("Aunt Petunia\n#hashtagname\n")
    empty = tmp_path / "empty"
    empty.mkdir()
    arena_log_export.main(["--verify-only", str(empty), "--private-dir", str(private)])
    assert "(2 term(s))" in capsys.readouterr().err


def test_a_real_name_and_its_pieces_are_harvested():
    h = harvest("", MachineFacts(real_names=("Gerald Fitzwilliam",)))
    assert {t.value for t in h.terms} >= {"Gerald Fitzwilliam", "Gerald", "Fitzwilliam"}


# --- naming ---------------------------------------------------------------


def test_the_name_is_the_local_startup_time_and_the_match_events():
    text = raw_log(events=("Ladder", "CubeDraft_Powered"))
    start = naming.session_start(text, ONE[0])
    assert f"{start:%Y-%m-%d %H:%M}" == "2026-03-04 19:05"
    suffix = naming.suffix_of(naming.match_events(text))
    assert suffix == "_ladder_cubedraft-powered"
    name = naming.unique_name(naming.base_name(start, suffix), set())
    assert name == "session_2026-03-04_1905_ladder_cubedraft-powered.log.gz"
    assert naming.CORPUS_NAME.match(name)


def test_no_startup_line_falls_back_to_the_archive_time_and_no_match_no_suffix():
    text = raw_log(startup=None, events=())
    start = naming.session_start(text, ONE[0])
    assert f"{start:%Y-%m-%d_%H%M}" == "2026-03-04_2100"
    assert naming.suffix_of(naming.match_events(text)) == ""


def test_a_taken_name_gets_a_numeric_suffix():
    taken = {"session_2026-03-04_1905.log.gz", "session_2026-03-04_1905_2.log.gz"}
    assert naming.unique_name("session_2026-03-04_1905", taken) == (
        "session_2026-03-04_1905_3.log.gz"
    )


# --- the pipeline ---------------------------------------------------------


def test_a_clean_session_is_written_with_its_manifest_entry(tmp_path, corpus):
    archive = _archive(tmp_path, ONE)
    out, state = _run(tmp_path, corpus, archive)
    assert [v.ok for v in out.verdicts] == [True]
    (name,) = out.written
    assert name == "session_2026-03-04_1905_ladder.log.gz"
    data = gzip.decompress((corpus / "corpus" / name).read_bytes())
    text = data.decode()
    assert f"Display Name: {PLACEHOLDER}" in text  # the line is kept
    for gone in (ME, "Quuxington", "Fennimore", STEAM, JWT, OPAQUE, ACCOUNT):
        assert gone.lower() not in text.lower()
    assert "match-0" in text  # the game id the cross-check keys on survives
    manifest = (corpus / MANIFEST).read_text()
    assert manifest.endswith(
        "\n\n[[files]]\n"
        f'filename      = "{name.removesuffix(".gz")}"\n'
        f'sha256        = "{hashlib.sha256(data).hexdigest()}"\n'
        f"size_bytes    = {len(data)}\n"
        'date_captured = "2026-03-04"\n'
    )
    assert len(tomllib.loads(manifest)["files"]) == 2
    assert state.exported == {
        f"{ACCOUNT}/{ONE[0]}": {
            "name": name,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    }
    assert (tmp_path / "private" / "exported.json").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "leak",
    [
        NAME,  # a name field's value
        "fennimore vex",  # an opponent's name, another case
        "CLIENTFAKE77",
        "SESSIONFAKE-4242-abcd",
        "ACCTFAKE-9876-5432",
        "PERSONAFAKE-1234",
        "USERIDFAKE0001",
        "quux.ington@example.invalid",
        "203.0.113.77",
        JWT,
        OPAQUE,
        ACCOUNT,  # a home-folder (and local) user name
        "Glimmerwick-Laptop",  # the host name
    ],
)
def test_a_leak_the_scrubber_misses_is_caught_and_not_written(tmp_path, corpus, leak):
    def leaky(text: str) -> str:
        out = fake_scrub(text)
        return out if f"left: {leak}" in out else out + f"left: {leak}\n"

    out, state = _run(tmp_path, corpus, _archive(tmp_path, ONE), leaky)
    (v,) = out.verdicts
    assert not v.ok
    assert "harvest" in v.failed
    assert out.written == []
    assert list((corpus / "corpus").iterdir()) == []
    assert state.exported == {}
    shown = render(out, dry_run=False)
    assert leak.lower() not in shown.lower()  # reported masked
    assert mask(leak).lower() in shown.lower()


@pytest.mark.parametrize("dropped", ["names", "ids", "paths", "emails", "ips"])
def test_a_scrubber_missing_a_whole_class_fails_closed(tmp_path, corpus, dropped):
    out, _ = _run(
        tmp_path,
        corpus,
        _archive(tmp_path, ONE),
        lambda t: fake_scrub(t, drop=dropped),
    )
    assert not out.verdicts[0].ok
    assert out.written == []


def test_a_scrubber_that_breaks_the_games_fails_the_signal_check(tmp_path, corpus):
    def mangles(text: str) -> str:
        return fake_scrub(text).replace('"matchID": "match-0"', '"matchID": "x"')

    out, _ = _run(tmp_path, corpus, _archive(tmp_path, ONE), mangles)
    (v,) = out.verdicts
    assert v.failed == ["signal"]
    assert out.written == []


def test_the_user_denylist_fails_a_file(tmp_path, corpus):
    path = tmp_path / "deny.txt"
    path.write_text("Ladder\n")  # the event name the file keeps
    out, _ = _run(
        tmp_path, corpus, _archive(tmp_path, ONE), denylist=load_denylist(path)
    )
    assert out.verdicts[0].failed == ["user-denylist"]


def test_dry_run_writes_nothing(tmp_path, corpus):
    before = (corpus / MANIFEST).read_bytes()
    out, _ = _run(tmp_path, corpus, _archive(tmp_path, ONE), dry_run=True)
    assert out.verdicts[0].ok
    assert out.written == []
    assert list((corpus / "corpus").iterdir()) == []
    assert (corpus / MANIFEST).read_bytes() == before
    assert not (tmp_path / "private" / "exported.json").exists()


def test_one_failure_writes_nothing_unless_keep_going(tmp_path, corpus):
    bad = ("20260305T210000-fedcba9876543210.log.gz", raw_log(startup=None) + "TRIP\n")

    def scrubber(text: str) -> str:
        return fake_scrub(text).replace("TRIP", "Quuxington")

    archive = _archive(tmp_path, ONE, bad)
    out, _ = _run(tmp_path, corpus, archive, scrubber)
    assert [v.ok for v in out.verdicts] == [True, False]
    assert out.written == []
    out, _ = _run(tmp_path, corpus, archive, scrubber, keep_going=True)
    assert out.written == ["session_2026-03-04_1905_ladder.log.gz"]


def test_the_run_is_incremental_and_a_collision_gets_a_suffix(tmp_path, corpus):
    archive = _archive(tmp_path, ONE)
    (corpus / "corpus" / "session_2026-03-04_1905_ladder.log.gz").write_bytes(b"x")
    out, _ = _run(tmp_path, corpus, archive)
    assert out.written == ["session_2026-03-04_1905_ladder_2.log.gz"]
    again, _ = _run(tmp_path, corpus, archive)
    assert again.verdicts == []
    assert again.already == 1


def test_no_account_name_reaches_the_corpus_or_the_table(tmp_path, corpus):
    out, _ = _run(tmp_path, corpus, _archive(tmp_path, ONE))
    assert out.written
    shown = render(out, dry_run=False)
    assert ACCOUNT not in shown
    assert "0123456789abcdef" not in shown  # nor the archive's own file hash
    for path in (corpus / "corpus").iterdir():
        assert ACCOUNT not in path.name
        assert "0123456789abcdef" not in path.name
    assert ACCOUNT not in (corpus / MANIFEST).read_text()


def test_commit_makes_one_local_commit(tmp_path, corpus, monkeypatch):
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "Test Author")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, NOREPLY_ADDR)
    subprocess.run(["git", "init", "-q", str(corpus)], check=True)
    _git(corpus, "config", "user.email", NOREPLY_ADDR)
    subprocess.run(["git", "-C", str(corpus), "add", "."], check=True)
    subprocess.run(["git", "-C", str(corpus), "commit", "-qm", "base"], check=True)
    out, _ = _run(tmp_path, corpus, _archive(tmp_path, ONE), do_commit=True)
    assert out.commit
    log = subprocess.run(
        ["git", "-C", str(corpus), "log", "-1", "--format=%B", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "session_2026-03-04_1905_ladder" in log
    assert MANIFEST in log


@pytest.mark.parametrize(
    ("config", "env"),
    [
        ("someone@example.invalid", None),  # a personal address in the clone
        (NOREPLY_ADDR, "someone@example.invalid"),  # an environment override
    ],
)
def test_commit_refuses_an_address_that_is_not_no_reply(
    tmp_path, corpus, monkeypatch, config, env
):
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(var, raising=False)
    if env:
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", env)
    subprocess.run(["git", "init", "-q", str(corpus)], check=True)
    _git(corpus, "config", "user.email", config)
    _git(corpus, "config", "user.name", "Test Author")
    with pytest.raises(CommitRefusedError, match=r"config user\.email"):
        _run(tmp_path, corpus, _archive(tmp_path, ONE), do_commit=True)
    assert list((corpus / "corpus").iterdir()) == []  # refused before writing
    assert _git(corpus, "config", "user.email") == config  # never rewritten


# --- the scrubber install and the CLI --------------------------------------


def test_install_builds_the_pinned_scrub_into_the_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(scrub.shutil, "which", lambda _tool: "/usr/bin/cargo")
    calls = []

    def run(cmd, *, check):
        assert check
        calls.append(cmd)
        root = Path(cmd[cmd.index("--root") + 1])
        (root / "bin").mkdir(parents=True)
        (root / "bin" / "scrub").write_text("")

    binary = scrub.install_scrub(run)
    assert binary == tmp_path / "manasight-scrub" / scrub.SCRUB_PIN / "bin" / "scrub"
    assert calls[0][:8] == [
        "cargo",
        "install",
        "manasight-parser",
        "--version",
        scrub.SCRUB_PIN,
        "--features",
        "tailer",
        "--bin",
    ]
    assert "--locked" in calls[0]
    assert scrub.find_scrub() == binary


def test_a_missing_scrub_names_the_install_command(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    with pytest.raises(scrub.ScrubError, match="--install-scrub"):
        scrub.find_scrub()


def _fake_scrub_bin(tmp_path: Path) -> Path:
    script = tmp_path / "bin" / "scrub"
    script.parent.mkdir()
    script.write_text(
        f"#!{sys.executable}\nimport sys\n"
        f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "from test_arena_log_export import fake_scrub\n"
        "sys.stdout.write(fake_scrub(sys.stdin.read()))\n"
    )
    script.chmod(0o755)
    return script


def test_the_cli_dry_run(tmp_path, corpus, monkeypatch, capsys):
    monkeypatch.setattr(MachineFacts, "read", staticmethod(lambda: MACHINE))
    archive = _archive(tmp_path, ONE)
    code = arena_log_export.main(
        [
            "--corpus",
            str(corpus),
            "--archive",
            str(archive),
            "--dry-run",
            "--skip-signal-check",
            "--scrub-bin",
            str(_fake_scrub_bin(tmp_path)),
            "--private-dir",
            str(tmp_path / "private"),
        ]
    )
    captured = capsys.readouterr()
    shown = captured.out
    assert code == 0
    assert "WARNING" in captured.err  # an unpinned --scrub-bin
    assert "denylist: none" in captured.err
    assert "no user denylist: only harvested names are searched" in shown
    assert "session_2026-03-04_1905_ladder.log.gz" in shown
    assert "PASS (7/8)" in shown
    assert "signal check skipped" in shown
    assert list((corpus / "corpus").iterdir()) == []
    assert (tmp_path / "private").stat().st_mode & 0o777 == 0o700


def test_verify_only_reports_masked_findings(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(MachineFacts, "read", staticmethod(MachineFacts))
    published = tmp_path / "published"
    published.mkdir()
    (published / "session_2026-01-01_0000.log.gz").write_bytes(
        gzip.compress(f"Display Name: {ME}\n".encode())
    )
    (published / "session_2026-01-02_0000.log.gz").write_bytes(gzip.compress(b"ok\n"))
    code = arena_log_export.main(
        ["--verify-only", str(published), "--private-dir", str(tmp_path / "p")]
    )
    shown = capsys.readouterr().out
    assert code == 1
    assert ME not in shown
    assert f"patterns/discriminator {mask('#24680')}" in shown
    assert "2 file(s) verified: 1 with findings." in shown


# --- round two: commit signing and identity, Steam forms, the pool, inherited ----

#: A fictional SteamID64 well above any account issued (account 1999999999).
FAR_STEAM = str(verify.STEAM_BASE + 1_999_999_999)


def test_a_steam_id_brings_its_other_spellings():
    h = harvest(f"Caching Steam ID:  {FAR_STEAM} [API]")
    values = {t.value for t in h.terms}
    assert {"1999999999", f"{int(FAR_STEAM):x}", f"{1_999_999_999:x}"} <= values
    assert check_terms("account 1999999999 here", h.terms, "harvest")


@pytest.mark.parametrize(
    ("address", "ok"),
    [
        (NOREPLY_ADDR, True),
        ("personal+@users.noreply.github.com", False),
        ("fictional@users.noreply.github.com", False),
        ("12345+fictional@users.noreply.github.com.example", False),
    ],
)
def test_only_the_id_plus_login_no_reply_shape_is_accepted(address, ok):
    assert bool(corpus_mod.NOREPLY_SHAPE.fullmatch(address)) is ok


def _signing_repo(corpus: Path, tmp_path: Path, monkeypatch) -> Path:
    """A clone set to sign every commit with a fake gpg that leaves a marker."""
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(var, raising=False)
    marker = tmp_path / "gpg-was-run"
    gpg = tmp_path / "fake-gpg"
    gpg.write_text(
        "#!/bin/sh\n"
        f"touch '{marker}'\n"
        "cat > /dev/null\n"
        "echo '[GNUPG:] SIG_CREATED D 1 8 00 1700000000 FAKE' >&2\n"
        "printf -- '-----BEGIN PGP SIGNATURE-----\\n\\nZmFrZQ==\\n"
        "-----END PGP SIGNATURE-----\\n'\n"
    )
    gpg.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(corpus)], check=True)
    for key, value in [
        ("user.email", NOREPLY_ADDR),
        ("user.name", "Test Author"),
        ("commit.gpgsign", "true"),
        ("user.signingkey", "FAKEKEY"),
        ("gpg.program", str(gpg)),
    ]:
        _git(corpus, "config", key, value)
    _git(corpus, "add", ".")
    _git(corpus, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
    return marker


def test_commits_are_never_signed(tmp_path, corpus, monkeypatch):
    marker = _signing_repo(corpus, tmp_path, monkeypatch)
    out, _ = _run(tmp_path, corpus, _archive(tmp_path, ONE), do_commit=True)
    assert out.commit
    assert "gpgsig" not in _git(corpus, "cat-file", "commit", "HEAD")
    assert not marker.exists()  # gpg was never asked


def test_a_signed_commit_is_undone(tmp_path, corpus, monkeypatch):
    marker = _signing_repo(corpus, tmp_path, monkeypatch)
    base = _git(corpus, "rev-parse", "HEAD")
    monkeypatch.setattr(corpus_mod, "UNSIGNED", ())  # as if signing were left on
    with pytest.raises(CommitRefusedError, match="undone"):
        _run(tmp_path, corpus, _archive(tmp_path, ONE), do_commit=True)
    assert marker.exists()
    assert _git(corpus, "rev-parse", "HEAD") == base
    assert MANIFEST in _git(corpus, "diff", "--cached", "--name-only")


def test_verify_only_reads_the_pooled_harvest(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(MachineFacts, "read", staticmethod(MachineFacts))
    private = tmp_path / "p"
    save_pool(private, harvest('{"playerName": "Wobblethorpe"}').terms)
    published = tmp_path / "published"
    published.mkdir()
    (published / "session_2026-01-01_0000.log.gz").write_bytes(
        gzip.compress(b"gg Wobblethorpe\n")
    )
    code = arena_log_export.main(
        ["--verify-only", str(published), "--private-dir", str(private)]
    )
    assert code == 1
    assert f"pool/name-field {mask('Wobblethorpe')}" in capsys.readouterr().out


def _inherited_corpus(corpus: Path, *files: tuple[str, str]) -> None:
    entries = ""
    for name, text in files:
        (corpus / "corpus" / name).write_bytes(gzip.compress(text.encode()))
        entries += (
            "\n[[files]]\n"
            f'filename      = "{name.removesuffix(".gz")}"\n'
            f'sha256        = "{hashlib.sha256(text.encode()).hexdigest()}"\n'
            f"size_bytes    = {len(text.encode())}\n"
            'date_captured = "2026-01-01"\n'
        )
    (corpus / MANIFEST).write_text('corpus_tag = "fake-v1"\n' + entries)


OLD = "session_2026-01-01_0000.log.gz"
CLEAN = "session_2026-01-02_0000.log.gz"
OLD_TEXT = fake_scrub(raw_log()) + "Using device Fictional GPU 9000\n"
CLEAN_TEXT = second_pass(fake_scrub(raw_log(events=("Draft",))))[0]


def _redo(tmp_path, corpus, **kw):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return inherited.resanitize(
        corpus, fake_scrub, work, signal_report=report_of, machine=MACHINE, **kw
    )


def test_resanitize_rewrites_only_what_changes(tmp_path, corpus):
    _inherited_corpus(corpus, (OLD, OLD_TEXT), (CLEAN, CLEAN_TEXT))
    before = {p.name: p.read_bytes() for p in (corpus / "corpus").iterdir()}
    manifest = (corpus / MANIFEST).read_text()
    dry = _redo(tmp_path, corpus, dry_run=True)
    assert [(v.name, v.changed, v.ok) for v in dry.files] == [
        (OLD, True, True),
        (CLEAN, False, True),
    ]
    assert {p.name: p.read_bytes() for p in (corpus / "corpus").iterdir()} == before
    assert (corpus / MANIFEST).read_text() == manifest
    out = _redo(tmp_path, corpus)
    assert out.written == [OLD]
    packed = (corpus / "corpus" / OLD).read_bytes()
    assert packed[3] & 0x08 == 0  # no file name in the gzip header
    assert packed[4:8] == b"\0\0\0\0"  # mtime 0
    data = gzip.decompress(packed)
    assert b"Fictional GPU" not in data
    assert (corpus / "corpus" / CLEAN).read_bytes() == before[CLEAN]
    rows = {
        f["filename"]: f
        for f in tomllib.loads((corpus / MANIFEST).read_text())["files"]
    }
    assert rows[OLD.removesuffix(".gz")]["sha256"] == hashlib.sha256(data).hexdigest()
    assert rows[OLD.removesuffix(".gz")]["size_bytes"] == len(data)
    clean_sha = hashlib.sha256(CLEAN_TEXT.encode()).hexdigest()
    assert rows[CLEAN.removesuffix(".gz")]["sha256"] == clean_sha


def test_resanitize_fails_closed(tmp_path, corpus):
    stuck = "session_2026-01-03_0000.log.gz"
    _inherited_corpus(
        corpus, (OLD, OLD_TEXT), (stuck, "Startup\n/Volumes/Gerald SSD/x\n")
    )
    before = {p.name: p.read_bytes() for p in (corpus / "corpus").iterdir()}
    out = _redo(tmp_path, corpus)
    assert [v.ok for v in out.files] == [True, False]
    assert out.written == []
    assert {p.name: p.read_bytes() for p in (corpus / "corpus").iterdir()} == before
    assert "patterns" in out.files[1].failed


def test_resanitize_commits_once_under_the_commit_rules(tmp_path, corpus, monkeypatch):
    _inherited_corpus(corpus, (OLD, OLD_TEXT), (CLEAN, CLEAN_TEXT))
    marker = _signing_repo(corpus, tmp_path, monkeypatch)
    out = _redo(tmp_path, corpus, do_commit=True)
    assert out.commit
    message = _git(corpus, "log", "-1", "--format=%B")
    assert message.startswith(
        f"Re-sanitize inherited sessions with manasight-parser {scrub.SCRUB_PIN}"
    )
    assert "gpgsig" not in _git(corpus, "cat-file", "commit", "HEAD")
    assert not marker.exists()


def test_the_cli_resanitize_dry_run_shows_progress(
    tmp_path, corpus, monkeypatch, capsys
):
    monkeypatch.setattr(MachineFacts, "read", staticmethod(lambda: MACHINE))
    _inherited_corpus(corpus, (OLD, OLD_TEXT), (CLEAN, CLEAN_TEXT))
    code = arena_log_export.main(
        [
            "--corpus",
            str(corpus),
            "--resanitize-inherited",
            "--dry-run",
            "--skip-signal-check",
            "--scrub-bin",
            str(_fake_scrub_bin(tmp_path)),
            "--private-dir",
            str(tmp_path / "private"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert f"[1/2] {OLD}: changes" in captured.err
    assert f"[2/2] {CLEAN}: unchanged" in captured.err
    assert "2 inherited file(s): 1 change, 2 pass, 0 fail." in captured.out
