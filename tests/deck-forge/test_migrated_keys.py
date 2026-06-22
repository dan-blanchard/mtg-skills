"""Durable invariant for the ADR-0027 regex→Card-IR strangler.

For EVERY key in ``MIGRATED_KEYS``, the migration must be real and complete:

  * ``extract_signals`` (the legacy regex path) must NO LONGER emit the key — its
    oracle-regex production (``_DETECTORS`` / ``_HAND_FLOOR`` / ``SWEEP_DETECTORS``
    rows + any ``add()``) is deleted.
  * ``extract_signals_hybrid(card, ir)`` (the production dispatcher) DOES emit it,
    served from the Card IR path (``extract_signals_ir``).

Each case is a real card (full oracle_text + type_line, never trimmed/fabricated)
paired with a hand-built IR that mirrors the structural source the IR path reads
for that key — so the proof holds without a phase dependency or the on-disk
sidecar. A new migration batch adds one ``(key, card, ir)`` row here; the
parametrization then guards it forever.
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.signals import (
    MIGRATED_KEYS,
    extract_signals,
    extract_signals_hybrid,
)
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


def _ir(*abilities: Ability, keywords: tuple[str, ...] = ()) -> Card:
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", keywords=keywords, abilities=tuple(abilities)),),
    )


# One representative real card per migrated key, paired with the IR that mirrors
# the structural source the IR path reads:
#   ki_counter_matters  ← Effect(place_counter, counter_kind="ki")  [_COUNTER_KIND_KEYS]
#   seek_matters        ← Effect(category="seek")                   [_DOER_EFFECT_KEYS]
#   specialize_matters  ← Scryfall "Specialize" keyword             [_IR_KEYWORD_MAP]
_CASES: dict[str, tuple[dict, Card]] = {
    # debuff_matters ← a `pump` Effect with amount.factor < 0 (Dead Weight's static
    # "Enchanted creature gets -2/-2" projects pump, factor=-2). The NEGATIVE factor IS
    # the debuff signal; the structural arm in extract_signals_ir fires scope "any".
    # ADR-0027 β.
    "debuff_matters": (
        {
            "name": "Dead Weight",
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature gets -2/-2.",
            "keywords": ["Enchant"],
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="any",
                        subject=Filter(
                            card_types=("Creature",), predicates=("EnchantedBy",)
                        ),
                        amount=Quantity(op="fixed", factor=-2),
                        raw="Enchanted creature gets -2/-2.",
                    ),
                ),
            )
        ),
    ),
    # pump_matters ← a byte-identical _IR_KEPT_DETECTORS mirror of the deleted regex
    # ("target creature gets +N/+N"). UNLIKE debuff_matters there is NO structural arm:
    # the projection drops the +N/+N value to amount==None and carries no temporal
    # marker, so a positive combat trick can't be told apart from a -1/-1 debuff or a
    # permanent buff structurally; the one clean positive form (EnchantedBy/EquippedBy
    # auras/equipment) is the separate voltron/suit-up lane. So the lane fires from the
    # kept mirror over the card's oracle_text (Giant Growth's "Target creature gets
    # +3/+3 until end of turn"); the paired IR is vanilla — the mirror reads the record,
    # not the IR structure. ADR-0027 β.
    "pump_matters": (
        {
            "name": "Giant Growth",
            "type_line": "Instant",
            "oracle_text": "Target creature gets +3/+3 until end of turn.",
        },
        _ir(),
    ),
    # unspent_mana ← a byte-identical _IR_KEPT_DETECTORS mirror of the deleted SWEEP
    # regex ("you don't lose unspent <color> mana as steps and phases end"). phase
    # carries a StepEndUnspentMana static for the pure statics but the v17 projection
    # drops it, AND all such cards already match the regex — so a structural arm gains
    # ZERO recall; the burst riders have no structural form at all. So the lane fires
    # from the kept mirror over the card's oracle_text (Leyline Tyrant's "You don't lose
    # unspent red mana as steps and phases end"); the paired IR is vanilla — the mirror
    # reads the record, not the IR structure. ADR-0027 β.
    "unspent_mana": (
        {
            "name": "Leyline Tyrant",
            "type_line": "Creature — Dragon",
            "oracle_text": (
                "Flying\n"
                "You don't lose unspent red mana as steps and phases end.\n"
                "When this creature dies, you may pay any amount of {R}. When you "
                "do, it deals that much damage to any target."
            ),
        },
        _ir(),
    ),
    # untap_engine ← an `untap` Effect whose raw matches the engine anchor "untap
    # target/all/each/two/up to" (Seedborn Muse's "Untap all permanents you control"
    # projects cat="untap", subject=None — phase drops the broad subject — so the raw
    # branch carries it). The structural arm in extract_signals_ir fires scope "you",
    # gated against the opponent-untap / provoke / single-attach over-fires. ADR-0027 β.
    "untap_engine": (
        {
            "name": "Seedborn Muse",
            "type_line": "Creature — Spirit",
            "oracle_text": (
                "Untap all permanents you control during each other player's "
                "untap step."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="untap",
                        scope="any",
                        raw=(
                            "Untap all permanents you control during each other "
                            "player's untap step"
                        ),
                    ),
                ),
            )
        ),
    ),
    # variable_pt ← a `characteristic_pt` Effect (a */* characteristic-defining P/T —
    # Nightmare's "power and toughness are each equal to the number of Swamps you
    # control"). phase fully structures the clause into a SetDynamicPower/Toughness
    # self-CDA static then drops it (the base_pt_set arm excludes the CDA flag +
    # SelfRef); project._self_cda_marker re-surfaces it via supplement._CDA_PT (SIDECAR
    # v10). The structural arm in extract_signals_ir reads cat=="characteristic_pt",
    # scope "any". ADR-0027 β.
    "variable_pt": (
        {
            "name": "Nightmare",
            "type_line": "Creature — Nightmare Horse",
            "oracle_text": (
                "Flying (This creature can't be blocked except by creatures with "
                "flying or reach.)\nNightmare's power and toughness are each equal "
                "to the number of Swamps you control."
            ),
            "keywords": ["Flying"],
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="characteristic_pt",
                        scope="any",
                        raw=(
                            "~'s power and toughness are each equal to the number "
                            "of Swamps you control."
                        ),
                    ),
                ),
            )
        ),
    ),
    # token_copy_matters ← a BYTE-IDENTICAL kept mirror (_TOKEN_COPY_MATTERS_MIRROR over
    # the reminder-stripped oracle: "create a token that's a copy of equipped creature").
    # phase structures CopyTokenOf/Populate but the projection collapses them to a plain
    # make_token AND a structural arm would 100%-over-fire with reminder-text self-copies
    # (Embalm/Offspring), so the lane rides the exact deleted regex (empty IR — the mirror
    # reads the dict oracle). ADR-0027 β.
    "token_copy_matters": (
        {
            "name": "Helm of the Host",
            "type_line": "Legendary Artifact — Equipment",
            "oracle_text": (
                "At the beginning of combat on your turn, create a token that's "
                "a copy of equipped creature, except the token isn't legendary. "
                "That token gains haste.\nEquip {5}"
            ),
        },
        _ir(),
    ),
    # tokens_matter ← a BYTE-IDENTICAL kept mirror (_TOKENS_MATTER_MIRROR over the
    # reminder-stripped oracle: "Creature tokens you control get +1/+1 …" is the broad
    # "tokens you control" payoff phase carries NO structural shape for — it survives only
    # in raw, so a structural-only migration would lose 161 cards). The lane rides the
    # exact deleted _HAND_FLOOR regex union (empty IR — the mirror reads the dict oracle).
    # ADR-0027.
    "tokens_matter": (
        {
            "name": "Intangible Virtue",
            "type_line": "Enchantment",
            "oracle_text": (
                "Creature tokens you control get +1/+1 and have vigilance."
            ),
        },
        _ir(),
    ),
    # creature_etb ← a BYTE-IDENTICAL kept mirror (_creature_etb_clauses over the
    # reminder-stripped oracle: "Whenever a creature you control enters, put a +1/+1
    # counter on each creature you control"). The structural etb-trigger arm gains
    # Graft/Soulbond but MISSES the ETB-trigger doublers (Panharmonicon — phase models
    # "triggers an additional time" as a static replacement) and Ephara's upkeep-gated
    # delayed payoff, so it's neutralized and the lane rides the exact per-clause
    # deleted regex (empty IR — the mirror reads the dict oracle). ADR-0027 β.
    "creature_etb": (
        {
            "name": "Cathars' Crusade",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever a creature enters the battlefield under your control, put "
                "a +1/+1 counter on each creature you control."
            ),
        },
        _ir(),
    ),
    # lifegain_matters ← a `life_gained` Trigger (Archangel of Thune's "Whenever you
    # gain life, put a +1/+1 counter on each creature you control" projects a triggered
    # ability with event=="life_gained"). The STRUCTURAL arm in extract_signals_ir fires
    # lifegain_matters scope "you" off that trigger (the gain PAYOFF), proving the real
    # IR arm — not just the byte-identical kept mirror that recovers the broader "if you
    # gained life" / self-bleed-sustain intent. ADR-0027 β.
    "lifegain_matters": (
        {
            "name": "Archangel of Thune",
            "type_line": "Creature — Angel",
            "oracle_text": (
                "Flying\nLifelink (Damage dealt by this creature also causes "
                "you to gain that much life.)\nWhenever you gain life, put a "
                "+1/+1 counter on each creature you control."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="life_gained", scope="you"),
                effects=(
                    Effect(
                        category="place_counter",
                        scope="you",
                        raw="put a +1/+1 counter on each creature you control",
                    ),
                ),
            )
        ),
    ),
    # conjure_matters ← a BYTE-IDENTICAL `\bconjure\b` kept word mirror
    # (signals._IR_KEPT_DETECTORS, scope "you", over the reminder-stripped oracle).
    # CONJURE is digital-only (Arena/Alchemy, CR 701.66a): phase carries a structural
    # `Conjure` effect type but the projection folds it to make_token AND the structural
    # set is INCOMPLETE (misses conjure-via-activated/triggered/modal ability), so the
    # lane rides the exact deleted SWEEP regex (empty IR — the mirror reads the dict
    # oracle). Brave Meadowguard's real oracle. ADR-0027 β.
    "conjure_matters": (
        {
            "name": "Brave Meadowguard",
            "type_line": "Creature — Mouse Soldier",
            "oracle_text": (
                "When Brave Meadowguard enters, conjure a card named Might of the "
                "Meek into your hand.\nValiant — Whenever Brave Meadowguard becomes "
                "the target of a spell or ability you control for the first time each "
                "turn, put a +1/+1 counter on it."
            ),
        },
        _ir(),
    ),
    # entered_attacker ← a BYTE-IDENTICAL kept mirror (_ENTERED_ATTACKER_MIRROR run
    # per-clause over the reminder-stripped oracle: "...deals combat damage to a player,
    # if that creature entered this turn..."). phase does NOT project the "entered this
    # turn" temporal predicate (it survives only in raw), so there is no structural shape
    # to read; the lane rides the exact deleted _HAND_FLOOR regex (empty IR — the mirror
    # reads the dict oracle). Samut's real oracle. ADR-0027 β.
    "entered_attacker": (
        {
            "name": "Samut, Vizier of Naktamun",
            "type_line": "Legendary Creature — Human Warrior Cleric",
            "oracle_text": (
                "First strike, vigilance, haste\n"
                "Whenever a creature you control deals combat damage to a "
                "player, if that creature entered this turn, draw a card."
            ),
        },
        _ir(),
    ),
    # attack_matters ← the BYTE-IDENTICAL kept mirror (_ATTACK_MATTERS_MIRROR + the inline
    # "whenever"&"attack" substring-AND). Relentless Assault carries the "attacked this
    # turn" combat-count payoff (CR 508) that phase types as an effect predicate, not an
    # attacks trigger — so it rides the mirror over the dict oracle (empty IR). The
    # structural `attacks`-trigger arm + the 10 combat keywords are exercised in
    # test_signals.py. ADR-0027.
    "attack_matters": (
        {
            "name": "Relentless Assault",
            "type_line": "Sorcery",
            "oracle_text": (
                "Untap all creatures that attacked this turn. After this main "
                "phase, there is an additional combat phase followed by an "
                "additional main phase."
            ),
        },
        _ir(),
    ),
    # color_change ← a BYTE-IDENTICAL kept mirror (_COLOR_CHANGE_MIRROR over the reminder-
    # stripped oracle: "Target permanent becomes the color or colors of your choice").
    # phase parses the clause inconsistently (AddChosenColor mods / Unimplemented
    # "become"s) and the only shared IR category (animate) 90%-over-fires, so the lane
    # rides the exact deleted SWEEP regex (empty IR — the mirror reads the dict oracle).
    # ADR-0027 β.
    "color_change": (
        {
            "name": "Prismatic Lace",
            "type_line": "Sorcery",
            "oracle_text": (
                "Target permanent becomes the color or colors of your choice. "
                "(This effect lasts indefinitely.)"
            ),
        },
        _ir(),
    ),
    # damage_redirect ← TWO byte-identical kept mirrors (phase ~90%-over-fires either
    # structural category: damage_prevention 396 vs 44, redirect/damage_replace(ment)
    # 224 vs 25). ARM A (the case here) is the NAME-AWARE self-prevention tell: the IR
    # path reuses _detect_self_damage_prevention over the dict oracle, which keys on the
    # card's own short name ("Cho-Manno") — Cho-Manno, Revolutionary is the canonical
    # unkillable Pariah carrier. ARM B (the redirect clause, _DAMAGE_REDIRECT_MIRROR) is
    # exercised separately in test_signals.py. Empty IR (the helper reads the dict
    # oracle, not the IR structure). ADR-0027 β.
    "damage_redirect": (
        {
            "name": "Cho-Manno, Revolutionary",
            "type_line": "Legendary Creature — Human Rebel",
            "oracle_text": "Prevent all damage that would be dealt to Cho-Manno.",
        },
        _ir(),
    ),
    # damage_prevention ← the BROAD `damage_prevention` Effect category (the PRIMARY
    # producer, _DOER_EFFECT_KEYS). Urza's Armor's "If a source would deal damage to
    # you, prevent 1 of that damage" projects cat="damage_prevention" (verified vs the
    # baked sidecar IR) — and is an ir_only card: the "prevent N of that damage" form
    # does NOT match the deleted SWEEP regex, so this case exercises the structural arm,
    # not the kept mirror. The structural arm fires scope "you" (matching the deleted
    # producer). The byte-identical _DAMAGE_PREVENTION_MIRROR for the 88 fog / CoP /
    # Aura-Equipment-ward forms phase's effect category misses is exercised separately in
    # test_signals.py. CR 615. ADR-0027.
    "damage_prevention": (
        {
            "name": "Urza's Armor",
            "type_line": "Artifact",
            "oracle_text": (
                "If a source would deal damage to you, prevent 1 of that damage."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="damage_prevention",
                        scope="any",
                        raw="",
                    ),
                ),
            )
        ),
    ),
    # animate_artifact ← a BYTE-IDENTICAL kept mirror (_ANIMATE_ARTIFACT_MIRROR over the
    # reminder-stripped oracle: "Target noncreature artifact becomes an artifact creature
    # …"). phase parses "artifacts become creatures" inconsistently (base_pt_set /
    # board_grant over an Artifact subject / a becomes_type{Artifact} grant / a
    # base_pt_set with subject=None) and none is cleanly separable from generic become /
    # type-conferral (the dead cat=='animate' arm fires 0 cards; a base_pt_set-over-
    # Artifact arm 90%-over-fires or, narrowed, loses 48 animators), so the lane rides the
    # exact deleted SWEEP regex (empty IR — the mirror reads the dict oracle). ADR-0027 β.
    "animate_artifact": (
        {
            "name": "Karn, Silver Golem",
            "type_line": "Legendary Artifact Creature — Golem",
            "oracle_text": (
                "Whenever Karn, Silver Golem blocks or becomes blocked, it gets "
                "-4/+4 until end of turn.\n"
                "{1}: Target noncreature artifact becomes an artifact creature with "
                "power and toughness each equal to its mana value until end of turn."
            ),
        },
        _ir(),
    ),
    # free_cast ← a BYTE-IDENTICAL kept mirror (_FREE_CAST_MIRROR over the reminder-
    # stripped oracle: "...without paying their mana cost(s)"). The IR carries
    # cast_from_zone/alt_cost but no 'free' discriminator, so the lane rides the exact
    # deleted SWEEP regex (empty IR — the mirror reads the dict oracle). ADR-0027 β.
    "free_cast": (
        {
            "name": "Omniscience",
            "type_line": "Enchantment",
            "oracle_text": (
                "You may cast spells from your hand without paying their mana costs."
            ),
        },
        _ir(),
    ),
    # gain_control ← a `gain_control` Effect (Control Magic's ChangeController static
    # projects cat="gain_control", subject=the enchanted creature, scope="you"). The
    # GATED structural arm in extract_signals_ir fires scope "you" (excl donate /
    # Owned-return / give-away). The bare `gain control of` literal is gone from the
    # regex path (Control Magic says "You control enchanted creature", not "gain control
    # of", and has no "don't own", so the regex cross-open stays silent too). ADR-0027 β.
    "gain_control": (
        {
            "name": "Control Magic",
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nYou control enchanted creature.",
            "keywords": ["Enchant"],
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="gain_control",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",), predicates=("EnchantedBy",)
                        ),
                        raw="You control enchanted creature.",
                    ),
                ),
            )
        ),
    ),
    # ltb_matters ← a STRUCTURAL `leaves` trigger (phase's LeavesBattlefield mode, or a
    # ChangesZone battlefield→elsewhere — here battlefield→hand). Azorius Aethermage's
    # "whenever a permanent is returned to your hand" is a BOUNCE leave (from:battlefield,
    # to:hand), an OTHER-permanent subject → the structural arm in extract_signals_ir
    # fires ltb_matters scope "you". Its oracle has NO "leaves the battlefield" text, so
    # the deleted regex never matched it AND the narrowed kept-mirror stays silent — this
    # is the structural arm's +9 recall (a bounce payoff the front-face-only regex
    # missed). ADR-0027 β. CR 603.6e (leaves the battlefield ⊃ dies).
    "ltb_matters": (
        {
            "name": "Azorius Aethermage",
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "Whenever a permanent is returned to your hand, you may pay {1}. "
                "If you do, draw a card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="leaves",
                    scope="you",
                    subject=Filter(card_types=("Permanent",), controller="you"),
                    zones=("from:battlefield", "to:hand"),
                ),
                effects=(
                    Effect(category="pay_cost", scope="you", raw="you may pay {1}"),
                    Effect(category="draw", scope="you", raw="draw a card"),
                ),
            )
        ),
    ),
    # death_matters ← a STRUCTURAL `dies`-trigger with a real subject (trig.event=="dies"
    # and trig.subject is not None — phase's battlefield→graveyard trigger, CR 700.4, the
    # disjoint complement of ltb_matters' broader `leaves` event). Blood Artist's
    # "Whenever this creature or another creature dies …" is the canonical aristocrats
    # payoff: the structural arm in extract_signals_ir fires death_matters scope "any".
    # The morbid "if a creature died this turn" CONDITION family rides the byte-identical
    # _DEATH_MATTERS_MIRROR instead (no trigger to read). ADR-0027. CR 700.4 / 603.6e.
    "death_matters": (
        {
            "name": "Blood Artist",
            "type_line": "Creature — Vampire",
            "oracle_text": (
                "Whenever this creature or another creature dies, target player "
                "loses 1 life and you gain 1 life."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="dies",
                    scope="any",
                    subject=Filter(card_types=("Creature",), controller="any"),
                    zones=("from:battlefield", "to:graveyard"),
                ),
                effects=(
                    Effect(category="lose_life", scope="opp", raw="loses 1 life"),
                    Effect(category="gain_life", scope="you", raw="you gain 1 life"),
                ),
            )
        ),
    ),
    # self_death_payoff ← a STRUCTURAL `dies`-trigger that is SELF (trig.event=="dies"
    # and trig.scope=="you" — phase's SelfRef self-death, subject dropped to None — with a
    # RECOGNIZED payoff effect, any e.category != "other"). Kokusho's "When Kokusho dies,
    # each opponent loses 5 life …" is the canonical self-death Aristocrats engine: the
    # structural arm in extract_signals_ir fires self_death_payoff scope "you". DISTINCT
    # from death_matters (an OTHER-creature dies trigger with a real subject); the SelfRef
    # gate (scope "you") is the discriminator. The 22 CONFERRED "When this creature dies"
    # grants phase leaves textual ride the name-aware kept mirror instead (no SelfRef
    # trigger to read). ADR-0027. CR 700.4 / 603.6e.
    "self_death_payoff": (
        {
            "name": "Kokusho, the Evening Star",
            "type_line": "Legendary Creature — Dragon Spirit",
            "oracle_text": (
                "Flying\nWhen Kokusho, the Evening Star dies, each opponent loses 5 "
                "life. You gain life equal to the life lost this way."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="dies",
                    scope="you",
                    subject=None,
                    zones=("from:battlefield", "to:graveyard"),
                ),
                effects=(
                    Effect(
                        category="lose_life",
                        scope="any",
                        raw="each opponent loses 5 life",
                    ),
                    Effect(
                        category="gain_life",
                        scope="any",
                        raw="You gain life equal to the life lost this way.",
                    ),
                ),
            )
        ),
    ),
    # self_counter_grow ← a STRUCTURAL place_counter carrying the SelfRef self-anchor
    # marker (project @ SIDECAR v12 — phase's PutCounter target=={type:SelfRef}, dropped
    # by _effect_subject, re-surfaced as Filter(predicates=("SelfRef",))). Adaptive
    # Snapjaw's adapt trigger "put a +1/+1 counter on this creature" is a self-grow: the
    # marker makes the structural arm in extract_signals_ir fire self_counter_grow scope
    # "you" (and counters_matter co-fires on the p1p1 placement). The marker is the
    # discriminator vs a "+1/+1 counter on TARGET / another creature" doer (subject=None
    # there). ADR-0027 β. CR 122.1 / 614.12 / 701.43 (adapt).
    "self_counter_grow": (
        {
            "name": "Adaptive Snapjaw",
            "type_line": "Creature — Dinosaur",
            "oracle_text": (
                "{4}{G}: Adapt 4. (If this creature has no +1/+1 counters on it, "
                "put four +1/+1 counters on it.)"
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other", scope="you"),
                effects=(
                    Effect(
                        category="place_counter",
                        scope="you",
                        subject=Filter(predicates=("SelfRef",)),
                        counter_kind="p1p1",
                        raw="Put a +1/+1 counter on this creature",
                    ),
                ),
            )
        ),
    ),
    # counter_distribute ← a STRUCTURAL place_counter carrying the MassEach mass marker
    # (project @ SIDECAR v18 — phase's PutCounterAll "on each creature you control", folded
    # by _EFFECT_CATEGORY to place_counter, re-surfaced as the MassEach subject predicate).
    # Cathars' Crusade's ETB trigger "put a +1/+1 counter on each creature you control" is a
    # board-wide spread: the marker makes the structural arm in extract_signals_ir fire
    # counter_distribute scope "you" (and counters_matter co-fires on the p1p1 placement).
    # The marker is the discriminator vs a single-target "on target creature you control"
    # placement (no MassEach there — New Horizons). ADR-0027 β. CR 122.1 / 122.6.
    "counter_distribute": (
        {
            "name": "Cathars' Crusade",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever a creature you control enters, put a +1/+1 counter on "
                "each creature you control."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="etb", scope="you"),
                effects=(
                    Effect(
                        category="place_counter",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",),
                            controller="you",
                            predicates=("MassEach",),
                        ),
                        counter_kind="p1p1",
                        raw="put a +1/+1 counter on each creature you control",
                    ),
                ),
            )
        ),
    ),
    # opponent_search_matters ← an opp-scoped `lib_search` TRIGGER (project @ SIDECAR v19
    # re-types phase's `SearchedLibrary` / `Shuffled` / scry-surveil-search
    # `PlayerPerformedAction` modes off the generic `other` event). Ob Nixilis
    # Unshackled's "Whenever an opponent searches their library, …" is a SearchedLibrary
    # trigger with valid_target.controller==Opponent → event 'lib_search', scope 'opp':
    # the scope=='opp' gate in extract_signals_ir fires opponent_search_matters scope
    # 'opponents'. The scope gate is the discriminator vs the YOU-scoped "whenever you
    # search your library / scry / surveil" payoffs (Search Elemental — scope 'any').
    # ADR-0027 β. CR 701.19.
    "opponent_search_matters": (
        {
            "name": "Ob Nixilis, Unshackled",
            "type_line": "Legendary Creature — Demon",
            "oracle_text": (
                "Flying, trample\nWhenever an opponent searches their library, "
                "that player sacrifices a creature of their choice and loses 10 "
                "life.\nWhenever another creature dies, put a +1/+1 counter on Ob "
                "Nixilis."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="lib_search", scope="opp"),
                effects=(
                    Effect(
                        category="sacrifice",
                        scope="opp",
                        raw=(
                            "that player sacrifices a creature of their choice and "
                            "loses 10 life"
                        ),
                    ),
                ),
            )
        ),
    ),
    # toughness_combat ← a BYTE-IDENTICAL kept mirror (_TOUGHNESS_COMBAT_MIRROR over the
    # reminder-stripped oracle: "Each creature you control assigns combat damage equal to
    # its toughness rather than its power"). TWO deleted regex producers (the SWEEP
    # combat-redirect + the inline value-payoff "X is … toughness") are joined into the
    # pinned TOUGHNESS_COMBAT_REGEX; phase parses the Doran clause as an
    # AssignDamageFromToughness modification but project drops it on every multi-ability
    # face (the structural category fires on only 21, MISSES 129/133, over-fires 81%), so
    # the lane rides the exact deleted regexes (empty IR — the mirror reads the dict
    # oracle). ADR-0027 β.
    "toughness_combat": (
        {
            "name": "Assault Formation",
            "type_line": "Enchantment",
            "oracle_text": (
                "Each creature you control assigns combat damage equal to its "
                "toughness rather than its power.\n{G}: Target creature with "
                "defender can attack this turn as though it didn't have defender.\n"
                "{2}{G}: Creatures you control get +0/+1 until end of turn."
            ),
        },
        _ir(),
    ),
    # ability_copy ← a BYTE-IDENTICAL kept mirror (_ABILITY_COPY_MIRROR over the
    # reminder-stripped oracle: "Copy target triggered ability you control"). The ONE
    # deleted SWEEP regex producer (copy an activated/triggered ability | "you may copy
    # it" | "has all activated abilities of") is pinned as ABILITY_COPY_REGEX; phase emits
    # ONE undifferentiated `spell_copy` category for spell-copy AND ability-copy alike, so
    # a structural arm over-fires 90% (303 vs 51, Twincast/Reverberate) and still misses
    # the granters (grant_keyword) — splitting needs a forbidden projection. So the lane
    # rides the exact deleted regex (empty IR — the mirror reads the dict oracle).
    # ADR-0027 β.
    "ability_copy": (
        {
            "name": "Strionic Resonator",
            "type_line": "Artifact",
            "oracle_text": (
                "{2}, {T}: Copy target triggered ability you control. You may "
                "choose new targets for the copy. (A triggered ability uses the "
                'words "when," "whenever," or "at.")'
            ),
        },
        _ir(),
    ),
    # cost_reduction ← a static ModifyCost{Reduce} Effect (subject = the spell_filter)
    # projected from "Instant and sorcery spells you cast cost {1} less to cast." The
    # structural arm in extract_signals_ir fires on the non-None subject. ADR-0027 β.
    "cost_reduction": (
        {
            "name": "Goblin Electromancer",
            "type_line": "Creature — Goblin Wizard",
            "oracle_text": (
                "Instant and sorcery spells you cast cost {1} less to cast."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cost_reduction",
                        scope="you",
                        subject=Filter(card_types=("Instant", "Sorcery")),
                        raw="Instant and sorcery spells you cast cost {1} less to cast.",
                    ),
                ),
            )
        ),
    ),
    # mana_amplifier ← a cat=="mana_amplifier" Effect, split OUT of the generic
    # mana_filter passthrough by supplement._MANA_AMPLIFY ("produces twice as much").
    # The structural arm in extract_signals_ir fires on the category directly. The
    # triggered "tap a land … add an additional" doublers (Crypt Ghast) ride a ramp/
    # double discriminator instead; the dork-support arm (Raggadragga) rides a kept
    # word mirror. ADR-0027 β.
    "mana_amplifier": (
        {
            "name": "Mana Reflection",
            "type_line": "Enchantment",
            "oracle_text": (
                "If you tap a permanent for mana, it produces twice as much "
                "of that mana instead."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="mana_amplifier",
                        scope="you",
                        raw=(
                            "If you tap a permanent for mana, it produces twice "
                            "as much of that mana instead"
                        ),
                    ),
                ),
            )
        ),
    ),
    "ki_counter_matters": (
        {
            "name": "Skullmane Baku",
            "type_line": "Creature — Spirit",
            "oracle_text": (
                "Whenever you cast a Spirit or Arcane spell, you may put a ki "
                "counter on this creature.\n{1}, {T}, Remove X ki counters from "
                "this creature: Target creature gets -X/-X until end of turn."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="place_counter",
                        counter_kind="ki",
                        scope="you",
                        raw="put a ki counter on ~",
                    ),
                ),
            )
        ),
    ),
    "seek_matters": (
        {
            "name": "Adherent's Heirloom",
            "type_line": "Artifact",
            "oracle_text": (
                "When this artifact enters, seek a creature card of the most "
                "prevalent creature type in your library.\n{T}: Add one mana of "
                "any color. Spend this mana only to cast a creature spell."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="seek",
                        scope="you",
                        raw="seek a creature card",
                    ),
                ),
            )
        ),
    ),
    "specialize_matters": (
        {
            "name": "Alora, Rogue Companion",
            "type_line": "Legendary Creature — Halfling Rogue",
            "oracle_text": (
                "Specialize {2}\nWhenever you attack, up to one target attacking "
                "creature can't be blocked this turn. At the beginning of the next "
                "end step, return that creature to its owner's hand."
            ),
            "keywords": ["Specialize"],
        },
        # specialize is read off the Scryfall keyword array, not the IR structure,
        # so a bare non-None IR is enough to route the hybrid to the IR path.
        _ir(),
    ),
    # Group "bending" — detected by the kept word-detector mirror
    # (_IR_KEPT_DETECTORS), which scans the oracle text directly, so any non-None
    # IR routes the hybrid to the IR path.
    "airbend_matters": (
        {
            "name": "Airbender Ascension",
            "type_line": "Enchantment",
            "oracle_text": (
                "When this enchantment enters, airbend up to one target creature.\n"
                "Whenever a creature you control enters, put a quest counter on "
                "this enchantment.\nAt the beginning of your end step, if this "
                "enchantment has four or more quest counters on it, exile up to one "
                "target creature you control, then return it to the battlefield "
                "under its owner's control."
            ),
        },
        _ir(),
    ),
    "earthbend_matters": (
        {
            "name": "Earthen Ally",
            "type_line": "Creature — Human Soldier Ally",
            "oracle_text": (
                "This creature gets +1/+0 for each color among Allies you "
                "control.\n{2}{W}{U}{B}{R}{G}: Earthbend 5. (Target land you "
                "control becomes a 0/0 creature with haste that's still a land. "
                "Put five +1/+1 counters on it. When it dies or is exiled, return "
                "it to the battlefield tapped.)"
            ),
        },
        _ir(),
    ),
    "waterbend_matters": (
        {
            "name": "Spirit Water Revival",
            "type_line": "Sorcery",
            "oracle_text": (
                "As an additional cost to cast this spell, you may waterbend {6}. "
                "(While paying a waterbend cost, you can tap your artifacts and "
                "creatures to help. Each one pays for {1}.)\nDraw two cards. If "
                "this spell's additional cost was paid, instead shuffle your "
                "graveyard into your library, draw seven cards, and you have no "
                "maximum hand size for the rest of the game.\nExile Spirit Water "
                "Revival."
            ),
        },
        _ir(),
    ),
    "firebending_matters": (
        {
            "name": "Fire Lord Azula",
            "type_line": "Legendary Creature — Human Noble",
            "oracle_text": (
                "Firebending 2 (Whenever this creature attacks, add {R}{R}. This "
                "mana lasts until end of combat.)\nWhenever you cast a spell while "
                "Fire Lord Azula is attacking, copy that spell. You may choose new "
                "targets for the copy. (A copy of a permanent spell becomes a "
                "token.)"
            ),
        },
        _ir(),
    ),
    # Group "set-mechanics" — celebration / coven / outlaw / snow / lessons detect
    # from the kept word-detector mirror (_IR_KEPT_DETECTORS, scans oracle text);
    # enlist / companion read the Scryfall keyword array. All route on any non-None
    # IR.
    "celebration_matters": (
        {
            "name": "Tuinvale Guide",
            "type_line": "Creature — Faerie Scout",
            "oracle_text": (
                "Flying\nCelebration — This creature gets +1/+0 and has lifelink "
                "as long as two or more nonland permanents entered the battlefield "
                "under your control this turn."
            ),
            "keywords": ["Flying", "Celebration"],
        },
        _ir(),
    ),
    "coven_matters": (
        {
            "name": "Leinore, Autumn Sovereign",
            "type_line": "Legendary Creature — Human Noble",
            "oracle_text": (
                "Coven — At the beginning of combat on your turn, put a +1/+1 "
                "counter on up to one target creature you control. Then if you "
                "control three or more creatures with different powers, draw a card."
            ),
            "keywords": ["Coven"],
        },
        _ir(),
    ),
    "outlaw_matters": (
        {
            "name": "Laughing Jasper Flint",
            "type_line": "Legendary Creature — Lizard Rogue",
            "oracle_text": (
                "Creatures you control but don't own are Mercenaries in addition "
                "to their other types.\nAt the beginning of your upkeep, exile the "
                "top X cards of target opponent's library, where X is the number of "
                "outlaws you control. Until end of turn, you may cast spells from "
                "among those cards, and mana of any type can be spent to cast those "
                "spells."
            ),
        },
        _ir(),
    ),
    "snow_matters": (
        {
            "name": "Diamond Faerie",
            "type_line": "Snow Creature — Faerie",
            "oracle_text": (
                "Flying\n{1}{S}: Snow creatures you control get +1/+1 until end of "
                "turn. ({S} can be paid with one mana from a snow source.)"
            ),
            "keywords": ["Flying"],
        },
        _ir(),
    ),
    "lessons_matter": (
        {
            "name": "Sokka, Bold Boomeranger",
            "type_line": "Legendary Creature — Human Warrior Ally",
            "oracle_text": (
                "When Sokka enters, discard up to two cards, then draw that many "
                "cards.\nWhenever you cast an artifact or Lesson spell, put a "
                "+1/+1 counter on Sokka."
            ),
        },
        _ir(),
    ),
    "enlist_matters": (
        {
            "name": "Benalish Faithbonder",
            "type_line": "Creature — Human Cleric",
            "oracle_text": (
                "Vigilance\nEnlist (As this creature attacks, you may tap a "
                "nonattacking creature you control without summoning sickness. When "
                "you do, add its power to this creature's until end of turn.)"
            ),
            "keywords": ["Vigilance", "Enlist"],
        },
        # enlist is read off the Scryfall keyword array, so a bare non-None IR
        # routes the hybrid to the IR path.
        _ir(),
    ),
    "companion_keyword": (
        {
            "name": "Lutri, the Spellchaser",
            "type_line": "Legendary Creature — Elemental Otter",
            "oracle_text": (
                "Companion — Each nonland card in your starting deck has a "
                "different name. (If this card is your chosen companion, you may "
                "put it into your hand from outside the game for {3} as a "
                "sorcery.)\nFlash\nWhen Lutri enters, if you cast it, copy target "
                "instant or sorcery spell you control. You may choose new targets "
                "for the copy."
            ),
            "keywords": ["Companion", "Flash"],
        },
        # companion is read off the Scryfall keyword array → bare non-None IR.
        _ir(),
    ),
    # Group "structural" — backed by a STRUCTURED IR shape (effect category /
    # grant subject / trigger event+scope), except facedown + voting which use the
    # kept word-detector mirror (oracle scan → bare IR).
    "token_doubling": (
        {
            "name": "Parallel Lives",
            "type_line": "Enchantment",
            "oracle_text": (
                "If an effect would create one or more tokens under your control, "
                "it creates twice that many of those tokens instead."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="token_doubling",
                        scope="you",
                        raw="creates twice that many tokens",
                    ),
                ),
            )
        ),
    ),
    "spell_copy_matters": (
        {
            "name": "Twincast",
            "type_line": "Instant",
            "oracle_text": "Copy target instant or sorcery spell. You may choose new "
            "targets for the copy.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="spell_copy",
                        scope="you",
                        raw="Copy target instant or sorcery spell.",
                    ),
                ),
            )
        ),
    ),
    "counters_matter": (
        {
            "name": "Steady Aim",
            "type_line": "Instant",
            "oracle_text": (
                "Put two +1/+1 counters on target creature. It gains "
                "indestructible until end of turn."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="place_counter",
                        scope="you",
                        counter_kind="p1p1",
                        raw="Put two +1/+1 counters on target creature.",
                    ),
                ),
            )
        ),
    ),
    "goad_matters": (
        {
            "name": "Disrupt Decorum",
            "type_line": "Sorcery",
            "oracle_text": "Goad all creatures your opponents control. (Until your "
            "next turn, those creatures attack each combat if able and attack a "
            "player other than you if able.)",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="goad_all",
                        scope="opp",
                        raw="Goad all creatures your opponents control.",
                    ),
                ),
            )
        ),
    ),
    "damage_doubling": (
        {
            "name": "Fiery Emancipation",
            "type_line": "Enchantment",
            "oracle_text": (
                "If a source you control would deal damage to a permanent or "
                "player, it deals triple that damage to that permanent or player "
                "instead."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="damage_doubling",
                        scope="you",
                        raw="it deals triple that damage instead",
                    ),
                ),
            )
        ),
    ),
    "counter_move": (
        {
            "name": "Scrounging Bandar",
            "type_line": "Creature — Cat Monkey",
            "oracle_text": (
                "This creature enters with two +1/+1 counters on it.\nAt the "
                "beginning of your upkeep, you may move any number of +1/+1 "
                "counters from this creature onto another target creature."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="counter_move",
                        scope="you",
                        raw="move +1/+1 counters from ~ onto another creature",
                    ),
                ),
            )
        ),
    ),
    "all_creatures_kw_grant": (
        {
            "name": "Angel's Trumpet",
            "type_line": "Artifact",
            "oracle_text": (
                "All creatures have vigilance.\nAt the beginning of each player's "
                "end step, tap all untapped creatures that player controls that "
                "didn't attack this turn. This artifact deals damage to the player "
                "equal to the number of creatures tapped this way."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        counter_kind="vigilance",
                        subject=Filter(card_types=("Creature",), controller="any"),
                    ),
                ),
            )
        ),
    ),
    "nonhuman_attackers": (
        {
            "name": "Winota, Joiner of Forces",
            "type_line": "Legendary Creature — Human Warrior",
            "oracle_text": (
                "Whenever a non-Human creature you control attacks, look at the "
                "top six cards of your library. You may put a Human creature card "
                "from among them onto the battlefield tapped and attacking. It "
                "gains indestructible until end of turn. Put the rest of the cards "
                "on the bottom of your library in a random order."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="attacks",
                    subject=Filter(
                        card_types=("Creature",),
                        controller="you",
                        predicates=("NotSubtype:Human",),
                    ),
                ),
            )
        ),
    ),
    "opponent_draw_matters": (
        {
            "name": "Underworld Dreams",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever an opponent draws a card, this enchantment deals 1 "
                "damage to that player."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="drawn", scope="opp"),
            )
        ),
    ),
    # draw_matters ← a `drawn` trigger with scope != "opp" (Chasm Skulker's "Whenever
    # you draw a card, put a +1/+1 counter on this creature" — phase parses a literal
    # "Whenever you draw a card" as scope 'any', NOT 'you', which the scope-gated
    # structural arm keeps; an OPP-scoped drawn trigger is the separate
    # opponent_draw_matters punisher lane, excluded). The past-tense draw-COUNT payoff
    # has no `drawn` trigger and rides the byte-identical _IR_KEPT_DETECTORS mirror
    # instead. ADR-0027 β.
    "draw_matters": (
        {
            "name": "Chasm Skulker",
            "type_line": "Creature — Squid Horror",
            "oracle_text": (
                "Whenever you draw a card, put a +1/+1 counter on this creature.\n"
                "When this creature dies, create X 1/1 blue Squid creature tokens "
                "with islandwalk, where X is the number of +1/+1 counters on this "
                "creature. (They can't be blocked as long as defending player "
                "controls an Island.)"
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="drawn", scope="any"),
            )
        ),
    ),
    # discard_matters ← a `discarded` trigger with scope != "opp" (Basking Rootwalla's
    # Madness — phase parses "If you discard this card, …" as a `discarded` trigger
    # scope 'you', which the scope-gated structural arm keeps; an OPP-scoped discarded
    # trigger is the separate opponent_discard punisher lane, excluded). The loot/
    # rummage OUTLET ("draw N cards, then discard") has no `discarded` trigger and
    # rides the byte-identical _LOOT_FULLTEXT_RE _IR_KEPT_DETECTORS mirror instead.
    # ADR-0027.
    "discard_matters": (
        {
            "name": "Basking Rootwalla",
            "type_line": "Creature — Lizard",
            "oracle_text": (
                "{1}{G}: This creature gets +2/+2 until end of turn. Activate only "
                "once each turn.\n"
                "Madness {0} (If you discard this card, discard it into exile. When "
                "you do, cast it for its madness cost or put it into your graveyard.)"
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="discarded", scope="you"),
            )
        ),
    ),
    # opponent_discard ← a `discard` EFFECT scope "opp" (the forced-OPPONENT-discard /
    # hand-attack lane — Mind Rot's "target player discards two cards"). DISJOINT from
    # discard_matters: opponent_discard reads the `discard` EFFECT scope 'opp', NOT the
    # `discarded` self-discard TRIGGER. The structural arm fires the 7 forced-opp
    # discards phase scopes 'opp'; the directed "target player discards" (scope 'any')
    # and "whenever an opponent discards" payoffs (a `discarded` trigger) ride the
    # byte-identical _OPPONENT_DISCARD_MIRROR _IR_KEPT_DETECTORS row. ADR-0027.
    "opponent_discard": (
        {
            "name": "Mind Rot",
            "type_line": "Sorcery",
            "oracle_text": "Target player discards two cards.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="discard",
                        scope="opp",
                        raw="target player discards two cards",
                    ),
                ),
            )
        ),
    ),
    # facedown + voting detect from the kept word-detector mirror, which scans the
    # oracle text directly, so any non-None IR routes the hybrid to the IR path.
    "facedown_matters": (
        {
            "name": "Etrata, Deadly Fugitive",
            "type_line": "Legendary Creature — Vampire Assassin",
            "oracle_text": (
                'Deathtouch\nFace-down creatures you control have "{2}{U}{B}: Turn '
                "this creature face up. If you can't, exile it, then you may cast "
                'the exiled card without paying its mana cost."\nWhenever an '
                "Assassin you control deals combat damage to an opponent, cloak "
                "the top card of that player's library."
            ),
        },
        _ir(),
    ),
    "voting_matters": (
        {
            "name": "Capital Punishment",
            "type_line": "Sorcery",
            "oracle_text": (
                "Council's dilemma — Starting with you, each player votes for "
                "death or taxes. Each opponent sacrifices a creature of their "
                "choice for each death vote and discards a card for each taxes "
                "vote."
            ),
        },
        _ir(),
    ),
    # ADR-0027 restriction-narrow batch. monarch ← Condition(ismonarch) on the
    # ability (the "if you're the monarch" gate phase keeps as a condition, lifted
    # in extract_signals_ir); saddle ← a `saddle` marker effect (project's
    # _narrow_mechanic_refs appends it for a "becomes saddled" grant phase folded
    # into a restriction carrier); soulbond ← a `soulbond` marker effect (appended
    # for a "paired with a creature with soulbond" reference on a non-keyword card).
    "monarch_matters": (
        {
            "name": "Throne Warden",
            "type_line": "Creature — Human Soldier",
            "oracle_text": (
                "At the beginning of your end step, if you're the monarch, put a "
                "+1/+1 counter on this creature."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="end_step"),
                condition=Condition(kind="ismonarch"),
                effects=(
                    Effect(
                        category="place_counter",
                        counter_kind="p1p1",
                        raw="put a +1/+1 counter on ~",
                    ),
                ),
            )
        ),
    ),
    "saddle_matters": (
        {
            "name": "Guidelight Matrix",
            "type_line": "Artifact",
            "oracle_text": (
                "When this artifact enters, draw a card.\n{2}, {T}: Target Mount "
                "you control becomes saddled until end of turn. Activate only as a "
                "sorcery.\n{2}, {T}: Target Vehicle you control becomes an artifact "
                "creature until end of turn."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(
                    Effect(
                        category="saddle",
                        scope="you",
                        raw="Target Mount you control becomes saddled",
                    ),
                ),
            )
        ),
    ),
    "soulbond_matters": (
        {
            "name": "Flowering Lumberknot",
            "type_line": "Creature — Plant",
            "oracle_text": (
                "This creature can't attack or block unless it's paired with a "
                "creature with soulbond."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="soulbond",
                        scope="you",
                        raw="paired with a creature with soulbond",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 trigger-other raw-marker batch. Each tail card is a PAYOFF trigger
    # phase flattened to Trigger(event="other") — the consequence is a typed effect,
    # the trigger condition survives only in the effect raw, and
    # project._narrow_trigger_other_refs appends a precise marker effect read via
    # _DOER_EFFECT_KEYS. coin_flip ← "Whenever you win a coin flip" (Chance
    # Encounter); discover ← "Whenever you discover, discover again" (Curator);
    # ninjutsu ← "Whenever you activate a ninjutsu ability" (Satoru); ring ←
    # "Whenever the Ring tempts you" (Faramir).
    "coin_flip": (
        {
            "name": "Chance Encounter",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever you win a coin flip, put a luck counter on this "
                "enchantment.\nAt the beginning of your upkeep, if this enchantment "
                "has ten or more luck counters on it, you win the game."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="coin_flip",
                        scope="you",
                        raw="Whenever you win a coin flip, put a luck counter on ~.",
                    ),
                ),
            )
        ),
    ),
    "discover_matters": (
        {
            "name": "Curator of Sun's Creation",
            "type_line": "Creature — Human Artificer",
            "oracle_text": (
                "Whenever you discover, discover again for the same value. This "
                "ability triggers only once each turn."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="discover",
                        scope="you",
                        raw="Whenever you discover, discover again for the same value.",
                    ),
                ),
            )
        ),
    ),
    "ninjutsu_matters": (
        {
            "name": "Satoru Umezawa",
            "type_line": "Legendary Creature — Human Ninja",
            "oracle_text": (
                "Whenever you activate a ninjutsu ability, look at the top three "
                "cards of your library. Put one of them into your hand and the rest "
                "on the bottom of your library in any order. This ability triggers "
                "only once each turn.\nEach creature card in your hand has ninjutsu "
                "{2}{U}{B}. ({2}{U}{B}, Return an unblocked attacker you control to "
                "hand: Put this card onto the battlefield from your hand tapped and "
                "attacking.)"
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="ninjutsu",
                        scope="you",
                        raw=(
                            "Whenever you activate a ninjutsu ability, look at the "
                            "top three cards of your library."
                        ),
                    ),
                ),
            )
        ),
    ),
    "ring_matters": (
        {
            "name": "Faramir, Field Commander",
            "type_line": "Legendary Creature — Human Soldier",
            "oracle_text": (
                "At the beginning of your end step, if a creature died under your "
                "control this turn, draw a card.\nWhenever the Ring tempts you, if "
                "you chose a creature other than Faramir, Field Commander as your "
                "Ring-bearer, create a 1/1 white Human Soldier creature token."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="ring_tempt",
                        scope="you",
                        raw=(
                            "Whenever the Ring tempts you, if you chose a creature "
                            "other than ~ as your Ring-bearer, create a token."
                        ),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 conferred-keyword re-parse batch. Each tail card GRANTS a keyword/
    # ability to a CLASS of objects — phase folds the grant into a carrier and the
    # granted keyword survives only in raw, so project._narrow_conferred_keyword_refs
    # appends a precise marker effect read by extract_signals_ir. affinity ←
    # "spells you cast have affinity for artifacts" (Tezzeret); damage_reflect ← the
    # quoted reflection grant 'Slivers you control have "Whenever ~ is dealt damage,
    # ~ deals that much damage to ..."' (Spiteful Sliver); evasion_denial ← the
    # generic-landwalk umbrella (Staff of the Ages).
    "affinity_type": (
        {
            "name": "Tezzeret, Master of the Bridge",
            "type_line": "Legendary Planeswalker — Tezzeret",
            "oracle_text": (
                "Creature and planeswalker spells you cast have affinity for "
                "artifacts. (They cost {1} less to cast for each artifact you "
                "control.)\n+2: Tezzeret deals X damage to each opponent, where X "
                "is the number of artifacts you control. You gain X life.\n−3: "
                "Return target artifact card from your graveyard to your hand.\n"
                "−8: Exile the top ten cards of your library. Put all artifact "
                "cards from among them onto the battlefield."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="affinity",
                        scope="you",
                        raw=(
                            "Creature and planeswalker spells you cast have "
                            "affinity for artifacts."
                        ),
                    ),
                ),
            )
        ),
    ),
    "damage_reflect": (
        {
            "name": "Spiteful Sliver",
            "type_line": "Creature — Sliver",
            "oracle_text": (
                'Sliver creatures you control have "Whenever this creature is '
                "dealt damage, it deals that much damage to target player or "
                'planeswalker."'
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="damage_reflect",
                        scope="you",
                        raw=(
                            'Sliver creatures you control have "Whenever this '
                            "creature is dealt damage, it deals that much damage "
                            "to target player or planeswalker"
                        ),
                    ),
                ),
            )
        ),
    ),
    "evasion_denial": (
        {
            "name": "Staff of the Ages",
            "type_line": "Artifact",
            "oracle_text": (
                "Creatures with landwalk abilities can be blocked as though they "
                "didn't have those abilities."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="evasion_denial",
                        scope="opp",
                        raw=(
                            "Creatures with landwalk abilities can be blocked as "
                            "though they didn't have those abilities."
                        ),
                    ),
                ),
            )
        ),
    ),
    # The go-wide scaling lane. The IR mirrors a board_count marker — a count operand
    # over the GENERIC creature board (Crusader's P/T == number of creatures you
    # control), the headline source the structured projection now recovers.
    "creatures_matter": (
        {
            "name": "Crusader of Odric",
            "type_line": "Creature — Human Soldier",
            "oracle_text": (
                "Crusader of Odric's power and toughness are each equal to the "
                "number of creatures you control."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="board_count",
                        scope="you",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        amount=Quantity(
                            op="count",
                            subject=Filter(card_types=("Creature",), controller="you"),
                        ),
                        raw="equal to the number of creatures you control",
                    ),
                ),
            )
        ),
    ),
    # The sacrifice-creatures-for-+1/+1-counters keyword lane (CR 702.82). The IR
    # mirror is the Scryfall "Devour" keyword (Mycoloth, the canonical Devour
    # build-around) read via _IR_KEYWORD_MAP — the structural source that keeps the
    # "Devour Intellect" flavor word and the "Devour in Flames" card name out. Like
    # specialize, devour is read off the Scryfall keyword array, not the IR
    # structure, so a bare non-None IR routes the hybrid to the IR path.
    "devour_matters": (
        {
            "name": "Mycoloth",
            "type_line": "Creature — Fungus",
            "oracle_text": (
                "Devour 2 (As this creature enters, you may sacrifice any number "
                "of creatures. It enters with twice that many +1/+1 counters on "
                "it.)\nAt the beginning of your upkeep, create a 1/1 green "
                "Saproling creature token for each +1/+1 counter on this creature."
            ),
            "keywords": ["Devour"],
        },
        _ir(),
    ),
    # The Blood token-subtype synergy lane (CR 111.10g). The IR mirror is a
    # make_token Effect whose subject Filter carries the Blood subtype (Bloodtithe
    # Harvester, a canonical Blood maker) — the structural maker the lane reads. The
    # sacrifice-payoff and choose-list / granted-ability maker paths are exercised by
    # the dedicated tests below.
    "blood_matters": (
        {
            "name": "Bloodtithe Harvester",
            "type_line": "Creature — Vampire",
            "oracle_text": (
                "When this creature enters, create a Blood token. (It's an "
                'artifact with "{1}, {T}, Discard a card, Sacrifice this token: '
                'Draw a card.")\n{T}, Sacrifice this creature: Target creature '
                "gets -X/-X until end of turn, where X is twice the number of "
                "Blood tokens you control. Activate only as a sorcery."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="make_token",
                        scope="you",
                        subject=Filter(card_types=("Artifact",), subtypes=("Blood",)),
                        raw="create a Blood token",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 tail-supplement batch ───────────────────────────────────────
    # Each pairs a real gap card with the IR marker the supplement appended for it.
    # Boast amplifier (Birgi) — the "can boast twice" static phase drops is recovered
    # as a `boast` dropped-static face marker.
    "boast_matters": (
        {
            "name": "Birgi, God of Storytelling",
            "type_line": "Legendary Creature — God",
            "oracle_text": (
                "Whenever you cast a spell, add {R}. Until end of turn, you don't "
                "lose this mana as steps and phases end.\nCreatures you control can "
                "boast twice during each of your turns rather than once."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(Effect(category="boast", scope="you", raw="can boast twice"),),
            )
        ),
    ),
    # Connive GRANTER (Security Bypass) — phase swallows the quoted "it connives"
    # grant into the Enchant parse; the Scryfall connive keyword lifts it.
    "connive_matters": (
        {
            "name": "Security Bypass",
            "type_line": "Enchantment — Aura",
            "oracle_text": (
                "Enchant creature\nAs long as enchanted creature is attacking "
                "alone, it can't be blocked.\nEnchanted creature has \"Whenever "
                'this creature deals combat damage to a player, it connives."'
            ),
            "keywords": ["Enchant", "Connive"],
        },
        # connive is read off the Scryfall keyword array, so a bare non-None IR
        # routes the hybrid to the IR path.
        _ir(keywords=("Enchant",)),
    ),
    # End-the-turn (Obeka) — phase's end_the_turn effect (the supplement category
    # reconciled to the lane's binding string).
    "end_the_turn": (
        {
            "name": "Obeka, Brute Chronologist",
            "type_line": "Legendary Creature — Ogre Wizard",
            "oracle_text": ("{T}: The player whose turn it is may end the turn."),
        },
        _ir(
            Ability(
                kind="activated",
                cost="tap",
                effects=(
                    Effect(
                        category="end_the_turn",
                        scope="any",
                        raw="The player whose turn it is may end the turn.",
                    ),
                ),
            )
        ),
    ),
    # Exhaust PAYOFF (Pit Automaton) — a delayed exhaust trigger inside an activated
    # ability, recovered by the now-ungated exhaust marker.
    "exhaust_matters": (
        {
            "name": "Pit Automaton",
            "type_line": "Artifact Creature — Construct",
            "oracle_text": (
                "Defender\n{T}: Add {C}{C}. Spend this mana only to activate "
                "abilities.\n{2}, {T}: When you next activate an exhaust ability "
                "that isn't a mana ability this turn, copy it. You may choose new "
                "targets for the copy."
            ),
            "keywords": ["Defender"],
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(
                    Effect(
                        category="exhaust",
                        scope="you",
                        raw="activate an exhaust ability",
                    ),
                ),
            )
        ),
    ),
    # Extra end step (Y'shtola) — the dropped "additional end step" clause recovered
    # as an `extra_end` dropped-static face marker.
    "extra_end_step": (
        {
            "name": "Y'shtola Rhul",
            "type_line": "Legendary Creature — Hyur Cleric",
            "oracle_text": (
                "At the beginning of your end step, exile target creature you "
                "control, then return it to the battlefield under its owner's "
                "control. Then if it's the first end step of the turn, there is an "
                "additional end step after this step."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="extra_end",
                        scope="you",
                        raw="additional end step",
                    ),
                ),
            )
        ),
    ),
    # Madness payoff (Anje) — the "if it has madness" condition recovered as a
    # `madness` payoff marker (distinct from the "has madness" grant).
    "madness_matters": (
        {
            "name": "Anje Falkenrath",
            "type_line": "Legendary Creature — Vampire",
            "oracle_text": (
                "Haste\n{T}, Discard a card: Draw a card.\nWhenever you discard a "
                "card, if it has madness, untap Anje Falkenrath."
            ),
            "keywords": ["Haste"],
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="madness",
                        scope="you",
                        raw="if it has madness",
                    ),
                ),
            )
        ),
    ),
    # Mutate payoff (Pollywog) — keyword-less cast-payoff recovered as a `mutate`
    # marker from "if it has mutate".
    "mutate_matters": (
        {
            "name": "Pollywog Symbiote",
            "type_line": "Creature — Frog",
            "oracle_text": (
                "Each creature spell you cast costs {1} less to cast if it has "
                "mutate.\nWhenever you cast a creature spell, if it has mutate, "
                "draw a card, then discard a card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(category="mutate", scope="you", raw="if it has mutate"),
                ),
            )
        ),
    ),
    # Phasing PAYOFF (The War Doctor) — the event='other' "permanents phase out"
    # payoff recovered as a `phasing` marker.
    "phasing_matters": (
        {
            "name": "The War Doctor",
            "type_line": "Legendary Creature — Time Lord Doctor",
            "oracle_text": (
                "Whenever one or more other permanents phase out and whenever one "
                "or more other cards are put into exile from anywhere, put a time "
                "counter on The War Doctor."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="phasing",
                        scope="you",
                        raw="permanents phase out",
                    ),
                ),
            )
        ),
    ),
    # Trigger-doubling GRANT (The Masamune) — the granted/quoted "triggers an
    # additional time" recovered as a `trigger_doubling` dropped-static face marker.
    "trigger_doubling": (
        {
            "name": "The Masamune",
            "type_line": "Legendary Artifact — Equipment",
            "oracle_text": (
                "As long as equipped creature is attacking, it has first strike "
                'and must be blocked if able.\nEquipped creature has "If a creature '
                "dying causes a triggered ability of this creature or an emblem you "
                'own to trigger, that ability triggers an additional time."\n'
                "Equip {2}"
            ),
            "keywords": ["Equip"],
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="trigger_doubling",
                        scope="you",
                        raw="triggers an additional time",
                    ),
                ),
            )
        ),
    ),
    # Experience SCALER (Atreus) — "for each experience counter you have" stamps
    # op="experience" on the draw operand.
    "experience_matters": (
        {
            "name": "Atreus, Impulsive Son",
            "type_line": "Legendary Creature — God Archer",
            "oracle_text": (
                "Reach\n{3}, {T}: Draw a card for each experience counter you "
                "have, then discard a card. Atreus deals 2 damage to each opponent."
            ),
            "keywords": ["Reach"],
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(
                    Effect(
                        category="draw",
                        scope="you",
                        amount=Quantity(op="experience", factor=1),
                        raw="Draw a card for each experience counter you have",
                    ),
                ),
            )
        ),
    ),
    # Explore (Topography Tracker) — read off the Scryfall explore keyword (the
    # authoritative path covering Map-token / granted-ability explore cards).
    "explore_matters": (
        {
            "name": "Topography Tracker",
            "type_line": "Creature — Elf Scout",
            "oracle_text": (
                "When this creature enters, create a Map token.\nIf a creature you "
                "control would explore, instead it explores, then it explores "
                "again."
            ),
            "keywords": ["Explore"],
        },
        # explore is read off the Scryfall keyword array, so a bare non-None IR
        # routes the hybrid to the IR path.
        _ir(),
    ),
    # Foretell payoff (Niko) — the Foretold predicate on a counted subject Filter.
    "foretell_matters": (
        {
            "name": "Niko Defies Destiny",
            "type_line": "Enchantment — Saga",
            "oracle_text": (
                "I — You gain 2 life for each foretold card you own in exile.\n"
                "II — Add {W}{U}. Spend this mana only to foretell cards or cast "
                "spells that have foretell.\nIII — Return target card with foretell "
                "from your graveyard to your hand."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="gain_life",
                        scope="any",
                        amount=Quantity(
                            op="multiply",
                            factor=2,
                            subject=Filter(
                                card_types=("Card",),
                                predicates=("Foretold", "Owned", "InZone"),
                            ),
                        ),
                        raw="gain 2 life for each foretold card you own in exile",
                    ),
                ),
            )
        ),
    ),
    # Scavenge GRANTER (Varolz) — the graveyard-wide "has scavenge" grant recovered
    # as a `scavenge` dropped-static face marker.
    "scavenge_fuel": (
        {
            "name": "Varolz, the Scar-Striped",
            "type_line": "Legendary Creature — Troll Warrior",
            "oracle_text": (
                "Each creature card in your graveyard has scavenge. The scavenge "
                "cost is equal to its mana cost.\nSacrifice another creature: "
                "Regenerate Varolz, the Scar-Striped."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="scavenge",
                        scope="you",
                        raw="has scavenge",
                    ),
                ),
            )
        ),
    ),
    # Scry-replacement payoff (Kenessos) — the "if you would scry a number of cards"
    # replacement recovered as a `scry_surveil` dropped-static face marker.
    "scry_surveil_matters": (
        {
            "name": "Kenessos, Priest of Thassa",
            "type_line": "Legendary Creature — Triton Wizard",
            "oracle_text": (
                "If you would scry a number of cards, scry that many cards plus "
                "one instead.\n{3}{G/U}: Look at the top card of your library. If "
                "it's a Kraken, Leviathan, Octopus, or Serpent creature card, you "
                "may put it onto the battlefield."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="scry_surveil",
                        scope="you",
                        raw="if you would scry a number of cards",
                    ),
                ),
            )
        ),
    ),
    # Extra beginning phase (Sphinx of the Second Sun) — "an additional beginning
    # phase after this phase" recovered as BOTH an `extra_upkeep` and an `extra_draw`
    # dropped-static face marker (CR 501.1). extra_draw_step fired 0 in the IR before.
    "extra_draw_step": (
        {
            "name": "Sphinx of the Second Sun",
            "type_line": "Creature — Sphinx",
            "oracle_text": (
                "Flying\nAt the beginning of each of your postcombat main phases, "
                "there is an additional beginning phase after this phase. (The "
                "beginning phase includes the untap, upkeep, and draw steps.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="extra_draw",
                        scope="you",
                        raw="additional beginning phase",
                    ),
                ),
            )
        ),
    ),
    "extra_upkeep": (
        {
            "name": "Sphinx of the Second Sun",
            "type_line": "Creature — Sphinx",
            "oracle_text": (
                "Flying\nAt the beginning of each of your postcombat main phases, "
                "there is an additional beginning phase after this phase. (The "
                "beginning phase includes the untap, upkeep, and draw steps.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="extra_upkeep",
                        scope="you",
                        raw="additional beginning phase",
                    ),
                ),
            )
        ),
    ),
    # Modal counter (Ertai Resurrected) — "• Counter target spell, activated ability,
    # or triggered ability" recovered as a `counter_spell` dropped-static face marker
    # (phase keeps only the `choose` header). CR 701.5.
    "counter_control": (
        {
            "name": "Ertai Resurrected",
            "type_line": "Legendary Creature — Phyrexian Human Wizard",
            "oracle_text": (
                "Flash\nWhen Ertai Resurrected enters, choose up to one —\n"
                "• Counter target spell, activated ability, or triggered ability. "
                "Its controller draws a card.\n• Destroy another target creature or "
                "planeswalker. Its controller draws a card."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="counter_spell",
                        scope="any",
                        raw="counter target spell",
                    ),
                ),
            )
        ),
    ),
    # Modal can't-block (Breeches) — "• Target creature can't block this turn"
    # recovered as a `cant_block` dropped-static face marker (phase keeps only the
    # `choose` header). CR 509.
    "cant_block_grant": (
        {
            "name": "Breeches, Eager Pillager",
            "type_line": "Legendary Creature — Goblin Pirate",
            "oracle_text": (
                "First strike\nWhenever a Pirate you control attacks, choose one "
                "that hasn't been chosen this turn —\n• Create a Treasure token.\n"
                "• Target creature can't block this turn.\n• Exile the top card of "
                "your library. You may play it this turn."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cant_block",
                        scope="any",
                        raw="• Target creature can't block",
                    ),
                ),
            )
        ),
    ),
    # Land exchange (Political Trickery) — phase's `gain_control` effect with
    # subject=None whose raw carries the "exchange control of … land" phrase, read by
    # the _LAND_EXCHANGE_RAW fallback (phase never binds the land-typed object).
    "land_exchange": (
        {
            "name": "Political Trickery",
            "type_line": "Sorcery",
            "oracle_text": (
                "Exchange control of target land you control and target land an "
                "opponent controls. (This effect lasts indefinitely.)"
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="gain_control",
                        scope="any",
                        subject=None,
                        raw=(
                            "Exchange control of target land you control and "
                            "target land an opponent controls."
                        ),
                    ),
                ),
            )
        ),
    ),
    # Myriad granter (Legion Loyalty) — "Creatures you control have myriad" carries
    # counter_kind='myriad' on a grant_keyword effect (the granter discriminator;
    # makers ride the keyword array, granters don't).
    "myriad_grant": (
        {
            "name": "Legion Loyalty",
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures you control have myriad. (Whenever a creature with "
                "myriad attacks, for each opponent other than defending player, "
                "you may create a token copy that's tapped and attacking that "
                "player or a planeswalker they control. Exile the tokens at end "
                "of combat.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        counter_kind="myriad",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw="Creatures you control have myriad.",
                    ),
                ),
            )
        ),
    ),
    # Convoke granter (Chief Engineer) — "Artifact spells you cast have convoke"
    # carries counter_kind='convoke' on a cast_with_keyword effect (the keyword-less
    # granter; makers ride the keyword array).
    "convoke_matters": (
        {
            "name": "Chief Engineer",
            "type_line": "Creature — Vedalken Artificer",
            "oracle_text": (
                "Artifact spells you cast have convoke. (Your creatures can help "
                "cast those spells. Each creature you tap while casting an artifact "
                "spell pays for {1} or one mana of that creature's color.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cast_with_keyword",
                        scope="you",
                        counter_kind="convoke",
                        raw="Artifact spells you cast have convoke.",
                    ),
                ),
            )
        ),
    ),
    # Tapped-count payoff (Throne of the God-Pharaoh) — the effect VALUE counts your
    # tapped creatures (a Tapped predicate on amount.subject, controller='you').
    "tapped_matters": (
        {
            "name": "Throne of the God-Pharaoh",
            "type_line": "Legendary Artifact",
            "oracle_text": (
                "At the beginning of your end step, each opponent loses life equal "
                "to the number of tapped creatures you control."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="end_step", scope="you"),
                effects=(
                    Effect(
                        category="lose_life",
                        scope="opp",
                        amount=Quantity(
                            op="count",
                            subject=Filter(
                                card_types=("Creature",),
                                controller="you",
                                predicates=("Tapped",),
                            ),
                        ),
                        raw=(
                            "each opponent loses life equal to the number of "
                            "tapped creatures you control"
                        ),
                    ),
                ),
            )
        ),
    ),
    # Multi-type anthem (Howlpack Resurgence) — a pump over a creature Filter naming
    # 2+ subtypes (a flat subtypes tuple, the phase shape the >=2 guard covers).
    "typed_anthem_multi": (
        {
            "name": "Howlpack Resurgence",
            "type_line": "Enchantment",
            "oracle_text": (
                "Flash\nEach creature you control that's a Wolf or a Werewolf "
                "gets +1/+1 and has trample."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",),
                            subtypes=("Wolf", "Werewolf"),
                            controller="you",
                        ),
                        raw=(
                            "Each creature you control that's a Wolf or a "
                            "Werewolf gets +1/+1 and has trample."
                        ),
                    ),
                ),
            )
        ),
    ),
    # Life doubling (Beacon of Immortality) — "double target player's life total"
    # routes to a `set_life` dropped-static face marker (the lane wants life
    # set/exchange/double; phase's bare `double` category isn't crosswalked).
    "life_total_set": (
        {
            "name": "Beacon of Immortality",
            "type_line": "Instant",
            "oracle_text": (
                "Double target player's life total. Shuffle Beacon of "
                "Immortality into its owner's library."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="set_life",
                        scope="any",
                        raw="Double target player's life total",
                    ),
                ),
            )
        ),
    ),
    # Energy producer (Aether Hub) — phase's `energy` effect category lights the lane.
    "energy_matters": (
        {
            "name": "Aether Hub",
            "type_line": "Land",
            "oracle_text": (
                "When this land enters, you get {E} (an energy counter).\n"
                "{T}: Add {C}.\n{T}, Pay {E}: Add one mana of any color."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="etb", scope="you"),
                effects=(
                    Effect(
                        category="energy",
                        scope="you",
                        raw="you get {E}",
                    ),
                ),
            )
        ),
    ),
    # Rad-counter maker (Nuclear Fallout) — the "rad counter(s)" clause phase mangles is
    # recovered as a `rad_counter` dropped-static face marker (scope opponents).
    "rad_counter_matters": (
        {
            "name": "Nuclear Fallout",
            "type_line": "Sorcery",
            "oracle_text": (
                "Each creature gets twice -X/-X until end of turn. Each player "
                "gets X rad counters."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="rad_counter",
                        scope="opp",
                        raw="rad counters",
                    ),
                ),
            )
        ),
    ),
    # Suspect doer (Case of the Stashed Skeleton) — "suspect it" (the verb buried
    # mid-clause) is recovered as a `suspect` dropped-static face marker.
    "suspect_matters": (
        {
            "name": "Case of the Stashed Skeleton",
            "type_line": "Enchantment — Case",
            "oracle_text": (
                "When this Case enters, create a 2/1 black Skeleton creature "
                "token and suspect it. (It has menace and can't block.)\nTo "
                "solve — You control no suspected Skeletons.\nSolved — {1}{B}, "
                "Sacrifice this Case: Search your library for a card, put it "
                "into your hand, then shuffle."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(Effect(category="suspect", scope="you", raw="suspect"),),
            )
        ),
    ),
    # Venture / dungeon payoff (Gloom Stalker) — the dungeon-completion gate is read off
    # the condition kind 'completedadungeon'.
    "venture_matters": (
        {
            "name": "Gloom Stalker",
            "type_line": "Creature — Dwarf Ranger",
            "oracle_text": (
                "As long as you've completed a dungeon, this creature has "
                "double strike."
            ),
        },
        _ir(
            Ability(
                kind="static",
                condition=Condition(kind="completedadungeon"),
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        raw="this creature has double strike",
                    ),
                ),
            )
        ),
    ),
    # Crime payoff (Oko, the Ringleader) — the condition-form "if you've committed a
    # crime this turn" is recovered as a `crime` dropped-static face marker.
    "crimes_matter": (
        {
            "name": "Oko, the Ringleader",
            "type_line": "Legendary Planeswalker — Oko",
            "oracle_text": (
                "At the beginning of combat on your turn, Oko becomes a copy of "
                "up to one target creature you control until end of turn, except "
                "he has hexproof.\n+1: Draw two cards. If you've committed a "
                "crime this turn, discard a card. Otherwise, discard two cards.\n"
                "−1: Create a 3/3 green Elk creature token."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="crime",
                        scope="you",
                        raw="if you've committed a crime",
                    ),
                ),
            )
        ),
    ),
    # Group mana (Magus of the Vineyard) — a ramp effect whose raw names a
    # non-controller recipient ("that player adds {G}{G}"), read by _GROUP_MANA_RAW
    # (phase has no recipient field, so the discriminator lives in the raw).
    "group_mana": (
        {
            "name": "Magus of the Vineyard",
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "At the beginning of each player's first main phase, that player "
                "adds {G}{G}."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="begin_main", scope="each"),
                effects=(
                    Effect(
                        category="ramp",
                        scope="any",
                        raw="that player adds {G}{G}",
                    ),
                ),
            )
        ),
    ),
    # ramp_matters ← a cat=="ramp" Effect on a NON-LAND card (the structural arm,
    # gated `not card_is_land`). Karametra's Acolyte's "{T}: Add an amount of {G}
    # equal to your devotion to green" is real recall the brittle "add {" regex
    # missed; phase types it as a `ramp` Mana effect.
    "ramp_matters": (
        {
            "name": "Karametra's Acolyte",
            "type_line": "Creature — Human Druid",
            "oracle_text": (
                "{T}: Add an amount of {G} equal to your devotion to green. "
                "(Each {G} in the mana costs of permanents you control counts "
                "toward your devotion to green.)"
            ),
        },
        _ir(
            Ability(
                kind="activated",
                effects=(
                    Effect(
                        category="ramp",
                        scope="any",
                        raw="{T}: Add an amount of {G} equal to your devotion",
                    ),
                ),
            )
        ),
    ),
    # Low-power payoff (Subira) — a Power:LE predicate on a you-controller Creature
    # Filter (the buff/etb shape's predicate phase drops, rebuilt by _LOW_POWER_REF),
    # read by _predicate_build_around_lanes.
    "low_power_matters": (
        {
            "name": "Subira, Tulzidi Caravanner",
            "type_line": "Legendary Creature — Human Shaman",
            "oracle_text": (
                "Haste\n{1}: Another target creature with power 2 or less can't "
                "be blocked this turn.\n{1}{R}, {T}, Discard your hand: Until end "
                "of turn, whenever a creature you control with power 2 or less "
                "deals combat damage to a player, draw a card."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="tap",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",),
                            controller="you",
                            predicates=("PtComparison:Power:LE:2",),
                        ),
                        raw="creature you control with power 2 or less",
                    ),
                ),
            )
        ),
    ),
    # power_matters ← the GE/GT twin of low_power_matters. Colossal Majesty is a
    # Ferocious upkeep payoff: phase carries the power threshold on the ability's
    # Condition.subject (a you-controlled Creature Filter with PtComparison:Power:GE:4),
    # read by the dedicated _condition_power_matters arm (CR 208 / 207.2c).
    "power_matters": (
        {
            "name": "Colossal Majesty",
            "type_line": "Enchantment",
            "oracle_text": (
                "At the beginning of your upkeep, if you control a creature with "
                "power 4 or greater, draw a card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="upkeep"),
                condition=Condition(
                    kind="controlstype",
                    subject=Filter(
                        card_types=("Creature",),
                        controller="you",
                        predicates=("PtComparison:Power:GE:4", "InZone"),
                    ),
                ),
                effects=(Effect(category="draw", scope="you"),),
            )
        ),
    ),
    # Conferred pay-life cost (Underworld Connections) — the "Pay 1 life:" inside a
    # granted quoted ability phase drops is recovered as a `life_payment` marker.
    "life_payment_insurance": (
        {
            "name": "Underworld Connections",
            "type_line": "Enchantment — Aura",
            "oracle_text": (
                'Enchant land\nEnchanted land has "{T}, Pay 1 life: Draw a card."'
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="life_payment",
                        scope="you",
                        raw="Pay 1 life:",
                    ),
                ),
            )
        ),
    ),
    # sacrifice_matters ← a you-sacrifice Effect (scope not opp/each, a non-land
    # subject, not a forced-opponent edict). Disciple of Bolas sacs "another
    # creature" — phase emits scope "any" with a Creature subject.
    "sacrifice_matters": (
        {
            "name": "Disciple of Bolas",
            "type_line": "Creature — Human Wizard",
            "oracle_text": (
                "When this creature enters, sacrifice another creature. You gain "
                "X life and draw X cards, where X is that creature's power."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="sacrifice",
                        scope="any",
                        subject=Filter(card_types=("Creature",), controller="any"),
                        raw="When ~ enters, sacrifice another creature. …",
                    ),
                ),
            )
        ),
    ),
    # removal_matters ← a `damage` / `destroy` Effect with a SINGLE-TARGET permanent
    # subject. Flame Slash deals 4 damage to a target Creature (phase emits a damage
    # effect, Creature subject, scope "any"); the regex no longer fires the lane.
    "removal_matters": (
        {
            "name": "Flame Slash",
            "type_line": "Sorcery",
            "oracle_text": "Flame Slash deals 4 damage to target creature.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="damage",
                        scope="any",
                        subject=Filter(card_types=("Creature",)),
                        amount=Quantity(op="fixed", factor=4),
                        raw="~ deals 4 damage to target creature.",
                    ),
                ),
            )
        ),
    ),
    # lifeloss_matters ← a structured `lose_life` Effect. Gray Merchant drains each
    # opponent (phase emits scope "any" for "each opponent loses N").
    "lifeloss_matters": (
        {
            "name": "Gray Merchant of Asphodel",
            "type_line": "Creature — Zombie",
            "oracle_text": (
                "When this creature enters, each opponent loses X life, where X is "
                "your devotion to black. You gain life equal to the life lost this "
                "way."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="lose_life",
                        scope="any",
                        raw="each opponent loses X life",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 sweep ──
    # Oil-counter PAYOFF (Kuldotha Cackler) — the count operand "permanents you control
    # with oil counters on them" is recovered as a place_counter(counter_kind='oil')
    # dropped-static marker, read via _COUNTER_KIND_KEYS['oil'].
    "oil_counter_matters": (
        {
            "name": "Kuldotha Cackler",
            "type_line": "Creature — Phyrexian Hyena",
            "oracle_text": (
                "Trample\nWhenever this creature attacks, it gets +X/+0 until "
                "end of turn, where X is the number of permanents you control "
                "with oil counters on them."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="place_counter",
                        scope="you",
                        counter_kind="oil",
                        raw="oil counters",
                    ),
                ),
            )
        ),
    ),
    # Mass-death payoff (Khabál Ghoul) — the aggregate "for each creature that died this
    # turn" count operand is recovered as a `mass_death` dropped-static marker.
    "mass_death_payoff": (
        {
            "name": "Khabál Ghoul",
            "type_line": "Creature — Zombie",
            "oracle_text": (
                "At the beginning of each end step, put a +1/+1 counter on this "
                "creature for each creature that died this turn."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="mass_death",
                        scope="you",
                        raw="for each creature that died this turn",
                    ),
                ),
            )
        ),
    ),
    # Starting-life payoff (Path of Bravery) — the "starting life total" compare is
    # recovered as a `starting_life` dropped-static marker.
    "starting_life_matters": (
        {
            "name": "Path of Bravery",
            "type_line": "Enchantment",
            "oracle_text": (
                "As long as your life total is greater than or equal to your "
                "starting life total, creatures you control get +1/+1.\nWhenever "
                "one or more creatures you control attack, you gain life equal to "
                "the number of attacking creatures."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="starting_life",
                        scope="you",
                        raw="starting life total",
                    ),
                ),
            )
        ),
    ),
    # Cycling payoff (Faith of the Devoted) — the "cycle or discard" trigger phase
    # flattens to event='other' is recovered as a `cycling_payoff` marker (distinct
    # from phase's native `cycling` landcycling doer).
    "cycling_matters": (
        {
            "name": "Faith of the Devoted",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever you cycle or discard a card, you may pay {1}. If you "
                "do, each opponent loses 2 life and you gain 2 life."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="cycling_payoff",
                        scope="you",
                        raw="Whenever you cycle or discard a card",
                    ),
                ),
            )
        ),
    ),
    # Dice payoff (Brazen Dwarf) — phase's native roll_die effect (and the "whenever
    # you roll" payoff marker) opens the lane via _DOER_EFFECT_KEYS['roll_die'].
    "dice_matters": (
        {
            "name": "Brazen Dwarf",
            "type_line": "Creature — Dwarf Shaman",
            "oracle_text": (
                "Whenever you roll one or more dice, this creature deals 1 "
                "damage to each opponent."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="other"),
                effects=(
                    Effect(
                        category="roll_die",
                        scope="you",
                        raw="Whenever you roll one or more dice",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 sweep 2 ──
    # Cascade granter (Maelstrom Nexus) — "the first spell you cast each turn has
    # cascade" is recovered as a `cascade` conferred-keyword marker.
    "cascade_matters": (
        {
            "name": "Maelstrom Nexus",
            "type_line": "Enchantment",
            "oracle_text": (
                "The first spell you cast each turn has cascade. (When you cast "
                "your first spell, exile cards from the top of your library "
                "until you exile a nonland card that costs less. You may cast it "
                "without paying its mana cost. Put the exiled cards on the bottom "
                "in a random order.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cascade",
                        scope="you",
                        raw="the first spell you cast each turn has cascade",
                    ),
                ),
            )
        ),
    ),
    # Changeling anthem (Maskwood Nexus) — "creatures you control are every creature
    # type" is recovered as a `changeling` dropped-static marker.
    "changeling_matters": (
        {
            "name": "Maskwood Nexus",
            "type_line": "Artifact",
            "oracle_text": (
                "Creatures you control are every creature type. The same is true "
                "for creature spells you control and creature cards you own that "
                "aren't on the battlefield.\n{3}, {T}: Create a 2/2 blue "
                "Shapeshifter creature token with changeling. (It is every "
                "creature type.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="changeling",
                        scope="you",
                        raw="are every creature type",
                    ),
                ),
            )
        ),
    ),
    # Regenerate grant (Tribal Golem) — the granted "{B}: Regenerate this creature"
    # is recovered as a `regenerate` dropped-static marker.
    "regenerate_matters": (
        {
            "name": "Tribal Golem",
            "type_line": "Artifact Creature — Golem",
            "oracle_text": (
                "This creature has trample as long as you control a Beast, haste "
                "as long as you control a Goblin, first strike as long as you "
                "control a Soldier, flying as long as you control a Wizard, and "
                '"{B}: Regenerate this creature" as long as you control a Zombie.'
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="regenerate",
                        scope="you",
                        raw="{B}: Regenerate this creature",
                    ),
                ),
            )
        ),
    ),
    # Undying grant (Mikaeus, the Unhallowed) — "other non-Human creatures you control
    # … have undying" is recovered as an `undying_persist` conferred-grant marker.
    "undying_persist_matters": (
        {
            "name": "Mikaeus, the Unhallowed",
            "type_line": "Legendary Creature — Zombie Cleric",
            "oracle_text": (
                "Intimidate\nWhenever a Human deals damage to you, destroy it.\n"
                "Other non-Human creatures you control get +1/+1 and have "
                "undying. (When a creature with undying dies, if it had no +1/+1 "
                "counters on it, return it to the battlefield under its owner's "
                "control with a +1/+1 counter on it.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="undying_persist",
                        scope="you",
                        raw="other non-Human creatures you control … have undying",
                    ),
                ),
            )
        ),
    ),
    # Creature-cast trigger (Glimpse of Nature) — a "whenever you cast a creature
    # spell" trigger phase dropped onto the face oracle is recovered as a
    # `creature_cast` marker (scope "any").
    "creature_cast_trigger": (
        {
            "name": "Glimpse of Nature",
            "type_line": "Sorcery",
            "oracle_text": (
                "Whenever you cast a creature spell this turn, draw a card."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="creature_cast",
                        scope="any",
                        raw="Whenever you cast a creature spell this turn",
                    ),
                ),
            )
        ),
    ),
    # Fight (Tolsimir, Friend to Wolves) — the granted "that creature fights" in the
    # Wolf-ETB trigger is recovered as a `fight` dropped-static marker.
    "fight_matters": (
        {
            "name": "Tolsimir, Friend to Wolves",
            "type_line": "Legendary Creature — Elf Scout",
            "oracle_text": (
                "When Tolsimir enters, create Voja, Friend to Elves, a legendary "
                "3/3 green and white Wolf creature token.\nWhenever a Wolf you "
                "control enters, you gain 3 life and that creature fights up to "
                "one target creature you don't control."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="fight",
                        scope="you",
                        raw="that creature fights up to one target creature",
                    ),
                ),
            )
        ),
    ),
    # Food maker (Trail of Crumbs) — the Food-subtype make_token opens the lane via
    # _TOKEN_SUBTYPE_KEYS (the same structural read blood_matters uses).
    "food_matters": (
        {
            "name": "Gingerbrute",
            "type_line": "Artifact Creature — Food Golem",
            "oracle_text": (
                "{1}: Gingerbrute can't be blocked this turn except by "
                "creatures with haste.\n{2}, {T}, Sacrifice Gingerbrute: You "
                "gain 3 life."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="make_token",
                        scope="you",
                        subject=Filter(card_types=("Artifact",), subtypes=("Food",)),
                        raw="create a Food token",
                    ),
                ),
            )
        ),
    ),
    # Treasure maker (Dockside Extortionist) — the Treasure-subtype make_token opens
    # the lane via _TOKEN_SUBTYPE_KEYS.
    "treasure_matters": (
        {
            "name": "Dockside Extortionist",
            "type_line": "Creature — Goblin Pirate",
            "oracle_text": (
                "When this creature enters, create a number of Treasure tokens "
                "equal to the number of artifacts and enchantments your "
                "opponents control."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="make_token",
                        scope="you",
                        subject=Filter(
                            card_types=("Artifact",), subtypes=("Treasure",)
                        ),
                        raw="create a number of Treasure tokens",
                    ),
                ),
            )
        ),
    ),
    # Saga / lore-counter payoff (Keldon Warcaller) — the "put a lore counter on target
    # Saga you control" manipulation is recovered as a `saga` dropped-static marker.
    "saga_matters": (
        {
            "name": "Keldon Warcaller",
            "type_line": "Creature — Human Warrior",
            "oracle_text": (
                "Whenever this creature attacks, put a lore counter on target "
                "Saga you control."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="saga",
                        scope="you",
                        raw="lore counter",
                    ),
                ),
            )
        ),
    ),
    # Cares-about kept-detector group (ADR-0027): moved floor->kept. devotion/party
    # prove the structural amount.op count-operand bind; the rest fire from the kept
    # word mirror over the oracle text (empty IR).
    "devotion_matters": (
        {
            "name": "Karametra's Acolyte",
            "type_line": "Creature — Human Druid",
            "oracle_text": (
                "{T}: Add an amount of {G} equal to your devotion to green. "
                "(Each {G} in the mana costs of permanents you control counts "
                "toward your devotion to green.)"
            ),
        },
        _ir(
            Ability(
                kind="activated",
                effects=(
                    Effect(
                        category="ramp",
                        scope="you",
                        amount=Quantity(op="devotion", factor=1),
                        raw="add {G} equal to your devotion to green",
                    ),
                ),
            )
        ),
    ),
    "party_matters": (
        {
            "name": "Archpriest of Iona",
            "type_line": "Creature — Human Cleric",
            "oracle_text": (
                "Archpriest of Iona's power is equal to the number of creatures "
                "in your party. (Your party consists of up to one each of Cleric, "
                "Rogue, Warrior, and Wizard.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="you",
                        amount=Quantity(op="party", factor=1),
                        raw="power equal to the number of creatures in your party",
                    ),
                ),
            )
        ),
    ),
    "historic_matters": (
        {
            "name": "Jhoira's Familiar",
            "type_line": "Artifact Creature — Bird",
            "oracle_text": (
                "Flying\nHistoric spells you cast cost {1} less to cast. "
                "(Artifacts, legendaries, and Sagas are historic.)"
            ),
            "keywords": ["Flying"],
        },
        _ir(),
    ),
    "multicolor_matters": (
        {
            "name": "Hero of Precinct One",
            "type_line": "Creature — Human Warrior",
            "oracle_text": (
                "Whenever you cast a multicolored spell, create a 1/1 white "
                "Human creature token."
            ),
        },
        _ir(),
    ),
    "colorless_matters": (
        {
            "name": "Herald of Kozilek",
            "type_line": "Creature — Eldrazi Drone",
            "oracle_text": (
                "Devoid (This card has no color.)\nColorless spells you cast "
                "cost {1} less to cast."
            ),
            "keywords": ["Devoid"],
        },
        _ir(),
    ),
    "initiative_matters": (
        {
            "name": "Aarakocra Sneak",
            "type_line": "Creature — Bird Rogue",
            "oracle_text": (
                "Flying\nWhen this creature enters, you take the initiative."
            ),
            "keywords": ["Flying"],
        },
        _ir(),
    ),
    "attractions_matter": (
        {
            "name": "Rad Rascal",
            "type_line": "Creature — Devil Employee",
            "oracle_text": (
                "When this creature enters, open an Attraction. (Put the top "
                "card of your Attraction deck onto the battlefield.)"
            ),
        },
        _ir(),
    ),
    # SWEEP batch (ADR-0027). donate / reanimator / opponent_exile read STRUCTURED IR
    # (a gain_control raw-recipient discriminator / a reanimate effect / a graveyard-
    # hate raw); the rest fire from the kept word mirror over the oracle text (empty
    # IR). Each card is real, full oracle_text + type_line.
    "color_hoser": (
        {
            "name": "Dark Betrayal",
            "type_line": "Instant",
            "oracle_text": "Destroy target black creature.",
        },
        _ir(
            Ability(
                kind="activated",
                effects=(
                    Effect(
                        category="destroy",
                        scope="any",
                        subject=Filter(
                            card_types=("Creature",),
                            predicates=("HasColor:Black",),
                        ),
                        raw="Destroy target black creature.",
                    ),
                ),
            )
        ),
    ),
    "donate_matters": (
        {
            "name": "Harmless Offering",
            "type_line": "Sorcery",
            "oracle_text": "Target opponent gains control of target permanent you control.",
        },
        _ir(
            Ability(
                kind="activated",
                effects=(
                    Effect(
                        category="gain_control",
                        scope="any",
                        subject=Filter(card_types=("Permanent",), controller="you"),
                        raw="Target opponent gains control of target permanent you control.",
                    ),
                ),
            )
        ),
    ),
    "minus_counters_matter": (
        {
            "name": "Crumbling Ashes",
            "type_line": "Enchantment",
            "oracle_text": (
                "At the beginning of your upkeep, destroy target creature with a "
                "-1/-1 counter on it."
            ),
        },
        _ir(),
    ),
    "team_evasion_grant": (
        {
            "name": "Galerider Sliver",
            "type_line": "Creature — Sliver",
            "oracle_text": "Sliver creatures you control have flying.",
        },
        _ir(),
    ),
    "hand_disruption": (
        {
            "name": "Peek",
            "type_line": "Instant",
            "oracle_text": "Look at target player's hand.\nDraw a card.",
        },
        _ir(),
    ),
    "commander_matters": (
        {
            "name": "Kediss, Emberclaw Familiar",
            "type_line": "Legendary Creature — Elemental Lizard",
            "oracle_text": (
                "Whenever a commander you control deals combat damage to an "
                "opponent, it deals that much damage to each other opponent.\n"
                "Partner (You can have two commanders if both have partner.)"
            ),
            "keywords": ["Partner"],
        },
        _ir(),
    ),
    "domain_matters": (
        {
            "name": "Matca Rioters",
            "type_line": "Creature — Human Warrior",
            "oracle_text": (
                "Domain — Matca Rioters's power and toughness are each equal to "
                "the number of basic land types among lands you control."
            ),
        },
        _ir(),
    ),
    "opponent_exile_matters": (
        {
            "name": "Bojuka Bog",
            "type_line": "Land",
            "oracle_text": (
                "This land enters tapped.\nWhen this land enters, exile target "
                "player's graveyard.\n{T}: Add {B}."
            ),
        },
        _ir(),
    ),
    "exalted_lone_attacker": (
        {
            "name": "Rogue Kavu",
            "type_line": "Creature — Kavu",
            "oracle_text": (
                "Whenever this creature attacks alone, it gets +2/+0 until end of turn."
            ),
        },
        _ir(),
    ),
    "speed_matters": (
        {
            "name": "The Speed Demon",
            "type_line": "Legendary Creature — Demon",
            "oracle_text": (
                "Flying, trample\nStart your engines!\nAt the beginning of your "
                "end step, you draw X cards and lose X life, where X is your speed."
            ),
            "keywords": ["Flying", "Trample"],
        },
        _ir(),
    ),
    "tap_untap_matters": (
        {
            "name": "Pheres-Band Tromper",
            "type_line": "Creature — Centaur Warrior",
            "oracle_text": (
                "Inspired — Whenever this creature becomes untapped, put a +1/+1 "
                "counter on it."
            ),
        },
        _ir(),
    ),
    "reanimator": (
        {
            "name": "Loyal Retainers",
            "type_line": "Creature — Human Advisor",
            "oracle_text": (
                "Sacrifice this creature: Return target legendary creature card "
                "from your graveyard to the battlefield. Activate only during "
                "your turn, before attackers are declared."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                effects=(
                    Effect(
                        category="reanimate",
                        scope="you",
                        subject=Filter(card_types=("Creature",)),
                        raw="Return target legendary creature card from your graveyard to the battlefield.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — creature_recursion (return a CREATURE card from a graveyard — the
    # broad GY→hand OR battlefield "loop a creature" build-around, DISTINCT from the
    # GY→BATTLEFIELD-only reanimator lane). Reanimate reads the STRUCTURAL arm
    # (cat=="reanimate" + a Creature-typed subject Filter → extract_signals_ir fires
    # creature_recursion scope "you"). Its oracle says "from A graveyard" (not "your
    # graveyard"), so the kept _CREATURE_RECURSION_MIRROR does NOT fire — this case
    # proves the recall-GAINING structural half (the GY→hand / GY→library tail rides
    # the byte-identical mirror instead). Real card, full oracle. CR 700.4.
    "creature_recursion": (
        {
            "name": "Reanimate",
            "type_line": "Sorcery",
            "oracle_text": (
                "Put target creature card from a graveyard onto the battlefield "
                "under your control. You lose life equal to that card's mana value."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="reanimate",
                        scope="you",
                        subject=Filter(card_types=("Creature",)),
                        raw="Put target creature card from a graveyard onto the battlefield under your control.",
                    ),
                ),
            )
        ),
    ),
    # SWEEP-floor->kept batch (ADR-0027). legends/lands read STRUCTURED IR (a
    # HasSupertype:Legendary subject predicate / an amount.subject=Land count operand);
    # poison/suspend fire from the kept word mirror over the oracle text (empty IR — a
    # granter / a time-counter card with no Scryfall keyword). Real cards, full text.
    "legends_matter": (
        {
            "name": "Kytheon's Irregulars",
            "type_line": "Creature — Human Soldier",
            "oracle_text": (
                "Renown 4 (When this creature deals combat damage to a player, "
                "if it isn't renowned, put four +1/+1 counters on it and it "
                "becomes renowned.)\n{W}, {T}: Tap target creature."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="draw",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",),
                            controller="you",
                            predicates=("HasSupertype:Legendary",),
                        ),
                        raw="Whenever another legendary creature you control enters, draw a card.",
                    ),
                ),
            )
        ),
    ),
    "lands_matter": (
        {
            "name": "Dakkon Blackblade",
            "type_line": "Legendary Creature — Human Wizard",
            "oracle_text": (
                "Dakkon Blackblade's power and toughness are each equal to the "
                "number of lands you control."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="characteristic_pt",
                        scope="you",
                        amount=Quantity(
                            op="count",
                            subject=Filter(card_types=("Land",), controller="you"),
                        ),
                        raw="power and toughness equal to the number of lands you control",
                    ),
                ),
            )
        ),
    ),
    "poison_matters": (
        {
            "name": "Phyresis",
            "type_line": "Enchantment — Aura",
            "oracle_text": "Enchant creature\nEnchanted creature has infect.",
            "keywords": ["Enchant"],
        },
        _ir(),
    ),
    "suspend_matters": (
        {
            "name": "Calciderm",
            "type_line": "Creature — Beast",
            "oracle_text": (
                "Vanishing 4 (This permanent enters with four time counters on "
                "it. At the beginning of your upkeep, remove a time counter from "
                "it. When the last is removed, sacrifice it.)\nThis spell can't "
                "be the target of spells or abilities your opponents control."
            ),
        },
        _ir(),
    ),
    # Group "tranche2-B" — structural IR migrations.
    #   mass_bounce       ← Effect(bounce, counter_kind="all") + board subject
    #   permanent_etb     ← Trigger(etb) with a Permanent-you-control subject
    #   team_buff         ← Effect(grant_keyword, ck=<evergreen kw>) + team subject
    #   destroy_legendary ← Effect(destroy) subject Filter HasSupertype:Legendary
    #   power_double      ← Effect(pump/pump_target) raw "double … power"
    "mass_bounce": (
        {
            "name": "Evacuation",
            "type_line": "Instant",
            "oracle_text": "Return all creatures to their owners' hands.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="bounce",
                        scope="any",
                        counter_kind="all",
                        subject=Filter(card_types=("Creature",), controller="any"),
                        raw="Return all creatures to their owners' hands.",
                    ),
                ),
            )
        ),
    ),
    "permanent_etb": (
        {
            "name": "Amareth, the Lustrous",
            "type_line": "Legendary Creature — Dragon Avatar",
            "oracle_text": (
                "Flying\nWhenever another permanent you control enters, look at "
                "the top card of your library. If it shares a card type with that "
                "permanent, you may reveal that card and put it into your hand."
            ),
            "keywords": ["Flying"],
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="etb",
                    scope="you",
                    subject=Filter(
                        card_types=("Permanent",),
                        controller="you",
                        predicates=("Another",),
                    ),
                ),
                effects=(
                    Effect(
                        category="topdeck_select",
                        scope="any",
                        raw="look at the top card of your library",
                    ),
                ),
            )
        ),
    ),
    "team_buff": (
        {
            "name": "Brave the Sands",
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures you control have vigilance.\nEach creature you control "
                "can block an additional creature each combat."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        counter_kind="vigilance",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw="Creatures you control have vigilance.",
                    ),
                ),
            )
        ),
    ),
    "destroy_legendary": (
        {
            "name": "Hero's Demise",
            "type_line": "Instant",
            "oracle_text": "Destroy target legendary creature.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="destroy",
                        scope="any",
                        subject=Filter(
                            card_types=("Creature",),
                            controller="any",
                            predicates=("HasSupertype:Legendary",),
                        ),
                        raw="Destroy target legendary creature.",
                    ),
                ),
            )
        ),
    ),
    "power_double": (
        {
            "name": "Unleash Fury",
            "type_line": "Instant",
            "oracle_text": "Double the power of target creature until end of turn.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="pump_target",
                        scope="any",
                        subject=Filter(card_types=("Creature",), controller="any"),
                        raw="Double the power of target creature until end of turn.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 tranche2-A structural sweeps.
    #   activated_draw ← Ability(kind="activated", 'tap' in cost) + a draw Effect.
    #   anthem_static  ← Ability(kind="static") pump over a creature GROUP, factor>=0.
    #   aoe_ping       ← a counter_kind="all" damage Effect over a Creature subject on
    #                    a repeatable-frame ability (activated tap/mana cost).
    #   mass_removal   ← a counter_kind="all" destroy of a battlefield permanent type.
    "activated_draw": (
        {
            "name": "Arch of Orazca",
            "type_line": "Land",
            "oracle_text": (
                "{T}: Add {C}.\nAscend (If you control ten or more permanents, you "
                "get the city's blessing for the rest of the game.)\n{5}, {T}: Draw "
                "a card. Activate only if you have the city's blessing."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(Effect(category="draw", scope="you", raw="Draw a card."),),
            )
        ),
    ),
    "anthem_static": (
        {
            "name": "Glorious Anthem",
            "type_line": "Enchantment",
            "oracle_text": "Creatures you control get +1/+1.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        amount=Quantity(op="fixed", factor=1),
                        scope="you",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw="Creatures you control get +1/+1.",
                    ),
                ),
            )
        ),
    ),
    "aoe_ping": (
        {
            "name": "Pestilence",
            "type_line": "Enchantment",
            "oracle_text": (
                "At the beginning of the end step, if no creatures are on the "
                "battlefield, sacrifice Pestilence.\n{B}: Pestilence deals 1 damage "
                "to each creature and each player."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana",
                effects=(
                    Effect(
                        category="damage",
                        counter_kind="all",
                        subject=Filter(card_types=("Creature",)),
                        raw="~ deals 1 damage to each creature and each player.",
                    ),
                ),
            )
        ),
    ),
    "mass_removal": (
        {
            "name": "Wrath of God",
            "type_line": "Sorcery",
            "oracle_text": "Destroy all creatures. They can't be regenerated.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="destroy",
                        counter_kind="all",
                        subject=Filter(card_types=("Creature",)),
                        raw="Destroy all creatures.",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 tranche2-C ───────────────────────────────────────────────────
    # exert_matters ← a team-VIGILANCE grant_keyword effect (counter_kind='vigilance')
    # over a generic creature board (Brave the Sands — team vigilance neutralizes
    # exert's "won't untap" downside). Read by the grant_keyword/vigilance/generic arm.
    "exert_matters": (
        {
            "name": "Brave the Sands",
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures you control have vigilance.\nEach creature you control "
                "can block an additional creature each combat."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        counter_kind="vigilance",
                        scope="you",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw="Creatures you control have vigilance.",
                    ),
                ),
            )
        ),
    ),
    # self_pump ← an ACTIVATED pump_target on the SELF (subject=None) — the
    # firebreathing mana sink (Shivan Dragon). The ab.kind=='activated' gate + the
    # subject=None self shape is the discriminator.
    "self_pump": (
        {
            "name": "Shivan Dragon",
            "type_line": "Creature — Dragon",
            "oracle_text": "Flying\n{R}: Shivan Dragon gets +1/+0 until end of turn.",
            "keywords": ["Flying"],
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana",
                effects=(
                    Effect(
                        category="pump_target",
                        scope="any",
                        subject=None,
                        raw="{R}: ~ gets +1/+0 until end of turn.",
                    ),
                ),
            )
        ),
    ),
    # tapper_engine ← a `tap` Effect with a TARGET subject Filter — the repeatable
    # tapper (Icy Manipulator). subject is not None separates it from tap-as-cost.
    "tapper_engine": (
        {
            "name": "Icy Manipulator",
            "type_line": "Artifact",
            "oracle_text": ("{1}, {T}: Tap target artifact, creature, or land."),
        },
        _ir(
            Ability(
                kind="activated",
                cost="mana,tap",
                effects=(
                    Effect(
                        category="tap",
                        scope="any",
                        subject=Filter(
                            card_types=("Artifact", "Creature", "Land"),
                            controller="any",
                        ),
                        raw="{1}, {T}: Tap target artifact, creature, or land.",
                    ),
                ),
            )
        ),
    ),
    # recast_etb ← the Scryfall `Sneak` keyword (the bounce-replay engine, read off
    # the keyword array → a bare non-None IR routes the hybrid to the IR path).
    "recast_etb": (
        {
            "name": "Karai's Technique",
            "type_line": "Instant — Ninjutsu",
            "oracle_text": (
                "Sneak {1}{U} (You may cast this spell for {1}{U} if you also return "
                "an unblocked attacker you control to hand.)\nUp to two target "
                "creatures get +2/+0 until end of turn."
            ),
            "keywords": ["Sneak"],
        },
        _ir(),
    ),
    # count_anthem ← a team +N/+N pump whose amount SCALES with a board count over a
    # generic creature Filter you control (Hold the Gates — "+0/+1 for each Gate").
    "count_anthem": (
        {
            "name": "Hold the Gates",
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures you control get +0/+1 for each Gate you control.\nYou "
                "may play lands from your graveyard."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="you",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        amount=Quantity(
                            op="count",
                            subject=Filter(subtypes=("Gate",), controller="you"),
                        ),
                        raw="Creatures you control get +0/+1 for each Gate you control.",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 tranche2 (t2b2-A) batch ─────────────────────────────────────
    # aura_equip_kw_grant ← a grant_keyword of an evergreen keyword over a YOUR
    # Aura/Equipment subgroup subject (Rashel: "Auras you control have exalted").
    "aura_equip_kw_grant": (
        {
            "name": "Rashel, Fist of Torm",
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": (
                "Double strike\nAuras you control have exalted. (Whenever a "
                "creature you control attacks alone, it gets +1/+1 until end of "
                "turn for each instance of exalted among permanents you control.)"
            ),
            "keywords": ["Double strike"],
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        counter_kind="exalted",
                        subject=Filter(
                            card_types=("Enchantment",),
                            subtypes=("Aura",),
                            controller="you",
                        ),
                        raw="Auras you control have exalted.",
                    ),
                ),
            )
        ),
    ),
    # counter_grants_kw ← a grant_keyword over a YOUR-creature subject carrying the
    # `Counters` predicate ("creatures you control with a +1/+1 counter have trample").
    "counter_grants_kw": (
        {
            "name": "Bramblewood Paragon",
            "type_line": "Creature — Elf Warrior",
            "oracle_text": (
                "Each other Warrior creature you control enters with an additional "
                "+1/+1 counter on it.\nEach creature you control with a +1/+1 "
                "counter on it has trample."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        counter_kind="trample",
                        subject=Filter(
                            card_types=("Creature",),
                            controller="you",
                            predicates=("Counters",),
                        ),
                        raw=(
                            "Each creature you control with a +1/+1 counter on it "
                            "has trample."
                        ),
                    ),
                ),
            )
        ),
    ),
    # conditional_self_protection ← a STATIC ability with a condition granting a
    # protective keyword to ITSELF (subject None = SelfRef). Zurgo: "during your
    # turn, ~ has indestructible" → Condition(duringyourturn) + grant_keyword.
    "conditional_self_protection": (
        {
            "name": "Zurgo Helmsmasher",
            "type_line": "Legendary Creature — Orc Warrior",
            "oracle_text": (
                "Haste\nZurgo Helmsmasher attacks each combat if able.\nZurgo "
                "Helmsmasher can't be blocked by creatures with power 2 or less.\n"
                "As long as it's your turn, Zurgo Helmsmasher has indestructible.\n"
                "Whenever a creature dealt damage by Zurgo Helmsmasher this turn "
                "dies, put a +1/+1 counter on Zurgo Helmsmasher."
            ),
            "keywords": ["Haste"],
        },
        _ir(
            Ability(
                kind="static",
                condition=Condition(kind="duringyourturn"),
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="any",
                        counter_kind="indestructible",
                        subject=None,
                        raw="As long as it's your turn, ~ has indestructible.",
                    ),
                ),
            )
        ),
    ),
    # control_exchange ← an `exile` Effect whose subject carries the `Owned`
    # predicate, PAIRED with a to:battlefield return in the same ability (Meneldor).
    "control_exchange": (
        {
            "name": "Meneldor, Swift Savior",
            "type_line": "Legendary Creature — Bird",
            "oracle_text": (
                "Flying, haste\nWhenever Meneldor, Swift Savior attacks, exile up "
                "to one target creature you own, then return it to the battlefield "
                "under your control tapped and attacking. Sacrifice it at the "
                "beginning of the next end step."
            ),
            "keywords": ["Flying", "Haste"],
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="attacks", scope="you"),
                effects=(
                    Effect(
                        category="exile",
                        scope="any",
                        zones=("to:exile",),
                        subject=Filter(
                            card_types=("Creature",),
                            controller="any",
                            predicates=("Owned",),
                        ),
                        raw="exile up to one target creature you own",
                    ),
                    Effect(
                        category="exile",
                        scope="any",
                        zones=("to:battlefield",),
                        subject=None,
                        raw="return it to the battlefield under your control",
                    ),
                ),
            )
        ),
    ),
    # bounce_tempo ← a first-class `bounce` Effect, no graveyard zone, subject not
    # controller='you' (Boomerang: "return target permanent to its owner's hand").
    "bounce_tempo": (
        {
            "name": "Boomerang",
            "type_line": "Instant",
            "oracle_text": "Return target permanent to its owner's hand.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="bounce",
                        scope="any",
                        subject=Filter(card_types=("Permanent",), controller="any"),
                        raw="Return target permanent to its owner's hand.",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 tranche2-B (counters / O-Ring lanes) ──
    # counter_manipulation ← a remove_counter Effect of a +1/+1 or -1/-1 counter (the
    # remove-as-EFFECT half; the move half rides counter_move and the cost half a kept
    # word mirror). Carnifex Demon removes -1/-1 counters as an activated effect.
    "counter_manipulation": (
        {
            "name": "Carnifex Demon",
            "type_line": "Artifact Creature — Demon",
            "oracle_text": (
                "This creature enters with four -1/-1 counters on it.\n{B}, Remove a "
                "-1/-1 counter from this creature: Put a -1/-1 counter on each other "
                "creature."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                effects=(
                    Effect(
                        category="remove_counter",
                        counter_kind="m1m1",
                        scope="you",
                        raw="Remove a -1/-1 counter from ~",
                    ),
                ),
            )
        ),
    ),
    # counter_place_trigger ← a counter_added TRIGGER (scope!='opp', non-Saga).
    # Flourishing Defenses triggers on a -1/-1 counter being put on a creature.
    "counter_place_trigger": (
        {
            "name": "Flourishing Defenses",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever a -1/-1 counter is put on a creature, you may create a 1/1 "
                "green Elf Warrior creature token."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="counter_added",
                    scope="any",
                    subject=Filter(card_types=("Creature",), controller="any"),
                ),
                effects=(
                    Effect(
                        category="make_token",
                        scope="you",
                        raw="create a 1/1 green Elf Warrior creature token",
                    ),
                ),
            )
        ),
    ),
    # counter_replace_bonus ← the counter_doubling replacement category (is_widen_of
    # counter_doubling, the same IR population). Hardened Scales adds one extra +1/+1.
    "counter_replace_bonus": (
        {
            "name": "Hardened Scales",
            "type_line": "Enchantment",
            "oracle_text": (
                "If one or more +1/+1 counters would be put on a creature you control, "
                "that many plus one +1/+1 counters are put on it instead."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="counter_doubling",
                        counter_kind="p1p1",
                        scope="you",
                        raw="that many plus one +1/+1 counters are put on it instead",
                    ),
                ),
            )
        ),
    ),
    # counter_doubling ← the kept-mirror recovery path (COUNTER_DOUBLING_REGEX). Vorel's
    # one-shot "Double the number of each kind of counter …" is what phase v0.1.19
    # MANGLES to a generic `double` effect with no counter_doubling category, so a bare
    # IR proves the lane fires from the oracle mirror, not a structural arm. (The
    # structural `cat == "counter_doubling"` replacement arm covers the Doubling Season /
    # Hardened Scales family — the 6 the regex missed — separately.) CR 122 / 614.
    "counter_doubling": (
        {
            "name": "Vorel of the Hull Clade",
            "type_line": "Legendary Creature — Human Merfolk",
            "oracle_text": (
                "{G}{U}, {T}: Double the number of each kind of counter on target "
                "artifact, creature, or land."
            ),
        },
        _ir(),
    ),
    # exile_until_leaves ← the TWO-ABILITY O-Ring shape: an exile Effect sending
    # to:exile + a SECOND ability whose dies/leaves trigger reanimates to:battlefield
    # (the linked return). Oblivion Ring is the canonical card.
    "exile_until_leaves": (
        {
            "name": "Oblivion Ring",
            "type_line": "Enchantment",
            "oracle_text": (
                "When Oblivion Ring enters, exile another target nonland permanent.\n"
                "When Oblivion Ring leaves the battlefield, return the exiled card to "
                "the battlefield under its owner's control."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="etb", scope="you"),
                effects=(
                    Effect(
                        category="exile",
                        scope="any",
                        zones=("to:exile",),
                        raw="exile another target nonland permanent",
                    ),
                ),
            ),
            Ability(
                kind="triggered",
                trigger=Trigger(event="dies", scope="you"),
                effects=(
                    Effect(
                        category="reanimate",
                        scope="any",
                        zones=("to:battlefield",),
                        raw="return the exiled card to the battlefield",
                    ),
                ),
            ),
        ),
    ),
    # ── ADR-0027 tranche2-C (batch C) ──
    # extra_land_drop ← Effect(cheat_play) with a Land subject you control (Burgeoning
    # "put a land card from your hand onto the battlefield").
    "extra_land_drop": (
        {
            "name": "Burgeoning",
            "type_line": "Enchantment",
            "oracle_text": (
                "Whenever an opponent plays a land, you may put a land card from "
                "your hand onto the battlefield."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="cheat_play",
                        scope="you",
                        subject=Filter(card_types=("Land",), controller="you"),
                        raw="you may put a land card from your hand onto the battlefield",
                    ),
                ),
            )
        ),
    ),
    # free_creature_payoff ← an ETB trigger whose condition tree carries a
    # manaspentcondition (Satoru the Infiltrator). The etb gate excludes the
    # cast_spell-triggered anti-free-spell punishers.
    "free_creature_payoff": (
        {
            "name": "Satoru, the Infiltrator",
            "type_line": "Legendary Creature — Human Ninja Rogue",
            "oracle_text": (
                "Menace\nWhenever Satoru, the Infiltrator and/or one or more other "
                "nontoken creatures you control enter, if none of them were cast or "
                "no mana was spent to cast them, draw a card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="etb", scope="you"),
                condition=Condition(
                    kind="or",
                    nested=(
                        Condition(kind="not", nested=(Condition(kind="wascast"),)),
                        Condition(kind="manaspentcondition"),
                    ),
                ),
                effects=(Effect(category="draw", scope="you"),),
            )
        ),
    ),
    # keyword_counter ← a place_counter whose counter_kind is in the CR-122.1b keyword
    # set (Luminous Broodmoth — returns with a flying counter).
    "keyword_counter": (
        {
            "name": "Luminous Broodmoth",
            "type_line": "Creature — Insect",
            "oracle_text": (
                "Flying\nWhenever a creature you control without a flying counter "
                "on it dies, return that card to the battlefield under your control "
                "with a flying counter on it."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="place_counter",
                        counter_kind="flying",
                        scope="any",
                        raw="return that card ... with a flying counter on it",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 tranche2-batch-3-A — land-animation + keyword-soup lanes.
    # keyword_soup ← >=5 DISTINCT evergreen grant_keyword counter_kinds in ONE
    # ability (Odric grants 13).
    "keyword_soup": (
        {
            "name": "Odric, Lunarch Marshal",
            "type_line": "Legendary Creature — Human Soldier",
            "oracle_text": (
                "At the beginning of each combat, creatures you control gain "
                "first strike until end of turn if a creature you control has "
                "first strike. The same is true for flying, deathtouch, double "
                "strike, haste, hexproof, indestructible, lifelink, menace, "
                "reach, skulk, trample, and vigilance."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=tuple(
                    Effect(
                        category="grant_keyword",
                        counter_kind=ck,
                        scope="you",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw="creatures you control gain first strike",
                    )
                    for ck in (
                        "firststrike",
                        "flying",
                        "deathtouch",
                        "doublestrike",
                        "haste",
                    )
                ),
            )
        ),
    ),
    # land_creatures_matter ← a pump over a Land+Creature dual-type subject (Sylvan
    # Advocate buffs "this creature and land creatures you control").
    "land_creatures_matter": (
        {
            "name": "Sylvan Advocate",
            "type_line": "Creature — Elf Druid Ally",
            "oracle_text": (
                "Vigilance\nAs long as you control six or more lands, this "
                "creature and land creatures you control get +2/+2."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature", "Land"), controller="you"
                        ),
                        raw="~ and land creatures you control get +2/+2",
                    ),
                ),
            )
        ),
    ),
    # land_protection ← the shared land-animator predicate: a base_pt_set over a Land
    # subject (Living Plane: "All lands are 1/1 creatures that are still lands.").
    "land_protection": (
        {
            "name": "Living Plane",
            "type_line": "World Enchantment",
            "oracle_text": "All lands are 1/1 creatures that are still lands.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="base_pt_set",
                        scope="any",
                        subject=Filter(card_types=("Land",), controller="any"),
                        raw="All lands are 1/1 creatures that are still lands.",
                    ),
                ),
            )
        ),
    ),
    # land_denial ← a phasing Effect on a controller=='you' Land subject (Taniwha
    # phases its own lands out — the self-land-phasing stax tell).
    "land_denial": (
        {
            "name": "Taniwha",
            "type_line": "Legendary Creature — Serpent",
            "oracle_text": (
                "Trample\nPhasing\nAt the beginning of your upkeep, all lands "
                "you control phase out."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="phasing",
                        scope="you",
                        subject=Filter(card_types=("Land",), controller="you"),
                        raw="all lands you control phase out",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 tranche2-B-3. spell_keyword_grant ← the WHOLE cast_with_keyword effect
    # category. Thrumming Stone grants ripple to your spells.
    "spell_keyword_grant": (
        {
            "name": "Thrumming Stone",
            "type_line": "Legendary Artifact",
            "oracle_text": (
                "Spells you cast have ripple 4. (Whenever you cast a spell, you may "
                "reveal the top four cards of your library. You may cast spells with "
                "the same name as that spell from among the revealed cards without "
                "paying their mana costs. Put the rest on the bottom of your library.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cast_with_keyword",
                        scope="you",
                        raw="Spells you cast have ripple 4.",
                    ),
                ),
            )
        ),
    ),
    # target_player_draws ← a `draw` effect with scope=='any' (the directed/forced
    # draw). Dictate of Kruphix's "that player draws an additional card".
    "target_player_draws": (
        {
            "name": "Dictate of Kruphix",
            "type_line": "Enchantment",
            "oracle_text": (
                "Flash (You may cast this spell any time you could cast an "
                "instant.)\nAt the beginning of each player's draw step, that player "
                "draws an additional card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="draw_step", scope="each"),
                effects=(
                    Effect(
                        category="draw",
                        scope="any",
                        raw="that player draws an additional card",
                    ),
                ),
            )
        ),
    ),
    # group_hug_draw ← a `draw` effect with scope=='each' (the symmetric group-hug
    # draw lane — a card that draws for EVERY player). Wheel of Fortune is the
    # STRUCTURAL-ONLY proof: its "each player discards their hand, then draws seven
    # cards" puts a discard clause BETWEEN "each player" and "draws", so the narrow
    # regex `each player (?:may )?draws?\b` never matches (regex drops it), while the
    # IR `draw` Effect carries scope=='each' regardless of the intervening clause.
    "group_hug_draw": (
        {
            "name": "Wheel of Fortune",
            "type_line": "Sorcery",
            "oracle_text": "Each player discards their hand, then draws seven cards.",
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="draw",
                        scope="each",
                        amount=Quantity(op="fixed", factor=7),
                        raw="Each player discards their hand, then draws seven cards.",
                    ),
                ),
            )
        ),
    ),
    # ── ADR-0027 tranche2-B (t2b3-B) ─────────────────────────────────────────
    # lose_unless_hand ← an ETB trigger scoped YOU whose effect is a lose_game
    # (Phage the Untouchable — "if you didn't cast it from your hand, you lose").
    "lose_unless_hand": (
        {
            "name": "Phage the Untouchable",
            "type_line": "Legendary Creature — Avatar Minion",
            "oracle_text": (
                "When Phage the Untouchable enters, if you didn't cast it from "
                "your hand, you lose the game.\nWhenever Phage the Untouchable "
                "deals combat damage to a creature, destroy that creature. It "
                "can't be regenerated.\nWhenever Phage the Untouchable deals "
                "combat damage to a player, that player loses the game."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="etb", scope="you"),
                effects=(
                    Effect(
                        category="lose_game",
                        scope="you",
                        raw=(
                            "When ~ enters, if you didn't cast it from your "
                            "hand, you lose the game."
                        ),
                    ),
                ),
            )
        ),
    ),
    # opponent_cast_matters ← a cast_spell trigger scoped opp (Lavinia — "Whenever
    # an opponent casts a spell" punisher).
    "opponent_cast_matters": (
        {
            "name": "Lavinia, Azorius Renegade",
            "type_line": "Legendary Creature — Human Soldier",
            "oracle_text": (
                "Each opponent can't cast noncreature spells with mana value "
                "greater than the number of lands that player controls.\nWhenever "
                "an opponent casts a spell, if no mana was spent to cast it, "
                "counter that spell."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="cast_spell", scope="opp"),
                effects=(
                    Effect(
                        category="counter_spell",
                        scope="any",
                        raw="counter that spell",
                    ),
                ),
            )
        ),
    ),
    # opponent_counter_grant ← a place_counter of a DETRIMENTAL bounty counter on
    # an opponent's permanent (Mathas, Fiend Seeker).
    "opponent_counter_grant": (
        {
            "name": "Mathas, Fiend Seeker",
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": (
                "Menace\nAt the beginning of your end step, put a bounty counter "
                "on target creature an opponent controls. For as long as that "
                'creature has a bounty counter on it, it has "When this creature '
                'dies, each opponent draws a card and gains 2 life."'
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="end_step"),
                effects=(
                    Effect(
                        category="place_counter",
                        counter_kind="bounty",
                        subject=Filter(card_types=("Creature",), controller="opp"),
                        raw="put a bounty counter on target creature an opponent "
                        "controls",
                    ),
                ),
            )
        ),
    ),
    # power_tap_engine ← an ACTIVATED ability cost~'tap' whose effect raw scales
    # with a creature's power (Marwyn, the Nurturer).
    "power_tap_engine": (
        {
            "name": "Marwyn, the Nurturer",
            "type_line": "Legendary Creature — Elf Druid",
            "oracle_text": (
                "Whenever another Elf you control enters, put a +1/+1 counter on "
                "Marwyn, the Nurturer.\n{T}: Add an amount of {G} equal to "
                "Marwyn, the Nurturer's power."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                cost="tap",
                effects=(
                    Effect(
                        category="ramp",
                        scope="any",
                        raw="{T}: Add an amount of {G} equal to ~'s power.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 tranche2-batch-4 (t2b4-C) — 5 kept_detector keys phase v0.1.60 cannot
    # structure. Each fires from a dedicated IR-path WORD MIRROR reading the record's
    # oracle_text (the exact deleted regex), so a bare `_ir()` Card routes the hybrid to
    # the IR path; the mirror does the rest. (self_blink also reuses the name-aware
    # fulltext detector; type_change the subtype-gated _type_hoser_clause — both read the
    # record, not structured IR.)
    "damage_to_you_punish": (
        {
            "name": "Flameblade Angel",
            "type_line": "Creature — Angel",
            "oracle_text": (
                "Flying\nWhenever a source an opponent controls deals damage to "
                "you or a permanent you control, you may have this creature deal 1 "
                "damage to that source's controller."
            ),
            "keywords": ["Flying"],
        },
        _ir(),
    ),
    "excess_damage": (
        {
            "name": "Aegar, the Freezing Flame",
            "type_line": "Legendary Creature — Giant Wizard",
            "oracle_text": (
                "Whenever a creature or planeswalker an opponent controls is dealt "
                "excess damage, if a Giant, Wizard, or spell you controlled dealt "
                "damage to it this turn, draw a card."
            ),
        },
        _ir(),
    ),
    "self_blink": (
        {
            "name": "Norin the Wary",
            "type_line": "Legendary Creature — Human Warrior",
            "oracle_text": (
                "When a player casts a spell or a creature attacks, exile Norin. "
                "Return it to the battlefield under its owner's control at the "
                "beginning of the next end step."
            ),
        },
        _ir(),
    ),
    "tap_down_blockers": (
        {
            "name": "Tromokratis",
            "type_line": "Legendary Creature — Kraken",
            "oracle_text": (
                "Tromokratis has hexproof unless it's attacking or blocking.\n"
                "Tromokratis can't be blocked unless all creatures defending player "
                "controls block it. (If any creature that player controls doesn't "
                "block this creature, it can't be blocked.)"
            ),
        },
        _ir(),
    ),
    "type_change": (
        {
            "name": "Gor Muldrak, Amphinologist",
            "type_line": "Legendary Creature — Human Scout",
            "oracle_text": (
                "You and permanents you control have protection from Salamanders.\n"
                "At the beginning of your end step, each player who controls the "
                "fewest creatures creates a 4/3 blue Salamander Warrior creature "
                "token."
            ),
        },
        _ir(),
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-A) — 5 kept_detector keys phase v0.1.60 cannot
    # structure. Each fires from a dedicated IR-path WORD MIRROR reading the record's
    # oracle_text (the exact deleted SWEEP / _HAND_FLOOR regex), so a bare `_ir()` Card
    # routes the hybrid to the IR path; the mirror does the rest. (free_plot's flip-side
    # is read on the joined-face oracle, so the two-face Kamigawa flip creature's "flip
    # this creature" survives even though its top-level oracle_text is empty.)
    "draft_spellbook": (
        {
            "name": "Cogwork Librarian",
            "type_line": "Artifact Creature — Construct",
            "oracle_text": (
                "Draft this card face up.\nAs you draft a card, you may draft an "
                "additional card from that booster pack. If you do, put this card "
                "into that booster pack."
            ),
        },
        _ir(),
    ),
    "each_mode_player": (
        {
            "name": "Vindictive Lich",
            "type_line": "Creature — Zombie Wizard",
            "oracle_text": (
                "When this creature dies, choose one or more. Each mode must target "
                "a different player.\n• Target opponent sacrifices a creature of "
                "their choice.\n• Target opponent discards two cards.\n• Target "
                "opponent loses 5 life."
            ),
        },
        _ir(),
    ),
    "flip_self": (
        {
            "name": "Nezumi Graverobber // Nighteyes the Desecrator",
            "type_line": ("Creature — Rat Rogue // Legendary Creature — Rat Wizard"),
            "oracle_text": (
                "{1}{B}: Exile target card from an opponent's graveyard. If no "
                "cards are in that graveyard, flip this creature.\n// \n{4}{B}: "
                "Put target creature card from a graveyard onto the battlefield "
                "under your control."
            ),
        },
        _ir(),
    ),
    "free_plot": (
        {
            "name": "Fblthp, Lost on the Range",
            "type_line": "Legendary Creature — Homunculus",
            "oracle_text": (
                "Ward {2}\nYou may look at the top card of your library any time.\n"
                "The top card of your library has plot. The plot cost is equal to "
                "its mana cost.\nYou may plot nonland cards from the top of your "
                "library."
            ),
        },
        _ir(),
    ),
    "miracle_grant": (
        {
            "name": "Lorehold, the Historian",
            "type_line": "Legendary Creature — Elder Dragon",
            "oracle_text": (
                "Flying, haste\nEach instant and sorcery card in your hand has "
                "miracle {2}. (You may cast a card for its miracle cost when you "
                "draw it if it's the first card you drew this turn.)\nAt the "
                "beginning of each opponent's upkeep, you may discard a card. If "
                "you do, draw a card."
            ),
            "keywords": ["Flying", "Haste"],
        },
        _ir(),
    ),
    # ADR-0027 tranche2-batch-4 (t2b4a-A) structural ETB / predicate arms.
    # tribal_etb_multi ← an `etb` Trigger whose subject Filter names a creature
    # SUBTYPE (vocab-gated _kindred_subjects). Goblin Assassin: a Goblin-ETB chain.
    "tribal_etb_multi": (
        {
            "name": "Goblin Assassin",
            "type_line": "Creature — Goblin Assassin",
            "oracle_text": (
                "Whenever this creature or another Goblin enters, each player flips "
                "a coin. Each player whose coin comes up tails sacrifices a creature "
                "of their choice."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="etb",
                    subject=Filter(subtypes=("Goblin",), controller="you"),
                ),
            )
        ),
    ),
    # typed_enters_punish ← an `etb` Trigger on a YOUR creature/typed-thing whose
    # consequence is a `damage` Effect with an OPPONENT recipient. Purphoros: phase
    # scopes the damage 'any', the "each opponent" recipient survives in raw.
    "typed_enters_punish": (
        {
            "name": "Purphoros, God of the Forge",
            "type_line": "Legendary Enchantment Creature — God",
            "oracle_text": (
                "As long as your devotion to red is less than five, Purphoros isn't "
                "a creature.\nWhenever another creature you control enters, Purphoros "
                "deals 2 damage to each opponent.\n{2}{R}: Creatures you control get "
                "+1/+0 until end of turn."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="etb",
                    subject=Filter(
                        card_types=("Creature",),
                        controller="you",
                        predicates=("Another",),
                    ),
                ),
                effects=(
                    Effect(
                        category="damage",
                        scope="any",
                        amount=Quantity(op="fixed", factor=2),
                        raw="~ deals 2 damage to each opponent.",
                    ),
                ),
            )
        ),
    ),
    # vanilla_matters ← the HasNoAbilities subject-Filter predicate (read in
    # _predicate_build_around_lanes). Muraganda Petroglyphs: a shared-board anthem
    # over creatures with no abilities (controller 'any').
    "vanilla_matters": (
        {
            "name": "Muraganda Petroglyphs",
            "type_line": "Enchantment",
            "oracle_text": (
                "Creatures with no abilities get +2/+2. (A creature has no "
                "abilities if it has no keywords or printed rules text and no "
                "abilities have been granted to it.)"
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="any",
                        subject=Filter(
                            card_types=("Creature",),
                            controller="any",
                            predicates=("HasNoAbilities",),
                        ),
                        raw="Creatures with no abilities get +2/+2.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 tranche2-batch-4a (t2b4a-B):
    #   win_lose_game     ← Effect(category="win_game")            [structural]
    #   xspell_matters    ← HasXInManaCost predicate on a cast_spell trigger subject
    #   alt_cost_keyword  ← Scryfall "Mayhem" keyword              [_IR_KEYWORD_MAP]
    #   curse_matters     ← trigger subject Filter subtypes=("Curse",)
    #   partner_background← Scryfall "Friends" (Friends-forever) keyword
    "win_lose_game": (
        {
            "name": "Thassa's Oracle",
            "type_line": "Creature — Merfolk Wizard",
            "oracle_text": (
                "When this creature enters, look at the top X cards of your library, "
                "where X is your devotion to blue. Put up to one of them on top of "
                "your library and the rest on the bottom of your library in a random "
                "order. If X is greater than or equal to the number of cards in your "
                "library, you win the game. (Each {U} in the mana costs of permanents "
                "you control counts toward your devotion to blue.)"
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="win_game",
                        scope="you",
                        raw="you win the game",
                    ),
                ),
            )
        ),
    ),
    "xspell_matters": (
        {
            "name": "Zaxara, the Exemplary",
            "type_line": "Legendary Creature — Nightmare Hydra",
            "oracle_text": (
                "Deathtouch\n{T}: Add two mana of any one color.\nWhenever you cast a "
                "spell with {X} in its mana cost, create a 0/0 green Hydra creature "
                "token, then put X +1/+1 counters on it."
            ),
            "keywords": ["Deathtouch"],
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="cast_spell",
                    scope="you",
                    subject=Filter(predicates=("HasXInManaCost",)),
                ),
                effects=(
                    Effect(
                        category="make_token",
                        scope="you",
                        raw="create a 0/0 green Hydra creature token",
                    ),
                ),
            )
        ),
    ),
    "alt_cost_keyword": (
        {
            "name": "Chameleon, Master of Disguise",
            "type_line": "Legendary Creature — Human Shapeshifter Villain",
            "oracle_text": (
                "You may have Chameleon enter as a copy of a creature you control, "
                "except his name is Chameleon, Master of Disguise.\nMayhem {2}{U} "
                "(You may cast this card from your graveyard for {2}{U} if you "
                "discarded it this turn. Timing rules still apply.)"
            ),
            "keywords": ["Mayhem"],
        },
        # alt_cost_keyword is read off the Scryfall keyword array → bare non-None IR.
        _ir(),
    ),
    "curse_matters": (
        {
            "name": "Lynde, Cheerful Tormentor",
            "type_line": "Legendary Creature — Human Warlock",
            "oracle_text": (
                "Deathtouch\nWhenever a Curse is put into your graveyard from the "
                "battlefield, return it to the battlefield attached to you at the "
                "beginning of the next end step.\nAt the beginning of your upkeep, "
                "you may attach a Curse attached to you to one of your opponents. If "
                "you do, draw two cards."
            ),
            "keywords": ["Deathtouch"],
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="dies",
                    scope="you",
                    subject=Filter(subtypes=("Curse",), controller="you"),
                ),
            )
        ),
    ),
    "partner_background": (
        {
            "name": "Astarion, the Decadent",
            "type_line": "Legendary Creature — Vampire Elf Rogue",
            "oracle_text": (
                "Deathtouch, lifelink\nAt the beginning of your end step, choose "
                "one —\n• Feed — Target opponent loses life equal to the amount of "
                "life they lost this turn.\n• Friends — You gain life equal to the "
                "amount of life you gained this turn."
            ),
            "keywords": ["Lifelink", "Feed", "Friends", "Deathtouch"],
        },
        # partner_background is read off the Scryfall keyword array (Friends-forever
        # → "Friends") → bare non-None IR.
        _ir(),
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-B) — five kept_detector keys phase v0.1.60
    # CANNOT structure (the discriminant is DROPPED in the parse), each served from a
    # byte-identical _IR_KEPT_DETECTORS word mirror over the joined-face oracle. The
    # kept-detector loop reads get_oracle_text(card), so a bare _ir() suffices.
    "per_target_payoff": (
        {
            "name": "Hinata, Dawn-Crowned",
            "type_line": "Legendary Creature — Kirin Spirit",
            "oracle_text": (
                "Flying, trample\nSpells you cast cost {1} less to cast for each "
                "target.\nSpells your opponents cast cost {1} more to cast for each "
                "target."
            ),
            "keywords": ["Flying", "Trample"],
        },
        _ir(),
    ),
    "sacrifice_protection": (
        {
            "name": "Sigarda, Host of Herons",
            "type_line": "Legendary Creature — Angel",
            "oracle_text": (
                "Flying, hexproof\nSpells and abilities your opponents control "
                "can't cause you to sacrifice permanents."
            ),
            "keywords": ["Flying", "Hexproof"],
        },
        _ir(),
    ),
    "secret_writedown": (
        {
            "name": "Burning Wish",
            "type_line": "Sorcery",
            "oracle_text": (
                "You may reveal a sorcery card you own from outside the game and "
                "put it into your hand. Exile Burning Wish."
            ),
        },
        _ir(),
    ),
    "target_own_payoff": (
        {
            "name": "Monk Gyatso",
            "type_line": "Legendary Creature — Human Monk",
            "oracle_text": (
                "Whenever another creature you control becomes the target of a "
                "spell or ability, you may airbend that creature. (Exile it. While "
                "it's exiled, its owner may cast it for {2} rather than its mana "
                "cost.)"
            ),
        },
        _ir(),
    ),
    "target_redirect": (
        {
            "name": "Rayne, Academy Chancellor",
            "type_line": "Legendary Creature — Human Wizard",
            "oracle_text": (
                "Whenever you or a permanent you control becomes the target of a "
                "spell or ability an opponent controls, you may draw a card. You "
                "may draw an additional card if Rayne is enchanted."
            ),
        },
        _ir(),
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-C) — four kept_detector keys read by the
    # _IR_KEPT_DETECTORS word mirror (which scans the oracle text directly), so a bare
    # non-None IR routes the hybrid to the IR path; plus one keyword-array field lookup.
    "targeting_matters": (
        {
            "name": "Reality Smasher",
            "type_line": "Creature — Eldrazi",
            "oracle_text": (
                "({C} represents colorless mana.)\nTrample, haste\nWhenever this "
                "creature becomes the target of a spell an opponent controls, counter "
                "that spell unless its controller discards a card."
            ),
            "keywords": ["Haste", "Trample"],
        },
        _ir(),
    ),
    "theft_protection": (
        {
            "name": "Kira, Great Glass-Spinner",
            "type_line": "Legendary Creature — Spirit",
            "oracle_text": (
                'Flying\nCreatures you control have "Whenever this creature becomes '
                "the target of a spell or ability for the first time each turn, "
                'counter that spell or ability."'
            ),
            "keywords": ["Flying"],
        },
        _ir(),
    ),
    "villainous_choice": (
        {
            "name": "The Valeyard",
            "type_line": "Legendary Creature — Time Lord Noble",
            "oracle_text": (
                "If an opponent would face a villainous choice, they face that choice "
                "an additional time. (They can make the same or different choices.)\n"
                "While voting, you may vote an additional time."
            ),
        },
        _ir(),
    ),
    "named_counter_misc": (
        {
            "name": "Tetzimoc, Primal Death",
            "type_line": "Legendary Creature — Elder Dinosaur",
            "oracle_text": (
                "Deathtouch\n{B}, Reveal this card from your hand: Put a prey counter "
                "on target creature. Activate only during your turn.\nWhen Tetzimoc "
                "enters, destroy each creature your opponents control with a prey "
                "counter on it."
            ),
            "keywords": ["Deathtouch"],
        },
        _ir(),
    ),
    # powerup_matters is read off the Scryfall "Power-up" keyword array
    # (_IR_KEYWORD_MAP['power-up']) → bare non-None IR.
    "powerup_matters": (
        {
            "name": "Extremis Elite",
            "type_line": "Creature — Human Mercenary Villain",
            "oracle_text": (
                "Power-up — {4}{R}: Put two +1/+1 counters on this creature. It deals "
                "1 damage to any target. (Activate each power-up ability only once. "
                "Reduce the cost by its mana cost if it entered this turn.)"
            ),
            "keywords": ["Power-up"],
        },
        _ir(keywords=("Power-up",)),
    ),
    # cmdzone_ability ← an Eminence ability gated on the source being in the command
    # zone: phase models the gate as Condition(kind="sourceinzone",
    # zones=("command",)) (Oloro's triggered Eminence). extract_signals_ir fires the
    # lane when "command" is in the ability's recursive condition-zone tree (or in
    # ab.zones for an activate-from-CZ ability). The STATIC-Eminence cost-reducer
    # half (The Ur-Dragon), whose condition phase drops, rides the kept word mirror.
    "cmdzone_ability": (
        {
            "name": "Oloro, Ageless Ascetic",
            "type_line": "Legendary Creature — Giant Soldier",
            "oracle_text": (
                "At the beginning of your upkeep, you gain 2 life.\nWhenever you gain "
                "life, you may pay {1}. If you do, draw a card and each opponent "
                "loses 1 life.\nAt the beginning of your upkeep, if Oloro, Ageless "
                "Ascetic is in the command zone, you gain 2 life."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="upkeep"),
                condition=Condition(kind="sourceinzone", zones=("command",)),
                effects=(
                    Effect(
                        category="gain_life",
                        scope="you",
                        raw="if ~ is in the command zone, you gain 2 life",
                    ),
                ),
            )
        ),
    ),
    # opp_top_exile ← the impulse-cast structural arm: an exile Effect scope=='opp' co-
    # occurring (same ability) with a cast_from_zone Effect scope=='opp' (the "you may
    # cast them" follow-through). Villainous Wealth's "Target opponent exiles the top X
    # cards" does NOT match the kept word mirror (it's "exile the top card OF an
    # opponent", not "target opponent exiles"), so this is a pure structural-arm proof.
    "opp_top_exile": (
        {
            "name": "Villainous Wealth",
            "type_line": "Sorcery",
            "oracle_text": (
                "Target opponent exiles the top X cards of their library. You may "
                "cast any number of spells with mana value X or less from among them "
                "without paying their mana costs."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="exile",
                        scope="opp",
                        raw="Target opponent exiles the top X cards of their library.",
                    ),
                    Effect(
                        category="cast_from_zone",
                        scope="opp",
                        raw="You may cast any number of spells from among them.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 (q2-D3). flash_matters ← the GRANT half is the cast_with_keyword{flash}
    # static (the same node flash_grant reads). Leyline of Anticipation.
    "flash_matters": (
        {
            "name": "Leyline of Anticipation",
            "type_line": "Enchantment",
            "oracle_text": (
                "If this card is in your opening hand, you may begin the game with "
                "it on the battlefield.\nYou may cast spells as though they had "
                "flash."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cast_with_keyword",
                        counter_kind="flash",
                        scope="you",
                        raw="You may cast spells as though they had flash.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027. flash_grant ← the GRANT-to-OTHERS flash enabler is the
    # cast_with_keyword{flash} static (the same node flash_matters reads). Vedalken
    # Orrery ("You may cast spells as though they had flash").
    "flash_grant": (
        {
            "name": "Vedalken Orrery",
            "type_line": "Artifact",
            "oracle_text": "You may cast spells as though they had flash.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cast_with_keyword",
                        counter_kind="flash",
                        scope="you",
                        raw="You may cast spells as though they had flash.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027. dies_recursion ← a byte-identical _IR_KEPT_DETECTORS mirror of the
    # deleted SWEEP regex ("when this dies, return it to the battlefield" + the
    # undying/persist words). phase v0.1.19 carries no structural "returns itself on
    # death" form (the dies trigger flattens to event='other' with the return buried in
    # the effect raw), so the bare dies-return cards ride the kept mirror over the
    # card's oracle_text; the paired IR is vanilla — the mirror reads the record, not
    # the IR structure (the undying/persist keyword BEARERS take the separate
    # _IR_KEYWORD_MAP path). Bronzehide Lion's intrinsic "When this creature dies,
    # return it to the battlefield" is the bare dies-return form. CR 700.4 / 603.6c.
    "dies_recursion": (
        {
            "name": "Bronzehide Lion",
            "type_line": "Legendary Creature — Cat",
            "oracle_text": (
                "{G}{W}: This creature gains indestructible until end of turn.\n"
                "When this creature dies, return it to the battlefield. It's an "
                'Aura enchantment with enchant creature you control and "{G}{W}: '
                'Enchanted creature gains indestructible until end of turn," and '
                "it loses all other abilities."
            ),
        },
        _ir(),
    ),
    # ADR-0027 (q2-D3). noncreature_cast_punish ← the OPPONENT-punisher half is a
    # cast_spell trigger scope=='opp' over a NotType:Creature subject. Kambal.
    "noncreature_cast_punish": (
        {
            "name": "Kambal, Consul of Allocation",
            "type_line": "Legendary Creature — Human Advisor",
            "oracle_text": (
                "Whenever an opponent casts a noncreature spell, that player loses "
                "2 life and you gain 2 life."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="cast_spell",
                    scope="opp",
                    subject=Filter(
                        card_types=("Card",),
                        predicates=("NotType:Creature",),
                    ),
                ),
                effects=(
                    Effect(
                        category="lose_life",
                        amount=Quantity(op="fixed", factor=2),
                        raw="that player loses 2 life and you gain 2 life.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 β. impulse_top_play ← the structural arm: a NON-static cast_from_zone
    # Effect carrying the recovered 'from:library' zone (project._recover_library_zones,
    # SIDECAR_VERSION 4). Light Up the Stage's real IR is a `spell` ability whose
    # cast_from_zone effect plays the exiled top cards — the ab.kind!='static' gate keeps
    # it in this lane (vs the static play_from_top permission, which stays DEFERRED).
    "impulse_top_play": (
        {
            "name": "Light Up the Stage",
            "type_line": "Sorcery",
            "oracle_text": (
                "Spectacle {R} (You may cast this spell for its spectacle cost "
                "rather than its mana cost if an opponent lost life this turn.)\n"
                "Exile the top two cards of your library. Until the end of your "
                "next turn, you may play those cards."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="exile",
                        scope="any",
                        raw=(
                            "Exile the top two cards of your library. Until the "
                            "end of your next turn, you may play those cards."
                        ),
                    ),
                    Effect(
                        category="cast_from_zone",
                        scope="any",
                        zones=("from:library",),
                        raw=(
                            "Exile the top two cards of your library. Until the "
                            "end of your next turn, you may play those cards."
                        ),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 β. play_from_top ← the structural arm: a STATIC cast_from_zone Effect
    # carrying the recovered 'from:library' zone (project._top_play_permission_marker over
    # phase's TopOfLibraryCastPermission static mode, SIDECAR v16). Future Sight's real IR
    # is a kind='static' ability whose cast_from_zone effect plays from the top of the
    # library — the ab.kind=='static' gate keeps it in this lane (vs the non-static
    # impulse_top_play). The deleted SWEEP + _HAND_FLOOR regexes no longer fire on the
    # regex path; the `"exile" not in raw` gate (the permission text has no "exile")
    # admits it.
    "play_from_top": (
        {
            "name": "Future Sight",
            "type_line": "Enchantment",
            "oracle_text": (
                "Play with the top card of your library revealed.\n"
                "You may play lands and cast spells from the top of your library."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="cast_from_zone",
                        scope="you",
                        zones=("from:library",),
                        raw=(
                            "You may play lands and cast spells from the top of "
                            "your library."
                        ),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027. cast_from_exile ← the byte-identical kept WORD MIRROR (the
    # CAST_FROM_EXILE_REGEX row in _IR_KEPT_DETECTORS, scope "you", HIGH conf; CR 207.2c
    # / 601.3b). Vega, the Watcher is the canonical Paradox PAYOFF — "Whenever you cast a
    # spell from anywhere other than your hand, draw a card". The mirror reads the
    # reminder-stripped oracle_text off the record dict (not the IR structure — phase
    # carries NO usable structural form: it drops the "from exile" zone off both the
    # cast_spell trigger AND the self-cast cast_from_zone Effect, and the only exile
    # cast-zone it projects — castable_zones=('exile',) — is the foretell-spell serve
    # pool, disjoint from the detector firings), so a bare non-None IR routes the hybrid
    # to the IR path. The regex path no longer emits the key (the _HAND_FLOOR producer is
    # deleted). scope "you". ADR-0027.
    "cast_from_exile": (
        {
            "name": "Vega, the Watcher",
            "type_line": "Legendary Creature — Bird Spirit",
            "oracle_text": (
                "Flying\n"
                "Whenever you cast a spell from anywhere other than your hand, "
                "draw a card."
            ),
        },
        _ir(),
    ),
    # ADR-0027. exile_matters ← the byte-identical kept WORD MIRROR (the
    # EXILE_MATTERS_REGEX row in _IR_KEPT_DETECTORS, scope "you", HIGH conf; CR 406).
    # Mairsil, the Pretender is the canonical EXILE-ZONE-AS-RESOURCE engine — "Mairsil has
    # all activated abilities of all cards you own in exile with cage counters on them"
    # (the cage-counter exile pile is a STANDING resource it draws abilities from). The
    # mirror reads the reminder-stripped oracle_text off the record dict (not the IR
    # structure — phase carries NO usable structural form: it scatters the exile-zone
    # reference across a zones=("in:exile",) count operand, a Condition(zones=("exile",)),
    # and a characteristic_pt Effect whose count operand drops the zone, with no single
    # category meaning "references cards standing in exile"), so a bare non-None IR routes
    # the hybrid to the IR path. The regex path no longer emits the key (the _HAND_FLOOR
    # producer is deleted). scope "you". Distinct from exile_removal / cast_from_exile /
    # opponent_exile_matters. ADR-0027.
    "exile_matters": (
        {
            "name": "Mairsil, the Pretender",
            "type_line": "Legendary Creature — Human Wizard",
            "oracle_text": (
                "When Mairsil enters, you may exile an artifact or creature card "
                "from your hand or graveyard and put a cage counter on it.\n"
                "Mairsil has all activated abilities of all cards you own in exile "
                "with cage counters on them. You may activate each of those "
                "abilities only once each turn."
            ),
        },
        _ir(),
    ),
    # ADR-0027 β. free_spell_storm ← the structural arm: a dedicated `free_spell_storm`
    # STATIC marker Effect (project._free_spell_storm_marker over phase's SelfRef
    # ModifyCost{Reduce} static, SIDECAR v20). Thrasta's cost drops {3} per other spell
    # cast this turn, so it wants free spells to chain — the marker re-surfaces the static
    # the SelfRef cost-reducer branch drops (a self-discount is rules-excluded from the
    # build-around cost_reduction lane). The deleted _HAND_FLOOR regex no longer fires on
    # the regex path; the IR arm reads the dedicated category.
    "free_spell_storm": (
        {
            "name": "Thrasta, Tempest's Roar",
            "type_line": "Legendary Creature — Dinosaur",
            "oracle_text": (
                "This spell costs {3} less to cast for each other spell cast this "
                "turn.\nTrample, haste\nTrample over planeswalkers (This creature can "
                "deal excess combat damage to the controller of the planeswalker it's "
                "attacking.)\nThrasta has hexproof as long as it entered this turn."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="free_spell_storm",
                        scope="you",
                        raw=(
                            "This spell costs {3} less to cast for each other spell "
                            "cast this turn."
                        ),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 β. edict_matters ← the structural opp/each `sacrifice` arm: a forced
    # PLAYER sacrifice (CR 701.16). Plaguecrafter's ETB makes each player sacrifice a
    # creature or planeswalker — phase emits scope "each" with the sacrificed subject's
    # controller "any". _ir_effect_is_edict KEEPs it (the raw names "each player
    # sacrifices", the affirmative edict tell), so the IR arm emits edict_matters at
    # scope "each"; the deleted SWEEP regex no longer fires on the regex path.
    "edict_matters": (
        {
            "name": "Plaguecrafter",
            "type_line": "Creature — Human Shaman",
            "oracle_text": (
                "When this creature enters, each player sacrifices a creature or "
                "planeswalker of their choice. Each player who can't discards a card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="sacrifice",
                        scope="each",
                        subject=Filter(
                            card_types=("Creature", "Planeswalker"),
                            controller="any",
                        ),
                        raw=(
                            "When ~ enters, each player sacrifices a creature or "
                            "planeswalker of their choice. Each player who can't "
                            "discards a card."
                        ),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 β. tribe_damage_trigger ← a byte-identical _IR_KEPT_DETECTORS mirror of
    # the deleted SWEEP regex. phase leaves the combat_damage trigger subject = None (no
    # structure to read), so the kept mirror scans the record's oracle_text directly and
    # any non-None IR routes the hybrid to the IR path. Under re.IGNORECASE the regex's
    # `[A-Z][a-z]+` also matches a generic "creature", so the lane fires on Toski's
    # "Whenever a creature you control deals combat damage to a player" — the lane is
    # really "your creatures connect for combat damage → reward", not strictly tribal.
    "tribe_damage_trigger": (
        {
            "name": "Toski, Bearer of Secrets",
            "type_line": "Legendary Creature — Squirrel",
            "oracle_text": (
                "Toski, Bearer of Secrets can't be countered.\nWhenever a "
                "creature you control deals combat damage to a player, draw a "
                "card.\nToski can't be blocked.\nOther Squirrels you control "
                "have haste."
            ),
        },
        _ir(),
    ),
    # ADR-0027 β kept-mirror — combat_damage_to_creature: the RECIPIENT-TYPE split phase
    # can't make structurally (it drops valid_target's TYPE onto the combat_damage
    # trigger, so a creature- and a player-recipient trigger project byte-identically).
    # The discriminator survives in the joined-face oracle ("to a creature"), so this is a
    # byte-identical _IR_KEPT_DETECTORS mirror of the deleted SWEEP regex. Voracious Cobra
    # is a CLEAN creature-recipient ("deals combat damage to a creature, destroy that
    # creature") — its oracle never says "to a player", so the sibling combat_damage_to_opp
    # lane stays silent. Bare IR (the mirror scans the record's oracle_text).
    "combat_damage_to_creature": (
        {
            "name": "Voracious Cobra",
            "type_line": "Creature — Snake",
            "oracle_text": (
                "First strike\nWhenever this creature deals combat damage to a "
                "creature, destroy that creature."
            ),
        },
        _ir(),
    ),
    # ADR-0027 β kept-mirror — combat_damage_to_opp: the player-recipient half of the
    # same split. Cold-Eyed Selkie is a CLEAN player-recipient ("deals combat damage to a
    # player"); its oracle never says "to a creature", so the sibling
    # combat_damage_to_creature lane stays silent. Bare IR.
    "combat_damage_to_opp": (
        {
            "name": "Cold-Eyed Selkie",
            "type_line": "Creature — Merfolk Rogue",
            "oracle_text": (
                "Islandwalk (This creature can't be blocked as long as "
                "defending player controls an Island.)\nWhenever this creature "
                "deals combat damage to a player, you may draw that many cards."
            ),
        },
        _ir(),
    ),
    # ADR-0027 β projection — damage_to_opp_matters: the GENERAL (any-source, ANY
    # damage) "deals damage to a PLAYER / opponent" connect-payoff. Deus of Calamity is
    # the STRUCTURAL-ONLY case that proves the projection is load-bearing: its "deals 6
    # OR MORE damage to an opponent" never matches the deleted word-order regex (so the
    # byte-identical kept mirror does NOT fire it), yet phase keeps the player recipient
    # on the DamageDone trigger's valid_target — which project re-surfaces as the
    # DamageToPlayer marker on the deals_damage trigger subject (SIDECAR v13). The
    # structural arm fires the lane on the marker. (combat-only recipients carry
    # event=='combat_damage', not 'deals_damage', so combat_damage_to_opp stays silent.)
    "damage_to_opp_matters": (
        {
            "name": "Deus of Calamity",
            "type_line": "Creature — Spirit Avatar",
            "oracle_text": (
                "Trample\nWhenever this creature deals 6 or more damage to an "
                "opponent, destroy target land that player controls."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(
                    event="deals_damage",
                    scope="opp",
                    subject=Filter(predicates=("DamageToPlayer",)),
                ),
                effects=(
                    Effect(
                        category="destroy",
                        raw=(
                            "Whenever this creature deals 6 or more damage to an "
                            "opponent, destroy target land that player controls."
                        ),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 kept-mirror — combat_damage_matters: the BASE CR-510 combat-damage payoff
    # (parent of the combat_* siblings above). The unconditional structural arm over-fired
    # the recipient (every combat_damage AND deals_damage trigger regardless of recipient),
    # so the lane rides a byte-identical _IR_KEPT_DETECTORS mirror of the deleted _DETECTORS
    # regex, anchored on the player/opponent recipient. Edric is a CLEAN player-recipient
    # ("deals combat damage to one of your opponents"); its oracle never says "to a
    # creature", so the structural arm's would-be creature/noncombat over-fire is absent.
    # Bare IR (the mirror scans the record's oracle_text directly).
    "combat_damage_matters": (
        {
            "name": "Edric, Spymaster of Trest",
            "type_line": "Legendary Creature — Elf Rogue",
            "oracle_text": (
                "Whenever a creature deals combat damage to one of your "
                "opponents, its controller may draw a card."
            ),
        },
        _ir(),
    ),
    # ADR-0027 β kept-mirror: phase's legend_exempt drops the BOUNDED variant
    # ("doesn't apply to permanents you control"), so Mirror Box has no structural
    # form — the byte-identical _IR_KEPT_DETECTORS mirror is what recovers it. Bare IR.
    "legend_rule_off": (
        {
            "name": "Mirror Box",
            "type_line": "Artifact",
            "oracle_text": (
                'The "legend rule" doesn\'t apply to permanents you control.\n'
                "Each legendary creature you control gets +1/+1.\nEach nontoken "
                "creature you control gets +1/+1 for each other creature you "
                "control with the same name as that creature."
            ),
        },
        _ir(),
    ),
    # ADR-0027 β kept-mirror: phase drops the cast-timing static entirely, so City of
    # Solitude has no structural form — the byte-identical _IR_KEPT_DETECTORS mirror is
    # what recovers it. Bare IR.
    "timing_control": (
        {
            "name": "City of Solitude",
            "type_line": "Enchantment",
            "oracle_text": (
                "Players can cast spells and activate abilities only during "
                "their own turns."
            ),
        },
        _ir(),
    ),
    # ADR-0027 β power-as-damage cluster. The damage Effect carries the op="power"
    # anchor (the d6620ac projection unlock). Soul's Fire = a creature_ping: a
    # SEPARATE target_only Effect names the you-controller Creature DOER, so the arm
    # fires creature_ping (it ALSO fires damage_equal_power via the "to any target"
    # player-reach raw — matching the deleted regexes' overlap — but the assert only
    # checks creature_ping is served).
    "creature_ping": (
        {
            "name": "Soul's Fire",
            "type_line": "Instant",
            "oracle_text": (
                "Target creature you control deals damage equal to its power to "
                "any target."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="target_only",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw=(
                            "Target creature you control deals damage equal to "
                            "its power to any target."
                        ),
                    ),
                    Effect(
                        category="damage",
                        amount=Quantity(op="power"),
                        raw=(
                            "Target creature you control deals damage equal to "
                            "its power to any target."
                        ),
                    ),
                ),
            )
        ),
    ),
    # Fling = a damage_equal_power: the op="power" damage reaches "any target" (a
    # player), and there is NO you-controller Creature DOER sibling — the source is
    # the spell / sacrificed creature ("the sacrificed creature's power"), so the
    # creature_ping doer test fails (the raw names a DIFFERENT object's power, not
    # "its power"). The additional-cost sacrifice is a separate static Effect.
    "damage_equal_power": (
        {
            "name": "Fling",
            "type_line": "Instant",
            "oracle_text": (
                "As an additional cost to cast this spell, sacrifice a "
                "creature.\nFling deals damage equal to the sacrificed "
                "creature's power to any target."
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="damage",
                        amount=Quantity(op="power"),
                        raw=(
                            "~ deals damage equal to the sacrificed creature's "
                            "power to any target."
                        ),
                    ),
                ),
            ),
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="sacrifice",
                        scope="you",
                        subject=Filter(card_types=("Creature",)),
                        raw="additional cost: sacrifice a permanent",
                    ),
                ),
            ),
        ),
    ),
    # global_ability_grant ← a board_grant Effect carrying counter_kind="grant_ability"
    # (project._global_ability_grant_markers), the v9 marker the extract_signals_ir arm
    # reads. Cryptolith Rite grants a QUOTED activated ability ("{T}: Add one mana of any
    # color.") to your whole creature board — the QUOTE is the tell that splits it from a
    # bare keyword anthem (grant_keyword). The arm fires scope "any", the deleted SWEEP
    # detector's firing identity. ADR-0027 β.
    "global_ability_grant": (
        {
            "name": "Cryptolith Rite",
            "type_line": "Enchantment",
            "oracle_text": (
                'Creatures you control have "{T}: Add one mana of any color."'
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="board_grant",
                        scope="you",
                        counter_kind="grant_ability",
                        subject=Filter(card_types=("Creature",), controller="you"),
                        raw='Creatures you control have "{T}: Add one mana of any color."',
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 β projection — keyword_grant_target: a keyword grant to a SINGLE TARGET
    # creature. Aim High is the STRUCTURAL-ONLY case that proves the projection is
    # load-bearing: its "Untap target creature. It gains reach" uses the "It gains X"
    # idiom, which the deleted word-order regex never matched (so the byte-identical kept
    # mirror does NOT fire it), yet phase keeps the real Typed-creature target on the
    # untap effect — which project re-surfaces as the single_target_grant marker (subject
    # = the creature target + a "SingleTarget" predicate, SIDECAR v14). The structural
    # arm fires the lane on the marker; the SingleTarget predicate guards it out of every
    # team/anthem grant_keyword gate, so the +2236 flood is structurally impossible.
    "keyword_grant_target": (
        {
            "name": "Aim High",
            "type_line": "Instant",
            "oracle_text": (
                "Untap target creature. It gets +2/+2 and gains reach until "
                "end of turn."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="single_target_grant",
                        scope="any",
                        subject=Filter(
                            card_types=("Creature",),
                            predicates=("SingleTarget",),
                        ),
                        raw="get +2/+2 and gains reach",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 β — activated_ability: a card whose ENGINE is a MEANINGFUL activated
    # ability. The Scarab God is the load-bearing case for BOTH discriminators that kill
    # the deleted regex's land/mana flood: its {2}{U}{B} cost projects to
    # cost='genericmana,mana' (the SIDECAR-v15 genericmana token — distinct from a
    # colored-only firebreathing {R}: cost the regex's generic branch excluded), and its
    # effects are 'exile'+'make_token' (NON-ramp — proving the is_mana_ability gate: a
    # {T}: Add mana ability projects ONLY 'ramp' and is dropped). The arm fires the lane
    # scope "you" off this ability; the deleted regex's bare cost shape would also have
    # fired on every basic land / Sol Ring / mana dork's "{T}: Add", which the arm now
    # excludes. The regex path no longer fires activated_ability at all (row deleted).
    "activated_ability": (
        {
            "name": "The Scarab God",
            "type_line": "Legendary Creature — God",
            "oracle_text": (
                "At the beginning of your upkeep, each opponent loses X life "
                "and you scry X, where X is the number of Zombies you control.\n"
                "{2}{U}{B}: Exile target creature card from a graveyard. Create "
                "a token that's a copy of it, except it's a 4/4 black Zombie.\n"
                "When The Scarab God dies, return it to its owner's hand at the "
                "beginning of the next end step."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                cost="genericmana,mana",
                effects=(
                    Effect(category="exile", scope="any", raw="exile target"),
                    Effect(
                        category="make_token",
                        scope="you",
                        raw="create a token that's a copy",
                    ),
                ),
            )
        ),
    ),
    # proliferate_matters ← the Scryfall "Proliferate" keyword (CR 701.27), read by
    # the IR path via _IR_KEYWORD_MAP (the keyword's "add another counter of each
    # kind" lives in stripped reminder text, so a vanilla-keyword body fires no
    # proliferate Effect — the keyword array is the structured anchor). Evolution
    # Sage is the canonical proliferate ENGINE (every landfall proliferates every
    # counter on the board). The regex path no longer emits it (the preset keyword
    # entry moved to _IR_KEYWORD_MAP). ADR-0027.
    "proliferate_matters": (
        {
            "name": "Evolution Sage",
            "type_line": "Creature — Elf Druid",
            "oracle_text": (
                "Landfall — Whenever a land you control enters, proliferate. "
                "(Choose any number of permanents and/or players, then give each "
                "another counter of each kind already there.)"
            ),
            "keywords": ["Proliferate", "Landfall"],
        },
        _ir(keywords=("Proliferate",)),
    ),
    # ADR-0027 — artifacts_matter: a COUNT operand over YOUR artifacts (the
    # `_TYPE_MATTERS_LANE` go-wide DOER, affinity CR 702.41 / CR 604.3). Storm-Kiln
    # Artist's static "This creature gets +1/+0 for each artifact you control" projects a
    # `pump` Effect whose amount.subject IS the Artifact-typed own-board filter; the
    # structural arm in extract_signals_ir reads that subject through _typed_matters_lanes
    # and fires artifacts_matter scope "you" — NO oracle regex needed (the mirror is the
    # fallback, not this case's proof). The regex path no longer fires the lane (the
    # _HAND_FLOOR producer is deleted; this card has no "if you control an artifact" SWEEP
    # match — its Treasure-maker branch lived in the deleted producer). CR 702.41 / 604.3.
    "artifacts_matter": (
        {
            "name": "Storm-Kiln Artist",
            "type_line": "Creature — Dwarf Shaman",
            "oracle_text": (
                "This creature gets +1/+0 for each artifact you control.\n"
                "Magecraft — Whenever you cast or copy an instant or sorcery "
                "spell, create a Treasure token. (It's an artifact with \"{T}, "
                'Sacrifice this token: Add one mana of any color.")'
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="you",
                        amount=Quantity(
                            op="multiply",
                            factor=1,
                            subject=Filter(card_types=("Artifact",), controller="you"),
                        ),
                        raw="This creature gets +1/+0 for each artifact you control.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — enchantments_matter: a COUNT operand over YOUR enchantments (the
    # `_TYPE_MATTERS_LANE` go-wide DOER, shared with artifacts_matter; Auras / Sagas / Roles
    # are all enchantments per CR 205.2 / 303 / 303.7). Tuvasa the Sunlit's static "Tuvasa
    # gets +1/+1 for each enchantment you control" projects a `pump` Effect whose
    # amount.subject IS the Enchantment-typed own-board filter; the structural arm in
    # extract_signals_ir reads that subject through _typed_matters_lanes and fires
    # enchantments_matter scope "you" — NO oracle regex needed (the mirror is the fallback,
    # not this case's proof). The regex path no longer fires the lane (the _HAND_FLOOR
    # producer + the type_line membership producer are deleted). CR 205.2 / 303 / 604.3.
    "enchantments_matter": (
        {
            "name": "Tuvasa the Sunlit",
            "type_line": "Legendary Creature — Merfolk Shaman",
            "oracle_text": (
                "Tuvasa gets +1/+1 for each enchantment you control.\n"
                "Whenever you cast your first enchantment spell each turn, "
                "draw a card."
            ),
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="pump",
                        scope="any",
                        amount=Quantity(
                            op="count",
                            factor=1,
                            subject=Filter(
                                card_types=("Enchantment",), controller="you"
                            ),
                        ),
                        raw="~ gets +1/+1 for each enchantment you control.",
                    ),
                ),
            )
        ),
    ),
    # landfall ← the BYTE-IDENTICAL kept mirror (_LANDFALL_MIRROR + the inline
    # "whenever a land" & "enter" substring-AND). Lotus Cobra is the canonical landfall
    # payoff — the "Landfall —" ability word (CR 207.2c) over the dict oracle fires the
    # mirror with an empty IR. The structural land-ETB trigger arm + the extra-land /
    # land-recursion mirror branches are exercised in test_signals.py /
    # test_signals_effect_axes.py. The regex path no longer emits it (the _DETECTORS
    # producer is deleted). ADR-0027.
    "landfall": (
        {
            "name": "Lotus Cobra",
            "type_line": "Creature — Snake",
            "oracle_text": (
                "Landfall — Whenever a land you control enters, add one mana of "
                "any color."
            ),
            "keywords": ["Landfall"],
        },
        _ir(),
    ),
    # mill_matters ← the Scryfall `Mill` keyword array via _IR_KEYWORD_MAP['mill']
    # (CR 701.13). Stitcher's Supplier is the canonical self-mill body ("mill three
    # cards"); the keyword is read off the record dict, not the IR structure, so a bare
    # non-None IR routes the hybrid to the IR path. The effect-category doer arm was
    # DELETED (it mislabeled 3 non-mill effects); the regex path no longer emits the key
    # (the _PRESET_KEYWORD_SIGNALS preset is deleted). scope "any". ADR-0027.
    "mill_matters": (
        {
            "name": "Stitcher's Supplier",
            "type_line": "Creature — Zombie",
            "oracle_text": (
                "When this creature enters or dies, mill three cards. (Put the "
                "top three cards of your library into your graveyard.)"
            ),
            "keywords": ["Mill"],
        },
        _ir(),
    ),
    # land_destruction ← the membership-gated _LAND_DESTRUCTION_MIRROR arm (CR 305.6).
    # Numot is the canonical LD COMMANDER — a CREATURE whose own ability says "destroy
    # up to two target lands" (a repeatable LD engine). The mirror reads type_line +
    # oracle_text off the record dict (creature + include_membership gated, LOW conf),
    # not the IR structure, so a bare non-None IR routes the hybrid to the IR path. The
    # broad `destroy`/Land structural arm was REMOVED (it floods one-shot LD spells);
    # the regex path no longer emits the key (the include_membership cross-open is
    # deleted). scope "you". ADR-0027.
    "land_destruction": (
        {
            "name": "Numot, the Devastator",
            "type_line": "Legendary Creature — Dragon",
            "oracle_text": (
                "Flying\nWhenever Numot deals combat damage to a player, you may "
                "pay {2}{R}. If you do, destroy up to two target lands."
            ),
            "keywords": ["Flying"],
        },
        _ir(),
    ),
    # second_spell_matters ← a byte-identical _SECOND_SPELL_MIRROR in
    # _IR_KEPT_DETECTORS for the SPECIFIC "whenever you cast your second spell each
    # turn" payoff (distinct from the broad spellcast_matters — phase parses the
    # second-spell trigger as a bare `cast_spell` with no "second spell" qualifier,
    # so there's no structural arm). The mirror reads the record's oracle_text, so a
    # bare non-None IR routes the hybrid to the IR path. scope "you". ADR-0027.
    "second_spell_matters": (
        {
            "name": "Saruman of Many Colors",
            "type_line": "Legendary Creature — Avatar Wizard",
            "oracle_text": (
                "Ward {3}\nWhenever you cast your second spell each turn, each "
                "opponent mills two cards. When one or more cards are milled this "
                "way, exile target enchantment, instant, or sorcery card with "
                "equal or lesser mana value than that spell from an opponent's "
                "graveyard. Copy the exiled card. You may cast the copy without "
                "paying its mana cost."
            ),
            "keywords": ["Ward"],
        },
        _ir(),
    ),
    # land_sacrifice_matters ← the byte-identical kept WORD MIRROR (the
    # LAND_SACRIFICE_REGEX row in _IR_KEPT_DETECTORS, scope "you", HIGH conf; CR
    # 701.16). The Gitrog Monster is the canonical land-sac COMMANDER — it pays an
    # ongoing land-sac cost ("sacrifice The Gitrog Monster unless you sacrifice a land")
    # AND draws when lands hit the graveyard ("whenever one or more land cards are put
    # into your graveyard … draw a card"). The mirror reads the reminder-stripped
    # oracle_text off the record dict (not the IR structure — phase carries NO
    # structural form, the structural sacrifice arm emits this lane on 0 cards), so a
    # bare non-None IR routes the hybrid to the IR path. The regex path no longer emits
    # the key (the _HAND_FLOOR producer is deleted). scope "you". ADR-0027.
    "land_sacrifice_matters": (
        {
            "name": "The Gitrog Monster",
            "type_line": "Legendary Creature — Frog Horror",
            "oracle_text": (
                "Deathtouch\n"
                "At the beginning of your upkeep, sacrifice The Gitrog Monster "
                "unless you sacrifice a land.\n"
                "You may play an additional land on each of your turns.\n"
                "Whenever one or more land cards are put into your graveyard from "
                "anywhere, draw a card."
            ),
        },
        _ir(),
    ),
    # kicked_spell_matters ← the byte-identical _KICKED_SPELL_MIRROR in
    # _IR_KEPT_DETECTORS for the Kicker build-around (CR 702.33): the "whenever you cast
    # a kicked spell" PAYOFF (distinct from the bare `\bkicked\b` keyword route, which
    # over-fires +171 — the lane is the PAYOFF/CONDITION, not Kicker presence). Verazol
    # is the canonical kicked-spell payoff commander. The mirror reads the record's
    # oracle_text, so a bare non-None IR routes the hybrid to the IR path. The regex
    # path no longer emits the key (the _HAND_FLOOR producer is deleted). scope "you".
    # ADR-0027.
    "kicked_spell_matters": (
        {
            "name": "Verazol, the Split Current",
            "type_line": "Legendary Creature — Hydra",
            "oracle_text": (
                "Verazol, the Split Current enters with a +1/+1 counter on it for "
                "each mana spent to cast it.\n"
                "Whenever you cast a kicked spell, you may remove two +1/+1 "
                "counters from Verazol, the Split Current. If you do, copy that "
                "spell. You may choose new targets for the copy."
            ),
        },
        _ir(),
    ),
    # extra_combats ← phase's ACCURATE structural form: the `extra_combat` effect
    # category fires the lane through the _DOER_EFFECT_KEYS doer loop (scope "you",
    # HIGH conf; CR 505.1a / 720). Aggravated Assault is the canonical extra-combat
    # ENABLER — "After this main phase, there is an additional combat phase". The IR
    # carries an Effect(category="extra_combat"), so the structural arm serves it; the
    # regex path no longer emits the key (the `extra-combats` _PRESET_REGEX_SIGNALS
    # producer is deleted). The under-structured tail (Illusionist's Gambit, which phase
    # folds into a lone `restriction` effect) rides the byte-identical EXTRA_COMBATS_REGEX
    # word mirror in _IR_KEPT_DETECTORS; structural union mirror == the deleted regex's 43.
    # scope "you". ADR-0027.
    "extra_combats": (
        {
            "name": "Aggravated Assault",
            "type_line": "Enchantment",
            "oracle_text": (
                "{3}{R}{R}: Untap all creatures you control. After this main "
                "phase, there is an additional combat phase followed by an "
                "additional main phase. Activate only as a sorcery."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                effects=(
                    Effect(
                        category="extra_combat",
                        scope="you",
                        raw="there is an additional combat phase",
                    ),
                ),
            ),
        ),
    ),
    # extra_turns ← the STRUCTURAL `extra_turn` effect-category arm
    # (_DOER_EFFECT_KEYS["extra_turn"] → add("extra_turns","you"), scope "you", HIGH
    # conf; CR 500.7) is the primary IR producer; the 6 cards where phase folds "take
    # an extra turn" into a sibling category ride the byte-identical EXTRA_TURNS_REGEX
    # _IR_KEPT_DETECTORS mirror. Temporal Manipulation is the canonical time-walk
    # payoff ("Take an extra turn after this one.") — the imperative form the bare
    # mirror reads off the record's oracle_text (a bare non-None IR routes the hybrid
    # to the IR path; the structural arm needs a phase-parsed extra_turn effect, so the
    # mirror is what fires for this bare _ir()). The regex path no longer emits the key
    # (the `extra-turns` theme preset is deleted). scope "you". ADR-0027.
    "extra_turns": (
        {
            "name": "Temporal Manipulation",
            "type_line": "Sorcery",
            "oracle_text": "Take an extra turn after this one.",
        },
        _ir(),
    ),
    # daynight_matters ← TWO structural arms (CR 726, Day/Night): the daybound /
    # nightbound Scryfall KEYWORD via _IR_KEYWORD_MAP (read off the record dict's
    # `keywords` array) PLUS the `day_night` EFFECT-category doer via _DOER_EFFECT_KEYS
    # (the "it becomes day/night" transition payoff phase structures cleanly). Tovolar
    # is the canonical Day/Night commander, firing BOTH arms (it carries the Daybound
    # keyword AND an upkeep "it becomes night" flip → a `day_night` effect). NO mirror
    # is needed — phase structures both halves, so the two arms reproduce the deleted
    # _HAND_FLOOR regex byte-identically. The regex path no longer emits the key (the
    # _HAND_FLOOR producer is deleted). scope "you". ADR-0027.
    "daynight_matters": (
        {
            "name": "Tovolar, Dire Overlord",
            "type_line": "Legendary Creature — Human Werewolf",
            "oracle_text": (
                "Whenever a Wolf or Werewolf you control deals combat damage to a "
                "player, draw a card.\n"
                "At the beginning of your upkeep, if you control three or more "
                "Wolves and/or Werewolves, it becomes night. Then transform any "
                "number of Human Werewolves you control.\n"
                "Daybound"
            ),
            "keywords": ["Daybound"],
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="upkeep", scope="any"),
                effects=(Effect(category="day_night", scope="any"),),
            ),
            keywords=("Daybound",),
        ),
    ),
    # ADR-0027 — stax_taxes: a static RESTRICTION/TAX on OPPONENTS. The structural arm
    # fires on a `restriction` Effect whose v22 scope=='opp'. Gnat Miser's hand-size tax
    # is GENUINE ir_only recall (the deleted regex carried no "maximum hand size" branch,
    # so the regex path drops it; the IR `restriction` scope=='opp' arm serves it). The
    # kept SWEEP row never matches "maximum hand size is reduced", so the regex path is
    # clean. CR 604.1.
    "stax_taxes": (
        {
            "name": "Gnat Miser",
            "type_line": "Creature — Spirit",
            "oracle_text": "Each opponent's maximum hand size is reduced by one.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="restriction",
                        scope="opp",
                        raw="Each opponent's maximum hand size is reduced by one.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — direct_damage: a source that CAN deal damage to a PLAYER (CR 120.1 /
    # 115.4). Sizzle is the CLEAN player-burn case — "deals 3 damage to each opponent"
    # projects a `damage` Effect scope=='opp' (the v22 recipient scope), which always
    # reaches a player, so the structural arm in extract_signals_ir fires direct_damage
    # scope "you" with NO creature subject in play (it can't be misread as removal). Its
    # oracle never says "each player", so the sibling symmetric_damage_each stays
    # silent.
    "direct_damage": (
        {
            "name": "Sizzle",
            "type_line": "Sorcery",
            "oracle_text": "Sizzle deals 3 damage to each opponent.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="damage",
                        scope="opp",
                        raw="~ deals 3 damage to each opponent.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — symmetric_stax: a controller-NEUTRAL lock affecting EVERYONE. The
    # structural arm fires on a `restriction` Effect whose v22 scope=='each'. Cursed
    # Totem's symmetric ability-shutoff is GENUINE ir_only recall (the SYMMETRIC_STAX
    # SWEEP regex matches only "players can't …" / "enter tapped" / "untap during …", not
    # "Activated abilities of creatures can't be activated", so the regex path drops it;
    # the IR scope=='each' arm serves it). CR 604.1.
    "symmetric_stax": (
        {
            "name": "Cursed Totem",
            "type_line": "Artifact",
            "oracle_text": "Activated abilities of creatures can't be activated.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="restriction",
                        scope="each",
                        raw="Activated abilities of creatures can't be activated.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — symmetric_damage_each: damage dealt to EACH player (CR 102.2 — an
    # opponent is not you, so "each opponent" is direct_damage, not this). Pestilence is
    # the canonical case — "deals 1 damage to each creature and each player" projects a
    # `damage` Effect scope=='each' (the v22 each-player recipient scope), which the
    # structural arm in extract_signals_ir reads directly. The subject Filter(Creature)
    # is the each-creature half; the scope=='each' is the each-PLAYER half that opens
    # this lane.
    "symmetric_damage_each": (
        {
            "name": "Pestilence",
            "type_line": "Enchantment",
            "oracle_text": (
                "At the beginning of the end step, if no creatures are on the "
                "battlefield, sacrifice this enchantment.\n{B}: This enchantment "
                "deals 1 damage to each creature and each player."
            ),
        },
        _ir(
            Ability(
                kind="activated",
                cost="{B}",
                effects=(
                    Effect(
                        category="damage",
                        scope="each",
                        counter_kind="all",
                        subject=Filter(card_types=("Creature",)),
                        raw=("{B}: ~ deals 1 damage to each creature and each player."),
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — big_mana (a COMMANDER that makes a LOT of mana wants X-spell sinks). The
    # STRUCTURAL arm in extract_signals_ir (include_membership-gated) reads the v23
    # mana-amount projection — a `ramp` Effect whose amount is amount.factor>1 (Gilded
    # Lotus "Add three mana of any one color" → factor=3) OR op=="variable" (a dynamic
    # scaler). A factor==1 dork (Llanowar — "Add {G}") is one mana and is EXCLUDED. Gilded
    # Lotus is GENUINE ir_only recall: its oracle has no `{X}{Y}` / "for each" / "an
    # additional" tell, so the deleted _BIG_MANA_RE never matched it — the regex path drops
    # it, the v23 structural arm serves it. (The "add … for each" under-structured tail —
    # Neheb → amount==None — rides the byte-identical _BIG_MANA_REGEX kept mirror instead.)
    # scope 'you', LOW conf. CR 106.4.
    "big_mana": (
        {
            "name": "Gilded Lotus",
            "type_line": "Artifact",
            "oracle_text": "{T}: Add three mana of any one color.",
        },
        _ir(
            Ability(
                kind="activated",
                cost="tap",
                effects=(
                    Effect(
                        category="ramp",
                        scope="you",
                        amount=Quantity(op="fixed", factor=3),
                        raw="{T}: Add three mana of any one color.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — big_hand_matters: a "no maximum hand size" ENABLER (CR 402.2 — it
    # removes the normal seven-card cap, so a full grip survives the cleanup step).
    # Reliquary Tower projects a v23 `no_max_handsize` Effect (scope you) from phase's
    # bare `NoMaximumHandSize` static mode, which the structural arm in
    # extract_signals_ir reads directly. The "X = cards in your hand" P/T-scaling
    # payoffs (Maro, Psychosis Crawler) instead ride the byte-identical
    # _BIG_HAND_MATTERS_MIRROR kept word mirror — phase encodes those as a
    # `characteristic_pt` Effect with NO in:hand zone, so they are not structural.
    "big_hand_matters": (
        {
            "name": "Reliquary Tower",
            "type_line": "Land",
            "oracle_text": "You have no maximum hand size.\n{T}: Add {C}.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="no_max_handsize",
                        scope="you",
                        raw="You have no maximum hand size.",
                    ),
                ),
            )
        ),
    ),
    # ADR-0027 — cheat_from_top: a COMMANDER that REVEALS the top card and cheats the
    # SAME card onto the battlefield (Hans Eriksson). MIRROR-ONLY migration — the v24
    # from:top zone projection is too coarse to carry this lane's narrow scope (a
    # structural arm over-fires +156, merging the cheat_into_play / topdeck_selection
    # lanes), so the include_membership-gated byte-identical _CHEAT_FROM_TOP_MIRROR (the
    # exact deleted _CHEAT_TOP_REVEAL_RE + _CHEAT_TOP_ONTO_RE over kept_oracle) serves
    # it. The IR's structure is irrelevant — the mirror reads oracle_text — but the
    # paired IR is Hans's REAL reveal/put-onto-battlefield triggered ability (faithful,
    # not fabricated). scope 'you', LOW conf. CR 401 / 701.20a.
    "cheat_from_top": (
        {
            "name": "Hans Eriksson",
            "type_line": "Legendary Creature — Human Scout",
            "oracle_text": (
                "Whenever Hans Eriksson attacks, reveal the top card of your "
                "library. If it's a creature card, put it onto the battlefield "
                "tapped and attacking defending player or a planeswalker they "
                "control. Otherwise, put that card into your hand. When you put a "
                "creature card onto the battlefield this way, it fights Hans "
                "Eriksson."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="reveal",
                        scope="any",
                        zones=("from:top",),
                        raw="reveal the top card of your library",
                    ),
                    Effect(
                        category="reveal",
                        scope="any",
                        zones=("to:battlefield",),
                        raw="put it onto the battlefield",
                    ),
                ),
            )
        ),
    ),
    # arcane_matters ← the byte-identical `\barcane\b` kept WORD MIRROR in
    # _IR_KEPT_DETECTORS for the Kamigawa Arcane / Splice-onto-Arcane / Spiritcraft
    # archetype (CR 205.3k spell type, CR 702.47 Splice). phase v0.1.19 doesn't structure
    # Arcane (a SPELL TYPE on Instants/Sorceries, not a creature subtype or keyword; the
    # "Spirit or Arcane spell" trigger drops the Arcane qualifier), so there's no
    # structural arm — the mirror reads the reminder-stripped oracle_text off the record
    # dict. Tallowisp is the canonical Spiritcraft payoff ("Whenever you cast a Spirit or
    # Arcane spell …"). A bare non-None IR routes the hybrid to the IR path; the regex
    # path no longer emits the key (the _HAND_FLOOR producer is deleted). scope "you".
    # ADR-0027.
    "arcane_matters": (
        {
            "name": "Tallowisp",
            "type_line": "Creature — Spirit",
            "oracle_text": (
                "Whenever you cast a Spirit or Arcane spell, you may search your "
                "library for an Aura card with enchant creature, reveal it, put it "
                "into your hand, then shuffle."
            ),
        },
        _ir(),
    ),
    # modified_matters ← the UNION kept WORD MIRROR (`\bmodified\b` OR "power greater
    # than its base power") in _IR_KEPT_DETECTORS for the Kamigawa Neon Dynasty
    # "modified" creature archetype (CR 700.9 — a permanent is modified if it has a
    # counter, is equipped, or is enchanted by an Aura its controller controls). phase
    # v0.1.19 doesn't structure "modified" (a DERIVED counter/Equipment/Aura union per
    # CR 700.9, not a parsed predicate/effect), so there's no structural arm — the mirror
    # reads the reminder-stripped oracle_text off the record dict. Chishiro, the
    # Shattered Blade is the canonical NEO "modified" commander ("put a +1/+1 counter on
    # each modified creature you control"). A bare non-None IR routes the hybrid to the
    # IR path; the regex path no longer emits the key (both _HAND_FLOOR producers are
    # deleted). scope "you". ADR-0027.
    "modified_matters": (
        {
            "name": "Chishiro, the Shattered Blade",
            "type_line": "Legendary Creature — Snake Samurai",
            "oracle_text": (
                "Whenever an Aura or Equipment you control enters, create a 2/2 "
                "red Spirit creature token with menace.\nAt the beginning of your "
                "end step, put a +1/+1 counter on each modified creature you "
                "control. (Equipment, Auras you control, and counters are "
                "modifications.)"
            ),
        },
        _ir(),
    ),
    # theft_matters ← the byte-identical THEFT_MATTERS_REGEX kept WORD MIRROR in
    # _IR_KEPT_DETECTORS for the STEAL-an-opponent's-cards-and-CAST-them archetype (the
    # impulse-from-opponent steal-and-cast engines, the heist Arena keyword action, the
    # name-strip three-zone rifles; CR DD9 / 613.1b). phase carries NO structural steal-
    # and-cast form, so there's no structural arm — the mirror reads the reminder-
    # stripped oracle_text off the record dict. Stolen Goods is the canonical clean
    # steal-and-cast spell ("Target opponent exiles cards from the top of their library
    # … you may cast that card"); it does NOT carry "don't own" text, so the regex
    # path's gain_control / don't-own sibling cross-open never fires it — only the
    # deleted SWEEP producer did. A bare non-None IR routes the hybrid to the IR path;
    # the regex path no longer emits the key (the SWEEP_DETECTORS row is deleted). scope
    # "opponents". ADR-0027.
    "theft_matters": (
        {
            "name": "Stolen Goods",
            "type_line": "Sorcery",
            "oracle_text": (
                "Target opponent exiles cards from the top of their library until "
                "they exile a nonland card. Until end of turn, you may cast that card "
                "without paying its mana cost."
            ),
        },
        _ir(),
    ),
    # evasion_self ← the byte-identical _IR_KEPT_DETECTORS WORD MIRROR of the deleted
    # _HAND_FLOOR producer ("This creature can't be blocked" / unblockable / landwalk /
    # the menace-family keyword words). phase v0.1.19 carries the self "can't be blocked"
    # only as a generic `restriction` Effect (shared with stax/"can't block"/tax — too
    # broad to key the lane off), so there's no clean structural arm — the mirror reads
    # the reminder-stripped oracle_text off the record dict. Slither Blade is the
    # canonical unconditional self-unblockable creature ("This creature can't be
    # blocked."). A bare non-None IR routes the hybrid to the IR path; the regex path no
    # longer emits the key (the _HAND_FLOOR producer is deleted). scope "you". ADR-0027.
    "evasion_self": (
        {
            "name": "Slither Blade",
            "type_line": "Creature — Snake Rogue",
            "oracle_text": "This creature can't be blocked.",
        },
        _ir(),
    ),
}


def test_every_migrated_key_has_a_case():
    """No migrated key may be left unproven: the case table must cover the manifest."""
    assert set(_CASES) == set(MIGRATED_KEYS), (
        "every key in MIGRATED_KEYS needs a representative (card, ir) case here"
    )


@pytest.mark.parametrize("key", sorted(MIGRATED_KEYS))
def test_migrated_key_left_regex_and_is_ir_served(key):
    """Regex path drops the key; the hybrid (IR) path serves it."""
    card, ir = _CASES[key]
    regex_keys = {s.key for s in extract_signals(card)}
    hybrid_keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert key not in regex_keys, f"{key} still emitted by the legacy regex path"
    assert key in hybrid_keys, f"{key} not served by the hybrid IR path"


def test_creatures_matter_mass_grant_fires_via_ir():
    """A MASS keyword grant to the generic creature board (Champion of Lambholt's
    CantBeBlockedBy) → creatures_matter via the IR grant_keyword arm, not regex."""
    card = {
        "name": "Champion of Lambholt",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": (
            "Creatures with power less than this creature's power can't block "
            "creatures you control.\nWhenever another creature you control enters, "
            "put a +1/+1 counter on this creature."
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="grant_keyword",
                    scope="you",
                    subject=Filter(card_types=("Creature",), controller="you"),
                    counter_kind="unblockable",
                    raw="creatures you control can't be blocked",
                ),
            ),
        )
    )
    assert "creatures_matter" not in {s.key for s in extract_signals(card)}
    assert "creatures_matter" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_creatures_matter_does_not_fire_on_a_subtype_lord():
    """The over-fire boundary: a SUBTYPE lord ("Goblin creatures you control get
    +1/+1") is tribal (type_matters, CR 205.3), NOT the generic go-wide lane — its
    IR pump subject carries the Goblin subtype, so the generic-set gate rejects it."""
    card = {
        "name": "Goblin King",
        "type_line": "Creature — Goblin",
        "oracle_text": (
            "Other Goblin creatures you control get +1/+1 and have mountainwalk."
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="you",
                    subject=Filter(
                        card_types=("Creature",),
                        subtypes=("Goblin",),
                        controller="you",
                    ),
                    raw="Other Goblin creatures you control get +1/+1",
                ),
            ),
        )
    )
    assert "creatures_matter" not in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_matters_fires_from_a_sacrifice_effect_subject():
    """Token-subtype sacrifice PAYOFF (effect side): Wedding Security "sacrifice a
    Blood token" — a `sacrifice` Effect whose subject Filter carries the Blood
    subtype opens blood_matters via the IR, not the deleted floor regex."""
    card = {
        "name": "Wedding Security",
        "type_line": "Creature — Human Soldier",
        "oracle_text": (
            "Whenever this creature attacks, you may sacrifice a Blood token. If "
            "you do, put a +1/+1 counter on this creature and draw a card."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="attacks", scope="you"),
            effects=(
                Effect(
                    category="sacrifice",
                    scope="any",
                    subject=Filter(
                        subtypes=("Blood",),
                        controller="you",
                        predicates=("Token",),
                    ),
                    raw="you may sacrifice a Blood token",
                ),
            ),
        )
    )
    assert "blood_matters" not in {s.key for s in extract_signals(card)}
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_matters_fires_from_a_sacrificed_trigger_subject():
    """Token-subtype sacrifice PAYOFF (trigger side): Blood Hypnotist "whenever you
    sacrifice one or more Blood tokens" — a `sacrificed` Trigger whose subject Filter
    carries the Blood subtype opens blood_matters via the IR."""
    card = {
        "name": "Blood Hypnotist",
        "type_line": "Creature — Vampire Wizard",
        "oracle_text": (
            "This creature can't block.\nWhenever you sacrifice one or more Blood "
            "tokens, target creature can't block this turn. This ability triggers "
            "only once each turn."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="sacrificed",
                scope="you",
                subject=Filter(
                    subtypes=("Blood",),
                    controller="you",
                    predicates=("Token",),
                ),
            ),
            effects=(Effect(category="cant_block", scope="any", raw="can't block"),),
        )
    )
    assert "blood_matters" not in {s.key for s in extract_signals(card)}
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_matters_fires_from_a_recovered_choice_list_maker():
    """Token-subtype maker recovery (choice list): Transmutation Font "create your
    choice of a Blood token, a Clue token, or a Food token" — phase drops the choice
    subtypes onto a `choose` effect; project._narrow_token_subtype_makers recovers
    them as make_token markers, so all three lanes fire via the IR."""
    card = {
        "name": "Transmutation Font",
        "type_line": "Artifact",
        "oracle_text": (
            "{T}: Create your choice of a Blood token, a Clue token, or a Food token."
        ),
    }
    ir = _ir(
        Ability(
            kind="activated",
            cost="tap",
            effects=(
                # the recovered make_token markers the projection appends
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Blood",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Clue",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Food",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
            ),
        )
    )
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "blood_matters" in keys
    # the generalized recovery also opens clue/food (these stay floor-served lanes,
    # but the structural maker recovery is general — proves the widening generalized)
    assert "clue_matters" in keys
    assert "food_matters" in keys


def test_blood_matters_fires_from_a_recovered_granted_ability_maker():
    """Token-subtype maker recovery (granted ability): Ceremonial Knife grants the
    equipped creature a quoted "create a Blood token" ability — phase folds it into a
    `pump` carrier raw; the projection recovers the Blood make_token marker, so
    blood_matters fires via the IR."""
    card = {
        "name": "Ceremonial Knife",
        "type_line": "Artifact — Equipment",
        "oracle_text": (
            'Equipped creature gets +1/+0 and has "Whenever this creature deals '
            'combat damage, create a Blood token."\nEquip {2}'
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="any",
                    subject=Filter(
                        card_types=("Creature",), predicates=("EquippedBy",)
                    ),
                    raw='Equipped creature gets +1/+0 and has "Whenever ~ deals '
                    'combat damage, create a Blood token."',
                ),
                # the recovered make_token marker the projection appends
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Blood",), predicates=("Token",)),
                    raw='Equipped creature gets +1/+0 and has "Whenever ~ deals '
                    'combat damage, create a Blood token."',
                ),
            ),
        )
    )
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}
