# Archived Arena logs are published, sanitized, to a fork of the public log corpus

The Arena log archive ADR-0064 keeps (`/Users/Shared/mtg-arena-logs/<account>/`, one
gzipped `Player.log` per session) is a record of what Arena's rules engine did with
real cards, useful to anyone who parses Arena logs. The public
[manasight-corpus](https://github.com/manasight/manasight-corpus) (MIT OR Apache-2.0)
collects such logs, each sanitized by the Manasight scrubber (`manasight-parser`'s
`scrub`, its strictest "corpus" profile), which the corpus's own CI re-runs on every
file it is sent. A log names people: the account's display name, every opponent's,
account and session ids, tokens, home paths.

**The owner's decisions (2026-11-26).** Publish sanitized logs to a fork of the public
corpus. Both household accounts consent, provided identifying information is
scrubbed. Reuse the Manasight scrubber, and make sure it removes nothing the
cross-check needs. The newer client's login line (`Logged in successfully. Display
Name: …`) is kept with only the name redacted, because the event itself is useful to
others. Match ids and draft ids are kept as they are, as the public corpus keeps them
(no pseudonymizing). Local time is accepted in the file name and in the `Startup
Timestamp:` line (no UTC conversion). Commits in the corpus clone are authored with the
owner's GitHub no-reply address, never a personal e-mail.

**Decision.** `arena-log-export` (mtg-utils, `_arena_corpus/`), a developer tool that
reads private data and never runs in CI, like `arena-crosscheck`.

- **The scrubber is pinned and not trusted.** `--install-scrub` runs `cargo install
  manasight-parser --version <SCRUB_PIN> --features tailer --bin scrub --locked` into
  `<cache root>/manasight-scrub/<SCRUB_PIN>/` (pinned at 0.8.1), the way
  `playtest-install-phase` builds phase, and records the binary's sha256 beside it
  (`scrub.sha256`). A run refuses an installed binary whose hash differs, or one with no
  record; a missing binary is an error naming the command; a `scrub` on `PATH` is never
  used. `--scrub-bin` runs another binary with a loud warning. Every run, whichever
  binary, first feeds it a built-in synthetic log (`verify.SELF_TEST_LOG`, fictional
  values, one of each class the scrubber is relied on for) and refuses it unless the
  same checks a real log faces find nothing left. And the verifier assumes nothing of it:
  with a scrubber that changes nothing, every class fails (a test).
- **A second pass for what it misses** (`redact.RULES`, one `(pattern, replacement,
  reason)` row per gap), each replaced by the scrubber's own placeholder `<redacted>`,
  the line kept: the login line's display name; Steam's minidump line (`Caching Steam
  ID: <SteamID64>`), found while building this — the Manasight scrubber keeps it; any
  SteamID64; any handle-shaped `Name#12345`, an emoji or apostrophe in the name included
  (an Arena name can hold spaces, so up to four words before it go too); the rest of a
  line after a bare `<user-path>` (the scrubber stops a bare home path at the first space
  of a user name like `First Last`); a lowercase `bearer` token.
- **Fail closed.** A file that fails any check is never written; by default nothing is
  written unless every selected session passes (`--keep-going` writes the rest and
  exits 0). The checks, each a table of one row per class (`verify`), every row with a
  test that fails when that row alone is removed:
  - *harvest* (`HARVESTERS`): every identifier stated in the raw text of every session
    in the run — name fields of any spelling (`screenName`, `opponentName`, `player_name`,
    a `name` inside an opponent / player / friend / user object, escaped or not, `\uXXXX`
    decoded), the login line's name, handles, id / key / token fields, the Steam line
    and SteamID64s (with the 32-bit account id and the hex of both), emails, non-local IPv4 addresses, home-folder and volume user names
    (to the end of the line for a bare path), JWTs, 26+ character opaque tokens (no
    lowercase run longer than four letters; lowercase hex is read as a content hash and
    listed) — plus every identifier of every session exported before (the pooled
    harvest, below), plus this machine's user names, host names and each account's
    macOS RealName (`dscl`), read at run time. A name is searched case-insensitively, as
    a whole word under six characters and anywhere at six or more (a name glued into a
    longer word), and so is every piece of it of at least four characters (split on
    spaces and punctuation). A name under four characters is searched only as an exact
    JSON string value (`"Bo"`) and, case-sensitively as a whole word, in lines with no
    JSON; anywhere else it relies on the scrubber's field redaction. Shorter pieces are
    not searched; the table counts them (`short`) and every skip is listed, masked;
  - *patterns*: no `#12345` discriminator (whatever comes before it; `\u0023` and `%23`
    spellings included), email, JWT, home path (`/Users/…` and `file:///Users/…`,
    `C:\Users\…`, Wine's `Z:\home\…`, `/home/…`, `%2FUsers%2F`, `~user/`), disk name
    (`/Volumes/<name>`, macOS system volumes excepted), Steam id (SteamID64, `[U:1:n]`,
    `STEAM_0:x:y`), IPv6 address, bearer token or `<host>.local` name anywhere;
  - *fields*: every value under a name, id / key, or token label holds the placeholder;
    every deck and course id (folder ids aside, as the scrubber keeps them) and every
    id used as an object key is one of the scrubber's stand-ins; every deck `Name` is its
    `Deck-<8hex>` pseudonym; every deck `Description` a localization key; every GPU /
    device-model / OS / CPU line the placeholder;
  - *user-denylist*: none of the terms in the private folder's `denylist.txt` (optional;
    every non-blank line is a term, so a term may start with `#`; the run prints which
    file is in use and how many terms, or that there is none);
  - *signal*: `arena-crosscheck`'s report (its Python API) on the raw log equals its
    report on the scrubbed one — the games, every resolution and every trigger row
    (`--skip-signal-check` only as an explicit flag);
  - *rescrub*: the scrubber leaves the final file unchanged, so the corpus's CI finds it
    clean rather than rewriting it; *size*: at most 10 MiB gzipped (the corpus's limit);
    *name*: the corpus's naming rule, and never the account folder's name.
- **The pooled harvest is kept in the clear, privately.** Every identifier harvested
  from a session is pooled with the rest of the run and, once a run writes, saved in
  the private folder (`harvest.json`, mode 600 in the mode-700 folder), so a later
  run's sessions are checked against names only earlier sessions stated. In the clear,
  not hashed: the piece and substring searches need the values (a salted hash could
  match only whole tokens), and the archive beside it holds the raw logs in the clear.
- **Names say only what the log says.** `session_YYYY-MM-DD_HHMM[_suffix].log.gz`: the
  session's start in local time (its `Startup Timestamp:` line, the corpus's own
  convention of the process start; else the archive file's timestamp, which is the
  session's end), and as the suffix the Arena events its matches were played in, read
  off each match room's `reservedPlayers[].eventId` (`Ladder`,
  `CubeDraft_Powered_20261020` → `_ladder`, `_cubedraft-powered`; at most three, then
  `_more`). That is the log's own record, not a guess at a deck or a format; a session
  with no match has no suffix. Never the account folder, a handle, or the archive's
  file hash. A taken name gets `_2`, `_3`, ….
- **State and staging stay private.** The archive-file → exported-name map
  (`exported.json`, which names the account), the pooled harvest, the denylist and
  staging live in `~/mtg/arena-log-corpus/private/` (`--private-dir`), mode 700; a private
  folder inside the corpus clone is refused. Nothing derived from a real log is written
  in the repo.
- **The corpus's manifest format.** Each file is added to `smoke-corpus-manifest.toml`
  as the corpus records it: the file name without `.gz`, and the sha256 and size of the
  uncompressed scrubbed log, `date_captured` the session's start date. A file whose
  sha256 the manifest already holds is reported and not written. `sessions.md` is not
  edited: its sections need the Manasight parser's coverage counts and the player's own
  notes, which the maintainer's `harvest-log` command gathers.
- **Never pushes; commits are unsigned and only as the no-reply address.** `--commit`
  makes one local commit in the corpus clone (the named files and the manifest only).
  It refuses, before anything is written, unless the clone's `user.email` and the
  author and committer git would actually use (environment overrides included) all have
  the shape `<id>+<login>@users.noreply.github.com` and nothing else, and it prints the
  identity (`user.name`, the owner's public GitHub name by his decision, is shown, not
  checked); it never writes git config. The tool's own rule: every commit runs with
  `-c commit.gpgsign=false -c tag.gpgsign=false`, because a signature would tie the
  corpus to a key whose identity (its UIDs) the tool cannot vet. After committing it
  reads the commit object back: a `gpgsig` header, or an author or committer address of
  any other shape, undoes it (`git reset --soft HEAD~1`) and fails. Pushing and the pull
  request are a separate, deliberate step. `--dry-run` scrubs and verifies into the
  private temp folder and writes nothing. `--verify-only <dir>` runs the checks that
  need no raw text (patterns, fields, the denylist, this machine's names, and the pooled
  harvest when the private folder has one) over already published files. A missing
  denylist is a note, and the summary says so in one line ("no user denylist: only
  harvested names are searched").
- **Inherited files are re-sanitized once.** The public corpus's files predate parts of
  the scrubber (37 of 38 hold real deck ids and deck names, 7 hold GPU lines; the
  maintainer's own data, already public). `--resanitize-inherited` puts every existing
  `corpus/*.log.gz` through the pinned scrubber and the second pass, then the checks
  that need no raw session (patterns, fields, the denylist, this machine's names; no
  harvest, since no raw text of these sessions exists), the cross-check of old file
  against new (reports identical), the re-scrub and size checks. A file is rewritten
  (gzip mtime 0, no name) only when its content changed, with its manifest `sha256` and
  `size_bytes` (the corpus's own `resanitize-corpus.yml` forgets the manifest); nothing
  is written unless every file passes, as an export. `--commit` makes one commit,
  "Re-sanitize inherited sessions with manasight-parser <PIN>", under the same rules.
  Progress is printed per file.
- **Scans stay linear.** Python's `re` tries a pattern that opens with a character class
  at every position, and a JSON line can be megabytes: the slow rows search a cheap
  literal anchor and match the full pattern only on the bounded line around each hit
  (`scan.Anchored`), and every keyed row reads one shared scan of the text's JSON
  key / value pairs (`verify.Keyed`). The same matches, about ten times faster.

**Consequences.** The first run (2026-11-26, six sessions, both accounts) passed every
check; the cross-check read the same 40 games on raw and scrubbed text. The Manasight
scrubber's gaps on these logs were the login line and the Steam ID; each is now a row.
An adversarial review (2026-11-26) found nothing identifying in the six files, and
synthetic attacks that passed the first verifier now fail it or are redacted. One
shape still passes by construction: a name that appears only in free text (`Welcome
back, Quixotl!`) in a run where no session states it in a field the harvest reads; the
account's own name is in every session's login response, so it is pooled, and the
denylist is the owner's backstop for any other name known in advance. The owner
confirmed on 2026-11-27 that he has no extra term to add: the harvested names and ids,
the machine's account names and their full names are the list, so the tool runs with
no denylist file by design.
