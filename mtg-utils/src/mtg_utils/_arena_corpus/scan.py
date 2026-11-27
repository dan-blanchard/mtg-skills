"""Fast scans over 20-40 MB logs, giving the same matches as the plain regex.

Python's ``re`` tries a pattern that opens with a character class at every
position of the text, so a pattern like ``\\w+#\\d{5}`` costs seconds per file
(the first verifier spent about two minutes a file in such scans). An
:class:`Anchored` pattern searches a cheap literal-led ``anchor`` and runs the
full pattern only on the line around each hit. It finds every match the full
pattern would find, provided each match holds an anchor hit, sits on one line,
and is no longer than ``reach`` either side of its anchor; each use states why
that holds for it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

__all__ = ["Anchored"]


class Anchored:
    def __init__(self, anchor: str, full: str, *, reach: int = 1024) -> None:
        self.anchor = re.compile(anchor)
        self.full = re.compile(full)
        self.reach = reach
        self.pattern = full

    def finditer(self, text: str) -> Iterator[re.Match[str]]:
        end = 0
        for hit in self.anchor.finditer(text):
            if hit.start() < end:
                continue  # inside the last match
            # the line around the hit, at most ``reach`` either side (bounded
            # searches: a JSON line can be megabytes long)
            lo = max(end, hit.start() - self.reach)
            lo = text.rfind("\n", lo, hit.start()) + 1 or lo
            hi = min(len(text), hit.end() + self.reach)
            newline = text.find("\n", hit.end(), hi)
            hi = hi if newline == -1 else newline
            # pos / endpos bound where a match may lie; lookbehinds still see
            # the text before ``lo``, as a search of the whole text would
            for m in self.full.finditer(text, lo, hi):
                if m.start() <= hit.start() < m.end():
                    end = m.end()
                    yield m
                    break

    def subn(self, repl: str, text: str) -> tuple[str, int]:
        out, last, n = [], 0, 0
        for m in self.finditer(text):
            out += [text[last : m.start()], m.expand(repl)]
            last, n = m.end(), n + 1
        if not n:
            return text, 0
        out.append(text[last:])
        return "".join(out), n
