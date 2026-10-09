"""The ADR-0038 Unimplemented recovery stage.

Re-decorates ``concept == "other"`` :class:`~mtg_utils._card_ir.crosswalk.
ConceptNode`\\ s whose ``.node`` is phase's ``T_effect__Unimplemented`` via the
shared clause grammar (:func:`~mtg_utils._card_ir.clause_grammar.parse_clause`,
falling back to :func:`~mtg_utils._card_ir.clause_grammar.scan_clause`, falling
back to :func:`~mtg_utils._card_ir.clause_grammar.static_token` for a STATIC
idiom phase's own static parser failed on but still parked in a role=effect
Unimplemented node — Staff of the Ages's "Static pattern matched but line
failed static parser: …" diagnostic wrapper), admitting only allowlisted
tokens (:data:`ALLOWLIST`).

Re-decoration keeps the SAME ``.node`` object, so substrate purity (object
identity of phase L1 nodes) holds by construction — this stage only ever
rewrites the overlay's own decoration fields, never the mirror node.

Substrate-wide: wired at the end of ``build_concept_tree``, so signal lanes
AND the compat projection both see recovered readings — ``concept`` for
lanes, the ``category`` override field for compat (``compat._effect_category``
short-circuits on ``cnode.category``).

See ``mtg-utils/CONTEXT.md`` for the **Recovery stage** / **Re-decoration** /
**Token allowlist** glossary entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from mtg_utils._card_ir._substrate_purity import assert_substrate_pure, l1_identity
from mtg_utils._card_ir.clause_grammar import (
    _VERB_PRESENT,
    parse_clause,
    scan_clause,
    static_token,
)
from mtg_utils._card_ir.crosswalk import (
    OTHER,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    tag_of,
    unit_zones,
)
from mtg_utils._card_ir.text_idioms import _DICE_TRIG


@dataclass(frozen=True)
class TokenRule:
    """One allowlisted grammar token -> the decoration it earns."""

    concept: str  # signal-facing ConceptNode.concept the lanes read
    category: str  # compat-facing old-IR category override
    zones: tuple[str, ...] = ()  # optional zone correction (e.g. reanimate)
    # Decorate the node with the clause's reading (:func:`read_clause`): scope,
    # subject marks, zones. Every row whose lanes test the clause does; the
    # rows that don't keep the overlay's own decoration. ``make_token`` can't:
    # a token node's ``subject`` is the token's own types, which token_maker /
    # artifacts_matter read, and the clause's other type words would pass for
    # them.
    reads_clause: bool = False
    # Where the verb's own object starts ("destroy", "damage … to", "counters
    # on"), for the marks bound to that object (``TARGET_OBJECT`` /
    # ``EACH_OBJECT``) rather than to the whole clause.
    object_verb: str = ""
    # Recover the verb even inside a replacement clause ("would … instead"): only
    # where the replacement's own effect IS the verb's effect (Words of Waste's
    # "each opponent discards a card instead", a die-roll or coin-flip modifier).
    in_replacements: bool = False


# ADR-0038 token allowlist — grows per-key with corpus measurement + pinned
# tests; empty at introduction (behavior-neutral).
ALLOWLIST: dict[str, TokenRule] = {
    # (RETIRED at the phase v0.23.0 bump, task #84: the "discover" ACTION
    # idiom row, CR 701.57 — Curator of Sun's Creation's "discover again for
    # the same value" re-trigger now parses natively as a typed ``Discover``
    # node with a ``TriggeringDiscoverValue`` mana_value_limit, and the row's
    # re-census found zero remaining Unimplemented-discover residues
    # corpus-wide.)
    # evasion-denial idiom (CR 509.1b/702.14): "can be blocked as though
    # it/they didn't have [landwalk/those abilities]" — an anti-evasion
    # static (Staff of the Ages) whose own static parser fails, leaving an
    # Unimplemented parse-failure residue (still role=effect) the typed
    # IgnoreLandwalkForBlocking static read never reaches. Matched via
    # clause_grammar.static_token (the STATIC_TOKENS table), not the
    # imperative-verb grammar.
    "evasion_denial": TokenRule(concept="evasion_denial", category="evasion_denial"),
    # end-the-turn ACTION idiom (CR 724): "(may) end the turn" — expedite
    # the rest of the turn. Obeka's player-scoped grant ("The player whose
    # turn it is may end the turn") leaves an Unimplemented effect phase
    # doesn't structure; the shared grammar's "the player whose turn it is "
    # subject peel + "end the turn" verb tag re-decorates it so the typed
    # effect_concepts("end_the_turn") read sees it directly.
    "end_the_turn": TokenRule(concept="end_the_turn", category="end_the_turn"),
    # roll-a-die ACTION idiom (CR 706): "roll a d20", "roll two d8 and choose
    # one result", "roll the planar die". A spell/cost-form die roll ("the
    # *Endeavor cycle", Six-Sided Die, Danse Macabre's sacrifice-then-roll)
    # leaves the roll itself as an Unimplemented effect phase doesn't
    # structure (the consequence that follows often DOES parse) — the
    # grammar's "roll_die" token re-decorates it so the dice_makers lane's
    # typed effect_concepts("roll_die") read (CR 706) sees it directly.
    "roll_die": TokenRule(
        concept="roll_die", category="roll_die", in_replacements=True
    ),
    # coin-flip idiom (CR 705.1/705.3): "flip a coin" (Molten Sentry's modal
    # ETB flip) / a flip-fixing static ("Two-Headed Coin — the first time
    # you flip ..., those coins come up heads and you win those flips" —
    # Edgar, King of Figaro). Matched via clause_grammar.static_token (the
    # STATIC_TOKENS table, mirroring the OLD-IR ``_COIN`` regex), not the
    # imperative-verb grammar (a flip-fixing static never itself instructs
    # a plain "flip" the way SIMPLE_VERB's other rows do). Maps to the
    # native FlipCoin/FlipCoins tags' own concept ("flip_coin") so the
    # coin_flip lane's ordinary ``effect_concepts("flip_coin")`` read
    # covers the recovered node with no special-case.
    "coin_flip": TokenRule(
        concept="flip_coin", category="coin_flip", in_replacements=True
    ),
    # opponent cast-lock idiom (CR 601.3/604.1): "each opponent can't cast
    # noncreature spells with mana value greater than ..." (Lavinia,
    # Azorius Renegade) -- maps straight to the REAL "stax_taxes" concept
    # so the ordinary stax lane's iter_concepts() read covers the
    # recovered node with no special-casing (ADR-0038: the synth_* marker
    # namespace retires; a recovered node earns its real concept name).
    "stax_cast_lock": TokenRule(concept="stax_taxes", category="restriction"),
    # fight ACTION idiom (CR 701.12): "~ fights up to one target creature"
    # (Gimli, Mournful Avenger's third-resolution rider) / a Saga modal
    # bullet ("Fight! — ~ fights up to one target creature an opponent
    # controls" — Summon: Magus Sisters). Maps to the native Fight tag's
    # own concept ("fight") so the fight_makers lane's ordinary
    # effect_concepts("fight") read covers the recovered node with no
    # special-case.
    "fight": TokenRule(concept="fight", category="fight"),
    # reveal/exile-until-a-condition dig idiom (CR 701.13/701.20a): "reveal
    # cards from the top of your library until you reveal ..." (Mass
    # Polymorph, Synthetic Destiny) / "Reveal cards from the top of your
    # library until you decide to stop" (Push Your Luck) / a
    # replacement-wrapped "instead exile cards from the top of your library
    # until ..." (Unpredictable Cyclone). Maps to the native RevealUntil /
    # ExileFromTopUntil tags' own concept ("reveal_until") so the
    # dig_until lane's ordinary structural arm covers the recovered node
    # with no special-case — the grammar's "your library"-gated match
    # already establishes the digger is YOU (the same direction the typed
    # path's ``reveal_until_player`` reads off the node's own ``player``
    # field), so the lane trusts a recovered node unconditionally (see
    # ``tree_synthesis._arm_dig_until``'s ``c.recovered_by`` branch).
    "dig_until": TokenRule(concept="reveal_until", category="dig_until"),
    # phasing ACTION idiom (CR 702.26a): "phase(s) out" / "phase(s) in" as an
    # imperative instruction (Dream Fighter, Spectral Adversary, The Phasing
    # of Zhalfir) — maps to the native PhaseOut/PhaseIn tags' own concept
    # ("phasing") so the phasing_makers lane's ordinary
    # ``tree.effect_concepts("phasing")`` read covers the recovered node
    # with no special-case.
    "phasing": TokenRule(concept="phasing", category="phasing"),
    # hand-revealed idiom (CR 402.3's disclosure family): "plays with
    # {their/its} hand revealed" (Sen Triplets, Stromgald Spy). Maps to
    # the native RevealHand static mode's own concept ("reveal_hand") so
    # the hand_disruption lane's static arm covers it — the recovered
    # node's own ``.node`` carries no target field to re-check (it is
    # still the phase Unimplemented wrapper), so the lane trusts a
    # recovered node unconditionally via ``recovered_by`` (the STATIC_
    # TOKENS regex's third-person-only gate already establishes the
    # digger is NOT you).
    "hand_revealed": TokenRule(concept="reveal_hand", category="hand_disruption"),
    # ADR-0038 deferral sweep unit 4: the IMPERATIVE "reveal(s) {their/his
    # or her/its} hand" ACTION idiom (Alhammarret, High Arbiter: "each
    # opponent reveals their hand. You choose the name of a nonland card
    # revealed this way." — a two-sentence blob phase parks whole as ONE
    # Unimplemented node, no other residue). Maps to the same
    # "reveal_hand" concept as the STATIC hand_revealed idiom above so the
    # hand_disruption lane's existing ``concept == "reveal_hand"`` arm
    # covers it with no special-case; the recovered node's ``.node``
    # carries no target field of its own to re-check, so the lane trusts
    # a recovered node unconditionally (the grammar's third-person-only
    # gate already establishes the digger is NOT you).
    "reveal_hand": TokenRule(concept="reveal_hand", category="hand_disruption"),
    # ADR-0038 W4 giants (lifeloss_makers): the life-LOSS ACTION idiom (CR
    # 119.3): "[Target player/opponent] loses N life" / "you lose life equal
    # to X" as the clause's OWN main verb — a computed-amount loss ("Target
    # opponent loses 5 life unless..." — Remorseless Punishment; "loses life
    # equal to the difference between..." — Jaws of Defeat; "loses 2 life and
    # you gain 2 life" inside a conditional — Knights of the Black Rose;
    # "loses life equal to the number of creatures attacking them" — Within
    # Range; "loses life equal to the damage already dealt" — Final
    # Punishment) or an "unless"-guarded drain (Remorseless Punishment) leaves
    # the whole clause as an Unimplemented residue phase's own amount-ref
    # grammar can't structure. Distinct from a "lost life this turn"
    # CONDITION reference (Savage Gorger, Rakdos, Lord of Riots) — that shape
    # phase parses into its OWN typed consequence node (PlaceCounter,
    # Surveil, cost-reduction, …) with a condition wrapper, never an
    # Unimplemented residue, so it never reaches this table (verified:
    # ADR-0038 W4 giants corpus check, 0 false hits). Maps to the native
    # LoseLife tag's own concept ("lose_life") so the lane's ordinary
    # ``effect_concepts("lose_life")`` read covers the recovered node with no
    # special-case.
    "lose_life": TokenRule(concept="lose_life", category="lose_life"),
    # ADR-0038 post-giants main-session batch: the token-creation ACTION
    # idiom (CR 701.7 "Create" keyword action; CR 111.2 token ownership;
    # CR 205.3g predefined artifact-token subtypes): "create a red Aura
    # enchantment token named ... attached to that creature" (Smoke
    # Spirits' Aid — the whole for-each-target clause parks as ONE
    # Unimplemented residue; phase's token grammar can't structure the
    # named-Aura-attached shape). The grammar's "create" verb row already
    # discriminates create-a-COPY (the "clone" token, ahead of this row in
    # _VERB order) so a token-copy clause never lands here — the
    # token_copy_makers boundary holds by grammar order. Maps to the
    # native Token tag's own concept ("make_token") so token_maker /
    # enchantments_matter / every make_token-reading lane's ordinary
    # effect_concepts read covers the recovered node with no special-case.
    "make_token": TokenRule(concept="make_token", category="make_token"),
    # ADR-0038 post-giants main-session batch: the discard ACTION idiom
    # (CR 701.8a): "discard a card unless <condition>" — the giants-wave
    # discard_outlet agent's ONLY remaining class (Timeline Inquiry,
    # Waterbending Lesson, Tainted Indulgence, Oblivious Bookworm,
    # Wonderscape Sage: a period-separated "Draw N cards. Then discard a
    # card unless ..." tail phase parks whole as one Unimplemented
    # residue). Corpus census at introduction: 22 residues tokenize to
    # "discard"; several are OPPONENT-directed ("each opponent discards" —
    # Bladecoil Serpent; "Target player discards" — Tainted Specter), and
    # a recovered node carries NO typed target — so every lane reading
    # recovered discard nodes MUST direction-gate on the raw (the
    # recovered-node raw-read precedent), never trust scope alone.
    # (Its lanes still read the clause; moving them onto read_clause is
    # backlog.)
    "discard": TokenRule(concept="discard", category="discard", in_replacements=True),
    # ADR-0038 post-giants main-session batch: the card-draw ACTION idiom
    # (CR 121.1): "draw cards equal to <computed amount>" / "For each
    # <thing>, draw a card" — amount-computed or per-thing draws phase's
    # own grammar can't structure (Curse of Surveillance, Arcane Endeavor,
    # Mob Verdict, Skull Raid; census: 29 residues tokenize to "draw").
    # A salvaged first attempt at this row was TRIMMED for flipping two
    # pinned boundary tests; the difference here is the seam guard below
    # (the two NON-draw senses: "the game is a draw" — Divine
    # Intervention — and "draw step" timing references — Elfhame
    # Sanctuary) plus lane-level recipient gates verified by the all-key
    # corpus diff. Recipient hazards are real (Forget / Soldevi Sentry
    # draw for the OTHER player), so lanes reading recovered draw nodes
    # must direction-gate. The seam decorates the clause's reading (a bulk
    # count is ``MANY``); the older directed-draw gate still reads the raw.
    "draw": TokenRule(concept="draw", category="draw", reads_clause=True),
    # ADR-0038 W5 tails (direct_damage): the deal-damage ACTION idiom (CR
    # 120.1/120.3): "deal[s] damage ... equal to <computed amount> ..." —
    # an amount phase's own ``Ref``/``Qty`` grammar can't structure at all
    # (a total-power sacrifice tally — Soulblast, Burn at the Stake; a
    # per-thing count — Mjölnir Storm Hammer, Molten Psyche, Fateful
    # Tempest; a modal/table row inside one triggered ability — Iron
    # Mastiff's d20 chart) leaves the WHOLE clause as an Unimplemented
    # residue (unlike the ``lose_life``/``draw`` rows above, a computed
    # ``DealDamage`` amount is common enough that phase drops the clause
    # entirely rather than parking a partial typed node — corpus census at
    # introduction: 85 residues tokenize to "damage" corpus-wide, 29
    # overlap direct_damage's residual tail). Maps to the native
    # ``DealDamage``/``DamageAll``/``DamageEachPlayer`` tags' own concept
    # ("deal_damage") so ``direct_damage``'s ordinary
    # ``effect_concepts("deal_damage")`` read reaches the recovered node —
    # but a recovered node carries NO typed ``target`` field
    # (:func:`~mtg_utils._card_ir.crosswalk.effect_reaches_player` needs
    # one), so the lanes read the recipient off the seam's decoration
    # (``ANY_TARGET`` / ``PLAYER`` / ``TARGETED`` and the type words; the
    # older direct_damage reach gate still reads the raw). The OTHER four
    # ``deal_damage`` consumers (``damage_equal_power``, the combat-trio's
    # ``creature_ping``/``symmetric_damage_each``/``aoe_ping``,
    # ``typed_enters_punish``, ``removal``) all gate on
    # ``tag_of(c.node) == "DealDamage"``/``"DamageAll"``/``"DamageEachPlayer"``
    # first, so a recovered ``Unimplemented`` node (tag never matches) is a
    # silent no-op for them — verified via the full-corpus ALL-KEY diff, 0
    # changed idents outside ``direct_damage``.
    "damage": TokenRule(
        concept="deal_damage",
        category="damage",
        reads_clause=True,
        object_verb=r"damage\b[^.]*?\bto",
    ),
    # ADR-0039 W8 grammar sprint (task #82): the counter TALLY idiom (CR
    # 122.1/701.6a): "count the number of X counters on <filter>" (Rumbling
    # Ruin's ETB, whose result feeds a following-sentence threshold phase's
    # own amount-ref grammar can't structure). Generic across counter kind
    # — maps to its own concept so no unrelated lane's ordinary
    # ``effect_concepts`` read picks it up by accident; ``plus_one_matters``
    # reads it via a dedicated ``recovered_by`` arm, kind-gated on the raw
    # (the "draw"/"discard"/"damage" recovered-node raw-read precedent — a
    # recovered node carries no typed counter-kind field to re-check).
    "count_operand": TokenRule(concept="count_operand", category="count_operand"),
    # ADR-0039 W8 grammar sprint (task #82): an activated ability's OWN
    # "costs {N} less to activate for each X counter" cost-reduction
    # sub-clause (CR 118.7/122.1): Deepwood Denizen's "This ability costs
    # {1} less to activate for each +1/+1 counter on creatures you
    # control." Generic across counter kind, same raw-read kind gate as
    # ``count_operand`` above.
    "counter_cost_reduction": TokenRule(
        concept="counter_cost_reduction", category="counter_cost_reduction"
    ),
    # ADR-0039 grammar sprint (task #82): the ellipsis REPEAT-for-another-
    # player construct (CR 608.2h): "<player> does the same" (The Wedding
    # of River Song's "Draw two cards, then you may exile a nonland card
    # … Then target opponent does the same."). Maps to the REAL "draw"
    # concept (not a dedicated marker) so ``target_player_draws``'s
    # ordinary ``effect_concepts("draw")`` walk picks it up, but with its
    # OWN ``recovered_by`` marker (never "draw") so the lane can gate it
    # separately: the token's raw carries no verb at all (just the peeled
    # subject's tail), so the direction/kind comes from the SAME-unit
    # self-tagged Draw SIBLING (the existing "you and X each draw" pairing
    # precedent), not a text re-scan.
    "ellipsis_repeat": TokenRule(concept="draw", category="draw"),
    # task #np_gyfam: graveyard recursion (CR 400.7/701.17a) inside a
    # for-each LOOP phase drops entirely (a for-each-color / for-each-vote
    # "return a card from your graveyard to your hand" repeat construct —
    # All Suns' Dawn, Rogues' Gallery, Travel Through Caradhras's
    # Mines-of-Moria branch). Own dedicated concept (not the native
    # "bounce"/"change_zone" a real ChangeZone node would carry) since a
    # recovered node has no typed origin/destination fields for
    # ``change_zone_dirs`` to read — ``_graveyard_makers``/
    # ``graveyard_return_direction`` trust a ``graveyard_return``-recovered
    # node unconditionally (the grammar's own "graveyard ... hand" gate
    # already establishes the direction), the same trust the "reveal_hand"/
    # "dig_until" rows extend their own recovered concepts. NOTE
    # (no-postponement integration): the ``graveyard_return`` grammar arm
    # (clause_grammar.py's ``_RETURN`` alt) is tried BEFORE the ``bounce``
    # arms below, so any clause naming both "graveyard" and "hand" tokenizes
    # here, not as "bounce" — the sibling row below is reached only by
    # bounce clauses that never mention "graveyard" at all (Quarry Colossus,
    # Psychic Pickpocket), so the two rows are disjoint in practice, not
    # merely in key-name.
    "graveyard_return": TokenRule(
        concept="graveyard_return", category="graveyard_return", reads_clause=True
    ),
    # np_boons task #3 (Comet, Stellar Pup): the return-to-hand/owner ACTION
    # idiom (CR 400.4/404) — "return a card ... from your graveyard to your
    # hand" as a numbered planeswalker die-outcome's OWN clause (each outcome
    # is its own Unimplemented node WITH a full description — a textbook
    # route-(i) residue, not a dropped-clause gap). Maps to the REAL
    # "change_zone" concept (not a dedicated marker) so ``graveyard_makers``'s
    # ordinary ``effect_concepts("change_zone")`` walk reaches it, but a
    # recovered node carries no typed ``origin``/``destination`` fields for
    # ``change_zone_dirs`` to read (same gap ``discard``/``draw``/``damage``
    # already document) — every consumer of this heavily-shared concept name
    # already discriminates via ``tag_of``/``change_zone_dirs`` first (both
    # silently False/None for an Unimplemented node), so a recovered node is a
    # no-op for all of them except ``graveyard_makers``, which gets its OWN
    # ``recovered_by == "bounce"`` raw-gated arm (the recovered-node raw-read
    # precedent — direction/origin decided from the raw text, never trusted
    # blind). Also the sole route by which ``wants_cloning``'s
    # ``is_clone_value_effect`` (``_CLONE_ETB_VALUE`` includes "change_zone"/
    # "bounce" by concept name) sees a bare bounce-to-hand ETB with no
    # graveyard involvement at all (Quarry Colossus's tuck-to-library,
    # Psychic Pickpocket's connive-then-bounce) — unaffected by the
    # ``graveyard_return`` row above since neither mentions "graveyard".
    "bounce": TokenRule(
        concept="change_zone",
        category="bounce",
        reads_clause=True,
        object_verb=r"return|put",
    ),
    # Phase v0.104.0 fails closed on clauses it can't fully represent (an
    # intervening-if, a granted ability's reference to its granter, a counter
    # tail …) and parks the whole effect as an ``Unimplemented`` residue named
    # for the shape. The shared grammar still names the verb (it peels the
    # "if …," prefix), so each verb earns the concept its native effect tag
    # carries, and the seam decorates the clause's reading (:func:`read_clause`)
    # for the lanes to test. A key the clause's SECOND verb carries ("…, and
    # there is an additional combat phase" after an untap) is a ledger row, not
    # a read of the first verb's node. Recovery runs only on ``Unimplemented``
    # nodes, so a phase fix retires it with no ledger row.
    # ``reanimate`` names no zone of its own: the grammar's "put/return …
    # onto the battlefield" token fires from a hand, exile or a spellbook
    # too, so ``zones`` is the clause's own (``Graveyard`` only when named).
    "reanimate": TokenRule(
        concept="change_zone", category="reanimate", reads_clause=True
    ),
    "place_counter": TokenRule(
        concept="place_counter",
        category="place_counter",
        reads_clause=True,
        object_verb=r"counters? on",
    ),
    "destroy": TokenRule(
        concept="destroy", category="destroy", reads_clause=True, object_verb="destroy"
    ),
    "exile": TokenRule(
        concept="change_zone", category="exile", reads_clause=True, object_verb="exile"
    ),
    "gain_control": TokenRule(
        concept="gain_control", category="gain_control", reads_clause=True
    ),
    "tap": TokenRule(
        concept="tap_untap", category="tap", reads_clause=True, object_verb="tap"
    ),
    "untap": TokenRule(
        concept="tap_untap", category="untap", reads_clause=True, object_verb="untap"
    ),
    "scry": TokenRule(concept="scry", category="scry", reads_clause=True),
    "spell_copy": TokenRule(
        concept="copy_spell", category="copy_spell", reads_clause=True
    ),
    "counter_move": TokenRule(
        concept="move_counters", category="counter_move", reads_clause=True
    ),
    "cast_from_zone": TokenRule(
        concept="cast_from_zone", category="cast_from_zone", reads_clause=True
    ),
    "clone": TokenRule(concept="copy_token", category="clone", reads_clause=True),
    "sacrifice": TokenRule(
        concept="sacrifice", category="sacrifice", reads_clause=True
    ),
    "mill": TokenRule(concept="mill", category="mill", reads_clause=True),
    "lose_game": TokenRule(
        concept="lose_game", category="lose_game", reads_clause=True
    ),
}


_NON_DRAW_SENSE = re.compile(r"\bgame is a draw\b|\bdraw step\b", re.IGNORECASE)
# "damage"'s grammar token also matches two NON-burn-effect senses: a
# face-up REPLACEMENT clause that merely LISTS "deals damage" among several
# conditions a face-down creature would trigger (Illusionary Mask's "...
# assigns or deals damage, is dealt damage, or becomes tapped" — CR 707.4a
# turning-face-up, no independent damage effect at all) and a granted
# TRIGGERED ability's quoted CONDITION ("escapes with '... deals combat
# damage to a player, you may ...'" — Skyway Robber's Escape rider, both
# parsers failing on the same line). Neither is a CR 120.1 direct-damage
# EFFECT; reject at the seam so no lane ever sees them (corpus census: 2 of
# 85 "damage"-token residues, both non-commander-relevant to any migrated
# key today — rejected on principle, not measured harm).
_NON_DAMAGE_SENSE = re.compile(r"\bturned face up\b|\bcombat damage\b", re.IGNORECASE)


# "place_counter"'s grammar token also matches a counter REMOVAL ("remove all
# mire counters from a land" — Cyclopean Tomb's parked dies trigger, phase
# v0.104.0): the clause names counters but places none.
_NON_PLACE_COUNTER_SENSE = re.compile(
    r"\bremoves?\b[^.]*\bcounters?\b"
    # Biomancer's Familiar: "it adapts as though it had no +1/+1 counters on it"
    # changes how adapt checks; it places nothing itself.
    r"|\bas though it had no\b",
    re.IGNORECASE,
)
# A REPLACEMENT clause ("if … would die this turn, exile it instead" — Gut,
# Fanatical Priestess; Enduring Angel's "If your life total would be reduced to 0
# or less, instead … you lose the game", parked with phase's replacement-parser
# diagnostic) only modifies an event; its verb is no imperative, so the seam
# recovers nothing from it, whatever the token.
_REPLACEMENT_SENSE = re.compile(
    r"\bwould\b[^.]*\binstead\b|^Replacement pattern matched", re.IGNORECASE
)


# ── The recovered clause's reading (ADR-0038 amended at phase v0.104.0) ────────
# A recovered node is still phase's ``Unimplemented`` residue: no typed target,
# recipient or zone. So the lanes read the same facts their typed arms read off a
# real node, the seam reads them ONCE off the clause and decorates the node:
# ``subject`` carries the clause's object and recipient marks below, ``zones``
# the zones it names, and ``scope`` the side it names ("opponents" / "each";
# otherwise the overlay's own scope is kept). Lanes test these fields; no lane
# reads a recovered clause's text.

#: The card itself as what the clause moves, casts, exiles, sacrifices or copies:
#: "return this card", "put ~ onto the battlefield", "a copy of this creature", or
#: "it"/"them" after such a verb on an ability whose "it" starts out as the card
#: (:func:`_it_names_self`). Not a mention as the doer or a possessive ("~ deals",
#: "~'s power").
SELF = "Self"
#: Counters put on the card itself ("put a +1/+1 counter on ~", "put … counters on
#: itself").
ON_SELF = "OnSelf"
#: The clause opens on its instruction ("sacrifice another creature", after an
#: "if …," condition or "you may"), so it names no other player to act.
IMPERATIVE = "Imperative"
#: The object is qualified as yours ("you control", "your graveyard", "you own").
YOURS = "Yours"
#: The object is qualified as an opponent's ("an opponent controls", "you don't
#: control", "your opponents' graveyards").
THEIRS = "Theirs"
#: A player is the recipient ("to you", "to its controller", "to each opponent").
PLAYER = "Player"
#: "any [other] target" (CR 115.4 — a creature, player, planeswalker or battle).
ANY_TARGET = "AnyTarget"
#: The clause targets ("target …").
TARGETED = "Targeted"
#: The recovered verb's own object is a target ("tap target creature", "destroy up
#: to one target artifact", "deals 2 damage to any target") — not a target the
#: clause names elsewhere ("damage to the owner of target creature").
TARGET_OBJECT = "TargetObject"
#: The recovered verb's target object is qualified as yours ("deal damage to target
#: creature you control").
YOUR_TARGET = "YourTarget"
#: "each" / "all" — a mass object, no single choice.
MASS = "Mass"
#: The recovered verb's own object is "each …" ("a +1/+1 counter on each creature
#: you control"), not a count elsewhere in the clause ("for each vote").
EACH_OBJECT = "EachObject"
#: The object is a card (in a zone), not a permanent.
CARD = "Card"
#: An amount scaled by power ("damage equal to its power").
POWER_SCALED = "PowerScaled"
#: More than one ("two or more", "X", "that many", "cards equal to").
MANY = "Many"
#: A chooser other than you ("of defending player's choice").
OTHER_CHOOSER = "OtherChooser"

#: Every mark :func:`read_clause` can put in ``subject`` (beside the type words and
#: the free-form "<kind> counter" marks).
CLAUSE_MARKS: tuple[str, ...] = (
    SELF,
    ON_SELF,
    IMPERATIVE,
    YOURS,
    THEIRS,
    PLAYER,
    ANY_TARGET,
    TARGETED,
    TARGET_OBJECT,
    YOUR_TARGET,
    MASS,
    EACH_OBJECT,
    CARD,
    POWER_SCALED,
    MANY,
    OTHER_CHOOSER,
)

_TYPE_WORDS: dict[str, str] = {
    w.lower(): w
    for w in (
        "Creature",
        "Artifact",
        "Enchantment",
        "Land",
        "Planeswalker",
        "Permanent",
        "Battle",
        "Instant",
        "Sorcery",
        "Aura",
        "Equipment",
        "Treasure",
        "Food",
        "Clue",
        "Blood",
        "Powerstone",
        "Mount",
        "Vehicle",
    )
}
_TYPE_RX = re.compile(
    r"(?<!non)(?<!non-)\b(" + "|".join(_TYPE_WORDS) + r")s?\b", re.IGNORECASE
)
# The verbs and prepositions that take the card as their object.
_SELF_WORDS = (
    r"(?:~(?![\w'])|this (?:card|creature|permanent|artifact|enchantment)\b(?!')"
    r"|itself\b)"
)
_SELF_NAMED_RX = re.compile(
    r"\b(?:return|put|cast|exile|sacrifice|copy of)\s+" + _SELF_WORDS, re.IGNORECASE
)
_ON_SELF_RX = re.compile(r"\bput\b[^.]*?\bcounters? on\s+" + _SELF_WORDS, re.IGNORECASE)
# "it" after a verb ("return it", "a copy of it"), never "on it": a counter "on
# it" refers back to whatever the clause just named.
_BACKREF_RX = re.compile(
    r"\b(?:return|put|cast|exile|sacrifice|copy of)\s+(?:it|them)\b", re.IGNORECASE
)
_IMPERATIVE_PEEL = re.compile(r"^(?:if [^,]*, )?(?:you may )?", re.IGNORECASE)
_YOURS_RX = re.compile(
    r"\byou control\b|\byour (?:graveyard|hand|library)\b|\byou own\b", re.IGNORECASE
)
_THEIRS_RX = re.compile(
    r"\b(?:an|each|target) opponent controls\b|\byou don't control\b"
    r"|\bopponents?'s? (?:graveyards?|hands?|librar(?:y|ies))\b",
    re.IGNORECASE,
)
_PLAYER_RECIPIENT_RX = re.compile(
    r"\bto (?:you|its controller|that creature's controller|defending player"
    r"|each (?:opponent|player)|that player|target (?:player|opponent))\b",
    re.IGNORECASE,
)
_COUNTER_KIND_RX = re.compile(r"(\+1/\+1|-1/-1|[a-z]+) counters?\b", re.IGNORECASE)
_POWER_RX = re.compile(
    r"\bequal to (?:its|his|her|that creature's|~'s|the) power\b", re.IGNORECASE
)
_MANY_RX = re.compile(
    r"\b(?:two|three|four|five|six|seven|x) (?:or more )?cards\b|\bthat many\b"
    r"|\bcards equal to\b",
    re.IGNORECASE,
)
_OPPONENT_SIDE_RX = re.compile(
    r"\b(?:each|an|target) opponent\b(?! controls)|\bdefending player\b(?!'s choice)"
    r"|\bopponent gains control\b",
    re.IGNORECASE,
)
_OTHER_CHOOSER_RX = re.compile(
    r"\bof (?:defending player|an opponent|target opponent|that player)'s choice\b",
    re.IGNORECASE,
)
_EACH_PLAYER_RX = re.compile(r"\beach player\b", re.IGNORECASE)
_ZONE_RX = {
    "Graveyard": re.compile(r"\bgraveyards?\b", re.IGNORECASE),
    "Hand": re.compile(r"\bhands?\b", re.IGNORECASE),
    "Library": re.compile(r"\blibrar(?:y|ies)\b", re.IGNORECASE),
    # The exile zone itself, not a linked pile ("cards exiled with ~", CR 607.2a).
    "Exile": re.compile(r"\b(?:in|from|into) exile\b", re.IGNORECASE),
}


def _it_names_self(unit: AbilityUnit) -> bool:
    """Whether "it" in the unit's clause starts out as the card: a trigger or
    replacement watching the card itself, a step trigger watching nothing (Pyre
    Zombie's upkeep), or a unit working from the card's graveyard. Not an
    activated ability, whose clause names its own object first ("search the other
    pile for a card, put it into your hand" — Phyrexian Portal)."""
    if "Graveyard" in unit_zones(unit):
        return True
    if unit.origin not in ("trigger", "replacement"):
        return False
    watched = tag_of(getattr(unit.node, "valid_card", None)) or tag_of(
        getattr(unit.node, "valid_source", None)
    )
    return watched == "SelfRef" or (watched is None and unit.trigger_event == "phase")


def read_clause(
    raw: str, unit: AbilityUnit | None = None, object_verb: str = ""
) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """``(scope, subject, zones)`` the seam decorates a recovered node with (see
    the marks above); ``scope`` is ``None`` when the clause names no side.
    ``object_verb`` (:attr:`TokenRule.object_verb`) anchors the object-bound
    marks."""
    text = raw or ""
    subject: list[str] = []
    for m in _TYPE_RX.finditer(text):
        word = _TYPE_WORDS[m.group(1).lower()]
        if word not in subject:
            subject.append(word)
    if re.search(r"\bcards?\b", text, re.IGNORECASE):
        subject.append(CARD)
    if _SELF_NAMED_RX.search(text) or (
        unit is not None and _it_names_self(unit) and _BACKREF_RX.search(text)
    ):
        subject.append(SELF)
    if _ON_SELF_RX.search(text):
        subject.append(ON_SELF)
    peeled = _IMPERATIVE_PEEL.match(text)
    if _VERB_PRESENT.match(text, peeled.end() if peeled else 0):
        subject.append(IMPERATIVE)
    for mark, rx in (
        (YOURS, _YOURS_RX),
        (THEIRS, _THEIRS_RX),
        (PLAYER, _PLAYER_RECIPIENT_RX),
        (POWER_SCALED, _POWER_RX),
        (MANY, _MANY_RX),
        (OTHER_CHOOSER, _OTHER_CHOOSER_RX),
    ):
        if rx.search(text):
            subject.append(mark)
    if re.search(r"\bany (?:other )?target\b", text, re.IGNORECASE):
        subject.append(ANY_TARGET)
    if re.search(r"\btarget\b", text, re.IGNORECASE):
        subject.append(TARGETED)
    if re.search(r"\b(?:each|all)\b", text, re.IGNORECASE):
        subject.append(MASS)
    if object_verb:
        head = rf"\b(?:{object_verb})\s+"
        target = (
            head + r"(?:up to \w+ )?(?:another |other )?(?:any (?:other )?)?target\b"
        )
        if re.search(target, text, re.IGNORECASE):
            subject.append(TARGET_OBJECT)
        if re.search(target + r" (?:\w+ ){1,2}you control\b", text, re.IGNORECASE):
            subject.append(YOUR_TARGET)
        if re.search(head + r"(?:each|all)\b", text, re.IGNORECASE):
            subject.append(EACH_OBJECT)
    for m in _COUNTER_KIND_RX.finditer(text):
        kind = f"{m.group(1).lower()} counter"
        if kind not in subject:
            subject.append(kind)
    zones = tuple(z for z, rx in _ZONE_RX.items() if rx.search(text))
    scope = None
    if _OPPONENT_SIDE_RX.search(text):
        scope = "opponents"
    elif _EACH_PLAYER_RX.search(text):
        scope = "each"
    return scope, tuple(subject), zones


def _recover(
    c: ConceptNode, table: dict[str, TokenRule], unit: AbilityUnit | None = None
) -> ConceptNode | None:
    """Recover one concept-node, or ``None`` if it is not a recovery candidate
    or its grammar token is not in ``table``."""
    if c.concept != OTHER or c.recovered_by or tag_of(c.node) != "Unimplemented":
        return None
    if not c.raw:
        return None
    token = parse_clause(c.raw) or scan_clause(c.raw) or static_token(c.raw)
    if token is None or token not in table:
        return None
    # roll_die's grammar token is a broad "roll(s)" verb match that ALSO
    # matches a die-roll REFERENCE — a replacement's "would roll ...,
    # instead roll ..." modifier (Pixie Guide) or an "after/whenever you
    # roll ..." payoff timing clause (Xenosquirrels) — not an instruction
    # to roll (CR 706's dice_makers DOER). ``_DICE_TRIG`` is the OLD-IR's
    # own doer/payoff discriminator for this exact ambiguity
    # (project._narrow_mechanic_refs's "doer loop" reroutes a matching
    # cat=='roll_die' raw to dice_matters, never dice_makers); reused
    # verbatim so the crosswalk draws the identical line rather than
    # widening a reference-only card into a maker.
    if token == "roll_die" and _DICE_TRIG.search(c.raw):
        return None
    # "draw"'s grammar token also matches two NON-draw senses (the exact
    # trap that got a first attempt at this row trimmed): the game-result
    # noun ("The game is a draw" — Divine Intervention, Celestial
    # Convergence) and the turn-structure timing reference ("during their
    # draw step" — Elfhame Sanctuary, Well of Knowledge). Neither is a
    # CR 121.1 card draw; reject at the seam so no lane ever sees them.
    if token == "draw" and _NON_DRAW_SENSE.search(c.raw):
        return None
    # "damage"'s grammar token also matches a face-up-replacement LIST sense
    # and a granted-ability's quoted combat-damage CONDITION — neither is a
    # CR 120.1 direct-damage effect (see ``_NON_DAMAGE_SENSE``'s docstring).
    if token == "damage" and _NON_DAMAGE_SENSE.search(c.raw):
        return None
    if token == "place_counter" and _NON_PLACE_COUNTER_SENSE.search(c.raw):
        return None
    rule = table[token]
    if not rule.in_replacements and _REPLACEMENT_SENSE.search(c.raw):
        return None
    if not rule.reads_clause:
        return replace(
            c,
            concept=rule.concept,
            category=rule.category,
            zones=rule.zones or c.zones,
            recovered_by=token,
        )
    scope, subject, zones = read_clause(c.raw, unit, rule.object_verb)
    return replace(
        c,
        concept=rule.concept,
        category=rule.category,
        scope=scope or c.scope,
        subject=subject or c.subject,
        zones=tuple(dict.fromkeys((*rule.zones, *zones))) or c.zones,
        recovered_by=token,
    )


def apply_unimplemented_recovery(
    tree: ConceptTree, allowlist: dict[str, TokenRule] | None = None
) -> ConceptTree:
    """Re-decorate every recoverable ``other``/``Unimplemented`` node in
    ``tree`` via the shared clause grammar, admitting only ``allowlist``
    tokens (:data:`ALLOWLIST` by default).

    Scans ``unit.effects`` (role=effect) ONLY — a genuine cost/static
    ConceptNode (``unit.costs`` / ``unit.statics``) is never re-decorated;
    that migrates later, per-key. A STATIC-shaped clause CAN still be
    recovered today when phase parks it in a role=effect Unimplemented node
    (its own static parser having failed — Staff of the Ages), via
    :func:`~mtg_utils._card_ir.clause_grammar.static_token`. Returns the
    SAME ``tree`` object (identity) when nothing changed (the empty-allowlist
    fast path this commit ships behavior-neutral).
    """
    table = ALLOWLIST if allowlist is None else allowlist
    if not table:
        return tree

    before = l1_identity(tree)
    changed = False
    new_units = []
    for unit in tree.units:
        new_effects = tuple(_recover(c, table, unit) or c for c in unit.effects)
        pairs = zip(new_effects, unit.effects, strict=True)
        if any(new is not old for new, old in pairs):
            changed = True
            new_units.append(replace(unit, effects=new_effects))
        else:
            new_units.append(unit)

    if not changed:
        return tree

    out = replace(tree, units=tuple(new_units))
    assert_substrate_pure(before, out)
    return out


__all__ = [
    "ALLOWLIST",
    "ANY_TARGET",
    "CARD",
    "CLAUSE_MARKS",
    "EACH_OBJECT",
    "IMPERATIVE",
    "MANY",
    "MASS",
    "ON_SELF",
    "OTHER_CHOOSER",
    "PLAYER",
    "POWER_SCALED",
    "SELF",
    "TARGETED",
    "TARGET_OBJECT",
    "THEIRS",
    "YOURS",
    "YOUR_TARGET",
    "TokenRule",
    "apply_unimplemented_recovery",
    "read_clause",
]
