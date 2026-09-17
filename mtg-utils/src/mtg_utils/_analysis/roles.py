"""Template roles — what a card DOES for the Command Zone template.

One owner for the per-card role facts every deck surface counts: the four
hard-counted template roles (``ramp`` / ``card_draw`` / ``interaction`` /
``board_wipe``, plus ``lands``) via :func:`role_of`, the ramp read on its own via
:func:`is_ramp` (deck-stats, mana-audit, the ranking floor, and the tuner's cut
side all ask just that), and the Tier-2 advisory :func:`protects` (ADR-0024).

Every role is a VIEW over the signal path — a ``theme_presets`` preset (itself a
view over ``extract_signals``) and, where the compat Card carries a sharper read, the
card's IR. Nothing here hand-rolls a second detector: the bands these roles are
measured against live in ``budgets``; the search that SOURCES a role reads the same
preset the role counts by (ADR-0051).

The one text read is the documented no-coverage degrade: a card the signal path
cannot see (no ``oracle_id``, no phase parse, no sidecar — a synthetic fixture, a
cube pool run with no card-data) answers ramp from
``card_classify.ramp_by_text``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from mtg_utils._card_ir.compat_lookup import ir_for
from mtg_utils.card_classify import get_oracle_text, is_land, ramp_by_text
from mtg_utils.card_ir import Card
from mtg_utils.theme_presets import get_preset, has_signal_coverage

# Targeted removal + counterspells fold together into one `interaction` role (ADR-0024).
# creature-edict (forced sacrifice — Diabolic Edict, Fleshbag) is removal that bypasses
# hexproof/indestructible, so it counts too.
# `creature-removal` is deliberately EXCLUDED: its removal SPELLS are already matched by
# `removal`, while its Fight/Infect/Wither KEYWORDS tag static combat creatures (CR
# 702.90a infect is a combat ability, not spot removal) — over-counting Infect beaters
# as interaction and then cutting a poison payoff to "trim the over-band role".
#
# Task #86 (the `removal` preset's structural-view flip): pacify auras
# ("Enchanted creature can't attack or block" — Pacifism, Arrest) briefly
# dropped OUT of `interaction` here — the 9-key signal_keys union `removal`
# reads has no lane for "neutralizes a permanent without destroying/
# exiling/countering/bouncing/fighting/-X'ing it" (the task #83/#86 scoping
# pass adjudicated Pacifism/Arrest as structurally `enchantments_matter`,
# not a removal-family effect — correct routing, not a lane bug).
#
# Task #87 restores the credit via the DEDICATED structural concept this
# comment used to flag as out of scope: `pacify-aura`
# (theme_presets.py — signal_keys=("pacify_makers",),
# crosswalk_signals._pacify_makers). Deliberately its OWN preset, not
# folded into `removal`'s signal_keys union — CR 611.2 keeps "neutralizes"
# and "removes" genuinely distinct facts; `removal`'s should_not_match
# pin on Pacifism stays in force.
_INTERACTION_PRESETS = (
    "removal",
    "counterspell",
    "bounce",
    "creature-edict",
    "pacify-aura",
)

# Protection (Tier-2, advisory) must GRANT a protective quality to another permanent — a
# card that merely HAS indestructible/hexproof itself (Darksteel Reactor) protects only
# itself, not your board, so the keyword-on-itself presets are deliberately NOT used. We
# anchor on a granting verb + the keyword in oracle text (reminder text stripped).
_PROTECT_GRANT = re.compile(
    r"\b(?:gains?|have|has|gets?)\b[^.]*?"
    r"\b(?:hexproof|indestructible|ward|shroud|protection from)\b",
    re.IGNORECASE,
)
# Single-use saves that protect your stuff for a turn. Regenerate / phase-out must apply
# to a TARGET or your permanents — a creature that only regenerates or phases ITSELF
# (Frenetic Efreet) is self-protection, which doesn't count (same rule as the keywords).
_PROTECT_SAVE = re.compile(
    r"regenerate (?:target|another|each|all|up to|creatures? you control|"
    r"permanents? you control)|"
    r"prevent (?:the next|all|that)\b[^.]*\bdamage|"
    r"(?:target|another target|each|all|creatures? you control|permanents? you control)"
    r"[^.]*phases? out",
    re.IGNORECASE,
)
# Pillow-fort / attack-deterrent effects that protect YOU the player (Ghostly Prison,
# Propaganda, Sphere of Safety, Crawlspace, Silent Arbiter, …).
_PROTECT_DETER = re.compile(
    r"can'?t attack you|"
    r"no more than \w+ creatures? can attack",
    re.IGNORECASE,
)
# Redirect answers (CR 115.7): a free "change the target" / "choose new targets for
# target spell or ability" (Misdirection, Deflecting Swat, Divert) answers removal aimed
# at your board like the counterspells protects() already counts. Anchored on "target
# spell" / "spell or ability" — NOT "the copy" — so copy spells (Twincast, Fork) don't
# match. Umbra/totem armor (CR 702.89a) grants a destroy-replacement shield to your
# permanents (Umbra Mystic and the totem-armor auras themselves).
_PROTECT_REDIRECT = re.compile(
    r"change the target(?:\(s\))? of target spell"
    r"|choose new targets for target spell or ability"
    r"|\b(?:umbra|totem) armor\b",
    re.IGNORECASE,
)


def _matches_preset(card: dict, name: str) -> bool:
    try:
        return get_preset(name).matches(card)
    except KeyError:
        return False


def _matches_any(card: dict, names: Sequence[str]) -> bool:
    return any(_matches_preset(card, name) for name in names)


def _ir_draws(ir: Card) -> bool:
    """Does the card's IR carry card advantage for YOU (the structured mirror of
    the ``card-draw`` / ``cantrip`` presets)? Phase projects every "draw a card" to
    ``category="draw"`` with the drawer in ``scope`` — ``you`` (Divination,
    Phyrexian Arena, Rhystic Study) or symmetric ``any`` (Howling Mine). Connive
    (``category="connive"``: "draw a card, then discard") is card advantage too —
    a distinct category the draw-word regex catches only via reminder text. An
    ``opp``-only draw (a giveaway) doesn't fill your card_draw slot.

    More precise than the presets, which match the word "draw" anywhere — including
    an OPPONENT'S draw (Underworld Dreams), a draw PAYOFF ("whenever you draw …" —
    Nadir Kraken), and reminder text — none of which is a draw SOURCE.

    NOT a superset of the ``card-draw`` PRESET, though: this compat-``Card``
    walk only ever tags a whole-ability's DIRECT effect chain ``category="draw"``
    — a ``draw_for_each`` fired from a nested branch (a ``Vote``
    ``per_choice_effect``, a granted ``GrantTrigger``/``CreateDelayedTrigger``
    descent — Truth or Consequences, Blitzball Stadium, Cosima // The
    Omenkeel) never surfaces here at all (task #93 corpus census: 10
    commander-legal cards fire the crosswalk's ``draw_for_each`` key with no
    matching ``_ir_draws`` category — see :func:`role_of`'s own union)."""
    return any(
        (e.category == "draw" and e.scope in ("you", "any")) or e.category == "connive"
        for ab in ir.all_abilities()
        for e in ab.effects
    )


# Mass-removal effect categories phase tags with the counter_kind="all" mass marker
# (DestroyAll / DamageAll / BounceAll — Wrath, Blasphemous Act, Evacuation).
_MASS_REMOVAL_CATS = frozenset({"destroy", "damage", "bounce"})


def _ir_board_wipe(ir: Card) -> bool:
    """Does the card's IR carry a creature/permanent BOARD WIPE — the structured mirror
    of the ``board-wipe`` preset? phase parses single-vs-mass and the projection keeps
    it as ``counter_kind="all"`` on a DestroyAll / DamageAll / BounceAll (a single
    Destroy does not). Three gates keep it to genuine sweepers:
      - subject is Creature / Permanent (not "destroy all LANDS" = mass land denial,
        not "all ARTIFACTS" = Bane of Progress);
      - controller != "you" (a "return all creatures YOU CONTROL" self-bounce, Denizen
        of the Deep, is a drawback; symmetric "any" / one-sided "opp" are kept);
      - no graveyard zone ("return all creature cards FROM YOUR GRAVEYARD" recursion,
        Lychguard, is not removal).

    A mass ``-X/-X`` shrink (Toxic Deluge, Drown in Sorrow) is read via the SIDECAR-v74
    ``Effect.toughness`` companion: a mass ``pump`` whose toughness factor is negative
    can kill, where a harmless power-only "-2/-0" (toughness factor 0) and a "+X/+X"
    anthem (factor > 0) are excluded. A SINGLE-target shrink is ``pump_target`` (not the
    mass ``pump``). Covers both a mass-shrink SPELL (Toxic Deluge) and a STATIC
    mass-debuff anthem (Elesh Norn's opponents' -2/-2 — SIDECAR v75)."""
    for ab in ir.all_abilities():
        for e in ab.effects:
            subj = e.subject
            if (
                subj is None
                or subj.controller == "you"
                or not ("Creature" in subj.card_types or "Permanent" in subj.card_types)
                or any("graveyard" in z for z in e.zones)
            ):
                continue
            if e.category in _MASS_REMOVAL_CATS and e.counter_kind == "all":
                return True
            tuf = e.toughness
            if e.category == "pump" and tuf is not None and tuf.factor < 0:
                return True
    return False


# Effect categories that ARE a real answer (so a card carrying one is not pure graveyard
# recursion). topdeck_stack is a tuck ("put target X on top of its owner's library" —
# Rootrunner, or graveyard hate); the rest are removal / counters / edict / pacify.
_IR_REAL_ANSWER_CATS = frozenset(
    {
        "destroy",
        "damage",
        "counter_spell",
        "exile",
        "restriction",
        "sacrifice",
        "topdeck_stack",
    }
)


def _ir_recursion_only(ir: Card) -> bool:
    """True iff the card's ONLY interaction-shaped effect is GRAVEYARD RECURSION — a
    bounce that returns a card from a graveyard, with no real answer alongside it.

    Such a card (Pharika's Mender, Pulse of Murasa, Neva — "return target creature OR
    enchantment card from your graveyard to your hand") is value/recursion, NOT removal;
    the ``removal`` / ``bounce`` presets misfire on the "X or Y card from graveyard"
    form their ``(?!\\s+card\\b)`` anchor can't exclude (the "card" doesn't immediately
    follow the first noun). The structural read vetoes those.

    A battlefield bounce (``in:battlefield`` target, or a bounce with no graveyard
    zone), a targeted ``-X/-X`` shrink (``pump_target`` with negative toughness), a
    tuck, or any destroy/damage/counter/exile/edict/pacify effect means the card has a
    REAL answer → NOT recursion-only (returns False). The veto only fires when a
    graveyard bounce is the SOLE interaction-shaped effect, so a card with no graveyard
    bounce can never be vetoed (``saw_gy_bounce`` stays False). Requires the SIDECAR-v76
    per-effect graveyard zones (before v76 a sibling's "from graveyard" bled onto
    battlefield bounces, which would have made answers like Aether Helix look
    recursion-only)."""
    saw_gy_bounce = False
    for ab in ir.all_abilities():
        for e in ab.effects:
            cat = e.category
            if cat == "bounce":
                if "in:battlefield" in e.zones:
                    return False  # targets a battlefield permanent — a real bounce
                if any("graveyard" in z for z in e.zones):
                    saw_gy_bounce = True
                else:
                    return False  # a non-graveyard bounce is a real tempo answer
            elif cat in _IR_REAL_ANSWER_CATS:
                return False
            elif (
                cat == "pump_target"
                and e.toughness is not None
                and e.toughness.factor < 0
            ):
                return False  # a targeted -X/-X shrink is removal
    return saw_gy_bounce


def is_ramp(card: dict) -> bool:
    """Does this NONLAND card accelerate your mana — the template's ``ramp`` role?

    THE ramp answer (ADR-0051): the ``ramp`` preset, a view over the signal path
    (rocks / dorks / rituals / granted mana, land-fetch-to-battlefield, mana
    amplifiers, extra land drops, Treasure makers you keep). A land is never ramp —
    it is the mana base (CR 305), counted by the ``lands`` role and the land band.

    A card the signal path cannot see at all (``has_signal_coverage`` false: no
    ``oracle_id``, no phase parse, no card-data) degrades to
    ``card_classify.ramp_by_text`` — the ONE surviving text read, so a no-sidecar
    ``deck-stats`` / cube goldfish still counts its rocks."""
    if is_land(card):
        return False
    if not has_signal_coverage(card):
        return ramp_by_text(card)
    return _matches_preset(card, "ramp")


def role_of(card: dict) -> set[str]:
    """Hard-counted template roles a card fills (a card may fill several).

    ``lands`` reads the type line; ``ramp`` is :func:`is_ramp` (the ``ramp`` preset,
    with the text degrade for a card the signal path can't see). ``card_draw`` and
    ``board_wipe`` read the candidate's Card IR when available (the ``draw`` category;
    the ``counter_kind="all"`` mass-removal marker), degrading to the curated presets
    when the card has no IR. The regex preset ALSO runs for ``board_wipe``: it still
    owns the ``-X/-X`` mass shrink the projection can't yet express (see
    ``_ir_board_wipe``). ``interaction`` stays on its presets for the positive match
    (the IR's ``destroy`` / ``restriction`` categories don't encode the pacify-vs-self
    and edict boundaries), but a structural VETO drops a preset hit the IR shows is pure
    graveyard recursion (``_ir_recursion_only`` — "return X or Y card from your
    graveyard", which the preset's ``card`` anchor misses).

    ``card_draw`` ALSO unions in the ``card-draw`` PRESET unconditionally
    (task #93) — ``_ir_draws`` alone under-counts: it only tags a whole-
    ability's DIRECT effect chain, so a ``draw_for_each`` reached only via
    a nested branch (Vote's ``per_choice_effect``, a granted
    ``GrantTrigger``/``CreateDelayedTrigger`` descent — Truth or
    Consequences, Master of Ceremonies, Blitzball Stadium, Cosima // The
    Omenkeel) fires the crosswalk key/preset (``card-draw`` unions
    ``card_draw_engine`` + ``draw_for_each`` since task #86) but never
    ``_ir_draws``'s own category walk. Corpus-verified (32,521
    commander-legal cards): 10 cards fire ``draw_for_each`` with no
    matching ``_ir_draws`` hit; this union closes all 10 with no new
    false positive (the preset itself is already the trusted source for
    the no-IR fallback below, unchanged)."""
    roles: set[str] = set()
    ir = ir_for(card)
    if is_land(card):
        roles.add("lands")
    elif is_ramp(card):
        roles.add("ramp")
    draws = (
        (ir is not None and _ir_draws(ir))
        or _matches_preset(card, "card-draw")
        or (ir is None and _matches_preset(card, "cantrip"))
    )
    if draws:
        roles.add("card_draw")
    if (ir is not None and _ir_board_wipe(ir)) or _matches_preset(card, "board-wipe"):
        roles.add("board_wipe")
    if _matches_any(card, _INTERACTION_PRESETS) and not (
        ir is not None and _ir_recursion_only(ir)
    ):
        roles.add("interaction")
    return roles


def _ir_redirect(ir: Card) -> bool:
    """A redirect answer (``cat=redirect`` — Misdirection, Deflecting Swat): changing a
    spell's target / choosing new targets answers removal aimed at your board like a
    counterspell. phase parses it as its own category, so this reads it structurally."""
    return any(
        e.category == "redirect" for ab in ir.all_abilities() for e in ab.effects
    )


def protects(card: dict) -> bool:
    """Tier-2 (advisory, ADR-0024): does this card protect your own board/commander?

    Counts counterspells (answer removal), REDIRECT answers (``cat=redirect``, read
    structurally), and cards that GRANT a protective quality to another permanent or
    save it for a turn — NOT a permanent that merely has hexproof / indestructible /
    ward on itself (which protects only itself, not your board).

    The grant/save/deter modes stay on oracle regex under ADR-0027 A3 (the regex
    residual here): the most common protect mode, a "gains protection from <color>"
    grant (Mother of Runes, Alseid, Apostle's Blessing — ~80 cards), projects to
    ``grant_keyword`` with an EMPTY ``counter_kind`` (the IR carries no "protection"
    marker; the keyword lives only in ``raw``), so an IR-only ``protects`` would
    silently drop them — a recall regression needing a project.py marker (out of A3
    scope). Umbra/totem armor likewise rides the regex (projects to ``grant_keyword``).
    """
    if _matches_preset(card, "counterspell"):
        return True
    ir = ir_for(card)
    if ir is not None and _ir_redirect(ir):
        return True
    text = re.sub(r"\([^)]*\)", " ", get_oracle_text(card) or "")  # strip reminder text
    return bool(
        _PROTECT_GRANT.search(text)
        or _PROTECT_SAVE.search(text)
        or _PROTECT_DETER.search(text)
        or _PROTECT_REDIRECT.search(text)
    )
