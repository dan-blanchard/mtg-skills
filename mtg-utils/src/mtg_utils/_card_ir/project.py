"""Project phase-rs's parsed ``card-data.json`` records into the Card IR.

phase already binds the hard part — the "for each Y" operand — as
``Ref → ObjectCount{filter}`` / ``Multiply{factor, inner}`` nodes, even when the
surrounding effect is wrapped in a ``GenericEffect``. This module walks those
trees into the synergy-shaped :mod:`mtg_utils.card_ir`, then hands off to
:func:`mtg_utils._card_ir.supplement.supplement_card` for the payoff/scope holes
phase leaves in description strings.

``project_card`` takes the list of phase face-records that share one
``scryfall_oracle_id`` (one element for a single-faced card; the front/back faces
for a DFC) so DFC faces become distinct :class:`~mtg_utils.card_ir.Face` objects
with no cross-face bleed.
"""

from __future__ import annotations

import re
from dataclasses import replace

from mtg_utils._card_ir.supplement import recover_effect_from_text, supplement_card
from mtg_utils.card_ir import (
    Ability,
    Card,
    Condition,
    Effect,
    Face,
    Filter,
    Quantity,
    Trigger,
)


def _norm(token: object) -> str:
    """Lowercase + strip non-alphanumerics, so ``DealDamage``/``deal_damage`` match."""
    return re.sub(r"[^a-z0-9]", "", str(token).lower())


def _norm_counter_kind(raw: object) -> str:
    """Normalize a phase ``counter_type`` into a clean kind token, recovering the
    +1/+1 signature phase sometimes mis-parses (ADR-0027).

    phase emits a clean ``"P1P1"`` for most placements, but when adjacent rider
    text leaks into the field it returns a garbled string that still CONTAINS the
    ``+1/+1`` signature — ``"additional +1/+1"`` (Necromantic Summons, Turntimber
    Symbiosis), ``"flying and with X +1/+1"`` (Dralnu's Pet), ``"trample. the token
    enters with X +1/+1"`` (Printlifter Ooze), ``"a number of +1/+1"`` (Grave
    Endeavor's ``enter_with_counters``). A clean ``_norm`` of those yields a
    distinct junk token (``additional11`` / ``flyingandwithx11`` / …) that no lane
    reads, so the +1/+1 placement is lost. Detect the ``+1/+1`` substring in the
    PRE-normalized text and collapse to ``p1p1``; likewise ``-1/-1`` → ``m1m1``.
    Anything else falls through to the ordinary ``_norm`` (clean kinds, named
    counters like ``study`` / ``growth`` stay themselves). CR 122.1 / 614.12."""
    if isinstance(raw, str):
        if "+1/+1" in raw:
            return "p1p1"
        if "-1/-1" in raw:
            return "m1m1"
    return _norm(raw) if isinstance(raw, str) else ""


def _str_tuple(value: object) -> tuple[str, ...]:
    """A JSON list field → tuple of its string items (() if absent/not a list)."""
    if not isinstance(value, list):
        return ()
    return tuple(x for x in value if isinstance(x, str))


def _as_list(value: object) -> list:
    """A JSON list field → the list (or [] if absent/not a list)."""
    return value if isinstance(value, list) else []


# ── effect.type discriminant → synergy category ───────────────────────────────
_EFFECT_CATEGORY: dict[str, str] = {
    "draw": "draw",
    "dealdamage": "damage",
    "damageall": "damage",
    "damageeachplayer": "damage",
    "token": "make_token",
    "populate": "make_token",
    "investigate": "make_token",
    "incubate": "make_token",
    # Amass (CR 701.47) primarily GROWS an Army with +1/+1 counters, making an Army
    # token only if you have none — modal, so it gets its own category and fans to
    # both tokens_matter and counters_matter rather than masquerading as a pure token.
    "amass": "amass",
    "conjure": "make_token",
    # Manifest puts a CARD onto the battlefield face down as a 2/2 (CR 701.40 + 708)
    # — it is NOT a token (CR 122.1 distinguishes them) and a token doubler does not
    # double it. Own `manifest` category → facedown_matters, mirroring cloak.
    "manifest": "manifest",
    "manifestdread": "manifest",
    # Fabricate (CR 702.123) is MODAL: create Servo tokens OR put +1/+1 counters.
    # Own category fans to both tokens_matter and counters_matter (make_token alone
    # dropped the counter mode).
    "fabricate": "fabricate",
    "addcounter": "place_counter",
    "putcounter": "place_counter",
    "putcounterall": "place_counter",
    "multiplycounter": "place_counter",
    "addpendingetbcounters": "place_counter",
    "removecounter": "remove_counter",
    "movecounters": "counter_move",  # Batch 7 — move counters between objects
    "proliferate": "proliferate",
    "mill": "mill",
    "gainlife": "gain_life",
    "loselife": "lose_life",
    "destroy": "destroy",
    "destroyall": "destroy",
    "exiletop": "exile",
    "bounce": "bounce",
    "counter": "counter_spell",
    # A single-target pump is distinct from a mass pump: only the mass form (and
    # static anthems, also category "pump") is the go-wide creatures_matter payoff;
    # a single "pump target creature you control" must not read as go-wide.
    "pump": "pump_target",
    "pumpall": "pump",
    "doublept": "pump_target",
    "doubleptall": "pump",
    "searchlibrary": "tutor",
    "mana": "ramp",
    "sacrifice": "sacrifice",
    "discard": "discard",
    "discardcard": "discard",
    "gaincontrol": "gain_control",
    "controlnextturn": "gain_control",
    "exchangecontrol": "gain_control",
    "givecontrol": "gain_control",
    "untap": "untap",
    "untapall": "untap",
    "tap": "tap",
    "tapall": "tap",
    "scry": "topdeck_select",
    "surveil": "topdeck_select",
    "dig": "topdeck_select",
    # Explore (CR 701.44): reveal top, land→hand else +1/+1 counter + top/GY choice.
    # Its own `explore_matters` lane (not topdeck_select — it's not a Brainstorm-style
    # stacker) captures the card-selection + counter + graveyard facets together.
    "explore": "explore",
    "fight": "fight",
    # Batch P — phase-native mechanic effects → their own categories.
    "becomemonarch": "monarch",
    "suspect": "suspect",
    "startyourengines": "speed",
    "increasespeed": "speed",
    "station": "station",
    "ventureinto": "venture",
    "ventureintodungeon": "venture",
    "takesinitiative": "venture",
    "connive": "connive",
    "preventdamage": "damage_prevention",
    "detain": "detain",
    "animate": "animate",
    "seek": "seek",
    "becomecopy": "clone",  # Batch 10 — "becomes a copy of" (clone synergy)
    "copyspell": "spell_copy",  # "copy target spell" (Twincast) — distinct from clone
    # Parse-completeness batch — common effect types that were falling to "other".
    "shuffle": "shuffle",
    "transform": "transform",
    "castfromzone": "cast_from_zone",  # impulse / free-cast / cast-from-exile-or-GY
    "attach": "attach",  # equip / aura attach — the voltron build-around
    "paycost": "pay_cost",
    "choose": "choose",  # a choice setup (color/type/mode); often the ParentTarget src
    "targetonly": "target_only",  # a pure-target effect (no state change of its own)
    "bounceall": "bounce",
    "gaincontrolall": "gain_control",
    "goad": "goad",
    "winthegame": "win_game",
    "losethegame": "lose_game",
    "monstrosity": "place_counter",  # +1/+1 counters up to N (Monstrous)
    "grantcastingpermission": "cast_from_zone",  # "you may cast/play …" permission
    # Parse-completeness tier 2 — the smaller remaining "other" effect types. Many
    # map to an EXISTING category because that IS the mechanic (adapt/bolster put
    # +1/+1 counters; myriad/encore make token copies; madness casts from exile).
    "revealtop": "reveal",
    "reveal": "reveal",
    "chooseoneof": "choose",
    "choosefromzone": "choose",
    # giveplayercounter is NOT here — it routes by counter_kind in _project_effect
    # (CR 122.1: counter kinds are non-interchangeable; a player poison/energy
    # counter is not a +1/+1 creature counter).
    "madnesscast": "cast_from_zone",
    "adapt": "place_counter",  # CR 701.43 — +1/+1 counters if it has none
    "bolster": "place_counter",  # CR 701.36 — +1/+1 on the weakest creature
    "myriad": "make_token",  # CR 702.116 — attacking token copies
    "encore": "make_token",  # CR 702.140 — token copies
    "createemblem": "emblem",
    "discover": "discover",
    "clash": "clash",
    "switchpt": "switch_pt",
    "removefromcombat": "remove_from_combat",
    "taketheinitiative": "venture",  # initiative shares the dungeon/venture lane
    "openattractions": "attraction",
    "setclasslevel": "class_level",
    "pairwith": "soulbond",
    "draftfromspellbook": "draft",  # Alchemy
    "becomeprepared": "prepared",
    "forceblock": "force_block",
    "addrestriction": "restriction",
    "changetargets": "redirect",
    "addtargetreplacement": "redirect",
    "registerbending": "bending",
    # Parse-completeness tier 3 — the remaining small effect-type tail. Single-mode
    # mechanics map to an existing category (renown = +1/+1 counters → place_counter);
    # modal/distinct named mechanics get their own honest category (rules-lawyer'd:
    # endure 702.62 = counters OR Spirit token; tribute 702.104 = modal; cloak 701.58
    # = face-down 2/2; forage 701.61 = a GY/Food cost).
    "renown": "place_counter",
    "searchoutsidegame": "tutor",
    "vote": "vote",
    # A plain "must attack" compulsion is force_attack, NOT goad: goad (CR 701.15a)
    # also forces the creature to attack a player OTHER than its controller, for one
    # turn cycle. force_attack feeds the forced_attack lane; goad is reserved for goad.
    "forceattack": "force_attack",
    "castcopyofcard": "spell_copy",
    "proliferatetarget": "proliferate",
    "counterall": "counter_spell",
    "revealfromhand": "reveal",
    "chooseandsacrificerest": "sacrifice",
    "flipcoinuntillose": "coin_flip",
    "exilehaunting": "exile",
    "returnasaura": "attach",
    "exchangelifewithstat": "set_life",
    "loseallplayercounters": "remove_counter",
    "exploreall": "explore",  # CR 701.44 — mass explore
    "freecastfromzones": "cast_from_zone",
    "copytokenblockingattacker": "clone",
    "exileresolvingspellinsteadofgraveyard": "exile",
    "endure": "endure",
    "tribute": "tribute",
    "cloak": "cloak",
    "forage": "forage",
    "learn": "learn",
    "specialize": "specialize",
    "planeswalk": "planeswalk",
    "double": "double",
    "setdaynight": "day_night",
    "intensify": "intensity",
    "solvecase": "solve_case",
    "blighteffect": "blight",
    "timetravel": "time_travel",
    "skipnextturn": "skip_turn",
    "skipnextstep": "skip_step",
    "collectevidence": "collect_evidence",
    "meld": "meld",
    "giftdelivery": "gift",
    "hideawayconceal": "hideaway",
    "grantnextspellability": "grant_spell_ability",
    "reducenextspellcost": "cost_reduction",
    "createdamagereplacement": "damage_replacement",
    "turnfaceup": "turn_face_up",
    "changespeed": "speed",
    "endcombatphase": "end_combat",
    "separateintopiles": "piles",
    "unattachall": "unattach",
    "becomeunprepared": "prepared",
    "rolltovisitattractions": "attraction",
    "chooseobjectsintotrackedset": "choose",
    "choosedrawnthisturnpayortopdeck": "choose",
    "grantextraloyaltyactivations": "grant_activation",
    "renowncounter": "place_counter",
    # Batch 0 — v0.1.60 structured effect types that previously fell to "other".
    "flipcoin": "coin_flip",
    "flipcoins": "coin_flip",
    "endtheturn": "end_the_turn",
    "extraturn": "extra_turn",
    "setlifetotal": "set_life",
    "exchangelifetotals": "set_life",
    "revealhand": "reveal_hand",
    "regenerate": "regenerate",
    "ringtemptsyou": "ring_tempt",
    "gainenergy": "energy",
    "phaseout": "phasing",
    "phasein": "phasing",
    "rolldie": "roll_die",
    # putontoporbottom / putatlibraryposition → topdeck_stack, but the WHERE
    # (top/bottom/nth) is load-bearing for the lane, so they get a dedicated
    # position-carrying handler in _single_effect (not this flat category map).
    "revealuntil": "dig_until",
    "exilefromtopuntil": "dig_until",
    "setcardtypes": "type_change",  # Batch 14 — sets/changes an object's types
    "goadall": "goad_all",  # Batch 14 — mass goad
}

# Mass (go-wide / non-targeted) bounce whose category collapses with the single-target
# Bounce in _EFFECT_CATEGORY (bounceall→bounce). It carries the non-interchangeable mass
# tell in counter_kind="all" (the SetTapState idiom) so a downstream type-payoff
# recursion lane (CR 115.10) can fire on a "return ALL <type>" form while a single
# target bounce stays out (CR 115.1, fixed magnitude 1 = generic value). Kept to
# bounce alone — pumpall / the tap variants are read by the creatures go-wide arm via
# its generic-set gate, not counter_kind, so marking them here would be inert noise.
# ChangeZoneAll is marked in _changezone_effect (its own zone-routing handler).
# DamageAll / DestroyAll carry the same counter_kind="all" mass tell so the single-
# target removal_matters arm (CR 115.1) can exclude the board-wipe form (CR 115.10):
# "deals N damage to EACH creature" / "destroy ALL creatures" is a board wipe, not
# the single-target destroy/burn the lane wants. The destroy arm's OTHER consumers
# (land_destruction / kill_engine read the type, not counter_kind) are unaffected.
_MASS_EFFECT_TYPES = frozenset({"bounceall", "damageall", "destroyall"})

# Batch 14 — AdditionalPhase.phase → the extra-phase category (distinct lanes).
_EXTRA_PHASE: dict[str, str] = {
    "begincombat": "extra_combat",
    "combat": "extra_combat",
    "upkeep": "extra_upkeep",
    "draw": "extra_draw",
    "drawstep": "extra_draw",
    "end": "extra_end",
    "endstep": "extra_end",
}

# Effect types that defer to recursion / the supplement rather than a category.
_RECURSE = {"genericeffect"}
_OTHER = {"unimplemented", "", "runtimehandled"}

# Pump-shaped static modifications (a +X/+X is one pump, not two).
_PUMP_MODS = {"adddynamicpower", "adddynamictoughness", "addpower", "addtoughness"}

# Card types, to split a made token's bare-string ``types`` list (which mixes the
# card type with subtypes) into card_types vs subtypes.
_CARD_TYPES = frozenset(
    {
        "Creature",
        "Artifact",
        "Enchantment",
        "Land",
        "Planeswalker",
        "Battle",
        "Instant",
        "Sorcery",
        "Tribal",
        "Kindred",
    }
)

# Keyword → cast-from zone, for Card.castable_zones.
_CASTABLE_ZONE_KEYWORDS: dict[str, str] = {
    "flashback": "graveyard",
    "escape": "graveyard",
    "disturb": "graveyard",
    "jumpstart": "graveyard",
    "aftermath": "graveyard",
    "embalm": "graveyard",
    "eternalize": "graveyard",
    "encore": "graveyard",
    "retrace": "graveyard",
    "foretell": "exile",
    "forecast": "hand",
}


def project_card(records: list[dict]) -> Card:
    """Project the phase face-records sharing one oracle_id into a Card."""
    faces = tuple(_project_face(rec) for rec in records)
    oracle_id = records[0].get("scryfall_oracle_id") or ""
    name = records[0].get("name") or ""
    card = Card(
        oracle_id=oracle_id,
        name=name,
        faces=faces,
        castable_zones=_castable_zones(records),
        parse_confidence="full",  # recomputed after the supplement
        many_copies=_allows_many_copies(records[0]),
    )
    card = supplement_card(card)
    # Post-supplement removal target-subject recovery (ADR-0027 removal_matters
    # shape 3): the supplement re-derives a `damage` / `destroy` CATEGORY from a
    # GenericEffect / Unimplemented body the projection left as `other` (Combo
    # Attack's "deal damage … to target creature", Broken Visage's "destroy target
    # … attacking creature"), but its SUBJECT stays None — the pre-supplement
    # _recover_removal_target_subject pass ran before the category existed. Re-run it
    # over the supplemented faces so the single-target creature/permanent subject is
    # rebuilt and removal_matters fires. Append-only on subject (a structured subject
    # is never overwritten); idempotent (an already-subject'd effect is untouched).
    card = replace(
        card,
        faces=tuple(
            replace(
                face,
                abilities=tuple(
                    _recover_removal_target_subject(a) for a in face.abilities
                ),
            )
            for face in card.faces
        ),
    )
    return replace(card, parse_confidence=_confidence(card))


def _confidence(card: Card) -> str:
    abilities = card.all_abilities()
    has_keywords = any(f.keywords for f in card.faces)
    if not abilities and not has_keywords:
        # No abilities AND no keywords means a VANILLA / textless face (Grizzly
        # Bears, a basic land): its complete mechanical content is its types + P/T,
        # which the IR already carries — there is nothing to parse, so it is fully
        # parsed. (A card that HAS oracle text but phase whiffed on never lands here:
        # _synthesize_from_oracle turns its sentences into abilities first. Verified
        # 0 text-bearing cards reach this branch.) The legacy "unparsed" label
        # conflated vanilla with failure; vanilla is `full`.
        return "full"
    effects = [e for a in abilities for e in a.effects]
    # An ability with no recovered effects, or any effect still 'other', is a gap.
    if any(e.category == "other" for e in effects):
        return "partial"
    if any(not a.effects for a in abilities if a.kind != "static"):
        return "partial"
    return "full"


def _synthesize_from_oracle(record: dict) -> list[Ability]:
    """phase recovered NO structured abilities AND the card has no keywords (a TOTAL
    parse failure, not a vanilla/keyword card) — synthesize one ability whose effects
    are the oracle's sentences as raw 'other' clauses, so the supplement's clause
    dispatch fills the gap. A vanilla face has no oracle sentences and yields nothing
    (correctly `full` — nothing to parse). Gated on the no-abilities-no-keywords
    condition, so a keyword card is never touched."""
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")  # drop reminder
    sentences = [
        s
        for s in (t.strip() for t in re.split(r"[.\n]", text))
        if len(s) > 4 and not _is_glue_sentence(s)
    ]
    effects = tuple(Effect(category="other", scope="any", raw=s) for s in sentences)
    return [Ability(kind="spell", effects=effects)] if effects else []


# Sentence fragments that are NOT a standalone effect — a sub-clause that qualifies a
# sibling effect ("where X is …" defines an operand; "if you do …" gates the prior
# clause), a Saga chapter marker, or a leftover. Dropping these from synthesis is
# accurate (they aren't effects) and avoids marking the card partial on glue alone.
_GLUE_SENTENCE = re.compile(
    r"^(?:where |if you do\b|rounded |then\b|otherwise\b|chapter [ivx0-9, ]+$"
    r"|and |or )",
    re.IGNORECASE,
)


def _is_glue_sentence(s: str) -> bool:
    return bool(_GLUE_SENTENCE.match(s))


# A trigger whose `raw` is only the CONDITION ("When ~ enters") with no effect after
# it (no comma, no sentence end) — phase parsed the trigger event but lost the effect.
# The effect survives in the oracle; we splice it back in from the matching sentence.
_BARE_TRIGGER = re.compile(r"^(?:when|whenever|at|as)\b[^,.]*$", re.IGNORECASE)


# Self-reference phrases phase folds to ``~`` ("When this creature enters" ->
# "When ~ enters"). Newer cards use "this creature"/"this permanent" in oracle text
# rather than the card name, so the oracle must be folded the same way to match.
# Self-reference phrases phase folds to ``~`` ("When this creature enters" ->
# "When ~ enters"). Newer cards use "this creature"/"this permanent" in oracle text
# rather than the card name, so the oracle must be folded the same way to match.
# NOT "this spell": phase keeps "When you cast this spell" literal (the spell on the
# stack is not the permanent self), so folding it would break that trigger's match.
_SELF_REF = re.compile(
    r"\bthis (?:creature|permanent|artifact|enchantment|land|planeswalker|saga"
    r"|vehicle|token|card|equipment|aura|battle|god|kindred)\b",
    re.IGNORECASE,
)
# A leading ability-word / keyword label before a trigger ("Landfall — Whenever a land
# …", "Alliance — Whenever another creature …") — stripped so a bare-trigger marker
# matches the trigger condition that follows the em-dash.
# allow commas so a multi-chapter marker "I, II, III, IV, V, VI —" is stripped too.
_LEADING_LABEL = re.compile(r"^[A-Za-z][\w ,'/]{0,30}—\s*")


def _self_oracle_sentences(record: dict) -> list[str]:
    """The card's oracle sentences with self-references folded to phase's self-name
    ``~`` (so a bare-trigger marker's "When ~ enters" matches the oracle's "When this
    creature enters" / "When <Name> enters"). Reminder text is dropped (it is
    explanatory, not the card's primary effect); legendaries also fold the pre-comma
    short name (Aang, … -> ~); a leading ability-word label ("Landfall — …") is
    stripped so the trigger after it matches."""
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    name = record.get("name") or ""
    names = {n for n in (name, name.split(",")[0].strip()) if n}
    for n in sorted(names, key=len, reverse=True):
        text = text.replace(n, "~")
    text = _SELF_REF.sub("~", text)
    return [
        _LEADING_LABEL.sub("", s.strip()) for s in re.split(r"[.\n]", text) if s.strip()
    ]


def _match_trigger_sentence(raw: str, sentences: list[str]) -> str | None:
    """The full oracle sentence for a bare-trigger marker. Prefers an exact prefix
    match; falls back to a trigger sentence CONTAINING all the marker's words (so a
    marker "Whenever ~ dies" matches a combined "Whenever ~ attacks or dies, …")."""
    lead = raw.lower()
    exact = next(
        (s for s in sentences if s.lower().startswith(lead) and len(s) > len(raw) + 2),
        None,
    )
    if exact is not None:
        return exact
    words = lead.split()
    trig = words[0] if words else ""
    return next(
        (
            s
            for s in sentences
            if s.lower().startswith(trig)
            and len(s) > len(raw) + 2
            and all(w in s.lower() for w in words)
        ),
        None,
    )


def _fill_bare_trigger(ab: Ability, sentences: list[str]) -> Ability:
    """Replace a triggered ability's bare-condition ``other`` raw with the full
    matching oracle sentence (condition + effect), so the supplement dispatches the
    effect phase dropped. No match → unchanged (stays an honest ``other``)."""
    if ab.kind != "triggered":
        return ab
    out: list[Effect] = []
    changed = False
    for e in ab.effects:
        raw = (e.raw or "").strip()
        if e.category == "other" and _BARE_TRIGGER.match(raw):
            full = _match_trigger_sentence(raw, sentences)
            if full is not None:
                out.append(replace(e, raw=full))
                changed = True
                continue
        out.append(e)
    return replace(ab, effects=tuple(out)) if changed else ab


# A bare Saga "Chapter N" label that the supplement drops LATER — at fill time it
# still occupies the ability, so treat such an ability as empty (mirrors
# supplement._CHAPTER_LABEL) so the oracle-fill reaches it.
_CHAPTER_LABEL = re.compile(r"^chapter [\divxlc, ]+$", re.IGNORECASE)


# Spells whose NAME is the effect's verb ("Regenerate" -> oracle "Regenerate target
# creature") — phase folds the name to `~`, dropping the verb ("~ target creature").
# Un-fold those so the supplement dispatches; only a closed verb-name set, and only
# when no verb follows the `~` (a real self-ref "~ deals …" keeps its verb).
_NAME_AS_VERB = frozenset(
    {"regenerate", "fight", "manifest", "conjure", "investigate", "populate"}
)


def _unfold_name_verb(ab: Ability, name: str) -> Ability:
    nm = name.split(",", 1)[0].strip().lower()
    if nm not in _NAME_AS_VERB:
        return ab
    out = [
        replace(e, raw=nm + (e.raw or "")[1:])
        if e.category == "other" and (e.raw or "").startswith("~ ")
        else e
        for e in ab.effects
    ]
    return replace(ab, effects=tuple(out))


def _is_sole_empty(ab: Ability) -> bool:
    """An ability phase recognized (cost/kind/trigger) but whose effect it wholly lost:
    NO effects (a Saga chapter phase failed -> `triggered: []`), only textless ``other``
    effects, or only a chapter-LABEL ``other`` (the supplement drops it later). A static
    ability is exempt (a no-effect static is a pure characteristic grant, not a gap)."""
    if ab.kind == "static":
        return False
    if not ab.effects:
        return True
    return all(
        e.category == "other"
        and (
            not (raw := (e.raw or "").strip())
            or raw in {"~", "~.", "."}  # phase's self-name placeholder (no real text)
            or bool(_CHAPTER_LABEL.match(raw))
        )
        for e in ab.effects
    )


def _fill_sole_empty(abilities: list[Ability], sentences: list[str]) -> list[Ability]:
    """Fill SOLE-empty abilities (effect lost, but the effect is in the oracle) by
    dispatching the card's oracle sentences. ONE sole-empty ability → gets all recovered
    categories the structured abilities don't already carry (deduped). MULTIPLE sole-
    empty abilities (e.g. a Saga's chapters phase wholly failed) → the recovered effects
    are distributed across them in oracle order (chapter abilities are in oracle order),
    one per ability — a best-effort attribution accurate at the CARD level (lanes are
    card-level). An empty with no recovered effect stays honestly empty."""
    empties = [i for i, a in enumerate(abilities) if _is_sole_empty(a)]
    if not empties:
        return abilities
    have = {e.category for a in abilities for e in a.effects if e.category != "other"}
    if len(empties) == 1:
        fills: list[Effect] = []
        seen: set[str] = set()
        for s in sentences:
            eff = recover_effect_from_text(s)
            if eff.category != "other" and eff.category not in have | seen:
                seen.add(eff.category)
                fills.append(eff)
        if fills:
            abilities[empties[0]] = replace(abilities[empties[0]], effects=tuple(fills))
            return abilities
        # POSITION fallback (e.g. a Saga chapter whose effect duplicates another
        # chapter's, so nothing is "missing"): the empty's effect is the recovered
        # oracle effect at its index — abilities and oracle sentences are in order.
        recovered_seq = [
            eff
            for s in sentences
            if (eff := recover_effect_from_text(s)).category != "other"
        ]
        i = empties[0]
        if i < len(recovered_seq):
            abilities[i] = replace(abilities[i], effects=(recovered_seq[i],))
        return abilities
    # multiple sole-empties (a Saga's chapters): distribute recovered effects across
    # them in oracle order, CYCLING if there are more empties than effects — Saga
    # chapters often share one effect ("I, II, III — …"), so every chapter gets one.
    # No "not in have" filter: a chapter may legitimately repeat a structured category.
    recovered = [
        eff
        for s in sentences
        if (eff := recover_effect_from_text(s)).category != "other"
    ]
    if recovered:
        for k, ab_i in enumerate(empties):
            abilities[ab_i] = replace(
                abilities[ab_i], effects=(recovered[k % len(recovered)],)
            )
    return abilities


# ── restriction-narrow (ADR-0027 projection deepening) ────────────────────────
# phase often parses a named-mechanic clause into a GENERIC carrier category —
# a static restriction, an Animate, a TargetOnly/Choose wrapper, a PayCost, a
# CoinFlip, a Tap, a Pump that grants a quoted ability — keeping the mechanic word
# only in the effect's `raw`. The signal lane the mechanic feeds reads a SPECIFIC
# effect category (cant_block / monarch / saddle / soulbond / phasing), so it can't
# fire off the generic carrier. We NARROW those carriers: when a carrier effect's
# raw encodes one of these mechanics, we APPEND a marker Effect carrying the precise
# category (never re-categorize — the original carrier may still feed a stax/animate
# lane). The append-only shape can never regress parse_confidence (a recognized
# marker is not an `other`), and mirrors how the supplement re-tags Unimplemented
# clauses. See ADR-0027 + the projection_worklist's "restriction not narrowed" set.

# Carriers we are willing to read a mechanic reference out of.
_NARROW_CARRIERS: frozenset[str] = frozenset(
    {
        "restriction",
        "animate",
        "target_only",
        "choose",
        "pump",
        "pay_cost",
        "coin_flip",
        "tap",
        "redirect",
        "make_token",
        "other",
    }
)
# cant_block grant is NARROWER: a created token's own "can't block" drawback
# (inside a make_token's quoted profile) is not a grant onto an enemy creature, so
# make_token is excluded for this one mechanic.
_CANT_BLOCK_CARRIERS: frozenset[str] = _NARROW_CARRIERS - {"make_token"}

# "<determiner> creature […] can't block" — a clause FORCING a targeted/affected
# creature OTHER THAN THE SOURCE to be unable to block (path-clearing / pillowfort
# grant, CR 509). The leading determiner excludes the bare self drawback
# "~ can't block" / "this creature can't block" (a vanilla downside, not a grant).
_CANT_BLOCK_REF = re.compile(
    r"\b(?:target|each|that|the chosen|chosen|enchanted|another) "
    r"(?:[a-z]+ )*?creature[^.]*?can'?t block\b",
    re.IGNORECASE,
)
# …but not the combat TAX "can't block with N" / "can't block more than" (a
# block-limiting effect, a different lane than an absolute can't-block grant).
_CANT_BLOCK_TAX = re.compile(r"can'?t block (?:with|more than)\b", re.IGNORECASE)
# Saddle (CR 702.171) reference: "becomes saddled" / "you saddle" / "whenever you
# saddle" — NOT a bare "saddles <X>" (a created token that saddles, a token-profile
# clause, not a saddle-payoff the avenue wants).
_SADDLE_REF = re.compile(
    r"\bsaddled\b|\bwhenever you saddle\b|\byou saddle\b", re.IGNORECASE
)
# Soulbond (CR 702.95) reference in a non-keyword card ("paired with a creature with
# soulbond" — Flowering Lumberknot's restriction).
_SOULBOND_REF = re.compile(r"\bsoulbond\b", re.IGNORECASE)
# Monarch (CR 725) reference buried in a carrier's raw ("you become the monarch",
# "unless that player is the monarch"). The Condition(kind=ismonarch) gate is lifted
# separately in signals.py; this catches the granted/become-monarch clauses phase
# folds into a tap/pump/restriction effect.
_MONARCH_REF = re.compile(r"becomes? the monarch|\bthe monarch\b", re.IGNORECASE)
# Phasing (CR 702.26) reference ("phases out", "phase in", "phased-out") buried in a
# pay_cost / coin_flip / choose / restriction / make_token carrier. (The Phasing
# KEYWORD is lifted from the keyword array in signals.py.)
_PHASING_REF = re.compile(r"\bphases? (?:in|out)\b|\bphased[- ]out\b", re.IGNORECASE)


def _narrow_mechanic_refs(ability: Ability) -> Ability:
    """Append precise marker effects for named mechanics phase left in a carrier's
    raw (restriction-narrow, ADR-0027). Append-only; the carrier effect is untouched
    so its own lanes still fire."""
    markers: list[Effect] = []
    have = {e.category for e in ability.effects}

    def want(cat: str) -> bool:
        # Don't duplicate a category phase already projected on this ability.
        return cat not in have and cat not in {m.category for m in markers}

    for e in ability.effects:
        raw = e.raw or ""
        if (
            e.category in _CANT_BLOCK_CARRIERS
            and want("cant_block")
            and _CANT_BLOCK_REF.search(raw)
            and not _CANT_BLOCK_TAX.search(raw)
        ):
            markers.append(Effect(category="cant_block", scope="any", raw=raw))
        if e.category in _NARROW_CARRIERS:
            if want("saddle") and _SADDLE_REF.search(raw):
                markers.append(Effect(category="saddle", scope="you", raw=raw))
            if want("soulbond") and _SOULBOND_REF.search(raw):
                markers.append(Effect(category="soulbond", scope="you", raw=raw))
            if want("monarch") and _MONARCH_REF.search(raw):
                markers.append(Effect(category="monarch", scope="you", raw=raw))
            if want("phasing") and _PHASING_REF.search(raw):
                markers.append(Effect(category="phasing", scope="you", raw=raw))
    if not markers:
        return ability
    return replace(ability, effects=ability.effects + tuple(markers))


# ── trigger-other raw-marker (ADR-0027 projection deepening) ──────────────────
# phase flattens many niche TRIGGERS to Trigger(event='other'): it parses the
# CONSEQUENCE (the draw / make_token / place_counter / damage / topdeck) as a
# typed effect, but the trigger CONDITION ("Whenever you win a coin flip",
# "Whenever you discover", "Whenever the Ring tempts you") survives only inside the
# effect's `raw` string — never as a typed trigger event. The signal lane the
# mechanic feeds reads a SPECIFIC effect category (coin_flip / ring_tempt /
# explore / discover / boast / exhaust / ninjutsu / scry_surveil), so it can't fire
# off the flattened 'other' trigger. We NARROW those triggers: when an
# event='other' triggered ability's effect raw encodes one of these trigger
# clauses, we APPEND a marker Effect carrying the precise category (append-only —
# the consequence effect is untouched, so its own lanes still fire). Each mechanic
# is CR-cited; markers are anchored on the SPECIFIC trigger phrase so a card that
# merely mentions the word in passing doesn't fire (no flood). The append-only
# shape can never regress parse_confidence (a recognized marker is not an `other`).
# See ADR-0027 + the projection_worklist's event='other' flattening set.

# Coin flip (CR 705.2) PAYOFF trigger: "Whenever you win/lose a coin flip …"
# (Chance Encounter, Karplusan Minotaur). Anchored on win/lose so a card that only
# instructs "flip a coin" as a cost is not double-tagged (that doer is already the
# coin_flip EFFECT category).
_COIN_FLIP_TRIG = re.compile(
    r"\b(?:win|lose)s? (?:a|the) (?:coin )?flip\b", re.IGNORECASE
)
# Discover (CR 701.57) PAYOFF trigger: "Whenever you discover, …" (Curator of
# Sun's Creation, "discover again"). The discover SOURCES carry the Discover
# keyword; this catches the keyword-less re-trigger payoff.
_DISCOVER_TRIG = re.compile(r"\bwhenever you discover\b", re.IGNORECASE)
# Explore (CR 701.44) PAYOFF trigger: "Whenever a creature you control explores, …"
# (Wildgrowth Walker, Nicanzil, Merfolk Cave-Diver, Lurking Chupacabra, Shadowed
# Caravel). The explore DOERS land in the explore EFFECT category; this is the
# keyword-less "cares when my creatures explore" payoff. Anchored on the
# "explores" verb after a creature subject (not the bare "explore" keyword) so an
# explore-doer's own reminder text isn't double-tagged.
_EXPLORE_TRIG = re.compile(r"\bcreature[^.]*?\bexplores\b", re.IGNORECASE)
# Boast (CR 702.142) PAYOFF trigger: "Whenever you activate a boast ability, …"
# (Frenzied Raider). Boast SOURCES carry the Boast keyword; this is the payoff.
_BOAST_TRIG = re.compile(r"\bactivate(?:s|d)? (?:a |an )?boast abilit", re.IGNORECASE)
# Exhaust (CR 702.177) PAYOFF trigger: "Whenever you activate an exhaust ability,
# …" (Rangers' Aetherhive, Adrenaline Jockey). Exhaust SOURCES carry an
# "Exhaust — {cost}:" ability the supplement tags; this is the keyword-less payoff.
_EXHAUST_TRIG = re.compile(
    r"\bactivate(?:s|d)? (?:a |an )?exhaust abilit", re.IGNORECASE
)
# Ninjutsu (CR 702.49) PAYOFF trigger: "Whenever you activate a ninjutsu ability,
# …" (Satoru Umezawa). The ninjutsu commander itself lacks the keyword.
_NINJUTSU_TRIG = re.compile(
    r"\bactivate(?:s|d)? (?:a |an )?ninjutsu abilit", re.IGNORECASE
)
# Scry (CR 701.22) / Surveil (CR 701.25) PAYOFF trigger: "Whenever you scry[ or
# surveil] …" / "Whenever you surveil …" (Matoya, Planetarium of Wan Shi Tong).
# The scry/surveil DOERS land in the topdeck_select effect category; this is the
# keyword-less "cares when I scry/surveil" payoff.
_SCRY_SURVEIL_TRIG = re.compile(r"\bwhenever you (?:scry|surveil)\b", re.IGNORECASE)
# Ring-tempt (CR 701.54) reference: a "Whenever the Ring tempts you" trigger
# (Faramir, Gandalf, Aragorn, Ringwraiths, Galadriel — phase flattens it to
# event='other') OR a "Ring-bearer" reference buried in any effect raw (Sauron has
# no tempt trigger — "unless ~ is your Ring-bearer" lives inside a make_token raw).
# Both are the precise mechanic boundary (CR 701.54 names "Ring-bearer"), so this
# one fires regardless of the trigger event (the only marker that does).
_RING_TEMPT_TRIG = re.compile(
    r"\bthe [Rr]ing tempts you\b|\b[Rr]ing-bearer\b", re.IGNORECASE
)
# Phasing (CR 702.26) PAYOFF trigger: "Whenever one or more … permanents phase
# out/in, …" (The War Doctor — phase flattens it to event='other' and keeps only
# the consequence's place_counter effect, the "phase out" condition surviving in
# its raw). The phase-out/in DOERS already ride the phasing keyword + the
# _PHASING_REF restriction-narrow marker (_narrow_mechanic_refs's carrier set,
# which place_counter is NOT in); this is the keyword-less "cares when permanents
# phase" payoff. Anchored on a permanent-subject "phase out/in" so a doer's own
# "~ phases out" reminder isn't double-tagged.
_PHASING_TRIG = re.compile(r"\bpermanents? phase(?:s)? (?:in|out)\b", re.IGNORECASE)
# Cycling (CR 702.29) PAYOFF trigger: "Whenever you cycle or discard a card, …"
# (Faith of the Devoted, Drake Haven, the Amonkhet cycling payoffs). phase has a
# typed `cycled` trigger for the self-cycle bonus, but flattens this DISCARD-OR-CYCLE
# payoff to event='other' (the "or discard" disjunction defeats the typed parse),
# keeping the trigger only in the consequence raw. The native cycling keyword + the
# `cycled` trigger event already bind the keyword-bearing / self-cycle cards; this is
# the keyword-less "cares when I cycle/discard" payoff. Anchored on "cycle or discard"
# (the payoff signature) so a plain cycling card's own reminder doesn't false-fire.
_CYCLING_TRIG = re.compile(
    r"\bcycles? or discard\b|\bwhenever you cycle\b", re.IGNORECASE
)
# Dice (CR 706, AFR/Unfinity) PAYOFF trigger: "Whenever you roll one or more dice/a
# die/a <N>/your <Nth> die, …" (Brazen Dwarf, Dee Kay, Feywild Trickster). phase
# parses the consequence (damage / make_token / place_counter / draw) but flattens the
# dice trigger to event='other', keeping the roll reference only in the raw. The
# roll-a-die DOERS already ride phase's roll_die effect; this is the keyword-less
# "cares when I roll" payoff. Anchored on the roll-trigger phrase.
_DICE_TRIG = re.compile(
    r"\bwhenever you roll\b|\broll(?:ed)? (?:one or more|your|a|\d+) (?:dice|die|\d)"
    r"|\brolled (?:one or more|\d+) (?:dice|die)\b",
    re.IGNORECASE,
)
# Dice (CR 706) as a SPELL/COST roll phase parses the consequence of but drops the
# roll_die effect of: "Roll two d6 and choose one result" (Valiant Endeavor, the
# *Endeavor cycle), "{6}, Roll a d8:" (Clay Golem cost), "reroll … dice" (Monitor
# Monitor). The roll-trigger payoffs ride _DICE_TRIG above; this is the spell/cost
# roll the dropped-static pass recovers. Mirrors the dice_matters regex anchors.
_DICE_REF = re.compile(
    r"\broll (?:a|one or more|two|\d+) (?:[a-z\-]+ )?(?:d\d+|dice|die)\b"
    r"|\breroll (?:any|a|that|one or more) (?:die|dice)\b"
    r"|\bresult of (?:the|a|your) (?:roll|die)\b",
    re.IGNORECASE,
)


def _narrow_trigger_other_refs(ability: Ability) -> Ability:
    """Append precise marker effects for named-mechanic TRIGGERS phase flattened to
    event='other', leaving the mechanic only in the effect raw (trigger-other
    raw-marker, ADR-0027). Append-only; the consequence effect is untouched so its
    own lanes still fire. Gated on event='other' so a typed trigger that phase
    already structured is never re-tagged — except ring-tempt's Ring-bearer scan,
    which catches a payoff with no tempt trigger (Sauron)."""
    is_other_trigger = (
        ability.kind == "triggered"
        and ability.trigger is not None
        and ability.trigger.event == "other"
    )
    markers: list[Effect] = []
    have = {e.category for e in ability.effects}

    def want(cat: str) -> bool:
        return cat not in have and cat not in {m.category for m in markers}

    for e in ability.effects:
        raw = e.raw or ""
        # Ring-tempt fires regardless of trigger event (Sauron's Ring-bearer
        # reference sits in a non-'other' attacks trigger).
        if want("ring_tempt") and _RING_TEMPT_TRIG.search(raw):
            markers.append(Effect(category="ring_tempt", scope="you", raw=raw))
        # Exhaust fires regardless of trigger event: Pit Automaton's exhaust PAYOFF
        # is a DELAYED trigger embedded inside an ACTIVATED ability ("{2},{T}: When
        # you next activate an exhaust ability …, copy it"), kind='activated' with no
        # 'other' trigger, so the gate below would skip it. The anchor
        # ("activate(s/d) an exhaust ability") is the precise payoff phrase — a
        # card merely carrying its own "Exhaust — {cost}:" reminder uses the keyword,
        # not "activate an exhaust ability", and exhaust SOURCES already ride the
        # keyword array, so this can't false-fire on a plain exhaust card (CR 702.177).
        if want("exhaust") and _EXHAUST_TRIG.search(raw):
            markers.append(Effect(category="exhaust", scope="you", raw=raw))
        # The rest require the event='other' flattening — they ARE the trigger
        # condition that phase dropped, so a typed trigger means phase kept it.
        if not is_other_trigger:
            continue
        if want("coin_flip") and _COIN_FLIP_TRIG.search(raw):
            markers.append(Effect(category="coin_flip", scope="you", raw=raw))
        if want("discover") and _DISCOVER_TRIG.search(raw):
            markers.append(Effect(category="discover", scope="you", raw=raw))
        if want("explore") and _EXPLORE_TRIG.search(raw):
            markers.append(Effect(category="explore", scope="you", raw=raw))
        if want("boast") and _BOAST_TRIG.search(raw):
            markers.append(Effect(category="boast", scope="you", raw=raw))
        if want("ninjutsu") and _NINJUTSU_TRIG.search(raw):
            markers.append(Effect(category="ninjutsu", scope="you", raw=raw))
        if want("scry_surveil") and _SCRY_SURVEIL_TRIG.search(raw):
            markers.append(Effect(category="scry_surveil", scope="you", raw=raw))
        # Phasing PAYOFF: an event='other' trigger whose consequence (a
        # place_counter, not in _narrow_mechanic_refs's carrier set) keeps the
        # "permanents phase out/in" condition only in its raw (The War Doctor).
        if want("phasing") and _PHASING_TRIG.search(raw):
            markers.append(Effect(category="phasing", scope="you", raw=raw))
        # Cycling PAYOFF: a "cycle or discard" trigger phase flattened to event='other'.
        if want("cycling_payoff") and _CYCLING_TRIG.search(raw):
            markers.append(Effect(category="cycling_payoff", scope="you", raw=raw))
        # Dice PAYOFF: a "whenever you roll …" trigger phase flattened to event='other'.
        if want("roll_die") and _DICE_TRIG.search(raw):
            markers.append(Effect(category="roll_die", scope="you", raw=raw))
    if not markers:
        return ability
    return replace(ability, effects=ability.effects + tuple(markers))


# ── conferred/granted-keyword re-parse (ADR-0027 projection deepening) ─────────
# When an effect/static GRANTS a keyword (or a keyword-ability) to a CLASS of
# objects — "spells you cast have affinity for artifacts" (Tezzeret),
# "Each ... card in your hand has ninjutsu {cost}", a token created "with devour 2"
# (Dragon Broodmother), an Aura/grant of a quoted ability ('Sliver creatures you
# control have "Whenever ~ is dealt damage, ~ deals that much damage to ..."') —
# phase parses it into a GRANT CARRIER (cast_with_keyword / grant_spell_ability /
# grant_keyword / clone / make_token / a generic carrier) but the SPECIFIC granted
# keyword the signal lane needs survives only inside the carrier's `raw`. The lane
# reads a precise keyword/effect (affinity_type ← the affinity keyword;
# damage_reflect ← a damage_received trigger; evasion_denial ← IgnoreLandwalk;
# connive ← the connive keyword-action; counter_spell ← a counter effect), so it
# can't fire off the grant carrier. We NARROW those carriers: when a carrier
# effect's raw encodes one of these GRANTED mechanics, we APPEND a marker Effect
# carrying the precise category (append-only — the carrier effect is untouched, so
# its own grant lanes still fire). FLOOD is the primary risk for a keyword grant,
# so every anchor is the EXPLICIT grant phrase ("<class> have/has/cast ... <kw>" /
# a quoted-ability body / "token with <kw>"), never a bare keyword mention. Each
# mechanic is CR-cited; the append-only shape can never regress parse_confidence
# (a recognized marker is not an `other`). See ADR-0027 + the projection_worklist's
# conferred/granted-keyword set.

# Carriers a granted keyword/ability can hide inside. Broader than the
# restriction-narrow set because grants also ride cast_with_keyword /
# grant_spell_ability / grant_keyword / clone.
_GRANT_CARRIERS: frozenset[str] = frozenset(
    {
        "cast_with_keyword",
        "grant_spell_ability",
        "grant_keyword",
        "clone",
        "make_token",
        "draw",
        "pump",
        "pump_target",
        "cast_from_zone",
        "other",
    }
)

# Affinity (CR 702.41) CONFERRED onto a class of spells: "<spells> you cast have
# affinity for <type>" / "the next spell you cast this turn has affinity for
# <type>". Anchored on "affinity for" — the conferring phrase, NOT the bare
# Affinity keyword (which the card's keyword array already carries). The granted
# type is captured into counter_kind for any future subject use; the lane itself is
# type-agnostic.
_AFFINITY_GRANT = re.compile(r"\bhave affinity for|\bhas affinity for", re.IGNORECASE)
# Madness (CR 702.35) CONFERRED onto a class of cards: "Each <Vampire> ... card you
# own ... has madness" (Falkenrath Gorger). Anchored on "has madness" — a grant,
# not the printed keyword (on the keyword array) nor an "if it has madness"
# condition (Anje — a condition-drop case this marker deliberately does not reach).
_MADNESS_GRANT = re.compile(r"\bhas madness\b", re.IGNORECASE)
# Foretell (CR 702.143) CONFERRED / referenced: "Each ... card in your hand ... has
# foretell" (Dream Devourer) OR a foretell PAYOFF reference ("the first card you
# foretell each turn", "whenever you foretell"). Anchored on "has foretell" (the
# grant) or "you foretell"/"foretold" (the cares-about reference) — NOT the printed
# Foretell keyword (keyword array).
_FORETELL_REF = re.compile(
    r"\bhas foretell\b|\byou foretell\b|\bforetold\b", re.IGNORECASE
)
# Devour (CR 702.82) on a CREATED TOKEN: "create a ... token with ... devour N"
# (Dragon Broodmother). Anchored on "devour" inside a make_token carrier's token
# profile (the carrier gate restricts this to token-grant rather than any mention).
_DEVOUR_TOKEN = re.compile(r"\bdevour \d+\b", re.IGNORECASE)
# Connive (CR 701.50) APPLIED to another creature ("up to one target creature you
# control connives" — Unstable Experiment) OR GRANTED inside a quoted ability ("it
# has 'Whenever ~ attacks, it connives'" — Copycrook). Anchored on the connive
# keyword-action VERB ("connive(s)"). The card's OWN intrinsic connive rides the
# Scryfall keyword + phase's connive effect; this catches the applied/granted form
# phase folded into a draw/clone carrier.
_CONNIVE_REF = re.compile(r"\bconnives?\b", re.IGNORECASE)
# Generic-landwalk evasion-denial (CR 702.14): the umbrella phrasing "Creatures
# with landwalk abilities can be blocked as though they didn't have those
# abilities" (Staff of the Ages) — phase parses the specific named-walk shapes into
# Effect(category='evasion_denial') but falls through to grant_keyword for the
# generic umbrella. Anchored on the umbrella "landwalk abilities ... blocked as
# though".
_LANDWALK_UMBRELLA = re.compile(
    r"landwalk abilities[^.]*?blocked as though", re.IGNORECASE
)
# Counter-spell (CR 701.5) GRANTED/QUOTED: "<class> you control gain '{T}: Counter
# target spell.'" (Psychic Trance) / a created token "with '... Counter target
# noncreature spell ...'" (Mage's Attendant). Anchored on the quoted "counter
# target ... spell/ability" verb phrase inside a grant/make_token carrier. The
# card's OWN top-level counter rides phase's counter_spell effect; this catches the
# counter buried inside a granted/quoted ability.
_COUNTER_GRANT = re.compile(r"counter target [^\".]*?(?:spell|ability)", re.IGNORECASE)
# Damage-reflection (CR 120) GRANTED/QUOTED: 'Sliver creatures you control have
# "Whenever this creature is dealt damage, it deals that much damage to ..."'
# (Spiteful Sliver). phase swallows the full quoted reflection ability inside a
# grant_keyword raw. Anchored TIGHTLY on the reflection signature: a "whenever ~ is
# dealt damage" TRIGGER (not an "if ~ is dealt damage this way" condition clause — a
# damage-source side effect, e.g. Marauding Raptor / Provoke the Trolls) AND a
# "deals that much damage" CONSEQUENCE (the reflection mirrors the received amount —
# not "deals N damage to it", which is a source dealing its own damage). Both anchors
# are required so a card that merely deals damage and checks "if dealt damage this
# way" doesn't fire.
_DAMAGE_REFLECT_TRIG = re.compile(
    r"\bwhenever\b[^.\"]*?\bis dealt damage\b", re.IGNORECASE
)
_DAMAGE_REFLECT_DEALS = re.compile(r"\bdeals that much damage\b", re.IGNORECASE)
# Myriad (CR 702.115) CONFERRED via a copy-with-modification: "becomes a copy of …
# except it has myriad" (Muddle, the Ever-Changing — CR 707.2). phase parses the
# copy as a `clone` carrier and drops the conferred keyword (counter_kind=''). The
# native myriad granters ("<class> have myriad" — Blade of Selves, Legion Loyalty)
# already carry counter_kind='myriad' on a grant_keyword effect; this catches the
# clone-exception conferral phase folds away. Anchored on "has/with myriad", never
# the bare keyword (the card's own printed myriad rides the keyword array).
_MYRIAD_GRANT = re.compile(r"\b(?:has|with) myriad\b", re.IGNORECASE)
# Cascade (CR 702.85) CONFERRED / referenced — phase rides the Scryfall `cascade`
# keyword for an INTRINSIC cascade spell, but the GRANTERS are keyword-less: "spells
# you cast have cascade" (Maelstrom Nexus, Yidris), "the next spell you cast … has
# cascade" (Maelstrom Nexus, the Doctor Who cascade-granters), "gain cascade" (Yidris),
# "with cascade" (Zhulodok's "Cascade, cascade"), and the cares-about "as you cascade"
# (Averna) / "cast a spell with cascade" (The First Doctor) payoff. Anchored on the
# conferring/reference phrase — "(have|has|gain[s]|with) cascade" / "as you cascade" /
# "spell with cascade" — NOT the bare keyword the card's own array already carries.
_CASCADE_GRANT = re.compile(
    r"\b(?:have|has|gains?|with) cascade\b|\bas you cascade\b"
    r"|\bspells? with cascade\b|\bcascade, cascade\b",
    re.IGNORECASE,
)
# Undying (CR 702.92) / Persist (CR 702.78) GRANTED to a class of creatures — phase
# rides the Scryfall keyword for an INTRINSIC undying/persist creature, but the
# GRANTERS are keyword-less: "creatures you control … have undying" (Mikaeus),
# "gains persist until end of turn" (Cauldron of Souls, Rhys, the persist-granters),
# "has persist as long as …" (the Scarecrows), a granted/quoted "gain undying"
# (Haunted One). Anchored on the GRANT VERB ("(gains?|have|has) undying/persist"),
# NOT the reminder text "(When a creature WITH undying dies …)" nor the bare keyword
# (the card's own array). The undying/persist counters mechanic stays its own lane.
_UNDYING_PERSIST_GRANT = re.compile(
    r"\b(?:gains?|have|has) (?:undying|persist)\b", re.IGNORECASE
)


def _narrow_conferred_keyword_refs(ability: Ability) -> Ability:
    """Append precise marker effects for keywords/abilities GRANTED to a class of
    objects, which phase leaves only in a grant carrier's raw (conferred-keyword
    re-parse, ADR-0027). Append-only; the carrier effect is untouched so its own
    grant lanes still fire. Every anchor is the explicit grant phrase (no flood)."""
    markers: list[Effect] = []
    have = {e.category for e in ability.effects}

    def want(cat: str) -> bool:
        return cat not in have and cat not in {m.category for m in markers}

    for e in ability.effects:
        if e.category not in _GRANT_CARRIERS:
            continue
        raw = e.raw or ""
        if want("affinity") and _AFFINITY_GRANT.search(raw):
            markers.append(Effect(category="affinity", scope="you", raw=raw))
        if want("madness") and _MADNESS_GRANT.search(raw):
            markers.append(Effect(category="madness", scope="you", raw=raw))
        if want("foretell") and _FORETELL_REF.search(raw):
            markers.append(Effect(category="foretell", scope="you", raw=raw))
        if want("cascade") and _CASCADE_GRANT.search(raw):
            markers.append(Effect(category="cascade", scope="you", raw=raw))
        if want("undying_persist") and _UNDYING_PERSIST_GRANT.search(raw):
            markers.append(Effect(category="undying_persist", scope="you", raw=raw))
        # Devour rides ONLY a make_token carrier's token profile (a "token with
        # devour N"), never a bare devour mention elsewhere.
        if e.category == "make_token" and want("devour") and _DEVOUR_TOKEN.search(raw):
            markers.append(Effect(category="devour", scope="you", raw=raw))
        if want("connive") and _CONNIVE_REF.search(raw):
            markers.append(Effect(category="connive", scope="you", raw=raw))
        if want("evasion_denial") and _LANDWALK_UMBRELLA.search(raw):
            markers.append(Effect(category="evasion_denial", scope="opp", raw=raw))
        if want("counter_spell") and _COUNTER_GRANT.search(raw):
            markers.append(Effect(category="counter_spell", scope="any", raw=raw))
        if (
            want("damage_reflect")
            and _DAMAGE_REFLECT_TRIG.search(raw)
            and _DAMAGE_REFLECT_DEALS.search(raw)
        ):
            markers.append(Effect(category="damage_reflect", scope="you", raw=raw))
        # Myriad conferred via a copy-exception (Muddle) → a grant_keyword marker
        # carrying counter_kind='myriad' (the same discriminator phase stamps on the
        # native "<class> have myriad" granters), gated so a card already carrying a
        # myriad-counter_kind grant isn't double-tagged.
        if (
            not any(m.counter_kind == "myriad" for m in markers)
            and "myriad" not in {e.counter_kind for e in ability.effects}
            and _MYRIAD_GRANT.search(raw)
        ):
            markers.append(
                Effect(
                    category="grant_keyword",
                    scope="you",
                    counter_kind="myriad",
                    raw=raw,
                )
            )
    if not markers:
        return ability
    return replace(ability, effects=ability.effects + tuple(markers))


# ── keyword-conditioned payoff refs (ADR-0027 projection deepening) ────────────
# A card that CARES about a discarded/cast/foretold card HAVING a named keyword —
# the discriminating "if it has <mechanic>" / "only to <mechanic>" clause that gates
# the payoff — is flattened by phase into the carrier effect's raw with no
# structured condition or keyword field. These are PAYOFF/ENABLER references (the
# "_matters = cares-about" rule), not keyword conferrals, and they ride carriers
# OUTSIDE _GRANT_CARRIERS (Anje's untap, Karfell's ramp), so the conferred-keyword
# pass can't reach them. We scan EVERY effect's raw for the precise gating phrase
# and APPEND a marker carrying the mechanic's payoff category (append-only). Each
# anchor is the explicit condition/restriction clause, never a bare keyword
# mention, so a card that merely uses the keyword itself can't false-fire:
#   madness  ← "if it has madness"  (Anje Falkenrath — a madness-gated untap loop;
#              distinct from _MADNESS_GRANT's "has madness" keyword conferral, which
#              this card lacks). CR 702.35.
#   mutate   ← "if it has mutate"   (Pollywog Symbiote — a keyword-less mutate
#              cast-payoff; the 34 mutate creatures ride the keyword array). CR 702.139.
#   foretell ← "to foretell"        (Karfell Harbinger — mana restricted to
#              foretelling; the foretell ENABLER axis phase keeps only in the ramp
#              raw). CR 702.143.
_MADNESS_COND = re.compile(r"\bif it has madness\b", re.IGNORECASE)
_MUTATE_COND = re.compile(r"\bif it has mutate\b", re.IGNORECASE)
_FORETELL_SPEND = re.compile(r"\bto foretell\b", re.IGNORECASE)


def _narrow_payoff_condition_refs(ability: Ability) -> Ability:
    """Append precise payoff markers for keyword-conditioned references phase left
    only in a non-grant carrier's raw (keyword-conditioned payoff refs, ADR-0027).
    Scans every effect (not carrier-gated — these ride untap/ramp carriers outside
    _GRANT_CARRIERS). Append-only; anchored on the explicit gating clause."""
    markers: list[Effect] = []
    have = {e.category for e in ability.effects}

    def want(cat: str) -> bool:
        return cat not in have and cat not in {m.category for m in markers}

    for e in ability.effects:
        raw = e.raw or ""
        if want("madness") and _MADNESS_COND.search(raw):
            markers.append(Effect(category="madness", scope="you", raw=raw))
        if want("mutate") and _MUTATE_COND.search(raw):
            markers.append(Effect(category="mutate", scope="you", raw=raw))
        if want("foretell") and _FORETELL_SPEND.search(raw):
            markers.append(Effect(category="foretell", scope="you", raw=raw))
    if not markers:
        return ability
    return replace(ability, effects=ability.effects + tuple(markers))


# ── +1/+1-counter ref recovery (ADR-0027 counters_matter pass 2) ───────────────
# counters_matter fires on ANY +1/+1 counter PLACEMENT regardless of recipient
# (self / on-others / on-attacking / distribute-among — all are sources, CR 122.1 /
# 122.6) and on a "has/with a +1/+1 counter" PAYOFF reference. phase structures the
# clean cases as a place_counter(p1p1) (the existing IR edge), but DROPS the +1/+1
# in two shapes, leaving it only inside a carrier effect's raw:
#   (1) PLACEMENT nested in a branch phase collapses to ONE parent effect — a
#       coin_flip ("Put a +1/+1 counter on ~ for each flip you won" — Crazed
#       Firecat), a roll_die ("For each even result, put a +1/+1 counter on ~" —
#       Clown Car, Journey to the Lost City, Overwhelming Encounter), a vote
#       (Emissary Green, Regna's Sanction), a pay-cost ("put that many +1/+1
#       counters" — the Adversary cycle, Chorus of the Conclave), a damage-prevention
#       replacement (Vigor, Stormwild Capridor), an exile/reanimate rider (Augusta,
#       Grey Host), or a distribute-among (Feast, Invoke Justice, Jared) — phase
#       keeps the parent category and drops the placement.
#   (2) PAYOFF REFERENCE — a creature/permanent referenced as HAVING a +1/+1
#       counter ("with a +1/+1 counter on it can't be blocked" — Herald; "if that
#       creature has a +1/+1 counter" — Bring Low; "for each +1/+1 counter on
#       creatures you control" — Deepwood Denizen; "power greater than its base
#       power" — Kutzil/Baird, the counters-on-it idiom). phase drops the +1/+1
#       restriction/condition to a restriction / draw / damage / cost_reduction
#       carrier, so the Counters filter-predicate the lane reads never lands.
# Recover both: append a place_counter(p1p1) marker for a PLACEMENT and a
# counters_have_ref marker for a PAYOFF reference, gated so neither fires on an
# ability that already carries a structured place_counter (phase kept it). Append-
# only; the carrier effect is untouched. The placement marker feeds the existing
# place_counter(p1p1)→counters_matter edge; counters_have_ref is read by the lane in
# signals.py. NO opponent gate: a +1/+1 placement is a source whoever receives it.
_P1P1_PLACE_REF = re.compile(
    r"\bput(?:s)?\b[^.]*?\+1/\+1 counter"
    r"|\bdistribute(?:s)?\b[^.]*?\+1/\+1 counter"
    r"|\bwith\b[^.]*?\+1/\+1 counters? on (?:it|them|him|her)\b"
    r"|\bwith X additional \+1/\+1 counter",
    re.IGNORECASE | re.DOTALL,
)
_P1P1_HAVE_REF = re.compile(
    r"\bwith (?:a |an |one or more |no )?\+1/\+1 counters? on (?:it|them|him|her)\b"
    r"|\bhas? (?:a |an )?\+1/\+1 counter on (?:it|him|her)\b"
    r"|\bwith (?:a )?counters? on (?:it|them|him|her)\b"
    r"|\+1/\+1 counters? you'?ve put\b"
    r"|\+1/\+1 counters? on creatures you control\b"
    r"|\bcounters? on creatures you control\b"
    r"|\bpower greater than its base power\b"
    r"|\bremove any number of \+1/\+1 counters\b",
    re.IGNORECASE,
)


def _narrow_counter_refs(ability: Ability) -> Ability:
    """Append +1/+1 markers phase left only in a carrier effect's raw: a
    place_counter(p1p1) for a PLACEMENT nested in a branch/cost/distribute parent,
    and a counters_have_ref for a "has/with a +1/+1 counter" PAYOFF reference
    (counters_matter pass 2, ADR-0027). Append-only; both gated on the ability
    having NO structured place_counter (so a clean placement phase already kept is
    never re-tagged), and the placement marker is preferred — when a raw both places
    AND references, the place_counter marker carries it (a placement IS a source)."""
    if any(e.category == "place_counter" for e in ability.effects):
        return ability
    have = {e.category for e in ability.effects}
    markers: list[Effect] = []
    placed = False
    for e in ability.effects:
        raw = e.raw or ""
        if not placed and _P1P1_PLACE_REF.search(raw):
            markers.append(
                Effect(
                    category="place_counter", scope="you", counter_kind="p1p1", raw=raw
                )
            )
            placed = True
    # A pure payoff reference (no placement recovered) — fire the have-ref marker.
    if not placed and "counters_have_ref" not in have:
        for e in ability.effects:
            raw = e.raw or ""
            if _P1P1_HAVE_REF.search(raw):
                markers.append(
                    Effect(category="counters_have_ref", scope="you", raw=raw)
                )
                break
    if not markers:
        return ability
    return replace(ability, effects=ability.effects + tuple(markers))


# ── token-subtype maker recovery (ADR-0027 token-subtype synergy) ──────────────
# A token MAKER for a named token subtype (Blood/Clue/Food/Treasure) normally rides
# a make_token Effect whose subject Filter carries the subtype — the signal lane
# (clue/food/treasure/blood_matters) reads that subtype. phase drops the subtype in
# two shapes, leaving it only in a carrier raw:
#   (1) CHOICE LIST — "Create your choice of a Blood token, a Clue token, or a Food
#       token" (Transmutation Font) flattens to Effect(category='choose',
#       subject=None); the choice-branch subtypes are lost.
#   (2) GRANTED/QUOTED ABILITY — 'Equipped creature ... has "Whenever ~ deals
#       combat damage, create a Blood token."' (Ceremonial Knife) folds the inner
#       make-token into a pump/grant carrier raw; the quoted body isn't re-parsed.
# Recover the named subtypes from the raw and APPEND a make_token marker Effect per
# subtype (subject Filter carries the subtype) so the existing make_token signal
# rule fires the right lane. Append-only; the carrier effect is untouched. Anchored
# on the explicit "<Subtype> token" phrase (a MAKER) or "Sacrifice a <Subtype>" (a
# SACRIFICE PAYOFF), never a bare subtype mention — general for clue/food/treasure/
# blood. Scans EVERY effect raw: phase drops the subtype off a make-token buried in a
# die-roll / vote / dilemma / coin-flip / cost branch (Hoarding Ogre, Seize the
# Spotlight, Treasure Chest) AND off a "Sacrifice a Food:" activated-ability cost
# (Wicked Wolf, Cauldron Familiar, Capenna Express — the food/treasure is the SAC
# fuel, which the lane reads off a sacrifice subject). The same-subtype dedup keeps a
# real make_token (which already carries the subtype on its subject) from double-firing.
# A MAKER reference: "<Subtype> token" — but ONLY counted when its raw also names a
# creation verb (create/creates), so a "discard a Blood token" / "exile a Food token"
# (a sac/discard outlet, NOT a maker) doesn't false-fire. The choice-list "Create your
# choice of a Blood token, a Clue token, …" and the d20/vote branch "Create a Treasure
# token" both carry "create" in the same raw.
_TOKEN_SUBTYPE_REF = re.compile(
    r"\b(blood|clue|food|treasure) tokens?\b", re.IGNORECASE
)
_TOKEN_CREATE_VERB = re.compile(r"\bcreates?\b", re.IGNORECASE)
_TOKEN_SUBTYPE_SAC = re.compile(
    r"\bsacrifice (?:a|an|another|\d+|two|three|four|five) "
    r"(blood|clue|food|treasure)s?\b",
    re.IGNORECASE,
)
# A CARES-ABOUT reference to a named token subtype WITHOUT making/sacrificing it —
# "<Subtype>s you control" (a count operand / anthem subject — Hobbit's Sting,
# Vihaan, Rent Is Due, Honored Dreyleader), "(was|were) (a|an) <Subtype>" (a sac
# condition — Evereth), "is a <Subtype>" / "that's a <Subtype>" (a Food-creature
# anthem — Brenard, Shelob). The lane (food/treasure/clue/blood_matters) is a
# cares-about payoff (the "_matters = cares-about" rule), so a deck running these
# wants the subtype. Anchored on the explicit own-control / state phrasing.
_TOKEN_SUBTYPE_OWN_REF = re.compile(
    r"\b(blood|clue|food|treasure)s? you control\b"
    r"|\b(?:was|were) (?:a |an )?(blood|clue|food|treasure)s?\b"
    r"|(?:\bis|\bare|that's|that are|it's|except it's) (?:a |an )?"
    r"(blood|clue|food|treasure)\b",
    re.IGNORECASE,
)


def _narrow_token_subtype_makers(ability: Ability) -> Ability:
    """Append token-subtype markers for named subtypes phase left only in an effect raw
    — a "<Subtype> token" MAKER (die-roll / vote / choice / granted-ability branch) or a
    "Sacrifice a <Subtype>" SAC PAYOFF (an activated cost). The subtype rides the
    marker's subject Filter so the make_token / sacrifice signal rule fires clue/food/
    treasure/blood_matters. Append-only; anchored on the explicit token/sac phrase."""
    have_make = {
        st
        for e in ability.effects
        if e.category == "make_token" and e.subject is not None
        for st in e.subject.subtypes
    }
    have_sac = {
        st
        for e in ability.effects
        if e.category == "sacrifice" and e.subject is not None
        for st in e.subject.subtypes
    }
    markers: list[Effect] = []
    made: set[str] = set()
    sacd: set[str] = set()
    for e in ability.effects:
        raw = e.raw or ""
        # A make_token marker only when the raw carries a creation verb (so a
        # "discard a Blood token" sac/discard outlet doesn't false-fire as a maker).
        for m in (
            _TOKEN_SUBTYPE_REF.finditer(raw) if _TOKEN_CREATE_VERB.search(raw) else ()
        ):
            sub = m.group(1).capitalize()
            if sub in have_make or sub in made:
                continue
            made.add(sub)
            markers.append(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=(sub,), predicates=("Token",)),
                    raw=raw,
                )
            )
        for m in _TOKEN_SUBTYPE_SAC.finditer(raw):
            sub = m.group(1).capitalize()
            if sub in have_sac or sub in sacd:
                continue
            sacd.add(sub)
            markers.append(
                Effect(
                    category="sacrifice",
                    scope="you",
                    subject=Filter(subtypes=(sub,), predicates=("Token",)),
                    raw=raw,
                )
            )
    if not markers:
        return ability
    return replace(ability, effects=ability.effects + tuple(markers))


def _project_face(record: dict) -> Face:
    abilities: list[Ability] = []
    for ab in record.get("abilities") or []:
        abilities.append(_project_spell_or_activated(ab))
    for tr in record.get("triggers") or []:
        abilities.append(_project_trigger(tr))
    for st in record.get("static_abilities") or []:
        a = _project_top_static(st)
        if a is not None:
            abilities.append(a)
    for rep in record.get("replacements") or []:
        a = _project_replacement(rep)
        if a is not None:
            abilities.append(a)
    if not abilities and not _keywords(record.get("keywords")):
        abilities = _synthesize_from_oracle(record)
    else:
        sentences = _self_oracle_sentences(record)
        name = record.get("name") or ""
        abilities = [_unfold_name_verb(a, name) for a in abilities]
        abilities = [_fill_bare_trigger(a, sentences) for a in abilities]
        abilities = _fill_sole_empty(abilities, sentences)
    # Restriction-narrow (ADR-0027): append precise markers for named mechanics
    # phase left only in a generic carrier's raw.
    abilities = [_narrow_mechanic_refs(a) for a in abilities]
    # Trigger-other raw-marker (ADR-0027): append precise markers for named-mechanic
    # triggers phase flattened to event='other', surviving only in the effect raw.
    abilities = [_narrow_trigger_other_refs(a) for a in abilities]
    # Conferred-keyword re-parse (ADR-0027): append precise markers for keywords/
    # abilities GRANTED to a class of objects, surviving only in a grant carrier raw.
    abilities = [_narrow_conferred_keyword_refs(a) for a in abilities]
    # Keyword-conditioned payoff refs (ADR-0027): append payoff markers for
    # "if it has <madness/mutate>" / "to foretell" clauses phase left in a non-grant
    # carrier raw (Anje's untap, Pollywog's draw, Karfell's ramp).
    abilities = [_narrow_payoff_condition_refs(a) for a in abilities]
    # +1/+1-counter ref recovery (ADR-0027 counters_matter pass 2): append a
    # place_counter(p1p1) for a +1/+1 placement phase nested in a branch/cost/
    # distribute parent, or a counters_have_ref for a "has/with a +1/+1 counter"
    # payoff reference, when phase kept no structured place_counter on the ability.
    abilities = [_narrow_counter_refs(a) for a in abilities]
    # Per-effect graveyard zone recovery (ADR-0027): append the missing graveyard
    # zone tag to a bounce/cheat_play/deposit whose raw names a GY movement phase
    # dropped (World Breaker's SelfRef return, Dakkon's hand-or-graveyard cheat,
    # Atris/Marchesa's "the other into your graveyard" self-mill).
    abilities = [_recover_graveyard_zones(a) for a in abilities]
    # Library-source recovery (ADR-0027 impulse_top_play / play_from_top): append
    # from:library to a cast_from_zone effect that plays from the top of a library but
    # lost the origin zone (Light Up the Stage, Ragavan, Future Sight, Bolas's Citadel).
    abilities = [_recover_library_zones(a) for a in abilities]
    # Edict-scope recovery (ADR-0027 edict_matters): promote a scope=='any' sacrifice
    # to each/opp from its raw when phase dropped the sacrificer scoping to a null
    # controller (Plaguecrafter, Fleshbag Marauder, Barter in Blood).
    abilities = [_recover_edict_scope(a) for a in abilities]
    # Removal target-subject recovery (ADR-0027 removal_matters shape 3): a damage /
    # destroy effect whose creature/permanent TARGET phase dropped to subject=None,
    # but the effect raw still names it ("deals N damage to target creature", "destroy
    # target Wall"). Rebuild a Creature/Permanent Filter so removal_matters fires —
    # the predicate-narrowed (Smite "blocked creature") and power-scaled (Crush
    # Underfoot "damage equal to its power to target creature") removal phase strips.
    abilities = [_recover_removal_target_subject(a) for a in abilities]
    # Count-operand recovery (ADR-0027 count-operand cluster): a draw / pump whose
    # "for each X" scaling operand phase dropped to op='fixed' factor=1 — restore the
    # op='count' (with the counted permanent class as subject when named) so
    # scaling_pump / draw_for_each fire (Strata Scythe, Pride of the Clouds,
    # Skullmulcher, Voice of Many).
    abilities = [_recover_count_operand(a) for a in abilities]
    # Token-subtype maker recovery (ADR-0027): append make_token markers for named
    # token subtypes phase left only in a choose-list / granted-ability carrier raw.
    abilities = [_narrow_token_subtype_makers(a) for a in abilities]
    # Own-board count operand (ADR-0027 go-wide): recover the count-over-your-board
    # operand phase keeps in its raw parse but the structured projection drops (a
    # characteristic-defining */* P/T, a ModifyCost reduction, a damage X, a gate
    # condition). Appended as one static ability of `board_count` markers.
    board_markers = _board_count_markers(record)
    if board_markers:
        abilities.append(Ability(kind="static", effects=tuple(board_markers)))
    # Affinity / Improvise keyword count operands (ADR-0027 go-wide): the affinity
    # subject's type the projection drops to a bare keyword (CR 702.41a / 702.126a —
    # the cost scales with that type's own-board population). artifacts/enchantments
    # only; other affinities (snow lands, gates, a tribe) emit nothing.
    affinity_markers = _affinity_improvise_markers(record)
    if affinity_markers:
        abilities.append(Ability(kind="static", effects=tuple(affinity_markers)))
    # Composite go-wide anthem/type-grant over the own-board artifact-AND-enchantment
    # set phase Unimplemented-parsed (Bello) — fires both artifacts/enchantments_matter.
    composite_grants = _composite_board_grant_markers(record)
    if composite_grants:
        abilities.append(Ability(kind="static", effects=tuple(composite_grants)))
    # "for each creature you control" count operand phase folded/Unrecognized — recover
    # it as a board_count marker only when no structured creature board-count already
    # exists (the board_markers above are already in `abilities`, so this scan covers
    # them; the structured path is preferred, this is the raw fallback).
    has_creature_count = any(
        e.category == "board_count"
        and e.amount is not None
        and e.amount.subject is not None
        and "Creature" in e.amount.subject.card_types
        for a in abilities
        for e in a.effects
    )
    if not has_creature_count:
        fe_marker = _for_each_creature_marker(record)
        if fe_marker is not None:
            abilities.append(Ability(kind="static", effects=(fe_marker,)))
    # Mass keyword/evasion grant (ADR-0027 go-wide): recover a "creatures you control
    # gain/have <kw>" / "...can't be blocked" mass grant phase swallowed into a chosen
    # ability (Linvala), a modal mode (Mishra), or a subjectless restriction (Keeper).
    grant_marker = _mass_creature_grant_marker(record)
    if grant_marker is not None:
        abilities.append(Ability(kind="static", effects=(grant_marker,)))
    # Mass untap (ADR-0027 go-wide): recover "untap all creatures you control" phase
    # left unstructured (a static, a dropped ability, an extra-combat sub-effect).
    if not any(
        e.category == "untap" and e.counter_kind == "all"
        for a in abilities
        for e in a.effects
    ):
        untap_marker = _mass_untap_marker(record)
        if untap_marker is not None:
            abilities.append(Ability(kind="static", effects=(untap_marker,)))
    # Dropped-static face markers (ADR-0027): named-mechanic statics/replacements
    # phase dropped from the parse entirely (boast amplifier, granted trigger-
    # doubling, graveyard-wide scavenge grant, scry replacement, extra end step),
    # surviving only on the face oracle text.
    dropped_markers = _dropped_static_markers(record, abilities)
    if dropped_markers:
        abilities.append(Ability(kind="static", effects=tuple(dropped_markers)))
    # Face-level +1/+1 fallback (ADR-0027 counters_matter pass 2): a +1/+1 placement
    # or "has/with a +1/+1 counter" reference phase dropped ENTIRELY (a trimmed grant
    # clause, a devour/enters-with-copy/cast-from-GY placement, a dropped damage-
    # prevention replacement), surviving only on the face oracle text. Gated on no
    # structured counters effect already present so it never re-tags a clean parse.
    counter_marker = _counter_face_marker(record, abilities)
    if counter_marker is not None:
        abilities.append(Ability(kind="static", effects=(counter_marker,)))
    # Graveyard count-operand (ADR-0027): a value scaling with cards-in-your-GY phase
    # kept in a static-mod / cost_reduction / threshold raw but the projection dropped
    # (Enigma Drake's P/T, Pteramander's cost reduction, Deep-Sea Terror's threshold).
    gy_count_markers = _graveyard_count_markers(record, abilities)
    if gy_count_markers:
        abilities.append(Ability(kind="static", effects=tuple(gy_count_markers)))
    # Graveyard-cast GRANT (ADR-0027): an emblem / quoted-static that lets you cast
    # spells from your graveyard, surviving only in the carrier raw (Jaya's emblem).
    gy_cast_markers = _graveyard_cast_grant_markers(record, abilities)
    if gy_cast_markers:
        abilities.append(Ability(kind="static", effects=tuple(gy_cast_markers)))
    # Additional-cost sacrifice (ADR-0027 sacrifice_matters): an "As an additional
    # cost to cast this spell, sacrifice a <permanent>" outlet. phase keeps it in the
    # record's `additional_cost` field but drops it off the projected spell ability
    # (Altar's Reap → only draw; Fling → only damage). Surface a sacrifice marker so
    # the you-sac lane fires; the land-sac form (Crop Rotation, Harrow) is a separate
    # land_sacrifice lane and is excluded.
    sac_cost_markers = _sacrifice_cost_markers(record, abilities)
    if sac_cost_markers:
        abilities.append(Ability(kind="static", effects=tuple(sac_cost_markers)))
    # Granted/dropped sac outlet (ADR-0027 sacrifice_matters shapes 4-5): a quoted
    # "Sacrifice a creature: …" inside a grant (Fallen Ideal), a "has casualty N"
    # grant (Anhelo), a free-spell pitch (Flare of Denial), or a flashback/escape sac
    # cost (Dread Return) phase keeps only in an opaque raw or drops to a body effect.
    sac_grant_markers = _sacrifice_grant_markers(record, abilities)
    if sac_grant_markers:
        abilities.append(Ability(kind="static", effects=tuple(sac_grant_markers)))
    # Typed sacrifice ACTIVATION-COST markers (ADR-0027 artifacts/enchantments
    # cost-payer): "Sacrifice an artifact: …" (Atog, Krark-Clan Ironworks) / "Sacrifice
    # an enchantment: …". phase keeps the activated ability but collapses the cost to a
    # bare "sacrifice" token, dropping the sacrificed TYPE — so the typeless cost-parts
    # arm fires sacrifice_matters but the artifacts/enchantments lane has no tell.
    # Surface a sacrifice marker carrying the sacrificed object's typed Filter so the
    # artifacts/enchantments sac-payoff arm fires (sacrifice_matters already fires off
    # the cost token, so this adds no new sac firing). Artifact/Enchantment only.
    typed_cost_markers = _typed_sacrifice_cost_markers(record)
    if typed_cost_markers:
        abilities.append(Ability(kind="static", effects=tuple(typed_cost_markers)))
    # Becomes-an-artifact / enchantment TYPE-GRANT markers (ADR-0027): "target
    # noncreature artifact becomes an artifact creature" (Sydri, Karn's Touch — animate
    # your artifacts) and "<permanent> becomes an artifact in addition to its other
    # types" (Argent Mutation, Titania's Song — grant the artifact type for affinity /
    # combo). phase parses these as a base_pt_set / animate / state with subject=None,
    # losing the granted TYPE (it survives only in the effect raw). Surface a
    # becomes_type marker carrying the granted card-type so the artifacts/enchantments
    # lane fires.
    becomes_markers = _becomes_type_markers(abilities)
    if becomes_markers:
        abilities.append(Ability(kind="static", effects=tuple(becomes_markers)))
    # Life-loss markers (ADR-0027 lifeloss_matters): a self pay-life additional cost /
    # free-spell pitch (Bitter Triumph, Contagion, K'rrik) → lose_life scope you; a
    # modal-bullet opponents drain phase swallowed into a `choose` (Inquisitor Exarch,
    # Junji, Skemfar Shadowsage) → lose_life scope opp.
    lifeloss_markers = _lifeloss_markers(record, abilities)
    if lifeloss_markers:
        abilities.append(Ability(kind="static", effects=tuple(lifeloss_markers)))
    return Face(
        name=record.get("name") or "",
        type_line=_type_line(record.get("card_type")),
        keywords=_keywords(record.get("keywords")),
        abilities=tuple(abilities),
    )


# ── ability projection ────────────────────────────────────────────────────────


# Cost-type discriminants we surface on Ability.cost (the activation cost shape:
# a sacrifice outlet, a tap ability, a discard/life/counter cost, ...).
_COST_TYPES = frozenset(
    {
        "sacrifice",
        "tap",
        "untap",
        "discard",
        "paylife",
        "exile",
        "removecounter",
        "mana",
        "return",
        "reveal",
        "mill",
    }
)


def _cost_string(cost: object) -> str | None:
    """Normalized, comma-joined activation cost types (e.g. "sacrifice", "tap")."""
    seen: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            t = _norm(node.get("type"))
            if t == "sacrifice":
                # A sac OUTLET sacrifices fodder; "sacrifice this" (SelfRef) is a
                # self-sac (Fling-style), not a sac-matters outlet.
                tgt = node.get("target")
                self_sac = isinstance(tgt, dict) and _norm(tgt.get("type")) == "selfref"
                seen.add("sacself" if self_sac else "sacrifice")
            elif t == "discard":
                # A discard OUTLET pitches fodder from hand ("Discard a card: ...")
                # — madness/reanimator fuel. "Discard this card" (Cycling, alt-costs)
                # is a SELF-discard (phase's ``self_ref``), not a discard-matters
                # outlet; splitting it out is what unblocks the lane (the +471 flood).
                self_discard = bool(node.get("self_ref"))
                seen.add("discardself" if self_discard else "discard")
            elif t == "exile":
                # An exile cost that PAYS FROM A GRAVEYARD ("Exile this card from your
                # graveyard" — Renew/escape-style, Boneyard Mycodrax; "Exile the top
                # card of your graveyard" — Alms) is a graveyard payoff: it spends GY
                # cards as fuel (CR 702.55a escape / Renew). Distinct cost marker so
                # graveyard_matters fires; a battlefield/exile-from-hand exile cost
                # stays the generic ``exile`` part (no GY synergy).
                if _norm(node.get("zone")) == "graveyard":
                    seen.add("exilegrave")
                else:
                    seen.add("exile")
            elif t == "effectcost":
                # An EffectCost wrapping a ChangeZone whose origin is the graveyard
                # ("Exile the top card of your graveyard: …" — Alms) — same GY-fuel
                # cost in a different phase shape. Surface exilegrave when the wrapped
                # effect's origin is a graveyard.
                inner = node.get("effect")
                if isinstance(inner, dict) and _norm(inner.get("origin")) == (
                    "graveyard"
                ):
                    seen.add("exilegrave")
            elif t in _COST_TYPES:
                seen.add(t)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(cost)
    return ",".join(sorted(seen)) or None


# Copied-type words, in priority order (Permanent last so a specific type wins).
_COPY_TYPE_WORDS: tuple[tuple[str, str], ...] = (
    ("creature", "Creature"),
    ("artifact", "Artifact"),
    ("enchantment", "Enchantment"),
    ("planeswalker", "Planeswalker"),
    ("land", "Land"),
    ("permanent", "Permanent"),
)


def _copied_type_from_text(raw: str) -> Filter | None:
    """The copied permanent type from a clone clause — the word right after "copy of"
    ("becomes a copy of target CREATURE" → Creature; "of any creature or planeswalker"
    → both). None when "copy of" is followed by a typeless referent ("copy of that
    card") — those fall back to the ability's sibling/trigger target."""
    low = raw.lower()
    i = low.find("copy of")
    if i < 0:
        return None
    seg = low[i : i + 60]
    types = tuple(title for word, title in _COPY_TYPE_WORDS if word in seg)
    return Filter(card_types=types) if types else None


def _recover_clone_subjects(ability: Ability) -> Ability:
    """A BecomeCopy with ``target: ParentTarget`` ("target creature becomes a copy of
    IT") loses its copied type. Recover it from the clone clause's own "copy of <type>"
    text, falling back to a sibling effect's / the trigger's target type (the parent
    the copy refers to). Leaves it None only when neither is present."""
    if not any(e.category == "clone" and e.subject is None for e in ability.effects):
        return ability
    borrowed: Filter | None = next(
        (
            e.subject
            for e in ability.effects
            if e.category != "clone"
            and isinstance(e.subject, Filter)
            and e.subject.card_types
        ),
        None,
    )
    if (
        borrowed is None
        and ability.trigger is not None
        and isinstance(ability.trigger.subject, Filter)
    ):
        borrowed = ability.trigger.subject
    effects = tuple(
        replace(e, subject=_copied_type_from_text(e.raw) or borrowed)
        if e.category == "clone" and e.subject is None
        else e
        for e in ability.effects
    )
    return replace(ability, effects=effects)


def _activation_condition(ab: dict) -> object:
    """Lift a RequiresCondition out of ``activation_restrictions`` (Threshold gates —
    Infected Vermin's "Activate only if there are seven or more cards in your
    graveyard"). phase files these in a separate ``activation_restrictions`` array
    (not the ``condition`` field), so the condition projection misses them entirely.
    Returns the first restriction's inner ``condition`` dict, or the ability's own
    ``condition`` when no RequiresCondition is present (CR 602.5)."""
    for restr in ab.get("activation_restrictions") or []:
        if not isinstance(restr, dict):
            continue
        if _norm(restr.get("type")) == "requirescondition":
            data = restr.get("data")
            if isinstance(data, dict) and isinstance(data.get("condition"), dict):
                return data["condition"]
    return ab.get("condition")


def _project_spell_or_activated(ab: dict) -> Ability:
    kind = "activated" if _norm(ab.get("kind")) == "activated" else "spell"
    effects = _collect_effects(ab, ab.get("description") or "")
    return _recover_clone_subjects(
        Ability(
            kind=kind,
            effects=tuple(effects),
            cost=_cost_string(ab.get("cost")),
            condition=_project_condition(_activation_condition(ab)),
        )
    )


def _project_trigger(tr: dict) -> Ability:
    trigger = Trigger(
        event=_trigger_event(tr),
        subject=_filter(tr.get("valid_card")),
        scope=_trigger_scope(tr),
        zones=_zone_tags(tr),
    )
    effects = _collect_effects(tr.get("execute"), tr.get("description") or "")
    return _recover_clone_subjects(
        Ability(
            kind="triggered",
            trigger=trigger,
            effects=tuple(effects),
            condition=_project_condition(tr.get("condition")),
        )
    )


def _project_top_static(st: dict) -> Ability | None:
    effects = _project_static_mods(st, st.get("description") or "")
    if not effects:
        return None
    return Ability(
        kind="static",
        effects=tuple(effects),
        condition=_project_condition(st.get("condition")),
    )


# Quantity-modification types that INCREASE the amount → the doubler archetype,
# whatever the exact multiplier: Double (2x), Multiply (triple — only Ojer Taq for
# tokens / Nyxbloom for mana exist today), Plus (the "+N"/"that many plus" adders,
# e.g. Hardened Scales, Conclave Mentor). Half / Prevent / Minus are the opposite
# (decreases) and excluded.
_INCREASE_MODS = ("double", "multiply", "plus")

# Damage-modification types that INCREASE dealt damage → the damage-doubling
# archetype (CR 615 replacement, combat AND noncombat). phase emits a distinct
# `Triple` for damage (City on Fire, Fiery Emancipation) where token/counter
# quantity uses `Multiply`, so the damage set adds it explicitly. Plus is the
# "deals that much damage plus N" adder (Gratuitous Violence's siblings). Minus /
# LifeFloor / Prevent / SetToSourcePower are decreases / floors / a source-power
# rewrite — NOT amplifiers — and excluded.
_DAMAGE_INCREASE_MODS = ("double", "triple", "multiply", "plus")


def _project_replacement(rep: dict) -> Ability | None:
    """A replacement effect (v0.1.60's top-level ``replacements``) → a static
    Ability. Doubling is split by the replaced EVENT — a token doubler and a
    counter doubler are different archetypes (one wants token makers, the other
    counter sources), so they are distinct categories, never one "doubling"."""
    event = _norm(rep.get("event"))
    raw = rep.get("description") or ""
    qmod = _norm((rep.get("quantity_modification") or {}).get("type"))
    dmod = _norm((rep.get("damage_modification") or {}).get("type"))
    if event == "createtoken" and qmod in _INCREASE_MODS:
        scope = "you" if _norm(rep.get("token_owner_scope")) == "you" else "any"
        return _static_effect("token_doubling", scope, raw)
    if event == "addcounter" and qmod in _INCREASE_MODS:
        cm = rep.get("counter_match") or {}
        ck = _norm(cm.get("data")) if isinstance(cm.get("data"), str) else ""
        return _static_effect("counter_doubling", "you", raw, counter_kind=ck)
    if event == "damagedone" and dmod in _DAMAGE_INCREASE_MODS:
        return _static_effect("damage_doubling", "you", raw)
    # Enters-with counter (ADR-0027): an enters-with replacement whose `execute` is
    # a PutCounter (counter_type carries the kind: P1P1 / M1M1 / Oil / Shield / Lore
    # / …). Two events reach the battlefield with this shape:
    #   • `Moved`→Battlefield — the SELF form "~ enters with N +1/+1 counters on it"
    #     (Faithful Watchdog, Mistcutter Hydra, Cryptborn Horror, Diregraf Colossus —
    #     469 p1p1 cards). CR 614.12.
    #   • `ChangeZone`→Battlefield — the OTHER/static form "each other Angel/creature/
    #     Vehicle you control enters with an additional +1/+1 counter on it" (Giada,
    #     Coin of Mastery, Oona's Blackguard, Bloodspore Thrinax, Bioengineered
    #     Future, Communal Brewing), a continuous static counter grant onto YOUR
    #     board (the `valid_card` set is controller You). CR 614.13.
    # phase treats enters-with as a characteristic-defining property, so the
    # structured projection emits NOTHING for either. Project the execute through the
    # normal effect machinery so the place_counter lands with its real counter_kind
    # (→ the matching counters / minus_counters / oil / shield / saga lane), scope
    # forced to you — the grant is over a permanent its controller drives. A garbled
    # counter_type is normalized to p1p1 by _norm_counter_kind. CR 122.1.
    if (
        event in ("moved", "changezone")
        and _norm(rep.get("destination_zone")) == "battlefield"
    ):
        execute = rep.get("execute")
        eff = execute.get("effect") if isinstance(execute, dict) else None
        if isinstance(eff, dict) and _norm(eff.get("type")) in (
            "putcounter",
            "putcounterall",
            "addpendingetbcounters",
        ):
            effs = _collect_effects(execute, raw or rep.get("description") or "")
            place = [
                replace(e, scope="you") for e in effs if e.category == "place_counter"
            ]
            if place:
                return Ability(kind="static", effects=tuple(place))
    return None


def _enter_with_counter_effects(eff: dict, raw: str) -> list[Effect]:
    """Recover the ``enter_with_counters`` rider phase nests INSIDE an effect dict
    (ADR-0027). Two shapes carry it on the effect itself (not a top-level
    replacement):

      • a ``Token`` effect — "create a Fractal token, then put X +1/+1 counters on
        it" parses the placement as ``token.enter_with_counters`` (Body of Research,
        the Fractal cycle, Slime Against Humanity, Clown Car). phase keeps the made
        token's entering counters as a property of the token spec, so the structured
        projection (which emits ``make_token``) drops the placement entirely.
      • a ``ChangeZone`` / reanimate effect — "return ~ to the battlefield WITH N
        +1/+1 counters on it" parses as ``changezone.enter_with_counters`` (Evil
        Reawakened, the Transmogrant cycle, Phoenix Chick, the exile-and-return
        blink riders Long Road Home / Planar Incision / Feign Death). The returned
        object's entering counters ride the move, again dropped by the structured
        projection.

    Either way the entering ``+1/+1`` counters are real counter placements (CR
    614.13c — the object enters with the counters), so emit a ``place_counter``
    per kind (scope you — the controller chooses to make/return it). The garbled
    kind (``"a number of +1/+1"``) is normalized through ``_norm_counter_kind`` so
    it lands as ``p1p1``, not junk. Non-+1/+1 entering counters (a named ``study`` /
    ``growth`` / Saga ``lore``) keep their own kind → their own lane."""
    ewc = eff.get("enter_with_counters")
    if not isinstance(ewc, list):
        return []
    out: list[Effect] = []
    for pair in ewc:
        if not (isinstance(pair, list) and pair):
            continue
        kind = _norm_counter_kind(pair[0])
        if kind:
            out.append(
                Effect(
                    category="place_counter",
                    scope="you",
                    raw=raw,
                    counter_kind=kind,
                )
            )
    return out


def _static_effect(
    category: str, scope: str, raw: str, *, counter_kind: str = ""
) -> Ability:
    return Ability(
        kind="static",
        effects=(
            Effect(category=category, scope=scope, raw=raw, counter_kind=counter_kind),
        ),
    )


def _collect_effects(node: dict | None, default_raw: str) -> list[Effect]:
    """Walk an ability node's effect + sub_ability chain into a flat effect list."""
    if not isinstance(node, dict):
        return []
    raw = node.get("description") or default_raw
    out: list[Effect] = []
    # Generalized modal-choose-split (ADR-0027): phase parses a modal ability
    # ("choose one/three — • …") into a placeholder GenericEffect plus a sibling
    # `mode_abilities` array — each entry a FULLY STRUCTURED ability dict (its own
    # typed `effect`/`sub_ability`/`cost`). The structured projection never descends
    # into it, so the per-mode bodies (• Destroy target artifact, • Mishra deals 3
    # damage, • you lose 2 life, • mill four) are LOST — only a downstream raw-text
    # recovery (_fill_sole_empty) re-derives their CATEGORY, dropping the SUBJECT
    # (the destroy/damage target). Recovering the modes structurally restores those
    # subjects, so subject-gated lanes (removal_matters' permanent target, the
    # counters kind, the graveyard self-mill zone) fire from real structure. General
    # by construction: it reuses _collect_effects per mode and benefits every lane,
    # not just removal (CR 700.2 — a modal spell/ability). When modes are recovered
    # we prepend a `choose` marker and SUPPRESS the empty GenericEffect placeholder
    # (it would only add an `other`, marking the card partial); a mode whose own body
    # also fails recursively still leaves its own `other`, an honest gap.
    modes = node.get("mode_abilities")
    mode_descs = (node.get("modal") or {}).get("mode_descriptions")
    mode_effects = _modal_split_effects(modes, mode_descs, raw) if modes else []
    if mode_effects:
        out.append(Effect(category="choose", scope="any", raw=raw))
        out.extend(mode_effects)
    else:
        eff = node.get("effect")
        if isinstance(eff, dict):
            out.extend(_project_effect(eff, raw))
    sub = node.get("sub_ability")
    if isinstance(sub, dict):
        out.extend(_collect_effects(sub, default_raw))
    return out


def _modal_split_effects(
    modes: object, descs: object, carrier_raw: str
) -> list[Effect]:
    """Project a `mode_abilities` array (the structured per-mode bodies of a modal
    `choose`) into a flat effect list (generalized modal-choose-split, ADR-0027).
    Each mode is itself an ability node; we recurse `_collect_effects` to recover its
    typed effects with their real subjects. The positionally-aligned
    `modal.mode_descriptions` text becomes each mode's effect raw, prefixed with "• "
    (the oracle bullet form) so a downstream raw-marker / discriminator pass keys on
    the bullet shape consistently; a mode's own `description` wins when present. A
    mode phase couldn't structure (a GenericEffect / Unimplemented body) falls back to
    the same supplement text-recovery `_fill_sole_empty` uses — preserving the prior
    category floor so confidence is unchanged, with the structured-subject modes a
    strict gain. Bounded by the mode list; no mode re-nests a modal in practice, so
    the recursion is shallow."""
    if not isinstance(modes, list):
        return []
    desc_list = descs if isinstance(descs, list) else []
    out: list[Effect] = []
    for i, mode in enumerate(modes):
        if not isinstance(mode, dict):
            continue
        own = mode.get("description")
        bullet = desc_list[i] if i < len(desc_list) else None
        if isinstance(own, str) and own:
            mode_raw = own
        elif isinstance(bullet, str) and bullet:
            mode_raw = f"• {bullet}"
        else:
            mode_raw = carrier_raw
        mode_effs = _collect_effects(mode, mode_raw)
        structural = [e for e in mode_effs if e.category != "other"]
        if structural:
            out.extend(structural)
            continue
        # The mode's body is unparsed (a GenericEffect / Unimplemented phase couldn't
        # structure — Outlaws' Merriment's token bullets, a "create a 3/1 …" body).
        # Recover its CATEGORY from the bullet raw via the same supplement grammar
        # _fill_sole_empty uses, so the lane still fires and the card stays `full`
        # (the structured-subject modes above are the gain; this preserves the prior
        # text-recovery floor for modes phase can't type). A truly empty bullet (no
        # raw) contributes nothing and is dropped.
        if (mode_raw or "").strip():
            rec = recover_effect_from_text(mode_raw)
            if rec.category != "other":
                out.append(rec)
    return out


# GivePlayerCounter.counter_kind → the IR category. Energy reuses the gainenergy
# category; poison/experience route to their own (the matching *_matters lanes
# already exist). Rad/ticket and unknown kinds stay distinct from +1/+1 counters.
_PLAYER_COUNTER_CATEGORY: dict[str, str] = {
    "poison": "poison",
    "energy": "energy",
    "experience": "experience_counter",
    "rad": "rad_counter",
    "ticket": "ticket_counter",
}


def _damage_doubling_from_replacement(eff: dict, raw: str) -> Effect | None:
    """A CONDITIONAL / temporal damage-doubler phase nests inside a replacement-
    creating effect (ADR-0027 damage cluster). Two shapes carry the amplifier as a
    NESTED modification the generic redirect/damage_replacement category drops:

      • ``AddTargetReplacement`` — an activated/spell effect that installs a
        DamageDone replacement for the turn ("If a source you control would deal
        damage … this turn, it deals double/triple that damage instead" — Goblin
        Goliath, Isengard Unleashed, Insult, Quest for Pure Flame). The amplifier
        is ``replacement.damage_modification`` on a DamageDone event.
      • ``CreateDamageReplacement`` — the coin-flip / choose-a-source one-shot
        ("the next time that source would deal damage, it deals double that damage"
        — Desperate Gambit, Impulsive Maneuvers). The amplifier is ``modification``.

    Both are real damage_doubling payoffs (CR 615): they want burn / big hits to
    amplify, the same archetype as Furnace of Rath. Returns a damage_doubling Effect
    when the nested modification INCREASES damage (double/triple/multiply/plus),
    else None (a Prevent / Minus / redirect-only replacement is not a doubler)."""
    etype = _norm(eff.get("type"))
    if etype == "addtargetreplacement":
        rep = eff.get("replacement")
        if isinstance(rep, dict) and _norm(rep.get("event")) == "damagedone":
            dmod = _norm((rep.get("damage_modification") or {}).get("type"))
            if dmod in _DAMAGE_INCREASE_MODS:
                return Effect(category="damage_doubling", scope="you", raw=raw)
    elif etype == "createdamagereplacement":
        md = _norm((eff.get("modification") or {}).get("type"))
        if md in _DAMAGE_INCREASE_MODS:
            return Effect(category="damage_doubling", scope="you", raw=raw)
    return None


def _project_effect(eff: dict, raw: str) -> list[Effect]:
    etype = _norm(eff.get("type"))
    dd = _damage_doubling_from_replacement(eff, raw)
    if dd is not None:
        return [dd]
    if etype in _RECURSE:
        out: list[Effect] = []
        for st in eff.get("static_abilities") or []:
            out.extend(_project_static_mods(st, raw))
        sub = eff.get("sub_ability")
        if isinstance(sub, dict):
            out.extend(_collect_effects(sub, raw))
        if not out:
            out.append(Effect(category="other", scope=_effect_scope(eff), raw=raw))
        return out
    if etype in ("changezone", "changezoneall"):
        return [
            _changezone_effect(eff, raw, mass=etype == "changezoneall"),
            *_enter_with_counter_effects(eff, raw),
        ]
    if etype == "copytokenof":
        return [_copy_token_effect(eff, raw)]
    if etype == "additionalphase":
        # Batch 14 — an extra phase, split by which phase it grants.
        ph = _norm(eff.get("phase"))
        cat = _EXTRA_PHASE.get(ph, "other")
        return [Effect(category=cat, scope="you", raw=raw)]
    if etype in ("putatlibraryposition", "putontoporbottom"):
        return [_library_position_effect(eff, raw)]
    if etype == "settapstate":
        # The biggest single parse gap (2427): tap/untap a permanent. The `state`
        # field is the direction; reuse the existing tap / untap categories so
        # untap_engine / tap_down derive from it. The `scope` (All vs Single) rides
        # in counter_kind so a MASS untap ("untap ALL creatures you control" —
        # Aggravated Assault, Reveille Squad) is distinguishable from a single-target
        # untap ("untap target creature") downstream: a go-wide creatures_matter lane
        # cares about the mass form, not a one-off untapper.
        state = _norm((eff.get("state") or {}).get("type"))
        cat = "untap" if state == "untap" else "tap"
        scope_all = _norm((eff.get("scope") or {}).get("type")) == "all"
        return [
            Effect(
                category=cat,
                scope=_effect_scope(eff),
                subject=_effect_subject(eff),
                raw=raw,
                counter_kind="all" if scope_all else "",
            )
        ]
    if etype == "giveplayercounter":
        # CR 122.1 — "a counter is not a token, and a token is not a counter"; counter
        # KINDS are likewise non-interchangeable. A player poison/energy/experience
        # counter is NOT a +1/+1 creature counter, so route by `counter_kind` instead
        # of folding into place_counter (the +1/+1 / counters_matter lane). Energy
        # reuses the gainenergy category for consistency.
        kind = _norm(eff.get("counter_kind"))
        cat = _PLAYER_COUNTER_CATEGORY.get(kind, "player_counter")
        return [
            Effect(
                category=cat,
                amount=_amount(eff),
                scope=_effect_scope(eff),
                raw=raw,
                counter_kind=kind,
            )
        ]
    if etype == "createdelayedtrigger":
        # A delayed trigger stores an effect to fire later ("at the beginning of the
        # next end step, ...") — recurse into the stored effect so its mechanics parse.
        inner = _collect_effects(eff.get("effect"), raw)
        return inner or [Effect(category="other", scope=_effect_scope(eff), raw=raw)]
    category = _EFFECT_CATEGORY.get(etype)
    if category is None or etype in _OTHER:
        return [Effect(category="other", scope=_effect_scope(eff), raw=raw)]
    ck = eff.get("counter_type")
    counter_kind = _norm_counter_kind(ck) if isinstance(ck, str) else ""
    if etype in _MASS_EFFECT_TYPES:
        counter_kind = "all"
    scope = _effect_scope(eff)
    # ADR-0027 sacrifice_matters edict split: a Sacrifice effect's "who sacrifices"
    # is the controller of the sacrificed object (the effect's `target`). phase
    # encodes a FORCED OTHER-player sacrifice (an edict) as target.controller =
    # TargetPlayer / ScopedPlayer / DefendingPlayer / Opponent, but _effect_scope
    # never reads a Typed target's `controller`, so every edict landed on scope
    # "any" — indistinguishable from a genuine you-sacrifice. Promote the scope to
    # opp/each from the sacrificing player so signals can keep the edict (opp/each →
    # edict_matters) out of the you-sac sacrifice_matters lane (CR 701.16).
    if category == "sacrifice":
        scope = _sacrifice_player_scope(eff, scope)
    return [
        Effect(
            category=category,
            amount=_amount(eff),
            scope=scope,
            subject=_effect_subject(eff),
            raw=raw,
            counter_kind=counter_kind,
            zones=_zone_tags(eff),
        ),
        *_enter_with_counter_effects(eff, raw),
    ]


# Static restriction modes (stax / taxes) — the mode is the restriction.
_RESTRICTION_MODES = frozenset(
    {
        "cantattack",
        "cantblock",
        "cantattackorblock",
        "cantbecast",
        "cantbeactivated",
        "cantcast",
        "cantuntap",
        "canttap",
        "cantdraw",
        "cantgainlife",
        "cantsearchlibrary",
        "mustattack",
        "mustblock",
        "raisecost",
        "perturncastlimit",
        "perturndrawlimit",
        "addrestriction",
        "blockrestriction",
        "maximumhandsize",
    }
)

# Batch 13 — combat-FORCING modes are pulled OUT of the stax-bound _RESTRICTION_MODES
# into their own categories (a "creatures must attack" is a force-the-table theme, not
# a tax). mustbeblocked* were not captured at all before. cantattack/cantattackorblock
# stay in _RESTRICTION_MODES (pillowfort = stax).
_COMBAT_FORCE_MODES: dict[str, str] = {
    "mustattack": "force_attack",
    "cantblock": "cant_block",
    "mustbeblocked": "lure",
    "mustbeblockedbyall": "lure",
}


def _restriction_scope(st: dict, affected: Filter | None) -> str:
    """Whom a restriction/combat-force static hobbles → the Effect scope (opp / each /
    any). Reads the affected set's controller and the mode's ``who`` qualifier."""
    who = _mode_who(st.get("mode"))
    if (affected is not None and affected.controller == "opp") or "opponent" in who:
        return "opp"
    if "all" in who:
        return "each"
    return "any"


def _mode_token(mode: object) -> str:
    """The restriction-mode discriminant — a bare string or a one-key dict."""
    if isinstance(mode, str):
        return _norm(mode)
    if isinstance(mode, dict) and len(mode) == 1:
        return _norm(next(iter(mode)))
    return ""


def _mode_who(mode: object) -> str:
    if isinstance(mode, dict):
        for v in mode.values():
            if isinstance(v, dict):
                return _norm(v.get("who"))
    return ""


def _modifycost_raise(mode: object) -> bool:
    """True for a v0.1.60 ``ModifyCost{mode: Raise}`` static — a cost TAX. v0.1.60
    merged the old ``raisecost``/``reducecost`` modes into one ``ModifyCost`` whose
    inner ``mode`` is the direction; only a Raise is a stax-style tax (a Reduce, or
    a self-only Strive-style Raise, is not)."""
    if isinstance(mode, dict) and len(mode) == 1:
        inner = next(iter(mode.values()))
        if isinstance(inner, dict):
            return _norm(inner.get("mode")) == "raise"
    return False


def _modifycost_reduce(mode: object) -> dict | None:
    """The inner payload of a v0.1.60 ``ModifyCost{mode: Reduce}`` static — a cost
    REDUCER (Goblin Electromancer, Ruby Medallion, Urza's Incubator, Helm of
    Awakening). The symmetric direction of :func:`_modifycost_raise`. Returns the
    inner ModifyCost dict (carrying ``spell_filter`` = which spells get cheaper) so
    the cost_reduction lane reads a direction-CORRECT structural form (never the
    cost-INCREASE text the regex also caught), or ``None``."""
    if isinstance(mode, dict) and len(mode) == 1:
        inner = next(iter(mode.values()))
        if isinstance(inner, dict) and _norm(inner.get("mode")) == "reduce":
            return inner
    return None


def _has_devotion_condition(st: dict) -> bool:
    """A static GATED on your devotion (a ``DevotionGE``, possibly wrapped in ``Not``
    for the 'less than N' form) — the Theros gods' "as long as your devotion to X is
    N or more". batch 8 captured devotion only as a scaling AMOUNT (qty); a devotion
    THRESHOLD lives in the condition subtree, so the lane missed the gods entirely."""

    def walk(n: object) -> bool:
        if isinstance(n, dict):
            if _norm(n.get("type")) == "devotionge":
                return True
            return any(walk(v) for v in n.values())
        if isinstance(n, list):
            return any(walk(x) for x in n)
        return False

    return walk(st.get("condition"))


def _granted_ability_effects(st: dict, affected: Filter | None) -> list[Effect]:
    """Recursively project a static's GRANTED QUOTED abilities into structured
    nested Effect(s) (quoted-grant-ability recursion, ADR-0027).

    phase parses an "Enchanted/Equipped creature has '<ability>'" / "Creatures you
    control have '<ability>'" / "<type> you control gain '<ability>'" grant as a
    GrantAbility / GrantTrigger MODIFICATION whose ``definition`` (activated/spell)
    or ``trigger`` is a FULLY STRUCTURED ability node — but the structured
    projection never descended into it, so the granted body (its destroy / damage /
    PutCounter / etc. Effect) was LOST and only the carrier raw survived. Recurse the
    granted node through the same ``_collect_effects`` machinery a real
    spell/activated/triggered ability goes through (mirrors how ``_modal_split_effects``
    recurses ``_collect_effects`` per mode), so the lanes that read those effect
    categories (removal: destroy / damage-to-permanent; counters: place_counter; …)
    fire from real STRUCTURE rather than a brittle raw scan.

    SCOPE / RULES-LAWYER GATE (CR 113.3, 702.x grant rules): the granted ability's
    SUBJECT — who HAS it — is the static's ``affected`` set, and the source it
    controls is controlled by that permanent's controller. A grant onto an
    OPPONENT'S permanents (``affected.controller == 'opp'``) is THEIR ability, not
    yours, so it is EXCLUDED (the recovered removal/counters are not a care of
    yours). Every other affected set — your team (controller You), an Aura/Equipment
    you control (EnchantedBy / EquippedBy → null controller), your commander, an
    owned card — describes a permanent you control, so the granted source is yours.
    Append-only: the carrier static's own effects (a board_grant / grant_keyword)
    are untouched; this only ADDS the recovered inner effects."""
    if affected is not None and affected.controller == "opp":
        return []
    out: list[Effect] = []
    for m in st.get("modifications") or []:
        mt = _norm(m.get("type"))
        if mt == "grantability":
            node = m.get("definition")
            if isinstance(node, dict):
                out.extend(_collect_effects(node, node.get("description") or ""))
        elif mt == "granttrigger":
            tr = m.get("trigger")
            if isinstance(tr, dict):
                out.extend(
                    _collect_effects(tr.get("execute"), tr.get("description") or "")
                )
    # Drop the textless `other` placeholders the recursion can leave for an inner
    # body phase couldn't structure (e.g. a granted "{T}: Add {G}" whose mana arm is
    # not lane-relevant) — they would only mark the carrier partial. Keep only the
    # genuinely structured inner effects (the gain over the prior raw-only floor).
    return [e for e in out if e.category != "other"]


def _project_static_mods(st: dict, raw: str) -> list[Effect]:
    """A continuous static's modifications + restriction mode → effects."""
    affected = _filter(st.get("affected"))
    desc = st.get("description") or raw
    out: list[Effect] = []
    # A devotion-threshold gate (gods) is a devotion payoff regardless of what the
    # static then does — carry the operand so the existing op="devotion" lane fires.
    if _has_devotion_condition(st):
        out.append(
            Effect(
                category="other",
                scope="you",
                raw=desc,
                amount=Quantity(op="devotion"),
            )
        )
    pump_amount: Quantity | None = None
    is_pump = False
    set_power = set_toughness = False
    grants_ability_or_type = False
    for m in st.get("modifications") or []:
        mt = _norm(m.get("type"))
        if mt == "changecontroller":
            # A continuous static that CHANGES the controller of the affected set —
            # the canonical theft Auras (Control Magic, Mind Control, Confiscate,
            # Take Possession) and steal statics. phase models these as a static
            # ChangeController modification (NOT a gaincontrol EFFECT), so the
            # gain_control effect-category never fired. Surface it as a gain_control
            # effect so the theft lane reads it. CR 805/720. The affected set is what's
            # stolen (EnchantedBy creature); scope is you (you take control).
            out.append(
                Effect(
                    category="gain_control",
                    scope="you",
                    subject=affected,
                    raw=desc,
                )
            )
        elif mt in _PUMP_MODS:
            is_pump = True
            if pump_amount is None:
                pump_amount = _quantity(m.get("value"))
        elif mt in ("setpower", "setdynamicpower", "setpowerdynamic"):
            set_power = True
        elif mt in ("settoughness", "setdynamictoughness", "settoughnessdynamic"):
            set_toughness = True
        elif mt in ("grantability", "addsubtype", "addtype"):
            # A continuous static that GRANTS an activated/triggered ability or ADDS a
            # type/subtype to the affected set ("Artifacts you control are Foods and
            # have '{2},{T},Sacrifice: gain 3 life'" — Ragost). Unlike AddKeyword, no
            # bare keyword survives, so it isn't a grant_keyword; surface it as a
            # board_grant when the set is the whole own-board artifact/enchantment set.
            # The GRANTED ability's structured body (its destroy / damage / PutCounter
            # Effect) is recovered separately by _granted_ability_effects below, so the
            # removal / counters lanes fire from the inner structure too.
            grants_ability_or_type = True
        elif mt == "addkeyword":
            # Batch 6 — a static that GRANTS a keyword (Levitation → Flying). The
            # granted keyword rides in counter_kind (a free str field); the lane
            # splits by keyword + whether the affected set is your whole team. Only a
            # BARE STRING keyword emits grant_keyword (unchanged — the keyword-grant
            # lanes split by the keyword name). A PARAMETERIZED keyword (Ward {1},
            # Protection from X — "Artifacts you control have ward {1}", Elder Owyn
            # Lyons) is a dict {"Ward": {...}} with no bare keyword name the keyword
            # lanes key on; it sets grants_ability_or_type so it surfaces as a
            # board_grant ONLY when the affected set is the own-board artifact/
            # enchantment set (scoped below), leaving the creature keyword-grant lanes
            # untouched.
            kw = m.get("keyword")
            if isinstance(kw, str):
                out.append(
                    Effect(
                        category="grant_keyword",
                        scope=_controller_scope(affected),
                        subject=affected,
                        raw=desc,
                        counter_kind=_norm(kw),
                    )
                )
            elif isinstance(kw, dict) and kw:
                grants_ability_or_type = True
    # A static that SETS base power AND toughness on OTHER permanents (Lignify 0/4,
    # Ovinize 0/1, Kenrith's Transformation, mass-animate like Living Plane) — the
    # base-P/T TOOLBOX. Distinct from a +X/+X pump. Excludes a characteristic-defining
    # */* creature (Tarmogoyf defines its OWN P/T) AND a self-animate (a manland like
    # Treetop Village animates ITSELF — a creature-land, not a toolbox): both set the
    # SOURCE's P/T, not another permanent's.
    _affected_raw = st.get("affected")
    _self_pt = (
        isinstance(_affected_raw, dict)
        and _norm(_affected_raw.get("type")) == "selfref"
    )
    if (
        set_power
        and set_toughness
        and not st.get("characteristic_defining")
        and not _self_pt
    ):
        out.append(
            Effect(
                category="base_pt_set",
                scope=_controller_scope(affected),
                subject=affected,
                raw=desc,
            )
        )
    # A board_grant over the whole own-board artifact/enchantment set (Ragost). Gated
    # to a generic own-board Artifact/Enchantment filter (controller you, no subtype)
    # via _is_generic_board_filter so a single-target or tribal grant never reaches the
    # artifacts/enchantments_matter lanes — the granted ability/type ranges over the
    # population (CR 604.3 / continuous static), the go-wide care.
    if grants_ability_or_type and any(
        _is_generic_board_filter(st.get("affected"), ct)
        for ct in ("Artifact", "Enchantment")
    ):
        out.append(
            Effect(
                category="board_grant",
                scope=_controller_scope(affected),
                subject=affected,
                raw=desc,
            )
        )
    if is_pump:
        out.append(
            Effect(
                category="pump",
                amount=pump_amount,
                scope=_controller_scope(affected),
                subject=affected,
                raw=desc,
            )
        )
    # A cost TAX (v0.1.60 ModifyCost{Raise}): scope = whose spells are taxed,
    # carried on ``affected.controller`` (Opponent → stax on them; unscoped "Card"
    # → symmetric; You → a self-drawback that hobbles no one, so emit nothing).
    if _modifycost_raise(st.get("mode")):
        if affected is not None and affected.controller == "opp":
            out.append(
                Effect(category="restriction", scope="opp", subject=affected, raw=desc)
            )
        elif affected is not None and affected.controller == "any":
            out.append(
                Effect(category="restriction", scope="each", subject=affected, raw=desc)
            )
        return out
    # A cost REDUCER (v0.1.60 ModifyCost{Reduce}): Goblin Electromancer / Ruby
    # Medallion / Urza's Incubator / Helm of Awakening make a CLASS OF YOUR (or
    # everyone's) spells cheaper — a cost_reduction build-around payoff. The
    # spell_filter (instant/sorcery, chosen tribe, artifact, by color, or null = all)
    # is what gets cheaper; carry it as subject so the lane reads the build-around.
    # scope="you": the reducer's controller is the payoff's owner, You-affected or
    # symmetric. EXCLUDE affected==SelfRef (Cavern-Hoard Dragon "this spell costs less"
    # — a one-off SELF discount that cheapens no OTHER spell in the deck; same CR
    # 601.2f operation, but not the build-around enabler the lane keys on — rules-
    # adjudicated, CR 601.2f/118.7). (ADR-0027 β — direction-correct vs the regex.)
    _aff = st.get("affected")
    _is_self = isinstance(_aff, dict) and _norm(_aff.get("type")) == "selfref"
    _cost_reduce = _modifycost_reduce(st.get("mode"))
    if _cost_reduce is not None and not _is_self:
        out.append(
            Effect(
                category="cost_reduction",
                scope="you",
                subject=_filter(_cost_reduce.get("spell_filter")),
                raw=desc,
            )
        )
        return out
    # Batch 13 — a combat-FORCING static (must attack / must be blocked / can't
    # block): its own category, not stax. The scope tracks whom it hobbles so the lane
    # can still feed stax (a "creatures opponents control can't block" is BOTH a
    # path-clearing payoff AND a pillowfort tax). A lure creature lures blockers to
    # ITSELF (SelfRef is the enabler) so lure keeps it; force_attack / cant_block need
    # a themeable affected (a real creature SET or a targeted creature) — a self
    # "this can't block" / "this must attack" is a vanilla drawback, not a theme.
    mode_tok = _mode_token(st.get("mode"))
    # Batch 6 (flash_grant, unblocked) — CastWithKeyword{Flash} is "you may cast
    # [creature] spells as though they had flash" (Teferi, Yeva, Alchemist's Refuge):
    # the flash ENABLER the AddKeyword path couldn't express (flash is a cast-time
    # permission, not a battlefield keyword). The granted keyword rides in
    # counter_kind so other CastWithKeyword grants can extend the lane later.
    if mode_tok == "castwithkeyword":
        mode = st.get("mode")
        inner = mode.get("CastWithKeyword") if isinstance(mode, dict) else None
        kw = inner.get("keyword") if isinstance(inner, dict) else None
        out.append(
            Effect(
                category="cast_with_keyword",
                scope="you",
                raw=desc,
                counter_kind=_norm(kw) if isinstance(kw, str) else "",
            )
        )
        return out
    # Batch 17 — DoubleTriggers static (Yarok / Panharmonicon / Ancient Greenwarden):
    # "a triggered ability triggers an additional time". One lane regardless of the
    # cause (ETB-only vs Any) — the want is the same trigger-doubling engine.
    if mode_tok == "doubletriggers":
        out.append(Effect(category="trigger_doubling", scope="you", raw=desc))
        return out
    # Batch 13 (evasion_denial) — IgnoreLandwalkForBlocking ("creatures can be
    # blocked as though they didn't have <landwalk>", Great Wall / Crevasse): denies
    # an evasion ability so you can block through it. scope "opp" (it strips THEIR
    # evasion); the lane reads it as opponents.
    if mode_tok == "ignorelandwalkforblocking":
        out.append(Effect(category="evasion_denial", scope="opp", raw=desc))
        return out
    # CantBeBlockedBy ("Creatures you control [with power N or less] can't be blocked
    # by …", Delney / Champion of Lambholt): a MASS-EVASION grant to your whole own-
    # board creature set (optionally a power band). Modeled as a grant_keyword over
    # the affected set so the go-wide creatures_matter arm reads it (the granted thing
    # is an evasion-class permission — counter_kind "unblockable"). Gated to YOUR
    # creatures — a "creatures opponents control can't be blocked" is not a care of
    # yours, and a single-target unblockable (affected not a your-team Typed set)
    # isn't a mass grant.
    if (
        mode_tok == "cantbeblockedby"
        and affected is not None
        and (affected.controller == "you" and "Creature" in affected.card_types)
    ):
        out.append(
            Effect(
                category="grant_keyword",
                scope="you",
                subject=affected,
                raw=desc,
                counter_kind="unblockable",
            )
        )
        return out
    combat_cat = _COMBAT_FORCE_MODES.get(mode_tok)
    if combat_cat is not None:
        scope = _restriction_scope(st, affected)
        affected_raw = st.get("affected")
        raw_type = (
            _norm(affected_raw.get("type")) if isinstance(affected_raw, dict) else ""
        )
        themeable = raw_type in ("typed", "parenttarget")
        if combat_cat == "lure" or themeable:
            out.append(
                Effect(category=combat_cat, scope=scope, subject=affected, raw=desc)
            )
        return out
    # A restriction static (stax/tax): scope = whom it hobbles.
    if mode_tok in _RESTRICTION_MODES:
        out.append(
            Effect(
                category="restriction",
                scope=_restriction_scope(st, affected),
                subject=affected,
                raw=desc,
            )
        )
    # Quoted-grant-ability recursion (ADR-0027): recover the STRUCTURED inner effects
    # of a GrantAbility / GrantTrigger modification (the carrier static keeps the
    # grant opaque; here we descend into the granted ability node so its destroy /
    # damage / place_counter Effect reaches the lanes that read those categories).
    out.extend(_granted_ability_effects(st, affected))
    return out


# ── operand / filter projection (the load-bearing part) ───────────────────────


def _amount(eff: dict) -> Quantity | None:
    for key in ("count", "amount", "value", "number"):
        if key in eff:
            q = _quantity(eff[key])
            if q is not None:
                return q
    return None


def _library_position_effect(eff: dict, raw: str) -> Effect:
    """A put-into-library effect → ``topdeck_stack``, tagged with WHERE in
    ``counter_kind``. The top-stacking archetype (Brainstorm; graveyard-/hand-to-top
    recursion) reads top/nth/topbottom; a Bottom put ("rest on the bottom", failed-
    tutor cleanup) is not a top-stack. ``PutOnTopOrBottom`` is a player choice
    (top-eligible) → 'topbottom'. The subject (moved cards) carries the controller so
    the lane can keep self-stacking apart from a bounce-to-top removal (controller
    None)."""
    pos = eff.get("position")
    where = _norm(pos.get("type")) if isinstance(pos, dict) else "topbottom"
    return Effect(
        category="topdeck_stack",
        scope=_effect_scope(eff),
        subject=_effect_subject(eff),
        raw=raw,
        counter_kind=where,
        # The moved card can be restricted IN a zone — "put target artifact card from
        # your graveyard on top of your library" (Academy Ruins) carries an
        # InZone:Graveyard target. Surfacing it as in:graveyard lets graveyard_matters
        # read this graveyard→library recursion (ADR-0027).
        zones=_zone_tags(eff),
    )


def _changezone_effect(eff: dict, raw: str, *, mass: bool = False) -> Effect:
    """A ChangeZone effect → category by its origin/destination zones.

    Graveyard → Battlefield is reanimation; → Exile of your own permanent is a
    blink (ETB-value flicker); → Exile of others' is exile removal; the rest stay
    'other'. The ``target`` (a Typed filter of what's moved) is the subject.

    ``mass`` is True for ``ChangeZoneAll`` ("return ALL <type> cards" — Crystal
    Chimes, Open the Vaults) vs the single-target ``ChangeZone`` / ``Bounce`` form
    ("return TARGET <type> card" — Skull of Orm). The non-interchangeable mass tell
    rides in ``counter_kind="all"`` (the same idiom SetTapState uses for a mass
    untap), so a downstream type-payoff recursion lane can fire on the go-wide form
    (CR 115.10) while gating out single-target recursion (CR 115.1, fixed
    magnitude 1 = generic value). It survives the supplement's verb-phrase
    category rewrite, which preserves every field but ``category``."""
    origin = _norm(eff.get("origin"))
    dest = _norm(eff.get("destination"))
    target = _filter(eff.get("target"))
    if origin == "graveyard" and dest == "battlefield":
        category = "reanimate"
    elif origin == "library" and dest == "hand":
        # A card moving library -> hand is the fetch-to-hand payoff of a search
        # (CR 701.23): basic/typecycling and tutors-to-hand. phase emits this as the
        # SearchLibrary's put-step, so `tutor` already fires from the sibling — mapping
        # it keeps the step from leaving an empty 'other' that marks the card partial.
        category = "tutor"
    elif dest == "battlefield" and origin in ("library", "hand"):
        # Batch 9 — put a permanent into play from library/hand WITHOUT casting it
        # (Sneak Attack / Elvish Piper / Through the Breach). The lane gates on a
        # creature subject in signals (a land into play is ramp, not a cheat).
        category = "cheat_play"
    elif dest == "exile" and target is not None and target.controller == "you":
        # exile-and-return of YOUR own permanent = blink (ETB-value flicker).
        category = "blink"
    elif dest == "exile":
        # exile of others' permanents = exile removal.
        category = "exile"
    else:
        category = "other"
    return Effect(
        category=category,
        amount=_amount(eff),
        scope=_effect_scope(eff),
        subject=target,
        raw=raw,
        counter_kind="all" if mass else "",
        zones=_zone_tags(eff),
    )


# Zones (other than the stack) an effect can structurally reference. Battlefield is
# included so signals can gate the battlefield→graveyard death case out of
# graveyard_matters; the stack is omitted (no synergy lane keys off it).
_ZONE_NAMES = frozenset(
    {"graveyard", "exile", "library", "hand", "battlefield", "command"}
)


def _zone_tags(eff: dict) -> tuple[str, ...]:
    """Directional zone references the effect touches: ``from:<zone>`` /
    ``to:<zone>`` from a ChangeZone's origin/destination, and ``in:<zone>`` for a
    target/filter restricted to a zone (an ``InZone`` property — "exile target card
    from a graveyard", delve, count-in-graveyard). Lane-agnostic IR."""
    tags: list[str] = []
    origin = _norm(eff.get("origin"))
    if origin in _ZONE_NAMES:
        tags.append(f"from:{origin}")
    dest = _norm(eff.get("destination"))
    if dest in _ZONE_NAMES:
        tags.append(f"to:{dest}")
    for key in ("target", "filter", "affected", "target_filter"):
        node = eff.get(key)
        if isinstance(node, dict):
            for prop in node.get("properties") or []:
                if isinstance(prop, dict) and _norm(prop.get("type")) == "inzone":
                    z = _norm(prop.get("zone"))
                    if z in _ZONE_NAMES:
                        tags.append(f"in:{z}")
    # The COUNT operand can count cards in a zone (ZoneCardCount — "draw cards equal
    # to the number of creature cards in your graveyard", "X = cards in your hand").
    # Surface that zone as in:<zone> so graveyard_matters / big_hand_matters fire.
    for key in ("count", "amount", "value", "number"):
        for z in _condition_zones(eff.get(key)):
            tags.append(f"in:{z}")
    return tuple(dict.fromkeys(tags))


# And/Or nest children under "conditions" (a list); Not/ConditionInstead under
# "condition" (a dict). Both keys are walked when projecting the nested tree.
_NESTED_CONDITION_KEYS = ("conditions", "condition")


def _condition_zones(node: object) -> tuple[str, ...]:
    """Every non-stack zone referenced anywhere in a condition subtree — a generic
    deep walk catching ``zone`` (SourceInZone/CastFromZone/InZone) and ``from`` /
    ``to`` (ZoneChangeCount), through nested filters and quantities. Zone-matters
    lanes read this to fire from a gate ("if a creature card is in your graveyard",
    a graveyard count, cast-from-graveyard)."""
    found: set[str] = set()

    def walk(n: object) -> None:
        if isinstance(n, dict):
            for key in ("zone", "from", "to"):
                v = n.get(key)
                if isinstance(v, str) and _norm(v) in _ZONE_NAMES:
                    found.add(_norm(v))
            # GraveyardSize ("the number of cards in your graveyard" — Deep-Sea
            # Terror's threshold lhs, Cryptbreaker, delirium-adjacent gates) carries
            # its zone in the NODE TYPE, not a `zone` key, so the key scan above
            # misses it. CR 400.1: it counts cards in a graveyard → surface graveyard.
            if _norm(n.get("type")) == "graveyardsize":
                found.add("graveyard")
            for child in n.values():
                walk(child)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(node)
    return tuple(sorted(found))


def _project_condition(c: object) -> Condition | None:
    """Project phase's ``condition`` gate into a structural Condition node. ``kind``
    is the normalized type; ``zones`` is the recursive zone set (the field
    graveyard_matters et al. read); ``subject`` is the checked filter (ControlsType
    → metalcraft, ZoneChangedThisWay); ``nested`` holds And/Or/Not children."""
    if not isinstance(c, dict):
        return None
    kind = _norm(c.get("type"))
    if not kind:
        return None
    counters = c.get("counters")
    counter_kind = ""
    if isinstance(counters, dict) and isinstance(counters.get("data"), str):
        counter_kind = _norm(counters.get("data"))
    nested: list[Condition] = []
    for key in _NESTED_CONDITION_KEYS:
        child = c.get(key)
        items = child if isinstance(child, list) else [child]
        for item in items:
            sub = _project_condition(item)
            if sub is not None:
                nested.append(sub)
    return Condition(
        kind=kind,
        zones=_condition_zones(c),
        subject=_condition_subject(c),
        counter_kind=counter_kind,
        comparator=_norm(c.get("comparator")),
        nested=tuple(nested),
    )


def _condition_subject(c: dict) -> Filter | None:
    """The type/object a condition checks: a direct ``filter`` (ControlsType,
    ZoneChangedThisWay, WhenDiesOrExiled) or, for a QuantityComparison/Check, the
    counted filter nested in ``lhs.qty.filter`` ("control three or more artifacts"
    → an Artifact filter). Lets gate-conditions feed the type-matters lanes."""
    direct = _filter(c.get("filter"))
    if direct is not None:
        return direct
    lhs = c.get("lhs")
    if isinstance(lhs, dict):
        qty = lhs.get("qty")
        if isinstance(qty, dict):
            return _filter(qty.get("filter"))
    return None


def _copy_token_effect(eff: dict, raw: str) -> Effect:
    """A CopyTokenOf effect (phase structures "create a token that's a copy of X")
    → a token maker. Scope is the ``owner`` (Controller → you); the made token's
    type is the copied object's filter (``target``) when it's a Typed filter — a
    self/parent/tracked copy leaves the subject unbound (its type is the source's,
    which the effect node doesn't carry)."""
    return Effect(
        category="make_token",
        amount=_amount(eff),
        scope=_effect_scope(eff),
        subject=_filter(eff.get("target")),
        raw=raw,
    )


def _effect_subject(eff: dict) -> Filter | None:
    """What the effect acts ON — the mass/typed filter, the single ``target``, or a
    made token's types. ``target`` is read last and only yields a Filter for a Typed
    object (destroy/bounce/exile target creature); a player target (DefendingPlayer)
    is not Typed, so `_filter` returns None and the effect stays subjectless."""
    for key in ("filter", "affected", "target_filter", "target"):
        f = _filter(eff.get(key))
        if f is not None:
            return f
    # Token effects carry the made token's types as bare strings (mixing the card
    # type "Creature" with subtypes "Goblin"/"Soldier") — split by the card-type set.
    types = eff.get("types")
    if isinstance(types, list):
        strs = [t for t in types if isinstance(t, str)]
        card_types = tuple(t for t in strs if t in _CARD_TYPES)
        subtypes = tuple(t for t in strs if t not in _CARD_TYPES)
        if card_types or subtypes:
            return Filter(card_types=card_types, subtypes=subtypes)
    return None


def _quantity(node: object) -> Quantity | None:
    if isinstance(node, bool):  # guard: bool is an int subclass
        return None
    if isinstance(node, int):
        return Quantity(op="fixed", factor=node)
    if not isinstance(node, dict):
        return None
    t = _norm(node.get("type"))
    if t == "fixed":
        return Quantity(op="fixed", factor=_int(node.get("value"), 1))
    if t == "ref":
        qty = node.get("qty")
        # a Ref over a named scaling operand (devotion/party/domain) — Gray Merchant
        # is Ref→Devotion, so the operand is nested under qty, not a top-level type.
        if isinstance(qty, dict):
            qt = _norm(qty.get("type"))
            op = _SCALING_OPERANDS.get(qt)
            if op is not None:
                return Quantity(op=op, factor=1)
            if qt == "counterson" and _norm(qty.get("counter_type")) == "p1p1":
                return Quantity(op="counters", factor=1)
            # "for each experience counter you have" — a Ref over a player-counter
            # operand (Atreus's draw-X, Azula's pump-X). The experience-scaler is a
            # genuine experience_matters PAYOFF (CR 122.1; parallel to the p1p1
            # counter-scaler above), so stamp the discriminator op="experience" the
            # lane reads, rather than collapsing to a bare op="count".
            if qt == "playercounter" and _norm(qty.get("kind")) == "experience":
                return Quantity(op="experience", factor=1)
            # "deals damage equal to its power" / Fling / Soul's Fire — a Ref over a
            # Power operand. phase folds this to a bare op="count" (subject=None);
            # recover op="power" so the damage_equal_power / creature_ping lanes can
            # read the power-scaling discriminator (ADR-0027 β; b-triage1). Broad by
            # design — only the DealDamage-gated damage arms read it; op="power" is
            # inert metadata on any other effect ("draw equal to its power", etc.).
            if qt == "power":
                return Quantity(op="power", factor=1)
            # a Ref over an Aggregate (Sum of total power/toughness over a filter —
            # Ghalta, Orysa's gate): the operand IS that population. Lift the filter
            # so a count-over-own-board lane reads it (CR 604.3). NB: this is still
            # op="count" — the lane keys on "scales with that filter's population",
            # whether the population is summed power or a head count.
            if qt == "aggregate":
                f = _filter(qty.get("filter"))
                return Quantity(op="count", factor=1, subject=f)
        return Quantity(op="count", factor=1, subject=_objectcount_filter(qty))
    if t == "counterson" and _norm(node.get("counter_type")) == "p1p1":
        # "for each +1/+1 counter on ~" — counter-scaling payoff (only +1/+1, not
        # charge/oil/lore/time, which aren't +1/+1-counters synergy).
        return Quantity(op="counters", factor=1)
    if t == "playercounter" and _norm(node.get("kind")) == "experience":
        # A top-level "for each experience counter you have" operand (the same
        # experience scaler, when phase emits it un-Ref-wrapped).
        return Quantity(op="experience", factor=1)
    if t == "objectcount":
        return Quantity(op="count", factor=1, subject=_filter(node.get("filter")))
    if t == "aggregate":
        # A top-level Aggregate (total power/toughness/etc. over a filter) — same
        # population operand as ObjectCount, the count lane keys on the filter.
        return Quantity(op="count", factor=1, subject=_filter(node.get("filter")))
    if t == "sum":
        # A Sum of expressions ("X = number of creatures you control plus the number
        # of Foods you control" — Hobbit's Sting). Return the FIRST operand that
        # carries a count-over-a-filter subject so a count-over-own-board lane fires;
        # a multi-operand sum isn't one clean Quantity, but the dominant population
        # operand is the build-around the lane cares about.
        for expr in _as_list(node.get("exprs")):
            q = _quantity(expr)
            if q is not None and q.subject is not None:
                return q
        return None
    if t == "multiply":
        inner = _quantity(node.get("inner"))
        return Quantity(
            op="multiply",
            factor=_int(node.get("factor"), 1),
            subject=inner.subject if inner else None,
        )
    # Batch 8 — named scaling operands (a "for each X" where X is a deck-wide count).
    op = _SCALING_OPERANDS.get(t)
    if op is not None:
        return Quantity(op=op, factor=1)
    return None


# Batch 8 — phase quantity operand type → the Quantity.op the lane reads.
_SCALING_OPERANDS: dict[str, str] = {
    "devotion": "devotion",
    "devotionge": "devotion",
    "partysize": "party",
    "basiclandtypecount": "domain",
    # (Power is handled directly in _quantity's Ref handler as op="power", read only
    # by the DealDamage-gated damage_equal_power / creature_ping lanes — NOT a generic
    # scaling operand here. CountersOn is handled in _quantity, gated to +1/+1
    # counters; charge/oil/lore/time scaling is not +1/+1-counters synergy.)
}


def _objectcount_filter(qty: object) -> Filter | None:
    if isinstance(qty, dict) and _norm(qty.get("type")) == "objectcount":
        return _filter(qty.get("filter"))
    return None


# ── count-operand-over-own-board (ADR-0027 go-wide projection) ─────────────────
# A GENERIC own-board count: an ObjectCount / Aggregate whose filter is "creatures
# (artifacts / enchantments) you control" with NO subtype — the whole own-board set
# of that type. CR 604.3: a value defined by that set's population is the strongest
# go-wide care signal (Crusader's P/T IS the creature count; Ghalta's cost reduction
# IS your total power). phase keeps these operands in its raw parse, but the
# STRUCTURED projection drops them when the carrying effect folds to a subjectless
# characteristic_pt / damage / ModifyCost / a gate condition. _board_count_filter
# recovers the operand from the raw phase node; _mark_board_count_operands appends
# a `board_count` marker effect carrying it, so the signals count arm fires.
#
# Parameterized by card_type so artifacts_matter / enchantments_matter reuse it.
# A controller of "you" OR null/unspecified counts (phase emits controller=null for
# "for each creature type among creatures you control" — Valiant Changeling — losing
# the "you", but the operand still ranges over a generic creature set, not an
# opponent's; an explicit "opp" is excluded, never a build-around of yours).
_AGG_FUNCTIONS: frozenset[str] = frozenset({"sum"})


def _is_generic_board_filter(node: object, card_type: str) -> bool:
    """A phase filter selecting your whole own-board set of ``card_type`` (no subtype).
    controller you/unspecified passes; an explicit opponent set fails. A COMPOSITE
    ``Or`` of generic board filters ("artifacts and/or enchantments you control" —
    Shambling Suit, Nettlecyst, Bello) matches ``card_type`` when ANY ``Or`` member is
    a generic board filter of that type (each member's population is summed, so the
    count operand covers both lanes — _board_count_markers emits one per type)."""
    if not isinstance(node, dict):
        return False
    t = _norm(node.get("type"))
    if t == "or":
        members = _as_list(node.get("filters"))
        return any(_is_generic_board_filter(m, card_type) for m in members)
    if t != "typed":
        return False
    card_types, subtypes = _type_and_subtype_filters(node)
    if card_type not in card_types or subtypes:
        return False
    controller = _norm(node.get("controller"))
    return controller in ("", "you", "none", "null")


def _board_count_filter(node: object, card_type: str) -> Filter | None:
    """The Filter of the FIRST own-board count operand (ObjectCount / Aggregate over a
    generic ``card_type``-you-control set) anywhere in ``node``, or None. Recursive —
    the operand can be wrapped in Ref / Sum / Multiply / nested under a condition or a
    modification value. Returns the PROJECTED Filter (controller forced to "you" so the
    downstream generic-set gate reads it, even when phase emitted controller=null)."""
    found: list[Filter] = []

    def walk(n: object) -> None:
        if found:
            return
        if isinstance(n, list):
            for x in n:
                walk(x)
            return
        if not isinstance(n, dict):
            return
        t = _norm(n.get("type"))
        if t in ("objectcount", "aggregate"):
            if t == "aggregate" and _norm(n.get("function")) not in _AGG_FUNCTIONS:
                pass  # only a summing aggregate is a population total (not min/max)
            elif _is_generic_board_filter(n.get("filter"), card_type):
                found.append(Filter(card_types=(card_type,), controller="you"))
                return
        # Formidable (CR 207.2c): phase's named "creatures you control total power at
        # least N" activation/trigger gate — a total-power aggregate over your WHOLE
        # creature board, the same go-wide care as an explicit Aggregate(Sum, Power).
        # Creature-only by name; the artifact/enchantment scan never matches it.
        elif t == "creaturesyoucontroltotalpoweratleast" and card_type == "Creature":
            found.append(Filter(card_types=("Creature",), controller="you"))
            return
        for v in n.values():
            walk(v)

    walk(node)
    return found[0] if found else None


# Permanent card-types the board-count marker scans for. Creature first (its lane is
# creatures_matter); artifacts/enchantments reuse the same helper (their lanes already
# fire from a STRUCTURED count operand the structured projection keeps — this marker
# is the supplement for the operands phase drops, same shape for every type).
_BOARD_COUNT_TYPES: tuple[str, ...] = ("Creature", "Artifact", "Enchantment")


def _board_count_markers(record: dict) -> list[Effect]:
    """Marker effects for own-board count operands the STRUCTURED projection drops.

    phase keeps the operand (an ObjectCount / summing Aggregate over "creatures /
    artifacts / enchantments you control") in its raw parse, but the carrying clause
    folds to a subjectless effect (a characteristic-defining */* P/T, a ModifyCost
    reduction, a damage/draw amount, or a gate condition) so the structured Effect
    loses it. This scans the raw record's static abilities (incl. their conditions and
    modification values), replacements, triggers, and spell/activated abilities for
    such an operand and appends ONE `board_count` marker per permanent type found —
    its `amount.subject` is the generic own-board Filter, which the signals count arm
    (``_is_generic_creature_filter`` / ``_typed_matters_lane``) reads as a go-wide
    care signal (CR 604.3). Append-only; deduped per type so a card with both a
    SetDynamicPower and SetDynamicToughness over the same set emits one marker."""
    nodes = (
        (record.get("static_abilities") or [])
        + (record.get("replacements") or [])
        + (record.get("triggers") or [])
        + (record.get("abilities") or [])
    )
    out: list[Effect] = []
    for card_type in _BOARD_COUNT_TYPES:
        for node in nodes:
            f = _board_count_filter(node, card_type)
            if f is not None:
                desc = node.get("description") or node.get("oracle_text") or ""
                out.append(
                    Effect(
                        category="board_count",
                        scope="you",
                        subject=f,
                        amount=Quantity(op="count", factor=1, subject=f),
                        raw=desc if isinstance(desc, str) else "",
                    )
                )
                break  # one marker per permanent type
    return out


# The artifact/enchantment "matters" types the affinity-keyword marker fires for —
# Affinity (CR 702.41a: "costs {1} less for each [text] you control") and Improvise
# (CR 702.126a: "tap an untapped artifact you control" — always artifacts) are LITERAL
# count-over-your-board operands. phase keeps the affinity subject's `type_filters` in
# the raw keyword node but the projection drops it to a bare `keywords=('Affinity',)`,
# so an affinity-for-artifacts and an affinity-for-enchantments are indistinguishable
# downstream. This recovers the type the cost scales with, so the right lane fires (and
# affinity-for-snow-lands / -gates / a tribe fires NEITHER artifacts nor enchantments).
_AFFINITY_MARKER_TYPES: tuple[str, ...] = ("Artifact", "Enchantment")


def _affinity_improvise_markers(record: dict) -> list[Effect]:
    """`board_count` markers for the Affinity / Improvise keyword count operands.

    Affinity (CR 702.41a) and Improvise (CR 702.126a) reduce a spell's cost for each
    [text] / artifact you control — a count over your own board. phase stores the
    Affinity subject's ``type_filters`` in the raw keyword node ({"Affinity": {...}})
    but the keyword projection drops it; this scans the raw keyword array, and for an
    Affinity-for-artifacts/-enchantments or any Improvise (artifacts only), emits one
    `board_count` marker over the generic own-board Filter of that type. An Affinity
    for a NON-artifact/-enchantment type (snow lands, gates, a tribe) emits nothing —
    only the two permanent-type lanes care. Deduped per type."""
    kws = record.get("keywords")
    if not isinstance(kws, list):
        return []
    seen: set[str] = set()
    out: list[Effect] = []

    def emit(card_type: str, raw: str) -> None:
        if card_type in seen:
            return
        seen.add(card_type)
        f = Filter(card_types=(card_type,), controller="you")
        out.append(
            Effect(
                category="board_count",
                scope="you",
                subject=f,
                amount=Quantity(op="count", factor=1, subject=f),
                raw=raw,
            )
        )

    for kw in kws:
        if isinstance(kw, str):
            if _norm(kw) == "improvise":
                emit("Artifact", "Improvise")
            continue
        if not isinstance(kw, dict) or not kw:
            continue
        name = next(iter(kw))
        if _norm(name) == "improvise":
            emit("Artifact", "Improvise")
        elif _norm(name) == "affinity":
            spec = kw[name]
            card_types, _subtypes = (
                _type_and_subtype_filters(spec) if isinstance(spec, dict) else ((), ())
            )
            for ct in _AFFINITY_MARKER_TYPES:
                if ct in card_types:
                    emit(ct, f"Affinity for {ct.lower()}s")
    return out


# A COMPOSITE go-wide anthem / type-grant over the whole own-board artifact-AND-
# enchantment set ("each non-Equipment artifact and non-Aura enchantment you control …
# is a 4/4 creature and has …" — Bello). phase Unimplemented-parses this static (a
# composite-typed mass type/ability grant), dropping the subject; both populations are
# buffed/animated, so it fires BOTH lanes. Anchored on the composite head "artifact[s]
# … (and|and/or) … enchantment[s] you control" FOLLOWED by a go-wide anthem verb (is a
# N/N creature / get(s) +X/+X / have/gain). A SINGLE-TARGET form ("up to one target
# artifact or enchantment you control", "target artifact, creature, or enchantment you
# control" — Adagia, Scrollshift) is excluded by the no-"target" gate, so removal /
# copy / blink of one permanent never matches (over-fire boundary, CR 604.3).
_COMPOSITE_BOARD_GRANT = re.compile(
    r"artifacts?\b[^.]*?\benchantments?\s+you\s+control"
    r"|artifacts?\s+and(?:/or)?\s+enchantments?\s+you\s+control",
    re.IGNORECASE,
)
_COMPOSITE_BOARD_ANTHEM = re.compile(
    r"\bis (?:a|an)\b[^.]*?\bcreature"  # "… is a 4/4 Elemental creature …"
    r"|\bare\b[^.]*?\bcreatures?\b"
    r"|\bget(?:s)?\s+[+-]"  # "… get +1/+1 …"
    r"|\b(?:have|has|gain|gains)\b",  # "… have shroud / have <ability>"
    re.IGNORECASE,
)


def _composite_board_grant_markers(record: dict) -> list[Effect]:
    """`board_grant` markers (Artifact + Enchantment) for a composite go-wide anthem /
    type-grant over the whole own-board artifact-and-enchantment set that phase
    Unimplemented-parses (Bello). None unless the oracle text has the composite head
    AND a go-wide anthem verb AND no single-target "target"/"up to … target" clause on
    the matched span. Fires both lanes (each population is buffed/animated)."""
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    m = _COMPOSITE_BOARD_GRANT.search(text)
    if m is None:
        return []
    # the clause around the composite head (to its sentence end) must carry an anthem
    # verb and must NOT be a single-target ("target …") effect.
    start = text.rfind(".", 0, m.start()) + 1
    end = text.find(".", m.end())
    clause = text[start : end if end != -1 else len(text)]
    if "target" in clause.lower() or not _COMPOSITE_BOARD_ANTHEM.search(clause):
        return []
    raw = clause.strip()
    return [
        Effect(
            category="board_grant",
            scope="you",
            subject=Filter(card_types=(ct,), controller="you"),
            raw=raw,
        )
        for ct in ("Artifact", "Enchantment")
    ]


# A MASS keyword/protection/evasion grant to your WHOLE own-board creature set
# ("Creatures you control gain/have <ability>", "creatures you control can't be
# blocked") that phase swallows into a subjectless carrier — a chosen-ability grant
# (Linvala → choose), a modal grant (Mishra), an upkeep restriction whose subject
# phase drops (Keeper). Mirrors the SWEEP team-evasion anchor: "creatures you
# control" preceded ONLY by "other"/"attacking" (so a SUBTYPE lord "Goblin creatures
# you control gain haste" — type_matters, CR 205.3 — never matches) AND a grant verb
# (gain/have) OR the "can't be blocked" team-unblockable phrasing. Protective +
# evasion keywords (CR 702): a generic mass grant of one is a go-wide creatures care.
# The bare-head anchor: "creatures you control" preceded ONLY by other/attacking
# (no subtype/color/class word), at a clause boundary — so a SUBTYPE/COLOR lord
# ("Goblin/White creatures you control") never matches (those route to type_matters /
# a color band, CR 205.3).
_BARE_CREATURES_YOU_CONTROL = (
    r"(?<![A-Za-z])(?:other |attacking )?creatures you control"
)
_MASS_CREATURE_GRANT = re.compile(
    _BARE_CREATURES_YOU_CONTROL + r" (?:gain|have)\b"
    r"(?:"
    # a QUOTED granted ability ("Creatures you control have '{T}: Add {G}'" —
    # Citanul Hierophants, Cryptolith Rite, Battery Bearer, Retaliation): the mass
    # grant of any quoted ability to the whole board is go-wide.
    r"\s*\""
    # OR a named evasion / protection / combat keyword within the grant clause.
    r"|[^.\"]{0,60}?\b(?:menace|fear|intimidate|shadow|horsemanship|skulk|flying"
    r"|trample|vigilance|haste|lifelink|deathtouch|first strike|double strike"
    r"|hexproof|shroud|indestructible|ward|protection|reach|flash|afterlife"
    # a chosen-ability grant: "Choose hexproof or indestructible. Creatures you
    # control gain THAT ABILITY" (Linvala) — the keyword is in the Choose clause,
    # the grant refers to it. "that ability"/"those abilities" is the anchor.
    r"|that abilit(?:y|ies)|those abilities"
    # a mass base-P/T SET grant ("Creatures you control have base power and
    # toughness 9/9" — The Capitoline Triad's emblem) — rewrites the whole board.
    r"|base power and toughness"
    # a formidable-style total-power/toughness GATE ("creatures you control have
    # total power 8 or greater" — Case of the Trampled Garden's solve condition).
    r"|total (?:power|toughness))\b"
    r")"
    r"|" + _BARE_CREATURES_YOU_CONTROL + r"[^.]*?can't be blocked",
    re.IGNORECASE,
)


# A MASS UNTAP of your whole creature board ("Untap all creatures you control") that
# phase leaves unstructured — a static (Drumbellower), a third ability phase dropped
# (Quest for Renewal), or a sub-effect folded into an extra-combat trigger (Lightning
# Runner). Mirror of the structured untap+counter_kind="all" path for the cards phase
# DID parse; this oracle anchor is the narrow recovery for the ones it didn't. Anchored
# on the literal "untap all creatures you control" (no broad substring).
_MASS_UNTAP = re.compile(r"untap all creatures you control", re.IGNORECASE)

# A "for each creature you control" COUNT operand phase left in raw (an Unrecognized /
# folded parse — Eidolon's per-creature self-pump, Siege Behemoth's per-creature
# trample, a draw/damage X-count). CR 604.3: a value defined by your creature count is
# a go-wide care. The narrow count-operand phrase (NOT the broad "creatures you
# control" substring the deleted regex floor used) — it always denotes a per-creature
# count, so it never over-fires onto a non-go-wide carrier; a trailing "with <pred>"
# (a restricted count) is still a go-wide count of a creature subset.
_FOR_EACH_CREATURE = re.compile(
    r"for each creature you control\b"
    # the X-defining count form ("X is the number of creatures you control",
    # "deals damage equal to the number of creatures you control" — Lantern Flare,
    # Superior Numbers' "in excess of") phase Unimplemented-parsed. Anchored on the
    # count-DEFINING phrase, NOT the bare "any number of creatures" QUANTIFIER (a
    # selection, not a count) and NOT a TRIBAL count ("...you control of that type" —
    # Kindred Summons) nor a PAST-TENSE death count ("...you controlled that died").
    r"|(?:where x is|x is|equal to) the number of creatures you control"
    r"(?!\w)(?! of (?:that|a|the chosen))",
    re.IGNORECASE,
)


# Count-operand recovery (ADR-0027 count-operand cluster). phase DROPS the "for each
# X" / "equal to the number of X" SCALING operand off some draw and pump effects,
# leaving amount.op='fixed' factor=1 — the scaling is lost (Strata Scythe, Pride of
# the Clouds, Skullmulcher, Voice of Many, Allied Strategies). The phrase survives in
# raw, so this anchor lifts the dropped count back to op='count' so scaling_pump /
# draw_for_each fire. Anchored on the genuine count phrase, NOT a "draw X cards" X-
# spell (Braingeyser — that is op='count' already, with no "for each") nor a "deals N
# to each" SYMMETRIC distribution.
_FOR_EACH_COUNT = re.compile(
    r"\bfor each\b|\bequal to the number of\b|\bcards equal to the number\b",
    re.IGNORECASE,
)
# The counted SUBJECT, when the raw names a clear permanent class right after "for
# each" / "number of" — so the recovered count carries a real Filter (a creature
# scaling vs an artifact scaling read differently downstream). A bare/uncapturable
# count (an opponent count, a same-name count) leaves subject=None — still a genuine
# scaling draw/pump, just unattributed.
_FOR_EACH_SUBJECT = re.compile(
    r"(?:for each|number of)\s+(?:other\s+)?(?:tapped\s+|attacking\s+)?"
    r"(creature|artifact|enchantment|land|permanent|aura|card|counter)s?\b",
    re.IGNORECASE,
)
_FOR_EACH_TYPE_MAP = {
    "creature": "Creature",
    "artifact": "Artifact",
    "enchantment": "Enchantment",
    "land": "Land",
    "permanent": "Permanent",
    "aura": "Aura",
}


def _recover_count_operand(ability: Ability) -> Ability:
    """Lift a DROPPED "for each X" scaling operand on a draw / pump effect back to
    op='count' (ADR-0027 count-operand cluster). phase leaves the amount as
    op='fixed' factor=1 when it loses the count, but the "for each" / "equal to the
    number of" phrase survives in raw — so this restores the count so scaling_pump /
    draw_for_each fire. A counted permanent CLASS named in the raw becomes the count
    subject; an uncapturable count (opponents, same-name) stays subject=None. Append-
    only: an effect already carrying a count/counters/domain/devotion/party operand
    is untouched (the structured count is preferred). CR 107.3."""
    new_effects: list[Effect] = []
    changed = False
    for e in ability.effects:
        amt = e.amount
        if (
            e.category in ("draw", "pump")
            and amt is not None
            and amt.op == "fixed"
            and amt.subject is None
            and _FOR_EACH_COUNT.search(e.raw or "")
        ):
            # The recovered count multiplies by the same per-unit factor phase kept
            # (Anya's +3/+3 for each, Nyxathid's -1/-1 for each), so preserve it.
            subj = None
            sm = _FOR_EACH_SUBJECT.search(e.raw or "")
            if sm is not None:
                ct = _FOR_EACH_TYPE_MAP.get(sm.group(1).lower())
                if ct is not None:
                    subj = Filter(card_types=(ct,))
            new_effects.append(
                replace(e, amount=Quantity(op="count", factor=amt.factor, subject=subj))
            )
            changed = True
        else:
            new_effects.append(e)
    if not changed:
        return ability
    return replace(ability, effects=tuple(new_effects))


def _mass_untap_marker(record: dict) -> Effect | None:
    """An `untap`+counter_kind="all" marker over the generic creature board when the
    oracle text says "untap all creatures you control" but phase left it unstructured.
    The subject is the synthesized generic creature Filter so the go-wide mass-untap
    arm reads it. None when absent."""
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    m = _MASS_UNTAP.search(text)
    if m is None:
        return None
    return Effect(
        category="untap",
        scope="you",
        subject=Filter(card_types=("Creature",), controller="you"),
        raw=m.group(0),
        counter_kind="all",
    )


# Record-level +1/+1 fallback (ADR-0027 counters_matter pass 2): a face whose +1/+1
# PLACEMENT or "has/with a +1/+1 counter" PAYOFF reference phase dropped ENTIRELY —
# not folded into a carrier raw (so _narrow_counter_refs can't see it), but absent
# from the structured parse, surviving only on the FACE oracle text. phase trims a
# grant's reference clause ("Target creature you control with a +1/+1 counter on it
# gains …" → kept only "gain lifelink" — Ollenbock, Steppe Glider), drops a devour /
# enters-with-copy / cast-from-graveyard placement (Preyseizer, The Mimeoplasm,
# Worldheart Phoenix, Undead Sprinter), or loses a damage-prevention replacement
# (Vigor, Stormwild Capridor). Mirrors _mass_creature_grant_marker / the dropped-
# static face markers: a narrowly-anchored face-text scan, GATED to faces with no
# structured counters effect (so it never re-tags a clean parse). The anchors are the
# explicit placement / has-a-counter phrases (never a bare "counter" word), CR 122.1
# / 122.6.
_P1P1_PLACE_FACE = re.compile(
    r"\bput(?:s)?\b[^.]*?\+1/\+1 counter"
    r"|\bdistribute(?:s)?\b[^.]*?\+1/\+1 counter"
    r"|\benters?\b[^.]*?\bwith\b[^.]*?\+1/\+1 counter"
    r"|\benters? as a copy\b[^.]*?\+1/\+1 counter"
    # A reanimate / blink RIDER: "return ~ to the battlefield with N +1/+1 counters
    # on it" (Cosima's voyage-return, Abuelo's "with X additional"). The placement
    # rides the return, which phase keeps as a changezone with the +1/+1 dropped.
    r"|\b(?:return|battlefield)\b[^.]*?\bwith\b[^.]*?\+1/\+1 counters? on it"
    r"|\bwith X additional \+1/\+1 counter",
    re.IGNORECASE | re.DOTALL,
)
_P1P1_HAVE_FACE = re.compile(
    r"\bwith (?:a |an |one or more |no )?\+1/\+1 counters? on (?:it|them|him|her)\b"
    r"|\bhas? (?:a |an )?\+1/\+1 counter on (?:it|him|her)\b"
    r"|\bwith (?:a )?counters? on (?:it|them|him|her)\b"
    r"|\+1/\+1 counters? on creatures you control\b"
    r"|\bpower greater than its base power\b"
    r"|\bremove any number of \+1/\+1 counters\b",
    re.IGNORECASE,
)


def _counter_face_marker(record: dict, abilities: list[Ability]) -> Effect | None:
    """A face-level +1/+1 marker when the oracle text places (or references a
    creature having) a +1/+1 counter but NO structured counters effect survived the
    parse — a place_counter(p1p1) for a placement, else a counters_have_ref for a
    payoff reference. None when a place_counter / counters_have_ref already exists on
    the face (the per-ability marker / structural parse covered it) or no phrase
    matches (counters_matter pass 2, CR 122.1 / 122.6). Reminder text is stripped so
    a keyword's own reminder ("(… put X +1/+1 counters …)") never false-fires. The
    gate blocks only a p1p1 place_counter or a counters_have_ref already present — a
    NON-p1p1 named-counter placement (voyage/oil/charge) does NOT cover a separate
    +1/+1 placement on the same face (Cosima's voyage counter alongside its
    enters-with-a-+1/+1-counter return rider)."""
    if any(
        (e.category == "place_counter" and e.counter_kind == "p1p1")
        or e.category == "counters_have_ref"
        for a in abilities
        for e in a.effects
    ):
        return None
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    m = _P1P1_PLACE_FACE.search(text)
    if m is not None:
        return Effect(
            category="place_counter", scope="you", counter_kind="p1p1", raw=m.group(0)
        )
    m = _P1P1_HAVE_FACE.search(text)
    if m is not None:
        return Effect(category="counters_have_ref", scope="you", raw=m.group(0))
    return None


def _for_each_creature_marker(record: dict) -> Effect | None:
    """A `board_count` marker carrying a generic creature count operand when the oracle
    text scales "for each creature you control" but phase folded/Unrecognized the
    operand (Eidolon's per-creature pump, Siege Behemoth, a draw/damage X). None when
    absent. Its amount.subject is the generic creature Filter the count arm reads."""
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    m = _FOR_EACH_CREATURE.search(text)
    if m is None:
        return None
    f = Filter(card_types=("Creature",), controller="you")
    return Effect(
        category="board_count",
        scope="you",
        subject=f,
        amount=Quantity(op="count", factor=1, subject=f),
        raw=m.group(0),
    )


def _mass_creature_grant_marker(record: dict) -> Effect | None:
    """A `grant_keyword` marker over the GENERIC own-board creature set when the card's
    oracle text mass-grants a keyword/evasion to "creatures you control" but phase
    folded the grant into a subjectless carrier (choose / modal / restriction). The
    subject is the synthesized generic creature Filter so the go-wide creatures_matter
    arm reads it. None when the card has no such grant. Narrowly anchored (no broad
    "creatures you control" substring) so it never mirrors the deleted regex floor —
    a SUBTYPE-lord grant is excluded by the bare-"creatures" head anchor."""
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    m = _MASS_CREATURE_GRANT.search(text)
    if m is None:
        return None
    return Effect(
        category="grant_keyword",
        scope="you",
        subject=Filter(card_types=("Creature",), controller="you"),
        raw=m.group(0).strip(),
        counter_kind="mass_grant",
    )


# ── dropped-static face markers (ADR-0027 projection deepening) ────────────────
# A handful of named-mechanic STATIC grants / replacement clauses are dropped by
# phase ENTIRELY — not folded into a carrier raw (so the per-ability marker passes
# can't see them), but absent from the parse, surviving only on the FACE's oracle
# text. (Birgi's "Creatures you control can boast twice"; The Masamune's quoted
# "triggers an additional time" granted ability; Varolz's "Each creature card in
# your graveyard has scavenge"; Kenessos/Eligeth's "If you would scry a number of
# cards … instead" replacement; Y'shtola's "there is an additional end step".) We
# scan the face oracle text for each precise grant/replacement phrase and APPEND a
# marker effect carrying the mechanic's payoff category, as one synthesized static
# ability. Append-only; each anchor is the explicit clause (never a bare keyword),
# CR-cited. trigger_doubling is GATED to faces with no structural trigger_doubling
# effect (the bare-doubler class — Panharmonicon/Yarok — already binds structurally;
# only the granted/quoted form, The Masamune, is the residual).
# Boast (CR 702.142) static AMPLIFIER: "… can boast twice …" (Birgi). The Boast
# SOURCES carry the keyword; this is the keyword-less amplifier.
_BOAST_GRANT = re.compile(r"\bcan boast\b", re.IGNORECASE)
# Trigger-doubling (CR 603.3 — "an additional time") GRANTED/QUOTED: a "… triggers
# an additional time" clause phase dropped from a granted ability (The Masamune).
_TRIGGER_DOUBLING_GRANT = re.compile(
    r"\btriggers? an additional time\b|\btrigger an additional time\b",
    re.IGNORECASE,
)
# Damage-doubling (CR 615) AMPLIFIER phase dropped the modification from — a
# DamageDone replacement whose `damage_modification` phase left None (Neriv —
# entered-this-turn-source condition; Lightning — a delayed source-scoped grant),
# an `Unimplemented` "deal triple that damage" sub_ability (Jeska's loyalty mode),
# or a one-shot "deals twice that much damage" rider on a sacrifice/discard payoff
# (Borborygmos, Surtland Flinger, Cut Propulsion). All are genuine damage
# amplifiers (burn / big-hit payoffs), the Furnace-of-Rath archetype. EXCLUDES
# halving / prevention ("prevent half that damage" — Dark Sphere; the opposite of a
# doubler, an old SWEEP over-fire the structural IR correctly drops). Gated to faces
# with no structural damage_doubling.
_DAMAGE_DOUBLING_REF = re.compile(
    r"\bdeals? (?:double|triple) that damage\b"
    r"|\bdeals? twice that (?:much|damage)\b"
    r"|\bdouble the (?:next )?damage\b"
    r"|\bdeals that much damage plus\b",
    re.IGNORECASE,
)
# Scavenge (CR 702.97) graveyard-wide GRANT: "Each creature card in your graveyard
# has scavenge" (Varolz, Young Deathclaws, The Cave of Skulls). The intrinsic
# scavengers carry the keyword; this is the keyword-less granter. Anchored on the
# grant phrase "has scavenge", not the bare keyword (so a "Scavenge the Dead"
# ability WORD — Malanthrope, CR 207.2c — can't match).
_SCAVENGE_GRANT = re.compile(r"\bhas scavenge\b", re.IGNORECASE)
# Scry (CR 701.22) REPLACEMENT amplifier: "If you would scry a number of cards, …
# instead" (Kenessos, Eligeth — phase drops the replacement static entirely). The
# scry/surveil DOERS land in topdeck_select + the scried/surveiled triggers; this is
# the replacement-amplifier arm with no trigger/effect to bind.
_SCRY_REPLACEMENT = re.compile(
    r"\bif you would scry (?:a number of cards|\d+)\b", re.IGNORECASE
)
# Extra end step (CR 513) grant: "there is an additional end step" / "an additional
# ending phase" (Y'shtola Rhul — phase drops the clause; it emits AdditionalPhase
# only for combat/upkeep). Mirrors the deleted SWEEP regex.
_EXTRA_END_GRANT = re.compile(
    r"\badditional end step\b|\badditional ending phase\b", re.IGNORECASE
)
# Tapped-creatures payoff (CR 509) phase strips the subject/predicate from: a GRANT
# ("Tapped creatures you control can block as though they were untapped" — Masako the
# Humorless) parsed as a grant_keyword with subject=None, or a COUNT ("X is the number
# of tapped creatures you control" — Harvest Season) whose board_count subject phase
# emits without the Tapped predicate. Anchored on the grant verb after the subject OR
# the "number of tapped creatures you control" count phrase, so a removal "destroy
# tapped creatures" can't match. The marker rebuilds a Tapped-creature subject Filter
# so the existing Tapped-predicate read fires tapped_matters. Gated to faces with no
# structural Tapped predicate.
_TAPPED_GRANT = re.compile(
    r"\btapped creatures you control (?:have|get|gain|gains|are|can|with)\b"
    r"|\bnumber of tapped creatures you control\b",
    re.IGNORECASE,
)
# Extra beginning phase (CR 501.1) grant: "an additional beginning phase after this
# phase" (Shadow / Sphinx of the Second Sun, Cyclonus's back face). A beginning
# phase contains the untap, UPKEEP, and DRAW steps, so an extra one re-triggers both
# "at the beginning of your upkeep" AND "at the beginning of your draw step" payoffs
# — phase mis-routes the grant to `extra_combats` (Second Sun) or drops it entirely
# (Cyclonus's combat-damage-triggered clause). Anchored on the exact phrase (only the
# 4 phase-doublers carry it), never a bare "beginning phase" reference.
_EXTRA_BEGINNING_PHASE_GRANT = re.compile(
    r"\badditional beginning phase\b", re.IGNORECASE
)
# Life-total SET / DOUBLE (CR 119/120) phase mis-categorizes or drops: "your life
# total becomes <X>" (the most common set-life wording) routes to animate (Touch of
# the Eternal, Invincible Hymn), shuffle (Lich's Mirror), or lose_game (Enduring
# Angel), or is dropped entirely on a modal bullet / replacement (Captive Audience,
# The Golden Throne, Exquisite Archangel, Stunning Reversal). Life DOUBLING ("double
# … life total") routes to the `double` category, which is NOT the set_life lane.
# Both are in-lane ("set/exchange/double a life total"); anchored on "life total
# becomes" and "double … life total" — the latter requires "life total" in the same
# clause so token/counter/damage doubling (the bulk of `double`) is excluded, and a
# damage-scaled-by-life clause ("damage equal to half … life total" — Heartless
# Hidetsugu) never says "becomes" or "double".
_LIFE_TOTAL_SET = re.compile(
    r"\blife total becomes\b|\bdouble\b[^.]*\blife total\b", re.IGNORECASE
)
# Lure / force-a-block (CR 509.1c/h) phase swallows into a pump/grant_keyword compound
# clause (Indrik Umbra, Revenge of the Hunted), drops in a conditional static (Seton's
# Desire, Stone-Tongue Basilisk), folds the equip rider as "must be blocked by <type>
# if able" (Ace's Baseball Bat, Slayer's Cleaver), or buries it in a modal bullet
# (Glorfindel). Two phrasings: "able to block <X> do so" (force ALL able blockers) and
# "must be blocked [by <type>] if able" (force a block on the attacker). Both force a
# block — the lane explicitly wants force-a-block — so a by-<type> restriction is a
# refinement, not a disqualifier. The block-LIMIT tax ("can't be blocked by more than
# one") never says "do so" or "must be blocked … if able", so it can't match.
_LURE_ABLE = re.compile(r"\bable to block\b[^.]*\bdo so\b", re.IGNORECASE)
_LURE_MUST = re.compile(r"\bmust be blocked\b[^.]*?\bif able\b", re.IGNORECASE)
# "Tap OR untap target" (CR 701.20) — phase parses the disjunction as a target_only
# + a `choose` "tap or untap" marker, DROPPING the untap half (Twiddle, Pestermite,
# Coral Trickster, the whole untap-engine cantrip family). The untap side is the
# engine half (used to untap mana sources / pseudo-vigilance), so recover an untap
# effect. Gated to faces with no structural untap (Dream's Grip's explicit modal
# "• Untap target permanent" already structures both, so it's skipped).
_TAP_OR_UNTAP_REF = re.compile(
    r"\btap or untap (?:target|another target|up to)\b", re.IGNORECASE
)
# Combat-forcing disentanglement (CR 508.1g / 701.38). Two structurally distinct
# compulsions phase DROPS to raw (the self/team static carries no abilities; the
# reward-payoff trigger flattens to event=None with the redirect condition in raw):
#
#   • FORCED ATTACK (self-force) — "~ attacks each/every combat if able", "attacks
#     that player this combat if able", a granted "creatures you control attack each
#     combat if able" (Dauthi Slayer, Battle-Mad Ronin, Goblin Spymaster's token
#     grant). A COMPULSION to swing — the forced_attack lane (an aggro/symmetric-force
#     theme), NOT goad. phase emits a `MustAttack` mode only for the ACTIVATED single-
#     target form (Basandra); the static self/team force is dropped.
#   • GOAD REWARD (redirect-payoff) — "attacks one of your opponents", "attacks a
#     player other than you", "whenever a(nother) player attacks (one of your
#     opponents)", the defending-player payoff (Gahiji, Breena, Frontier Warmonger,
#     Kazuul). The card REWARDS opponents' creatures being redirected at another player
#     — the goad mechanic's payoff (CR 701.38b: a goaded creature attacks a player
#     other than its controller), so it wants goad effects. NOT a self-force.
#
# The two patterns are mutually exclusive by construction: "each combat if able" is
# the self-compulsion; "one of your opponents" / "a player other than you" / "a player
# attacks" is the redirect-reward. A single-target "target creature attacks … if able"
# (Basandra) keeps phase's force_attack effect and is NOT matched here (no "each/every
# combat", no opponent-redirect) — it stays forced_attack-adjacent without leaking goad.
_FORCE_ATTACK_REF = re.compile(
    r"attacks? (?:each|every) combat if able"
    r"|attacks? that player this combat if able"
    r"|may attack only the nearest opponent",
    re.IGNORECASE,
)
_GOAD_REWARD_REF = re.compile(
    r"attacks? one of your opponents"
    r"|attacks? a player other than (?:you|its controller)"
    r"|whenever a(?:nother)? player attacks"
    r"|creature an opponent controls attacks[^.]*"
    r"(?:you're|you are) the defending player",
    re.IGNORECASE,
)
# Energy ({E}, CR 122.1) phase loses on a SINK ("pay {E}", "Replicate—Pay {E}{E}{E}",
# "unless you pay {E}"), a "Whenever you get one or more {E}" PAYOFF trigger (flattened
# to event='other'), or a replacement/doubler ("get that many plus one {E} instead").
# The {e} symbol is an unambiguous anchor — it appears only on real energy cards (no
# reminder/flavor/adjacent-mechanic collision) — so a single broad marker is safe.
_ENERGY_REF = re.compile(r"\{e\}", re.IGNORECASE)
# Rad counters (CR 122, Fallout) phase mangles: a place_counter with the rad kind
# dropped (counter_kind=''), a counter_doubling, or a clause dropped entirely. phase's
# player-counter-kind projection is unreliable here, so anchor on the literal phrase —
# "rad counter(s)" appears only on real rad cards.
_RAD_REF = re.compile(r"\brad counters?\b", re.IGNORECASE)
# Suspect (CR 701.60) phase emits only on the leading imperative verb. The verb buried
# mid-clause / in a granted ability ("…and suspect it", "suspect up to one target") and
# the adjective/state form ("suspected creature") survive only in raw. Anchored on the
# verb (NOT followed by "counter" — Investigator's Journal's "suspect counter" is a
# same-named COUNTER type, not the Suspect designation, CR 701.60b) or "suspected".
_SUSPECT_REF = re.compile(r"\bsuspects?\b(?! counter)|\bsuspected\b", re.IGNORECASE)
# Venture / dungeon-completion (CR 701.46) phase drops on a non-primary modal mode (You
# Find a Cursed Idol), a granted nested ability (Fly), or an unrecognized "complete a
# dungeon" trigger (Dungeon Crawler). Anchored on the venture/complete verb phrase;
# gated OUT of a `restriction` effect (Keen-Eared Sentry's opponent-scoped anti-venture
# hate is not a venture enabler/payoff for the controller).
_VENTURE_REF = re.compile(
    r"\bventure into the dungeon\b|\bcomplete a dungeon\b", re.IGNORECASE
)
# Crimes (CR 701.49, Outlaws) in CONDITION form — "(if|as long as) you've committed a
# crime this turn" / a cost reduction "if you've committed a crime" — the dominant
# crime-PAYOFF template phase has no condition kind for (it flattens the crime check
# into a quantitycomparison condition or drops it into raw). The TRIGGER form ("Whenever
# you commit a crime") already binds via phase's commit_crime trigger event; this is the
# keyword-less condition-form payoff. Anchored on the explicit "committed a crime".
_CRIME_REF = re.compile(
    r"(?:if|as long as|whenever) you'?ve committed a crime"
    r"|committed a crime this turn",
    re.IGNORECASE,
)
# Counter a spell/ability (CR 701.5) buried where phase loses it: a modal mode body
# ("• Counter target creature spell" — Fangkeeper's Familiar, Ertai Resurrected,
# phase keeps only the `choose` header), a granted/quoted Aura ability ("Enchanted
# land has '{T}: Counter target spell…'" — Equinox, Sunken Field, phase emits
# abilities=()), or a non-grant carrier (Goblin Artisans' coin_flip absorbs "counter
# target artifact spell you control"). The same `counter target … spell/ability`
# phrase the counter_control regex uses (FP-free at this breadth), gated to faces
# with no structural counter_spell so the 426 real counterspells aren't re-tagged.
_COUNTER_TARGET_REF = re.compile(
    r"counter target (?:[a-z-]+ )*(?:spell|ability)", re.IGNORECASE
)
# Spell-copy (CR 707) GRANTED / QUOTED / CONDITIONAL phase drops to raw: a "copy
# that/it/this/the … spell|card" clause phase loses in a modal bullet (Twinferno),
# a granted/quoted ability (Ral's emblem, God-Eternal Kefnet), a coin-flip /
# replacement / reflexive body (Krark, Pyromancer's Goggles), or a storm-style "copy
# it for each spell cast" reminder (Storm Force of Nature, Crackling Spellslinger).
# The structural CopySpell effect + the storm/replicate/conspire/casualty KEYWORDS
# cover the rest; this is the keyword-less granted/conditional residual. EXCLUDES
# "copy of …" (clone — "create a copy of target creature" is CopyTokenOf / BecomeCopy,
# the clone lanes, not spell-copy) by anchoring "copy <pron> … spell/card" and "copy
# it for each spell". Gated to faces with no structural spell_copy.
_COPY_SPELL_REF = re.compile(
    r"\bcop(?:y|ies)\s+(?:that|it|this|the|each|target)\b[^.]*\b(?:spell|card)\b"
    r"|\bcop(?:y|ies)\s+(?:it|that spell)\s+for each spell\b"
    r"|\bcop(?:y|ies)\s+(?:it|that spell)(?:\s+three times| twice| \d+ times)"
    # Keyword-less GRANTER of a spell-copy keyword ("… spell you cast has/have
    # casualty/replicate/conspire/storm/demonstrate" — Anhelo, Djinn Illuminatus,
    # Wort, Threefold Signal, Crackling Spellslinger, The Twelfth Doctor). The HAVERS
    # ride the Scryfall keyword; this is the conferral phase folds into the cast-grant
    # carrier. Anchored on "has/have <copy-keyword>" so a card NAMED "… Storm" can't
    # match.
    r"|\b(?:has|have)\s+(?:casualty|replicate|conspire|storm|demonstrate)\b",
    re.IGNORECASE,
)
# Low-power payoff (CR 208) — "creature(s) you control with power N or less" buff /
# evasion / etb. phase DROPS the power threshold predicate on these effect/trigger
# subject shapes (the subject is None, or the Filter has empty predicates), so the
# low_power_matters detector (which keys on a PtComparison:Power:LE/LT predicate on a
# you-controller Creature Filter) never fires. We rebuild that subject Filter from the
# raw, captured with the threshold N so the existing predicate read fires the lane.
# Anchored on "you control with power N or less/fewer" — removal ("destroy a target
# with power N or less") and evasion-bypass ("can't be blocked by creatures with power
# N or greater") never say "you control".
_LOW_POWER_REF = re.compile(
    r"creatures? you control with power (\d+) or (?:less|fewer)", re.IGNORECASE
)
# Repeatable "Pay N life:" activated-ability cost phase loses: it misparses the cost
# (Arco-Flagellant's Endurant ability becomes a spell-with-pay_cost; Hibernation
# Sliver's self-usable granted ability) or drops the conferred quoted "…Pay 1 life:
# Draw" ability entirely (Underworld Connections, Degavolver, Anavolver, Lithoform
# Blight, Forgotten Monument). The colon-delimited "Pay N life:" is the precise cost
# anchor (not reminder text, not a one-shot cast-time additional cost). Gated to faces
# with no structural paylife cost so the 167 cards that parse it natively aren't
# double-tagged. CR 118.
_PAY_LIFE_REF = re.compile(r"[Pp]ay \d+ life:")
# Can't-block grant (CR 509) phase loses in a MODAL mode body ("• Target creature
# can't block this turn" — Breeches, Retreat to Valakut, phase keeps only the
# `choose` header) or a GRANTED QUOTED ability ("Enchanted land has '{T}: Target
# creature can't block…'" — Hostile Realm, Malicious Intent, phase emits
# abilities=()). We isolate the modal bullet / quoted-grant SEGMENT, then apply the
# same _CANT_BLOCK_REF (leading determiner + "creature … can't block") minus
# _CANT_BLOCK_TAX as the carrier-raw marker — segment isolation keeps the greedy
# determiner match from spanning an unrelated make_token "create … token with 'this
# token can't block'" clause (Anax, Totentanz), which the per-carrier marker already
# excludes via _CANT_BLOCK_CARRIERS dropping make_token.
_CANT_BLOCK_MODAL_BULLET = re.compile(r"•[^•\n]*?can'?t block", re.IGNORECASE)
_CANT_BLOCK_GRANT_QUOTE = re.compile(
    r'(?:has|have|enters with) "[^"]*?can\'?t block[^"]*"', re.IGNORECASE
)
# Oil counters (CR 122, ONE/MOM) as a PAYOFF reference — a card that COUNTS or
# CONDITIONS on existing oil counters ("permanents you control with oil counters on
# them", "if you control a permanent with an oil counter"). phase parses the
# consequence (draw / damage / pump / cost reduction) but DROPS the oil-counter
# operand/condition entirely (no place_counter, so _COUNTER_KIND_KEYS['oil'] never
# fires). Anchored on the literal "oil counter(s)" phrase — it appears only on real
# oil cards. The PLACER side (a place_counter with counter_kind='oil') already binds
# the lane natively; this is the keyword-less cares-about payoff half.
_OIL_REF = re.compile(r"\boil counters?\b", re.IGNORECASE)
# "Starting life total" (CR 103.4) payoff reference — a card that compares against /
# resets to the starting life total ("less than half their starting life total",
# "your life total becomes equal to your starting life total", "greater than your
# starting life total"). phase has no structure for this specific game value, so it
# survives only on the face oracle text. Anchored TIGHTLY on "starting life total"
# (the specific value) — NOT the broad regex's "life total is greater/less" second
# arm, which over-fires on unrelated life thresholds ("if your life total is less
# than 7" — Elderscale Wurm), which the structural IR correctly drops.
_STARTING_LIFE_REF = re.compile(r"\bstarting life total\b", re.IGNORECASE)
# Saga (CR 714) / lore-counter MANIPULATION & PAYOFF — a card that puts/removes lore
# counters on a Saga (Keldon Warcaller, Satsuki, Garnet), references lore counters in a
# payoff/condition ("for each lore counter on this Saga", "lore counters among Sagas
# you control" — the chapter-scaling Sagas, Tom Bombadil), or builds its own lore engine
# on a non-Saga (Myth Realized, Mind Unbound, Scroll of the Masters). phase synthesizes
# a place_counter(lore) for EVERY Saga's intrinsic advancement, so the counter-kind read
# would flood the lane with every Saga; instead anchor on the FACE oracle "lore counter"
# / "Saga you control" phrase (the reminder "(As this Saga enters … add a lore counter)"
# is stripped, so a vanilla Saga whose only lore mention is the reminder doesn't fire —
# exactly mirroring the deleted regex).
_SAGA_REF = re.compile(
    r"\blore counters?\b|\bon (?:a|target) saga you control\b", re.IGNORECASE
)
# Fight (CR 701.12) GRANTED / QUOTED / modal / symmetric phase drops: a granted
# "it fights" (Tolsimir's Wolf trigger), a quoted token "when this token enters, it
# fights" (Aggressive Biomancy, Mythos of Illuna's copy grant), a modal "Fight!"
# bullet (Magus Sisters), a DFC face (Prepare // Fight), an emblem "have it fight"
# (Kiora), or a symmetric "fight each other" (Tunnel of Love). phase emits a `fight`
# effect for a plain top-level fight; this recovers the granted/quoted/modal residual.
# Anchored on the fight VERB in its real shapes (mirrors the fight_matters regex):
# "fight(s) [up to N] [other/another] target/creature", "fight(s) it", "fight each
# other" — the verb appears only on real fight cards (the noun "fight" is rare and the
# anchor requires a fight TARGET/object).
_FIGHT_REF = re.compile(
    r"\bfights? (?:up to (?:one|two|\d+) )?(?:other |another )?target\b"
    r"|\bfights? (?:up to (?:one|two) )?(?:other )?creature"
    r"|\bfight each other\b|\bfights? it\b|\bfights? (?:another|each)\b",
    re.IGNORECASE,
)
# Creature-cast trigger (CR 601) phase drops ENTIRELY (the quoted token ability —
# Blink's "create a token with 'Whenever an opponent casts a creature spell …'" — or a
# spell's delayed trigger — Glimpse of Nature's "Whenever you cast a creature spell this
# turn, draw") survives only on the face oracle text. Anchored on the "casts a creature
# spell" / "creature spell is cast" phrase — a real creature-cast payoff (the typed
# trigger + effect-raw scan in extract_signals_ir bind what phase structured/kept).
_CREATURE_CAST_REF = re.compile(
    r"\bwhen(?:ever)? (?:you|a player|an opponent|each opponent|another player)"
    r" casts? (?:a|an|another)\b[^.]*?\bcreature spell\b"
    r"|\bwhen(?:ever)? (?:a|another) creature spell is cast\b",
    re.IGNORECASE,
)
# Regenerate (CR 701.15) GRANTED / QUOTED / replacement phase drops: a granted
# "{B}: Regenerate this creature" (quoted ability on a token / Aura / kicker-conferred
# "with 'Pay 3 life: Regenerate this creature'" — Degavolver, Anavolver, Tribal Golem,
# Skeletonize's token), or the "If this creature would be destroyed, regenerate it"
# REPLACEMENT phase drops off a creature whose other clause it parsed (Mossbridge
# Troll, Clergy / Knight of the Holy Nimbus). phase emits a `regenerate` effect for a
# plain top-level regenerate; this recovers the granted/quoted/replacement residual.
# Anchored on the "regenerate" verb (it appears only on real regenerate cards).
_REGENERATE_REF = re.compile(r"\bregenerate\b", re.IGNORECASE)
# Changeling (CR 702.73) / "is every creature type" — the all-tribes lane. phase
# rides the Scryfall `changeling` keyword for an INTRINSIC changeling, but DROPS the
# subtype on a "create a … Shapeshifter token WITH changeling" maker (the changeling
# lives in the token profile raw — Maskwood Nexus, Birthing Boughs), folds an
# "is/are every creature type" anthem/grant into a grant_keyword/pump carrier raw
# (Arachnoform, Amorphous Axe), or types the self-static as `type_set` / a place_
# counter (Mistform Ultimus, Omo's everything counter). Anchored on the literal
# "changeling" keyword OR the "(is|are|becomes) every creature type" phrase — both
# appear only on real all-tribes cards (no flavor/name collision).
_CHANGELING_REF = re.compile(
    r"\bchangeling\b|\b(?:is|are|becomes) every creature type\b", re.IGNORECASE
)
# Mass-death count operand (CR 700.4) payoff — a value/effect that SCALES with the
# number of creatures that died this turn ("a +1/+1 counter for each creature that
# died this turn", "a Treasure for each nontoken creature that died this turn",
# "connives X, where X is the number of creatures that died this turn"). phase
# parses the consequence (place_counter / make_token / connive / reanimate) but
# drops the "creatures that died this turn" operand. Anchored on the AGGREGATE
# ("for each" / "number of") shape — the board-wipe payoff the regex deliberately
# isolates — NOT the single-death conditional ("if a creature died this turn",
# morbid — Bone Picker, Tragic Slip), which is plain death_matters and would flood
# the lane. Mirrors the mass_death_payoff regex exactly (4 board-wipe commanders).
_MASS_DEATH_REF = re.compile(
    r"(?:for each|number of) (?:nontoken )?(?:creature|permanent)s?[^.]*died this turn",
    re.IGNORECASE,
)


# ── graveyard count-operand + zone recovery (ADR-0027 graveyard_matters) ───────
# A value that SCALES with the number of cards in your graveyard — Enigma Drake's
# "power equal to the number of instant and sorcery cards in your graveyard"
# (SetDynamicPower → Ref → ZoneCardCount(zone=Graveyard)), Pteramander's "{1} less
# … for each instant and sorcery card in your graveyard" (cost_reduction.count →
# Ref → ZoneCardCount), Deep-Sea Terror's threshold lhs (GraveyardSize) — is the
# strongest your-graveyard build-around (CR 400.1). phase keeps the operand in its
# raw parse (a static_abilities modification value, a cost_reduction count, a
# condition lhs), but the structured projection drops it (Enigma Drake has no
# projected abilities; Pteramander's count collapses to a Fixed adapt amount). We
# deep-scan the WHOLE phase record for a graveyard-zoned count node and, when one
# exists, append ONE marker effect carrying zones=('in:graveyard',) so the
# zone-aware graveyard_matters hook fires (mirrors the in:graveyard path the
# structured count operands already take — a count OVER cards-in-GY, scope you).


def _has_graveyard_count(node: object) -> bool:
    """True if ``node`` (any phase subtree) contains a count/size operand over a
    GRAVEYARD zone: a ZoneCardCount/ZoneCardCountAtLeast with zone='Graveyard', or a
    GraveyardSize. The discriminator vs a recursion target: this is a NUMERIC operand
    (the value scales with the GY's population), not a card pulled FROM the GY."""
    if isinstance(node, list):
        return any(_has_graveyard_count(x) for x in node)
    if not isinstance(node, dict):
        return False
    t = _norm(node.get("type"))
    # GraveyardSize ("number of cards in your graveyard") and a graveyard-zoned
    # ZoneCardCount / ZoneCardCountAtLeast (a typed/threshold GY count) are
    # unambiguously NUMERIC operands over the GY population (CR 400.1).
    if t == "graveyardsize":
        return True
    if t in ("zonecardcount", "zonecardcountatleast") and (
        _norm(node.get("zone")) == "graveyard"
    ):
        return True
    # DistinctCardTypes over a graveyard Zone ("card types among cards in all
    # graveyards" — Polygoyf): the COUNT wrapper makes the Zone a population total,
    # not a recursion source. Gated to the wrapper so a bare Zone(Graveyard) used as
    # a ChangeZone origin/filter (recursion — Reanimate, Feldon) is NOT a count.
    if t == "distinctcardtypes":
        src = node.get("source")
        if isinstance(src, dict) and _norm(src.get("zone")) == "graveyard":
            return True
    return any(_has_graveyard_count(v) for v in node.values())


def _graveyard_count_player(node: object) -> str:
    """The scope of the FIRST graveyard count operand in ``node``: 'opp' when the
    count is over an opponent's graveyard ("eight or more cards in their graveyard"
    — Anticognition: GraveyardSize.player.type == 'Opponent'), else 'you' (Controller
    / a DistinctCardTypes whose Zone carries no player defaults to your graveyard).
    Mirrors ``_has_graveyard_count``'s match set so the marker's scope tracks whose
    graveyard the build-around counts (ADR-0027 scope-split)."""
    if isinstance(node, list):
        for x in node:
            s = _graveyard_count_player(x)
            if s == "opp":
                return s
        return "you"
    if not isinstance(node, dict):
        return "you"
    t = _norm(node.get("type"))
    src = node.get("source")
    is_count = (
        t == "graveyardsize"
        or (
            t in ("zonecardcount", "zonecardcountatleast")
            and _norm(node.get("zone")) == "graveyard"
        )
        or (
            t == "distinctcardtypes"
            and isinstance(src, dict)
            and _norm(src.get("zone")) == "graveyard"
        )
    )
    if is_count:
        # GraveyardSize carries `player`; a graveyard ZoneCardCount carries `scope`
        # ('Controller'/'Opponent'). Either naming an opponent → 'opp'.
        owner = node.get("player")
        owner_t = _norm(owner.get("type")) if isinstance(owner, dict) else None
        scope = _norm(node.get("scope"))
        if owner_t == "opponent" or scope == "opponent":
            return "opp"
        return "you"
    for v in node.values():
        s = _graveyard_count_player(v)
        if s == "opp":
            return s
    return "you"


def _graveyard_count_markers(record: dict, abilities: list[Ability]) -> list[Effect]:
    """One in:graveyard count-operand marker when the record scales a value with /
    gates on the number of cards in a graveyard (graveyard count-operand, ADR-0027).
    Deep-scans the static_abilities / abilities / triggers / replacements subtrees
    for a graveyard-zoned count node phase kept in its raw but the projection dropped
    (a cost_reduction count, a ModifyCost dynamic_count, a threshold/spell-mastery
    sub_ability condition). Gated to faces with no structural in:graveyard count
    already (the projected zone-aware path is preferred; this is the raw fallback for
    the dropped-operand cards). Scope tracks whose graveyard the count is over
    (Controller → you, Opponent → opp)."""
    has_struct = any("in:graveyard" in e.zones for a in abilities for e in a.effects)
    if has_struct:
        return []
    # Deep-scan the ability containers as WHOLE subtrees: a graveyard count operand
    # rides many phase slots the structured projection drops — a cost_reduction count
    # (Pteramander), a static ModifyCost.dynamic_count (The Magic Mirror, in
    # `static_abilities[].mode.ModifyCost`), an activation_restrictions threshold
    # (Infected Vermin), a NESTED sub_ability.condition QuantityCheck (Kirtar's Wrath,
    # Cabal Ritual — the threshold "instead" sub-ability), or the effect's own amount
    # subtree (Liliana Waker). _has_graveyard_count matches ONLY a count-typed node
    # (GraveyardSize / a graveyard ZoneCardCount / a DistinctCardTypes over a
    # graveyard Zone), never a bare Zone(Graveyard) recursion origin, so scanning the
    # whole container can't mistake a Reanimate/Feldon recursion for a count.
    sources: list[object] = [
        record.get("static_abilities"),
        record.get("abilities"),
        record.get("triggers"),
        record.get("replacements"),
    ]
    if not any(_has_graveyard_count(s) for s in sources):
        return []
    # Whose graveyard the count is over decides the marker's scope (Anticognition's
    # "their graveyard" → opp = graveyard interaction; a Controller count → you).
    scope = "you"
    for s in sources:
        if _has_graveyard_count(s):
            p = _graveyard_count_player(s)
            if p == "opp":
                scope = "opp"
                break
    return [
        Effect(
            category="board_count",
            scope=scope,
            raw="count of cards in a graveyard",
            zones=("in:graveyard",),
        )
    ]


# Per-effect graveyard ZONE recovery: phase parsed the EFFECT (a bounce / cheat_play
# / topdeck_select) but lost the graveyard zone tag — a SelfRef recursion target
# ("Return this card from your graveyard to your hand" — World Breaker, zones=()),
# a hand-OR-graveyard disjunct phase collapsed to from:hand only (Dakkon's "from
# your hand or graveyard"), or a "the other into your graveyard" self-mill deposit
# phase dropped (Atris, Marchesa). We APPEND the missing zone tag from the effect's
# raw, narrowly anchored on the explicit GY-movement phrase, so the signals zone
# hooks fire. Append-only: a zone already present is untouched.
_GY_RETURN_PHRASE = re.compile(
    r"\breturn\b[^.]*\bfrom (?:your|a|an? \w+'?s?) graveyard\b[^.]*\bto\b",
    re.IGNORECASE,
)
_HAND_OR_GY_PHRASE = re.compile(
    r"\bfrom your hand (?:or|and) graveyard\b"
    r"|\bfrom (?:your )?graveyard\b[^.]*\bonto the battlefield\b",
    re.IGNORECASE,
)
_INTO_GY_DEPOSIT = re.compile(
    r"\b(?:the (?:rest|other)|all[^.]*?)\b[^.]*?\binto (?:your|a|their) graveyard\b",
    re.IGNORECASE,
)
# A card REFERENCED in/from a graveyard, surviving only in a target_only / topdeck /
# choose / bounce raw whose structured target lost the InZone:Graveyard property
# ("choose target instant or sorcery card in your graveyard" — Aberrant Mind; "put
# up to one target card from your graveyard on top of your library" — Biblioplex,
# Academy Ruins; "return … card … from your graveyard to your hand" — All Suns'
# Dawn after the Unimplemented recovery). Anchored on a CARD object "(in|from) …
# graveyard" so a "put X into your graveyard" deposit (to:graveyard, a different
# tag) or a "from the battlefield" dies-event can't match.
_GY_CARD_REFERENCE = re.compile(
    r"\bcards?\b[^.]*?\b(?:in|from)\b[^.]*?\bgraveyard\b", re.IGNORECASE
)
_GY_FROM_BATTLEFIELD = re.compile(r"\bfrom the battlefield\b", re.IGNORECASE)
# A TUTOR whose search zone INCLUDES a graveyard — "Search your graveyard, hand,
# and/or library for …" (Boonweaver Giant, Dark Supplicant), "Search target
# opponent's graveyard, hand, and library …" (Dispossess — GY hate). phase types the
# Token/CheatPlay/tutor but DROPS the graveyard disjunct from the multi-zone search,
# so from:graveyard is lost. The "your" vs "opponent's/target player's" prefix
# decides whose graveyard the search reaches (recovered as the effect's scope).
# "search your … graveyard" with the graveyard anywhere in the multi-zone list
# ("search your graveyard, hand, and/or library", "search your library and/or
# graveyard" — Raven Clan War-Axe, The First Doctor). Bounded to one clause (no
# sentence break) so a "search your library …. put into your graveyard" can't match.
_SEARCH_OWN_GY = re.compile(
    r"\bsearch your (?:[\w,/ ]*?\b(?:and/or|and|or) )?graveyard\b", re.IGNORECASE
)
_SEARCH_OPP_GY = re.compile(
    r"\bsearch (?:target )?(?:that |its )?(?:\w+ )?"
    r"(?:opponent'?s?|player'?s?|controller'?s?) "
    r"(?:[\w,/ ]*?\b(?:and/or|and|or) )?graveyard\b",
    re.IGNORECASE,
)
# A card REFERENCED in a graveyard inside a GRANT raw — "Each instant and sorcery
# card in your graveyard has flashback" (Lier), "card in your graveyard gains
# flashback" (Snapcaster), "card in your graveyard that's exactly two colors has
# jump-start" (Niv-Mizzet, Supreme). phase types these grant_keyword (or drops the
# static entirely), keeping the GY reference only in the raw — a graveyard-cast
# payoff. Anchored on the same _GY_CARD_REFERENCE so a non-GY grant can't match.


def _recover_graveyard_zones(ability: Ability) -> Ability:
    """Append a missing graveyard zone tag to an effect whose raw names a GY movement
    phase dropped (per-effect graveyard zone recovery, ADR-0027). A return-from-GY →
    in:graveyard (World Breaker, Grim Captain's Call SelfRef forms); a hand-or-GY /
    GY-onto-battlefield cheat → from:graveyard (Dakkon); a deposit "the other into
    your graveyard" → to:graveyard (Atris, Marchesa); a card REFERENCED in/from a
    graveyard whose target lost the InZone (Aberrant Mind, Biblioplex, All Suns'
    Dawn) or a GY-wide cast-keyword GRANT (Lier, Snapcaster, Niv-Mizzet) becomes
    in:graveyard; a multi-zone TUTOR whose graveyard disjunct phase dropped becomes
    from:graveyard (Boonweaver scope you, Dispossess scope opp). Append-only (a
    tutor's scope is also recovered when its search reaches a graveyard)."""
    new_effects: list[Effect] = []
    changed = False
    for e in ability.effects:
        raw = e.raw or ""
        zones = set(e.zones)
        before = set(zones)
        before_scope = e.scope
        scope = e.scope
        if (
            e.category in ("bounce", "reanimate", "cast_from_zone", "blink")
            and "in:graveyard" not in zones
            and "from:battlefield" not in zones
            and _GY_RETURN_PHRASE.search(raw)
        ):
            zones.add("in:graveyard")
        # A card referenced IN/FROM a graveyard in a target_only / topdeck_stack /
        # choose / make_token / bounce / grant_keyword raw — graveyard
        # recursion / selection / cast-grant whose InZone target the structured
        # projection dropped. grant_keyword covers a GY-wide cast-keyword grant
        # ("Each instant and sorcery card in your graveyard has flashback" — Lier;
        # "card in your graveyard gains flashback" — Snapcaster; jump-start —
        # Niv-Mizzet, Supreme). Excludes a deposit (no to:/in: added when the only GY
        # mention is "into … graveyard") and a from:battlefield dies-event.
        if (
            e.category
            in (
                "target_only",
                "topdeck_stack",
                "choose",
                "make_token",
                "bounce",
                "grant_keyword",
            )
            and "in:graveyard" not in zones
            and "to:graveyard" not in zones
            and not _GY_FROM_BATTLEFIELD.search(raw)
            and _GY_CARD_REFERENCE.search(raw)
        ):
            zones.add("in:graveyard")
        # A TUTOR whose multi-zone search reaches a graveyard (the GY disjunct phase
        # dropped). "search your graveyard …" → from:graveyard, scope you (the search
        # recovers YOUR graveyard — Boonweaver, Dark Supplicant); "search … an
        # opponent's graveyard …" → from:graveyard, scope opp (graveyard hate —
        # Dispossess, Unmoored Ego). The tutor doer lane uses a fixed scope, so the
        # scope override only steers the graveyard hook (ADR-0027 scope-split).
        if (
            e.category == "tutor"
            and "from:graveyard" not in zones
            and not _GY_FROM_BATTLEFIELD.search(raw)
        ):
            if _SEARCH_OWN_GY.search(raw):
                zones.add("from:graveyard")
                scope = "you"
            elif _SEARCH_OPP_GY.search(raw):
                zones.add("from:graveyard")
                scope = "opp"
        if (
            e.category in ("cheat_play", "reanimate")
            and "from:graveyard" not in zones
            and _HAND_OR_GY_PHRASE.search(raw)
        ):
            zones.add("from:graveyard")
        if (
            e.category in ("topdeck_select", "reveal", "mill", "discard", "dig_until")
            and "to:graveyard" not in zones
            and "from:battlefield" not in zones
            and _INTO_GY_DEPOSIT.search(raw)
        ):
            zones.add("to:graveyard")
        if zones != before or scope != before_scope:
            changed = True
            new_effects.append(replace(e, zones=tuple(sorted(zones)), scope=scope))
        else:
            new_effects.append(e)
    if not changed:
        return ability
    return replace(ability, effects=tuple(new_effects))


# Library-source recovery (ADR-0027 impulse_top_play / play_from_top) — a
# `cast_from_zone` effect whose raw plays/casts FROM THE TOP OF A LIBRARY but whose
# `from:library` zone phase did not populate on the origin field. Two shapes: an
# impulse exile-then-play ("exile the top N cards of your library … you may play/cast
# them" — Light Up the Stage, Ragavan) and an ongoing top-play permission ("you may
# play lands/cards from the top of your library", "play with the top card of your
# library revealed" — Future Sight, Bolas's Citadel, Vizier of the Menagerie). Gated
# on category=='cast_from_zone' (phase already classified it a from-zone cast) so the
# library reference can't false-fire on a scry / surveil / topdeck_select. Append-only
# and behavior-neutral until a lane reads from:library (impulse_top_play /
# play_from_top); no existing migrated key consumes it. CR 116 / 601.3b.
_LIBRARY_CAST_REF = re.compile(
    r"top (?:card|cards|\w+ cards?) of (?:your|their|his or her|that player's) "
    r"library"
    r"|from the top of (?:your|their) library"
    r"|play with the top card of (?:your|their) library",
    re.IGNORECASE,
)


def _recover_library_zones(ability: Ability) -> Ability:
    """Append from:library to a cast_from_zone effect whose raw plays from the top of
    a library but lost the origin zone (impulse exile-cast + ongoing top-play)."""
    new_effects: list[Effect] = []
    changed = False
    for e in ability.effects:
        if (
            e.category == "cast_from_zone"
            and "from:library" not in e.zones
            and _LIBRARY_CAST_REF.search(e.raw or "")
        ):
            changed = True
            new_effects.append(
                replace(e, zones=tuple(sorted(set(e.zones) | {"from:library"})))
            )
        else:
            new_effects.append(e)
    if not changed:
        return ability
    return replace(ability, effects=tuple(new_effects))


# Edict-scope recovery (ADR-0027 edict_matters) — a `sacrifice` effect whose
# SACRIFICER scope phase dropped to "any" because the structural target.controller
# was null (an Or-of-Typed filter with the player scoping lost — Plaguecrafter,
# Fleshbag Marauder, Barter in Blood). The raw still names who sacrifices: "each
# player sacrifices" → scope each (a symmetric edict, the deck still runs it as an
# edict — it was in the regex hit set), and "(each|target|an|that) opponent / target
# player sacrifices" → scope opp (a one-sided edict). A YOU-sacrifice ("you
# sacrifice") is NOT promoted (it stays a you-sac, scope any — sacrifice_matters, not
# edict). Gated on scope=='any' so a structural opp/each from _sacrifice_player_scope
# is never overwritten. CR 701.16 / 601.
_EDICT_EACH_RAW = re.compile(
    r"\beach player sacrifices?\b|\ball players sacrifice\b", re.IGNORECASE
)
_EDICT_OPP_RAW = re.compile(
    r"\b(?:each|target|an|that) opponent(?:'s)? sacrifices?\b"
    r"|\btarget player sacrifices?\b",
    re.IGNORECASE,
)


def _recover_edict_scope(ability: Ability) -> Ability:
    """Promote a scope=='any' sacrifice effect to each/opp from its raw when the
    structural sacrificer-controller was null (edict whose player scoping phase
    dropped)."""
    new_effects: list[Effect] = []
    changed = False
    for e in ability.effects:
        if e.category == "sacrifice" and e.scope == "any":
            raw = e.raw or ""
            if _EDICT_OPP_RAW.search(raw):
                changed = True
                new_effects.append(replace(e, scope="opp"))
                continue
            if _EDICT_EACH_RAW.search(raw):
                changed = True
                new_effects.append(replace(e, scope="each"))
                continue
        new_effects.append(e)
    if not changed:
        return ability
    return replace(ability, effects=tuple(new_effects))


# Removal target-subject recovery (ADR-0027 removal_matters shape 3) — a damage /
# destroy effect whose creature/permanent TARGET phase dropped to subject=None, the
# target surviving only in the effect raw. Three lossy shapes: a power-scaled fight
# ("deals damage equal to its power to target creature" — Crush Underfoot), a
# predicate-narrowed destroy ("destroy target blocked/attacking creature" — Smite,
# Broken Visage; phase emits Typed with empty type_filters), and a "destroy target
# <Subtype>" the projection didn't bind. The raw must name a CREATURE/PERMANENT
# target; a player/PW-only burn, an "any target", a "divided among targets" split,
# a board wipe ("destroy all/each"), and a land target are all EXCLUDED (they are
# direct_damage / board_wipe / land_destruction, not single-target removal).
_REMOVAL_DAMAGE_TARGET = re.compile(
    r"(?:deals?|dealt|deal) [^.]*?\bto target (?:[a-z]+ )*?"
    r"(?:creature|permanent)\b",
    re.IGNORECASE,
)
_REMOVAL_DESTROY_TARGET = re.compile(
    r"\bdestroy (?:up to (?:one|two|three|x) )?target (?:[a-z]+ )*?"
    r"(?:creature|permanent|artifact|enchantment|planeswalker|wall)\b",
    re.IGNORECASE,
)
# Land target / board-wipe exclusions — these route to land_destruction / board_wipe.
_REMOVAL_LAND_TARGET = re.compile(r"\btarget (?:non-?\w+ )?land\b", re.IGNORECASE)
_REMOVAL_MASS = re.compile(r"\bdestroy (?:all|each)\b", re.IGNORECASE)


def _recover_removal_target_subject(ability: Ability) -> Ability:
    """Rebuild a Creature/Permanent Filter on a damage / destroy effect whose target
    phase dropped to subject=None but whose raw still names a creature/permanent
    target (ADR-0027 removal_matters shape 3). Append-only on subject: a structured
    subject is never overwritten; a player/PW/land/any-target/board-wipe raw is left
    untouched (those are not single-target permanent removal)."""
    new_effects: list[Effect] = []
    changed = False
    for e in ability.effects:
        raw = e.raw or ""
        if (
            e.subject is None
            and e.category in ("damage", "destroy")
            and not _REMOVAL_LAND_TARGET.search(raw)
            and not _REMOVAL_MASS.search(raw)
            and (
                (e.category == "damage" and _REMOVAL_DAMAGE_TARGET.search(raw))
                or (e.category == "destroy" and _REMOVAL_DESTROY_TARGET.search(raw))
            )
        ):
            subj = (
                Filter(card_types=("Creature",))
                if "creature" in raw.lower()
                else (Filter(card_types=("Permanent",)))
            )
            new_effects.append(replace(e, subject=subj))
            changed = True
        else:
            new_effects.append(e)
    if not changed:
        return ability
    return replace(ability, effects=tuple(new_effects))


# Graveyard-cast GRANT marker (ADR-0027): a card that LETS YOU cast spells from your
# graveyard via an emblem / quoted-static GRANT — Jaya Ballard's "[-8]: You get an
# emblem with 'You may cast instant and sorcery spells from your graveyard'" — parses
# as category='emblem' with the GY-cast permission only in its raw. The keyworded
# self-cast (flashback/escape) rides castable_zones; a structured CastFromZone fires
# directly; this is the emblem/grant residual. Anchored on "cast … from your/a
# graveyard" so a reminder-text mention can't false-fire.
_GRAVEYARD_CAST_GRANT = re.compile(
    r"\bcast\b[^.\"]*\bfrom (?:your|a) graveyard\b", re.IGNORECASE
)
# A GY-WIDE cast-keyword grant whose static phase DROPPED entirely (no carrier
# effect to attach a zone to): "Each nonland card in your graveyard has escape"
# (Underworld Breach), "Each creature card in your graveyard has scavenge" (Varolz),
# "has unearth" (Dregscape Sliver). Each of these keywords (CR 702.x) lets you cast /
# play the card from the graveyard, so the card is a graveyard-cast payoff. Anchored
# on a GY card reference + a known graveyard-castable keyword.
_GY_WIDE_CAST_GRANT = re.compile(
    r"cards? in your graveyard (?:ha(?:s|ve)|gains?) (?:[^.]*\b)?"
    r"(?:flashback|escape|jump-?start|retrace|encore|disturb|unearth|scavenge"
    r"|embalm|eternalize|aftermath)\b",
    re.IGNORECASE,
)


def _graveyard_cast_grant_markers(
    record: dict, abilities: list[Ability]
) -> list[Effect]:
    """One cast_from_zone marker when an emblem / grant raw lets you cast from a
    graveyard but no structural cast_from_zone already fires (graveyard-cast grant,
    ADR-0027). Gated to faces with no structural cast_from_zone (the structured path
    is preferred). Scans the emblem/grant carrier raws on the face."""
    has_struct = any(
        e.category == "cast_from_zone" for a in abilities for e in a.effects
    )
    if has_struct:
        return []
    for a in abilities:
        for e in a.effects:
            if e.category in ("emblem", "grant_keyword", "static", "other") and (
                _GRAVEYARD_CAST_GRANT.search(e.raw or "")
            ):
                return [
                    Effect(
                        category="cast_from_zone",
                        scope="you",
                        raw=e.raw,
                        zones=("from:graveyard",),
                    )
                ]
    # Face oracle fallback: a graveyard-cast permission STATIC phase dropped entirely
    # (Danitha's "you may cast an Aura or Equipment spell from your graveyard" — its
    # static_abilities row recovers no recognized mode, so no carrier raw exists).
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    if (m := _GRAVEYARD_CAST_GRANT.search(text)) is not None:
        return [
            Effect(
                category="cast_from_zone",
                scope="you",
                raw=m.group(0),
                zones=("from:graveyard",),
            )
        ]
    # GY-WIDE cast-keyword grant whose static phase dropped entirely (no carrier
    # effect, and the grant_keyword zone-recovery couldn't attach in:graveyard) —
    # Underworld Breach, Varolz, Dregscape Sliver. Gated to faces with no recovered
    # in:graveyard reference so a Lier/Snapcaster (whose grant_keyword already carries
    # in:graveyard) doesn't also emit a redundant marker.
    has_ingy = any("in:graveyard" in e.zones for a in abilities for e in a.effects)
    if not has_ingy and (m := _GY_WIDE_CAST_GRANT.search(text)) is not None:
        return [
            Effect(
                category="cast_from_zone",
                scope="you",
                raw=m.group(0),
                zones=("from:graveyard",),
            )
        ]
    return []


def _additional_cost_data(record: dict) -> dict | None:
    """The inner data of a record's ``additional_cost`` (phase wraps it as
    ``{type: Required/Optional, data: {...}}``; some records inline it). None when
    absent or malformed."""
    ac = record.get("additional_cost")
    if not isinstance(ac, dict):
        return None
    data = ac.get("data")
    return data if isinstance(data, dict) else ac


def _nonland_sacrifice_target(node: object) -> Filter | None | bool:
    """Find a Sacrifice cost's non-land sacrificed-object Filter anywhere under
    ``node`` (an ``additional_cost`` subtree — phase wraps a sac additional cost as a
    bare Sacrifice, or nests it inside a Choice list / Kicker ``costs`` — Bone Shards,
    Spark Harvest, Final Payment, Vicious Offering). Returns the first matching
    Sacrifice's target Filter (None when it has no typed filter, i.e. "sacrifice a
    permanent"); returns False when no non-land Sacrifice exists. A land-ONLY sac
    target (Crop Rotation, Harrow) is skipped — that is the land_sacrifice lane."""
    if isinstance(node, list):
        for x in node:
            r = _nonland_sacrifice_target(x)
            if r is not False:
                return r
        return False
    if not isinstance(node, dict):
        return False
    if _norm(node.get("type")) == "sacrifice":
        subject = _filter(node.get("target"))
        if subject is None or subject.card_types != ("Land",):
            return subject
        return False
    for v in node.values():
        r = _nonland_sacrifice_target(v)
        if r is not False:
            return r
    return False


def _sacrifice_cost_markers(record: dict, abilities: list[Ability]) -> list[Effect]:
    """One you-sacrifice marker when the card's ``additional_cost`` carries a non-land
    Sacrifice phase kept in the record but dropped off the projected spell — a bare
    additional-cost sac (Altar's Reap, Fling, Bone Splinters), a Choice that includes
    a sac (Bone Shards "sacrifice a creature or discard", Spark Harvest, Final
    Payment), or a Kicker sac (Vicious Offering). Projects the sacrificed object's
    Filter as the subject so the lane's land VETO + scope read it identically to a
    structural sacrifice Effect. The land-ONLY form (Crop Rotation, Harrow) is the
    land_sacrifice lane and is excluded. Skipped when a structural sacrifice Effect
    already exists. ADR-0027 sacrifice_matters shape 2."""
    if any(e.category == "sacrifice" for a in abilities for e in a.effects):
        return []
    subject = _nonland_sacrifice_target(record.get("additional_cost"))
    if subject is False:
        return []
    # A bare "sacrifice a permanent" with no typed filter still wants a concrete
    # non-land subject so the signals land-ONLY veto reads it as a real sac outlet.
    if not isinstance(subject, Filter):
        subject = Filter(card_types=("Permanent",), controller="you")
    return [
        Effect(
            category="sacrifice",
            scope="you",
            subject=subject,
            raw="additional cost: sacrifice a permanent",
        )
    ]


# Artifact/Enchantment card-types whose typed sacrifice ACTIVATION cost opens the
# matching matters lane (ADR-0027 cost-payer). Other typed sac costs (creature,
# permanent, land) are read by the existing sacrifice/land-sac lanes off the cost
# token, so only these two need the type recovered.
_COST_PAYER_TYPES = frozenset({"Artifact", "Enchantment"})


def _typed_sacrifice_cost_markers(record: dict) -> list[Effect]:
    """One sacrifice marker per ABILITY whose activation cost sacrifices an
    Artifact / Enchantment ("Sacrifice an artifact: …" — Atog, Krark-Clan Ironworks;
    "Sacrifice an enchantment: …"). phase keeps the activated ability but collapses the
    cost to a bare ``sacrifice`` token, dropping the sacrificed object's TYPE — so the
    artifacts/enchantments cost-payer lane has no tell (sacrifice_matters still fires
    off the cost token). Surfaces the sacrificed Filter as a marker subject so the
    artifacts/enchantments sac-payoff arm reads it. ADR-0027 cost-payer shape."""
    markers: list[Effect] = []
    seen: set[tuple[str, ...]] = set()
    for ab in record.get("abilities") or []:
        subject = _typed_sacrifice_cost_target(ab.get("cost"))
        if subject is None:
            continue
        key = subject.card_types
        if key in seen:
            continue
        seen.add(key)
        markers.append(
            Effect(
                category="sacrifice",
                scope="you",
                subject=subject,
                raw=f"cost: sacrifice {' or '.join(subject.card_types).lower()}",
            )
        )
    return markers


def _typed_sacrifice_cost_target(node: object) -> Filter | None:
    """The Filter of an Artifact/Enchantment Sacrifice cost anywhere under ``node`` (an
    activation ``cost`` subtree). None when there is no such typed Sacrifice cost — a
    bare/SelfRef sac, a land/creature/permanent sac, or no sac at all."""
    if isinstance(node, list):
        for x in node:
            r = _typed_sacrifice_cost_target(x)
            if r is not None:
                return r
        return None
    if not isinstance(node, dict):
        return None
    if _norm(node.get("type")) == "sacrifice":
        subject = _filter(node.get("target"))
        if subject is not None and (set(subject.card_types) & _COST_PAYER_TYPES):
            return subject
    for v in node.values():
        r = _typed_sacrifice_cost_target(v)
        if r is not None:
            return r
    return None


# "becomes a/an artifact|enchantment" — a TYPE-GRANT (animate / grant the type) whose
# granted card-type phase drops to a subject=None base_pt_set/animate/state. Anchored
# on "becomes" + the type so a token "create a token that's an artifact" (a maker, not
# a grant) and a clone "becomes a copy of" never match.
_BECOMES_TYPE_RE = re.compile(
    r"becomes? (?:a|an) (?:\w+ )*?(artifact|enchantment)\b", re.IGNORECASE
)


def _becomes_type_markers(abilities: list[Ability]) -> list[Effect]:
    """One becomes_type marker per distinct Artifact/Enchantment a "becomes a/an
    <type>" type-grant confers (Sydri, Karn's Touch, Argent Mutation, Titania's Song).
    Read off the projected effect raws (the type survives there after phase drops it to
    a subject=None base_pt_set/animate/state). Skipped when a structural make_token or
    clone already carries the type (a token maker / copy is not a type-grant)."""
    markers: list[Effect] = []
    seen: set[str] = set()
    for ab in abilities:
        for e in ab.effects:
            if e.category in ("make_token", "clone"):
                continue
            m = _BECOMES_TYPE_RE.search(e.raw or "")
            if not m:
                continue
            ctype = m.group(1).capitalize()
            if ctype in seen:
                continue
            seen.add(ctype)
            markers.append(
                Effect(
                    category="becomes_type",
                    scope="you",
                    subject=Filter(card_types=(ctype,), controller="you"),
                    raw=f"grant: becomes a {ctype.lower()}",
                )
            )
    return markers


# Sac-outlet shapes phase keeps only in an opaque raw / drops to a body effect
# (granted/quoted sac outlets, casualty grants, free-spell pitch, graveyard-cast and
# morph sac costs — ADR-0027 sacrifice_matters shapes 4-5). Each anchors on a NON-land
# sacrificed object: the lazy ``[^.]*?`` between the count and the type lets an
# adjective ("three black creatures") through while ``_SAC_TYPE`` excludes a bare
# "sacrifice a land" (Brutal Suppression) and a land-fetch alt cost.
_SAC_COUNT = r"(?:a|an|another|two|three|any number of|x|\d+)"
_SAC_TYPE = r"(?:creature|artifact|permanent|enchantment|token|planeswalker)"
# A granted / quoted sac outlet ("…has \"Sacrifice a creature: …\"" — Fallen Ideal,
# Animal Boneyard, Lunarch Mantle, Ob Nixilis's emblem; Custody Battle's granted
# upkeep edict-on-self). Anchored inside quotes.
_GRANTED_SAC = re.compile(
    rf'"[^"]*\bsacrifice {_SAC_COUNT}\b[^".]*?{_SAC_TYPE}',
    re.IGNORECASE,
)
# A free-spell pitch ("you may sacrifice three black creatures rather than pay this
# spell's mana cost" — Flare of Denial, Salvage Titan, Delraich, Demon of Death's
# Gate, Dark Triumph). CR 118.9.
_PITCH_SAC = re.compile(
    rf"sacrifice {_SAC_COUNT}\b[^.]*?{_SAC_TYPE}[^.]*\brather than pay\b",
    re.IGNORECASE,
)
# A keyworded cost paid in a non-land sacrifice phase drops with the keyword cost:
# graveyard-cast ("Flashback—Sacrifice three creatures" — Dread Return; Cabal
# Therapy's flashback sac) and a morph turn-up ("Morph—Sacrifice another creature" —
# Gift of Doom). CR 702.34 / 702.37.
_KEYWORD_COST_SAC = re.compile(
    rf"(?:flashback|escape|buyback|morph|megamorph|disturb|embalm)\b[^.]*\bsacrifice "
    rf"{_SAC_COUNT}\b[^.]*?{_SAC_TYPE}",
    re.IGNORECASE,
)
# A GRANT that confers the Casualty keyword ("has casualty N" — Anhelo, Silverquill,
# Ashad). The card's own printed Casualty rides the Scryfall keyword array; this is
# the keyword-LESS granter. CR 702.153.
_CASUALTY_GRANT = re.compile(r"\bhas casualty\b", re.IGNORECASE)
# A pay-or-die outlet ("counter that spell / deals N damage to you / exile it / tap
# this creature / discard a card UNLESS you sacrifice a creature" — Blood Funnel,
# Minion of Leshrac, Demonlord of Ashmouth, Apocalypse Demon, Read the Runes) where
# phase parsed only the penalty effect (counter/damage/exile/draw) and dropped the
# you-sac alternative. The "you sacrifice" anchor keeps a forced opponent/each-player
# sac out (their controller IS not "you").
_PAY_OR_DIE_SAC = re.compile(
    rf"\bunless you (?:may )?sacrifice {_SAC_COUNT}\b[^.]*?{_SAC_TYPE}",
    re.IGNORECASE,
)
# A "discard a card AND sacrifice a creature" additional cost phase clipped to the
# discard half (Ruthless Disposal — additional_cost keeps only Discard).
_DISCARD_AND_SAC = re.compile(
    rf"\bdiscard a card and sacrifice {_SAC_COUNT}\b[^.]*?{_SAC_TYPE}",
    re.IGNORECASE,
)
# A modal-bullet sac option phase did not expand into the `choose` carrier ("choose
# one — • Sacrifice an artifact: …" — Gearbane Orangutan, Plunge into Darkness,
# Lorehold Command, Grab the Reins).
_BULLET_SAC = re.compile(
    rf"•\s*sacrifice {_SAC_COUNT}\b[^.•]*?{_SAC_TYPE}",
    re.IGNORECASE,
)
# A cumulative-upkeep sac cost phase parsed as a SelfRef "sacrifice it" (Phyrexian
# Soulgorger — "Cumulative upkeep—Sacrifice a creature"). CR 702.24.
_CUMULATIVE_UPKEEP_SAC = re.compile(
    rf"cumulative upkeep\s*[—-]\s*sacrifice {_SAC_COUNT}\b[^.]*?{_SAC_TYPE}",
    re.IGNORECASE,
)


def _sacrifice_grant_markers(record: dict, abilities: list[Ability]) -> list[Effect]:
    """One you-sacrifice marker when a sac OUTLET survives only in an opaque raw or
    phase dropped it to a body effect (granted/quoted sac outlet, casualty grant,
    free-spell pitch, keyworded-cost sac, pay-or-die alternative, clipped discard+sac
    additional cost — ADR-0027 sacrifice_matters shapes 4-5). Gated to faces with no
    structural sacrifice effect (the structured path and the additional-cost marker
    are preferred). The subject is a generic Permanent so the signals land-ONLY veto
    passes (all anchors require a non-land sac target)."""
    if any(e.category == "sacrifice" for a in abilities for e in a.effects):
        return []
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    if (
        _GRANTED_SAC.search(text)
        or _PITCH_SAC.search(text)
        or _KEYWORD_COST_SAC.search(text)
        or _CASUALTY_GRANT.search(text)
        or _PAY_OR_DIE_SAC.search(text)
        or _DISCARD_AND_SAC.search(text)
        or _BULLET_SAC.search(text)
        or _CUMULATIVE_UPKEEP_SAC.search(text)
    ):
        return [
            Effect(
                category="sacrifice",
                scope="you",
                subject=Filter(card_types=("Permanent",), controller="you"),
                raw="granted/dropped sacrifice outlet",
            )
        ]
    return []


# Life-loss shapes phase keeps in the record / collapses to a non-lose_life node
# (ADR-0027 lifeloss_matters shape 4). The SELF half (→ lose_life scope you): a
# pay-life additional cost (PayLife in additional_cost — Bitter Triumph, Final
# Payment), a free-spell pitch ("pay N life rather than pay" — Contagion, K'rrik), a
# keyworded-cost pay-life (Flashback/Escape/Blitz/Morph/Warp—Pay N life — Deep
# Analysis, Tenacious Underdog), a "you may pay N life. If you do" value engine
# (Arrogant Poet, Seymour Flux), a cumulative-upkeep pay-life (Inner Sanctum,
# Gallowbraid), a "tap this unless you pay N life" / "unless you pay N life" upkeep
# tax (Carnophage), a Defiler-style static additional cost ("as an additional cost
# to cast … you may pay 2 life"), a quoted granted "you lose N life", and a modal "•
# … you lose N life". The DRAIN half (→ lose_life scope opp): a modal-bullet opponent
# drain (Inquisitor Exarch), a quoted granted "target player loses N life" (Caustic
# Tar, Claim of Erebos), and a "lost life this turn" past-tense payoff (Rakdos, Sygg).
_LIFE = r"(?:\d+|x|that much|half)"
_PITCH_PAY_LIFE = re.compile(
    r"\bpay (?:\d+|x) life\b[^.]*\brather than pay\b", re.IGNORECASE
)
_KEYWORD_COST_PAY_LIFE = re.compile(
    r"\b(?:flashback|escape|blitz|morph|megamorph|disturb|warp|buyback|embalm"
    r"|unearth|recover|aftermath)\b[^.]*\bpay \d+ life\b",
    re.IGNORECASE,
)
_MAY_PAY_LIFE = re.compile(
    r"\byou may pay (?:\d+|x) life\b[\s.,]*?\b(?:if you do|when you do|where x is)\b"
    r"|\bwhenever you (?:gain or lose|lose or gain) life\b",
    re.IGNORECASE,
)
_CUMULATIVE_UPKEEP_LIFE = re.compile(
    r"cumulative upkeep\s*[—-]\s*pay \d+ life", re.IGNORECASE
)
_TAX_PAY_LIFE = re.compile(r"\bunless you pay \d+ life\b", re.IGNORECASE)
_DEFILER_PAY_LIFE = re.compile(
    r"as an additional cost to cast[^.]*\byou may pay \d+ life\b", re.IGNORECASE
)
_GRANTED_SELF_LOSS = re.compile(rf'"[^"]*\byou lose {_LIFE}[^"]*\blife', re.IGNORECASE)
_MODAL_SELF_LOSS = re.compile(rf"•[^•]*?\byou lose {_LIFE}[^•.]*?\blife", re.IGNORECASE)
_DRAIN_PARTY = (
    r"(?:each opponent|target opponent|target player|each player|that player"
    r"|an opponent|opponents?|a player)"
)
_MODAL_DRAIN = re.compile(
    rf"•[^•]*?\b{_DRAIN_PARTY}\b[^•.]*?\bloses? {_LIFE}[^•.]*?\blife", re.IGNORECASE
)
_GRANTED_DRAIN = re.compile(
    rf'"[^"]*\b{_DRAIN_PARTY}\b[^"]*\bloses? {_LIFE}[^"]*\blife', re.IGNORECASE
)
# A past-tense "lost life this turn" payoff — the card CARES that a player lost life
# (Rakdos, Sygg, Belbe), the cares-about half of the lane.
_LOST_LIFE_TURN = re.compile(
    r"\blost (?:\d+ or more |\d+ )?life this turn\b"
    r"|\blife [^.]*\blost this turn\b",
    re.IGNORECASE,
)
# A die-roll result row that costs you life ("1—9 | You draw a card and you lose 1
# life" — Nothic, Treasure Chest's "Trapped! — You lose 3 life") or drains opponents
# ("1—9 | Each opponent loses 2 life" — Herald of Hadar) phase keeps in a d20-table
# raw the projection drops. The "N |" / "N—M |" row marker anchors it.
_DICE_SELF_LOSS = re.compile(r"\d+\s*[|—-][^|]*?\byou lose \d+ life", re.IGNORECASE)
_DICE_DRAIN = re.compile(
    rf"\d+\s*[|—-][^|]*?\b{_DRAIN_PARTY}\b[^|]*?\bloses? \d+ life", re.IGNORECASE
)
# A "choose one … you lose N life" modal where the self-loss mode rides a non-bullet
# choose list (Zuko, Promise of Power, Gruesome Realization).
_CHOOSE_SELF_LOSS = re.compile(
    r"\bchoose (?:one|two|any number)[^.]*?\byou lose \d+ life", re.IGNORECASE
)


def _has_paylife_additional_cost(record: dict) -> bool:
    """True if the record's ``additional_cost`` contains a PayLife (a bare cost or
    one nested in a Choice — Bitter Triumph "discard a card or pay 3 life", Final
    Payment "pay 5 life or sacrifice a creature")."""
    found = [False]

    def walk(n: object) -> None:
        if isinstance(n, dict):
            if _norm(n.get("type")) == "paylife":
                found[0] = True
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(record.get("additional_cost"))
    return found[0]


_LIFELOSS_SELF_PATTERNS = (
    _PITCH_PAY_LIFE,
    _KEYWORD_COST_PAY_LIFE,
    _MAY_PAY_LIFE,
    _CUMULATIVE_UPKEEP_LIFE,
    _TAX_PAY_LIFE,
    _DEFILER_PAY_LIFE,
    _GRANTED_SELF_LOSS,
    _MODAL_SELF_LOSS,
    _DICE_SELF_LOSS,
    _CHOOSE_SELF_LOSS,
)
_LIFELOSS_DRAIN_PATTERNS = (
    _MODAL_DRAIN,
    _GRANTED_DRAIN,
    _LOST_LIFE_TURN,
    _DICE_DRAIN,
)


def _lifeloss_markers(record: dict, abilities: list[Ability]) -> list[Effect]:
    """lose_life markers for life-loss phase kept in the record but dropped off the
    projection (ADR-0027 lifeloss_matters shape 4). A SELF life-loss (a pay-life
    additional cost, a free-spell pitch, a keyworded-cost / cumulative-upkeep / tax /
    Defiler pay-life, a granted or modal "you lose N life") → a `lose_life` scope=you
    marker; a DRAIN (a modal-bullet / quoted-granted opponent loss, a "lost life this
    turn" payoff) → a scope=opp marker. Gated to faces with no structural lose_life. A
    Land card is excluded (the lane's pay-life mana-source VETO)."""
    if "Land" in _type_line(record.get("card_type")):
        return []
    if any(e.category == "lose_life" for a in abilities for e in a.effects):
        return []
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    out: list[Effect] = []
    if _has_paylife_additional_cost(record) or any(
        p.search(text) for p in _LIFELOSS_SELF_PATTERNS
    ):
        out.append(
            Effect(category="lose_life", scope="you", raw="pay-life cost / self loss")
        )
    if any(p.search(text) for p in _LIFELOSS_DRAIN_PATTERNS):
        out.append(
            Effect(category="lose_life", scope="opp", raw="opponents drain / payoff")
        )
    return out


def _dropped_static_markers(record: dict, abilities: list[Ability]) -> list[Effect]:
    """Markers for named-mechanic statics/replacements phase dropped from the parse
    entirely, surviving only on the face oracle text (dropped-static face markers,
    ADR-0027). Returned as effects for one synthesized static ability; empty when
    none match. trigger_doubling is gated to faces lacking a structural one."""
    text = re.sub(r"\([^)]*\)", " ", record.get("oracle_text") or "")
    markers: list[Effect] = []
    if (m := _BOAST_GRANT.search(text)) is not None:
        markers.append(Effect(category="boast", scope="you", raw=m.group(0)))
    has_struct_td = any(
        e.category == "trigger_doubling" for a in abilities for e in a.effects
    )
    if not has_struct_td and (m := _TRIGGER_DOUBLING_GRANT.search(text)) is not None:
        markers.append(Effect(category="trigger_doubling", scope="you", raw=m.group(0)))
    has_struct_dd = any(
        e.category == "damage_doubling" for a in abilities for e in a.effects
    )
    if not has_struct_dd and (m := _DAMAGE_DOUBLING_REF.search(text)) is not None:
        markers.append(Effect(category="damage_doubling", scope="you", raw=m.group(0)))
    if (m := _SCAVENGE_GRANT.search(text)) is not None:
        markers.append(Effect(category="scavenge", scope="you", raw=m.group(0)))
    if (m := _SCRY_REPLACEMENT.search(text)) is not None:
        markers.append(Effect(category="scry_surveil", scope="you", raw=m.group(0)))
    if (m := _EXTRA_END_GRANT.search(text)) is not None:
        markers.append(Effect(category="extra_end", scope="you", raw=m.group(0)))
    # "Additional beginning phase" → an extra upkeep AND an extra draw step (CR
    # 501.1). Gated to faces with no structural extra_upkeep/extra_draw (phase emits
    # neither today — it mis-routes these to extra_combats — so this is the sole
    # producer, but the gate keeps it append-only if phase ever grows the category).
    if (m := _EXTRA_BEGINNING_PHASE_GRANT.search(text)) is not None:
        have = {e.category for a in abilities for e in a.effects}
        raw = m.group(0)
        if "extra_upkeep" not in have:
            markers.append(Effect(category="extra_upkeep", scope="you", raw=raw))
        if "extra_draw" not in have:
            markers.append(Effect(category="extra_draw", scope="you", raw=raw))
    # "Counter target … spell/ability" phase lost in a modal/Aura/coin_flip carrier
    # → a counter_spell marker, gated to faces with no structural counter_spell.
    has_counter = any(
        e.category == "counter_spell" for a in abilities for e in a.effects
    )
    if not has_counter and (m := _COUNTER_TARGET_REF.search(text)) is not None:
        markers.append(Effect(category="counter_spell", scope="any", raw=m.group(0)))
    # Spell-copy GRANTED / QUOTED / CONDITIONAL ("copy that/it/this spell|card", "copy
    # it for each spell cast") phase lost in a modal / granted / coin-flip / storm-
    # reminder carrier → a spell_copy marker, gated to faces with no structural
    # spell_copy. The CopySpell effect + storm/replicate/conspire keywords cover the
    # rest; the "copy of <creature>" clone form is excluded by the spell|card anchor.
    has_spell_copy = any(
        e.category == "spell_copy" for a in abilities for e in a.effects
    )
    if not has_spell_copy and (m := _COPY_SPELL_REF.search(text)) is not None:
        markers.append(Effect(category="spell_copy", scope="you", raw=m.group(0)))
    # "Life total becomes <X>" / "double … life total" phase mis-tagged or dropped →
    # a set_life marker, gated to faces with no structural set_life effect.
    has_set_life = any(e.category == "set_life" for a in abilities for e in a.effects)
    if not has_set_life and (m := _LIFE_TOTAL_SET.search(text)) is not None:
        markers.append(Effect(category="set_life", scope="any", raw=m.group(0)))
    # Force-a-block (lure) phase swallowed into a compound pump/grant clause or
    # dropped, gated to faces with no structural lure effect.
    has_lure = any(e.category == "lure" for a in abilities for e in a.effects)
    if not has_lure:
        m = _LURE_ABLE.search(text) or _LURE_MUST.search(text)
        if m is not None:
            markers.append(Effect(category="lure", scope="you", raw=m.group(0)))
    # Forced-attack SELF/TEAM static (CR 508.1g) phase dropped → a force_attack marker
    # (read into forced_attack), gated to faces with no structural force_attack. The
    # ACTIVATED single-target form (Basandra) keeps phase's effect and so is gated out.
    has_force_attack = any(
        e.category == "force_attack" for a in abilities for e in a.effects
    )
    if not has_force_attack and (m := _FORCE_ATTACK_REF.search(text)) is not None:
        markers.append(Effect(category="force_attack", scope="any", raw=m.group(0)))
    # Goad REWARD payoff (CR 701.38b) phase flattened to event=None with the redirect
    # condition in raw → a goad_all marker (read into goad_matters via
    # _DOER_EFFECT_KEYS). Distinct from the self-force above: this REWARDS opponents
    # being redirected at another player, so it wants goad effects, not a self-swing.
    if (m := _GOAD_REWARD_REF.search(text)) is not None:
        markers.append(Effect(category="goad_all", scope="opp", raw=m.group(0)))
    # "Tap or untap target" modal phase dropped the untap half from → an untap marker
    # carrying a Permanent target subject (read into untap_engine), gated to faces with
    # no structural untap effect. The tap half stays in phase's target_only/tap; this
    # recovers the untap-engine side (Twiddle, Pestermite, Coral Trickster).
    has_untap = any(e.category == "untap" for a in abilities for e in a.effects)
    if not has_untap and (m := _TAP_OR_UNTAP_REF.search(text)) is not None:
        markers.append(
            Effect(
                category="untap",
                scope="you",
                subject=Filter(card_types=("Permanent",)),
                raw=m.group(0),
            )
        )
    # Energy sink / payoff / replacement phase loses → an energy marker, gated to faces
    # with no structural energy effect.
    has_energy = any(e.category == "energy" for a in abilities for e in a.effects)
    if not has_energy and (m := _ENERGY_REF.search(text)) is not None:
        markers.append(Effect(category="energy", scope="you", raw=m.group(0)))
    # Rad-counter clause phase mangled/dropped → a rad_counter marker, gated to faces
    # with no structural rad place_counter / rad_counter effect.
    has_rad = any(
        e.category == "rad_counter"
        or (e.category == "place_counter" and e.counter_kind == "rad")
        for a in abilities
        for e in a.effects
    )
    if not has_rad and (m := _RAD_REF.search(text)) is not None:
        markers.append(Effect(category="rad_counter", scope="opp", raw=m.group(0)))
    # Suspect verb (mid-clause / granted) or "suspected" state phase loses → a suspect
    # marker, gated to faces with no structural suspect effect.
    has_suspect = any(e.category == "suspect" for a in abilities for e in a.effects)
    if not has_suspect and (m := _SUSPECT_REF.search(text)) is not None:
        markers.append(Effect(category="suspect", scope="you", raw=m.group(0)))
    # Condition-form crime check phase has no condition kind for → a `crime` marker,
    # gated to faces with no structural commit_crime trigger (the trigger form already
    # binds) and no crime marker yet.
    has_crime_trigger = any(
        a.trigger is not None and a.trigger.event == "commit_crime" for a in abilities
    )
    if not has_crime_trigger and (m := _CRIME_REF.search(text)) is not None:
        markers.append(Effect(category="crime", scope="you", raw=m.group(0)))
    # Venture / dungeon-completion phase drops (modal mode, granted ability, "complete
    # a dungeon" trigger) → a venture marker, gated to faces with no structural venture
    # effect AND where the venture phrase is NOT confined to a `restriction` effect
    # (Keen-Eared Sentry's opponent anti-venture hate).
    has_venture = any(e.category == "venture" for a in abilities for e in a.effects)
    venture_in_restriction_only = any(
        e.category == "restriction" and _VENTURE_REF.search(e.raw or "")
        for a in abilities
        for e in a.effects
    ) and not any(
        e.category != "restriction" and _VENTURE_REF.search(e.raw or "")
        for a in abilities
        for e in a.effects
    )
    if (
        not has_venture
        and not venture_in_restriction_only
        and (m := _VENTURE_REF.search(text)) is not None
    ):
        markers.append(Effect(category="venture", scope="you", raw=m.group(0)))
    # "Creatures you control with power N or less" buff/etb phase dropped the power
    # threshold from → a pump marker carrying the rebuilt Power:LE subject Filter, so
    # the existing predicate read fires low_power_matters. Gated to faces with no
    # structural you-controller Power:LE/LT predicate already present.
    has_low_power = any(
        s is not None
        and s.controller == "you"
        and any(
            p.startswith(("PtComparison:Power:LE:", "PtComparison:Power:LT:"))
            and not p.endswith(":*")
            for p in s.predicates
        )
        for a in abilities
        for e in a.effects
        for s in (
            e.subject,
            e.amount.subject if e.amount is not None else None,
        )
    )
    if not has_low_power and (m := _LOW_POWER_REF.search(text)) is not None:
        # category="tap" (not pump): the predicate read (_predicate_build_around_lanes)
        # scans EVERY effect's subject Filter regardless of category, so the Power:LE
        # predicate lights low_power_matters — while `tap` stays out of the
        # creatures_matter team-anthem read (which keys on pump/grant_keyword/base_pt).
        markers.append(
            Effect(
                category="tap",
                scope="you",
                subject=Filter(
                    card_types=("Creature",),
                    controller="you",
                    predicates=(f"PtComparison:Power:LE:{m.group(1)}",),
                ),
                raw=m.group(0),
            )
        )
    # Repeatable "Pay N life:" cost phase misparsed / dropped (a conferred quoted
    # ability) → a life_payment marker, gated to faces with no structural paylife cost.
    has_paylife = any(a.cost is not None and "paylife" in a.cost for a in abilities)
    if not has_paylife and (m := _PAY_LIFE_REF.search(text)) is not None:
        markers.append(Effect(category="life_payment", scope="you", raw=m.group(0)))
    # Oil-counter PAYOFF reference phase dropped → a place_counter marker carrying
    # counter_kind='oil' (the same discriminator phase stamps on a real oil placement),
    # so the existing _COUNTER_KIND_KEYS['oil'] read fires oil_counter_matters. Gated to
    # faces with no structural oil placement/marker already present. The counter_kind
    # 'oil' is NOT 'p1p1', so this never leaks into counters_matter.
    has_oil = any(
        e.category == "place_counter" and e.counter_kind == "oil"
        for a in abilities
        for e in a.effects
    )
    if not has_oil and (m := _OIL_REF.search(text)) is not None:
        markers.append(
            Effect(
                category="place_counter",
                scope="you",
                counter_kind="oil",
                raw=m.group(0),
            )
        )
    # "Starting life total" reference phase has no structure for → a starting_life
    # marker. Read via _DOER_EFFECT_KEYS (CR 103.4).
    if (m := _STARTING_LIFE_REF.search(text)) is not None:
        markers.append(Effect(category="starting_life", scope="you", raw=m.group(0)))
    # Mass-death count operand phase dropped → a mass_death marker. Read via
    # _DOER_EFFECT_KEYS (CR 700.4).
    if (m := _MASS_DEATH_REF.search(text)) is not None:
        markers.append(Effect(category="mass_death", scope="you", raw=m.group(0)))
    # Changeling / "is every creature type" phase drops onto a token-profile raw, a
    # grant carrier, or a type_set/place_counter self-static → a changeling marker.
    # Read via _DOER_EFFECT_KEYS (CR 702.73). The card's OWN intrinsic changeling rides
    # the Scryfall keyword (_IR_KEYWORD_MAP); this is the keyword-less maker / anthem.
    if (m := _CHANGELING_REF.search(text)) is not None:
        markers.append(Effect(category="changeling", scope="you", raw=m.group(0)))
    # Regenerate GRANTED / QUOTED / replacement phase drops → a regenerate marker,
    # gated to faces with no structural regenerate effect already present (the plain
    # top-level regenerate binds natively). Read via _DOER_EFFECT_KEYS (CR 701.15).
    has_regen = any(e.category == "regenerate" for a in abilities for e in a.effects)
    if not has_regen and (m := _REGENERATE_REF.search(text)) is not None:
        markers.append(Effect(category="regenerate", scope="you", raw=m.group(0)))
    # Cascade reference phase keeps only in a non-grant-carrier raw (a "cast a spell
    # with cascade" PAYOFF trigger — The First Doctor — whose consequence is a
    # place_counter outside _GRANT_CARRIERS) → a cascade marker, gated to faces with no
    # structural cascade marker (the conferred-keyword pass binds the grant carriers).
    # An intrinsic cascade card's own text (keyword + stripped reminder) never matches
    # _CASCADE_GRANT's grant/reference phrasing, so the array-bearer isn't re-tagged.
    has_cascade = any(e.category == "cascade" for a in abilities for e in a.effects)
    if not has_cascade and (m := _CASCADE_GRANT.search(text)) is not None:
        markers.append(Effect(category="cascade", scope="you", raw=m.group(0)))
    # Creature-cast trigger phase dropped onto the face oracle (a quoted token ability
    # or a spell's delayed trigger — Blink, Glimpse of Nature) → a creature_cast marker.
    # Gated to faces with no structural creature_cast marker. The extract_signals_ir
    # face-scan covers the effect-raw survivors; this is the face-only-drop residual.
    has_creature_cast = any(
        e.category == "creature_cast" for a in abilities for e in a.effects
    )
    if not has_creature_cast and (m := _CREATURE_CAST_REF.search(text)) is not None:
        markers.append(Effect(category="creature_cast", scope="any", raw=m.group(0)))
    # Token-subtype (Food/Treasure/Clue/Blood) phase drops off EVERY raw — a "Create a
    # <Subtype> token" buried in a die-roll / vote / dilemma branch whose consequence
    # phase doesn't keep (Hoarding Ogre, Treasure Chest, Seize the Spotlight) or a
    # "Sacrifice a <Subtype>" cost on a branch phase dropped — surviving only on face
    # oracle. A face-level marker per subtype, gated to faces with no structural maker /
    # sac for that subtype (the per-ability _narrow_token_subtype_makers binds the
    # raw-survivors). CR 111.10 / 701.16.
    have_make_sub = {
        st
        for a in abilities
        for e in a.effects
        if e.category == "make_token" and e.subject is not None
        for st in e.subject.subtypes
    }
    have_sac_sub = {
        st
        for a in abilities
        for e in a.effects
        if e.category == "sacrifice" and e.subject is not None
        for st in e.subject.subtypes
    }
    made_face: set[str] = set()
    for tm in (
        _TOKEN_SUBTYPE_REF.finditer(text) if _TOKEN_CREATE_VERB.search(text) else ()
    ):
        sub = tm.group(1).capitalize()
        if sub in have_make_sub or sub in made_face:
            continue
        made_face.add(sub)
        markers.append(
            Effect(
                category="make_token",
                scope="you",
                subject=Filter(subtypes=(sub,), predicates=("Token",)),
                raw=tm.group(0),
            )
        )
    sacd_face: set[str] = set()
    for tm in _TOKEN_SUBTYPE_SAC.finditer(text):
        sub = tm.group(1).capitalize()
        if sub in have_sac_sub or sub in sacd_face:
            continue
        sacd_face.add(sub)
        markers.append(
            Effect(
                category="sacrifice",
                scope="you",
                subject=Filter(subtypes=(sub,), predicates=("Token",)),
                raw=tm.group(0),
            )
        )
    # CARES-ABOUT subtype reference ("<Subtype>s you control" / "was a <Subtype>" / "is
    # a <Subtype>") phase has no structure for → a token_subtype_ref marker carrying the
    # subtype in counter_kind. Read in extract_signals_ir → the right lane. Gated to
    # subtypes not already made/sacd on this face (the maker/sac is the stronger tell).
    ref_seen: set[str] = set()
    for tm in _TOKEN_SUBTYPE_OWN_REF.finditer(text):
        sub = next(g for g in tm.groups() if g).capitalize()
        if sub in have_make_sub or sub in have_sac_sub or sub in ref_seen:
            continue
        ref_seen.add(sub)
        markers.append(
            Effect(
                category="token_subtype_ref",
                scope="you",
                counter_kind=sub.lower(),
                raw=tm.group(0),
            )
        )
    # Fight GRANTED / QUOTED / modal / symmetric phase drops → a fight marker, gated to
    # faces with no structural fight effect (the plain top-level fight binds natively).
    # Read via _DOER_EFFECT_KEYS (CR 701.12).
    has_fight = any(e.category == "fight" for a in abilities for e in a.effects)
    if not has_fight and (m := _FIGHT_REF.search(text)) is not None:
        markers.append(Effect(category="fight", scope="you", raw=m.group(0)))
    # Saga / lore-counter manipulation & payoff phase has no structure for (the lore
    # placement is the synthesized intrinsic advancement, subjectless) → a saga marker.
    # Anchored on the stripped-oracle "lore counter" / "Saga you control" so a vanilla
    # Saga (reminder-only lore mention) doesn't fire. Read via _DOER_EFFECT_KEYS.
    if (m := _SAGA_REF.search(text)) is not None:
        markers.append(Effect(category="saga", scope="you", raw=m.group(0)))
    # Cycling "cycle or discard" PAYOFF trigger phase dropped ENTIRELY (the trigger
    # phrase truncated off both the trigger and the effect raw — Pitiless Vizier,
    # Zenith Seeker keep only "gain indestructible"/"gain flying") → a cycling marker.
    # Gated to faces with no structural cycling marker (the _narrow_trigger_other_refs
    # arm already binds the cards whose effect raw kept the phrase) and no `cycled`
    # trigger (the typed self-cycle bonus binds natively).
    has_cycling = any(
        e.category == "cycling_payoff" for a in abilities for e in a.effects
    ) or any(a.trigger is not None and a.trigger.event == "cycled" for a in abilities)
    if not has_cycling and (m := _CYCLING_TRIG.search(text)) is not None:
        markers.append(Effect(category="cycling_payoff", scope="you", raw=m.group(0)))
    # Dice roll in a SPELL/COST form phase parsed the consequence of but dropped the
    # roll_die effect → a roll_die marker, gated to faces with no structural roll_die
    # effect/marker (the _narrow_trigger_other_refs arm + phase's native roll_die
    # already bind the trigger / recognized-roll forms).
    has_roll = any(e.category == "roll_die" for a in abilities for e in a.effects)
    if not has_roll and (m := _DICE_REF.search(text)) is not None:
        markers.append(Effect(category="roll_die", scope="you", raw=m.group(0)))

    # "Tapped creatures you control <grant>" phase parsed with the subject dropped →
    # a grant_keyword marker carrying the rebuilt Tapped-creature subject Filter, so
    # the existing Tapped-predicate read fires tapped_matters (Masako). Gated to faces
    # with no structural Tapped predicate already present.
    def _has_tapped(a: Ability) -> bool:
        if (
            a.condition is not None
            and a.condition.subject is not None
            and "Tapped" in a.condition.subject.predicates
        ):
            return True
        for e in a.effects:
            if e.subject is not None and "Tapped" in e.subject.predicates:
                return True
            if (
                e.amount is not None
                and e.amount.subject is not None
                and "Tapped" in e.amount.subject.predicates
            ):
                return True
        return False

    has_tapped_pred = any(_has_tapped(a) for a in abilities)
    if not has_tapped_pred and (m := _TAPPED_GRANT.search(text)) is not None:
        # category="tap" (not grant_keyword): the Tapped-creature subject lights the
        # tapped_matters predicate read, while NOT tripping the creatures_matter
        # team-anthem read (which keys on grant_keyword/pump/base_pt_set) — Masako's
        # "tapped creatures can block as though untapped" is a state grant, not a
        # whole-board anthem. The tapped_matters read is effect-category-agnostic.
        markers.append(
            Effect(
                category="tap",
                scope="you",
                subject=Filter(
                    card_types=("Creature",),
                    controller="you",
                    predicates=("Tapped",),
                ),
                raw=m.group(0),
            )
        )
    # Modal / granted-quoted "can't block" phase dropped → a cant_block marker, gated
    # to faces with no structural cant_block effect (the per-carrier marker already
    # covers the carrier-raw shapes).
    has_cant_block = any(
        e.category == "cant_block" for a in abilities for e in a.effects
    )
    if not has_cant_block:
        for pat in (_CANT_BLOCK_MODAL_BULLET, _CANT_BLOCK_GRANT_QUOTE):
            for m in pat.finditer(text):
                seg = m.group(0)
                if _CANT_BLOCK_REF.search(seg) and not _CANT_BLOCK_TAX.search(seg):
                    markers.append(Effect(category="cant_block", scope="any", raw=seg))
                    break
            else:
                continue
            break
    return markers


def _type_and_subtype_filters(node: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split a Typed filter's ``type_filters`` into (card_types, subtypes).

    phase encodes card types as bare strings (``"Creature"``) and subtypes as
    one-key dicts (``{"Subtype": "Goblin"}``) within the same ``type_filters``
    list, plus an optional separate ``subtype_filters``. Composite entries —
    ``{"Non": X}`` (negation) and ``{"AnyOf": [...]}`` (disjunction) — are NOT a
    plain type/subtype (a ``{Non: Land}`` must not read as a Land filter); they
    become predicates via ``_composite_predicates`` and are skipped here."""
    card_types: list[str] = []
    subtypes: list[str] = list(_str_tuple(node.get("subtype_filters")))
    for tf in _as_list(node.get("type_filters")):
        if isinstance(tf, str):
            card_types.append(tf)
        elif isinstance(tf, dict):
            for k, v in tf.items():
                if _norm(k) == "subtype" and isinstance(v, str):
                    subtypes.append(v)
    return tuple(card_types), tuple(subtypes)


def _anyof_member(it: object) -> str:
    """The descriptor of one ``AnyOf`` member — a bare card type or a subtype."""
    if isinstance(it, str):
        return it
    if isinstance(it, dict):
        sub = it.get("Subtype")
        if isinstance(sub, str):
            return sub
    return ""


def _composite_predicates(node: dict) -> list[str]:
    """Negation / disjunction type_filter entries → predicate strings (the flat
    Filter has no nested-filter slot). ``{Non: "Land"}`` → ``NotType:Land`` (mirrors
    NotColor), ``{Non: {Subtype: Human}}`` → ``NotSubtype:Human``, ``{AnyOf: [...]}``
    → ``AnyOf:<sorted|members>`` (Instant/Sorcery, basic-land types, an Outlaw
    subtype set, …). Before this, ``{Non: X}`` was silently dropped INTO card_types
    (inverting the meaning) and ``{AnyOf}`` was dropped entirely."""
    out: list[str] = []
    for tf in _as_list(node.get("type_filters")):
        if not isinstance(tf, dict):
            continue
        for k, v in tf.items():
            kn = _norm(k)
            if kn == "non":
                if isinstance(v, str):
                    out.append(f"NotType:{v}")
                elif isinstance(v, dict) and isinstance(v.get("Subtype"), str):
                    out.append(f"NotSubtype:{v['Subtype']}")
            elif kn == "anyof" and isinstance(v, list):
                members = sorted(m for m in (_anyof_member(x) for x in v) if m)
                if members:
                    out.append("AnyOf:" + "|".join(members))
    return out


def _merge_filters(members: list[Filter]) -> Filter:
    """Union member filters into one — for an ``Or`` composite (Spark Double copies a
    Creature OR a Planeswalker; Absorbing Man an Artifact OR an Enchantment). Unions
    card_types/subtypes so a lane that keys on a type sees every type the effect can
    apply to; controller is kept only if all members agree (else "any"); predicates
    are dropped (their union semantics across an Or are ambiguous)."""
    card_types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    for m in members:
        card_types += tuple(t for t in m.card_types if t not in card_types)
        subtypes += tuple(s for s in m.subtypes if s not in subtypes)
    controllers = {m.controller for m in members}
    controller = members[0].controller if len(controllers) == 1 else "any"
    return Filter(card_types=card_types, subtypes=subtypes, controller=controller)


def _filter(node: object) -> Filter | None:
    if not isinstance(node, dict):
        return None
    # An ``Or`` composite target (a copy/effect that can apply to one of several
    # filters) — union the members so the type hierarchy sees every type it reaches.
    if _norm(node.get("type")) == "or":
        members = [f for f in (_filter(x) for x in _as_list(node.get("filters"))) if f]
        return _merge_filters(members) if members else None
    card_types, subtypes = _type_and_subtype_filters(node)
    controller = _controller(node.get("controller"))
    predicates = tuple(
        p for p in (_predicate(x) for x in _as_list(node.get("properties"))) if p
    ) + tuple(_composite_predicates(node))
    if not (card_types or subtypes or controller != "any" or predicates):
        return None
    return Filter(
        card_types=card_types,
        subtypes=subtypes,
        controller=controller,
        predicates=predicates,
    )


def _scalar_value(v: object) -> int | None:
    """An int from a bare int or a ``{type: Fixed, value: N}`` wrapper; None for a
    DYNAMIC value (Ref / Offset / Variable — a relative comparison like "power less
    than this creature's power", not a fixed threshold a theme keys on)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, dict) and _norm(v.get("type")) == "fixed":
        inner = v.get("value")
        return inner if isinstance(inner, int) else None
    return None


def _predicate(p: object) -> str:
    if not isinstance(p, dict):
        return ""
    ptype = p.get("type")
    if not ptype:
        return ""
    # Keep the load-bearing discriminant for the predicates whose meaning is NOT a
    # bare `value` field — color / multicolor-count / power-threshold lanes read it
    # (it was dropped before, collapsing every HasColor to a bare "HasColor"). A
    # dynamic (non-Fixed) comparison value becomes "*" so a relative fight-style
    # "power < source's power" never reads as a fixed power threshold.
    if ptype in ("HasColor", "NotColor"):
        color = p.get("color")
        return f"{ptype}:{color}" if color is not None else str(ptype)
    if ptype == "ColorCount":
        n = _scalar_value(p.get("count"))
        return f"ColorCount:{p.get('comparator')}:{n if n is not None else '*'}"
    if ptype == "PtComparison":
        n = _scalar_value(p.get("value"))
        return (
            f"PtComparison:{p.get('stat')}:{p.get('comparator')}:"
            f"{n if n is not None else '*'}"
        )
    val = p.get("value")
    if isinstance(val, dict):
        val = val.get("value")
    return f"{ptype}:{val}" if val is not None else str(ptype)


# ── scope / controller / type helpers ─────────────────────────────────────────


def _controller(c: object) -> str:
    n = _norm(c)
    if n == "you":
        return "you"
    if "opponent" in n:
        return "opp"
    return "any"


def _controller_scope(f: Filter | None) -> str:
    return f.controller if f is not None else "any"


def _effect_scope(eff: dict) -> str:
    # A Token effect's recipient is its ``owner`` (Controller → you; a target's
    # controller → opp, so "destroy target creature, its controller makes a Beast"
    # is removal, not a token engine for you).
    owner = eff.get("owner")
    if isinstance(owner, dict):
        on = _norm(owner.get("type"))
        if on == "controller":
            return "you"
        if "opponent" in on or "target" in on:
            return "opp"
    tgt = eff.get("target")
    if isinstance(tgt, dict):
        tt = _norm(tgt.get("type"))
        if tt == "controller":
            return "you"
        if "opponent" in tt:
            return "opp"
        if tt in ("eachplayer", "allplayers"):
            return "each"
    player = eff.get("player")
    if isinstance(player, str):
        pl = player.lower()
        if pl == "controller":
            return "you"
        if "opponent" in pl:
            return "opp"
        if pl in ("each", "all", "allplayers"):
            return "each"
    ps = eff.get("player_scope")
    if isinstance(ps, dict):
        pst = _norm(ps.get("type"))
        if "opponent" in pst:
            return "opp"
        if pst == "all":
            return "each"
    return "any"


# Player-controller values phase puts on a sacrificed object's `target.controller`
# when ANOTHER player does the sacrificing (an edict). "You"/null/None mean the
# active player sacrifices their own permanent — a genuine self-sacrifice — so they
# are NOT promoted off scope "any".
_EDICT_PLAYER_CONTROLLERS = frozenset(
    {"targetplayer", "targetopponent", "defendingplayer", "opponent"}
)
_EACH_PLAYER_CONTROLLERS = frozenset({"eachplayer", "allplayers", "scopedplayer"})


def _sacrifice_player_scope(eff: dict, fallback: str) -> str:
    """Scope for a Sacrifice effect, read from WHO sacrifices (the controller of the
    sacrificed object). A forced opponent sacrifice (edict) → opp; an each-player
    sacrifice → each; an explicit YOU-sacrifice → "any" (a you-sac, even when the
    effect's broader ``_effect_scope`` leaked opp from a downstream target-player
    clause — Cabal Therapist's "you may sacrifice … then target player reveals");
    otherwise the existing ``fallback``. ADR-0027 sacrifice_matters edict split."""
    tgt = eff.get("target")
    if not isinstance(tgt, dict):
        return fallback
    ctrl = tgt.get("controller")
    cn = _norm(ctrl.get("type")) if isinstance(ctrl, dict) else _norm(ctrl)
    if cn in _EDICT_PLAYER_CONTROLLERS:
        return "opp"
    if cn in _EACH_PLAYER_CONTROLLERS:
        return "each"
    if cn in ("you", "controller"):
        return "any"
    return fallback


def _trigger_event(tr: dict) -> str:
    mode = _norm(tr.get("mode"))
    if mode in ("changeszone", "changeszoneall"):
        dest = _norm(tr.get("destination"))
        origin = _norm(tr.get("origin"))
        if dest == "battlefield":
            return "etb"
        if origin == "battlefield" and dest == "graveyard":
            return "dies"
        return "leaves"
    if mode in ("damagedone", "damagedoneonce", "damagedealtonce"):
        return (
            "combat_damage"
            if _norm(tr.get("damage_kind")) == "combatonly"
            else "deals_damage"
        )
    if mode == "damagereceived":
        return "damage_received"
    if mode in ("spellcast", "spellcopy", "spellcastorcopy", "spellabilitycast"):
        return "cast_spell"
    if mode in (
        "attacks",
        "youattack",
        "attackersdeclared",
        "attackersdeclaredonetarget",
        # v0.1.60 split "attacks and isn't blocked" into its own modes; v0.1.19
        # folded them into Attacks, so map them back to keep attack_matters parity.
        "attackerunblocked",
        "youattackunblocked",
    ):
        return "attacks"
    if mode in ("blocks", "blockersdeclared", "becomesblocked"):
        return "blocks"
    if mode == "phase":
        ph = _norm(tr.get("phase"))
        if ph == "upkeep":
            return "upkeep"
        if ph == "end":
            return "end_step"
        if ph == "draw":
            return "draw_step"
        if ph in ("begincombat", "combat"):
            return "begin_combat"
        return "other"
    if mode in ("counteradded", "counteraddedonce", "counteraddedall"):
        return "counter_added"
    if mode == "lifegained":
        return "life_gained"
    if mode in ("lifelost", "lifelostall", "paylife"):
        return "life_lost"
    if mode in ("destroyed", "leavesbattlefield"):
        return "dies"
    if mode in ("sacrificed", "sacrificedonce"):
        return "sacrificed"
    if mode in ("taps", "tapsformana"):
        return "taps"
    if mode in ("discarded", "discardedall"):
        return "discarded"
    if mode == "drawn":
        return "drawn"
    if mode in ("milled", "milledonce", "milledall"):
        return "milled"
    if mode in ("blocks", "blockersdeclared", "becomesblocked", "attackerblocked"):
        return "blocks"
    # Batch 1 — payoff trigger modes previously falling to "other". The Scry/Surveil
    # TRIGGER modes ("whenever you scry/surveil") are distinct from the Scry/Surveil
    # EFFECT types (the doer → topdeck_select in _EFFECT_CATEGORY).
    if mode == "commitcrime":
        return "commit_crime"
    if mode == "cycled":
        return "cycled"
    if mode == "scry":
        return "scried"
    if mode == "surveil":
        return "surveiled"
    if mode in ("excessdamageall", "excessdamage"):
        return "excess_damage"
    return "other"


def _trigger_scope(tr: dict) -> str:
    vc = tr.get("valid_card")
    if isinstance(vc, dict):
        n = _norm(vc.get("type"))
        if n == "selfref":
            return "you"
        c = _controller(vc.get("controller"))
        if c != "any":
            return c
    # Batch 11 — a player-EVENT trigger (whenever an opponent draws/searches) carries
    # the player in valid_target, not valid_card (Nekusar: Drawn + valid_target
    # controller=Opponent). Fall back to it so the scope isn't lost.
    vt = tr.get("valid_target")
    if isinstance(vt, dict):
        c = _controller(vt.get("controller"))
        if c != "any":
            return c
    return "any"


def _type_line(card_type: object) -> str:
    if not isinstance(card_type, dict):
        return ""
    left = _str_tuple(card_type.get("supertypes")) + _str_tuple(
        card_type.get("core_types")
    )
    subs = _str_tuple(card_type.get("subtypes"))
    line = " ".join(left)
    if subs:
        line = f"{line} — {' '.join(subs)}".strip()
    return line.strip()


def _keywords(kws: object) -> tuple[str, ...]:
    if not isinstance(kws, list):
        return ()
    out: list[str] = []
    for kw in kws:
        if isinstance(kw, str):
            out.append(kw)
        elif isinstance(kw, dict) and kw:
            k = next(iter(kw))
            if isinstance(k, str):
                out.append(k)
    return tuple(out)


def _allows_many_copies(record: dict) -> bool:
    """The CR 100.2a copy-limit exception (a deck may run many copies of this name —
    Relentless Rats, Hare Apparent, Seven Dwarves): phase's ``deck_copy_limit`` is
    ``Unlimited`` or ``UpTo`` with a bound >= 2. UpTo:1 (Vazal's Megalegendary, Once
    More With Feeling) RESTRICTS to one copy — the opposite — so it is excluded."""
    dl = record.get("deck_copy_limit")
    if not isinstance(dl, dict):
        return False
    t = _norm(dl.get("type"))
    if t == "unlimited":
        return True
    return t == "upto" and _int(dl.get("data"), 0) >= 2


def _castable_zones(records: list[dict]) -> tuple[str, ...]:
    zones: dict[str, None] = {}
    for rec in records:
        for kw in _keywords(rec.get("keywords")):
            zone = _CASTABLE_ZONE_KEYWORDS.get(_norm(kw))
            if zone:
                zones.setdefault(zone, None)
    return tuple(zones)


def _int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default
