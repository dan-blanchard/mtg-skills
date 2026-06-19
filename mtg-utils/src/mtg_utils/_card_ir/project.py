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
        if want("exhaust") and _EXHAUST_TRIG.search(raw):
            markers.append(Effect(category="exhaust", scope="you", raw=raw))
        if want("ninjutsu") and _NINJUTSU_TRIG.search(raw):
            markers.append(Effect(category="ninjutsu", scope="you", raw=raw))
        if want("scry_surveil") and _SCRY_SURVEIL_TRIG.search(raw):
            markers.append(Effect(category="scry_surveil", scope="you", raw=raw))
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


def _project_spell_or_activated(ab: dict) -> Ability:
    kind = "activated" if _norm(ab.get("kind")) == "activated" else "spell"
    effects = _collect_effects(ab, ab.get("description") or "")
    return _recover_clone_subjects(
        Ability(
            kind=kind,
            effects=tuple(effects),
            cost=_cost_string(ab.get("cost")),
            condition=_project_condition(ab.get("condition")),
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
    if event == "damagedone" and dmod in _INCREASE_MODS:
        return _static_effect("damage_doubling", "you", raw)
    return None


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
    eff = node.get("effect")
    if isinstance(eff, dict):
        out.extend(_project_effect(eff, raw))
    sub = node.get("sub_ability")
    if isinstance(sub, dict):
        out.extend(_collect_effects(sub, default_raw))
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


def _project_effect(eff: dict, raw: str) -> list[Effect]:
    etype = _norm(eff.get("type"))
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
        return [_changezone_effect(eff, raw)]
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
        # untap_engine / tap_down derive from it.
        state = _norm((eff.get("state") or {}).get("type"))
        cat = "untap" if state == "untap" else "tap"
        return [
            Effect(
                category=cat,
                scope=_effect_scope(eff),
                subject=_effect_subject(eff),
                raw=raw,
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
    return [
        Effect(
            category=category,
            amount=_amount(eff),
            scope=_effect_scope(eff),
            subject=_effect_subject(eff),
            raw=raw,
            counter_kind=_norm(ck) if isinstance(ck, str) else "",
            zones=_zone_tags(eff),
        )
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
    for m in st.get("modifications") or []:
        mt = _norm(m.get("type"))
        if mt in _PUMP_MODS:
            is_pump = True
            if pump_amount is None:
                pump_amount = _quantity(m.get("value"))
        elif mt in ("setpower", "setdynamicpower", "setpowerdynamic"):
            set_power = True
        elif mt in ("settoughness", "setdynamictoughness", "settoughnessdynamic"):
            set_toughness = True
        elif mt == "addkeyword":
            # Batch 6 — a static that GRANTS a keyword (Levitation → Flying). The
            # granted keyword rides in counter_kind (a free str field); the lane
            # splits by keyword + whether the affected set is your whole team.
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
    )


def _changezone_effect(eff: dict, raw: str) -> Effect:
    """A ChangeZone effect → category by its origin/destination zones.

    Graveyard → Battlefield is reanimation; → Exile of your own permanent is a
    blink (ETB-value flicker); → Exile of others' is exile removal; the rest stay
    'other'. The ``target`` (a Typed filter of what's moved) is the subject."""
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
        return Quantity(op="count", factor=1, subject=_objectcount_filter(qty))
    if t == "counterson" and _norm(node.get("counter_type")) == "p1p1":
        # "for each +1/+1 counter on ~" — counter-scaling payoff (only +1/+1, not
        # charge/oil/lore/time, which aren't +1/+1-counters synergy).
        return Quantity(op="counters", factor=1)
    if t == "objectcount":
        return Quantity(op="count", factor=1, subject=_filter(node.get("filter")))
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
    # (Power is NOT here: "equal to its power" is ubiquitous and mostly a one-off
    # damage/draw scale, not a power build-around — no clean lane. CountersOn is
    # handled in _quantity, gated to +1/+1 counters; charge/oil/lore/time scaling
    # is not +1/+1-counters synergy.)
}


def _objectcount_filter(qty: object) -> Filter | None:
    if isinstance(qty, dict) and _norm(qty.get("type")) == "objectcount":
        return _filter(qty.get("filter"))
    return None


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
