"""The second pass: what the Manasight scrubber leaves, redacted, the line kept.

One row per gap, so the next gap is one row. Each replacement uses the
scrubber's own placeholder, so a redacted line reads like one the scrubber
wrote, and the scrubber leaves the result unchanged (the corpus's CI re-runs it
and rewrites any file it would change).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import NamedTuple

from mtg_utils._arena_corpus.scan import Anchored

__all__ = ["PLACEHOLDER", "RULES", "Rule", "second_pass"]

#: The scrubber's placeholder for a redacted name, id or token.
PLACEHOLDER = "<redacted>"


class Rule(NamedTuple):
    pattern: re.Pattern[str] | Anchored
    replacement: str
    reason: str


RULES: tuple[Rule, ...] = (
    Rule(
        re.compile(r"(Display Name:[ \t]*)[^\r\n]*[^\s]"),
        rf"\g<1>{PLACEHOLDER}",
        "the newer client's login line ('Logged in successfully. Display Name: …') "
        "keeps the handle; the scrubber only redacts name fields in JSON",
    ),
    Rule(
        re.compile(r"(Steam ID:[ \t]*)\d+"),
        rf"\g<1>{PLACEHOLDER}",
        "Steam's minidump line ('Caching Steam ID: …') names the Steam account",
    ),
    Rule(
        Anchored("7656119", r"(?<!\d)7656119\d{10}(?!\d)", reach=32),
        PLACEHOLDER,
        "a SteamID64 anywhere else",
    ),
    Rule(
        # a handle is on one line and holds its #12345
        Anchored(r"#\d{5}(?!\d)", r'(?:[^\s"\\<>#]+ ){0,4}[^\s"\\<>#]+#\d{5}(?!\d)'),
        PLACEHOLDER,
        "handle-shaped text (Name#12345) anywhere, an emoji or apostrophe in the "
        "name included; a name can hold spaces, so up to four words before it go too",
    ),
    Rule(
        re.compile(r"(<user-path>)[ \t][^\r\n]*"),
        r"\g<1>",
        "a bare home path whose user name holds a space keeps the rest of the name "
        "after the scrubber's <user-path>: the rest of the line goes",
    ),
    Rule(
        # a token can run to kilobytes: the line, up to 64 KiB, is searched
        Anchored(
            r"(?i)bearer",
            rf"(?i)\b(bearer\s+)(?!{re.escape(PLACEHOLDER)})\S+",
            reach=65536,
        ),
        rf"\g<1>{PLACEHOLDER}",
        "a bearer token in lowercase (the scrubber's row is case-sensitive)",
    ),
)


def second_pass(text: str) -> tuple[str, Counter[str]]:
    """``text`` with every :data:`RULES` match replaced, and how many each row
    replaced (keyed by its reason)."""
    counts: Counter[str] = Counter()
    for rule in RULES:
        text, n = rule.pattern.subn(rule.replacement, text)
        if n:
            counts[rule.reason] += n
    return text, counts
