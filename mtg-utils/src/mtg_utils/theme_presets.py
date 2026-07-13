"""Theme presets for archetype detection.

A canonical, tested library of named matchers for common MTG mechanics.
Each preset bundles a keyword list (matched against Scryfall's ``keywords``
array), a list of regex patterns (matched against oracle text), and/or a
STRUCTURAL VIEW over the production signal extractor (see "Structural
views" below). Callers use ``get_preset(name).matches(card)`` to test a
single card.

Presets ship with test fixtures (``should_match`` / ``should_not_match``
card-name tuples). ``tests/mtg-utils/test_theme_presets.py`` pins each
preset against those fixtures so regex drift is caught before landing.

# Why keywords, not just regex

Scryfall's ``keywords`` array is the authoritative source for named
keyword abilities. Matching by keyword avoids the false-positive problem
regex has with flavor text, reminder text on older printings, and cards
that mention a keyword without having it (e.g. "Target creature gets
flying"). When a theme is a keyword ability (flying, scry, flashback,
cascade, cycling, …) the preset uses the keyword list only.

Regex used to be reserved for FUNCTIONAL themes without a matching
keyword and without a structural view yet (removal, mill, reanimate,
counterspells, burn, tokens, …) — task #86 flipped ``removal``, the last
one, so no BUILT-IN preset carries a raw ``patterns`` arm anymore. The
only live regex path left is USER-SUPPLIED: ``archetype_audit``'s
``--theme name=regex`` CLI flag and a cube's ``designer_intent.
stated_archetypes`` custom-regex entries (``_archetype_resolver.
CustomRegexArchetype``) — a cube author's own pattern for a theme the
presets don't name at all, never a second detector shadowing the signal
extractor. Both build their ``Preset``/matcher directly rather than
through this module's (now-unused) ``patterns`` arm plumbing.

# Structural views (task #83, ADR-0035/0039)

A regex/keyword preset is a hand-rolled SECOND detector shadowing the
production signal extractor (``mtg_utils._deck_forge.signals.
extract_signals_hybrid``, the crosswalk read over phase-rs's parse). Per
Dan's directive (2026-07-12), presets are being migrated one lane at a
time into DECLARATIVE VIEWS over that extractor's own output — never a
third detector system:

- ``signal_keys``: the card matches if its production signal keyset
  (memoized per ``oracle_id`` — see :func:`_signal_keys_for`) intersects
  these keys. This is the primary conversion mechanism — most presets
  map onto exactly one signal key (``landfall`` → the ``landfall`` key,
  ``sacrifice-outlet`` → ``sacrifice_outlets``, …).
- ``keywords`` stays live and UNIONS with ``signal_keys`` where a
  Scryfall keyword-array fact isn't fully folded into the signal lane
  (a keyword-only maker the effect lane doesn't independently derive —
  ``landfall``'s ``Landfall`` keyword is one such case; see the
  per-preset conversion note).
- ``concept``: an OPTIONAL named predicate, ``(card) -> bool``, for a
  fact the signal system doesn't carry at all. Two motivating cases so
  far: (1) a target's PERMANENT TYPE — ``removal``/``exile_removal``/
  ``mass_removal``/``edict_makers`` all emit ``subject=""``, so "this
  card is removal" never says WHICH type it answers; the 10 type-scoped
  removal/edict presets (creature/artifact/enchantment/land/planeswalker/
  universal x removal/edict) bind ``_removal_edict_concept`` to a target
  permanent type. (2) a shared key covering several distinct facts, or a
  fact needing a different query mode than the key index caches — the
  'graveyard-return' / 'self-mill' / 'card-draw' / 'blink' conversions
  each bind a thin per-card glue wrapper (``_graveyard_return_concept``,
  ``_self_mill_concept``, ``_etb_bulk_draw_concept``,
  ``_blink_maker_concept``). In both cases a concept predicate MUST reuse
  an existing crosswalk lane helper (``mtg_utils._deck_forge.
  crosswalk_signals`` — e.g. ``removal_edict_targets_type``) rather than
  hand-roll a new text scan — the TREE-level logic lives next to the lane
  helper(s) it reuses, with the same docstring discipline as the lane
  itself; the per-card glue (resolving the card's per-face trees, or —
  for ``blink`` — calling ``extract_signals_hybrid`` directly) lives in
  THIS module next to :func:`_signal_keys_for`. Because
  :meth:`Preset.matches` only ORs its arms (there is no AND), a concept
  predicate that needs "is removal/edict of SOME kind AND targets THIS
  type" does the full walk itself rather than intersecting against
  ``signal_keys`` at the ``Preset`` level.

A converted preset drops its ``patterns`` (the regex is superseded by the
view, not run in parallel) and keeps ``keywords`` only for facts the
signal system genuinely doesn't reproduce. Every arm — ``keywords``,
``patterns``, ``type_patterns``, ``layouts``, ``signal_keys``,
``concept`` — still combines with OR in :meth:`Preset.matches`, so a
partially-converted registry (some presets structural, most still regex)
behaves identically from every existing call site's point of view; the
public API (``Preset.matches`` / ``get_preset`` / ``matches`` /
``list_presets`` / ``PRESETS``) is unchanged.

# Public API

- :class:`Preset` — frozen dataclass with name, description, match
  conditions, and test fixtures.
- :func:`get_preset` — look up a preset by name.
- :func:`matches` — convenience wrapper around ``get_preset(name).matches(card)``.
- :func:`list_presets` — ``name -> description`` for discoverability.
- :data:`PRESETS` — the full registry as a frozen dict.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from mtg_utils.card_classify import get_oracle_text

if TYPE_CHECKING:
    # Type-only: mtg_utils._card_ir.crosswalk has no _deck_forge dependency
    # (verified), so this import is safe even at runtime, but every OTHER
    # crosswalk-adjacent import in this module is lazy (see _signal_keys_for
    # / _concept_any_face's own docstrings) to dodge the _deck_forge.
    # _signals_regex -> theme_presets cycle — keeping this one TYPE_CHECKING-
    # only too keeps the whole module's import discipline uniform.
    from mtg_utils._card_ir.crosswalk import ConceptTree

# Matches a count in digit form, word form (one..twelve), or X. IGNORECASE
# is applied at pattern compile time, so word forms match "Three" too.
# Unused by any PRESETS entry as of task #86 (the removal flip retired the
# last built-in preset with a raw ``patterns`` arm) — kept for a future
# genuinely-textual fact, same reasoning as :func:`_rx` below.
_COUNT = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|X)"


@dataclass(frozen=True)
class Preset:
    """A named, testable theme matcher.

    A card matches if ANY declared condition matches:

    - ``keywords``: the card's ``keywords`` array contains any of these
      (case-insensitive).
    - ``patterns``: any regex matches the card's oracle text.
    - ``type_patterns``: any regex matches the card's ``type_line``.
      Useful for kindred/tribal themes where the card's identity comes
      from its creature type (e.g., Llanowar Elves is an Elf whether or
      not its oracle mentions the word).
    - ``layouts``: the card's Scryfall ``layout`` field equals one of
      these (case-sensitive, matching Scryfall values like
      ``"adventure"``, ``"prototype"``, ``"split"``, ``"saga"``).
    - ``signal_keys``: the card's production signal keyset (see the
      module docstring's "Structural views" section) intersects these
      keys. Empty for every not-yet-converted preset.
    - ``concept``: an optional ``(card) -> bool`` predicate for a fact
      neither the regex arms nor the signal system carry. ``None`` for
      every preset today.

    All six may be set; they combine with OR. ``should_match`` and
    ``should_not_match`` are card-name fixtures used by the test suite —
    for a preset with a non-empty ``signal_keys``/``concept``, the golden
    fixture test routes these through ``mtg_utils.testkit`` (a real
    Scryfall record + real crosswalk trees) instead of the inline
    synthetic ``FIXTURE_CARDS`` dict, since the structural arms need a
    real ``oracle_id`` to resolve anything (see
    ``test_theme_presets.py``'s structural-view test class).
    """

    name: str
    description: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = ()
    type_patterns: tuple[re.Pattern[str], ...] = ()
    layouts: tuple[str, ...] = ()
    signal_keys: tuple[str, ...] = ()
    concept: Callable[[dict], bool] | None = None
    should_match: tuple[str, ...] = ()
    should_not_match: tuple[str, ...] = ()

    def matches(self, card: dict) -> bool:
        if self.keywords:
            card_kws = {k.lower() for k in (card.get("keywords") or [])}
            if card_kws & {k.lower() for k in self.keywords}:
                return True
        if self.patterns:
            oracle = get_oracle_text(card)
            if any(p.search(oracle) for p in self.patterns):
                return True
        if self.type_patterns:
            type_line = card.get("type_line") or ""
            if any(p.search(type_line) for p in self.type_patterns):
                return True
        if self.layouts and card.get("layout") in self.layouts:
            return True
        if self.signal_keys and _signal_keys_for(card) & set(self.signal_keys):
            return True
        return self.concept is not None and self.concept(card)


# ─── Structural-view seam (task #83, ADR-0035/0039) ───────────────────────
#
# oracle_id -> frozenset(production signal key) index, populated LAZILY —
# one entry per card the FIRST time any signal_keys-bearing preset sees it,
# never eagerly for the whole pool. A card_search.py-style full-pool scan
# still pays one extract_signals_hybrid call per card overall (same as
# before conversion — every card is visited once regardless), but this
# cache is what makes a SECOND structural preset scanning the SAME pool (or
# the same card revisited by a different consumer in one process) free: it
# reuses the already-computed key set instead of re-running the crosswalk
# lanes. extract_signals_hybrid itself already memoizes the expensive part
# (_ir_lookup.trees_for's per-face ConceptTree resolution) per oracle_id, so
# this index is a second, cheaper memoization layer on top of that one —
# the (key, scope, subject) -> Signal lane pass, not the tree build.
_SIGNAL_KEY_INDEX: dict[str, frozenset[str]] = {}


def _signal_keys_for(card: dict) -> frozenset[str]:
    """CARD's production signal-key set (memoized per ``oracle_id``).

    Empty for a card with no ``oracle_id`` (a synthetic fixture — the same
    "no oracle_id" degradation ``extract_signals_hybrid`` documents) or
    whose oracle_id resolves to no phase parse at all — a structural-view
    preset just never matches such a card, exactly like the ``keywords`` /
    ``patterns`` arms matching nothing on a card missing the field they
    read. Imports ``mtg_utils._deck_forge.signals`` LAZILY inside the
    function body (never at module import time): ``_deck_forge.
    _signals_regex`` imports ``theme_presets.get_preset``, so a top-level
    import here would create an import-time cycle racing partial module
    initialization the first time either module loads.
    """
    oid = card.get("oracle_id")
    if not oid:
        return frozenset()
    cached = _SIGNAL_KEY_INDEX.get(oid)
    if cached is not None:
        return cached
    from mtg_utils._deck_forge.signals import extract_signals_hybrid

    keys = frozenset(sig.key for sig in extract_signals_hybrid(card))
    _SIGNAL_KEY_INDEX[oid] = keys
    return keys


def _concept_any_face(card: dict, predicate: Callable[[ConceptTree], bool]) -> bool:
    """True if ``predicate(tree)`` holds for any of CARD's per-face concept
    trees — mirrors ``extract_signals_hybrid``'s own per-face union (a
    DFC's two faces are read independently, never merged into one tree).
    ``False`` for a card with no ``oracle_id`` / no phase parse, the same
    degradation :func:`_signal_keys_for` documents for the ``signal_keys``
    arm. Shared plumbing for the tree-level concept predicates below —
    each names the crosswalk lane helper it actually reuses in its own
    docstring; this function only resolves the trees.

    Runs each tree through the SAME two corrections passes
    ``crosswalk_signals.extract_crosswalk_signals`` applies before handing
    a tree to any lane (``apply_overlay_corrections`` — ADR-0035 Stage-3b
    concept-overlay fixes, e.g. a dig-into-play flipped to cheat_play; then
    ``apply_tree_synthesis`` — ADR-0037 synthetic concept-nodes for
    genuine phase-parse gaps, e.g. the ``group_hug_draw`` "each player
    draws" recovery). A concept predicate reading a RAW tree would silently
    diverge from every ``signal_keys``-based lane it sits beside in the
    same preset's OR (a corrected node the lane sees, the predicate
    wouldn't) — this keeps the two arms reading the identical tree shape.

    Lazily imports ``mtg_utils._deck_forge._ir_lookup`` for the same
    import-cycle reason :func:`_signal_keys_for` imports ``_deck_forge.
    signals`` lazily.
    """
    if not card.get("oracle_id"):
        return False
    from mtg_utils._card_ir.overlay_corrections import apply_overlay_corrections
    from mtg_utils._card_ir.tree_synthesis import apply_tree_synthesis
    from mtg_utils._deck_forge._ir_lookup import trees_for

    for raw_tree in trees_for(card):
        corrected = apply_overlay_corrections(raw_tree)
        corrected = apply_tree_synthesis(corrected)
        if predicate(corrected):
            return True
    return False


def _graveyard_return_concept(card: dict) -> bool:
    """concept arm for the 'graveyard-return' preset (task #83): true when
    ANY face's ``ChangeZone`` reads a Graveyard->Hand direction. See
    ``crosswalk_signals.graveyard_return_direction`` / ``_graveyard_makers``'s
    own docstring for why this direction isn't exposed on the merged
    ``graveyard_makers`` Signal (``subject=""``) — raw ``signal_keys``
    membership on that key can't discriminate this preset from
    reanimate/self-mill, which share the same key for their OTHER two
    directions."""
    from mtg_utils._deck_forge.crosswalk_signals import graveyard_return_direction

    return _concept_any_face(card, graveyard_return_direction)


def _self_mill_concept(card: dict) -> bool:
    """concept arm for the 'self-mill' preset (task #83): true when ANY
    face fills YOUR OWN graveyard from YOUR OWN library. See
    ``crosswalk_signals.self_mill_fill`` for the two structural shapes it
    reads (a self-scoped ``Mill``, or a filter ``Dig`` whose
    ``rest_destination`` is Graveyard) — deliberately NOT a raw
    ``signal_keys`` union of ``mill_makers``/``graveyard_makers``/
    ``topdeck_selection``, which would match Contingency Plan (a
    look-then-reorder-to-bottom effect, never a mill) through
    ``topdeck_selection``'s unconditional Scry/Surveil arm."""
    from mtg_utils._deck_forge.crosswalk_signals import self_mill_fill

    return _concept_any_face(card, self_mill_fill)


def _etb_bulk_draw_concept(card: dict) -> bool:
    """concept arm for the 'card-draw' preset (task #83): true when ANY
    face draws 2+ cards off its own ETB trigger (Mulldrifter). See
    ``crosswalk_signals.etb_bulk_draw``. Unions (OR) with this preset's
    ``signal_keys=("card_draw_engine",)`` arm; the two arms are
    structurally disjoint by construction (``card_draw_engine``'s bulk
    gate excludes an ``enters`` unit, ``etb_bulk_draw`` requires one), so
    the OR never double-counts a card under both arms."""
    from mtg_utils._deck_forge.crosswalk_signals import etb_bulk_draw

    return _concept_any_face(card, etb_bulk_draw)


def _blink_maker_concept(card: dict) -> bool:
    """concept arm for the 'blink' preset (task #83): true when CARD
    carries a MAKER-half ``blink_flicker`` signal (Flickerwisp/Ephemerate/
    Soulherder), never :func:`~mtg_utils._deck_forge.crosswalk_signals.
    apply_membership_floor`'s "worth blinking" payoff cross-open (Academy
    Journeymage/Mulldrifter). See ``crosswalk_signals.
    blink_flicker_maker_present``. Unions (OR) with this preset's
    ``signal_keys=("self_blink",)`` arm — a genuinely different
    self-flicker engine (CR 611.2b, a card exiling and returning ITSELF,
    Aetherling) sharing no cards with the maker-of-OTHERS shape this
    predicate reads."""
    from mtg_utils._deck_forge.crosswalk_signals import blink_flicker_maker_present

    return blink_flicker_maker_present(card)


def _plus_one_counters_self_grow_concept(card: dict) -> bool:
    """concept arm for the 'plus-one-counters' preset (task #85): the
    ``self_counter_grow`` KEY minus its ``synth_self_power_scale`` cross-
    open (Esper Sentinel, the Khenra cycle — a card whose value scales
    with its OWN power, never a +1/+1 counter reference). See
    ``crosswalk_signals.self_counter_grow_narrow`` for why the raw key is
    too broad for THIS preset specifically. Unions (OR) with this
    preset's ``signal_keys=("plus_one_makers", "plus_one_matters",
    "counter_distribute")`` arm."""
    from mtg_utils._deck_forge.crosswalk_signals import self_counter_grow_narrow

    return _concept_any_face(card, self_counter_grow_narrow)


def _rx(*patterns: str) -> tuple[re.Pattern[str], ...]:
    """Compile a tuple of patterns with IGNORECASE.

    Unused by any PRESETS entry as of task #86 (the ``removal`` flip
    retired the last built-in preset with a raw ``patterns`` arm) — kept
    in case a future genuinely-textual fact needs it; NOT a place to add a
    second regex detector shadowing a signal (Dan's standing directive).
    """
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


def _removal_edict_concept(
    core_type: str, *, family: str = "removal", generous_any: bool = False
) -> Callable[[dict], bool]:
    """Bind a task #83 type-scoped ``concept`` predicate (creature/artifact/
    enchantment/land/planeswalker/universal x removal/edict) to a specific
    target CORE_TYPE. ``family`` selects the effect shape: "removal"
    (destroy/exile/burn/fight/shrink — the default, used by the six
    ``*-removal`` presets) or "edict" (forced sacrifice only, used by the
    six ``*-edict`` presets — a destroy/exile/burn effect is never an
    edict, CR 701.8 vs 701.21a). Reuses ``_deck_forge.crosswalk_signals.
    removal_edict_targets_type`` — the ONE lane helper every type-scoped
    preset in this registry shares (see that function's docstring, and its
    module's "Task #83 structural-view helper" section, for the target-
    filter mechanics). Imported LAZILY inside the closure for the same
    import-cycle reason :func:`_signal_keys_for` documents.
    """

    def _match(card: dict) -> bool:
        from mtg_utils._deck_forge.crosswalk_signals import (
            removal_edict_targets_type,
        )

        return removal_edict_targets_type(
            card, core_type, family=family, generous_any=generous_any
        )

    return _match


# ─── Evergreen keyword abilities ──────────────────────────────────────────
# These match via the card's ``keywords`` array — no regex needed.

_EVERGREEN_KEYWORDS: tuple[Preset, ...] = (
    Preset(
        name="flying",
        description="Creature has flying (evergreen).",
        keywords=("Flying",),
        should_match=("Serra Angel", "Baleful Strix"),
        should_not_match=("Llanowar Elves", "Lightning Bolt"),
    ),
    Preset(
        name="vigilance",
        description="Creature has vigilance (evergreen).",
        keywords=("Vigilance",),
        should_match=("Serra Angel",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="trample",
        description="Creature has trample (evergreen).",
        keywords=("Trample",),
        should_match=("Goldvein Hydra",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="haste",
        description="Creature has haste (evergreen).",
        keywords=("Haste",),
        should_match=("Goblin Guide", "Monastery Swiftspear"),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="deathtouch",
        description="Creature has deathtouch (evergreen).",
        keywords=("Deathtouch",),
        should_match=("Baleful Strix",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="lifelink",
        description="Creature has lifelink (evergreen).",
        keywords=("Lifelink",),
        should_match=("Tymna the Weaver",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="first-strike",
        description="Creature has first strike (evergreen).",
        keywords=("First strike",),
        should_match=("White Knight",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="double-strike",
        description="Creature has double strike (evergreen).",
        keywords=("Double strike",),
        should_match=("Fury",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="reach",
        description="Creature has reach (evergreen).",
        keywords=("Reach",),
        should_match=("Giant Spider",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="menace",
        description="Creature has menace (evergreen).",
        keywords=("Menace",),
        should_match=("Obeka, Splitter of Seconds",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="defender",
        description="Creature has defender (evergreen).",
        keywords=("Defender",),
        should_match=("Wall of Omens",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="flash",
        description="Permanent has flash (evergreen).",
        keywords=("Flash",),
        should_match=("Snapcaster Mage", "Dictate of Erebos"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="hexproof",
        description="Permanent has hexproof (evergreen).",
        keywords=("Hexproof",),
        should_match=("Invisible Stalker",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="indestructible",
        description="Permanent has indestructible (evergreen).",
        keywords=("Indestructible",),
        should_match=("Darksteel Myr",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="ward",
        description="Permanent has ward (evergreen).",
        keywords=("Ward",),
        # Note: Star Whale grants ward to OTHER creatures but doesn't have
        # it itself, so it isn't a valid fixture for this preset.
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="protection",
        description="Permanent has protection from something (evergreen).",
        keywords=("Protection",),
        should_match=("White Knight",),
        should_not_match=("Lightning Bolt",),
    ),
)

# ─── Named non-evergreen keyword abilities ────────────────────────────────

_KEYWORD_ABILITIES: tuple[Preset, ...] = (
    Preset(
        name="scry",
        description="Card performs scry N (look at top, may bottom).",
        keywords=("Scry",),
        # Aang's Iceberg has Scry in its keywords array (its waterbend
        # ability scries), so it matches via the Scry keyword directly.
        should_match=("Preordain", "Omen of the Sun", "Magma Jet", "Aang's Iceberg"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="surveil",
        description="Card performs surveil N (look at top, may discard).",
        keywords=("Surveil",),
        should_match=("Thought Erasure", "Notion Rain", "Sinister Sabotage"),
        # Ransack the Lab is sometimes misremembered as surveil but its actual
        # oracle text is "Look at the top three ... put the rest into your
        # graveyard" — no Surveil keyword.
        should_not_match=("Lightning Bolt", "Ransack the Lab"),
    ),
    Preset(
        name="cascade",
        description="Spell has cascade.",
        keywords=("Cascade",),
        should_match=("Bloodbraid Elf", "Shardless Agent"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="flashback",
        description="Spell has flashback.",
        keywords=("Flashback",),
        should_match=("Lingering Souls", "Faithless Looting", "Deep Analysis"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="kicker",
        description="Spell has a kicker cost.",
        keywords=("Kicker",),
        should_match=("Gatekeeper of Malakir",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="cycling",
        description="Card has cycling.",
        keywords=("Cycling",),
        should_match=("Ketria Triome",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="evoke",
        description="Creature has evoke.",
        keywords=("Evoke",),
        should_match=("Mulldrifter", "Fury"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="ninjutsu",
        description="Creature has ninjutsu.",
        keywords=("Ninjutsu",),
        should_match=("Fallen Shinobi",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="exalted",
        description="Permanent has exalted.",
        keywords=("Exalted",),
        should_match=("Noble Hierarch", "Qasali Pridemage"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="prowess",
        description="Creature has prowess.",
        keywords=("Prowess",),
        should_match=("Monastery Swiftspear", "Abbot of Keral Keep"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="revolt",
        description="Card cares about revolt.",
        keywords=("Revolt",),
        should_match=("Fatal Push",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="investigate",
        description="Card creates a Clue (investigate).",
        keywords=("Investigate",),
        should_match=("Thraben Inspector",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="landfall",
        description=(
            "Card has landfall (whenever a land enters under your control), "
            "OR is a landfall ENABLER the crosswalk `landfall` signal folds "
            "in: casts a land from the graveyard (Crucible of Worlds, "
            "Ramunap Excavator), grants extra land drops (Exploration, "
            "Azusa), or returns lands from the graveyard to the "
            "battlefield — all read the same 'more land-ETB triggers' "
            "archetype the old oracle-text regex only caught the trigger "
            "half of (task #83 structural-view conversion)."
        ),
        # Keyword arm UNIONS with the signal_keys view rather than being
        # subsumed by it: the scoping census found landfall is one of the
        # mechanics whose keyword-only makers the crosswalk effect lane can
        # miss (a card whose ONLY landfall tell is the bare Scryfall
        # `Landfall` array entry, no oracle-text form the lane's structural
        # reads independently derive). Dropping this arm risks a silent
        # keyword-only regression the corpus census didn't specifically
        # rule out; keeping it is a one-line, zero-cost belt-and-suspenders
        # union — CR 701.19 (Landfall keyword action).
        keywords=("Landfall",),
        signal_keys=("landfall",),
        should_match=("Courser of Kruphix", "Bloodghast"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="dredge",
        description="Card has dredge (BANNED in shared-library format).",
        keywords=("Dredge",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="miracle",
        description="Spell has miracle (BANNED in shared-library format).",
        keywords=("Miracle",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="storm",
        description="Spell has storm.",
        keywords=("Storm",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="infect",
        description=(
            "Creature has infect — a STATIC ability (CR 702.90a) that modifies how "
            "its damage is dealt: damage to players becomes poison counters instead "
            "of life loss (702.90b) and damage to creatures is dealt as -1/-1 "
            "counters (702.90c). Distinct from Poisonous/Toxic, which add poison "
            "ON TOP of normal damage and never touch creatures."
        ),
        keywords=("Infect",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="toxic",
        description="Creature has toxic.",
        keywords=("Toxic",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="poison",
        description=(
            "Creature has poisonous — a TRIGGERED ability (CR 702.70a) that gives a "
            "player N poison counters when it deals combat damage, IN ADDITION to "
            "the normal damage. Unlike Infect it does not modify the damage and does "
            "nothing to creatures (no -1/-1 counters)."
        ),
        keywords=("Poisonous",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="delve",
        description="Spell has delve.",
        keywords=("Delve",),
        should_match=("Murderous Cut",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="mill",
        description=(
            "Card has the Mill keyword action (puts cards into a "
            "graveyard from a library). Covers both self-mill and "
            "targeted mill."
        ),
        keywords=("Mill",),
        should_match=("Stitcher's Supplier",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="suspend",
        description="Card has suspend.",
        keywords=("Suspend",),
        should_match=("Star Whale", "Ancestral Vision"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="undying",
        description="Creature has undying.",
        keywords=("Undying",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="persist",
        description="Creature has persist.",
        keywords=("Persist",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="equip",
        description="Equipment with an equip cost.",
        keywords=("Equip",),
        should_match=("Skullclamp", "Helm of the Host"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="paradigm",
        description=(
            "Spell-copy: exile this spell on resolution. After the first "
            "spell with this name resolves, you may cast a copy of it "
            "from exile for free at the beginning of each of your first "
            "main phases. Recurring free-cast from exile (Secrets of "
            "Strixhaven)."
        ),
        keywords=("Paradigm",),
        should_match=("Improvisation Capstone",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="prepared",
        description=(
            "Creature paired with a spell on a split face (Secrets of "
            "Strixhaven 'prepare' layout). The creature becomes prepared "
            "under a trigger condition (first main phase, attack, etc.). "
            "While prepared, you may cast the paired spell; doing so "
            "unprepares the creature. A conditional two-card single-slot "
            "design, closer in spirit to Adventure than to spell-copy."
        ),
        keywords=("Prepared",),
        layouts=("prepare",),
        should_match=("Scathing Shadelock // Venomous Words",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Individual keyword presets (cast-later / graveyard-cast / spell-copy
    # / tokens / plus-one-counters / misc) ──
    Preset(
        name="foretell",
        description=(
            "Cast-later: exile from hand for {2}, cast for foretell cost next turn or "
            "later (CR 702.145)."
        ),
        keywords=("Foretell",),
        should_match=("Scorn Effigy",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="plot",
        description=(
            "Cast-later: exile from hand, cast for its mana cost on a future turn as a "
            "sorcery (CR 702.167)."
        ),
        keywords=("Plot",),
        should_match=("Djinn of Fool's Fall",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="warp",
        description=(
            "Cast-later: cast from hand for warp cost, exile at the next end step, "
            "cast "
            "again from exile later (CR 702.185)."
        ),
        keywords=("Warp",),
        should_match=("Voidcalled Devotee",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="rebound",
        description=(
            "Cast-later: cast from hand, exile at resolution, cast from exile next "
            "turn "
            "(CR 702.88)."
        ),
        keywords=("Rebound",),
        should_match=("Unnatural Summons",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="impending",
        description=(
            "Cast-later: cast for impending cost; enters as a non-creature enchantment "
            "with time counters and becomes a creature later (CR 702.182)."
        ),
        keywords=("Impending",),
        should_match=("Lurker in the Deep",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="jump-start",
        description=(
            "Graveyard-cast: cast from graveyard by discarding a card in addition to "
            "other costs (CR 702.133)."
        ),
        keywords=("Jump-start",),
        should_match=("Surge of Acclaim",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="aftermath",
        description=(
            "Graveyard-cast: split card whose second half can only be cast from the "
            "graveyard (CR 702.127)."
        ),
        keywords=("Aftermath",),
        should_match=("Appeal // Authority",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="retrace",
        description=(
            "Graveyard-cast: cast from graveyard by discarding a land in addition to "
            "other costs (CR 702.81)."
        ),
        keywords=("Retrace",),
        should_match=("Oona's Grace",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="disturb",
        description=(
            "Graveyard-cast: cast a transformed double-faced card from the graveyard "
            "(CR 702.146)."
        ),
        keywords=("Disturb",),
        should_match=("Baithook Angler // Hook-Haunt Drifter",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="mayhem",
        description=(
            "Graveyard-cast: cast from graveyard for the mayhem cost if discarded this "
            "turn (CR 702.187)."
        ),
        keywords=("Mayhem",),
        should_match=("Spider-Islanders",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="harmonize",
        description=(
            "Graveyard-cast: cast from graveyard for a harmonize cost; tap a creature "
            "you control to reduce the cost by {1} (CR 702.180)."
        ),
        keywords=("Harmonize",),
        should_match=("Ureni's Counsel",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="casualty",
        description=(
            "Spell-copy: as you cast, sacrifice a creature with power N or greater to "
            "copy this spell (CR 702.153)."
        ),
        keywords=("Casualty",),
        should_match=("Cut of the Profits",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="replicate",
        description=(
            "Spell-copy: when you cast, pay the replicate cost any number of times to "
            "create that many copies (CR 702.42)."
        ),
        keywords=("Replicate",),
        should_match=("Train of Thought",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="cipher",
        description=(
            "Spell-copy: encode this spell on a creature you control; whenever that "
            "creature deals combat damage to a player, you may cast a copy of the "
            "encoded spell (CR 702.99). Niche Dimir mechanic from Gatecrash."
        ),
        keywords=("Cipher",),
        should_match=("Last Thoughts",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="conspire",
        description=(
            "Spell-copy: tap two untapped creatures sharing a color with this spell to "
            "copy it (CR 702.75)."
        ),
        keywords=("Conspire",),
        should_match=("Ghastly Discovery",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="demonstrate",
        description=(
            "Spell-copy: when you cast, you may copy it; if you do, choose an opponent "
            "to copy it too (CR 702.152)."
        ),
        keywords=("Demonstrate",),
        should_match=("Incarnation Technique",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="populate",
        description=(
            "Tokens: create a copy of a creature token you control (CR 701.36)."
        ),
        keywords=("Populate",),
        should_match=("Wake the Reflections",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="amass",
        description=(
            "Tokens: create a Zombie Army creature token or grow the one you have with "
            "+1/+1 counters (CR 701.47)."
        ),
        keywords=("Amass",),
        should_match=("Gríma Wormtongue",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="offspring",
        description=(
            "Tokens: pay extra as you cast a creature to create a 1/1 token copy of it "
            "when it enters (CR 702.175)."
        ),
        keywords=("Offspring",),
        should_match=("Fountainport Charmer",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="manifest",
        description=(
            "Tokens: put a card face down onto the battlefield as a 2/2 creature (CR "
            "701.40)."
        ),
        keywords=("Manifest",),
        should_match=("Paranormal Analyst",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="cloak",
        description=(
            "Tokens: manifest with ward {2} — a 2/2 face-down creature with ward {2} "
            "(CR 701.58)."
        ),
        keywords=("Cloak",),
        should_match=("Ransom Note",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="incubate",
        description=(
            "Tokens: create an Incubator token that transforms into a 3/3 colorless "
            "Phyrexian when 2+ +1/+1 counters are on it (CR 701.53)."
        ),
        keywords=("Incubate",),
        should_match=("Eyes of Gitaxias",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="fabricate",
        description=(
            "Tokens and +1/+1 counters: when this creature enters, choose to create N "
            "1/1 Servo tokens OR put N +1/+1 counters on it (CR 702.123)."
        ),
        keywords=("Fabricate",),
        should_match=("Accomplished Automaton",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="afterlife",
        description=(
            "Tokens: when this creature dies, create N 1/1 white-and-black Spirit "
            "tokens with flying (CR 702.135)."
        ),
        keywords=("Afterlife",),
        should_match=("Debtors' Transport",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="mobilize",
        description=(
            "Tokens: whenever this creature attacks, create N tapped-and-attacking red "
            "Warrior tokens that are sacrificed at end of combat (CR 702.181)."
        ),
        keywords=("Mobilize",),
        should_match=("Dalkovan Outrider",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="encore",
        description=(
            "Tokens: pay the encore cost and exile this creature from your graveyard "
            "to "
            "create a token copy of it for each opponent, each attacking that opponent "
            "(CR 702.141)."
        ),
        keywords=("Encore",),
        should_match=("Broodmate Tyrant",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="myriad",
        description=(
            "Tokens: whenever this creature attacks, for each other opponent, create a "
            "tapped-and-attacking token copy attacking that opponent (CR 702.116)."
        ),
        keywords=("Myriad",),
        should_match=("The Master, Multiplied",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="bolster",
        description=(
            "+1/+1 counters: choose a creature you control with the least toughness "
            "and "
            "put N +1/+1 counters on it (CR 701.39)."
        ),
        keywords=("Bolster",),
        should_match=("Dromoka's Gift",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="reinforce",
        description=(
            "+1/+1 counters: pay reinforce cost and discard this card to put N +1/+1 "
            "counters on target creature (CR 702.77)."
        ),
        keywords=("Reinforce",),
        should_match=("Burrenton Bombardier",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="monstrosity",
        description=(
            "+1/+1 counters: pay an activated cost to put N +1/+1 counters on this "
            "creature and make it monstrous (CR 701.37)."
        ),
        keywords=("Monstrosity",),
        should_match=("Gluttonous Cyclops",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="graft",
        description=(
            "+1/+1 counters: enters with N +1/+1 counters on it; may move one counter "
            "to another creature entering the battlefield (CR 702.58)."
        ),
        keywords=("Graft",),
        should_match=("Simic Initiate",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="outlast",
        description=(
            "+1/+1 counters: sorcery-speed activated ability that puts a +1/+1 counter "
            "on this creature (CR 702.107)."
        ),
        keywords=("Outlast",),
        should_match=("Disowned Ancestor",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="renown",
        description=(
            "+1/+1 counters: when this creature deals combat damage to a player for "
            "the "
            "first time, becomes renowned with N +1/+1 counters (CR 702.112)."
        ),
        keywords=("Renown",),
        should_match=("Knight of the Pilgrim's Road",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="evolve",
        description=(
            "+1/+1 counters: whenever a creature with greater power OR toughness "
            "enters "
            "under your control, put a +1/+1 counter on this creature (CR 702.100)."
        ),
        keywords=("Evolve",),
        should_match=("Adaptive Snapjaw",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="adapt",
        description=(
            "+1/+1 counters: pay adapt cost to put N +1/+1 counters on this creature "
            "if "
            "it has no +1/+1 counters (CR 701.46)."
        ),
        keywords=("Adapt",),
        should_match=("Skitter Eel",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="modular",
        description=(
            "+1/+1 counters: artifact creature enters with N +1/+1 counters; when it "
            "dies, may move them to another artifact creature (CR 702.43)."
        ),
        keywords=("Modular",),
        should_match=("Arcbound Worker",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="training",
        description=(
            "+1/+1 counters: whenever this creature and at least one other creature "
            "with greater power attack, put a +1/+1 counter on this creature (CR "
            "702.149)."
        ),
        keywords=("Training",),
        should_match=("Apprentice Sharpshooter",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="support",
        description=(
            "+1/+1 counters: put a +1/+1 counter on each of up to N target creatures "
            "(CR 701.41)."
        ),
        keywords=("Support",),
        should_match=("Lead by Example",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="tribute",
        description=(
            "+1/+1 counters: an opponent chooses whether this creature enters with N "
            "+1/+1 counters or instead triggers an additional ability (CR 702.104)."
        ),
        keywords=("Tribute",),
        should_match=("Snake of the Golden Grove",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="endure",
        description=(
            "+1/+1 counters OR tokens: modal — choose to put N +1/+1 counters on a "
            "creature or create an N/N Spirit token (CR 702.62)."
        ),
        keywords=("Endure",),
        should_match=("Amber-Plate Ainok",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="devour",
        description=(
            "+1/+1 counters: as this creature enters, you may sacrifice any number of "
            "creatures; it enters with N +1/+1 counters per creature sacrificed this "
            "way (CR 702.82)."
        ),
        keywords=("Devour",),
        should_match=("Gorger Wurm",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="dethrone",
        description=(
            "+1/+1 counters: whenever this creature attacks the player with the most "
            "life, put a +1/+1 counter on it (CR 702.105)."
        ),
        keywords=("Dethrone",),
        should_match=("Enraged Revolutionary",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="earthbend",
        description=(
            "Land animation: turn a target land you control into a 0/0 creature with "
            "haste and put N +1/+1 counters on it. When that land dies or is exiled, "
            "return it tapped (CR 701.66)."
        ),
        keywords=("Earthbend",),
        should_match=("Toph, Greatest Earthbender",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="wither",
        description=(
            "Creature damage: whenever this creature deals damage to a creature, that "
            "damage is dealt as -1/-1 counters instead (CR 702.80)."
        ),
        keywords=("Wither",),
        should_match=("Harvest Gwyllion",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="unearth",
        description=(
            "Reanimate: pay unearth cost to return this card from your graveyard to "
            "the "
            "battlefield with haste; exile it at the beginning of the next end step "
            "(CR "
            "702.84)."
        ),
        keywords=("Unearth",),
        should_match=("Gixian Recycler",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="exploit",
        description=(
            "Sacrifice trigger: when this creature enters, you may sacrifice a "
            "creature "
            "for an additional effect (CR 702.110)."
        ),
        keywords=("Exploit",),
        should_match=("Sidisi's Faithful",),
        should_not_match=("Lightning Bolt",),
    ),
    # crew/prototype/firebending are defined as standalone presets in
    # _FUNCTIONAL_PRESETS below (with richer descriptions + layout support).
)

# ─── Functional regex presets ─────────────────────────────────────────────
# Themes without a matching keyword ability. Each pattern is tested against
# the should_match / should_not_match fixtures in the test suite.

_FUNCTIONAL_PRESETS: tuple[Preset, ...] = (
    # Top-of-library manipulation: scry + surveil keywords, plus "look/reveal/
    # exile the top" non-keyword phrasings. Handles both singular ("the top
    # card") and plural ("the top four cards") forms.
    # Structural view (task #83): signal key `topdeck_selection` — OWN-
    # library top curation (CR 701.22a scry / 701.25a surveil / 701.20a
    # reveal / 701.13a exile / 701.17 mill / 401.5 look-at-top statics). See
    # `_deck_forge.crosswalk_signals._topdeck_selection` — already unions in
    # most of the old regex's territory via typed Dig/RevealTop/ExileTop/
    # MayLookAtTopOfLibrary reads, plus the "reveal from the top until you
    # find X" dig-until idiom the old regex never phrase-matched (a genuine
    # gain: Abundant Harvest, Ajani's +1). `keywords=("Scry", "Surveil")`
    # stays as a belt-and-suspenders union (the landfall precedent):
    # verified via a live investigation that a CONDITIONAL scry rider
    # (Bane's Contingency — "if that spell targets a commander you control,
    # instead counter that spell, scry 2, then draw a card") carries `Scry`
    # in its Scryfall keyword array but produces no typed Scry node in
    # phase's parse of the modal branch, so the structural arm alone misses
    # it — the raw keyword-array fact recovers it at zero cost. Residue
    # (scoping census, ~179 preset-only / ~208 candidate-only over the
    # corpus): preset-only is dominated by opponent-DIRECTED top effects
    # ("exile the top three cards of TARGET OPPONENT's library" — Ashiok,
    # Nightmare Weaver — routes to the disjoint `opp_top_exile` lane, not
    # your-own-library curation) and symmetric "look at the top of TARGET
    # PLAYER's library" riders on cards whose primary archetype lies
    # elsewhere (Architects of Will routes to `blink_flicker`/
    # `voltron_matters`); candidate-only is the genuine dig-until gain
    # above. Scope-noise, not a concept gap — the view's `topdeck_selection`
    # key is deliberately "YOUR library, top curation" per its own CR
    # grounding, and opponent-directed exile is correctly a different
    # archetype.
    Preset(
        name="top-manipulation",
        description=(
            "Any effect that looks at, reveals, scries, surveils, or "
            "exiles cards from the top of the library."
        ),
        keywords=("Scry", "Surveil"),
        signal_keys=("topdeck_selection",),
        should_match=(
            "Preordain",
            "Thought Erasure",
            "Abbot of Keral Keep",
            "Satyr Wayfinder",
        ),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Self-mill (task #83 structural-view conversion). No candidate signal
    # KEY is precise enough on its own: mill_makers is keyword-only with
    # scope "any" (self OR opponent, undiscriminated); graveyard_makers'
    # Mill arm bundles self-mill with reanimate/recursion under ONE key
    # (see graveyard-return's own conversion note below); topdeck_selection
    # fires unconditionally on any Scry/Surveil node regardless of
    # destination (would false-match Contingency Plan's reveal-then-
    # reorder-to-bottom, the preset's own long-standing false-positive
    # test case). ``self_mill_fill`` (crosswalk_signals.py) reads the two
    # precise structural shapes instead: a self-scoped Mill into Graveyard
    # (Stitcher's Supplier), or a filter ``Dig`` whose ``rest_destination``
    # is Graveyard (Satyr Wayfinder / Grisly Salvage / Ransack the Lab —
    # "look at/reveal the top N, put a card to hand, the rest into your
    # graveyard").
    Preset(
        name="self-mill",
        description=(
            "Puts cards from YOUR library into YOUR graveyard "
            "(graveyard-value, not targeted mill)."
        ),
        concept=_self_mill_concept,
        should_match=(
            "Stitcher's Supplier",
            "Satyr Wayfinder",
            "Grisly Salvage",
            "Ransack the Lab",
            # Mulch's "reveal top N, put type X to hand, rest to
            # graveyard" is a THIRD structural shape (reveal_top + a
            # sibling Graveyard-bound ChangeZone, not a Dig node) —
            # self_mill_fill's own docstring names it.
            "Mulch",
            # task #87 census residue — one representative per shape
            # class the ``self_mill_fill`` predicate's own docstring
            # names: a bare Mill buried in a trigger's ``else_ability``
            # branch, and the Dig/RevealTop "look-then-keep-one" marker
            # (a draw-replacement Dig — Underrealm Lich; a RevealTop +
            # Unimplemented-hop chain — Animal Magnetism).
            "HYDRA Troopers",
            "Underrealm Lich",
            "Animal Magnetism",
        ),
        # Contingency Plan is the canonical false-positive test case —
        # its oracle reveals top 5 but returns them to the BOTTOM of the
        # library, never the graveyard (structurally a bare Surveil node
        # with no rest_destination field at all — see self_mill_fill's
        # docstring). The task #87 census non-members are all
        # graveyard-TO-BATTLEFIELD reanimation cards (Dread Wanderer /
        # Cauldron Dance / Evershrike / Defossilize / Greasefang, Okiba
        # Boss) or dredge (The Necrobloom) — none fills the graveyard
        # from the library.
        should_not_match=(
            "Lightning Bolt",
            "Counterspell",
            "Contingency Plan",
            "Dread Wanderer",
            "Cauldron Dance",
            "Evershrike",
            "Defossilize",
            "Greasefang, Okiba Boss",
            "The Necrobloom",
        ),
    ),
    # Counterspell (task #83 structural-view conversion). ``counter_control``
    # is the stack counterspell (CR 701.6a): a Counter/CounterAll effect
    # whose target is a StackSpell (Counterspell, Mana Leak, Remand,
    # Sinister Sabotage) — see
    # ``_deck_forge.crosswalk_signals._counter_control``. Structurally
    # DISJOINT from the OTHER meaning of "counter" (+1/+1 counters) and from
    # "can't be countered" permission statics, so the view carries none of
    # the old regex's theoretical false-positive surface on those. 10
    # preset-only residue (scoping census): "counter target activated/
    # triggered ability" phrasings (Rule of Law-adjacent, Voidslime-style
    # "counter target activated or triggered ability") — the lane's own
    # target read is a StackSpell only, so a spell that counters an
    # ABILITY instead of a SPELL genuinely never fires here; a narrower,
    # more precise scope than the old "spell|ability" regex alternation,
    # not a regression (deferred — a lane widen to add an ability-target
    # arm needs its own corpus-diff + CR-citation bar, out of scope for a
    # view conversion).
    Preset(
        name="counterspell",
        description="Counters a target spell (CR 701.6a — the stack counterspell).",
        signal_keys=("counter_control",),
        should_match=("Counterspell", "Mana Leak", "Remand", "Sinister Sabotage"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Creature/permanent removal (task #83/#86 structural-view conversion —
    # the LAST regex-bearing preset). ``signal_keys`` is the 9-key union
    # scoped by task #83's census (rec 0.81 vs the old intentionally-
    # generous regex): ``removal`` + ``exile_removal`` + ``mass_removal`` +
    # ``mass_bounce`` + ``counter_control`` + ``direct_damage`` +
    # ``bounce_tempo`` + ``fight_makers`` + ``debuff_makers``.
    #
    # Two lane gaps the original scoping deferred on are now fixed (task
    # #85, crosswalk_signals.py): (1) ``debuff_makers``'s single-target Pump
    # arm now reads a dynamic ``-X/-X`` (mirroring the mass ``PumpAll``
    # arm's existing ``_negative_pt_field`` read, CR 704.5f) — Toxic Deluge,
    # Death Wind, Flunk, Cloudkill and 83 more recover; (2) a "target
    # [combat-state/color]-qualified creature" Destroy (Smite) that lost its
    # ``Creature`` type_filter in phase's own typed target node now recovers
    # via a raw-text bridge gated on total structural silence.
    #
    # Real residue the union still misses vs the old regex (fixtures that
    # FLIP — the old regex matched these, the view doesn't; adjudicated as
    # MORE-correct routing, not a lane bug, per task #83's scoping pass):
    #   - Pacifism / Arrest (pacify auras — "enchanted creature can't
    #     attack"): neutralizes the threat but never destroys/exiles/
    #     counters/bounces/fights/-X's it, so it's not a removal-FAMILY
    #     effect by ANY of the 9 keys; routes to ``enchantments_matter``.
    #   - Condemn ("put target attacking creature on the bottom of its
    #     owner's library, its controller gains life…"): a library-tuck, not
    #     a removal-family effect either; routes to ``lifegain_makers`` /
    #     ``toughness_combat``.
    #   - Chaos Warp ("target permanent" shuffled into its owner's library):
    #     same library-tuck pattern; routes to ``cheat_from_top`` /
    #     ``cheat_into_play`` (Chaos Warp's OWN "then that player reveals
    #     the top card of their library and puts it onto the battlefield"
    #     is the card's structurally-dominant read).
    # A prior flip attempt this session hit a SEPARATE problem: three
    # downstream call sites (``cube_balance._is_removal``, archetype_audit's
    # CLI preset flag, and the tuner's classify/swaps role checks) exercised
    # this preset against SYNTHETIC cards with no ``oracle_id`` in their own
    # unit tests, which a ``signal_keys``-only Preset always fails to match
    # (see the module docstring's "Structural views" section) — task #86
    # migrated those 12 tests to real testkit-served cards FIRST (see
    # ``test_cube_balance.py``, ``test_archetype_audit.py``,
    # ``test_tuner_classify.py``, ``test_tuner_swaps.py``), so this flip
    # lands clean.
    Preset(
        name="removal",
        description=(
            "Creature/permanent removal — destroy/exile/counter/damage/"
            "bounce/fight/-X effects (intentionally generous)."
        ),
        signal_keys=(
            "removal",
            "exile_removal",
            "mass_removal",
            "mass_bounce",
            "counter_control",
            "direct_damage",
            "bounce_tempo",
            "fight_makers",
            "debuff_makers",
        ),
        should_match=(
            "Murder",  # bare `removal` key
            "Swords to Plowshares",  # exile_removal
            "Wrath of God",  # mass_removal
            "Evacuation",  # mass_bounce
            "Counterspell",  # counter_control
            "Lightning Bolt",  # direct_damage
            "Boomerang",  # bounce_tempo
            "Prey Upon",  # fight_makers
            "Disfigure",  # debuff_makers
            "Toxic Deluge",  # debuff_makers + mass_removal (dynamic -X/-X)
        ),
        should_not_match=(
            "Llanowar Elves",
            "Command Tower",
            "Lupine Prototype",
            "Pacifism",  # pacify aura -> enchantments_matter, not removal
            "Chaos Warp",  # library-tuck -> cheat_from_top/cheat_into_play
            "Condemn",  # library-tuck -> lifegain_makers/toughness_combat
        ),
    ),
    # Board wipe — subset of removal that hits all/many creatures.
    Preset(
        name="board-wipe",
        description=(
            "Destroys or damages all creatures (board-wide removal) — "
            "task #83 structural-view conversion: signal keys "
            "`mass_removal` (DestroyAll / mass-exile / DamageAll / a "
            "SYMMETRIC negative-toughness PumpAll, FIXED or dynamic-X — CR "
            "115.10 / 701.8 / 701.21a / 406.1 — plus a "
            "ChooseAndSacrificeRest sweep, Tragic Arrogance/Cataclysm) + "
            "`symmetric_damage_each` (DamageAll/DamageEachPlayer, the "
            "burn-side twin). mass_removal deliberately EXCLUDES an "
            "opponent-scoped one-sided shrink (Massacre Wurm, Cower in "
            "Fear: 'creatures your opponents control get -N/-N') — a real "
            "deck-building distinction between a SYMMETRIC sweep and a "
            "one-sided punisher (adjudicated, not a gap; see "
            "`_mass_removal`'s own docstring) — so Massacre Wurm moves to "
            "should_not_match here. Recall 0.86 vs the old regex; the "
            "large majority of the 75 preset-only cards are this same "
            "one-sided-debuff family (Doomwake Giant, Elesh Norn, Ethereal "
            "Absolution, ...) plus graveyard-hate mass-exile ('exile all "
            "creature cards from a graveyard' — Crypt Incursion, Honor the "
            "Fallen — a different mechanic, not a battlefield wipe), both "
            "correct sheds. DEFERRED narrow residual (not fixed here — a "
            "lane change, out of scope for a view conversion): 6 symmetric "
            "'All creatures get -X/-X' wipes whose X is a COMPUTED value "
            "(Cloudkill: negative of a commander's mana value; also Deluge "
            "of Doom, Planar Despair, Kagemaro First to Suffer, Ichor "
            "Explosion, Terisiare's Devastation) carry the toughness "
            "reduction as a `Quantity`/`Multiply(factor=-1, ...)` node, "
            "not the `Variable('-X')` shape `_negative_pt_field` reads (the "
            "Toxic Deluge dynamic-X fix, ADR-0035 task #83 chunk-A) — that "
            "helper's own docstring assumed 'no corpus mass-debuff "
            "representative' for the Quantity shape, which this residue "
            "corrects. 6 cards of 543 (recall 0.989) — the view is still "
            "correct to ship; these are the residual tail."
        ),
        signal_keys=("mass_removal", "symmetric_damage_each"),
        should_match=(
            "Wrath of God",
            "Farewell",
            "Drown in Sorrow",
            "Tragic Arrogance",
            "Toxic Deluge",
            "Crux of Fate",
            "Culling Ritual",
        ),
        should_not_match=(
            "Lightning Bolt",
            "Swords to Plowshares",
            "Ivory Charm",
            "Massacre Wurm",
        ),
    ),
    # ── Type-specific removal ──
    #
    # These are strict: they match cards that NAME the target type (or its
    # umbrellas like "creature or planeswalker"). Cards with universal
    # "destroy target permanent" phrasing (Vindicate, Beast Within) appear
    # only in `universal-removal`; count both presets to get the full set
    # of cards that can answer a given type.
    #
    # All patterns use [^.]* to stay within a single sentence, avoiding
    # false-positives like Beast Within where "creature token" appears
    # AFTER the destroy clause.
    #
    # Overlap warning: presets deliberately overlap where cards can answer
    # multiple types — e.g. Lightning Bolt matches both `creature-removal`
    # and `planeswalker-removal` via "any target" burn, and Hero's
    # Downfall matches both via "creature or planeswalker". This is
    # correct (Bolt CAN kill either) but callers summing counts across
    # presets will double-count these cards. Use set-union semantics on
    # the `cards` list in each theme's audit result if you need
    # deduplicated totals.
    # ── Task #83 structural views: the target's PERMANENT CORE TYPE (CR
    # 109.3) is a fact the production signal lanes don't carry as a
    # ``Signal.subject`` (``removal``/``exile_removal``/``mass_removal``/
    # ``edict_makers`` all emit ``subject=""``). Each preset below is a
    # ``concept`` predicate bound to one core type via
    # ``_removal_edict_concept`` (see that function + ``crosswalk_signals.
    # removal_edict_targets_type``'s docstrings for the target-filter
    # mechanics they reuse) — no regex, no ``signal_keys`` (Preset ORs
    # every arm; the AND between "is removal/edict" and "targets THIS type"
    # lives entirely inside the concept predicate's own tree walk).
    Preset(
        name="creature-removal",
        description=(
            "Single-target OR mass creature removal: destroy/exile "
            "targeting Creature, damage-to-creature (including 'any "
            "target' burn — generous, matches the legacy preset), fight, "
            "and a P/T shrink (fixed or dynamic -X/-X)."
        ),
        keywords=("Fight", "Infect", "Wither"),
        concept=_removal_edict_concept("Creature", generous_any=True),
        should_match=(
            "Swords to Plowshares",
            "Doom Blade",
            "Lightning Bolt",
            "Hero's Downfall",
            "Toxic Deluge",
            "Prey Upon",  # fight branch
            "Electrolyze",  # divided-damage / any-target branch
            "Disfigure",  # -N/-N branch
        ),
        should_not_match=(
            "Counterspell",  # counters a spell, doesn't remove a creature
            "Llanowar Elves",
            "Beast Within",  # universal-removal, not creature-specific
            "Shatter",  # artifact-specific
        ),
    ),
    Preset(
        name="artifact-removal",
        description=(
            "Single-target OR mass artifact removal: destroy/exile "
            "targeting Artifact (including 'target artifact or "
            "enchantment' bridge spells)."
        ),
        concept=_removal_edict_concept("Artifact"),
        should_match=("Shatter", "Disenchant", "Reclamation Sage"),
        should_not_match=("Lightning Bolt", "Wrath of God", "Sinkhole"),
    ),
    Preset(
        name="enchantment-removal",
        description=(
            "Single-target OR mass enchantment removal: destroy/exile "
            "targeting Enchantment (including 'target artifact or "
            "enchantment')."
        ),
        concept=_removal_edict_concept("Enchantment"),
        should_match=("Disenchant", "Reclamation Sage"),
        should_not_match=("Lightning Bolt", "Shatter", "Sinkhole"),
    ),
    Preset(
        name="land-removal",
        description=(
            "Land destruction, single-target or mass (MLD). Includes "
            "Sinkhole, Strip Mine, Wasteland, Armageddon. Unions the "
            "``land_destruction`` REPEATABLE-LD-ENGINE membership floor "
            "(a creature-commander cross-open the target-type walk below "
            "can't see — Numot, Goblin Settler) with a target-type walk "
            "over destroy/exile effects (the ``removal``/``mass_removal`` "
            "lanes deliberately EXCLUDE Land, routing it here instead —"
            " see ``_removal``'s docstring)."
        ),
        signal_keys=("land_destruction",),
        concept=_removal_edict_concept("Land"),
        should_match=("Sinkhole", "Strip Mine", "Wasteland", "Armageddon"),
        should_not_match=("Lightning Bolt", "Doom Blade", "Wrath of God"),
    ),
    Preset(
        name="planeswalker-removal",
        description=(
            "Single-target OR mass planeswalker removal: destroy/exile "
            "targeting Planeswalker, damage-to-planeswalker (including "
            "'any target' burn — generous, matches the legacy preset)."
        ),
        concept=_removal_edict_concept("Planeswalker", generous_any=True),
        should_match=("Hero's Downfall", "Lightning Bolt"),
        should_not_match=("Counterspell", "Shatter"),
    ),
    Preset(
        name="universal-removal",
        description=(
            "Destroys or exiles any permanent regardless of type: a "
            "target/sacrifice filter whose bare core-type word is the "
            "literal 'Permanent' (Vindicate, Beast Within, Nicol Bolas, "
            "Planeswalker's +3). Cards here are in addition to the "
            "type-specific presets — check both for full coverage of a "
            "given permanent type."
        ),
        concept=_removal_edict_concept("Permanent"),
        should_match=(
            "Vindicate",
            "Beast Within",
            "Maelstrom Pulse",
            "Nicol Bolas, Planeswalker",
        ),
        should_not_match=(
            "Lightning Bolt",
            "Swords to Plowshares",  # creature-only
            "Shatter",  # artifact-only
            "Wrath of God",  # mass, not single-target universal
        ),
    ),
    # Bounce — return target creature/permanent to hand.
    Preset(
        name="bounce",
        description=(
            "Returns a target creature, nonland permanent, or permanent to "
            "its owner's hand (CR 402.1) — task #83 structural-view "
            "conversion: signal keys `bounce_tempo` (single-target "
            "battlefield->hand, self-bounce/GY-recall vetoed — CR 402.1 vs "
            "404.1) + `mass_bounce` (board-wide). Recall 0.87 vs the old "
            "regex; 30 preset-only, near all a deliberate self-bounce "
            "('return target permanent YOU CONTROL' — a protection idiom, "
            "not tempo) or GY-card-recursion ('return target ... CARD from "
            "a graveyard') the old regex's own comment already meant to "
            "exclude but its negative lookahead missed on 'creature OR "
            "land card' phrasings (Awaken the Honored Dead). "
            "DEFERRED narrow residual (not fixed here — a lane change, out "
            "of scope for a view conversion): Aether Helix's genuine "
            "'return target permanent to hand' tempo bounce is wrongly "
            "GY-veto'd because its sibling graveyard-return effect tags as "
            "`change_zone`, not `bounce` — the veto's `len(bounces) == 1` "
            "guard (`_card_ir/tree_synthesis.py::_arm_bounce_tempo`) treats "
            "the ONE `bounce`-tagged node as if it were the unit's sole "
            "(self-referential) GY return, when it's really the OTHER "
            "sentence's untagged pair; Alchemist's Retrieval's Cleave "
            "alternate mode (which drops the '[you control]' restriction) "
            "isn't modeled separately, so its base parse reads as a vetoed "
            "self-bounce; Whirlpool Whelm's Clash-then-bounce composite "
            "gets no `bounce` concept node at all; Banishing Knack / "
            "Retraction Helix grant another creature a bounce-activated "
            "ability ('target creature gains \"{T}: Return...\"') and the "
            "granted ability's effect isn't walked (the same GrantAbility-"
            "descent gap the sacrifice-outlet conversion's Rakdos Riteknife "
            "note names). 5 cards of 231 (recall 0.978) — the view is "
            "still correct to ship; these are the residual tail."
        ),
        signal_keys=("bounce_tempo", "mass_bounce"),
        should_match=("Unsummon", "Boomerang"),
        should_not_match=("Lightning Bolt", "Unnatural Restoration"),
    ),
    # Targeted discard — opponent discards card(s) (task #83 structural-view
    # conversion). Union of `opponent_discard` (CR 701.9 — a forced
    # OPPONENT discard, direction read off the discard effect's OWN
    # recipient: targeted/opponent player or a symmetric each-player wheel)
    # and `hand_disruption` (CR 402.3 — the Thoughtseize-style reveal-and-
    # choose family: reveal the opponent's hand, then discard a chosen
    # card). See `_deck_forge.crosswalk_signals._opponent_discard` /
    # `._hand_disruption`. 2 preset-only residue (scoping census): Collective
    # Defiance / Steal the Show ("Target player discards all/any number of
    # cards, then draws that many cards") — the old regex fired on the bare
    # word "discards", but the card's actual effect is a symmetric hand
    # FILTER for a targeted player (rummage — you can target yourself too,
    # net card count unchanged), not a punisher-style forced-discard hand
    # attack; the crosswalk correctly routes it to `card_draw_engine` /
    # `target_player_draws` instead — a regex-over-catch shed, signals are
    # more correct here.
    Preset(
        name="discard",
        description="Forces a target player or opponent to discard cards.",
        signal_keys=("opponent_discard", "hand_disruption"),
        should_match=(),  # fixture cards added if Thoughtseize etc. exist in test data
        should_not_match=("Lightning Bolt",),
    ),
    # Tutors — search your library for a card (task #83 structural-view
    # conversion). Signal key `tutor` (CR 701.23/701.23a — your-library
    # search). `tutor` INCLUDES basic-land ramp fetch (Sakura-Tribe Elder,
    # Cultivate both fire it), so the old regex's should_match fixtures
    # don't flip. See `_deck_forge.crosswalk_signals._tutor_lane` — the lane
    # has an ADJUDICATED VETO (ADR-0037, `synth_tutor_directed`) for a
    # directed/symmetric search ("target opponent's library" — Head Games;
    # "each player searches their library" — Oath of Lieges): searching
    # SOMEONE ELSE's library, or a symmetric search that reaches everyone,
    # is a fundamentally different card (opponent-directed disruption, not
    # a self-tutor) even though the old preset's `search (?:your|target
    # opponent's|a) library` regex explicitly widened to catch the
    # opponent-directed phrasing too. 121 preset-only residue (scoping
    # census) is this veto's territory: every preset-only card the census
    # sampled is a directed/symmetric search the tutor lane deliberately
    # excludes by design — an adjudicated exclusion (cite the lane's own
    # veto comment), not a preset-noise catch the old regex correctly
    # avoided nor a genuine capability loss for the SELF-tutor concept this
    # preset is named for.
    Preset(
        name="tutors",
        description=(
            "Searches your library for a card (BANNED in shared-library format)."
        ),
        signal_keys=("tutor",),
        should_match=("Sakura-Tribe Elder", "Cultivate"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Creature-token creation. Oracle text uses both singular ("create a
    # 1/1 ... creature token") and plural ("create two 1/1 ... creature
    # tokens"), so the count atom here accepts "a"/"an" in addition to
    # digit/word-form numbers. Includes Embalm and Eternalize — their
    # reminder text says "Create a token that's a copy of it" (omitting
    # "creature token" literally), so the regex misses them; the keyword
    # tuple catches them instead.
    Preset(
        name="tokens",
        description=(
            "Creates one or more creature tokens — task #83 structural-view "
            "conversion: the `token_maker` signal key (a CreateToken effect) "
            "UNION the broad family of keywords that create tokens as part "
            "of their OWN keyword template rather than a separately-tagged "
            "effect (`token_maker` doesn't fire on the keyword alone): "
            "Embalm and Eternalize (Zombie copies from graveyard), Populate "
            "(copy your own token), Amass (Zombie Army), Offspring (1/1 "
            "copy), Manifest and Cloak (face-down 2/2), Incubate (Incubator "
            "transform token), Fabricate (Servos), Afterlife (Spirits on "
            "death), Mobilize (attacking Warriors), Encore (attacking "
            "copies), Myriad (combat token copies), Endure (CR 702.62 — "
            "counters OR a Spirit token, a genuine possible-token maker). "
            "Corpus diff vs the old regex (commander-legal, by oracle_id): "
            "18 preset-only before the Endure keyword closed 10 of them "
            "(a modal 'put counters or make a Spirit token' cycle); the "
            "remaining 8 are a small, named residual, not fixed here (a "
            "lane change, out of scope for a view conversion) — Afterlife "
            "Insurance / Infantry Shield TEMPORARILY GRANT the Afterlife / "
            "Mobilize keyword to a creature ('creatures you control gain "
            "afterlife 1 until end of turn') rather than printing it, so "
            "the keyword-array check (which reads the CARD's own printed "
            "keywords) never fires; the other 6 use the `Gift` keyword's "
            "token-flavored variant ('Gift a tapped Fish') — `Gift` itself "
            "is too coarse to union (most Gift cards gift a card, life, or "
            "something else, never a token), so the token-specific Gift "
            "cards stay a narrow, acceptable residual."
        ),
        keywords=(
            "Embalm",
            "Eternalize",
            "Populate",
            "Amass",
            "Offspring",
            "Manifest",
            "Cloak",
            "Incubate",
            "Fabricate",
            "Afterlife",
            "Mobilize",
            "Encore",
            "Myriad",
            "Endure",
        ),
        signal_keys=("token_maker",),
        should_match=(
            "Omen of the Sun",
            "Blade Splicer",
            "Lingering Souls",
            "Angel of Sanctions",  # Embalm
        ),
        should_not_match=("Lightning Bolt",),
    ),
    # Sacrifice outlet / payoff (task #83 structural-view conversion). The
    # crosswalk `sacrifice_outlets` signal (see
    # `_deck_forge.crosswalk_signals._sacrifice_outlets`) is DELIBERATELY
    # broader than the old "sacrifice X: <effect>" regex: it is the
    # concept's own true scope — a repeatable activated-cost outlet
    # (Viscera Seer, Ashnod's Altar), a ONE-SHOT outlet (an alt-cost pitch
    # — Salvage Titan, Anchor to Reality; an ETB "sacrifice any number" —
    # Angelic Aberration; Devour/Exploit/Casualty/Bargain), a GRANTED
    # outlet (Lunarch Mantle), OR a sacrifice PAYOFF (a `sacrificed`/
    # `exploited` trigger with no outlet of its own — Cabal Therapist,
    # Blood Artist-style death-payoff cousins) — CR 701.21. A random
    # 25-card sample of the ~875 corpus cards this view gains over the old
    # regex (session adjudication) confirmed every one is genuinely
    # sacrifice-related (one-shot/alt-cost/granted outlets or payoffs),
    # not noise the regex correctly excluded — the regex's narrower
    # "repeatable, colon-suffixed cost" phrasing was UNDER-catching this
    # whole family, not over-catching a different one.
    #
    # DEFERRED single-card gap (not fixed here — a lane change needs the
    # full corpus-diff + CR-citation bar, out of scope for a view
    # conversion): Rakdos Riteknife (equipment) grants its wielder
    # "{T}, Sacrifice a creature: Put a blood counter…" bundled into ONE
    # static ability alongside a dynamic +1/+0 pump ("Equipped creature
    # gets +1/+0 for each blood counter … and has '…'"). phase-rs parses
    # that combined static ability as a bare `AddDynamicPower`
    # modification with NO `GrantAbility` node for the quoted granted
    # ability at all (verified via `_ir_lookup.trees_for` — the granted
    # activated ability's text is dropped from the typed tree entirely),
    # so `_sac_outlet_granted_cost`'s `GrantAbility` walk has nothing to
    # find. This is a phase-rs parse gap on the "buff + grant" combined
    # idiom, not a crosswalk-lane bug; the old regex caught it via the
    # mid-sentence ", sacrifice a creature:" text this view can't yet
    # reach structurally. One card of 303 (recall 0.997) — the view is
    # still correct to ship; this card is the residual tail.
    Preset(
        name="sacrifice-outlet",
        description=(
            "Has a sacrifice outlet (repeatable activated, one-shot "
            "alt-cost, granted, or ETB) OR triggers on a sacrifice you "
            "make (sacrifice PAYOFF) — CR 701.21. Broader than the old "
            "'repeatable activated cost' regex; see the crosswalk "
            "conversion note above."
        ),
        signal_keys=("sacrifice_outlets",),
        should_match=("Viscera Seer", "Ashnod's Altar"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Burn: direct damage to creature or player (task #83 structural-view
    # conversion). Union of `direct_damage` (CR 120.1 — a DealDamage /
    # DamageEachPlayer / DamageAll effect that reaches a PLAYER — Lightning
    # Bolt, Fanatic of Mogis) and `removal` (CR 701.8/701.8a — includes its
    # DealDamage-to-a-permanent arm, so a creature-only bolt like Shock is
    # covered too). See `_deck_forge.crosswalk_signals._direct_damage` /
    # `._removal`. 6 preset-only residue (scoping census: Arc Spitter,
    # Lavamancer's Skill, Pathway Arrows, Showstopper, Shuriken, Tyrant's
    # Familiar) — every one is a "deals N damage to target creature" ability
    # GRANTED onto another permanent (an Equipment's "equipped creature has
    # '{cost}: deals N damage...'", an Aura's "enchanted creature has...", a
    # Lieutenant-conditional granted attack trigger) rather than the card's
    # OWN direct effect; `_removal`'s per-unit `effect_concepts` walk (unlike
    # `direct_damage`'s player-reaching arm, which already recovers a
    # GRANTED damage effect via `has_nested_damage_reaching_player`) does not
    # descend into a granted ability's body for a permanent-targeted damage
    # effect. A genuine, narrow gap (6 of 1274, recall 0.995) — deferred, not
    # fixed here: extending `_removal`'s granted-ability descent is a lane
    # change with its own corpus-diff + CR-citation bar, out of scope for a
    # view conversion.
    Preset(
        name="burn",
        description=(
            "Deals direct damage to a creature, player, planeswalker, or any target."
        ),
        signal_keys=("direct_damage", "removal"),
        should_match=("Lightning Bolt",),
        should_not_match=("Counterspell", "Llanowar Elves"),
    ),
    # Reanimate-to-battlefield: the classic "put target creature card from a
    # graveyard onto the battlefield" effect. Structural view (task #83):
    # union of `creature_recursion` (CR 700.4/401.4/404 — a Graveyard→
    # Battlefield ChangeZone over a Creature-cored filter, controller-gated
    # so an opponent's-graveyard-ONLY pull reads as graveyard hate rather
    # than your loop) and `reanimator` (CR 700.4/603.6e — the creature-
    # PERMANENT that itself has a GY→battlefield ChangeZone, the archetype
    # card rather than the spell). See `_deck_forge.crosswalk_signals.
    # _creature_recursion` / `._reanimator`.
    #
    # DEFERRED residue (17 preset-only, scoping census; NOT fixed here — a
    # lane change or substrate fix is out of scope for a view conversion),
    # two distinct classes, verified against phase's own parse (not just
    # the crosswalk read):
    #
    # 1. ADJUDICATED EXCLUSION (the lane's own Gate #6 — "subject
    #    controller != Opponent... an opponents'-graveyard-ONLY pull is
    #    graveyard hate, not your loop"): Agadeem Occultist, Ashen Powder,
    #    Gruesome Encore, Immortal Obligation, Macabre Mockery, Nurgle's
    #    Conscription, Puppeteer Clique all target "a creature card from AN
    #    OPPONENT'S graveyard" — a design choice already made by the lane,
    #    not a bug this conversion introduces.
    # 2. GENUINE SUBSTRATE GAP (phase-rs's parse itself, confirmed via the
    #    raw card-data.json records, not a crosswalk-lane miss): Animate
    #    Dead / Necromancy structure the return as an Aura's "return
    #    ENCHANTED creature card to the battlefield" (an enchanted-permanent
    #    reference, not a typed Creature `SearchLibrary`/`ChangeZone` filter
    #    the lane's subject test reads) — CR 303.4g aura-attach idiom, no
    #    existing crosswalk lane helper reads this shape yet. Can't Stay
    #    Away / Heroic Return are worse: phase's own record has an EMPTY
    #    `abilities` array for the card — the primary "Return target
    #    creature card from your graveyard to the battlefield" effect isn't
    #    parsed into ANY node at all (only the attached "if it enters this
    #    way" replacement survives), a parser-level swallow on the
    #    template-plus-replacement-clause idiom. Aerith, Last Ancient /
    #    Doctor Jane Foster / Karai, Future of the Foot have a genuinely
    #    conditional destination (return to hand, UNLESS a condition —
    #    lifegain, sneak cost — then to the battlefield instead); Liliana,
    #    Waker of the Dead's is emblem-granted. None of these have a
    #    reachable typed node a bounded concept predicate could reuse
    #    without hand-rolling new text detection, which the standing rule
    #    forbids — genuinely deferred to a future substrate/lane task, not
    #    silently dropped.
    Preset(
        name="reanimate",
        description=(
            "Puts a creature card from a graveyard onto the battlefield "
            "(reanimator-style, not just grave-to-hand)."
        ),
        signal_keys=("creature_recursion", "reanimator"),
        should_match=("Reanimate",),
        should_not_match=("Lightning Bolt", "Counterspell", "Regrowth"),
    ),
    # Graveyard-to-hand recursion (Eternal Witness-style). task #83
    # structural-view conversion: NOT ``signal_keys=("graveyard_makers",)``
    # — that key bundles THREE GY-interaction directions under one Signal
    # with no ``subject`` to discriminate them (reanimate GY->Battlefield,
    # this preset's GY->Hand, and self-mill's Mill->Graveyard — see
    # ``graveyard_return_direction``'s own docstring). The concept
    # predicate re-runs the SAME ``change_zone_dirs`` read
    # ``_graveyard_makers`` performs, keeping the destination that lane's
    # ``fire()`` helper collapses away.
    #
    # ``keywords=("Soulshift", "Recover")`` (task #87): the sanctioned
    # keyword-array union (mill/goad/magecraft/proliferate precedent) —
    # BOTH keywords are CR 702.46a/702.59a graveyard-to-hand recursion by
    # definition, and this arm is the ONLY thing that catches Garza's
    # Assassin: its whole "Recover—Pay half your life..." clause is a
    # ``SwallowedClause`` parse_warning upstream, with ZERO surviving
    # phase-level residue — not even a keyword tag (unlike Kodama of the
    # Center Tree's dynamic-X Soulshift, which DOES carry a phase-native
    # ``AddKeyword`` marker read structurally by
    # ``graveyard_return_direction`` itself). Harmless-redundant for every
    # properly-parsed Soulshift/Recover carrier (a FIXED-N Soulshift or a
    # Coldsnap Recover cycle card already carries a full ``ChangeZone``
    # trigger the concept arm catches on its own — corpus-swept 2026-07,
    # 32/34 total carriers).
    Preset(
        name="graveyard-return",
        description=(
            "Returns a card from a graveyard to a player's hand "
            "(Eternal Witness, Regrowth, Raise Dead)."
        ),
        keywords=("Soulshift", "Recover"),
        concept=_graveyard_return_concept,
        should_match=(
            "Regrowth",
            "Eternal Witness",
            "Garza's Assassin",
            # task #87 census residue — one representative per shape
            # class the ``graveyard_return_direction`` predicate's own
            # docstring names: a modal ``ChooseMode`` branch, the
            # opponent-chooses idiom, a cost-shaped ``ReturnToHand``
            # rider, and a dynamic-X Soulshift keyword grant.
            "Ghostly Dancers",
            "Tasigur, the Golden Fang",
            "Harvest Wurm",
            "Kodama of the Center Tree",
        ),
        # task #87 census non-members (verified structurally False):
        # each of these carries a graveyard-TO-BATTLEFIELD reanimation
        # ability (Dread Wanderer / Cauldron Dance / Evershrike /
        # Defossilize / Greasefang, Okiba Boss) or a dredge alternative-
        # draw (The Necrobloom) — none is a graveyard-TO-HAND recursion.
        should_not_match=(
            "Lightning Bolt",
            "Dread Wanderer",
            "Cauldron Dance",
            "Evershrike",
            "Defossilize",
            "Greasefang, Okiba Boss",
            "The Necrobloom",
        ),
    ),
    # Cantrip (task #83 structural-view conversion): a low-opportunity-cost
    # spell that draws exactly ONE card as a RIDER on another primary
    # effect (Preordain, Opt, Ponder, Remand — CR 121.1). The crosswalk
    # ``cantrip`` lane (crosswalk_signals._cantrip) is a BOUNDED read (a
    # fixed-1, non-scaling Draw sharing its unit with a sibling non-draw
    # effect, gated to Instant/Sorcery, recipient never Opponent) —
    # corpus-scanned to 433 commander-legal hits vs the deleted regex's
    # unbounded ~3174-card "draws a card" substring match. Rhystic Study
    # correctly falls OUT (an enchantment, not Instant/Sorcery — a
    # repeatable payoff engine, not a one-shot rider; routes to
    # enchantments_matter/opponent_cast_matters instead) and Divination
    # correctly falls out (a bare 2-for-1 draw spell with no sibling
    # effect — the WHOLE point of the card, not a rider).
    Preset(
        name="cantrip",
        description=(
            "Draws exactly ONE card as a rider or primary effect. For "
            "multi-card draw effects use 'card-draw'."
        ),
        signal_keys=("cantrip",),
        should_match=("Preordain", "Opt", "Ponder", "Remand"),
        should_not_match=(
            "Lightning Bolt",
            "Llanowar Elves",
            "Rhystic Study",
            "Divination",
        ),
    ),
    # Card draw (multi-card effects): draws 2+ cards in a single effect.
    # Does not overlap with cantrip. task #83 structural-view conversion:
    # ``card_draw_engine`` alone is the recurring/bulk-draw lane and
    # deliberately EXCLUDES a one-shot ETB bulk draw (Mulldrifter's "when
    # ~ enters, draw two cards" — see that lane's own docstring), so it
    # ORs with ``etb_bulk_draw`` (crosswalk_signals.py, next to
    # ``_card_draw_engine``) to reach it. The two arms are structurally
    # disjoint (one requires an ``enters`` trigger, the other excludes
    # one), so the OR never double-fires a card under both.
    #
    # ``draw_for_each`` UNIONED IN (task #86 / #85's census): a "draw a
    # card for each X" board-scaling draw (Shamanic Revelation, Truth or
    # Consequences) is functionally a multi-card-draw engine the same as
    # ``card_draw_engine``, but is its own crosswalk lane (a for-each COUNT
    # read, CR 120/107.3 — see ``_draw_for_each``'s own docstring) that
    # never independently sets ``card_draw_engine``. Probed against 14
    # scaling-draw residue cards (#85's census) — Messenger Jays, Observed
    # Stasis, Cirdan the Shipwright, Truth or Consequences, Spell
    # Contortion among them — all carry ONLY ``draw_for_each`` (not
    # ``card_draw_engine``/``etb_bulk_draw``), confirming the view was
    # silently dropping them. Narrow lane: 234 of 32,521 commander/brawl-
    # legal cards (0.7%) carry ``draw_for_each`` corpus-wide — a for-each
    # scaling read, not a broad "mentions draw" catch-all, so folding it in
    # doesn't widen the preset the way a raw-text union would.
    Preset(
        name="card-draw",
        description="Draws two or more cards in a single effect.",
        signal_keys=("card_draw_engine", "draw_for_each"),
        concept=_etb_bulk_draw_concept,
        should_match=(
            "Mulldrifter",
            "Deep Analysis",
            "Brainstorm",
            "Rielle, the Everwise",
            "Truth or Consequences",  # draw_for_each-only residue
        ),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Lifegain — gains life AS an effect, OR cares about gaining life as a
    # payoff (whenever-trigger). Typed broadly because lifegain as an
    # archetype includes both the "taps" and the "matters" sides.
    Preset(
        name="lifegain",
        description=(
            "Gains life OR triggers when you gain life (lifegain-matters) — "
            "task #83 structural-view conversion: signal keys "
            "`lifegain_makers` (a gain-life EFFECT) + `lifegain_matters` "
            "(a your-lifegain PAYOFF, including the Secrets of Strixhaven "
            "`Infusion` 'if you gained life this turn' idiom and a "
            "recurring self-life-loss engine read as the same 'life as a "
            "resource' archetype — Ad Nauseam, Phyrexian Arena cousins) "
            "UNION the printed `Lifelink` keyword (a keyword-only lifelink "
            "grant the effect lane doesn't independently derive). "
            "Corpus diff vs the old regex (commander-legal, by oracle_id): "
            "183 preset-only, ALL correctly shed — 173 are old-regex "
            "reminder-text false positives (a Food/Clue/Ninjutsu token's "
            "OWN 'You gain 3 life' explainer text, or a granted/modal "
            "'lifelink' mention unrelated to the card's own effect) or "
            "self-only 'this Aura has lifelink' static grants; the "
            "remaining 10 (Armistice, Fiery Justice, Phelddagrif, ...) are "
            "OPPONENT-directed lifegain (group-hug 'target opponent gains "
            "N life') — a different scope than lifegain_makers' `you` "
            "read, correctly excluded (same shed pattern as the removal "
            "preset's Condemn/Chaos Warp exclusions)."
        ),
        keywords=("Lifelink",),
        signal_keys=("lifegain_makers", "lifegain_matters"),
        should_match=("Thragtusk", "Lightning Helix", "Efflorescence"),
        should_not_match=("Lightning Bolt", "Counterspell"),
    ),
    # +1/+1 counters — puts +1/+1 counters on a creature, OR cares about
    # creatures with +1/+1 counters. Covers the classic counters-matter
    # archetype (Simic, Abzan, Hardened Scales, etc.). Excludes other
    # counter types (loyalty, charge, time, etc.) by anchoring on the
    # literal "+1/+1" token.
    #
    # task #83 named FOUR lane-gap families as the reason this preset
    # stayed regex/keyword-only (585 -> 379 preset-only residue after
    # adding self_counter_grow/counter_distribute/Mentor/Explore, ~75% of
    # a 110-card genuine-miss sample). task #85 re-measured at v0.23 (the
    # residue had grown to 415, not shrunk — new-set churn outpaces the
    # bump's own counter-parse additions) and closed all four:
    #
    # (1) ETB "enters with N +1/+1 counters" template (Cogwork Grinder,
    #     Naya Soulbeast, Lupine Harbingers, Worldheart Phoenix, Undead
    #     Sprinter): phase's static-replacement parser fails outright on
    #     the computed-X form (decorates ``Unimplemented`` with a
    #     "Replacement pattern matched but line failed replacement
    #     parser" raw prefix) and drops the fixed-N form with no node at
    #     all.
    # (2) the Kamigawa "Fractal" token+counter cycle (Body of Research,
    #     Sequence Engine, ...) and its general form (Alien Invasion,
    #     Amzu, Emissary Green, Furgul, ...): a COMPUTED-amount
    #     ``PutCounter`` clause following a ``make_token``/other effect in
    #     the same unit is dropped entirely (mirrors the ``direct_damage``
    #     computed-amount-clause-drop precedent).
    # (3) planeswalker LOYALTY abilities placing counters (Jared
    #     Carthalion's -3, Elspeth Resplendent's +1): the clause survives
    #     as an ``Unimplemented`` EFFECT-role node with the placement text
    #     verbatim as its raw.
    # (4) the "creature(s) [you control] with a +1/+1 counter on it/them"
    #     PAYOFF condition (Bred for the Hunt, Foundry Hornet, Chronicler
    #     of Heroes): FOUR distinct typed sites the prior
    #     ``plus_one_matters`` structural read didn't check — a
    #     ``deals_damage``/``attacks``-mode trigger's ``valid_source``
    #     (only ``valid_card`` was read), a static/trigger ``ControlsType``
    #     condition (only ``IsPresent`` was read), a ``QuantityCheck``
    #     whose ``Ref`` wraps an ``ObjectCount`` filter (only the direct
    #     ``CountersOn`` shape was read), and the v0.23-bump-added
    #     ``HadCounters`` past-tense condition on a leaves-the-battlefield
    #     trigger (Promising Duskmage's dies-with-a-counter check — only
    #     the live-object ``HasCounters`` tag was read).
    #
    # (1)+(2)+(3) close via one bucket-B ``tree_synthesis`` bridge feeding
    # ``plus_one_makers`` (:func:`mtg_utils._card_ir.tree_synthesis.
    # _arm_plus_one_makers` — see its own docstring for the unified idiom
    # read and why reminder-stripping keeps it from re-opening the
    # Connive/Amass/Explore/Incubate/Megamorph/Awaken keyword-mechanic
    # shed). (4) closes as four genuine structural-read widenings in
    # ``crosswalk_signals._plus_one_matters`` (no bridge — real typed
    # fields/tags the prior code just didn't check yet).
    #
    # Re-measuring the post-fix residual (a 194-card manual census: the
    # task #83 four-family examples plus every remaining preset-only
    # card) found no OTHER fixable structural gap — it splits cleanly
    # into six documented, CR-grounded exclusion classes (every card
    # individually checked, none silently dropped):
    #
    # * reanimation/zone-change-with-a-bonus-counter (CR 614.12 — a
    #   replacement rider on a graveyard/exile/dies recursion effect, the
    #   counter is incidental to the RECURSION, not this preset's DOER;
    #   ~29 cards — A-Graveyard Shift, Drana, Undying Malice, Valkyrie's
    #   Call, ...).
    # * cost-reduction-by-counter-count (CR 118.7 — Hamza, Starport
    #   Security: the counter is a THRESHOLD reference for an unrelated
    #   cost reducer).
    # * a kind-AGNOSTIC "with/has A counter on it" reference (Michelangelo,
    #   Mutant BFF — CR 122.1 requires a KIND; belongs to
    #   any_counter_matters, the SAME split ``_plus_one_matters``'s own
    #   docstring already documents for The Swarmlord/Cleopatra).
    # * an EQ-0/negation "no +1/+1 counter"/"without a +1/+1 counter"
    #   predicate (Hindervines, Wave Goodbye — the inverse of a
    #   counter-caring payoff; already deliberately excluded corpus-wide
    #   per ``_plus_one_matters``'s own documented Hindervines exception).
    # * a GRANTED keyword/ability, or a SEPARATELY CREATED permanent's own
    #   ability, placing the counter — never this card's own effect (~36
    #   cards: the "Mutagen token" cycle — April O'Neil, Crustacean
    #   Commando, Genghis Frog, Mona Lisa, Mutagen Man, Mutant Chain
    #   Reaction, Ooze Spill, Return to the Sewers, Shellshock, Slithering
    #   Cryptid, Zoo Escapees; the "Young Hero Role" token cycle — Cut In,
    #   Embereth Veteran, Merry Bards, Protective Parents, Return
    #   Triumphant; a granted Sunburst/Bloodthirst/Riot/Evolve/Training/
    #   Devour/Scavenge/Dethrone (Lux Artillery, Solar Array, Twins of
    #   Discord, Domri Chaos Bringer, Propagator Drone, Elder Arthur
    #   Maxson, Dragon Broodmother, Varolz, Young Deathclaws, Dack's
    #   Duplicate); a delayed "one-time boon" granted to a FUTURE spell
    #   (Arcane Archery, Champions of Tyr, March Toward Perfection,
    #   Tenacious Pup); a bare Amass/Incubate ACTION reference from a
    #   loyalty ability or spell effect rather than the creature's own
    #   keyword (Angrath, Commence the Endgame, Assimilate Essence,
    #   Excise the Imperfect, Tangled Skyline); Aegis of the Legion's
    #   granted Mentor; Ral and the Implicit Maze's created token's own
    #   ability — the SAME GrantAbility-descent / token's-own-ability
    #   substrate gap named in the bounce/edict/extra-turns deferrals
    #   (task #85), cross-lane and out of scope for one preset. Ledgered
    #   here, not silently dropped.
    # * niche singleton residue, individually inspected and genuinely
    #   ambiguous/complex enough to defer rather than force a fix:
    #   Biomancer's Familiar (a counter-COUNT reference for an unrelated
    #   Adapt-nerf, not a cares-about), Blightbeetle (a counter-PLACEMENT
    #   DENIAL static on opponents' creatures — the inverse of a doer),
    #   Bewitching Leechcraft (the counter is a RESOURCE for an unrelated
    #   untap-lock Aura, opponent-directed), Ion Storm (a P1P1-OR-charge
    #   alternative counter-sink cost), Rite of the Serpent (a
    #   target-had-a-counter removal rider), Tizerus Charger (an
    #   Escape-cost modal counter CHOICE), Cosima // The Omenkeel (a
    #   self-granted delayed replacement ability, one card).
    #
    # Legitimate different-archetype exclusions carried over unchanged
    # from task #83's own finding: counter_doubling (its own lane) and
    # opponent-directed placement (a different scope than this preset's
    # ``you`` read). Keyword mechanics whose OWN +1/+1-counter rider is
    # reminder text on a DIFFERENT primary mechanic stay shed to their
    # existing preset/lane: Connive (CR 702.153, cantrip), Amass/Incubate
    # (CR 701.47/701.53, token-preset), Megamorph (CR 702.75,
    # facedown_makers), Undying/Persist (CR 702.92/702.79, their own
    # death-replacement lane). Mentor (CR 702.134) and Explore (CR
    # 701.44) join the keywords list per task #83's own scoping-pass
    # recommendation — both mechanics' placement is unconditional-or-
    # primary, the same class as Bolster; Awaken (CR 702.113), Ravenous
    # (CR 702.156), and Scavenge (CR 702.97) join for the identical
    # reason (task #85 finding — Boiling Earth's land-animation counters,
    # Tervigon's ETB counters, the Golgari scavenge cycle's recursion-
    # into-counters).
    Preset(
        name="plus-one-counters",
        description=(
            "Puts +1/+1 counters on creatures OR cares about creatures with "
            "+1/+1 counters (counters-matter archetype). Includes every "
            "keyword whose primary mechanic is adding +1/+1 counters: "
            "Bolster, Increment (SOS), Reinforce, Monstrosity, Graft, "
            "Outlast, Renown, Evolve, Adapt, Modular, Fabricate (modal), "
            "Training, Support, Tribute, Endure (modal), Devour, Dethrone, "
            "Mentor, Explore, Awaken, Ravenous, Scavenge."
        ),
        keywords=(
            "Bolster",
            "Increment",
            "Reinforce",
            "Monstrosity",
            "Graft",
            "Outlast",
            "Renown",
            "Evolve",
            "Adapt",
            "Modular",
            "Fabricate",
            "Training",
            "Support",
            "Tribute",
            "Endure",
            "Devour",
            "Dethrone",
            "Mentor",
            "Explore",
            "Awaken",
            "Ravenous",
            "Scavenge",
        ),
        signal_keys=("plus_one_makers", "plus_one_matters", "counter_distribute"),
        concept=_plus_one_counters_self_grow_concept,
        should_match=(
            "Scavenging Ooze",
            "Goldvein Hydra",
            "Berta, Wise Extrapolator",
            "Cogwork Grinder",
            "Body of Research",
            "Jared Carthalion",
            "Bred for the Hunt",
        ),
        should_not_match=("Lightning Bolt", "Counterspell", "Esper Sentinel"),
    ),
    # Cantrip gets Connive added via keywords tuple — Connive's core effect
    # is "draw a card, then discard a card" (with a +1/+1 rider on nonland
    # discards), so it's card-filtering; matches cantrip's single-card-draw
    # semantics.
    Preset(
        name="connive",
        description=(
            "Keyword action from Streets of New Capenna: draw a card, "
            "then discard a card. If a nonland card was discarded, put "
            "a +1/+1 counter on the conniving creature."
        ),
        keywords=("Connive",),
        should_match=("Change of Plans",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Cost-reduction via tapping (Convoke / Improvise / Waterbend) ──
    #
    # All three let you tap untapped permanents rather than pay mana to
    # cast a spell. Convoke (702.51) taps creatures; Improvise (702.126)
    # taps artifacts; Waterbend (701.67) taps both — it's the Avatar
    # crossover's generalized "each tap pays for {1}" cost mechanic.
    Preset(
        name="convoke",
        description=(
            "Tap untapped creatures you control rather than pay mana to "
            "cast a spell (CR 702.51)."
        ),
        keywords=("Convoke",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="improvise",
        description=(
            "Tap untapped artifacts you control rather than pay mana to "
            "cast a spell (CR 702.126). Artifact-cost-reduction sibling "
            "of Convoke."
        ),
        keywords=("Improvise",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="waterbend",
        description=(
            "Alt-cost mechanic from the Avatar crossover (CR 701.67). "
            "While paying a waterbend cost, tap untapped artifacts or "
            "creatures to help — each tap pays for {1}. Generalizes "
            "Convoke + Improvise into a single keyword action."
        ),
        keywords=("Waterbend",),
        should_match=("Aang's Iceberg",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Airbend (Avatar crossover) ──
    #
    # Per CR 701.65 (glossary says "Airbend", not "Airbending" — the
    # Scryfall keywords array uses "Airbend"): exiles one or more
    # permanents/spells; the owner of each exiled card may cast it
    # from exile for {2}. Mechanically closer to Warp/Suspend than
    # to bounce; NOT in the `bounce` preset because airbend never
    # returns cards to hand.
    #
    # Does NOT include Warp (CR 702.185) — Warp is a cast-from-hand-
    # for-alternative-cost-then-exile-at-EOT keyword (a suspend-like
    # cast-later mechanic), distinct enough from airbend's "exile
    # someone else's thing, they may recast for {2}" mechanic that
    # bundling them would conflate politically very different cards.
    Preset(
        name="airbend",
        description=(
            "Exile a permanent or spell and let its owner cast it from "
            "exile for {2} (Airbend, Avatar crossover, CR 701.65)."
        ),
        keywords=("Airbend",),
        should_match=("Aang, the Last Airbender",),
        should_not_match=("Lightning Bolt", "Unsummon", "Boomerang"),
    ),
    # ── Proliferate ──
    Preset(
        name="proliferate",
        description=(
            "Choose any number of permanents and/or players with counters "
            "and add another counter of each kind. Scales with +1/+1, "
            "poison, -1/-1, charge, loyalty counters — so proliferate "
            "decks usually pair with counter-producing archetypes."
        ),
        keywords=("Proliferate",),
        should_match=("Contagion Clasp", "Atraxa, Praetors' Voice"),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Goad (political / multiplayer) ──
    Preset(
        name="goad",
        description=(
            "Forces a creature to attack each combat if able, and to attack a "
            "player OTHER THAN the one who goaded it (the goader) — not merely "
            "other than its own controller. So goading an opponent's creature "
            "steers it at your other opponents, not you. Multiplayer politics "
            "mechanic (CR 701.15)."
        ),
        keywords=("Goad",),
        should_match=("Disrupt Decorum",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Magecraft (Strixhaven spellslinger) ──
    Preset(
        name="magecraft",
        description=(
            "Triggers 'whenever you cast or copy an instant or sorcery "
            "spell' — the Strixhaven spellslinger payoff. Mechanically "
            "overlaps with Prowess (combat buff on spell cast) but "
            "Magecraft can trigger any effect, so it gets its own preset."
        ),
        keywords=("Magecraft",),
        should_match=("Storm-Kiln Artist", "Archmage Emeritus"),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Opus (Secrets of Strixhaven big-spells trigger) ──
    Preset(
        name="opus",
        description=(
            "Triggers on instant/sorcery casts with a 5+-mana threshold. "
            "The effect can be anything — not just combat buffs — and "
            "Opus cards typically have a lesser mode that triggers for "
            "cheaper instants/sorceries as well. Big-spells-matter "
            "spellslinger archetype."
        ),
        keywords=("Opus",),
        should_match=("Colorstorm Stallion",),
        should_not_match=("Lightning Bolt", "Monastery Swiftspear"),
    ),
    # ── Graveyard-cast umbrella (cast-from-graveyard mechanics) ──
    #
    # Strict: only keywords that actually CAST the card from the
    # graveyard. Notably excludes:
    #   * Embalm/Eternalize — create a TOKEN COPY, not cast the card.
    #     These live in the `tokens` preset.
    #   * Unearth — RETURNS the card to the battlefield, not cast.
    #     Lives in the `reanimate` preset.
    Preset(
        name="graveyard-cast",
        description=(
            "Umbrella for 'cast this card from the graveyard' keyword "
            "mechanics: Flashback, Jump-start, Aftermath, Retrace, "
            "Escape, Disturb, Mayhem. Graveyard-value payoff. The "
            "narrower `flashback` preset still exists; use this one "
            "when you want the full cast-from-graveyard archetype "
            "density."
        ),
        keywords=(
            "Flashback",
            "Jump-start",
            "Aftermath",
            "Retrace",
            "Escape",
            "Disturb",
            "Mayhem",
            "Harmonize",
        ),
        should_match=(
            "Lingering Souls",  # Flashback
            "Chemister's Insight",  # Jump-start
            "Kroxa, Titan of Death's Hunger",  # Escape
        ),
        should_not_match=(
            "Lightning Bolt",
            "Counterspell",
            "Angel of Sanctions",  # Embalm creates a token, not cast
        ),
    ),
    # ── Cast-later family (exile-then-cast-later mechanics) ──
    Preset(
        name="cast-later",
        description=(
            "Cards that are cast at a time other than normal spell timing — "
            "exiled or held to be cast on a future turn, often for an "
            "alternative cost. Covers Suspend, Foretell, Plot, Warp, "
            "Rebound, Impending, and Adventure (matched via the 'adventure' "
            "layout since Scryfall doesn't tag it as a keyword)."
        ),
        keywords=(
            "Suspend",
            "Foretell",
            "Plot",
            "Warp",
            "Rebound",
            "Impending",
        ),
        layouts=("adventure",),
        should_match=(
            "Ancestral Vision",  # Suspend
            "Scorn Effigy",  # Foretell
            "Djinn of Fool's Fall",  # Plot
            "Voidcalled Devotee",  # Warp
        ),
        should_not_match=("Lightning Bolt", "Counterspell"),
    ),
    # ── Spell-copy family ──
    Preset(
        name="spell-copy",
        description=(
            "Copies a spell (self or another spell). Covers Storm, "
            "Casualty, Replicate, Cipher, Conspire, Demonstrate, and the "
            "Secrets of Strixhaven 'Paradigm' recurring free-cast-from-"
            "exile mechanic. Does NOT include Splice (which adds text "
            "onto an Arcane spell rather than copying) or Prepared "
            "(which casts a paired spell, not a copy of the current one)."
        ),
        keywords=(
            "Storm",
            "Casualty",
            "Replicate",
            "Cipher",
            "Conspire",
            "Demonstrate",
            "Paradigm",
        ),
        should_match=(
            "Weather the Storm",
            "Cut of the Profits",  # Casualty
            "Train of Thought",  # Replicate
            "Last Thoughts",  # Cipher
            "Improvisation Capstone",  # Paradigm
        ),
        should_not_match=("Lightning Bolt", "Counterspell"),
    ),
    # ── Edict family (forced-sacrifice) ──
    Preset(
        name="edict",
        description=(
            "Forced-sacrifice effects. Defender chooses which permanent to "
            "sacrifice (a kind of removal that bypasses hexproof/"
            "indestructible) — task #83 structural-view conversion: the "
            "`edict_makers` signal key (a forced player-sacrifice of ANY "
            "type, CR 701.21a) UNION the printed `Annihilator` keyword (a "
            "forced-sacrifice-on-attack that the effect lane doesn't "
            "independently derive). Recall 0.945 vs the old regex; 10 "
            "preset-only, ALL the same named, deferred (not fixed here — a "
            "lane change, out of scope for a view conversion) structural "
            "gap: the sacrifice clause is embedded inside a CONDITIONAL / "
            "MODAL / vote / dice-roll branch phase doesn't decorate as a "
            "typed `edict_makers`-recognized effect at the unit's top "
            "level — a Council's-dilemma vote (Capital Punishment, "
            "Tyrant's Choice), an 'unless that player sacrifices' cost-"
            "alternative (Demanding Dragon, Indulgent Tormentor), a "
            "dice-roll modal (Earth-Cult Elemental, Myrkul's Edict), or an "
            "ETB 'you may choose' branch (Lurking Spinecrawler). The same "
            "root cause the extra-turns preset's deferred residue names "
            "(a Time Warp effect nested inside a vote/dice/conditional "
            "branch is likewise undecorated) — a shared, well-understood "
            "crosswalk limitation, not several unrelated bugs. 10 cards of "
            "183 (recall 0.945) — the view is still correct to ship; these "
            "are the residual tail."
        ),
        keywords=("Annihilator",),
        signal_keys=("edict_makers",),
        should_match=("Diabolic Edict",),
        should_not_match=("Lightning Bolt", "Wrath of God", "Vindicate"),
    ),
    # ── Task #83 structural views: same target-type predicate as the
    # removal family above, bound to the SACRIFICE (edict) shape only —
    # ``edict_makers``, like ``removal``, emits ``subject=""`` (see that
    # lane's docstring). No ``generous_any``: a burn spell never forces a
    # sacrifice, so the "Any" fallback never applies to an edict.
    Preset(
        name="creature-edict",
        description=(
            "Forced-sacrifice of a creature (Diabolic Edict, Fleshbag "
            "Marauder, Plaguecrafter, Liliana's Triumph, Sheoldred's "
            "Edict). Mass forms like Barter in Blood also match. "
            "Includes 'creature or planeswalker' modals."
        ),
        concept=_removal_edict_concept("Creature", family="edict"),
        should_match=("Diabolic Edict",),
        should_not_match=("Lightning Bolt", "Shatter", "Sinkhole"),
    ),
    Preset(
        name="artifact-edict",
        description=(
            "Forced-sacrifice of an artifact — rare category, mostly "
            "Tribute to the Wild, Pick Your Poison, Perilous Predicament."
        ),
        concept=_removal_edict_concept("Artifact", family="edict"),
        should_match=("Tribute to the Wild",),
        should_not_match=("Lightning Bolt", "Diabolic Edict"),
    ),
    Preset(
        name="enchantment-edict",
        description=(
            "Forced-sacrifice of an enchantment — rare category "
            "(Dromoka's Command, Pharika's Libation, Abzan Advantage)."
        ),
        concept=_removal_edict_concept("Enchantment", family="edict"),
        should_match=("Dromoka's Command",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="land-edict",
        description=(
            "Forced-sacrifice of a land. Includes mass LD like Wildfire, "
            "plus Smallpox-style combined effects. Distinct from "
            "``land_sacrifice_makers`` (a YOU-sac cost engine — Zuran "
            "Orb): this is a FORCED sacrifice a caster inflicts."
        ),
        concept=_removal_edict_concept("Land", family="edict"),
        should_match=("Wildfire",),
        should_not_match=("Lightning Bolt", "Armageddon"),
    ),
    Preset(
        name="planeswalker-edict",
        description=(
            "Forced-sacrifice of a planeswalker — very rare. Usually "
            "appears as 'sacrifices a creature or planeswalker' in modern "
            "edict design (Sheoldred's Edict, Angrath's Rampage), so this "
            "overlaps heavily with creature-edict."
        ),
        concept=_removal_edict_concept("Planeswalker", family="edict"),
        should_match=("Sheoldred's Edict",),
        should_not_match=("Lightning Bolt", "Diabolic Edict"),
    ),
    Preset(
        name="universal-edict",
        description=(
            "Forced-sacrifice of any permanent type: a sacrifice filter "
            "whose bare core-type word is the literal 'Permanent' (Shard "
            "of the Void Dragon, Martyr's Bond). Unions the Annihilator "
            "keyword (CR 702.86 — an attack trigger forcing the defender "
            "to sacrifice N permanents of their choice, a first-class "
            "Scryfall keyword fact the target-type walk doesn't "
            "independently reach)."
        ),
        keywords=("Annihilator",),
        concept=_removal_edict_concept("Permanent", family="edict"),
        should_match=("Shard of the Void Dragon", "Martyr's Bond"),
        should_not_match=("Lightning Bolt", "Diabolic Edict", "Wildfire"),
    ),
    # ── Land-animation (manlands + Earthbend) ──
    Preset(
        name="land-animation",
        description=(
            "Turns a land into a creature — task #83 structural-view "
            "conversion: the concept is DELIBERATELY SPLIT across three "
            "signal keys (see each lane's own exclusion comment): "
            "`land_protection` (self-animating manlands — Mutavault, "
            "Treetop Village, the Restless cycle — deliberately NOT in "
            "land_creatures_matter; also carries reverse-animators like "
            "Ashaya, hence prec ~0.66 for this composite) + "
            "`land_creatures_matter` (anthem/maker land-creature builds) + "
            "`earthbend_makers` (the Avatar-crossover Earthbend keyword, "
            "CR 701.66, prec 1.00) UNION the printed `Earthbend` and "
            "`Awaken` (CR 702.113 — turns a land you control into a "
            "creature, the alternative-cost Battle for Zendikar mechanic; "
            "the whole 15-card Awaken cycle was the entire preset-only "
            "residue before this union) keywords. Recall 0.88 vs the old "
            "regex; the remaining 3 preset-only (Gaea's Liege, Graceful "
            "Antelope, Tide Shaper) are confirmed old-regex false "
            "positives — each says '...until THIS CREATURE leaves the "
            "battlefield' (a duration clause referencing the ABILITY's OWN "
            "source, a creature), which the old regex's lazy "
            "'land...becomes a[^.]*?creature' pattern matched even though "
            "the land becomes a Forest/Island/Plains (a land TYPE change, "
            "CR 305.1), never a creature. Signals correctly exclude these; "
            "0 genuine losses."
        ),
        keywords=("Earthbend", "Awaken"),
        signal_keys=(
            "land_protection",
            "land_creatures_matter",
            "earthbend_makers",
        ),
        should_match=("Mutavault", "Treetop Village"),
        should_not_match=("Lightning Bolt", "Counterspell", "Sinkhole"),
    ),
    # ── Vehicles (Crew) ──
    Preset(
        name="crew",
        description=(
            "Vehicles with a crew cost — tap creatures with total power "
            "N or greater to animate the Vehicle until end of turn "
            "(CR 702.122). Vehicles are a distinct archetype."
        ),
        keywords=("Crew",),
        should_match=("Unicycle",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Prototype (alt-cost smaller mode) ──
    Preset(
        name="prototype",
        description=(
            "Cast the card for its prototype cost with different mana "
            "value, color, and power/toughness — usually a smaller, "
            "cheaper mode (CR 702.160). The Scryfall layout is also "
            "'prototype' on these cards."
        ),
        keywords=("Prototype",),
        layouts=("prototype",),
        should_match=("Blitz Automaton",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Firebending (combat-triggered red mana) ──
    #
    # Structural view (task #83): signal keys `firebending_makers` (the
    # keyword-bearer — the lane reads the caller-supplied Scryfall keyword
    # array directly, same fact the `keywords=("Firebending",)` arm below
    # would test) + `firebending_matters` (a keyword-less GRANT of
    # Firebending — Sozin's Comet, Iroh, Fire Nation Palace/Cadets/Turret —
    # via `has_structural_firebending_grant` plus a bucket-B
    # `synth_firebending_matters` tail for grants baked into a make_token
    # spec's own body). See `_deck_forge.crosswalk_signals._bending_lanes`.
    # `keywords=("Firebending",)` stays as a belt-and-suspenders union (the
    # landfall precedent): a card with no oracle_id/phase parse degrades the
    # signal_keys arm to empty exactly like every other regex/keyword arm
    # does on a field it can't read, so keeping the raw keyword-array test
    # costs nothing and covers that corner. 1 preset-only residue (per the
    # lane's own docstring): Firebending Lesson — the card's OWN NAME
    # contains "Firebending" with zero mechanic relevance; the lane's
    # narrower structural anchor already sheds this over-catch the deleted
    # flat regex used to double-count, so this is a regex-over-catch shed,
    # not a loss.
    Preset(
        name="firebending",
        description=(
            "Combat-triggered red mana: whenever this creature attacks, "
            "add N red mana until end of combat (CR 702.189). Avatar "
            "crossover mechanic."
        ),
        keywords=("Firebending",),
        signal_keys=("firebending_makers", "firebending_matters"),
        should_match=("Mai and Zuko", "Sozin's Comet"),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Turn manipulation ──────────────────────────────────────────────
    # Extra-turn / extra-combat / extra-upkeep payoffs that commander
    # archetypes (Obeka, Aurelia, Godo, Isshin, Narset) are built around.
    #
    # extra-turns task #83/#85 structural-view conversion: CONVERTED
    # (2026-07-12, phase v0.23.0). The prior deferral found all 9
    # preset-only residue cards were a genuine recall gap, not a scope/
    # precision boundary — fixed at the lane, not papered over here:
    # Chance for Glory / Perch Protection / Ugin's Nexus are a no-node-
    # at-all static-collapse or ``Unimplemented`` residue phase leaves
    # zero real ``ExtraTurn`` trace for (a ``tree_synthesis._arm_extra_
    # turns`` bucket-B idiom scan, gap-gated on
    # ``crosswalk.has_nested_extra_turn`` finding nothing); Expropriate /
    # Plea for Power (``Vote.per_choice_effect``), Stitch in Time / Ral
    # Zarek (``FlipCoin``/``FlipCoins.win_effect``), and Ichormoon
    # Gauntlet (a static ability's ``GrantAbility.definition``) all carry
    # a REAL typed ``ExtraTurn`` node the narrow per-unit effect-chain
    # walk never reached — ``has_nested_extra_turn``'s generic deep-field
    # walk (the ``has_nested_roll_die``/``has_nested_flip_coin`` precedent)
    # now reaches all three shapes. See
    # `_deck_forge.crosswalk_signals._extra_turns` for the lane and
    # `_card_ir.tree_synthesis._arm_extra_turns` for the synthesis arm.
    Preset(
        name="extra-turns",
        description=(
            "Take another turn after this one. Time Walk effects — the "
            "pillar of Obeka / Narset / Sakashima extra-turns archetypes "
            "(Time Walk, Temporal Manipulation, Nexus of Fate, "
            "Expropriate, Temporal Trespass). Structural view (task #83/"
            "#85): signal key `extra_turns` — an ExtraTurn effect, "
            "regardless of who takes it (CR 500.7)."
        ),
        signal_keys=("extra_turns",),
        should_match=("Time Walk", "Temporal Manipulation", "Nexus of Fate"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Illusionist's Gambit fix (task #85, phase v0.23.0): the ``extra_combats``
    # signal now reads the ``illusionists_gambit_additional_combat_swallowed``
    # ledgered bridge (`_deck_forge.bridge_ledger`) — the ``Condition_If``
    # SwallowedClause parse-warning on "After this phase, there is an
    # additional combat phase" was STILL unstructured at v0.23.0 (unchanged
    # since v0.20.0), so this stays a bridge (an upstream_parse_failure,
    # not a forced arm) rather than a real typed node.
    Preset(
        name="extra-combats",
        description=(
            "Additional combat phase (CR 505/506). Aggravated Assault, "
            "Seize the Day, Waves of Aggression — the pillar of Aurelia / "
            "Godo / Isshin commander archetypes and multi-combat 60-card "
            "lists. Structural view (task #83): signal key `extra_combats` "
            "— an AdditionalPhase effect whose phase is a combat phase (see "
            "`_deck_forge.crosswalk_signals._extra_combats`)."
        ),
        signal_keys=("extra_combats",),
        should_match=("Aggravated Assault", "Seize the Day", "Waves of Aggression"),
        should_not_match=("Lightning Bolt", "Serra Angel"),
    ),
    Preset(
        name="extra-upkeeps",
        description=(
            "Additional upkeep step. Paradox Haze and Obeka Splitter of "
            "Seconds turn beginning-of-upkeep triggers into repeatable "
            "engines — the core of upkeep-payoff archetypes. The "
            "crosswalk `extra_upkeep` signal also folds in the wider "
            "'additional beginning phase' idiom (Sphinx of the Second "
            "Sun) — a beginning phase INCLUDES the upkeep step (CR 501.1), "
            "so it's the same archetype under a broader templating "
            "(task #83 structural-view conversion)."
        ),
        signal_keys=("extra_upkeep",),
        should_match=("Obeka, Splitter of Seconds", "Paradox Haze"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # ── Blink / ETB abuse ──────────────────────────────────────────────
    # Exile-then-return-to-battlefield cards that re-trigger enter-the-
    # battlefield effects. task #83 structural-view conversion: the
    # ``blink_flicker`` key is shared by TWO producers (the literal
    # exile-and-return MAKER, always HIGH confidence, and
    # apply_membership_floor's "worth blinking" payoff cross-open off a
    # card's own strong ETB value — Academy Journeymage/Mulldrifter,
    # always LOW) — a raw signal_keys union would catch both, cratering
    # precision (the task #83 preset-scoping pass measured .06 over the
    # raw union). ``_blink_maker_concept`` filters to the MAKER half only
    # (crosswalk_signals.blink_flicker_maker_present /
    # blink_flicker_is_maker). ``self_blink`` (a card exiling and
    # returning ITSELF — Aetherling — a genuinely different self-flicker
    # engine, CR 611.2b) unions in as a separate arm; the old regex's
    # "exile ... until this creature leaves the battlefield" (Angel of
    # Sanctions — exile + battlefield but no return) never matched either
    # arm, matching the regex's own should_not_match fixture.
    Preset(
        name="blink",
        description=(
            "ETB abuse: exile then return to the battlefield. Soulherder, "
            "Ephemerate, Eldrazi Displacer, Conjurer's Closet, "
            "Restoration Angel — re-trigger enter-the-battlefield effects "
            "by flickering creatures in and out of exile."
        ),
        signal_keys=("self_blink",),
        concept=_blink_maker_concept,
        should_match=("Soulherder", "Ephemerate", "Conjurer's Closet"),
        should_not_match=("Lightning Bolt", "Angel of Sanctions"),
    ),
)


def _build_registry() -> MappingProxyType[str, Preset]:
    """Construct the immutable PRESETS registry."""
    all_presets = _EVERGREEN_KEYWORDS + _KEYWORD_ABILITIES + _FUNCTIONAL_PRESETS
    names_seen: dict[str, Preset] = {}
    for p in all_presets:
        if p.name in names_seen:
            msg = f"duplicate preset name: {p.name!r}"
            raise ValueError(msg)
        names_seen[p.name] = p
    return MappingProxyType(names_seen)


PRESETS: MappingProxyType[str, Preset] = _build_registry()


def get_preset(name: str) -> Preset:
    """Look up a preset by name. Raises KeyError if unknown."""
    try:
        return PRESETS[name]
    except KeyError as exc:
        msg = f"unknown preset {name!r}. Known: {', '.join(sorted(PRESETS.keys()))}"
        raise KeyError(msg) from exc


def matches(name: str, card: dict) -> bool:
    """Convenience wrapper: ``get_preset(name).matches(card)``."""
    return get_preset(name).matches(card)


def list_presets() -> dict[str, str]:
    """Return ``name -> description`` for every preset, sorted by name."""
    return {name: PRESETS[name].description for name in sorted(PRESETS)}
