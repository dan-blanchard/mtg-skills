"""Resolve a Scryfall record to its Card IR by ``oracle_id`` (ADR-0027 / 0035).

``ranking.py`` and ``budgets.py`` cluster / role-classify a candidate by reading
its structured abilities instead of re-grepping oracle text. Both join the card
to the IR the same way the engine does (``engine._ir_index``): one memoized load
of the sidecar (oracle_id → :class:`Card`), then an ``oracle_id`` lookup per card.

The lookup degrades to ``None`` whenever the sidecar is absent / the wrong
version (``load_crosswalk_card_ir`` raises) or the card carries no ``oracle_id``
— so a no-IR deployment, or a synthetic test fixture with no oracle_id, simply
degrades gracefully in the caller. Memoized so a tune issuing many searches
never re-reads the sidecar.

ADR-0035/0039 — the crosswalk is the ONLY serving path (task #80 step 6 deleted
the ``MTG_SKILLS_CROSSWALK_SIGNALS`` cutover flag and the legacy projected-Card
revert path it gated):

* :func:`ir_for` (Seam B — the five dataclass-API consumers ``ranking`` /
  ``budgets`` / ``cut_check`` / ``metrics`` / ``bracket``) returns the
  crosswalk-backed :class:`Card` sidecar — ``None`` when that sidecar is
  unbuilt, NEVER a silent fall-through to a different builder's Card
  (ADR-0039 task #80 step 4).
* :func:`trees_for` (Seam A — the hybrid signal dispatch) resolves a record to
  its Layer-2 concept trees, ONE PER PHASE FACE RECORD (a DFC / split card
  shares one ``oracle_id`` across faces, each face a separate phase record —
  ADR-0035/0038 task #74), built lazily from phase's ``card-data.json`` + the
  committed mirror schema, keyed by ``oracle_id`` (cache-parallel to ir_for).
  Callers union signals across the returned trees; nothing merges the trees
  themselves (a merged multi-face tree would corrupt card-level reads like
  ``is_type`` / cmc that only make sense per-face). ADR-0038 W2c: phase emits
  NO record at all for some multi-face halves (every aftermath second half
  corpus-wide, plus one two-face split); the production caller threads the
  bulk (MTGJSON) record's ``card_faces`` in as ``bulk=`` so those get one
  additional TEXT-ONLY tree apiece, carrying the bulk face's oracle text
  verbatim with zero units — the bulk record is the text source of record
  when phase has nothing to parse at all."""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from mtg_utils.card_ir import Card

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from mtg_utils._card_ir.crosswalk import ConceptTree
    from mtg_utils._card_ir.mirror.schema import MirrorSchema


# ── Seam B — the Card dataclass API resolver ──────────────────────────────────


@functools.cache
def _crosswalk_index() -> Mapping[str, Card] | None:
    """The crosswalk-backed Card IR index, loaded once per process (lazy per
    card — see ``load.LazyCardMap``). ``None`` when the crosswalk sidecar is
    absent / the wrong version, so :func:`ir_for` degrades gracefully."""
    from mtg_utils._card_ir.load import load_crosswalk_card_ir

    try:
        return load_crosswalk_card_ir()
    except (FileNotFoundError, ValueError):
        return None


def ir_for(card: dict) -> Card | None:
    """The candidate's Card IR (by ``oracle_id``), or ``None`` when unavailable.

    Returns the crosswalk-backed sidecar's Card (the single index every Seam-B
    consumer reads); if the sidecar is unbuilt, returns ``None`` — the SAME
    graceful "nothing here" contract ``production.default_state`` uses for a
    missing bulk file (``bulk_available=False``, empty search).
    ``production.ensure_card_ir`` builds this sidecar at launch so the degraded
    branch is the exception, not the common case (ADR-0039 task #80 step 4).

    ``None`` covers the cases the callers treat identically — no sidecar, an
    oracle_id absent from the index, and a record with no ``oracle_id``
    (synthetic fixtures) — each degrading gracefully in the Seam-B caller."""
    index = _crosswalk_index()
    if index is None:
        return None
    return index.get(card.get("oracle_id") or "")


# ── Seam A — the concept-tree resolver ──────────────────────────────────────


@functools.cache
def _phase_record_index() -> dict[str, tuple[dict, ...]] | None:
    """oracle_id → ALL phase ``card-data.json`` records sharing it (insertion
    order, so a DFC's front face precedes its back face), loaded once per
    process. ``None`` when phase card-data is unavailable so :func:`trees_for`
    degrades. Reuses :func:`~mtg_utils._card_ir.build._group_by_oracle_id` — the
    same grouping the sidecar builders use — so a DFC / split card's faces are
    never silently dropped here (ADR-0035/0038 task #74; a first-record-wins
    index previously dropped whichever face iterated second, e.g. Avatar
    Aang's front face when phase's dict keys sort its back face first)."""
    from mtg_utils import _phase
    from mtg_utils._card_ir.build import _group_by_oracle_id

    try:
        cdp = _phase.ensure_card_data()
        data = json.loads(cdp.read_text())
    except (FileNotFoundError, RuntimeError, OSError, ValueError):
        return None
    groups = _group_by_oracle_id(data)
    if not groups:
        return None
    return {oid: tuple(recs) for oid, recs in groups.items()}


@functools.cache
def _committed_schema() -> MirrorSchema | None:
    """The committed phase-mirror schema (CI-usable fixture), loaded once per
    process. ``None`` when the fixture is missing."""
    from mtg_utils._card_ir.mirror.build import load_committed_schema

    try:
        return load_committed_schema()
    except (FileNotFoundError, ValueError):
        return None


# oracle_id → the tuple of per-face ConceptTrees (empty when unresolvable).
# Built lazily on first request per card so a tune never strict-loads
# the whole corpus up front (the Stage-4 overlay cache supersedes this).
# Cleared alongside the memoized indexes in tests.
_TREES_MEMO: dict[str, tuple[ConceptTree, ...]] = {}


def clear_caches() -> None:
    """Drop every memoized index / tree (test hygiene between fixture swaps).

    Defensive: a test may ``monkeypatch`` any of the memoized loaders with a plain
    lambda (no ``cache_clear``), so skip anything that is not an active cache."""
    for fn in (
        _crosswalk_index,
        _phase_record_index,
        _committed_schema,
        _known_tokens_index,
    ):
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()
    _TREES_MEMO.clear()


# ── ADR-0038 W2c — text-only face trees ────────────────────────────────────
# phase emits NO ``card-data.json`` record at all for some multi-face halves
# (never even a drifted / Unimplemented one — a name lookup in phase's own
# corpus comes back empty). The refined census (casefolded bulk-face-name ↔
# phase-record-name join, over every bulk record whose oracle_id DOES have a
# phase group) found this is corpus-wide for the ``aftermath`` layout (96/96
# second halves — Failure // Comply's "Comply" face, etc.) plus exactly one
# two-face ``split`` gap ("Furious", off "Fast // Furious" — legal in
# commander/brawl/modern/legacy/vintage). adventure / transform / modal_dfc /
# flip / prepare are FULLY covered by phase (0 missing faces each); the
# original crude substring probe's larger numbers for those layouts were
# false positives from imprecise text matching, not real gaps.
#
# Defer-not-hack: three-/five-way "split" cards (Unglued/Unstable/Unfinity
# jokes like "Smelt // Herd // Saw", "Who // What // When // Where // Why")
# also miss faces by this join, but they are EXCLUDED — real tournament
# Magic never has more than two card faces on a split/aftermath/adventure/
# transform/modal_dfc card, so ``len(card_faces) != 2`` is a clean, principled
# gate (not a name/layout special-case) that drops every funny-set multi-way
# split while keeping the one legal two-face split gap. ``art_series`` /
# ``double_faced_token`` / ``reversible_card`` are excluded by layout name —
# none of them is a real two-face gameplay split (an art-card back, a token
# pair, two independent full prints sharing one physical card).

_TEXT_ONLY_EXCLUDED_LAYOUTS: frozenset[str] = frozenset(
    {
        "art_series",  # art-card backs, not a playable gameplay face
        "double_faced_token",  # token pairs, not a real card
        "reversible_card",  # two independent full prints, not a face-split
    }
)

_MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def _face_key(name: str | None) -> str:
    """Casefold a face name to phase's join key (phase's own ``card-data.json``
    keys are lowercased face names; casefold is the Unicode-correct match)."""
    return (name or "").strip().casefold()


def _face_cmc(mana_cost: str) -> int | None:
    """Mana value (CR 202.3) of one face's ``mana_cost`` string, or ``None``
    for an empty string (the caller falls back to the record ``cmc``). A
    generic symbol adds its number; ``X``/``Y``/``Z`` add 0 (CR 107.3c); a
    hybrid symbol (``{2/W}``/``{W/P}``) adds the larger side (1 when neither
    side is numeric); any other symbol (a color, ``{C}``, ``{S}``) adds 1."""
    if not mana_cost:
        return None
    total = 0
    for raw_sym in _MANA_SYMBOL_RE.findall(mana_cost):
        sym = raw_sym.upper()
        if sym.isdigit():
            total += int(sym)
        elif sym in ("X", "Y", "Z"):
            continue
        elif "/" in sym:
            nums = [int(p) for p in sym.split("/") if p.isdigit()]
            total += max(nums) if nums else 1
        else:
            total += 1
    return total


def _face_power(value: object) -> int | None:
    """A face's fixed printed power as an int, or ``None`` for a missing /
    non-fixed (``*``, ``1+*``) power — mirrors ``build_concept_tree``'s
    ``Fixed``-tag-only read of phase's own ``power`` node."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _text_only_tree(face: dict, bulk: dict, *, oracle_id: str) -> ConceptTree | None:
    """One phase-missing face as a zero-unit text-only tree, or ``None`` for a
    blank oracle text (nothing to carry).

    ``units=()`` — no typed substrate exists for this face, so every
    unit-scoped structural lane (per-ability sibling co-occurrence, cost /
    static reads) sees an honest empty rather than a fabricated parse; every
    membership/gap gate that checks ``tree.units`` (or iterates it) degrades
    the same way it would for a vanilla card with no abilities. The
    whole-card ``oracle`` field carries the bulk text verbatim: the
    SANCTIONED byte-mirror lanes (b12) read it directly off ``tree.oracle``,
    and ``crosswalk_signals.extract_crosswalk_signals`` runs
    ``apply_overlay_corrections`` + ``apply_tree_synthesis`` over EVERY tree
    it is handed (not only phase-built ones) — so the ``tree_synthesis``
    bucket-B reference-only arms that key off ``tree.oracle`` (and the
    ADR-0038 clause-grammar recovery, which has nothing to re-decorate here
    since there are no ``other``-concept nodes) apply to a text-only tree
    exactly as they would to a phase-built one."""
    from mtg_utils._card_ir.crosswalk import ConceptTree
    from mtg_utils.deck import CARD_TYPE_WORDS, split_type_line

    oracle = (face.get("oracle_text") or "").strip()
    if not oracle:
        return None
    type_words, sub_words = split_type_line(face.get("type_line") or "")
    # split_type_line lowercases; ConceptTree's card_types/supertypes/subtypes
    # are Title Case single words (phase's own convention — see
    # build_concept_tree). CARD_TYPE_WORDS classifies the em-dash-prefix
    # words into core types vs. supertypes (Legendary/Snow/Basic/…); every
    # word appearing on a split/aftermath/adventure/transform/modal_dfc face
    # in practice is one of the two (never Tribal/Plane/Scheme/…).
    card_types = tuple(w.capitalize() for w in type_words if w in CARD_TYPE_WORDS)
    card_supertypes = tuple(
        w.capitalize() for w in type_words if w not in CARD_TYPE_WORDS
    )
    card_subtypes = tuple(w.capitalize() for w in sub_words)
    cmc = _face_cmc(face.get("mana_cost") or "")
    if cmc is None:
        cmc = int(bulk.get("cmc") or 0)
    return ConceptTree(
        name=face.get("name") or "",
        oracle_id=oracle_id,
        units=(),
        card_types=card_types,
        card_subtypes=card_subtypes,
        card_supertypes=card_supertypes,
        cmc=cmc,
        power=_face_power(face.get("power")),
        has_printed_cost=bool(face.get("mana_cost")),
        oracle=face.get("oracle_text") or "",
    )


def _text_only_trees(
    bulk: dict, phase_recs: tuple[dict, ...], *, oracle_id: str
) -> list[ConceptTree]:
    """Text-only trees for every ``bulk`` face with no name-matched phase
    record among ``phase_recs`` — scoped to real two-face gameplay layouts
    (see the module comment above the exclusion set)."""
    faces = bulk.get("card_faces") or []
    if bulk.get("layout") in _TEXT_ONLY_EXCLUDED_LAYOUTS or len(faces) != 2:
        return []
    phase_names = frozenset(_face_key(r.get("name")) for r in phase_recs)
    out: list[ConceptTree] = []
    for face in faces:
        if _face_key(face.get("name")) in phase_names:
            continue
        tree = _text_only_tree(face, bulk, oracle_id=oracle_id)
        if tree is not None:
            out.append(tree)
    return out


# ── task #92 — KNOWN-TOKENS SUBSTRATE ──────────────────────────────────────
# phase's Token effect node (the CreateToken payload) carries the PREDEFINED
# token's printed body — types / power / toughness / colors / whatever
# keywords or static abilities its OWN static-ability parser DOES decompose —
# but for a token whose ability is an activated cost ("{1}, {T}, Sacrifice
# this token: …" — the Mutagen cycle) or a granted triggered ability the
# static parser doesn't unpack (the WOE Role cycle's "Enchanted creature
# has…"), the Token node is a bare shell: no ``static_abilities``, no
# ``keywords``, nothing. That ability text is NOT missing upstream — it lives
# in phase's own ``known-tokens.toml`` data file (``ensure_known_tokens``
# above), one ``[[token]]`` entry per predefined token id, carrying a
# ``rules_text`` string plus a ``[token.body]`` sub-table (``display_name`` /
# ``core_types`` / ``subtypes`` / ``supertypes``).
#
# THE JOIN: a source card's raw phase record carries ``metadata.
# related_token_ids`` — the toml ``id``(s) of every predefined token it can
# create. A card creating exactly one predefined token type has one id; a
# card offering a CHOICE of Role (WOE's "Young Hero Role" vs "Royal" tokens
# both showing up on Cut In's ``related_token_ids``, per the shared per-SET
# ``source_card_names`` census) has several — so the id list alone doesn't
# disambiguate WHICH token a given Token effect node instantiates. The
# reliable disambiguator is the Token node's OWN ``name`` field (phase always
# parses this correctly — it's what prints on the token): "Young Hero Role"
# for Cut In, matched against toml's ``display_name`` "Young Hero" (the toml
# omits the trailing " Role" subtype suffix phase's Token node name carries).
#
# THE ATTACHMENT SEAM: one extra zero-unit TEXT-ONLY ``ConceptTree`` per
# distinct matched token, appended to the SAME per-oid tuple :func:`build_trees`
# returns (the ADR-0038 W2c text-only-face precedent, mirrored exactly — see
# :func:`_text_only_tree`). This is deliberate: every existing lane that asks
# "does ANY tree for this card do X" (``_concept_any_face``, the crosswalk's
# own per-oid union in ``signals.py``) already iterates the WHOLE tuple, so a
# card that creates a Mutagen token gets "this card's stuff includes a +1/+1
# counter maker" for free, with ZERO changes to any consuming lane — while a
# card that creates no predefined token (the overwhelming majority) gets an
# unchanged, single-tree-per-face tuple. No new tree IDENTITY, no widening of
# any structural walk — purely additive.
#
# GAP-GATED, NOT AN OVERRIDE: only fires when the card's own Token node
# carries NEITHER ``static_abilities`` NOR ``keywords`` — i.e. only when phase
# genuinely parsed nothing for that token's ability. A predefined token phase
# DOES fully decompose (a bare vanilla keyword token, say) is left alone; this
# substrate never second-guesses a structural parse that already exists.
#
# ADJUDICATED ALLOWLIST (task #92, widened task #95): a corpus-wide sweep of
# every predefined token this gap-gate matches found 34 distinct token
# identities with NONEMPTY ``rules_text`` (a much larger set of identities
# carries BLANK ``rules_text`` — a vanilla creature token with no ability at
# all, e.g. a plain Zombie/Soldier/Goblin — those never produce a tree
# regardless of this allowlist: :func:`_known_token_tree` returns ``None``
# for blank text). Task #95 (Dan's 2026-07-13 directive: adjudicate EVERY
# remaining identity, wire what's real) re-swept all 34 and widened the
# wired set from 2 to 8, each verified to open a real, already-existing
# lane — the corpus-discipline bar (every membership delta gets a verified
# reason) applied per identity, not mass-enabled:
#
# * "Mutagen" (task #92; the TMT cycle) — "{1}, {T}, Sacrifice this token:
#   Put a +1/+1 counter on target creature." opens ``plus_one_makers``
#   (CR 122.1) via :func:`~mtg_utils._card_ir.tree_synthesis.
#   _arm_plus_one_makers`.
# * "Young Hero" (task #92; the WOE cycle) — "Whenever this creature
#   attacks, if its toughness is 3 or less, put a +1/+1 counter on it"
#   opens the SAME ``plus_one_makers`` lane, same mechanism.
# * "Powerstone" / "Gold" (task #95) — "{T}: Add {C}. This mana can't be
#   spent to cast a nonartifact spell." / "Sacrifice this token: Add one
#   mana of any color." each open ``ramp`` (CR 106.1/605.1a) via
#   :func:`~mtg_utils._card_ir.tree_synthesis._arm_known_token_ramp`.
# * "Lander" (task #95) — "…Sacrifice this token: Search your library for
#   a basic land card, put it onto the battlefield tapped…" is corpus-
#   verified NOT ``ramp`` in this system's own convention (Rampant Growth
#   / Nature's Lore / Wayfarer's Bauble / Solemn Simulacrum / Migration
#   Path all probed: none tags ``ramp``, since ``_ramp`` requires a
#   literal Mana-producing effect, not a land fetch) — it opens ``tutor``
#   (CR 701.23/701.23a) instead, for FREE, via ``_tutor_lane``'s existing
#   ``synth_tutor`` bucket-B oracle-text rescue arm (no new code needed;
#   confirmed by the corpus diff — all 20 Lander creators gained
#   ``tutor``, zero gained ``ramp``).
# * "Map" (task #95) — "…Sacrifice this artifact: Target creature you
#   control explores…" opens ``explore_makers`` (CR 701.44a) via
#   :func:`~mtg_utils._card_ir.tree_synthesis._arm_known_token_explore`.
# * "Junk" (task #95) — "…Sacrifice this artifact: Exile the top card of
#   your library. You may play that card this turn…" opens
#   ``impulse_top_play`` (CR 601.3b/116) via
#   :func:`~mtg_utils._card_ir.tree_synthesis.
#   _arm_known_token_impulse_top_play`.
# * "Wicked" (task #95; one of the WOE Role cycle) — "…When this Aura is
#   put into a graveyard from the battlefield, each opponent loses 1
#   life." opens ``lifeloss_makers`` scope "opponents" (CR 119.3) via
#   :func:`~mtg_utils._card_ir.tree_synthesis.
#   _arm_known_token_lifeloss_opponents`.
#
# EVERYTHING ELSE the sweep found is DOCUMENTED RESIDUE — each individually
# adjudicated (task #95), not a blanket deferral:
#
# * Treasure (337 cards) / Food (140) / Clue (26) / Blood (41) — ALREADY
#   fully covered without this substrate at all: ``_resource_token_makers``
#   reads the Token node's own printed ``types``/subtypes (Treasure/Food/
#   Clue/Blood), never the ability text — verified at task #95 by probing
#   2 creators each (e.g. Dire Fleet Hoarder / Contract Killing for
#   Treasure) against ``extract_signals_hybrid``: ``treasure_makers`` /
#   ``food_makers`` / ``clue_makers`` / ``blood_makers`` already fire.
#   Enabling their ability text here would be pure redundancy.
# * Eldrazi Scion / Eldrazi Spawn — ALSO already fully covered, but by a
#   DIFFERENT mechanism than Treasure/Food/Clue/Blood: every corpus
#   creator (Vile Redeemer, Grave Birthing, Corpsehatch, Essence Feed, …)
#   structures the "Sacrifice this token: Add {C}." grant as a SIBLING
#   ``GenericEffect``/``GrantAbility`` static node right after the Token
#   creation (phase's own inline-grant idiom for simple sac-for-mana
#   tokens), which ``crosswalk_signals._granted_mana_defs`` already reads
#   — ``ramp`` fires at baseline for all 4 probed creators. The known-
#   tokens gap-gate still matches these two identities (the raw ``Token``
#   node itself carries neither ``static_abilities`` nor ``keywords`` — the
#   grant lives on the NEXT sibling node, not the Token node), but wiring
#   them here would be pure redundancy through a second path.
# * Virtuous (1 card: Ellivere of the Wild Court) — "…gets +1/+1 for each
#   enchantment you control" is itself an enchantments-matter PAYOFF, but
#   Ellivere already fires ``enchantments_matter`` at baseline via the
#   GENERIC ``make_token`` Enchantment-subject read every Role-token
#   creator gets (a Role token's own core type is Enchantment/Aura, so
#   ``_artifacts_enchantments_matter``'s token-maker branch fires
#   regardless of ability text). The devotion-style per-enchantment
#   SCALING nuance isn't separately captured, but the lane already opens.
# * Cursed (base P/T set to 1/1, a single-target Aura neutralize — soft
#   removal, Darksteel-Mutation-shaped) — NO lane in ``crosswalk_signals``
#   reads a single-target base-P/T-set at all: ``_debuff_makers`` explicitly
#   EXCLUDES a single-Aura shrink by design (its own docstring: "a single-
#   Aura/single-target shrink … is a neutralize, NOT a mass -1/-1
#   enabler"), and neither ``_removal`` nor ``_pacify_makers`` reads the
#   ``set_pt`` concept. This is a genuine, PRE-EXISTING lane gap (a real
#   Darksteel Mutation-shaped card would be equally unserved) — not
#   specific to the known-tokens substrate, and out of scope for a token-
#   identity wiring sweep (it needs a NEW lane, not a new source feeding
#   an old one). Left unwired; a future task can design that lane.
# * Royal (+1/+1 + ward {1}) / Monster (+1/+1 + trample) — a single-target
#   keyword grant. ``_keyword_grant_lanes`` DOES have a text-only-tree
#   fallback (``_KEYWORD_GRANT_TARGET_KEPT_RX``), but it's anchored to the
#   "target creature … gains/gets +X/+Y and gains KEYWORD" phrasing (built
#   for a split/aftermath back-face gap) — the Aura-reminder wording here
#   ("Enchanted creature gets +1/+1 and has KEYWORD") uses a different verb
#   ("has", not "gains") and subject ("Enchanted creature", not "target
#   creature"), so it does not match. Widening that SHARED regex risks
#   unaudited over-fire on other text-only-tree consumers (the split/
#   aftermath gap it was built for); a dedicated marker-and-lane-edit (the
#   Wicked/Junk precedent above) is the safer fix but needs its own gate
#   design against ``_keyword_grant_lanes``'s multi-branch structure — not
#   done this session.
# * Sorcerer (+1/+1 + granted "whenever attacks, scry 1") — there is no
#   "scry doer" lane at all in ``crosswalk_signals`` today:
#   ``_scry_surveil_matters`` is explicitly the PAYOFF-only lane ("a bare
#   Scry EFFECT node … never fires; doers ride the ported
#   ``topdeck_selection``"), and ``topdeck_selection`` itself is unit/
#   typed-node-based with no oracle-text fallback branch to extend safely.
#   Needs its own marker-and-lane-edit design; not done this session.
_KNOWN_TOKEN_WIRED_DISPLAY_NAMES = frozenset(
    {
        "Mutagen",
        "Young Hero",
        "Powerstone",
        "Lander",
        "Gold",
        "Map",
        "Junk",
        "Wicked",
    }
)


def _iter_raw_token_effects(node: object) -> Iterator[dict]:
    """Depth-first walk of a RAW (pre-strict-load) phase JSON fragment,
    yielding every ``dict`` that is a ``Token`` effect node (a CreateToken
    payload — always carries its own ``name``). Deliberately independent of
    the typed mirror schema: this substrate must still see a Token node whose
    OTHER fields have drifted (unrecognized-tag drift raises inside
    ``strict_load_card``, never reaches here at all — this walk is plain
    dict/list recursion over the untyped JSON)."""
    if isinstance(node, dict):
        if node.get("type") == "Token" and "name" in node:
            yield node
        for v in node.values():
            yield from _iter_raw_token_effects(v)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_raw_token_effects(item)


def _known_token_display_name_candidates(token_name: str) -> tuple[str, ...]:
    """Normalize a Token node's own printed ``name`` against toml
    ``display_name`` conventions. phase's Role-token Token nodes carry the
    FULL subtype suffix ("Young Hero Role"); the toml's ``display_name`` is
    just the Role's proper name ("Young Hero") — the ``token.body.subtypes``
    array is what carries "Role" instead. Tries the exact name first, then
    the suffix-stripped form."""
    name = (token_name or "").strip()
    if not name:
        return ()
    if name.endswith(" Role"):
        return (name, name[: -len(" Role")])
    return (name,)


_KNOWN_TOKENS_FALLBACK_ASSET = "known_tokens_fallback.toml"


def _parse_known_tokens_toml(text: str) -> dict[str, dict] | None:
    """toml text -> ``{id: {display_name, rules_text, core_types, subtypes,
    supertypes}}``, or ``None`` on any parse failure. Shared by the live
    fetch and the committed fallback below."""
    import tomllib

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    entries = data.get("token")
    if not isinstance(entries, list):
        return None
    out: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tid = entry.get("id")
        if not tid:
            continue
        body = entry.get("body") or {}
        out[tid] = {
            "display_name": body.get("display_name") or "",
            "rules_text": (entry.get("rules_text") or "").strip(),
            "core_types": tuple(body.get("core_types") or ()),
            "subtypes": tuple(body.get("subtypes") or ()),
            "supertypes": tuple(body.get("supertypes") or ()),
        }
    return out


@functools.cache
def _known_tokens_index() -> dict[str, dict] | None:
    """toml token ``id`` -> ``{display_name, rules_text, core_types,
    subtypes, supertypes}``.

    Prefers the LIVE tag-pinned ``known-tokens.toml`` (:func:`_phase.
    ensure_known_tokens` — the full ~600-entry file, fetched once and
    cached), so a future widening of ``_KNOWN_TOKEN_WIRED_DISPLAY_NAMES``
    needs no code change here. Falls back to the small COMMITTED subset at
    ``mtg_utils/data/known_tokens_fallback.toml`` — carrying only the
    identities this task actually wires — whenever the live file can't be
    fetched/read (offline, cold cache, CI: :mod:`mtg_utils.testkit`-driven
    tests must stay network-independent). ``None`` only if BOTH fail (the
    fallback ships in the package, so this is theoretical short of a
    corrupted install)."""
    from mtg_utils import _phase

    path = _phase.ensure_known_tokens()
    if path is not None:
        try:
            text = path.read_text()
        except OSError:
            text = None
        if text is not None:
            parsed = _parse_known_tokens_toml(text)
            if parsed is not None:
                return parsed

    fallback = (
        Path(__file__).resolve().parent.parent / "data" / _KNOWN_TOKENS_FALLBACK_ASSET
    )
    try:
        text = fallback.read_text()
    except OSError:
        return None
    return _parse_known_tokens_toml(text)


def _known_token_tree(entry: dict, *, oracle_id: str) -> ConceptTree | None:
    """One matched known-tokens.toml entry as a zero-unit text-only
    ``ConceptTree`` (the ADR-0038 W2c shape), or ``None`` for a blank
    ``rules_text`` (nothing to carry — e.g. a vanilla creature token that
    already fully round-trips through the Token node's own printed body)."""
    from mtg_utils._card_ir.crosswalk import ConceptTree

    rules_text = entry["rules_text"]
    if not rules_text:
        return None
    return ConceptTree(
        name=entry["display_name"],
        oracle_id=oracle_id,
        units=(),
        card_types=entry["core_types"],
        card_subtypes=entry["subtypes"],
        card_supertypes=entry["supertypes"],
        cmc=0,
        power=None,
        has_printed_cost=False,
        oracle=rules_text,
    )


def _known_token_trees(rec: dict, *, oracle_id: str) -> list[ConceptTree]:
    """Every predefined-token ability tree ``rec`` (one raw phase face
    record) creates, gap-gated to Token nodes phase parsed NO ability
    substance for (see the module comment above). Empty whenever the
    known-tokens index is unavailable, the card carries no
    ``related_token_ids``, or every Token node phase already fully parsed."""
    index = _known_tokens_index()
    if not index:
        return []
    related_ids = (rec.get("metadata") or {}).get("related_token_ids") or []
    candidates = {
        index[tid]["display_name"].casefold(): index[tid]
        for tid in related_ids
        if tid in index
        and index[tid]["display_name"] in _KNOWN_TOKEN_WIRED_DISPLAY_NAMES
    }
    if not candidates:
        return []
    trees: list[ConceptTree] = []
    seen: set[str] = set()
    for token_node in _iter_raw_token_effects(rec):
        if token_node.get("static_abilities") or token_node.get("keywords"):
            continue  # phase already parsed something for this token — leave it
        entry = None
        for cand in _known_token_display_name_candidates(
            str(token_node.get("name") or "")
        ):
            entry = candidates.get(cand.casefold())
            if entry is not None:
                break
        if entry is None or entry["display_name"] in seen:
            continue
        seen.add(entry["display_name"])
        tree = _known_token_tree(entry, oracle_id=oracle_id)
        if tree is not None:
            trees.append(tree)
    return trees


def build_trees(
    oid: str, recs: Sequence[dict], bulk: dict | None = None
) -> tuple[ConceptTree, ...]:
    """The per-face ``ConceptTree`` tuple for ``oid`` from EXPLICIT phase face
    records — pure (no caching, no ``_phase_record_index`` / ``ensure_card_data``
    I/O beyond the always-committed mirror schema fixture and the known-tokens
    index's own lazy ``functools.cache``).

    :func:`trees_for` wraps this with the production oid→records lookup +
    memo; :mod:`mtg_utils.testkit` calls it directly against the committed
    snapshot's stored raw phase records (ADR-0039 task #80 step 5), so a
    signal test builds the SAME trees production would with zero
    ``_phase.ensure_card_data`` dependency (no phase cache / network in CI).
    See :func:`trees_for` for the per-face / ``bulk`` W2c contract this
    mirrors exactly. Task #92 adds one more per-rec extension: every
    predefined token ``rec`` creates whose OWN ability text phase's parse
    left blank gets an extra text-only tree appended (see the module comment
    above :func:`_known_token_trees`) — independent of ``schema``/strict-load
    succeeding, since it reads the raw JSON directly."""
    schema = _committed_schema()
    if schema is None:
        return ()
    from mtg_utils._card_ir.crosswalk import build_concept_tree
    from mtg_utils._card_ir.mirror import MirrorDriftError, strict_load_card

    trees: list[ConceptTree] = []
    for rec in recs:
        nm = rec.get("name") or ""
        try:
            root = strict_load_card(rec, schema, name=nm)
        except MirrorDriftError:
            root = None
        if root is not None:
            trees.append(build_concept_tree(root, name=nm, oracle_id=oid))
        trees.extend(_known_token_trees(rec, oracle_id=oid))
    if bulk is not None:
        trees.extend(_text_only_trees(bulk, tuple(recs), oracle_id=oid))
    return tuple(trees)


def seed_trees(oid: str, trees: tuple[ConceptTree, ...]) -> None:
    """Pre-populate the trees memo for ``oid`` (testkit only).

    :func:`trees_for` checks ``_TREES_MEMO`` BEFORE touching
    ``_phase_record_index`` / ``_phase.ensure_card_data`` — so a caller that
    seeds the memo first makes every downstream ``trees_for`` call (the
    production ``_crosswalk_merge`` path included) CI-safe: no phase cache,
    no network, byte-identical trees to what production would build from a
    live phase install. ``mtg_utils.testkit.test_signals`` is the one caller."""
    _TREES_MEMO[oid] = trees


def trees_for(card: dict, bulk: dict | None = None) -> tuple[ConceptTree, ...]:
    """The candidate's Layer-2 concept trees by ``oracle_id`` — one per phase
    face record (plus ADR-0038 W2c text-only trees, see below), empty when
    unavailable.

    A DFC / split card shares one ``oracle_id`` across its faces, and phase
    emits one ``card-data.json`` record per face; each face is strict-loaded
    against the committed mirror schema and run through ``build_concept_tree``
    independently — NEVER merged into one tree (a merged tree would corrupt
    card-level reads like ``is_type`` / cmc that only make sense per-face).
    Callers union the per-tree signals instead (ADR-0035/0038 task #74; the
    same per-face-union-of-signals shape ``crosswalk_diff.py`` already
    measures the corpus against). Built lazily then memoized as a tuple (see
    :func:`build_trees` for the pure per-oid construction; :func:`seed_trees`
    lets a caller pre-populate the memo — CI-safe, no phase cache needed). An
    empty tuple covers no oracle_id, no phase record / schema, and every face
    drifting from the committed schema — each degrading the hybrid
    (``signals.extract_signals_hybrid``) to an empty signal list for that
    card, not a crash (ADR-0039 task #80 step 6: there is no legacy IR path
    left to fall back to; the full commander/brawl-legal corpus census found
    this tuple is never actually empty for a sanctioned card).

    ``bulk`` (ADR-0038 W2c) is the full Scryfall/MTGJSON-shaped record (with
    ``card_faces``) for the same card, supplied explicitly rather than read
    off ``card`` — every OTHER caller (every existing pinned test, the
    ``ir_for`` Seam-B API) stays a pure oracle_id join with ``bulk=None``, the
    default; only the production caller (``signals.py``, which already holds
    the bulk record) threads it. When given, a bulk face with no name-matched
    phase record among this oid's group gets one additional zero-unit
    text-only ``ConceptTree`` carrying its bulk oracle text verbatim (the
    aftermath-second-half gap; see the module comment above). The per-oid
    memo assumes ``bulk`` is supplied consistently across calls for the same
    oid within a process, matching every other cache in this module."""
    oid = card.get("oracle_id") or ""
    if not oid:
        return ()
    if oid in _TREES_MEMO:
        return _TREES_MEMO[oid]
    index = _phase_record_index()
    if index is None:
        _TREES_MEMO[oid] = ()
        return ()
    recs = index.get(oid)
    if not recs:
        _TREES_MEMO[oid] = ()
        return ()
    out = build_trees(oid, recs, bulk=bulk)
    _TREES_MEMO[oid] = out
    return out
