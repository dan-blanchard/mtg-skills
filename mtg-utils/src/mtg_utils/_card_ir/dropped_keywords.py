"""Keywords phase drops from a node it otherwise types, restored on the raw face
records before strict load.

Three shapes of phase's parse leave a creature's keyword out of the node that
should carry it, while the node itself keeps the words (backlog (o), the keyword
tribe):

* **a static def's grant left out of its modifications** — a ``Continuous`` def
  (top-level or a spell's ``GenericEffect``) whose own ``description`` grants a
  keyword no ``AddKeyword`` of the record carries: Chariot of the Sun's "gain
  flying and has base toughness 1" typed as ``SetToughness`` alone, Valkyrie's
  Call's "has flying and is an Angel" as ``AddSubtype`` alone, Tek's "has flying
  as long as you control an Island" parked in an ``Unrecognized`` condition, an
  animation's "4/4 Elemental creature with reach and haste" (Nissa's Zendikon);
* **a copy's keyword left out of its exceptions** — "create a token that's a
  copy of target creature you control, except the token has flying" typed with no
  ``AddKeyword`` among the copy's ``additional_modifications`` (Irenicus's Vile
  Duplication), or the rider after it ("… becomes a copy of target creature you
  control until end of turn and gains haste" — March from Velis Vel);
* **a keyword misread as a subtype** — a copy's "except it's a 4/4 Dragon
  creature with flying" typed as the subtypes ``With`` and ``Flying`` (Will of the
  Temur).

Restoring the input, rather than teaching each read a correction, means every
read — the keyword reads, the team grants, the anthem walk — sees the keyword the
way phase types it elsewhere (the ADR-0047 amendment's reason for pruning the
certain records before load). Each fix is keyed on phase's structure and reads
only the node's own clause (``clause_grammar.keyword_grants``) — a copy's, the
ability holding it, which phase types with one copy effect; a keyword the
record types anywhere is never added. A ``retirement_canary`` test per shape
(tests/mtg-utils/test_phase_gaps_keywords.py) fails once phase types the keyword
itself.

Pure functions over plain dicts; nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
import itertools
from collections.abc import Iterator

from mtg_utils._card_ir.clause_grammar import GRANT_KEYWORDS, keyword_grants

#: Phase's spelling of each keyword ``keyword_grants`` reads (``AddKeyword``'s
#: ``keyword``: ``"first strike"`` → ``"FirstStrike"``).
PHASE_KEYWORDS: dict[str, str] = {
    kw: kw.title().replace(" ", "") for kw in GRANT_KEYWORDS
}
_BY_PHASE_SPELLING = {v: k for k, v in PHASE_KEYWORDS.items()}
_COPY_TAGS = frozenset({"CopyTokenOf", "BecomeCopy"})


def _dicts(node: object) -> Iterator[dict]:
    """Every dict under ``node``, ``node`` included (``trees._iter_raw_dicts``)."""
    from mtg_utils._card_ir.trees import _iter_raw_dicts

    return _iter_raw_dicts(node, lambda _d: True)


def _typed_keywords(rec: dict) -> set[str]:
    """The vocabulary keywords the record types anywhere: an ``AddKeyword``, a
    token's ``keywords``, a token copy's ``extra_keywords``."""
    out: set[str] = set()
    for d in _dicts(rec):
        if d.get("type") == "AddKeyword" and isinstance(d.get("keyword"), str):
            out.add(_BY_PHASE_SPELLING.get(d["keyword"], ""))
        for field in ("keywords", "extra_keywords"):
            if d is not rec and isinstance(d.get(field), list):
                out.update(
                    _BY_PHASE_SPELLING.get(k, "")
                    for k in d[field]
                    if isinstance(k, str)
                )
    out.discard("")
    return out


def _animates(mods: list) -> bool:
    """Whether a def's modifications make its object a creature (an animation's
    "is a 4/4 Elemental creature with reach and haste")."""
    return any(
        isinstance(m, dict)
        and (
            (m.get("type") == "AddType" and m.get("core_type") == "Creature")
            or (
                m.get("type") == "SetCardTypes"
                and "Creature" in (m.get("core_types") or ())
            )
        )
        for m in mods
    )


def _grants(rec: dict) -> Iterator[tuple[dict, str, frozenset[str]]]:
    """``(node, field, keywords)`` per node whose own clause grants keywords: a
    ``Continuous`` def (``modifications``) by its description, and an ability's one
    copy effect (``additional_modifications``) by the ability's — an exception
    ("except the token has flying" — Irenicus's Vile Duplication) or a rider after
    it ("becomes a copy of target creature you control until end of turn and gains
    haste" — March from Velis Vel)."""
    for d in _dicts(rec):
        mods, desc = d.get("modifications"), d.get("description")
        if d.get("mode") == "Continuous" and isinstance(mods, list) and desc:
            mode = "any" if _animates(mods) else None
            yield d, "modifications", keyword_grants(desc, creature_with=mode)
    for field in ("abilities", "triggers", "replacements"):
        for ab in rec.get(field) or ():
            desc = ab.get("description") if isinstance(ab, dict) else None
            if not desc:
                continue
            copies = [d for d in _dicts(ab) if d.get("type") in _COPY_TAGS]
            if len(copies) == 1:
                yield copies[0], "additional_modifications", keyword_grants(desc)


def _dropped_grants(rec: dict) -> list[tuple[dict, str, tuple[str, ...]]]:
    """``(node, field, keywords)`` per :func:`_grants` node whose keywords the
    record types nowhere."""
    found = [(n, f, kws) for n, f, kws in _grants(rec) if kws]
    if not found:
        return []
    typed = _typed_keywords(rec)
    return [
        (n, f, missing)
        for n, f, kws in found
        if (missing := tuple(sorted(kws - typed)))
    ]


def _subtype_keyword(mod: object) -> str | None:
    """The phase keyword spelling an ``AddSubtype`` names, or ``None``."""
    if isinstance(mod, dict) and mod.get("type") == "AddSubtype":
        sub = mod.get("subtype")
        if isinstance(sub, str) and sub in _BY_PHASE_SPELLING:
            return sub
    return None


def _is_with(mod: object) -> bool:
    return (
        isinstance(mod, dict)
        and mod.get("type") == "AddSubtype"
        and mod.get("subtype") == "With"
    )


def _misread_subtype_lists(rec: dict) -> list[list]:
    """Each modification list holding an ``AddSubtype("With")`` followed by an
    ``AddSubtype`` that names a keyword."""
    return [
        mods
        for d in _dicts(rec)
        for field in ("modifications", "additional_modifications")
        if isinstance(mods := d.get(field), list)
        and any(
            _is_with(a) and _subtype_keyword(b) is not None
            for a, b in itertools.pairwise(mods)
        )
    ]


def _keywords_for_subtypes(mods: list) -> list:
    """``mods`` with each ``With`` + keyword-subtype run read as ``AddKeyword``\\ s."""
    out: list = []
    run = False
    for m in mods:
        if _is_with(m):
            run = True
            continue
        kw = _subtype_keyword(m) if run else None
        if kw is not None:
            out.append({"type": "AddKeyword", "keyword": kw})
            continue
        run = False
        out.append(m)
    return out


def restore_dropped_keywords(rec: dict) -> dict:
    """``rec`` with the keywords phase dropped restored (a copy when any are)."""
    grants = _dropped_grants(rec)
    subtype_lists = _misread_subtype_lists(rec)
    if not grants and not subtype_lists:
        return rec
    memo: dict[int, object] = {}
    out = copy.deepcopy(rec, memo)
    for node, field, missing in grants:
        target = memo[id(node)]
        assert isinstance(target, dict)
        target[field] = [
            *(target.get(field) or ()),
            *({"type": "AddKeyword", "keyword": PHASE_KEYWORDS[kw]} for kw in missing),
        ]
    for mods in subtype_lists:
        target = memo[id(mods)]
        assert isinstance(target, list)
        target[:] = _keywords_for_subtypes(target)
    return out
