"""Keywords phase drops from a node it otherwise types, restored on the raw face
records before strict load.

Four shapes of phase's parse leave a creature's keyword out of the node that
should carry it, while the node itself (or phase's own known-tokens entry) keeps
the words (backlog (o), the keyword tribe):

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
  Temur);
* **a Role token's own ability** — "Create a Monster Role token attached to it"
  typed as a ``Token`` with no static, where the Role is "Enchanted creature gets
  +1/+1 and has trample" (CR 111.10k; Royal's "has ward {1}", 111.10m).

A restored ward carries the generic mana cost its clause states (phase's
``{"Ward": {"type": "Mana", …}}``); a ward of any other cost is left alone.

Restoring the input, rather than teaching each read a correction, means every
read — the keyword reads, the team grants, the anthem walk — sees the keyword the
way phase types it elsewhere (the ADR-0047 amendment's reason for pruning the
certain records before load). Each fix is keyed on phase's structure and reads
only the node's own clause (``clause_grammar.keyword_grants``) — a copy's, the
ability holding it, which phase types with one copy effect; a keyword the
record types anywhere is never added. A ``retirement_canary`` test per shape
(tests/mtg-utils/test_phase_gaps_keywords.py) fails once phase types the keyword
itself.

Pure functions over plain dicts (and, for a Role, phase's known-tokens index —
``trees._known_tokens_index``); nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
import itertools
from collections.abc import Iterator

from mtg_utils._card_ir.clause_grammar import (
    GRANT_KEYWORDS,
    keyword_grants,
    ward_generic_cost,
)

#: Phase's spelling of each keyword ``keyword_grants`` reads (``AddKeyword``'s
#: ``keyword``: ``"first strike"`` → ``"FirstStrike"``; ward's is a variant's
#: key, ``{"Ward": <cost>}``, which a bare ``AddKeyword`` never restores).
PHASE_KEYWORDS: dict[str, str] = {
    kw: kw.title().replace(" ", "") for kw in GRANT_KEYWORDS
}
_BY_PHASE_SPELLING = {v: k for k, v in PHASE_KEYWORDS.items()}
_COPY_TAGS = frozenset({"CopyTokenOf", "BecomeCopy"})


def _dicts(node: object) -> Iterator[dict]:
    """Every dict under ``node``, ``node`` included (``trees._iter_raw_dicts``)."""
    from mtg_utils._card_ir.trees import _iter_raw_dicts

    return _iter_raw_dicts(node, lambda _d: True)


def _keyword_name(kw: object) -> str:
    """The vocabulary keyword a raw keyword names — a bare spelling or a
    parameterized one's variant key (``{"Ward": <cost>}``) — or ``""``."""
    if isinstance(kw, dict) and len(kw) == 1:
        kw = next(iter(kw))
    return _BY_PHASE_SPELLING.get(kw, "") if isinstance(kw, str) else ""


def _typed_keywords(rec: dict) -> set[str]:
    """The vocabulary keywords the record types anywhere: an ``AddKeyword``, a
    token's ``keywords``, a token copy's ``extra_keywords``."""
    out: set[str] = set()
    for d in _dicts(rec):
        if d.get("type") == "AddKeyword":
            out.add(_keyword_name(d.get("keyword")))
        for field in ("keywords", "extra_keywords"):
            if d is not rec and isinstance(d.get(field), list):
                out.update(_keyword_name(k) for k in d[field])
    out.discard("")
    return out


def _add_keyword(kw: str, text: str) -> dict | None:
    """Phase's ``AddKeyword`` for a keyword ``text`` grants: the bare keyword, or
    ward with the generic mana cost ``text`` states ("ward {1}" — phase's
    ``{"Ward": {"type": "Mana", …}}``, CR 702.21a); ``None`` for a parameter it
    can't read."""
    if kw != "ward":
        return {"type": "AddKeyword", "keyword": PHASE_KEYWORDS[kw]}
    generic = ward_generic_cost(text)
    if generic is None:
        return None
    cost = {"type": "Cost", "shards": [], "generic": generic}
    return {"type": "AddKeyword", "keyword": {"Ward": {"type": "Mana", "data": cost}}}


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


def _grants(rec: dict) -> Iterator[tuple[dict, str, str, frozenset[str]]]:
    """``(node, field, clause, keywords)`` per node whose own clause grants
    keywords: a ``Continuous`` def (``modifications``) by its description, and an
    ability's one copy effect (``additional_modifications``) by the ability's — an
    exception ("except the token has flying" — Irenicus's Vile Duplication) or a
    rider after it ("becomes a copy of target creature you control until end of
    turn and gains haste" — March from Velis Vel)."""
    for d in _dicts(rec):
        mods, desc = d.get("modifications"), d.get("description")
        if d.get("mode") == "Continuous" and isinstance(mods, list) and desc:
            mode = "any" if _animates(mods) else None
            yield d, "modifications", desc, keyword_grants(desc, creature_with=mode)
    for field in ("abilities", "triggers", "replacements"):
        for ab in rec.get(field) or ():
            desc = ab.get("description") if isinstance(ab, dict) else None
            if not desc:
                continue
            copies = [d for d in _dicts(ab) if d.get("type") in _COPY_TAGS]
            if len(copies) == 1:
                yield copies[0], "additional_modifications", desc, keyword_grants(desc)


def _dropped_grants(rec: dict) -> list[tuple[dict, str, list[dict]]]:
    """``(node, field, AddKeywords)`` per :func:`_grants` node whose keywords the
    record types nowhere."""
    typed: set[str] | None = None
    out = []
    for node, field, desc, kws in _grants(rec):
        if not kws:
            continue
        if typed is None:
            typed = _typed_keywords(rec)
        adds = [a for kw in sorted(kws - typed) if (a := _add_keyword(kw, desc))]
        if adds:
            out.append((node, field, adds))
    return out


# A Role token's own ability: "Enchanted creature gets +1/+1 and has trample" (CR
# 111.10k — Monster) or "… has ward {1}" (111.10m — Royal), which phase leaves
# off the Token node. Its text is phase's own known-tokens entry (the same join
# ``trees._known_token_trees`` makes), restored the way phase types an Aura
# token's ability: a SelfRef ``GrantStaticAbility`` of the static the token has.
_ENCHANTED_CREATURE = {
    "type": "Typed",
    "type_filters": ["Creature"],
    "controller": None,
    "properties": [{"type": "EnchantedBy"}],
}


def _static_def(affected: dict, modifications: list, description: str) -> dict:
    return {
        "mode": "Continuous",
        "affected": affected,
        "modifications": modifications,
        "condition": None,
        "affected_zone": None,
        "effect_zone": None,
        "active_zones": [],
        "characteristic_defining": False,
        "description": description,
    }


def _role_grants(rec: dict) -> list[tuple[dict, list[dict]]]:
    """``(Token node, AddKeywords)`` per Role token the record creates that phase
    typed with no ability, whose known-tokens text grants its enchanted creature a
    keyword."""
    from mtg_utils._card_ir.trees import (
        _known_token_display_name_candidates,
        _known_tokens_index,
    )

    related = (rec.get("metadata") or {}).get("related_token_ids") or []
    if not related:
        return []
    index = _known_tokens_index() or {}
    entries = {
        index[tid]["display_name"].casefold(): index[tid]
        for tid in related
        if tid in index
    }
    if not entries:
        return []
    out = []
    for d in _dicts(rec):
        if (
            d.get("type") != "Token"
            or "Role" not in (d.get("types") or ())
            or d.get("static_abilities")
            or d.get("keywords")
        ):
            continue
        names = _known_token_display_name_candidates(str(d.get("name") or ""))
        found = [entries[n.casefold()] for n in names if n.casefold() in entries]
        if not found:
            continue
        text = found[0]["rules_text"]
        adds = [
            a for kw in sorted(keyword_grants(text)) if (a := _add_keyword(kw, text))
        ]
        if adds:
            out.append((d, adds))
    return out


def _role_static(adds: list[dict]) -> dict:
    grant = {
        "type": "GrantStaticAbility",
        "definition": _static_def(_ENCHANTED_CREATURE, adds, "Enchanted creature"),
    }
    return _static_def({"type": "SelfRef"}, [grant], "The token has its ability")


def _subtype_keyword(mod: object) -> str | None:
    """The phase keyword spelling an ``AddSubtype`` names, or ``None``."""
    if isinstance(mod, dict) and mod.get("type") == "AddSubtype":
        sub = mod.get("subtype")
        if isinstance(sub, str) and sub in _BY_PHASE_SPELLING and sub != "Ward":
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
    roles = _role_grants(rec)
    if not grants and not subtype_lists and not roles:
        return rec
    memo: dict[int, object] = {}
    out = copy.deepcopy(rec, memo)
    for node, field, adds in grants:
        target = memo[id(node)]
        assert isinstance(target, dict)
        target[field] = [*(target.get(field) or ()), *adds]
    for mods in subtype_lists:
        target = memo[id(mods)]
        assert isinstance(target, list)
        target[:] = _keywords_for_subtypes(target)
    for token, adds in roles:
        target = memo[id(token)]
        assert isinstance(target, dict)
        target["static_abilities"] = [_role_static(adds)]
    return out
