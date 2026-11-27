"""The fail-closed checks a scrubbed log must pass before it is published.

They assume nothing about the scrubber: run with one that changes nothing, a log
with anything in it fails.

* **harvest** (:data:`HARVESTERS`, :func:`harvest`, :func:`check_terms`): every
  identifier read off the raw text of every session in the run, of every session
  ever exported (the pooled harvest, ``corpus.load_pool``), and this machine's user,
  host and real names must be gone. A name is searched case-insensitively, as a
  whole word under :data:`UNBOUNDED_MIN` characters and anywhere at or above it
  (a name glued into a longer word), and so is every piece of it (split on spaces
  and punctuation) of at least :data:`NAME_MIN`. A shorter name is searched only as
  an exact JSON string value (``"Bo"``), case-sensitively; its free-text uses are
  protected only by the scrubber's field redaction. A shorter piece is not searched.
  Every skip is listed and counted, never dropped silently.
* **patterns** (:data:`PATTERNS`): shapes that must not appear at all.
* **fields** (:data:`FIELD_ROWS`): every value under a name, id, token, deck or
  hardware label has the scrubber's placeholder or stand-in shape.
* **user-denylist** (:func:`load_denylist`): the owner's terms, outside the repo.

Each table row is one class, so the next gap is one row. A finding carries the
value it found; anything printed shows it only through :func:`mask`.
"""

from __future__ import annotations

import functools
import ipaddress
import re
import socket
import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from mtg_utils._arena_corpus.redact import PLACEHOLDER
from mtg_utils._arena_corpus.scan import Anchored

__all__ = [
    "FIELD_ROWS",
    "HARVESTERS",
    "NAME_MIN",
    "PATTERNS",
    "UNBOUNDED_MIN",
    "Finding",
    "Harvest",
    "MachineFacts",
    "Row",
    "SelfTestError",
    "Term",
    "check_fields",
    "check_patterns",
    "check_terms",
    "harvest",
    "load_denylist",
    "mask",
    "self_test",
]

#: The shortest name or name piece searched as a word: a shorter one would match
#: ordinary words.
NAME_MIN = 4
#: A name (or piece) this long is searched anywhere, not only as a whole word.
UNBOUNDED_MIN = 6
#: The shortest id-field value searched (shorter ones are flags, not ids).
ID_MIN = 8

#: Home-folder and volume names that are system folders, not people.
NOT_PEOPLE = frozenset(
    {
        "shared",
        "public",
        "guest",
        "default",
        "default user",
        # macOS system volumes (/System/Volumes/<name>)
        "preboot",
        "data",
        "recovery",
        "vm",
        "update",
        "xarts",
        "iscpreboot",
        "hardware",
        "macintosh hd",
    }
)

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
#: A JSON string value at any escaping level, ``\\uXXXX`` escapes included.
_VAL = r'\\*"(?P<val>(?:[^"\\]|\\u[0-9a-fA-F]{4})*)'
_NAME_KEY = (
    r"(?i:\w*(?:screen|player|display|persona|user|opponent|friend|nick|account)"
    r"_?name|nick_?name|nick|handle|gamer_?tag)"
)
_ID_KEY = (
    r"(?i:\w*(?:account|user|persona|client|session|device|steam|install|machine|"
    r"hardware|player)\w*(?:id|key|identifier))"
)


#: Every JSON string value and its key, at any escaping level: one scan a text,
#: shared by every :class:`Keyed` row.
_KV = re.compile(r'"(?P<key>\w+)\\*"\s*:\s*' + _VAL)


@functools.lru_cache(maxsize=4)
def _pairs(text: str) -> tuple[re.Match[str], ...]:
    return tuple(_KV.finditer(text))


class Keyed:
    """The string values under every key ``key`` fully matches."""

    def __init__(self, key: str) -> None:
        self.key = re.compile(key)

    def finditer(self, text: str) -> Iterator[re.Match[str]]:
        return (m for m in _pairs(text) if self.key.fullmatch(m["key"]))


class Row(NamedTuple):
    kind: str
    pattern: re.Pattern[str] | Anchored | Keyed
    #: The shape a ``val`` match must have; ``None``: any match is a finding.
    allowed: re.Pattern[str] | None
    reason: str


_PH = re.compile(rf"{re.escape(PLACEHOLDER)}|")
#: The scrubber's stand-ins: deck ``…-8000-…``, course ``…-9000-…``, and the
#: all-zero "no deck".
STAND_IN = re.compile(
    r"[0-9a-f]{8}-0000-4000-[89]000-000000000000|00000000-0000-0000-0000-000000000000"
)
_HW_LABELS = (
    r"\s+(?:Renderer|Vendor|VRAM|Driver):\s+|\s*preferred device:\s+"
    r"|\s*Metal devices available:\s+|\s*\d+:\s+|\s*Using device\s+"
    r"|\s*Initializing Metal device caps:\s+"
    r"|(?:graphicsDeviceName|graphicsDeviceVendor|graphicsDeviceVersion|deviceModel"
    r"|operatingSystem|processorType) "
)
_IPV6 = (
    r"\B::(?:[0-9a-fA-F]{1,4}:)*(?:(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F]{1,4})\b"
    r"|\b[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4})*::(?:(?:[0-9a-fA-F]{1,4}:)*"
    r"(?:(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F]{1,4})\b|\B)"
    r"|\b(?:[0-9a-fA-F]{1,4}:){3,7}(?:(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F]{1,4})\b"
)
_EMAIL = r"[\w.%+\-]+@[\w.\-]+\.[A-Za-z]{2,}"
_JWT = r"\beyJ[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{2,}"
_STEAM_ID = r"(?<!\d)7656119\d{10}(?!\d)"

#: Shapes that must not appear anywhere in a scrubbed log.
PATTERNS: tuple[Row, ...] = (
    Row(
        "discriminator",
        re.compile(r"(?:#|\\u0023|%23)\d{5}(?!\d)"),
        None,
        "a handle's #12345, whatever comes before it",
    ),
    Row("email", Anchored("@", _EMAIL), None, "an email address"),
    Row("jwt", Anchored("eyJ", _JWT), None, "a JWT"),
    Row(
        "mac-home",
        Anchored("Users", r'\\*/Users\\*/[^/\\"\s<]+'),
        None,
        "/Users/<name>, file URLs included",
    ),
    Row(
        "windows-home",
        re.compile(r'(?i:[a-z]:\\+(?:users|home)\\+)[^\\"\s<]+'),
        None,
        r"C:\Users\<name>, Wine's Z:\home\<name>",
    ),
    Row(
        "linux-home",
        Anchored("home", r'\\*/home\\*/[^/\\"\s<]+'),
        None,
        "/home/<name>",
    ),
    Row("encoded-home", re.compile(r"(?i)%2F(?:Users|home)%2F"), None, "%2FUsers%2F"),
    Row(
        "tilde-home",
        Anchored("~", r"(?<![\w~/])~[A-Za-z][\w.\-]*/"),
        None,
        "~user/ (another user's home)",
    ),
    Row(
        "volume",
        Anchored(
            "/Volumes/",
            r"(?<!/System)/Volumes/"
            r"(?!(?:Preboot|Data|Recovery|VM|Update|xarts|iSCPreboot|Hardware)\b)",
        ),
        None,
        "/Volumes/<name>: a disk's name (macOS system volumes excepted)",
    ),
    Row("steam-id", Anchored("7656119", _STEAM_ID, reach=32), None, "a SteamID64"),
    Row(
        "steam-id3",
        Anchored(r"\[U:", r"\[U:1:\d+\]", reach=32),
        None,
        "a Steam id in [U:1:n] form",
    ),
    Row(
        "steam-id2",
        Anchored("STEAM_", r"\bSTEAM_[0-5]:[01]:\d+", reach=32),
        None,
        "a Steam id in STEAM_0:x:y form",
    ),
    # an address holds "::" or a hex digit after a colon, and is at most 45 long
    Row(
        "ipv6",
        Anchored(":(?=[0-9a-fA-F:])", _IPV6, reach=48),
        None,
        "an IPv6 address",
    ),
    Row(
        "bearer",
        Anchored("(?i)bearer", rf"(?i)\bbearer\s+(?!{re.escape(PLACEHOLDER)})\S{{6,}}"),
        None,
        "a bearer token, any case",
    ),
    Row(
        "mdns-host",
        Anchored(r"\.local\b", r"\b[\w-]+\.local\b"),
        None,
        "a <host>.local name",
    ),
)

#: Values that must have one shape: the scrubber's placeholder or stand-in.
FIELD_ROWS: tuple[Row, ...] = (
    Row(
        "name-field",
        Keyed(_NAME_KEY),
        _PH,
        "a display-name field of any spelling",
    ),
    Row(
        "opponent-name",
        re.compile(
            r'(?i:\\*"(?:opponent|player|friend|user)\w*\\*")\s*:\s*\{[^{}]*?'
            r'\\*"(?P<key>name)\\*"\s*:\s*' + _VAL
        ),
        _PH,
        "a 'name' inside an opponent / player / friend / user object",
    ),
    Row(
        "id-field",
        Keyed(_ID_KEY),
        re.compile(rf"{re.escape(PLACEHOLDER)}|{STAND_IN.pattern}|.{{0,7}}"),
        "an account / user / persona / client / session / device id or key",
    ),
    Row(
        "token-field",
        Keyed(r"(?i:\w*token)"),
        _PH,
        "a token field (TokenId, a cosmetic, ends otherwise)",
    ),
    Row(
        "deck-id",
        Keyed(
            r"(?i:(?:(?!folder)[a-z_])*(?:deck|course)(?:(?!folder)[a-z_])*id[a-z_]*)"
        ),
        re.compile(rf"{STAND_IN.pattern}|(?!{_UUID}$).*"),  # other values are kept
        "a deck or course id (folder ids are kept, as the scrubber keeps them)",
    ),
    Row(
        "uuid-key",
        re.compile(r'\\*"(?P<val>' + _UUID + r')\\*"\s*:'),
        STAND_IN,
        "a deck id used as an object key",
    ),
    Row(
        "deck-name",
        re.compile(
            r'\\*"DeckId(?:Internal)?\\*"\s*:\s*\\*"[0-9a-fA-F-]+\\*",\s*'
            r'(?:\\*"[A-Za-z0-9_]+\\*":(?:\\*"[^"\\]*\\*"|-?[0-9]+|true|false|null),\s*)*'
            r'\\*"Name\\*"\s*:\s*' + _VAL
        ),
        re.compile(r"Deck-[0-9a-fA-F]{8}"),
        "a deck's free-text name: the scrubber's Deck-<8hex> pseudonym",
    ),
    Row(
        "deck-description",
        Keyed("Description"),
        re.compile(r"[\w?=/.\-]*"),
        "a deck description: a localization key, never free text",
    ),
    Row(
        "hardware",
        re.compile(rf"(?m)^(?:{_HW_LABELS})(?P<val>[^\r\n]*)"),
        re.compile(rf"{re.escape(PLACEHOLDER)}(?: \((?:high|low) power\))?\r?"),
        "a GPU / device model / OS / CPU line",
    ),
)


def mask(value: str) -> str:
    """A value as it may be printed: its first two characters and its length."""
    return f"{value[:2]}…({len(value)})"


@dataclass(frozen=True)
class Term:
    """One identifier that must not appear in the scrubbed text."""

    kind: str
    value: str
    #: matched case-insensitively (names)
    fold: bool = False
    #: matched only as a whole word, between non-alphanumerics
    bounded: bool = False
    #: matched only as an exact JSON string value (a name too short for a word)
    quoted: bool = False


@dataclass(frozen=True)
class Finding:
    check: str
    kind: str
    value: str

    def __str__(self) -> str:
        return f"{self.check}/{self.kind} {mask(self.value)}"


def _unescape(value: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), value)


@dataclass
class Harvest:
    terms: list[Term] = field(default_factory=list)
    #: Each identifier not searched, and why (values masked).
    skipped: list[str] = field(default_factory=list)
    #: How many name pieces were too short to search.
    short: int = 0
    _seen: set[tuple] = field(default_factory=set, repr=False)
    _short: set[str] = field(default_factory=set, repr=False)

    def add(self, term: Term) -> None:
        value = term.value.lower() if term.fold else term.value
        key = (term.fold, term.bounded, term.quoted, value)
        if term.value in ("", PLACEHOLDER) or key in self._seen:
            return
        self._seen.add(key)
        self.terms.append(term)

    def merge(self, terms: Iterable[Term]) -> None:
        for t in terms:
            self.add(t)

    def note(self, text: str) -> None:
        if text not in self.skipped:
            self.skipped.append(text)

    def _word(self, kind: str, value: str) -> None:
        if len(value) >= NAME_MIN:
            bounded = len(value) < UNBOUNDED_MIN
            self.add(Term(kind, value, fold=True, bounded=bounded))
        elif value.lower() not in self._short:
            self._short.add(value.lower())
            self.short += 1

    def name(self, kind: str, value: str) -> None:
        """A name, a ``Name#12345`` handle, and every piece of it."""
        for whole in dict.fromkeys((value.strip(), _unescape(value).strip())):
            if not whole or whole == PLACEHOLDER:
                continue
            form = whole
            if "#" in whole:
                self.add(Term(kind, whole, fold=True, bounded=True))
                form = whole.split("#", 1)[0].strip()
            if len(form) < NAME_MIN:
                # too short for a word: only an exact JSON string value
                self.add(Term(kind, form, quoted=True))
                self.note(
                    f"{kind} {mask(form)}: under {NAME_MIN} characters, searched "
                    'only as an exact JSON string ("…") and as a case-sensitive word '
                    "in lines with no JSON; elsewhere it relies on the scrubber's "
                    "field redaction"
                )
            else:
                self._word(kind, form)
            if "\\" in form:
                continue  # the escaped spelling: its pieces come from the decoded one
            for piece in re.split(r"[\W_]+", form):
                if piece and piece.lower() != form.lower():
                    self._word(f"{kind}-piece", piece)

    def ident(self, kind: str, value: str) -> None:
        if len(value) >= ID_MIN:
            self.add(Term(kind, value))
        elif value not in ("", PLACEHOLDER):
            self.note(f"{kind} values under {ID_MIN} characters are not searched")


@dataclass(frozen=True)
class MachineFacts:
    """This machine's user, host and real names, read at run time."""

    users: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    real_names: tuple[str, ...] = ()

    @classmethod
    def read(cls) -> MachineFacts:
        home = Path("/Users")
        users = tuple(
            sorted(
                p.name
                for p in (home.iterdir() if home.is_dir() else ())
                if p.is_dir() and not p.name.startswith(".")
            )
        )
        hosts = {socket.gethostname(), socket.gethostname().split(".")[0]}
        real: list[str] = []
        if sys.platform == "darwin":
            for key in ("ComputerName", "LocalHostName", "HostName"):
                out = _run(["scutil", "--get", key])
                if out:
                    hosts.add(out)
            for user in users:
                out = _run(["dscl", ".", "-read", f"/Users/{user}", "RealName"])
                name = out.split(":", 1)[-1].strip() if out else ""
                if name:
                    real.append(name)
        return cls(users, tuple(sorted(h for h in hosts if h)), tuple(real))


def _run(cmd: list[str]) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


_LOWER_HEX = re.compile(r"[0-9a-f]+")
#: Addresses that name no one outside the machine's own network.
_LOCAL_NETS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/3",
    )
)


def _opaque(word: str) -> bool:
    """A 26+ character word with no structure: an id or a token. Not lowercase
    hex (a content hash), not a run of one or two characters, not an identifier
    with an English word in it (a lowercase run longer than four letters)."""
    return (
        len(set(word)) >= 4
        and sum(c.isdigit() for c in word) >= 2
        and not _LOWER_HEX.fullmatch(word)
        and max((len(r) for r in re.findall(r"[a-z]+", word)), default=0) <= 4
    )


def _take_ip(h: Harvest, kind: str, value: str) -> None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return  # a version number, not an address
    if not any(address in net for net in _LOCAL_NETS):
        h.add(Term(kind, value, bounded=True))


def _take_home(h: Harvest, kind: str, value: str) -> None:
    if value.strip().lower() in NOT_PEOPLE:
        h.note(f"home folder {value.strip()!r}: a system folder, not a person")
    else:
        h.name(kind, value)


def _take_opaque(h: Harvest, kind: str, value: str) -> None:
    if _opaque(value):
        h.add(Term(kind, value))
    elif _LOWER_HEX.fullmatch(value):
        h.note("lowercase-hex runs of 26+ read as content hashes, not searched")


class Harvester(NamedTuple):
    kind: str
    pattern: re.Pattern[str] | Anchored | Keyed
    take: Callable[[Harvest, str, str], None]


def _exact(h: Harvest, kind: str, value: str) -> None:
    h.add(Term(kind, value))


#: SteamID64 = this base + the 32-bit account id (individual accounts, universe 1).
STEAM_BASE = 76561197960265728


def _steam(h: Harvest, kind: str, value: str) -> None:
    """A Steam id, and the other spellings of the same account: the 32-bit
    account id and the hex of both (``[U:1:n]`` / ``STEAM_0:x:y`` are pattern
    rows)."""
    h.add(Term(kind, value))
    account = int(value) - STEAM_BASE
    if account <= 0:
        return  # not an individual account's id
    if len(str(account)) < 6:
        h.note(f"{kind} account id under 6 digits: its 32-bit forms are not searched")
        return
    h.add(Term(f"{kind}-account", str(account), bounded=True))
    h.add(Term(f"{kind}-hex", f"{int(value):x}", fold=True))
    h.add(Term(f"{kind}-hex", f"{account:x}", fold=True, bounded=True))


def _email(h: Harvest, kind: str, value: str) -> None:
    h.add(Term(kind, value, fold=True))


#: Where the raw text states an identifier; each row's group ``val`` is taken.
HARVESTERS: tuple[Harvester, ...] = (
    Harvester("name-field", Keyed(_NAME_KEY), Harvest.name),
    Harvester("opponent-name", FIELD_ROWS[1].pattern, Harvest.name),
    Harvester(
        "display-name",
        re.compile(r"Display Name:[ \t]*(?P<val>[^\r\n]*[^\s])"),
        Harvest.name,
    ),
    Harvester(
        "handle",
        Anchored(r"#\d{5}", r"(?P<val>\w[\w.\-]*(?: [\w.\-]+){0,3}#\d{5})"),
        Harvest.name,
    ),
    Harvester("id-field", Keyed(_ID_KEY), Harvest.ident),
    Harvester("token-field", Keyed(r"(?i:\w*token)"), Harvest.ident),
    Harvester("steam-line", re.compile(r"Steam ID:[ \t]*(?P<val>\d+)"), _steam),
    Harvester(
        "steam-id", Anchored("7656119", rf"(?P<val>{_STEAM_ID})", reach=32), _steam
    ),
    Harvester("email", Anchored("@", rf"(?P<val>{_EMAIL})"), _email),
    Harvester(
        "ip",
        Anchored(
            r"\.\d{1,3}\.\d",
            r"(?<![\d.])(?P<val>(?:\d{1,3}\.){3}\d{1,3})(?![\d.])",
            reach=16,
        ),
        _take_ip,
    ),
    Harvester(
        "home-user",
        re.compile(
            r"(?:\\*/(?:Users|home|Volumes)\\*/|(?i:[a-z]:\\+(?:users|home)\\+))"
            r'(?P<val>[^/\\"\s<>:]+)'
        ),
        _take_home,
    ),
    Harvester(
        "home-user-line",
        re.compile(
            r"(?m)(?:/(?:Users|home|Volumes)/|(?i:[a-z]:\\+(?:users|home)\\+))"
            r'(?P<val>[^/\\"\r\n<>:]*[^/\\"\s<>:])$'
        ),
        _take_home,
    ),
    Harvester(
        "jwt", Anchored("eyJ", rf"(?P<val>{_JWT}[A-Za-z0-9_.\-]*)", reach=65536), _exact
    ),
    Harvester(
        "opaque-token",
        re.compile(r"(?<![A-Za-z0-9])(?P<val>[A-Za-z0-9]{26,})(?![A-Za-z0-9])"),
        _take_opaque,
    ),
)


def harvest(
    raw: str,
    machine: MachineFacts | None = None,
    harvesters: Sequence[Harvester] = HARVESTERS,
) -> Harvest:
    """Every identifier in ``raw`` (:data:`HARVESTERS`), and this machine's names."""
    h = Harvest()
    for row in harvesters:
        for m in row.pattern.finditer(raw):
            row.take(h, row.kind, m["val"])
    machine = machine or MachineFacts()
    for user in machine.users:
        if user.lower() in NOT_PEOPLE:
            h.note(f"local user {user!r}: a system folder, not a person")
        else:
            h.name("local-user", user)
    for host in machine.hosts:
        if "." in host:  # a full host name: whole, not its domain's pieces
            h.add(Term("host-name", host, fold=True, bounded=True))
        else:
            h.name("host-name", host)
    for name in machine.real_names:
        h.name("real-name", name)
    return h


def _occurs(hay: str, needle: str, *, bounded: bool) -> bool:
    start = hay.find(needle)
    while start != -1:
        end = start + len(needle)
        if not bounded or (
            (start == 0 or not hay[start - 1].isalnum())
            and (end == len(hay) or not hay[end].isalnum())
        ):
            return True
        start = hay.find(needle, start + 1)
    return False


def _free_text(text: str) -> str:
    """The lines that hold no JSON: Unity's and the client's own messages."""
    return "\n".join(
        line for line in text.splitlines() if "{" not in line and '"' not in line
    )


#: A maximal run of letters and digits.
_RUN = re.compile(r"[^\W_]+")


@functools.lru_cache(maxsize=2)
def _vocabulary(lowered: str) -> str:
    """Every distinct letter-and-digit run of ``lowered``, one a line."""
    return "\n".join(set(_RUN.findall(lowered)))


def _may_occur(lowered: str, value: str) -> bool:
    """False only when ``value`` cannot occur in the text: some run of it is in
    no run of the text. (Each run of an occurrence lies inside a run of the
    text.) Not used for non-ASCII values, whose lowercasing can depend on
    context."""
    if not value.isascii():
        return True
    vocabulary = _vocabulary(lowered)
    return all(run in vocabulary for run in _RUN.findall(value.lower()))


def check_terms(text: str, terms: Iterable[Term], check: str) -> list[Finding]:
    """The terms that occur in ``text``. A ``quoted`` (short) name is looked for
    as an exact JSON string value and, case-sensitively as a whole word, in the
    lines that hold no JSON. A term none of whose runs the text holds is ruled
    out from the text's vocabulary before any search of the text itself."""
    lowered: str | None = None
    free: str | None = None
    out = []
    for t in terms:
        lowered = text.lower() if lowered is None else lowered
        if not _may_occur(lowered, t.value):
            continue
        if t.quoted:
            free = _free_text(text) if free is None else free
            hit = any(f"{q}{t.value}{q}" in text for q in ('"', '\\"')) or _occurs(
                free, t.value, bounded=True
            )
        elif t.fold:
            hit = _occurs(lowered, t.value.lower(), bounded=t.bounded)
        else:
            hit = _occurs(text, t.value, bounded=t.bounded)
        if hit:
            out.append(Finding(check, t.kind, t.value))
    return out


def check_patterns(
    text: str, rows: Sequence[Row] = PATTERNS, *, limit: int = 5
) -> list[Finding]:
    """Each :data:`PATTERNS` shape in ``text`` (up to ``limit`` values a row)."""
    out = []
    for row in rows:
        seen: list[str] = []
        for m in row.pattern.finditer(text):
            if m[0] not in seen:
                seen.append(m[0])
                if len(seen) == limit:
                    break
        out += [Finding("patterns", row.kind, v) for v in seen]
    return out


def check_fields(
    text: str, rows: Sequence[Row] = FIELD_ROWS, *, limit: int = 5
) -> list[Finding]:
    """Each :data:`FIELD_ROWS` value without its row's allowed shape."""
    out = []
    for row in rows:
        bad: dict[str, None] = {}
        for m in row.pattern.finditer(text):
            allowed = row.allowed
            if allowed is not None and not allowed.fullmatch(m["val"]):
                bad[m["val"]] = None
                if len(bad) == limit:
                    break
        out += [Finding("fields", row.kind, v) for v in bad]
    return out


def load_denylist(path: Path | None) -> list[Term]:
    """The owner's denylist: one term per line, every non-blank line a term (no
    comment marker, so a term may start with ``#``), each searched
    case-insensitively as a whole word, however short."""
    if path is None or not path.is_file():
        return []
    terms = []
    for line in path.read_text().splitlines():
        term = line.strip()
        if term:
            terms.append(Term("user-denylist", term, fold=True, bounded=True))
    return terms


def machine_terms(machine: MachineFacts) -> Sequence[Term]:
    """This machine's names alone (for a log with no raw text to harvest)."""
    return harvest("", machine).terms


class SelfTestError(RuntimeError):
    """The scrubber left something the built-in synthetic log plants."""


#: A synthetic log planting, with fictional values, one of everything the
#: Manasight scrubber is relied on to remove (not what the second pass removes).
_SELF_TEST_LINES = (
    "Token: SELFTESTTOKENVALUE0001",
    "Authorization: Bearer SELFTESTBEARER0001",
    "Match to QWERTYUIOPASDFGHJKL0123456: AuthenticateResponse",
    "QWERTYUIOPASDFGHJKL0123456 to Match: hello",
    (
        '{"clientId": "SELFTESTCLIENT01", "userId": "SELFTESTUSER0001",'
        ' "sessionId": "SELFTESTSESSION1", "token": "SELFTESTJSONTOK1",'
        ' "screenName": "Selftestia Quorn", "playerName": "Selftestia Quorn"}'
    ),
    "[Subsystems] path /Users/selftestuser/Library/Logs",
    r"path C:\Users\selftestuser\AppData\LocalLow",
    "path /home/selftestuser/.config",
    (
        '<== DeckGetDeckSummariesV3 {"Summaries":[{"DeckId":'
        '"1b2c3d4e-5f60-4111-8222-123456789abc","Name":"Selftest Family Night"}]}'
    ),
    '{"CourseId":"9b2c3d4e-5f60-4111-8222-123456789abc"}',
    "  Renderer: Selftest GPU 9000",
    " preferred device: Selftest GPU 9000 (high power)",
    "Using device Selftest GPU 9000",
    "deviceModel SelftestBook17,3",
    "contact selftest.person@example.invalid",
    "relay 203.0.113.77 and 2001:db8:85a3::8a2e:370:7334",
)
SELF_TEST_LOG = "\n".join(_SELF_TEST_LINES) + "\n"


def self_test(scrub: Callable[[str], str]) -> None:
    """Feed :data:`SELF_TEST_LOG` through ``scrub``: every class it plants must
    be gone, by the same checks a real log faces. Raise :class:`SelfTestError`
    naming the classes left (values masked)."""
    out = scrub(SELF_TEST_LOG)
    found = check_terms(out, harvest(SELF_TEST_LOG).terms, "harvest")
    found += check_patterns(out) + check_fields(out)
    if out == SELF_TEST_LOG or found:
        left = ", ".join(sorted({str(f) for f in found})) or "it changed nothing"
        raise SelfTestError(f"the scrubber failed its self-test: {left}")
