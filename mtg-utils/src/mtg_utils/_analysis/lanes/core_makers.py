"""Crosswalk signal lanes — first-wave makers: tokens, death/lifegain, pacify /
neutralize, type changers, grant payloads, direct damage, landfall (split from
crosswalk_signals.py)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis._subtypes import CREATURE_SUBTYPES
from mtg_utils._analysis.bridge_ledger import (
    keep_n_casr_reads,
    keep_n_shape_b_reads,
)
from mtg_utils._analysis.lanes._shared import (
    _GRANT_ABILITY_MOD_TAGS,
    _LAND_SUBTYPE_WORDS,
    _REMINDER_RX,
    YOU_EACH,
    _kept,
    _root_target_filter,
    _site_raw,
    _target_owner_beneficiary_scope,
)
from mtg_utils._analysis.signal_base import (
    Signal,
    _clauses,
    _resolve_subject,
)
from mtg_utils._analysis.text_reads import (
    _TOKEN_SUBJECT_WORDS,
    _detect_token_maker,
)
from mtg_utils._analysis.tree_synthesis import (
    _double_triggers_creature_dying,
    _is_creature_death_subject,
    _is_death_payoff_effect,
    _mirror_token_maker_type_subjects,
    animates_itself_as_land,
    creature_death_condition,
)
from mtg_utils._card_ir.crosswalk import (
    ATTACHED_OBJECT_PREDICATES,
    CHOSEN_PLAYER_SCOPE,
    OBJECT_FILTER_TAGS,
    OPPONENT_ACTOR_TAGS,
    SELF_REFERENCE_TARGETS,
    AbilityUnit,
    ConceptTree,
    adds_creature_type,
    answers_its_target,
    change_zone_dirs,
    controller_paid_cost_leaves,
    counter_kind,
    creature_type_change_kinds,
    effect_actor_scope,
    effect_facing_player,
    effect_owner_player_scope,
    effect_owner_rebinds_kind,
    effect_reaches_player,
    ends_the_game,
    entered_this_turn_filters,
    filter_controller,
    filter_controller_side,
    filter_core_types,
    filter_inanyzone_zones,
    filter_inzone_zones,
    filter_names_creatures,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    has_nested_damage_reaching_player,
    has_nested_extra_turn,
    hurts_triggering_player,
    is_dies_return_trigger,
    is_self_discard_cost,
    iter_granted_triggers,
    iter_mod_sites,
    iter_nested_token_effects,
    iter_nested_trigger_defs,
    iter_static_defs,
    iter_threaded_target_statics,
    iter_typed_nodes,
    iter_unit_trigger_defs,
    keyword_action_events,
    keyword_counter_placements,
    keyword_token_creations,
    mod_keyword_name,
    mod_value,
    names_attached_object,
    nested_plus_one_keyword_grant,
    own_turn_step_triggers,
    plays_lands_from_graveyard,
    recipient_tag,
    redirects_stack_object,
    ref_count_filter,
    static_mode_tag,
    steals_stack_spell,
    tag_of,
    trigger_def_event,
    trigger_phase,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
    walk_effect_chain,
    watches_itself,
)
from mtg_utils._card_ir.crosswalk.reads import (
    Choice,
    GrantedTrigger,
    choice_of,
    strips_abilities,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    TypedMirrorNode,
)
from mtg_utils._card_ir.recovery import OTHER_PLAYER


def _win_lose_game(tree: ConceptTree) -> list[Signal]:
    """Terminal alt-win / alt-loss (CR 104.2b: "An effect may state that a
    player wins the game"; CR 104.3e: "An effect may state that a player loses
    the game"). Whole-card; scope "any" (HIGH), subject "".

    The card must end the game in your favour: you win or another player
    loses (:func:`ends_the_game`, which also reads a loss granted to a
    creature, an Equipment's wielder or an emblem — Vorpal Sword, Vraska,
    Golgari Queen). A loss aimed at you is a drawback, never a win
    condition: the Pacts' unpaid upkeep, Final Fortune / Last Chance's
    extra-turn end step, Lich's Mastery leaving the battlefield. Two more
    shapes:

    * a lose / win concept the clause grammar recovered onto an untyped
      node (Hidetsugu Consumes All's "they lose the game");
    * a ``LoseTheGame`` whose player phase drops ("each player Angel of
      Destiny attacked this turn loses the game"; Nicol Bolas, Dragon-God's
      "each opponent who doesn't control …") — never a self-loss in the
      pool (each self-loss carries ``Controller``), guarded by a
      ``retirement_canary`` that fails once phase fills the player in.
    """
    if ends_the_game(tree):
        return [Signal("win_lose_game", "any", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept not in ("win_game", "lose_game"):
            continue
        tag = tag_of(c.node)
        if tag not in ("WinTheGame", "LoseTheGame") or (
            tag == "LoseTheGame" and getattr(c.node, "target", MISSING) is MISSING
        ):
            return [Signal("win_lose_game", "any", "", c.raw, tree.name, "high")]
    return []


# Owner actors naming someone other than the controller alone.
_OTHER_ACTORS = frozenset({*OPPONENT_ACTOR_TAGS, CHOSEN_PLAYER_SCOPE})


def _discard_makers(tree: ConceptTree) -> list[Signal]:
    """Loot / rummage / connive OUTLET — a draw + discard in the SAME ability unit.

    Granularity (a), per-ability sibling co-occurrence. Mirrors the deleted legacy IR
    engine's line ~7535: an ability carrying BOTH a ``draw`` effect AND a ``discard``
    effect
    scoped you/each is a self-loot outlet. The per-unit gate (``effect_concepts``
    reads role=effect only, scoped to one unit) is load-bearing: Psychic Frog and
    Nezahal carry a combat-damage draw *trigger* and a separate ``Discard a card:``
    *cost* in DIFFERENT units, so they are no loot (their discard cost fires the
    cost arm below instead).

    A RANDOM discard counts here (Burning Inquiry, Goblin Lore; Dan, 2026-10-10),
    unlike ``discard_outlet``, which skips it: this key makes discard EVENTS, and a
    "whenever you discard" payoff (Drake Haven) fires whichever card goes, where
    an outlet must put the card you choose into your graveyard (CR 701.9b).

    Two more shapes make discards without a draw + discard pair of effects:

    * a discard COST you pay (:func:`controller_paid_cost_leaves` +
      :func:`is_self_discard_cost`, the cost walk ``self_graveyard_fills``
      reads): Fauna Shaman's "Discard a creature card:", Lion's Eye Diamond's
      "Discard your hand", Tormenting Voice's additional cost, and a random
      one (Amok's "Discard a card at random:"; CR 701.9b). Each payment is a
      discard. A ``self_ref`` "Discard this card" (cycling, CR 702.29a) is the
      cycling lanes' read, not this one. A tax ("sacrifice it unless you
      discard a card": echo, CR 702.30a; Masticore; Hidden Horror) is not a
      discard a deck is built on (Dan's upkeep-payment verdict), so it is
      skipped.
    * connive (CR 701.50a: the conniving permanent's controller draws a card,
      then discards a card), which phase types as its own ``Connive`` node:
      read deep, so a granted connive counts (Security Bypass, Copycrook), off
      :func:`~mtg_utils._card_ir.crosswalk.keyword_action_events`; the
      reference-arm ``connive`` concept (Unstable Experiment) too.
    """
    for unit in tree.units:
        if not unit.has_effect("draw"):
            continue
        # The discard must be yours: "each opponent discards a card … you draw"
        # (Bad Deal) is the opponents' — its clause's actor — and a villainous
        # choice's "that opponent discards" (Dr. Eggman, Sycorax Commander) the
        # facing player's.
        disc = next(
            (
                c
                for c in unit.effect_concepts("discard")
                if c.scope in YOU_EACH
                and effect_owner_player_scope(unit.node, c.node) not in _OTHER_ACTORS
                and effect_facing_player(unit.node, c.node) is None
            ),
            None,
        )
        if disc is not None:
            return [Signal("discard_makers", "you", "", disc.raw, tree.name, "high")]
    for unit in tree.units:
        if any(
            how != "tax" and is_self_discard_cost(leaf)
            for leaf, how in controller_paid_cost_leaves(unit)
        ):
            return [Signal("discard_makers", "you", "", "", tree.name, "high")]
    if tree.has_effect("connive") or any(
        e.tag == "Connive" and e.yours for e in keyword_action_events(tree)
    ):
        return [Signal("discard_makers", "you", "", "", tree.name, "high")]
    return []


def _spell_copy_makers(tree: ConceptTree) -> list[Signal]:
    """A spell-copier (Twincast / Fork — "copy target spell"). Whole-card (HIGH).

    Mirrors the deleted ``_signals_ir``'s line ~8684: a ``copy_spell`` effect →
    spell_copy_makers
    you. Distinct from clone (creatures-on-battlefield) and token-copy.
    """
    hits = tree.effect_concepts("copy_spell")
    if hits:
        return [Signal("spell_copy_makers", "you", "", hits[0].raw, tree.name, "high")]
    return []


# The symmetric "each player creates" idiom (CR 111.2) — a widening on the
# byte-identical kept mirror, see ``_token_maker``'s docstring. Deliberately
# "each player" only, never "each opponent"/"its controller" (a DIRECTED
# gift the token-maker lane must not claim as a "you" build-around).
_EACH_PLAYER_TOKEN_MAKER_RE = re.compile(
    r"\beach player\b[^.]*?\bcreates?\b[^.]*?\bcreature tokens?\b", re.IGNORECASE
)


def _token_maker(tree: ConceptTree) -> list[Signal]:
    """A creature-token MAKER — subject-bearing (the token's kindred subtype).

    Mirrors the deleted ``_signals_ir``'s line ~8072: a ``make_token`` effect scoped
    you/each
    whose token is a creature → ``token_maker`` with the vocab-resolved subtype
    subject ("" when none resolves). The owner-scope gate drops opponent-gift
    tokens (Hunted Dragon). Reads the token's ``types`` from the typed node —
    EXCEPT the two raw-text fallbacks below, both already corpus-verified
    single-source with ``type_matters``'s token-profile membership
    reconciliation (ADR-0036/0037 T10-finalize2, :func:`structural_token_maker_
    type_subjects` / :func:`_mirror_token_maker_type_subjects`):

    * NESTED descent (:func:`iter_nested_token_effects`, ADR-0038 W5b): a
      make_token effect buried inside a granted static/triggered ability
      (Presence of Gond's Aura grant, "Commander creatures you own have
      '...'" — Veteran Soldier), a ``CreateEmblem`` (Kiora, the Crashing
      Wave's -5 Kraken emblem), a Saga chapter (Urza's Saga's chapter II),
      or a dice-roll/coin-flip modal branch (Swarming Goblins, Bottle of
      Suleiman) — none of which the flat per-unit walk surfaces as its own
      unit-level effect. Corpus-verified no false hit off a token-COPY
      clause (CR 707: ``CopyTokenOf``/``Populate``/``BecomeCopy`` never
      nest a ``Token`` tag of their own, so the ``token_copy_makers``
      boundary holds).
    * EMPTY-TYPES mirror fallback: phase's ``Token`` effect carries NO
      ``types`` at all for a MODAL bullet where only one bullet's node
      survives the walk (Ghalta and Mavren's Dinosaur bullet) or a token
      whose creation rides a die-roll/investigate-adjacent shape (Circuits
      Act, Chalk Outline). An empty tuple is ambiguous on its own (it could
      be a non-creature Treasure/Clue token instead), so it is resolved
      ONLY via the literal-gated ``create ... creature token(s)`` per-clause
      mirror (never a bare "creature token" REFERENCE elsewhere on the
      card) — a card whose empty-typed maker isn't a genuine creature token
      contributes no subject and fires nothing, matching the structural
      arm's own "Creature not in types → skip" precision. CR 111.2/205.3i.

    ADR-0038 W5 tails, two further widenings — the byte-identical kept
    mirror runs UNCONDITIONALLY now (not gated behind an empty-types
    structural hit), closing the recovered-node tail with NO structural
    ``make_token`` anchor at all (a whole-clause ``Unimplemented`` residue a
    recovery row decorates with an EMPTY types tuple never sets
    ``need_mirror`` unless at least one OTHER structural node also fired —
    Helm of Kaldra, Consuming Blob, Kalitas, Bloodchief of Ghet all carry
    exactly one such node and nothing else):

    * **The byte-identical kept mirror** (ADR-0027 precedent,
      the deleted ``_signals_ir``'s line ~11840): :func:`_detect_token_maker` (kept
      pinned in ``text_reads``) re-run over every reminder-stripped
      clause, forced scope "you" — the SAME producer legacy's own ground
      truth runs, so it can only ever ADD idents legacy already has, never
      diverge from it. ``_TOKEN_MAKER_PATTERN`` requires the literal
      "create " (imperative) substring immediately followed — within ONE
      clause — by "creature token(s)", so it never matches a token-COPY
      clause ("create a token that's a copy of target creature" has no
      "creature token(s)" substring — the token_copy_makers boundary holds
      structurally, CR 707.1) or the Populate reminder ("(Create a token
      that's a copy of a creature token you control.)" — reminder text is
      stripped before the clause scan ever runs).
    * **SYMMETRIC "each player creates" widening** (CR 111.2 — you're one
      of the "each player"s, so you get a token too): a LOCAL regex, kept
      scoped to THIS lane only (never touching the shared
      ``_TOKEN_MAKER_PATTERN``/``_detect_token_maker`` — widening those
      directly was tried in the prior W5b pass and reverted: it also
      widened legacy's OWN ground truth to opponent-directed "Its
      controller creates ..." clauses, corpus-wide live_only regressing
      111 -> 136). Catches the inflected third-person "creates" a symmetric
      "Each player creates ..." (Elephant Resurgence) / "each player who
      controls the fewest creatures creates ..." (Gor Muldrak,
      Amphinologist) always uses — deliberately "each player" only, never
      "each opponent"/"its controller" (a DIRECTED gift the lane must not
      claim as a "you" build-around), and excludes an "other than target
      player" qualifier (Death by Dragons — corpus-verified the ONLY
      "each player ... other than" token-maker instance, which makes the
      excluded player possibly YOU, not symmetric).

    Also fires on a keyword action that creates a creature token
    (:func:`~mtg_utils._card_ir.crosswalk.keyword_token_creations`): amass's
    Army (CR 701.47a), endure's Spirit (701.63a) and populate's copy of a
    creature token you control (701.36a, subject ""). phase types each as its
    own effect node; the token they make is spelled only in reminder text,
    which the mirror strips. So does a token-making keyword the card grants
    (``keyword_token_creations(granted=True)``):
    afterlife's Spirit (CR 702.135a — Afterlife Insurance) and mobilize's
    Warrior (CR 702.181a — Infantry Shield).

    A token the target's controller creates ("Destroy target permanent. Its
    controller creates a 3/3 green Beast creature token." — Beast Within,
    Pongify) reads the target like the ``ParentTargetOwner`` case above, and
    when the effect answers that target
    (:func:`~mtg_utils._card_ir.crosswalk.answers_its_target`) anywhere but a
    graveyard the token is the answered player's consolation: "opponents", a
    directed gift the scope gate drops. A
    token "each opponent creates" (Slaughter Specialist) is skipped through
    :func:`~mtg_utils._card_ir.crosswalk.effect_actor_scope`.
    """
    seen: set[str] = set()
    out: list[Signal] = []

    def fire(subject: str, raw: str, scope: str = "you") -> None:
        if subject in seen:
            return
        seen.add(subject)
        out.append(
            Signal(signal_keys.TOKEN_MAKER, scope, subject, raw, tree.name, "high")
        )

    need_mirror = False
    for unit in tree.units:
        concepts = list(unit.effect_concepts("make_token"))
        concepts.extend(iter_nested_token_effects(unit.node))
        owner_scope: str | None = None
        owner_scope_checked = False
        for concept in concepts:
            scope = concept.scope
            # task #93 — Pharika, God of Affliction / Funeral Pyre's
            # "Exile target card from a graveyard. Its owner creates a
            # token." tags the Token's recipient ``ParentTargetOwner``.
            # ``_effect_scope`` has no case for that tag and falls back
            # to its own "you" default (so ``concept.scope`` already
            # reads "you" and would slip past the gate below UNCHECKED,
            # hiding the real ambiguity — the actual beneficiary is
            # whoever's card you target, not always you). Read the task
            # #91 beneficiary helper directly to get the REAL scope
            # before gating: an unconstrained root target (Pharika/
            # Funeral Pyre's bare "target [creature] card") makes the
            # recipient "any" — a genuine, choosable "you can get this
            # token" build-around (CR 601.2c: you may legally target
            # your own graveyard) — while an opponent-constrained filter
            # (no commander-legal token_maker case exists today, per
            # task #91's exhaustive 63-card ParentTargetOwner census)
            # would resolve "opponents", a directed gift correctly
            # excluded below like Hunted Dragon's ``Typed``/``Opponent``
            # maker. A SelfRef-anchored owner (no real root filter —
            # :func:`_target_owner_beneficiary_scope` returns ``None``)
            # leaves ``scope`` at its "you" default, unaffected.
            owner_override = False
            rtag = recipient_tag(concept.node)
            if rtag in ("ParentTargetOwner", "ParentTargetController"):
                if not owner_scope_checked:
                    owner_scope = _target_owner_beneficiary_scope(unit)
                    owner_scope_checked = True
                if owner_scope is not None:
                    scope = owner_scope
                    owner_override = True
                    # "Destroy target permanent. Its controller creates a 3/3
                    # Beast" (Beast Within, Pongify, Swan Song): the token is
                    # the consolation for the permanent or spell the effect
                    # answers, a directed gift. Only an exiled graveyard card
                    # (Pharika, Funeral Pyre) is a target you'd pick as your own.
                    filt = _root_target_filter(unit)
                    root = next(
                        e.node
                        for e in unit.effects
                        if getattr(e.node, "target", None) is filt
                    )
                    if answers_its_target(root) and (
                        tag_of(root) not in ("ChangeZone", "ChangeZoneAll")
                        or change_zone_dirs(root)[0] != "Graveyard"
                    ):
                        scope = "opponents"
            # "Each opponent creates ..." (Slaughter Specialist, Akroan Horse):
            # phase writes the Token's owner Controller-relative under an
            # opponent wrapper, so the concept's own scope reads "you"
            # (CR 111.2: the player who creates a token controls it).
            if effect_actor_scope(unit, concept.node) == "opponents":
                continue
            # The "any" bypass below is scoped STRICTLY to the owner-
            # override path above — an unrelated concept whose OWN
            # natural scope happens to be "any" (a ``Player``/``Target``/
            # ``ParentTarget`` recipient mapped there for a totally
            # different reason) must still fail the gate exactly like
            # before this task; only the ParentTargetOwner beneficiary
            # read is new admission territory.
            if scope not in YOU_EACH and not (owner_override and scope == "any"):
                continue
            types = concept.subject
            if not types:
                need_mirror = True
                continue
            if "Creature" not in types:
                continue
            subject = ""
            for word in reversed(types):
                resolved = _resolve_subject(word, CREATURE_SUBTYPES)
                if resolved:
                    subject = resolved
                    break
            fire(subject, concept.raw, "any" if owner_override else "you")
    for keyword, subject in keyword_token_creations(tree, granted=True):
        fire(subject, keyword)
    if need_mirror:
        for subject in sorted(_mirror_token_maker_type_subjects(tree.oracle or "")):
            fire(subject, "")

    for clause in _clauses(_kept(tree)):
        for _key, subject in _detect_token_maker(clause, CREATURE_SUBTYPES):
            fire(subject, clause)
        m = _EACH_PLAYER_TOKEN_MAKER_RE.search(clause)
        if m is None or "other than" in m.group(0).lower():
            continue
        head = re.split(r"creature tokens?", m.group(0), flags=re.IGNORECASE)[0]
        chosen = ""
        for word in reversed(_TOKEN_SUBJECT_WORDS.findall(head)):
            resolved = _resolve_subject(word, CREATURE_SUBTYPES)
            if resolved:
                chosen = resolved
                break
        fire(chosen, clause)
    return out


def _is_your_draw_step_draw(unit: AbilityUnit, trig: TypedMirrorNode) -> bool:
    """Whether a trigger definition of ``unit`` draws you extra cards at the
    beginning of YOUR draw step (Grafted Skullcap / Sylvan Library's "At the
    beginning of your draw step, draw an additional card"): a ``Phase``
    trigger at ``Draw`` that fires on your own turn
    (:func:`~mtg_utils._card_ir.crosswalk.own_turn_step_triggers`) whose
    ability has you draw — read
    off the unit's effect concepts for its own trigger (so a clause the
    grammar recovered counts: Lord Skitter's Blessing's "if you control an
    enchanted creature, … you draw an additional card"), off the typed
    ``Draw`` for a granted one (Sarkhan, the Dragonspeaker's emblem). CR
    504.1: the draw step's turn-based draw is the active player's, so these
    add to it. "Each player's draw step" (Howling Mine) is the symmetric
    ``card_draw_engine`` read."""
    if trigger_phase(trig) != "Draw" or "Draw" not in own_turn_step_triggers(unit):
        return False
    if trig is unit.node:
        return any(c.concept == "draw" and c.scope == "you" for c in unit.effects)
    return any(
        tag_of(n) == "Draw" and recipient_tag(n) in ("Controller", None)
        for n in iter_typed_nodes(getattr(trig, "execute", None))
    )


def _draw_matters(tree: ConceptTree) -> list[Signal]:
    """ "Whenever you draw a card" payoff (The Locust God, Chasm Skulker) and
    your own draw-step extra draws.

    * ``draw_matters|you|`` — a ``Drawn`` trigger, the card's own or one it
      grants (Diviner's Wand's equipped creature) or puts on an emblem
      (Teferi, Hero of Dominaria's): :func:`iter_unit_trigger_defs`. Its
      watched scope is not the opponent (the opponent-draw punisher —
      Bowmasters, Nekusar — is ``opponent_draw_matters``), not the enchanted
      player (Curse of Fool's Wisdom, Psychic Possession — an Aura on another
      player), and a symmetric watcher that hurts the drawer (Phyrexian
      Tyranny, Spiteful Visions — :func:`hurts_triggering_player`) is a
      punisher, not a payoff.
    * ``draw_matters|you|draw_step`` — an extra draw at the beginning of your
      draw step (:func:`_is_your_draw_step_draw`): an engine of the extra
      draws the payoffs count, the doer side of the theme.
    """
    out: list[Signal] = []
    payoff = draw_step = False
    for unit in tree.units:
        # A trigger granted to an opponent or an opponent's object is theirs:
        # its "you" is that player (Ob Nixilis Reignited's "Target opponent
        # gets an emblem with 'Whenever a player draws a card, you lose 2
        # life'").
        theirs = filter_controller_side(_root_target_filter(unit)) == "opponents"
        for trig in iter_unit_trigger_defs(unit):
            if trig is not unit.node and theirs:
                continue
            if not payoff and trigger_def_event(trig) == "drawn":
                scope = trigger_scope(trig)
                if (
                    scope != "opponents"
                    and tag_of(getattr(trig, "valid_target", None)) != "AttachedTo"
                    and not (scope != "you" and hurts_triggering_player(trig))
                ):
                    payoff = True
                    out.append(Signal("draw_matters", "you", "", "", tree.name, "high"))
            if not draw_step and _is_your_draw_step_draw(unit, trig):
                draw_step = True
                out.append(
                    Signal("draw_matters", "you", "draw_step", "", tree.name, "high")
                )
    return out


def _is_creature_animator(unit: object, scopes: tuple[str, ...] = ("you",)) -> bool:
    """A static ability that turns its Land subject into a creature (animate-land).

    Granularity (b) per-ability aggregation: the unit's ``affected`` Land subject
    and an ``AddType Creature`` (or a base-P/T set that makes it a creature) modi-
    fication are read TOGETHER off one continuous ability — the split-subject the
    old projection drops to ``None`` and spreads across effects (Natural
    Emergence). ``scopes`` mirrors the live controller tuple: ``("you",)`` for
    land_creatures_matter (a symmetric all-lands animate — Living Plane — does
    not open a your-lands build), widened to ``("you", "any")`` by the b12
    land_protection lane (live passes the same widened tuple).
    """
    statics = getattr(unit, "statics", ())
    if not statics:
        return False
    if statics[0].scope not in scopes:  # the affected-filter controller gate
        return False
    subject = statics[0].subject  # all mods share the ability's affected subject
    if "Land" not in subject or "Creature" in subject:
        return False
    for concept in statics:
        if (
            concept.concept == "add_type"
            and getattr(concept.node, "core_type", None) == "Creature"
        ):
            return True
        # A Land made into a 1/1 via base-P/T set + AddType handled above; a bare
        # set_pt with no AddType is not an animator (it stays a land).
    return False


def _has_land_and_creature(subject: tuple[str, ...]) -> bool:
    """A dual Land+Creature subject (the anthem/maker shape — Sylvan Advocate)."""
    return "Land" in subject and "Creature" in subject


def _land_creatures_matter(tree: ConceptTree) -> list[Signal]:
    """A land-creatures build — anthem over Land+Creature (subject ``""``), or a
    land-animator (subject ``animator``); a land that is or makes itself a
    creature is the page-only ``self``.

    Mirrors the deleted ``_signals_ir``'s line ~7720, plus two ADR-0038 W3 batch 4
    additions
    that close the residual mass/threaded-search animate gap. Arms read off the
    typed substrate:

    * **anthem** — a pump / grant-keyword / set-P/T modification (static) OR a
      ``make_token`` effect whose subject is a dual Land+Creature (Sylvan Advocate,
      Jyoti).
    * **animator (static)** — a static ability turning a Land subject into a
      creature (Living Plane — excluded, see below), via
      :func:`_is_creature_animator` (granularity b).
    * **animator (Animate effect / threaded target)** — a first-class ``Animate``
      effect or a ``ParentTarget``-threaded static (Badgermole, Awakener Druid).
    * **animator (mass static / threaded search-chain)** — a MASS animate static
      def (:func:`iter_static_defs`) whose ``affected`` is YOU-controlled Land, or
      a ParentTarget-threaded chain whose SAME unit also tutors/moves a Land-only
      card (Rude Awakening's Entwine mode, Life // Death's "Life" face,
      Rampaging Growth's search-then-animate).

    Two ADR-0039 W7 structural closers extend the animator reach further:

    * a mass animate static's ``affected`` controller admits ``TargetPlayer``
      alongside ``You`` — Jolrael, Empress of Beasts's "All lands target
      player controls become 3/3 creatures..." is still YOUR OWN spell
      (the recipient is chosen at activation), corpus-verified narrow (the
      sole commander-legal TargetPlayer-controller mass Land→Creature
      static); the symmetric/any-controller case (Natural Affinity, Living
      Plane — controller ``None``) stays excluded below.
    * a self-recursion ``ChangeZone`` whose face-down substitute profile
      carries the Land core type (Yedora, Grave Gardener: "return it to the
      battlefield face down... It's a Forest land.") MAKES a new land from
      a dying creature — the fuel a land-animator payoff (Living Plane,
      Life and Limb) turns into a creature army, corpus-verified singleton.

    One remaining ADR-0039 W7 ledgered bridge (bridge_ledger.py) closes a
    residual grammar-straggler: ``land_creatures_condition_reference_dropped``
    (Earth Rumble Wrestlers — a "you control a land creature" condition-
    reference the parser's Or handling drops).

    ADR-0039 task #82 (post-deletion grammar sprint) retired the other two
    W7 bridges into typed ``tree_synthesis`` sweep arms instead (the "land_
    creatures_matter grammar-sprint stragglers" section in
    ``tree_synthesis.py``). The subtype-animate arm itself then RETIRED at
    the phase v0.23.0 bump (task #84): Ambush Commander's "Forests you
    control are 1/1 green Elf creatures that are still lands" (CR
    305.6/305.7/613.1d) now parses as a real Continuous static the set_pt
    static read below sees directly, and the arm's bounding-regex re-census
    found zero remaining gap members corpus-wide. Primal Adversary / Sage
    of the Maze's deferred repeat-count / formula-X animate clauses (CR
    107.3/613.1d/613.4) still fire via ``synth_land_creatures_dynamic_
    animate`` below. Same three pins, membership unchanged.

    Deliberately EXCLUDED (adjudicated legacy over-fires / design boundary, CR
    grounded — landfall rule: every remaining ``live_only`` card corpus-verified
    into one of these classes):

    * **manland self-animate** (Faerie Conclave, Mutavault, Celestial Colonnade,
      the "Restless" cycle, ~35 corpus cards) and its Aura-granted sibling (the
      Genju cycle: Genju of the Cedars/Falls/Spires/Realm) open no theme (a
      utility land-into-creature isn't a build-around "theme" the way an
      anthem/maker is): the manland itself carries only the page-only
      ``self`` subject below, the theme's own body, and the Genju nothing; the
      REVERSE animator that makes creatures BE lands STATICALLY (Ashaya's
      "Nontoken creatures you control are Forest lands...") is the same
      non-anthem utility case, one level up (CR 305/110.1) — distinct from
      Yedora's ONE-SHOT land-MAKING recursion above, which fires.
    * a **SYMMETRIC/any-controller mass animate** (Natural Affinity, Living
      Plane — affected controller ``None``) is a versatile removal/tempo
      tool, not a self-directed build — CR 613.1d.
    * a **land TYPE/subtype change with no Creature type added** (Dryad of
      the Ilysian Grove, Celestial Dawn, Realmwright, Leyline of the
      Guildpact, Prismatic Omen, Swampbenders, Gaea's Liege's own land-type
      ability, and the large "target land becomes a basic land type" /
      "becomes an Island/Swamp/artifact" cycle — Orcish Farmer, Mystic
      Compass, Tundra Kavu, Myr Landshaper, et al. — CR 305.7: "Setting a
      land's subtype doesn't add or remove any card types") is a different
      mechanic entirely.
    * a **REMOVAL** spell whose target filter merely NAMES a land creature
      (Consuming Sinkhole, Bumi Bash) is not an anthem/animator; a
      **disjunctive copy-target filter** that lists Land and Creature as
      ALTERNATIVES, not a dual type (Relm's Sketching) is not a dual
      Land+Creature subject; an unrelated self-type TOGGLE keyed off a
      landfall trigger on a card that never itself has the Land type at all
      (Hidden Stag — an Enchantment/Creature flip-flop, not a land ever
      becoming a creature) is a legacy text-mention over-fire.
    """
    # ADR-0039 task #82 grammar sprint: the former ledgered bridges read a
    # bucket-B ``tree_synthesis`` sweep arm instead of a text-anchored
    # bridge — see the "land_creatures_matter grammar-sprint stragglers"
    # section in ``tree_synthesis.py`` for the CR citations + node-shape
    # rationale. The subtype-animate arm RETIRED at the v0.23.0 bump (task
    # #84): Ambush Commander's mass animate now parses as a real static the
    # set_pt read below sees directly, and the arm's re-census found zero
    # remaining gap members. Primal Adversary / Sage of the Maze's
    # dynamic-value animate stays bucket-B; membership unchanged.
    # The animators — an effect turning your lands into creatures — carry the
    # subject ``animator``; the payoffs (a land-creature anthem, a land-creature
    # token maker) the empty one.
    _animator = Signal(
        "land_creatures_matter", "you", "animator", "", tree.name, "high"
    )
    hits: list[Signal] = []
    for c in tree.iter_concepts():
        if c.concept == "synth_land_creatures_dynamic_animate":
            hits.append(_animator)
    for unit in tree.units:
        for concept in unit.statics:
            if concept.concept in (
                "pump",
                "grant_keyword",
                "set_pt",
            ) and _has_land_and_creature(concept.subject):
                animates = any(
                    adds_creature_type(d) for d in iter_static_defs(unit.node)
                )
                hits.append(
                    Signal(
                        "land_creatures_matter",
                        "you",
                        "animator" if animates else "",
                        concept.raw,
                        tree.name,
                        "high",
                    )
                )
        for concept in unit.effect_concepts("make_token"):
            if _has_land_and_creature(concept.subject):
                hits.append(
                    Signal(
                        "land_creatures_matter",
                        "you",
                        "",
                        concept.raw,
                        tree.name,
                        "high",
                    )
                )
        if _is_creature_animator(unit):
            hits.append(_animator)
        # recall-completion b2 (ADR-0034): align the you-scoped land ANIMATOR with the
        # land_protection breadth. _is_creature_animator (static-only, Land-core-only)
        # missed the first-class ``Animate`` EFFECT node (the earthbend family — Bumi,
        # Badgermole: "Animate {types:[Creature], target: Land you control}") and the
        # threaded one-shot animate ("target Forest becomes a 3/3 creature" — Awakener
        # Druid, Kamahl). Both turn YOUR land into a creature, the same land-creatures
        # payoff the IR fires off ``_is_land_animator``. Land-SUBTYPE targets (Forest /
        # Swamp / Cave — Elvish Branchbender, Fendeep Summoner) are admitted, a
        # structural catch the IR's Land-core-only ``_is_land_subject`` gate misses.
        # The reverse animator (creatures→lands — Ashaya) and the symmetric all-lands /
        # manland self-animate cases stay land_protection-only. CR 305 / 110.1.
        for c in unit.iter_concepts():
            if c.role != "effect" or tag_of(c.node) != "Animate":
                continue
            tgt = getattr(c.node, "target", None)
            landish = "Land" in filter_core_types(tgt) or (
                {t.lower() for t in filter_subtypes(tgt)} & _LAND_SUBTYPE_WORDS
            )
            if (
                landish
                and "Creature" in (getattr(c.node, "types", None) or ())
                and filter_controller(tgt) in ("You", None)
            ):
                hits.append(
                    Signal(
                        "land_creatures_matter",
                        "you",
                        "animator",
                        c.raw,
                        tree.name,
                        "high",
                    )
                )
        for resolved, sdef in iter_threaded_target_statics(unit.node):
            landish = "Land" in filter_core_types(resolved) or (
                {t.lower() for t in filter_subtypes(resolved)} & _LAND_SUBTYPE_WORDS
            )
            if not landish:
                continue
            for _sd, mod in iter_mod_sites(sdef):
                if (
                    tag_of(mod) == "AddType"
                    and getattr(mod, "core_type", None) == "Creature"
                ):
                    hits.append(_animator)
        # ADR-0038 W3 batch 4 (lands-and-ramp cluster): a MASS animate static def
        # (:func:`iter_static_defs` — reachable via a nested ``GenericEffect``
        # anywhere in the unit, not just the threaded-ParentTarget shape above)
        # whose ``affected`` filter is YOU-controlled Land/land-subtype and whose
        # modifications add Creature (Rude Awakening's Entwine mode, Life //
        # Death's "Life" face). Controller MUST be "You" STRICTLY (not None) —
        # a symmetric/any-controller mass animate (Natural Affinity, Living
        # Plane) is the land_protection-only case the comment above already
        # scopes out; admitting None here would re-conflate them (corpus-
        # verified: Natural Affinity's ``affected`` controller is None, so it
        # correctly stays excluded). CR 305 / 110.1.
        for sdef in iter_static_defs(unit.node):
            mods = getattr(sdef, "modifications", None)
            if not any(
                tag_of(m) == "AddType" and getattr(m, "core_type", None) == "Creature"
                for m in (mods or [])
            ):
                continue
            aff = getattr(sdef, "affected", None)
            if tag_of(aff) == "ParentTarget":
                # ADR-0038 W3 batch 4: a threaded search-then-animate chain
                # iter_threaded_target_statics doesn't trace (the "real"
                # target lives on a SearchLibrary/tutor's own filter, not a
                # `.target` field — Rampaging Growth's "search for a basic
                # land, put it onto the battlefield, ... that land becomes a
                # creature"). Same-unit co-occurrence of a Land-only
                # tutor/change_zone concept is the structural anchor.
                if any(
                    "Land" in c.subject
                    for c in unit.iter_concepts()
                    if c.concept in ("tutor", "change_zone")
                ):
                    hits.append(_animator)
                continue
            if tag_of(aff) not in ("Typed", "Or", "And"):
                continue
            # ADR-0039 W7: "TargetPlayer" joins "You" — a mass animate whose
            # recipient is CHOSEN by the caster at activation (Jolrael,
            # Empress of Beasts: "All lands target player controls become
            # 3/3 creatures...") is still your OWN spell/ability, not a
            # symmetric/any-controller effect — CORPUS-VERIFIED narrow (the
            # sole commander-legal TargetPlayer-controller AddType-Creature
            # mass static): the "any"/symmetric case (Natural Affinity,
            # Living Plane — affected controller None) stays excluded below.
            if filter_controller(aff) not in ("You", "TargetPlayer"):
                continue
            landish = "Land" in filter_core_types(aff) or (
                {t.lower() for t in filter_subtypes(aff)} & _LAND_SUBTYPE_WORDS
            )
            if landish:
                hits.append(_animator)
        # ADR-0039 W7: a self-recursion whose face-down substitute profile
        # carries the Land core type + a land subtype (Yedora, Grave
        # Gardener: "return it to the battlefield face down... It's a
        # Forest land.") MAKES a new land from a dying creature — the fuel
        # a land-animator payoff (Living Plane, Life and Limb) turns into a
        # creature army, the same build-around care a Land+Creature
        # token-maker anthem already fires for. Corpus-verified singleton
        # (the sole commander-legal ChangeZone face_down_profile carrying
        # Land in extra_core_types). CR 707.9/305.
        for c in unit.iter_concepts():
            if c.role != "effect" or tag_of(c.node) != "ChangeZone":
                continue
            prof = getattr(c.node, "face_down_profile", None)
            extra = getattr(prof, "extra_core_types", None) if prof else None
            if extra and extra is not MISSING and "Land" in extra:
                hits.append(
                    Signal("land_creatures_matter", "you", "", c.raw, tree.name, "high")
                )
    # A land that is or makes itself a creature (Dryad Arbor; a manland —
    # Mutavault, Inkmoth Nexus; CR 613.1d): the theme's own body, subject
    # ``self`` — a page member that opens no avenue (the manland exclusion
    # above), read off phase's self-animation or, where phase drops the
    # ability, the manland synth arm.
    if not hits and (
        tree.is_type("Land")
        and (
            tree.is_type("Creature")
            or animates_itself_as_land(tree)
            or any(c.concept == "synth_manland" for c in tree.iter_concepts())
        )
    ):
        hits.append(
            Signal("land_creatures_matter", "you", "self", "", tree.name, "high")
        )
    # One signal per subject: a card both pays off and animates (Embodiment of
    # Insight's vigilance anthem and its landfall animation).
    return list({sig.subject: sig for sig in hits}.values())


# ── Batch 2 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────


# ``_is_creature_death_subject`` (CR 700.4 — only creatures die) is SHARED with the
# ``tree_synthesis`` gap gate (``_has_structural_death``) so the lane and the synth
# stage agree on which dies-triggers phase structuralizes; it lives there (one
# source, no drift) and is imported above. A dies-trigger whose subject is NOT a
# recognized creature (Tentacle — token-only, absent from the card-face vocab) is
# rejected by both, so it is not falsely "covered" and reaches the SUBTYPE synth arm.


def _grantee_is_your_creature(granted: GrantedTrigger) -> bool:
    """Whether a granted trigger goes to a creature you control other than the
    card itself. A granted trigger's source is the creature whose ability
    triggered (CR 113.7), and its controller is that creature's controller (CR
    603.3a), so a death payoff granted to an opponent's creature pays that
    opponent, and one granted to every creature pays each controller alike. Read
    as yours: a population or a target you control; a chosen target naming no
    controller (the caster aims a death payoff at their own creature, the read's
    own decision — Clavileño's "target attacking Vampire" also can't be another
    player's, CR 508.1a); the enchanted or equipped creature; a soulbond pair
    (CR 702.95a: both creatures you control). Not the card itself (``SelfRef`` —
    a self-grant is :func:`_self_death_payoff`'s; a token's own ability), a token
    just made (``LastCreated``), or a back-reference left unresolved."""
    grantee = granted.grantee
    tag = grantee if isinstance(grantee, str) else tag_of(grantee)
    if tag == "SourceOrPaired":
        return True
    if tag not in OBJECT_FILTER_TAGS:
        return False
    if names_attached_object(grantee):
        return True
    side = filter_controller_side(grantee)
    if side != "you" and not (granted.chosen and side is None):
        return False
    return filter_names_creatures(grantee)


def _grants_death_payoff(granted: GrantedTrigger) -> bool:
    """Whether a unit grants "When this creature dies, <payoff>" to creatures you
    control (:func:`_grantee_is_your_creature`), making the granter a death
    payoff for each of them (CR 700.4, 113.1a). The payoff is
    :func:`_is_death_payoff_effect`'s value; a grant that returns the dying
    creature (to the battlefield, :func:`is_dies_return_trigger` — Feign Death;
    or to its owner's hand — Kaya the Inexorable's ghostform, Verdant Rebirth)
    is resilience, not a payoff, whatever it adds beside."""
    trig = granted.trigger
    if (
        trigger_def_event(trig) != "dies"
        or getattr(trig, "origin", None) != "Battlefield"
        or not watches_itself(trig)
        or not _grantee_is_your_creature(granted)
        or is_dies_return_trigger(trig)
    ):
        return False
    execute = getattr(trig, "execute", None)
    if not isinstance(execute, TypedMirrorNode):
        return False
    effects = tuple(walk_effect_chain(execute))
    if any(
        tag_of(c.node) == "Bounce"
        and tag_of(getattr(c.node, "target", None)) in SELF_REFERENCE_TARGETS
        for c in effects
    ):
        return False
    return any(_is_death_payoff_effect(c) for c in effects)


# The aristocrats death-payoff effect kinds (CR 700.4): the equipment/aura
# AttachedTo dies-trigger arm fires ONLY when the trigger's effect EXTRACTS VALUE
# from the equipped/enchanted creature's death — draw (Skullclamp, Bequeathal),
# drain (Lead Pipe, Death Watch), damage (Creature Bond), a token (Elephant Guide),
# a counter (Malefic Scythe), mill/surveil/discard card advantage, or DEPLOY a
# creature onto the battlefield from hand/graveyard (Deathrender — "put a creature
# card from your hand onto the battlefield", the change_zone arm below). It does NOT
# fire when the effect only RETURNS / REATTACHES / exiles the SOURCE (the ~40
# resilience auras — Gift of Immortality, the Zendikons, Resurrection Orb,
# Oathkeeper, Forebear's Blade), which are a resilience lane, not aristocrats.
# rules-lawyer-grounded (CR 700.4 + the aristocrats-payoff boundary).
# Retired 2026-10-25: ``DEATH_MATTERS_REGEX``, the mined sweep pattern ("whenever …
# creatures die", "creatures that died this turn") this lane's Card IR read replaced
# (ADR-0027).
def _death_matters(tree: ConceptTree) -> list[Signal]:
    """Aristocrats payoff — cares about OTHER creatures dying (CR 700.4). Tier-1.

    Six structural arms, zero oracle text / regex at lane time (ADR-0036 fold —
    the ``_DEATH_MATTERS_MIRROR`` is deleted):

    * a battlefield ``dies`` trigger watching a real CREATURE object (Blood Artist /
      Zulaport / Midnight Reaper — the ``Or[SelfRef, Typed Creature]`` surfaces
      ``Creature`` past the self arm). A bare ``SelfRef`` self-death carries no
      subject → ``self_death_payoff``, excluded. Scope = the watched object's
      controller (Blood Artist → "any", Grave Pact → "you", Massacre Wurm →
      "opponents").
    * an equipment/aura ``AttachedTo`` dies-trigger whose effect is an aristocrats
      PAYOFF (:func:`_is_death_payoff_effect`) — Skullclamp / Bequeathal / Elephant
      Guide, or a deploy-a-creature-from-hand (Deathrender). Resilience auras
      (return/reattach the SOURCE) are shed.
    * a morbid creature-death CONDITION (:func:`creature_death_condition`) — the "if
      a creature died this turn" state family (Bone Picker, Mahadi, the Zubera
      count payoffs).
    * a ``CreatureDying`` trigger-DOUBLER (Teysa Karlov, Drivnod — CR 603.2).
    * a "When this creature dies, <payoff>" the card GRANTS to other creatures you
      control (:func:`_grants_death_payoff` — Clavileño's attacking Vampire,
      Showstopper's team, Infernal Scarring's enchanted creature): each of their
      deaths pays its controller. Scope "you".
    * the ``tree_synthesis`` bucket-B synth node (the morbid / combat-damage-dies /
      description-only other-creature death tail phase emits no typed node for).
    """
    out: list[Signal] = []
    for unit in tree.units:
        if any(_grants_death_payoff(g) for g in iter_granted_triggers(unit)):
            out.append(Signal("death_matters", "you", "", "", tree.name, "high"))
        if unit.trigger_event != "dies":
            continue
        # CR 700.4: "dies" is put into a graveyard FROM THE BATTLEFIELD. A
        # "put into a graveyard from anywhere" trigger (origin unset — Planar Void,
        # Countryside Crusher) is a graveyard-arrival payoff, not a death payoff.
        if getattr(unit.node, "origin", None) != "Battlefield":
            continue
        subj = trigger_subject(unit.node)
        # CR 700.4: only CREATURES die. A non-creature GY-arrival watcher (Scrapheap
        # — artifact/enchantment) is not a death payoff even though phase emits the
        # same battlefield→graveyard shape; the SelfRef self-death has no subject.
        if subj and _is_creature_death_subject(subj):
            out.append(
                Signal(
                    "death_matters",
                    trigger_subject_scope(unit.node),
                    "",
                    "",
                    tree.name,
                    "high",
                )
            )
            continue
        # equipment / aura "whenever equipped/enchanted creature dies" — the watched
        # object is the AttachedTo host (``trigger_subject`` empty). An aristocrats
        # payoff ONLY when the effect extracts value, not resilience (CR 700.4).
        vc = getattr(unit.node, "valid_card", None)
        if (
            vc is not None
            and tag_of(vc) == "AttachedTo"
            and any(_is_death_payoff_effect(e) for e in unit.effects)
        ):
            out.append(Signal("death_matters", "any", "", "", tree.name, "high"))
    # morbid creature-death condition ("if a creature died this turn") + the
    # ``CreatureDying`` trigger-doubler. scope "any"; the extractor dedups.
    if creature_death_condition(tree) or _double_triggers_creature_dying(tree):
        out.append(Signal("death_matters", "any", "", "", tree.name, "high"))
    # bucket-B tail (ADR-0037): the tree_synthesis stage's synthesized death node.
    for c in tree.iter_concepts():
        if c.concept == "synth_death_matters":
            out.append(Signal("death_matters", "any", "", "", tree.name, "high"))
    return out


def _extra_turns(tree: ConceptTree) -> list[Signal]:
    """An extra-turn grant (Time Warp, Nexus of Fate — CR 500.7). Whole-card, "you".

    Mirrors the ``extra_turn`` doer (``_DOER_EFFECT_KEYS`` → ("extra_turns","you")):
    any ``ExtraTurn`` effect, regardless of who takes it ("that player takes an
    extra turn" is still a build-around). The 5-card raw-fold tail phase buries in a
    sibling category is a known ``live_only`` residue (no ``_EXTRA_TURN_RAW`` here).

    task #85 (phase v0.23.0): a flat top-level ``ExtraTurn`` OR
    :func:`has_nested_extra_turn` reaching one buried inside a GRANTED
    construct the narrow ``_EFFECT_CHILD_FIELDS`` walk never surfaces —
    a ``Vote``'s ``per_choice_effect`` branch (Expropriate, Plea for
    Power), a ``FlipCoin``/``FlipCoins`` ``win_effect`` (Stitch in Time,
    Ral Zarek's -7), or a static ability's ``GrantAbility.definition``
    (Ichormoon Gauntlet's granted planeswalker loyalty ability).
    """
    if tree.has_effect("extra_turn"):
        return [Signal("extra_turns", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        if has_nested_extra_turn(unit.node):
            return [Signal("extra_turns", "you", "", "", tree.name, "high")]
    return []


# ADR-0038 W3 batch 4 — the lifegain_makers bucket-B text-idiom bridge (last
# resort, arms 1-3 above already found nothing): a genuine "you gain N life"
# / "you gain life equal to ~" clause phase fails to structurally parse at
# ALL (no GainLife node anywhere — a bare ``Unimplemented`` "gain"/
# "static_structure" clause, or a replacement/loyalty-ability shape the
# static parser drops entirely: Drain Life's capped-lifegain formula, Soul
# Burn / Predator's Rapport / Discerning Taste / Shadowgrange Archfiend /
# War Report / Song of Inspiration's "life equal to ~" scalers, Ajani /
# Serra Paragon / Fasting / Life of Toshiro Umezawa's loyalty/Saga-chapter/
# replacement shapes, Necravolver / Rakavolver's kicker-branched granted
# trigger). Requires "you" DIRECTLY followed by "gain(s)" (never "you MAY
# HAVE an opponent gain" — Invigorate, Reverent Silence — nor "target
# opponent gains" / "that player gains" alone — Fiery Justice, Soldevi Steam
# Beast, Armistice, the Phelddagrifs — none of which put "you" immediately
# before "gain"), so the SAME opponent-benefit exclusion arm-3 applies
# structurally falls out of the wording itself, no extra scope check needed.
# Per-CLAUSE (period-delimited, boundary lesson (iii)) so an unrelated
# opponent-benefit clause elsewhere on the same card never leaks in. CR
# 119.3.
#
# A SECOND exclusion, found corpus-verifying this arm: the ubiquitous
# lifegain_MATTERS trigger condition "Whenever you gain life, <payoff>"
# (Ajani's Pridemate, Sanguine Bond, ~65 more — plus "gain OR LOSE life",
# Wax-Wane Witness/Vampire Scrivener, and "gain life FOR THE FIRST TIME
# each turn", Deathless Knight/Vanguard Seraph) is a bare "gain life" with
# NO amount between "gain" and "life" — phase parses the WheneverEvent
# condition itself perfectly structurally; it's the PAYOFF lane
# (lifegain_matters), never a lifegain SOURCE, and must not co-fire here.
# Not clause-start-anchored (a preceding keyword line with no period —
# "Flying\nWhenever you gain life, …" — or a preceding UNRELATED trigger
# joined by "and" — "When MACH-1 enters and whenever you gain life, …" —
# both keep the idiom out of clause-head position). A genuine source clause
# never puts "whenever/when you (may) gain(s) (or lose) life" immediately
# before a comma (Necravolver's "Whenever this creature deals damage, you
# gain that much life" puts an unrelated event between "whenever" and "you
# gain", so it's unaffected; "you gain 2 life." / "you gain life equal to
# ~" never have a comma right after "life").
_LIFEGAIN_TEXT_RX = re.compile(
    r"\byou (?:may )?gains?\b[^.]{0,80}\blife\b", re.IGNORECASE
)
_LIFEGAIN_MATTERS_TRIGGER_RX = re.compile(
    r"(?:whenever|when)\s+you\s+(?:may\s+)?gains?(?:\s+or\s+lose)?\s+life[^,]{0,60},",
    re.IGNORECASE,
)


def _lifegain_text_idiom(tree: ConceptTree) -> str | None:
    """The "you gain ... life" clause text, per-clause gated (CR 119.3)."""
    for clause in _kept(tree).split("."):
        if _LIFEGAIN_MATTERS_TRIGGER_RX.search(clause):
            continue
        if _LIFEGAIN_TEXT_RX.search(clause):
            return clause.strip()
    return None


def _lifegain_makers(tree: ConceptTree) -> list[Signal]:
    """A life-gain SOURCE — a ``gain_life`` effect, or a granted ``lifelink``.

    Mirrors the deleted ``_signals_ir``'s lines ~7843 / ~7862. (a) a ``GainLife`` effect
    scoped
    you/any (Gray Merchant, Kitchen Finks); (b) a static ``AddKeyword(Lifelink)``
    grant (Basilisk Collar, Talus Paladin, Vault of the Archangel — CR 702.15b), the
    grantee NOT opponent-only. The card's OWN printed lifelink keyword rides the
    keyword path (out of this typed-effect arm). Scope "you".

    ADR-0038 W3 batch 4 — a THIRD arm: a ``GainLife`` effect buried ANYWHERE
    inside a unit's tree — a GRANTED ability's own quoted definition
    (``GrantTrigger``/``GrantAbility``), reachable a level deeper still
    inside a created TOKEN's own ``static_abilities``, or a die-roll /
    coin-flip modal branch — that the flat per-unit concept-node walk never
    surfaces as its own node (the ``has_nested_roll_die`` /
    ``has_nested_flip_coin`` / ``has_nested_fight`` precedent: one
    :func:`~mtg_utils._card_ir.crosswalk.iter_typed_nodes` deep walk reaches
    every container shape uniformly, no per-container-type code). Two source
    families this recovers: a granted trigger/activated ability on an Aura/
    Equipment's OWN enchanted/equipped permanent (Farmstead, Ephara's
    Radiance, Sugar Coat, Victual Sliver — "Enchanted/Equipped X has '...
    you gain N life'"), and the SAME grant buried inside a created token's
    own ability text (the Pest-token family — Send in the Pest, Pest
    Summoning, Professor of Zoomancy). Each found node's OWN ``player``
    field is inspected (not just presence) — an explicit ``Typed`` player
    with ``controller == "Opponent"`` (Fiery Justice, Invigorate, Soldevi
    Steam Beast, Armistice) or an "Another" player property (Reverent
    Silence's "each OTHER player gains life") is a drawback/alt-cost/
    opponent-benefit GainLife, never this deck's own life-gain source, and
    is excluded — corpus-verified as the only two opponent-reaching shapes
    among 1724 GainLife nodes commander-wide. CR 119.3 / 603.6.

    task #91 — "any" when the gainer is the OWNER of an earlier-targeted
    permanent (:func:`_target_owner_beneficiary_scope`, CR 108.3): Path of
    Peace / Misfortune's Gain's "Destroy target creature. Its owner gains 4
    life." target an UNCONSTRAINED "target creature" — the gainer could be
    YOU or an opponent, never the caster unconditionally. Iterates
    ``tree.units`` (not the whole-card ``tree.effect_concepts`` this arm
    used before) so the SAME unit is available for the root-filter read;
    the iteration order is identical (:meth:`ConceptTree.effect_concepts`
    itself walks ``self.units`` in order), so membership is unchanged.
    """
    for unit in tree.units:
        for c in unit.effect_concepts("gain_life"):
            if c.scope in ("you", "any"):
                scope = "you"
                if recipient_tag(c.node) == "ParentTargetOwner":
                    override = _target_owner_beneficiary_scope(unit)
                    if override is not None:
                        scope = override
                return [Signal("lifegain_makers", scope, "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.statics:
            if (
                c.concept == "grant_keyword"
                and getattr(c.node, "keyword", None) == "Lifelink"
                and c.scope != "opponents"
            ):
                return [Signal("lifegain_makers", "you", "", c.raw, tree.name, "high")]
    for n in tree.iter_typed():
        if tag_of(n) != "GainLife":
            continue
        player = getattr(n, "player", None)
        if tag_of(player) == "Typed":
            if getattr(player, "controller", None) == "Opponent":
                continue
            props = getattr(player, "properties", None) or []
            if any(tag_of(p) == "Another" for p in props):
                continue
        return [Signal("lifegain_makers", "you", "", "", tree.name, "high")]
    idiom = _lifegain_text_idiom(tree)
    if idiom is not None:
        return [Signal("lifegain_makers", "you", "", idiom, tree.name, "high")]
    return []


def _reanimator(tree: ConceptTree) -> list[Signal]:
    """A creature that returns creatures GY→battlefield (the archetype, not a spell).

    Mirrors the deleted ``_signals_ir``'s line ~8095 (``cat=="reanimate" and
    is_creature(card)
    and _reanimates_creature``). Structural: the card is a Creature AND a
    ``ChangeZone`` effect with origin=Graveyard / destination=Battlefield whose
    moved subject is a Creature (Sheoldred, Chainer). Excludes GY→hand recursion and
    exile-return (those are different ``ChangeZone`` zone pairs). CR 700.4 / 603.6e.
    """
    if not tree.is_type("Creature"):
        return []
    for c in tree.effect_concepts("change_zone"):
        origin, dest = change_zone_dirs(c.node)
        if origin == "Graveyard" and dest == "Battlefield" and "Creature" in c.subject:
            return [Signal("reanimator", "you", "", c.raw, tree.name, "high")]
    return []


def _plus_one_makers(tree: ConceptTree) -> list[Signal]:
    """A +1/+1 counter PLACEMENT source (Forgotten Ancient, Avenger — CR 122.1).

    Mirrors the deleted ``_signals_ir``'s line ~8472: a ``place_counter`` effect whose
    ``counter_type`` is ``P1P1`` (the discriminator phase isolates from loyalty /
    oil / shield placements), plus the blank-kind enters-with/modal form whose raw
    literally names "+1/+1 counter". Counter DOUBLERS are a separate lane.

    task #85 adds the ``synth_plus_one_makers`` bucket-B fallback (see
    :func:`mtg_utils._analysis.tree_synthesis._arm_plus_one_makers`'s own
    docstring) — the ETB-replacement / dropped-computed-amount / granted-
    loyalty-ability P1P1 placement residue phase's static parser or effect
    walk doesn't reach at all. Scope "you".

    task #87 adds the GRANTED/TOKEN-BODY placement class the plus-one-
    counters Preset's own module docstring names as its last standing
    deferral (~36 cards, three families): a GRANTED keyword mechanic
    (Twins of Discord's Bloodthirst grant, Varolz/Young Deathclaws's
    Scavenge grant, Propagator Drone's Evolve grant, Elder Arthur Maxson's
    Training grant, Dack's Duplicate's Dethrone copy-exception) or a
    CREATED TOKEN'S OWN keyword profile (Dragon Broodmother's Devour
    token) placing the counter, never this card's own top-level keyword
    array or ``place_counter`` effect — see
    :func:`~mtg_utils._card_ir.crosswalk.nested_plus_one_keyword_grant`'s
    own docstring for the three shapes read and why the Mutagen-token /
    Young-Hero-Role-token cycles stay OUT (no ability body at all in
    phase's parse, a substrate gap rather than a missed read).

    ``ChooseOneOf`` branches (Fabricate, CR 702.123a — "put a +1/+1 counter
    on it or create a Servo token"; Tizerus Charger's escape choice; Me, the
    Immortal's multi-kind choice) reach the first arm through the shared effect
    walk. EXCLUDED (by design) are Quarry Hauler / Dramatist's Puppet's "for
    each kind of counter on target permanent, put ANOTHER counter of that kind"
    loop, whose branch carries phase's own ``iteration_kind_binding:
    RebindToIteratedKind`` marker (:func:`effect_owner_rebinds_kind`) — "P1P1"
    there is the loop-iteration sentinel value, not a genuine reference to
    +1/+1 counters (the card's own text never says "+1/+1" at all).

    task #94 (residual close-out) adds the GrantTrigger-nested-effect
    descent named above as the unblock path: Eternal Thirst, Agent of
    the Shadow Thieves, and Thundering Mightmare each place the same
    genuine P1P1 counter from a GRANTED TRIGGER nested in a top-level
    STATIC's ``GrantTrigger`` modification (an Aura/anthem/Soulbond
    granting "whenever X, put a +1/+1 counter on this creature" to
    something), never a ``ChooseOneOf`` branch — the analogous gap
    :func:`nested_plus_one_keyword_grant` already closed for a GRANTED
    KEYWORD (``AddKeyword``). The same ``_GRANT_ABILITY_MOD_TAGS``
    ``.trigger.execute`` descent :func:`_draw_for_each` already
    establishes (mirrors its ``Draw`` read exactly), keyed on
    ``PutCounter``/``P1P1`` instead, closes it. Full-corpus sweep of
    the shape (every ``GrantTrigger`` modification whose granted
    trigger's execute chain carries a ``PutCounter``/``P1P1`` ANYWHERE,
    not just the 3 named cards): 19 distinct commander/brawl-legal
    cards match structurally. 16 of the 19 already carried
    ``plus_one_makers`` via another existing read (mostly Sliver-
    lord/tribal-anthem statics whose OWN top-level ``place_counter``
    concept node already reaches the nested effect); only the 3 named
    cards were the genuine gap this arm closes. All affected filters
    in the swept class scope to permanents "you" control, own, or
    equip/enchant (Aura ``EnchantedBy``/Equipment ``EquippedBy``/
    tribal-anthem "creatures you control"/commander-only "you own"/
    Soulbond's own "you control both" pairing gate) — none grant the
    trigger to an opponent's permanents only, so scope stays "you"
    with no opponent-scope carve-out needed (corpus-verified, no
    counter-example). Corpus re-measure at this arm (32,521 commander-
    legal cards, same set task #93 measured): 3 gains (the 3 named
    cards), 0 losses.

    Also fires on a keyword action that places +1/+1 counters
    (:func:`~mtg_utils._card_ir.crosswalk.keyword_counter_placements`);
    tribute is excluded because the opponent chooses (CR 702.104a).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("place_counter"):
            if effect_owner_rebinds_kind(unit.node, c.node):
                continue  # the "for each kind of counter" loop placeholder
            ck = counter_kind(c.node).upper()
            if ck == "P1P1" or (not ck and "+1/+1 counter" in (c.raw or "")):
                return [Signal("plus_one_makers", "you", "", c.raw, tree.name, "high")]
    if any(kind == "P1P1" for _kw, kind in keyword_counter_placements(tree)):
        return [Signal("plus_one_makers", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_plus_one_makers":
            return [Signal("plus_one_makers", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        if nested_plus_one_keyword_grant(unit.node):
            return [Signal("plus_one_makers", "you", "", "", tree.name, "high")]
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) in _GRANT_ABILITY_MOD_TAGS:
                trig = getattr(n, "trigger", None)
                execute = getattr(trig, "execute", None) if trig is not None else None
                for m in iter_typed_nodes(execute) if execute is not None else ():
                    if tag_of(m) != "PutCounter":
                        continue
                    if counter_kind(m).upper() == "P1P1":
                        return [
                            Signal("plus_one_makers", "you", "", "", tree.name, "high")
                        ]
        # A replacement that puts the card onto the battlefield with +1/+1
        # counters (Dodecapod's "put it onto the battlefield with two +1/+1
        # counters on it instead of putting it into your graveyard"; CR 122.6:
        # counters an object is given as it enters are counters put on it). A
        # dies or blink return "with a +1/+1 counter" (undying, Long Road Home)
        # stays out, the plus-one preset's documented exclusion.
        if unit.origin == "replacement" and any(
            _enters_with_plus_one(n) for n in unit.iter_typed()
        ):
            return [Signal("plus_one_makers", "you", "", "", tree.name, "high")]
    return []


def _enters_with_plus_one(node: object) -> bool:
    """A ``ChangeZone`` onto the battlefield whose ``enter_with_counters`` names
    +1/+1 counters."""
    if tag_of(node) != "ChangeZone" or getattr(node, "destination", None) != (
        "Battlefield"
    ):
        return False
    counters = getattr(node, "enter_with_counters", None)
    return isinstance(counters, list) and any(
        isinstance(c, list) and c and c[0] == "P1P1" for c in counters
    )


# task #87 — the pacify-aura structural concept. Task #86's removal-preset
# flip correctly dropped Pacifism/Arrest from `removal` (CR 611.2 leaves the
# enchanted permanent on the battlefield — it's not removed), which
# incidentally cost the `interaction` budget role its Pacifism/Arrest credit
# (see roles.py's `_INTERACTION_PRESETS` comment). This is the DEDICATED
# structural concept that comment named as the recovery mechanism: an Aura
# whose OWN static ability restricts what it enchants from attacking/
# blocking (CR 508.1c / 509.1b — the standard restriction-effect hooks a
# static "can't attack"/"can't block" grant plugs into; CR 303.4 governs the
# Aura's own "enchant" object).
#
# Structural: a `CantAttack`/`CantBlock`/`CantAttackOrBlock` static def
# (Pacifism's separate CantAttack + CantBlock pair, Arrest/Faith's
# Fetters/Prison Term's combined CantAttackOrBlock) whose `affected` filter
# carries an `EnchantedBy` predicate — "whatever THIS card enchants", the
# same self-referential attach marker `_stax_structural_walk`'s pacify veto
# already keys on (`crosswalk.ATTACHED_OBJECT_PREDICATES`) to keep Pacifism out
# of stax_taxes/symmetric_stax. A co-occurring `CantBeActivated{EnchantedBy}`
# rider (Arrest/Prison Term's "activated abilities can't be activated") is
# NOT independently required — it rides along on cards that already have
# it, never gates the signal alone (a hypothetical Aura that ONLY locked
# activated abilities, with no attack/block restriction, would be a
# different mechanic, not this one).
#
# `EquippedBy` joined the predicate set in task #93: CR 613's layer system
# applies a can't-attack/can't-block restriction identically regardless of
# whether the granting permanent is an Aura or an Equipment (CR 301.5/303.4
# both just attach; the restriction itself is an ordinary layer-6
# ability-modifying effect either way, no rules distinction). A full
# commander-legal corpus census (32,521 cards) for an `EquippedBy`-affected
# `CantAttack`/`CantBlock`/`CantAttackOrBlock` static turns up exactly ONE
# hit, Copper Carapace ("Equipped creature gets +2/+2 and can't block.") —
# and it is the SAME Rage/Vow-cycle compensating-benefit shape the veto
# below already excludes for Auras (a positive P/T buff riding the SAME
# restriction, a combat enabler you put on your OWN creature, never a
# Pacifism-style neutralize). So widening the predicate set changes NOTHING
# in the current corpus (the veto below now also scans `EquippedBy`-
# affected statics, correctly still excluding Copper Carapace) — it is a
# rules-motivated generalization, not a card-count-driven one, kept ready
# for a future genuine Equipment-pacify printing.
#
# COMPENSATING-BENEFIT veto (corpus-measured, task #87; widened #93): a bare mode/pred
# scan over-fires on the "Rage"/"Vow" cycles (Undying Rage, Maniacal Rage,
# Cagemail, Gnarled Scarhide's bestow, Vow of Malice/Duty/Flight/Lightning/
# Torment/Wildness) — a SEPARATE top-level static in the SAME card grants a
# POSITIVE P/T buff or keyword to the SAME EnchantedBy target alongside the
# restriction. That's a combat ENABLER (a pump-with-a-drawback you put on
# YOUR OWN attacker, or a directed "can't attack you" political tool),
# never the Pacifism/Arrest neutralize-a-threat archetype — vetoed. A
# NEGATIVE P/T modification alongside the restriction (Cast into Darkness's
# -2/-0, Crippling Blight's -1/-1, Clawing Torment's -1/-1) is a DEBUFF, not
# a benefit — stays IN, it's the same "shut this creature down" archetype,
# arguably more so. Scoped to `origin == "static"` units only (the card's
# OWN top-level continuous grants, one `AbilityUnit` per phase's
# `static_abilities` list entry) — a rider ACTIVATED ability the Aura's
# controller must additionally pay for (Gelid Shackles's optional
# "{S}: Enchanted creature gains defender until end of turn", an anti-
# synergy escape hatch, not an unconditional benefit) lives in a DIFFERENT,
# "ability"-origin unit and never gates this veto.
_PACIFY_AURA_MODES = frozenset({"CantAttack", "CantBlock", "CantAttackOrBlock"})
_PACIFY_PT_MOD_TAGS = frozenset({"AddPower", "AddToughness"})
_PACIFY_ALWAYS_COMPENSATING_TAGS = frozenset({"AddKeyword", "SetPower", "SetToughness"})


def _pacify_aura_compensates(tree: ConceptTree) -> bool:
    """True if a top-level static grants a POSITIVE benefit to the SAME
    EnchantedBy/EquippedBy target a pacify restriction (also top-level)
    targets — see :func:`_pacify_makers`'s module note for the
    corpus-measured boundary (widened to Equipment in task #93; Copper
    Carapace is the sole commander-legal ``EquippedBy`` hit and is
    correctly caught by this SAME veto)."""
    for unit in tree.units:
        if unit.origin != "static":
            continue
        node = unit.node
        if not set(filter_predicates(getattr(node, "affected", None))) & (
            ATTACHED_OBJECT_PREDICATES
        ):
            continue
        for m in getattr(node, "modifications", None) or ():
            if not isinstance(m, TypedMirrorNode):
                continue
            tag = tag_of(m)
            if tag in _PACIFY_ALWAYS_COMPENSATING_TAGS:
                return True
            if tag in _PACIFY_PT_MOD_TAGS:
                v = mod_value(m)
                if v is None or v > 0:
                    return True
    return False


def _pacify_makers(tree: ConceptTree) -> list[Signal]:
    """pacify_makers — an Aura OR Equipment that NEUTRALIZES the permanent
    it's attached to (Pacifism, Arrest, Faith's Fetters, Prison Term — CR
    508.1c/509.1b) by granting a can't-attack/can't-block restriction to
    "whatever this enchants"/"equipped creature", rather than destroying/
    exiling/countering/bouncing/fighting/-X'ing it (CR 611.2 — the
    permanent stays on the battlefield, so this is deliberately NOT part
    of `removal`; see the module note above and roles.py's
    `_INTERACTION_PRESETS` comment for the task #86 flip that split these
    two facts apart). Scope "you" (the controller neutralized someone/
    something). Gated by :func:`_pacify_aura_compensates` — see its own
    docstring for the Rage/Vow-cycle veto.
    """
    if _pacify_aura_compensates(tree):
        return []
    for unit in tree.units:
        for node in iter_static_defs(unit.node):
            if static_mode_tag(node) not in _PACIFY_AURA_MODES:
                continue
            affected = getattr(node, "affected", None)
            if set(filter_predicates(affected)) & ATTACHED_OBJECT_PREDICATES:
                return [
                    Signal(
                        "pacify_makers", "you", "", _site_raw(node), tree.name, "high"
                    )
                ]
    return []


def _neutralize_aura_compensates(tree: ConceptTree) -> bool:
    """True when the Aura pays its attached target back — a positive
    ``AddPower``/``AddToughness`` on an EnchantedBy/EquippedBy site (Burden
    of Proof's conditional "+2/+2 as long as it's a Detective you control")
    or a ``+1/+1``-counter placement aimed at the attached permanent
    (Awakened Awareness's enters-trigger "put X +1/+1 counters on enchanted
    permanent") — the ``_pacify_aura_compensates`` boundary re-cut for the
    base-P/T-set shape. ``AddKeyword`` deliberately does NOT veto here
    (unlike pacify's ``_PACIFY_ALWAYS_COMPENSATING_TAGS``): the neutralize
    class's own members grant keywords AS PART of the lock (Darksteel
    Mutation's indestructible, Deep Freeze's defender, Coerced to Kill's
    deathtouch — corpus-verified this session), so a keyword grant is not
    compensation evidence for this shape."""
    for unit in tree.units:
        for node in iter_static_defs(unit.node):
            if not set(filter_predicates(getattr(node, "affected", None))) & (
                ATTACHED_OBJECT_PREDICATES
            ):
                continue
            for m in getattr(node, "modifications", None) or ():
                if not isinstance(m, TypedMirrorNode):
                    continue
                if tag_of(m) in _PACIFY_PT_MOD_TAGS:
                    v = mod_value(m)
                    if v is None or v > 0:
                        return True
        for c in unit.effects:
            if (
                c.concept == "place_counter"
                and counter_kind(c.node).upper() == "P1P1"
                and set(filter_predicates(getattr(c.node, "target", None)))
                & ATTACHED_OBJECT_PREDICATES
            ):
                return True
    return False


def _single_target_neutralize(tree: ConceptTree) -> list[Signal]:
    """single_target_neutralize — an Aura that NEUTRALIZES the creature it
    enchants by overwriting its base power (CR 613.4b layer 7b) down to 0/1
    (Darksteel Mutation, Lignify, Frogify, Witness Protection — usually
    alongside "loses all abilities") or its card types to a non-creature's
    (CR 205.1a: Song of the Dryads), the soft-removal answer that beats
    indestructible and dodges death triggers (case law: Darksteel
    Mutation's own 2013-10-17 rulings — the creature keeps supertypes and
    stays a commander, it just stops being a threat). Deliberately its OWN
    narrow key (the ``counter_hate`` / ``adapt_matters`` narrow-lane
    precedent), not folded into:

    * ``removal`` — CR 611.2: the permanent STAYS on the battlefield, the
      same neutralizes-vs-removes boundary ``pacify_makers`` / budgets'
      ``_INTERACTION_PRESETS`` comment already enforce;
    * ``pacify_makers`` — a pacify lock is an attack/block RESTRICTION
      (CR 508.1c/509.1b ``CantAttack``-family static modes); a base-P/T
      set is a layer-7b characteristic overwrite (CR 613.4b), a different
      mechanic that still lets the 1/1 attack and block;
    * ``debuff_makers`` — that lane's own docstring EXCLUDES the
      single-Aura shrink by design (a neutralize is not a mass -1/-1
      enabler); ``base_pt_set`` keeps firing alongside as the broad P/T-SET
      toolbox lane (it also holds buff-animators like Ensoul Artifact and
      self-level-ups like Figure of Destiny, so it cannot serve the
      answer-shaped subset on its own).

    Structural arm: an ``EnchantedBy``/``EquippedBy``-affected static site
    that sets the object's card types without Creature and strips its
    abilities (Song of the Dryads, Imprisoned in the Moon —
    :func:`_neutralizing_mod`) or whose ``SetPower``
    value is <= 1 (the neutralize tell — power decides
    whether the threat still attacks; Lignify's 0/4 and Deep Freeze's 0/4
    keep firing on power, while Kenrith's Transformation's 3/3 Elk and Eye
    of Nidhogg's 4/2 goad-enabler stay out). Vetoed by
    :func:`_neutralize_aura_compensates` (Burden of Proof, Awakened
    Awareness — the Aura pays the target back, a buff wearing the same
    site shape). The ``synth_single_target_neutralize`` marker read serves
    the Cursed Role known-token tree (CR 111.10j), which has no unit to
    walk. Scope "you" (you neutralized someone's threat — the
    ``pacify_makers`` scope precedent).
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_single_target_neutralize":
            return [
                Signal("single_target_neutralize", "you", "", "", tree.name, "high")
            ]
    if _neutralize_aura_compensates(tree):
        return []
    for unit in tree.units:
        for node in iter_static_defs(unit.node):
            if not set(filter_predicates(getattr(node, "affected", None))) & (
                ATTACHED_OBJECT_PREDICATES
            ):
                continue
            for m in getattr(node, "modifications", None) or ():
                if _neutralizing_mod(m, node):
                    return [
                        Signal(
                            "single_target_neutralize",
                            "you",
                            "",
                            _site_raw(node),
                            tree.name,
                            "high",
                        )
                    ]
    return []


def _neutralizing_mod(m: object, static_def: object) -> bool:
    """A modification of ``static_def`` on the attached object that neutralizes
    it: a base power set to 1 or less, or a card-type set without Creature — the
    new type replaces the old (CR 205.1a, layer 4: CR 613.1d), so Song of the
    Dryads' and Imprisoned in the Moon's land is no creature at all — when the
    static also strips the object's abilities (:func:`strips_abilities`). A
    retype that keeps them is a dual-use Aura, as often on your own creature as
    an answer: One with the Stars' enchantment and Swift Reconfiguration's
    Vehicle (crewed back into a creature) keep every ability, per their
    rulings."""
    if not isinstance(m, TypedMirrorNode):
        return False
    tag = tag_of(m)
    if tag == "SetCardTypes":
        retyped = getattr(m, "core_types", None) or ()
        return (
            bool(retyped) and "Creature" not in retyped and strips_abilities(static_def)
        )
    if tag == "SetPower":
        v = mod_value(m)
        return v is not None and v <= 1
    return False


# ── task #96 (ADR-0040): type_changers — mass creature-type changers ─────────
def _type_changer_zone(affected: object, preds: set[str]) -> str | None:
    """Structural zone reach of a type-adding static's ``affected`` filter.

    "battlefield" (no zone qualifier — CR 400.7's default), "graveyard"
    (a Graveyard-only span — the Ashes of the Fallen shape, structured
    since phase v0.28.0), "all_zones" (a multi-zone beyond-battlefield
    span — the same-is-true rider, structured since phase v0.26.0; both
    retired their ledgered bridges at the v0.35.2 pin bump). ``InAnyZone``
    is parameterized (carries a ``zones`` list) — the payload, not the
    property's presence, decides the reach; a payload-less ``InAnyZone``
    (pre-v0.35 shape) reads as everywhere. ``None`` = a beyond-battlefield
    span that skips the graveyard and no serve arm consumes yet — skip
    rather than mis-key it battlefield."""
    anyzones = set(filter_inanyzone_zones(affected))
    if "InAnyZone" in preds and not anyzones:
        return "all_zones"
    zones = set(filter_inzone_zones(affected)) | anyzones
    beyond = zones - {"Battlefield"}
    if not beyond:
        return "battlefield"
    if beyond == {"Graveyard"}:
        return "graveyard"
    if "Graveyard" in beyond:
        return "all_zones"
    return None


def _single_target_type_changes(
    unit: AbilityUnit, node: object
) -> list[tuple[str, str, str, str]]:
    """The ``_type_changer_static_reads`` rows of one static def that makes a
    single TARGET creature the creature type of your choice or every type
    (Imagecrafter / Unnatural Selection's "Target creature becomes that type
    until end of turn", Trickery Charm, Amoeboid Changeling's "gains all
    creature types"): CR 613.1d, a layer-4 type-changing effect; CR 205.1a,
    the chosen type replaces the creature's others. Only a target either
    player's creature can be (controller unset), scoped "any" — the tool that
    forces another player's creature into a type a hoser punishes — which
    ADR-0040's tribal serves (scopes you / each) never read: a single target
    grows no tribe. A fixed subtype on one target is a polymorph (Turn to
    Frog), a reanimation rider or a land animation, never a changer of
    choice, so it is left out (:func:`creature_type_change_kinds`)."""
    target = _root_target_filter(unit)
    if (
        target is None
        or "Creature" not in filter_core_types(target)
        or filter_controller(target) is not None
        or filter_inzone_zones(target)
    ):
        return []
    return [
        ("any", "all" if kind == "all" else "", _site_raw(node), "battlefield")
        for kind in creature_type_change_kinds(node)
    ]


def _type_changer_static_reads(
    tree: ConceptTree,
) -> list[tuple[str, str, str, str]]:
    """(scope, subject, raw, zone) per qualifying mass type-adding static def.

    Qualifying: non-CDA (a changeling's own every-type is a CDA, CR
    702.73a/604.3 — membership, not a changer), a Creature-cored ``affected``
    with no attach predicate (Equipment/Aura "equipped/enchanted creature is
    a …" is a single recipient — ADR-0040 excludes single-target), and
    controlled by You or unscoped (None) ONLY — every other controller value
    skips (Dismiss into Dream's ``Opponent`` is removal-shaped, never
    tribal-serving; Polymorphist's Jest's ``TargetPlayer`` is the SAME
    removal shape — "each creature target player controls loses all
    abilities and becomes a blue Frog" pairs its ``AddSubtype`` with
    ``RemoveAllAbilities``/``SetPower``/``SetToughness``, a one-shot
    polymorph on a player-chosen board, not a Granter serving yours).
    Controller You → scope "you"; a bare "each/other creatures" static
    (Kudo) → "each" (it grows YOUR side too). A def over a single TARGET
    creature reads :func:`_single_target_type_changes` (scope "any")."""
    out: list[tuple[str, str, str, str]] = []
    for unit in tree.units:
        for node in iter_static_defs(unit.node):
            # The card's OWN every-creature-type CDA (``reads.is_every_creature_
            # type``) is the complement of this lane: type_changers reads what a
            # card grants to other creatures, so it skips the CDA.
            if getattr(node, "characteristic_defining", False):
                continue
            affected = getattr(node, "affected", None)
            if affected is None:
                continue
            if tag_of(affected) == "ParentTarget":
                out.extend(_single_target_type_changes(unit, node))
                continue
            preds = set(filter_predicates(affected))
            if preds & ATTACHED_OBJECT_PREDICATES:
                continue
            cores = {c.lower() for c in filter_core_types(affected)}
            if "creature" not in cores:
                continue
            ctrl = filter_controller(affected)
            if ctrl not in ("You", None):
                continue
            if ctrl is None:
                # A controller-less span still scopes "you" when it reaches
                # only YOUR OWN cards (Ashes of the Fallen's ``Owned: You``
                # graveyard grant — CR 108.3); an opponent-owned span is
                # never tribal-serving.
                owned = filter_owned_controller(affected)
                if owned == "You":
                    ctrl = "You"
                elif owned is not None:
                    continue
            scope = "you" if ctrl == "You" else "each"
            zone = _type_changer_zone(affected, preds)
            if zone is None:
                continue
            for m in getattr(node, "modifications", None) or ():
                tag = tag_of(m)
                if tag == "AddAllCreatureTypes":
                    out.append((scope, "all", _site_raw(node), zone))
                elif (
                    tag == "AddChosenSubtype"
                    and getattr(m, "kind", None) == "CreatureType"
                ):
                    out.append((scope, "", _site_raw(node), zone))
                elif tag == "AddSubtype":
                    # The _subtypes vocabulary gate: Ashaya's Forest is a LAND
                    # type, Equipment an artifact subtype — never a tribe.
                    resolved = _resolve_subject(
                        str(getattr(m, "subtype", "") or ""), CREATURE_SUBTYPES
                    )
                    if resolved:
                        out.append((scope, resolved, _site_raw(node), zone))
                elif tag == "AddKeyword" and mod_keyword_name(m) == "Changeling":
                    # Verified-review Fix 5: Mirror Entity's "{X}: ...
                    # creatures you control ... gain all creature types" is
                    # a CONFERRED static (inside the {X} activated ability's
                    # effect) that phase encodes as a plain AddKeyword grant
                    # rather than AddAllCreatureTypes — CR 702.73a: having
                    # changeling means every creature type, the exact "all"
                    # shape AddAllCreatureTypes already serves. Distinct
                    # from the ``characteristic_defining`` skip above (a
                    # card's OWN inherent changeling, a CDA membership read,
                    # never reaches this non-CDA conferred-static arm).
                    out.append((scope, "all", _site_raw(node), zone))
    return out


def _type_changers(tree: ConceptTree) -> list[Signal]:
    """type_changers (+_all_zones / +_graveyard) — mass creature-type changers
    (CR 613.1d layer 4), the ADR-0040 extraction prerequisite: Leyline of
    Transformation was the Sliver benchmark's falsely-filler build-around.

    Scopes: "you" / "each" for a mass changer, "any" for a single target
    creature made the type of your choice or every type (Imagecrafter,
    Amoeboid Changeling — :func:`_single_target_type_changes`, which the
    tribal serves never read).

    Subjects: "" = the chosen type (``AddChosenSubtype`` kind=CreatureType,
    Xenograft), "all" = every creature type (``AddAllCreatureTypes``,
    Maskwood Nexus), "<Type>" = a fixed subtype (``AddSubtype`` through the
    ``_resolve_subject`` vocabulary gate, Hivestone → Sliver). Whether the
    grant retains prior types ("in addition", CR 205.1b) or replaces them
    (Conspiracy) both count — either way your board IS the tribe.

    Zone reach is modeled as sibling keys from v1 (ADR-0040): a bare
    "creatures you control" static is battlefield-only (CR 109.2), so the
    base key alone (Xenograft). The "The same is true for creature spells
    you control and creature cards you own that aren't on the battlefield"
    rider reaches the stack/hand/library/graveyard — phase structures it as
    an InAnyZone span since v0.26.0, and Ashes of the Fallen's
    graveyard-only static as InZone Graveyard since v0.28.0; both zone keys
    are pure structural reads now (their ledgered bridges retired at the
    v0.35.2 pin bump)."""
    reads = _type_changer_static_reads(tree)
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def push(key: str, scope: str, subject: str, raw: str) -> None:
        if (key, scope, subject) not in seen:
            seen.add((key, scope, subject))
            out.append(Signal(key, scope, subject, raw, tree.name, "high"))

    for scope, subject, raw, zone in reads:
        if zone == "graveyard":
            # A structurally-zoned graveyard-only static (the Ashes shape)
            # keys graveyard alone — never battlefield.
            push("type_changers_graveyard", scope, subject, raw)
            continue
        push("type_changers", scope, subject, raw)
        if zone == "all_zones":
            # Structural InAnyZone reach — the same-is-true rider.
            push("type_changers_all_zones", scope, subject, raw)
            push("type_changers_graveyard", scope, subject, raw)
    return out


# ── task B-1: chosen_type_matters — wildcard tribal payoffs ──────────────────
# The chosen-type reference markers phase stamps into filters. A CreatureType
# choice made as the permanent enters (CR 614.12 — the Voice of All as-enters
# replacement shape) persists, and every payoff site that cares carries one of
# these filter properties. IsChosenCardType is the spell-cast form (Door of
# Destinies watches CAST SPELLS of the chosen type, a Card filter).
_CHOSEN_TYPE_PREDS = frozenset({"IsChosenCreatureType", "IsChosenCardType"})
# Static modes admitted by the marked-static arm: a plain continuous payload
# (Door's dynamic anthem, Adaptive Automaton's lord line) or a trigger-doubler
# over the chosen type (Roaming Throne). Default-deny keeps punisher-shaped
# statics out (An-Zerrin Ruins' marked "CantUntap" static).
_CHOSEN_STATIC_MODES = frozenset({"Continuous", "DoubleTriggers"})


def _chosen_type_serve_statics(tree: ConceptTree) -> list[tuple[str, str]]:
    """(scope, raw) per marked static that SERVES the chosen type.

    Serve-vs-punish gates, in order: controller ``Opponent`` skips (Plague
    Engineer projects -1/-1 onto an opponent's chosen tribe); a mode outside
    ``_CHOSEN_STATIC_MODES`` skips (An-Zerrin Ruins' CantUntap); a negative
    literal AddPower/AddToughness payload skips (the valence gate — phase
    drops Engineered Plague's marker today, but once its parser structures
    the "-1/-1 to the chosen type" static this gate keeps it out). Controller
    You → scope "you"; unscoped (Cover of Darkness's symmetric Fear grant,
    Urza's-Incubator-style neutral filters) → "each"."""
    out: list[tuple[str, str]] = []
    for unit in tree.units:
        for node in iter_static_defs(unit.node):
            mode = static_mode_tag(node)
            affected = getattr(node, "affected", None)
            if affected is None:
                continue
            ctrl = filter_controller(affected)
            if ctrl == "Opponent":
                continue
            # Cost-reduction rides the ModifyCost static mode: a Reduce whose
            # spell_filter is marked serves the chosen type (Herald's Horn /
            # Urza's Incubator); an Increase would be a tax, never a serve.
            if mode == "ModifyCost":
                inner = getattr(getattr(node, "mode", None), "inner", None)
                spell_filter = getattr(inner, "spell_filter", None)
                if (
                    getattr(inner, "mode", None) == "Reduce"
                    and spell_filter is not None
                    and set(filter_predicates(spell_filter)) & _CHOSEN_TYPE_PREDS
                ):
                    scope = "you" if ctrl == "You" else "each"
                    out.append((scope, _site_raw(node)))
                continue
            if not set(filter_predicates(affected)) & _CHOSEN_TYPE_PREDS:
                continue
            if mode not in _CHOSEN_STATIC_MODES:
                continue
            if any(
                tag_of(m) in ("AddPower", "AddToughness")
                and isinstance(getattr(m, "value", None), int)
                and getattr(m, "value", 0) < 0
                for m in getattr(node, "modifications", None) or ()
            ):
                continue
            scope = "you" if ctrl == "You" else "each"
            out.append((scope, _site_raw(node)))
    return out


#: The type choices that are not a creature type (CR 205.2a card types; land
#: types): a chosen-type marker read off one of these names no tribe.
_NON_CREATURE_TYPE_CHOICES = frozenset({"CardType", "LandType"})


def _choices(tree: ConceptTree) -> list[Choice]:
    """Every ``Choose`` effect on the tree (:func:`choice_of`):
    ``("CreatureType", ())`` for an open choice (Door of Destinies),
    ``("CreatureType", ("Elemental", …))`` for a listed one (Dawn-Blessed
    Pennant), ``("CardType", ("Artifact", …))`` for Cloud Key."""
    return [
        choice
        for unit in tree.units
        for eff in getattr(unit, "effects", None) or ()
        if (choice := choice_of(getattr(eff, "node", None))) is not None
    ]


def _chosen_type_options(choices: list[Choice]) -> tuple[str, ...] | None:
    """The creature types a RESTRICTED chooser may pick (Dawn-Blessed Pennant:
    "choose Elemental, Elf, …, or Treefolk"); ``None`` for an open choice
    ("choose a creature type": Door of Destinies) or when no creature-type
    Choose is present."""
    options: list[str] = []
    for kind, listed in choices:
        if kind != "CreatureType":
            continue
        if not listed:
            return None  # an open chosen type: the wildcard serves every tribe
        options.extend(listed)
    return tuple(dict.fromkeys(options)) or None


def _chosen_type_matters(tree: ConceptTree) -> list[Signal]:
    """chosen_type_matters — wildcard tribal payoffs (task B-1, 2026-07-16
    study: 7 adjudicated extraction gaps).

    Cards that choose a creature type as they enter (CR 614.12) and PAY OFF
    the chosen type — Door of Destinies, Kindred Discovery, Herald's Horn,
    Urza's Incubator. The subject is chosen at runtime, so the payoff serves
    WHATEVER tribe the deck fields; every per-subject tribal spec credits the
    key via its serve-side ``signal_idents`` arm (a Sliver deck wants
    Herald's Horn exactly as a Goblin deck does). Subject is always ``""``
    (the chosen type), mirroring type_changers' chosen-subject convention.

    The lane keys on the payoff sites that REFERENCE the choice — the
    ``IsChosenCreatureType`` / ``IsChosenCardType`` filter properties — never
    on the ``Choose`` replacement itself (punishers like Engineered Plague
    choose too). Type-GRANTS stay type_changers-only (CR 613.1d layer 4:
    granting membership is the enabler side; referencing the choice in a
    reward filter is the payoff side — the c934b718 membership-not-payoff
    law). Two read sites:

    * marked STATICS via ``_chosen_type_serve_statics`` (continuous payloads,
      trigger-doublers, ModifyCost reductions — with the serve-vs-punish
      gates documented there);
    * marked TRIGGERS: a trigger whose ``valid_card`` carries the marker
      (Kindred Discovery's enters-or-attacks draw). Corpus-verified all-
      serve at phase v0.23.0 (9 cards, every payload beneficial). Scope
      "you" when the watched filter is controller-You or the trigger is a
      SpellCast (you cast the spells that Door counts); "each" for an
      any-player watch (Species Specialist's chosen-type dies-trigger).

    One-shot chosen-type value (Distant Melody), chosen-type mana
    (Cavern of Souls), and replacement payoffs (Metallic Mimic) are known
    not-served-yet classes — recorded for a v2 arm, not dismissed.

    A card that chooses a card or land type and no creature type (Cloud Key,
    Umori, the Collector, Shimmer) is no tribal payoff, whatever its filter's
    marker reads.

    A RESTRICTED chooser (Dawn-Blessed Pennant picks from eight printed types)
    serves only those tribes, so it emits one signal per listed type instead of
    the wildcard ``""`` — a Scarecrow deck never reads it as a payoff."""
    out: list[Signal] = []
    choices = _choices(tree)
    kinds = {kind for kind, _ in choices}
    if kinds & _NON_CREATURE_TYPE_CHOICES and "CreatureType" not in kinds:
        # A card that chooses a card type (CR 205.2a: Cloud Key's "artifact,
        # creature, …") or a land type (Shimmer) and no creature type reads
        # no creature type (CR 205.3m) off its marker, so the chosen-type
        # payoff serves no tribe.
        return out
    seen: set[tuple[str, str]] = set()
    subjects = _chosen_type_options(choices) or ("",)

    def push(scope: str, raw: str) -> None:
        for subject in subjects:
            if (scope, subject) not in seen:
                seen.add((scope, subject))
                out.append(
                    Signal(
                        "chosen_type_matters", scope, subject, raw, tree.name, "high"
                    )
                )

    for scope, raw in _chosen_type_serve_statics(tree):
        push(scope, raw)
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        node = unit.node
        valid_card = getattr(node, "valid_card", None)
        if valid_card is None:
            continue
        if not set(filter_predicates(valid_card)) & _CHOSEN_TYPE_PREDS:
            continue
        ctrl = filter_controller(valid_card)
        if ctrl == "Opponent":
            continue
        mode = getattr(node, "mode", None)
        mode_tag = mode if isinstance(mode, str) else tag_of(mode)
        scope = "you" if ctrl == "You" or mode_tag == "SpellCast" else "each"
        push(scope, str(getattr(node, "description", "") or ""))
    return out


# ── task B-2: damage_for_each — board-count damage ───────────────────────────
# Recovered-residue arm (ADR-0038 W5 tails discipline): phase parses these
# whole effects as Unimplemented, but the recovery allowlist surfaces them as
# recovered deal_damage nodes carrying the raw clause. Corpus census at phase
# v0.23.0: the tapped-this-way form is Burn at the Stake alone; the
# creatures-you-control form is Superior Numbers alone (Angel's Trumpet's
# punisher counts THAT player's tapped creatures — matches neither).
_DFE_RECOVERED_RX = re.compile(
    r"any target equal to \w+ times the number of creatures tapped this way"
    r"|number of creatures you control",
    re.IGNORECASE,
)
# Phase mis-parses "the number of X that player controls" counts as
# controller "You". Full You-pool census (phase v0.23.0): Jovial Evil and
# Wing Storm are the two live false fires; Anathemancer / Price of Progress
# die at the creature/vocabulary gate anyway.
_DFE_MISPARSE_RX = re.compile(
    r"number of\b[^.\n]*\bthat player controls", re.IGNORECASE
)


def _damage_for_each(tree: ConceptTree) -> list[Signal]:
    """damage_for_each — one-shot damage that scales with YOUR board (task
    B-2, 2026-07-16 study: the go-wide deck's reach/finisher read).

    Structural: a ``deal_damage`` concept whose AMOUNT is an ``ObjectCount``
    over a board you control — ``amount → (Multiply?) Ref → ObjectCount``
    via ``ref_count_filter`` (Thraben Charm's x2 reads through) — with the
    counted filter's controller strictly ``You`` (Chain Reaction's symmetric
    count and Gempalm Incinerator's all-Goblins count stay out). The count
    is game information determined once, on application (CR 608.2h: "such
    as the number of creatures on the battlefield") — which is exactly why
    a wide board turns these into finishers. X-cost damage is NOT a board
    read: X is fixed at announcement as a mana choice (CR 601.2b / 107.3b)
    — Comet Storm (Variable amount) and Crackle with Power never enter.
    Crater's Claws' ObjectCount lives in its Ferocious CONDITION, not the
    amount site, so the amount-site read never sees it (correctly: the
    count gates a bonus, it doesn't scale the X).

    Subject: ``""`` when the counted filter is Creature-cored (generic
    go-wide); a fixed subtype through the ``_subtypes`` vocabulary gate
    (Goblin War Strike → "Goblin", Scourge of Valkas → "Dragon") — a
    non-creature count (Equipment, Treasure, lands) never fires. Scope:
    ``"opponents"`` when the damage reaches a player (``effect_reaches_
    player`` — the finisher read), ``"any"`` for a creature-only bite
    (board-scaled removal, Outnumber). A "that player controls" text guard
    kills phase's two mis-parsed opponent-board counts (Jovial Evil, Wing
    Storm). Goblin Lyre's count sits inside FlipCoin's ``win_effect``, which
    the effect walk descends."""
    out: list[Signal] = []
    seen: set[tuple[str, str]] = set()

    def push(scope: str, subject: str, raw: str) -> None:
        if (scope, subject) not in seen:
            seen.add((scope, subject))
            out.append(
                Signal("damage_for_each", scope, subject, raw, tree.name, "high")
            )

    for unit in tree.units:
        for c in unit.effect_concepts("deal_damage"):
            raw = c.raw or ""
            if c.recovered_by == "damage":
                if _DFE_RECOVERED_RX.search(raw):
                    scope = "opponents" if "any target" in raw.lower() else "any"
                    push(scope, "", raw)
                continue
            filt = ref_count_filter(c.node, "amount")
            if filt is None:
                continue
            if filter_controller(filt) != "You":
                continue
            desc = str(getattr(unit.node, "description", "") or "")
            if _DFE_MISPARSE_RX.search(raw + " " + desc):
                continue
            cores = {t.lower() for t in filter_core_types(filt)}
            if "creature" in cores:
                subject = ""
            else:
                subject = next(
                    (
                        resolved
                        for st in filter_subtypes(filt)
                        if (resolved := _resolve_subject(str(st), CREATURE_SUBTYPES))
                    ),
                    "",
                )
                if not subject:
                    # The vocabulary gate: an Equipment/Treasure/land count is
                    # not a board-of-bodies read.
                    continue
            scope = "opponents" if effect_reaches_player(c.node, unit.node) else "any"
            push(scope, subject, raw or desc)
    return out


# ── task B-3: keep_n_wrath — choose-N-keep-the-rest board resets ─────────────
# The core-type gate and both shape walks live in bridge_ledger
# (keep_n_casr_reads / keep_n_shape_b_reads) — one home for the lane AND
# the bridge's gap (verified-review F1/F9).


def _keep_n_wrath(tree: ConceptTree) -> list[Signal]:
    """keep_n_wrath — "each player chooses N, then sacrifices/destroys the
    rest" board resets (task B-3, 2026-07-16 study): Single Combat,
    Cataclysm, Tragic Arrogance, Divine Reckoning.

    DISJOINT from edict_makers by adjudication: an edict forces the fresh
    CR 701.21a sacrifice choice (its controller picks which permanent to
    lose — the political dodge-indestructible read); a keep-N wrath INVERTS
    the choice (pick which to KEEP — the rest go), which is why a voltron
    deck actively wants them: the one big threat is exactly what you keep,
    and the reset dodges targeted removal entirely. A keep-N IS still a
    wipe, so the mass_removal overlap (Cataclysm fires both) is correct.

    Two structural shapes at phase v0.23.0 (whole-bulk prototype: 14 cards,
    zero false positives):

    * the first-class ``ChooseAndSacrificeRest`` node (8-card corpus:
      Cataclysm class), gated on a ``sacrifice_filter`` core in
      ``_KEEP_N_CHOOSE_TYPES`` — both chooser_scope values fire (every
      player's board resets whether each player picks or you pick for all,
      Tragic Arrogance);
    * a ``TargetOnly`` choose followed by a ``Sacrifice``/``Destroy`` whose
      target is the ``TrackedSet`` back-reference (Single Combat class).
      ``DestroyAll(TrackedSet)`` is deliberately NOT accepted — that is
      destroy-the-CHOSEN (Druid of Purification), mass_removal's arm.

    Scope: "each" for the symmetric resets; "opponents" when the choose is
    scoped away from you — a You-controller filter under an Opponent
    player_scope (No One Will Hear Your Cries — phase's ScopedPlayer
    mislabel class) or under an OnlyDuringOpponentsTurn trigger (Archfiend
    of Depravity). The Unimplemented-choose members (Duneblast, Stick
    Together, Mount Doom, Promise of Loyalty) ride the ledgered
    ``keep_n_wrath_unimplemented_choose`` bridge, "at random" vetoed (Last
    One Standing keeps a random creature — protects nothing). Winnowing's
    tribal-keep (SharesQuality/DoesNotShare sacrifice, n=1 corpus) is a
    recorded v2 arm, not dismissed; Harsh Mercy's dropped complement stays
    a plain mass_removal fire until phase structures it."""
    out: list[Signal] = []
    seen: set[str] = set()

    def push(scope: str, raw: str) -> None:
        if scope not in seen:
            seen.add(scope)
            out.append(Signal("keep_n_wrath", scope, "", raw, tree.name, "high"))

    for scope, raw in (*keep_n_casr_reads(tree), *keep_n_shape_b_reads(tree)):
        push(scope, raw)
    return out


# ── task B-4: spell_redirect — the ChangeTargets(Spell) doer ─────────────────
def _spell_redirect(tree: ConceptTree) -> list[Signal]:
    """spell_redirect — redirect instruments for spells and abilities on the
    stack (task B-4, 2026-07-16 study): Wild Ricochet, Deflecting Swat, Bolt
    Bend, Misdirection, Spellskite, Reroute's "Change the target of target
    activated ability with a single target", and the spell thieves that take a
    spell and may retarget it (Commandeer, Aethersnatch, Perplexing Chimera).

    Structural: a ``ChangeTargets`` node whose ``target`` carries a
    ``StackSpell`` / ``StackAbility`` leaf (``reads.redirects_stack_object`` —
    one walk over the tree, so a redirect nested in a d20 table, Wyll's
    Reversal, counts too), or a unit that gains control of a stack spell
    (``reads.steals_stack_spell``). Changing the targets of the ORIGINAL spell
    or ability (CR 115.7: "Some effects allow a player to change the target(s)
    of a spell or ability") is fizzle protection and a political blowout —
    distinct from copy-with-new-targets (Fork), where only the COPY is
    retargeted (CR 707.10c): Fork's retarget rides a FIELD on its CopySpell
    node, never a ChangeTargets node (that stays spell_copy_makers; Wild
    Ricochet fires both lanes off its two nodes). ``forced_to`` (Spellskite's
    redirect-to-self) and ``scope`` (All/Single) are irrelevant.

    ``roles.protects`` reads this key: Reroute (an ability redirect) and the
    thieves joined 2026-10-08 (Dan: taking a removal spell answers it like a
    counterspell). Corpus census at phase v0.94.0: 36 ChangeTargets nodes, 28
    carry a stack leaf; zero Unimplemented residue — no bridge."""
    if any(redirects_stack_object(n) for n in tree.iter_typed()) or any(
        steals_stack_spell(u) for u in tree.units
    ):
        return [Signal("spell_redirect", "you", "", "", tree.name, "high")]
    return []


@dataclass(frozen=True)
class GrantPayload:
    """WHAT a static mass-grant confers (ADR-0040 prerequisite): the
    ``AddKeyword`` / ``GrantAbility`` payload the ``type_matters`` static-def
    read deliberately drops. A structured read for the value layer (Granter
    quality, grant-covered roles, closer counting — tasks #97/#98/#100),
    never a Signal: emission stays strict, a recipient never emits the
    granted ability.

    ``kind`` is "keyword" (an ``AddKeyword`` — Bonescythe's double strike)
    or "ability" (a ``GrantAbility`` quoted activated/triggered body —
    Scuttling Sliver's untap, CR 113.3b — which carries no keyword for the
    quality table to grade). ``keyword`` is normalized lowercase ("double
    strike", "protection" — a parameterized MirrorVariant normalizes to its
    key name; "" for an ability grant); ``subject`` is the recipient
    filter's lowercased words (("creature", "sliver")); ``raw`` carries the
    grant sentence so a quality predicate (ADR-0040 §2's hellbent-gate
    mislead) can read the condition without new fields."""

    keyword: str
    scope: str
    subject: tuple[str, ...]
    raw: str
    kind: str = "keyword"


_GRANT_KW_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")

# Verified-review Fix 4: a recipient defined by a COMBAT relationship
# (``CombatRelation`` — "blocking or blocked by ~") is never a controller-
# scoped mass grant: Alms Beast's "Creatures blocking or blocked by this
# creature have lifelink." gifts lifelink to whichever creature ends up in
# that combat, including an OPPONENT'S blocker — a drawback riding a fight,
# not a Granter payload. Same exclusion discipline as the EquippedBy/
# EnchantedBy attach predicates below.
_GRANT_HOSTILE_PREDS = frozenset({"CombatRelation"})
_GRANT_ANTHEM_TAGS = frozenset({"AddPower", "AddToughness"})


def extract_grant_payloads(tree: ConceptTree) -> tuple[GrantPayload, ...]:
    """Every MASS static grant payload on the tree, in static-def order.

    Walks the static defs directly (the ``_type_changer_static_reads``
    discipline) rather than the concept overlay, so the mass gate is the
    same one the lane applies: an attach-predicate ``affected`` ("equipped/
    enchanted creature has flying") is a single recipient — never a Granter
    payload; a COMBAT-relation ``affected`` ("creatures blocking or blocked
    by this creature" — Alms Beast, verified-review Fix 4) is a hostile/
    shared recipient, same exclusion; Opponent-side statics are excluded;
    controller You → scope "you", a bare mass static ("All creatures
    have …") → "each".

    A raw stat-boost (``AddPower``/``AddToughness``, no keyword for the
    quality table to grade — Goblin King's +1/+1 anthem) is its OWN
    payload, ``kind="anthem"``, one per static regardless of whether both
    mods are present (verified-review Fix 3: the anthem IS the card's
    value; the payload read must not see only its table-weak sibling
    keyword)."""
    out: list[GrantPayload] = []
    for unit in tree.units:
        for node in iter_static_defs(unit.node):
            affected = getattr(node, "affected", None)
            if affected is None:
                continue
            preds = set(filter_predicates(affected))
            if preds & ATTACHED_OBJECT_PREDICATES or preds & _GRANT_HOSTILE_PREDS:
                continue
            cores = {c.lower() for c in filter_core_types(affected)}
            if "creature" not in cores:
                continue
            ctrl = filter_controller(affected)
            if ctrl == "Opponent":
                continue
            scope = "you" if ctrl == "You" else "each"
            subject = tuple(
                s.lower()
                for s in (*filter_core_types(affected), *filter_subtypes(affected))
            )
            raw = _site_raw(node)
            anthem_emitted = False
            for m in getattr(node, "modifications", None) or ():
                tag = tag_of(m)
                if tag == "AddKeyword":
                    kw = mod_keyword_name(m)
                    if kw:
                        out.append(
                            GrantPayload(
                                keyword=_GRANT_KW_CAMEL.sub(" ", kw).lower(),
                                scope=scope,
                                subject=subject,
                                raw=raw,
                            )
                        )
                elif tag == "GrantAbility":
                    out.append(
                        GrantPayload(
                            keyword="",
                            scope=scope,
                            subject=subject,
                            raw=raw,
                            kind="ability",
                        )
                    )
                elif tag in _GRANT_ANTHEM_TAGS and not anthem_emitted:
                    anthem_emitted = True
                    out.append(
                        GrantPayload(
                            keyword="",
                            scope=scope,
                            subject=subject,
                            raw=raw,
                            kind="anthem",
                        )
                    )
    return tuple(out)


def _direct_damage(tree: ConceptTree) -> list[Signal]:
    """Burn that reaches a PLAYER (Fanatic of Mogis, Lightning Bolt — CR 120.1).

    Mirrors the deleted ``_signals_ir``'s line ~8237 (``cat=="damage"`` +
    ``_ir_damage_reaches_
    player``). Structural: a ``DealDamage`` / ``DamageEachPlayer`` / ``DamageAll``
    effect whose recipient reaches a player (``effect_reaches_player`` — each/opp
    player, "any target"/"any other target", "target player or planeswalker" (an
    ``Or`` alternation), "target opponent" (an empty-``type_filters`` ``Typed``
    scoped by ``controller``), "that player" (``ScopedPlayer``), "that creature's/
    permanent's controller" (``ParentTargetController``, CR 102.1), or "defending
    player" (``DefendingPlayer``, CR 506.4c) — NOT a creature/permanent-only bite,
    NOT incidental self-damage ("deals N damage to you" — a bare ``Controller``).
    Damage DOUBLERS are a separate lane. Scope "you" (the burn controller).

    ADR-0038 W4 giants: a structural fallback (:func:`has_nested_damage_
    reaching_player`, the ``has_nested_fight`` precedent) recovers a damage
    effect buried inside a GRANTED activated/static ability's ``.definition``
    or a ``CreateToken`` token-ability definition — none of which the flat
    per-unit ``effect_concepts`` walk surfaces as its own top-level concept
    (Barbed Field's Aura-granted "{T}: ... deals 1 damage to any target.",
    Acidic Sliver's lord-granted Sliver ability, Dance with Devils's token
    "When this token dies, it deals 1 damage to any target").

    Walked per-UNIT (not the whole-card ``tree.effect_concepts`` union) so
    ``effect_reaches_player`` can pass the owning ability as ``root`` — a
    bare ``ParentTarget`` recipient (a modal "instead" amendment quoting an
    earlier clause) only resolves against ITS OWN ability's sibling targets
    (Aggressive Sabotage's "Target player discards ... deals 3 damage to
    that player" vs. Fiery Impulse's "target creature ... deals 3 instead").

    ADR-0038 W5 tails: a recovered "damage" node (a computed-amount clause
    phase parks whole — Soulblast's sacrifice tally, Iron Mastiff's d20 rows)
    has no typed recipient, so it reads the seam's ``OTHER_PLAYER`` mark
    (``recovery.read_clause``: any target, each opponent, target / that /
    defending player, a permanent's controller). "to you" alone is no reach —
    the typed path's incidental self-damage exclusion (Iron Mastiff's "1-9"
    row).

    ADR-0039 W7 endgame (2026-07-11) — PROMOTED. One real structural gain
    (:func:`~mtg_utils._card_ir.crosswalk._unit_has_target`'s
    ``optional_for`` widening — Sin Prodder's "Any opponent may have you
    put that card into your graveyard. If a player does, ~ deals damage to
    that player..." reads the choosing player off a bare ``optional_for``
    string marker no ``_SCOPE_FIELDS`` slot carried). One card
    (Cruel Sadist) joins the PRE-EXISTING creature-only tap-ability shed —
    legacy's OWN ``_DIRECT_DAMAGE_MIRROR`` regex over-fires on it via its
    recipient-blind ``{T}:...deals damage`` alternative even though the
    card's real text has no player-reaching clause at all (an empty-``raw``
    legacy signal — see :func:`test_direct_damage_excludes_tap_ability_
    creature_only_shed`). Ten REMAINING ledgered bridges
    (``bridge_ledger.py``, all sharing :func:`~mtg_utils._deck_forge.
    bridge_ledger._no_player_reaching_damage_node`) close most of the rest
    — a compound "creature + that creature's controller" dropped-clause
    template (Judgment Bolt / Liquid Fire / Synchronized Spellcraft), six
    further singleton dropped-clause/upstream-parse-failure shapes (Vexing
    Arcanix, Curse of Shaken Faith, Flames of the Blood Hand, Insult //
    Injury, Captain Rex Nebula, Ellie Vengeful Hunter; Valakut Exploration's
    row RETIRED at the v0.66.0 pin bump — upstream #7047 restored the
    trailing damage clause — and Avatar Aang's at v0.104.0, which carries the
    fifth conjunct), and a kicker-mode ParentTarget-reuse pair (Goblin
    Barrage / Unstable Footing). Phase v0.104.0's granted burns behind a cost
    (Karn, Living Legacy's emblem "Tap an untapped artifact you control: ~ deals
    1 damage to any target", Blazing Torch's "Sacrifice ~: ~ deals 2 damage …")
    recover as the grant's own damage instruction. See each bridge row for its
    own corpus census; every remaining shed class stays pinned from W4/W6
    (creature/battle-only, bare-self-damage, damage doubler/matters/
    prevention). CR 120.1 / 102.1 / 303.4c / 702.33d verified this session.

    Keranos, God of Storms's ``effect_structure`` parse-failure residue (its
    whole reveal-and-punish ability) is recovered instruction by instruction
    (``recovery.recover_concepts``): "… Keranos deals 3 damage to any target"
    reads as a recovered damage clause. (The synthesis arms that stood in for
    it and for Maestros Diabolist's quoted Devil grant retired at phase
    v0.104.0.)
    """
    for unit in tree.units:
        for c in unit.effect_concepts("deal_damage"):
            if c.recovered_by == "damage":
                if OTHER_PLAYER in c.reading:
                    return [
                        Signal("direct_damage", "you", "", c.raw, tree.name, "high")
                    ]
                continue
            if effect_reaches_player(c.node, unit.node):
                return [Signal("direct_damage", "you", "", c.raw, tree.name, "high")]
        if has_nested_damage_reaching_player(unit.node):
            return [Signal("direct_damage", "you", "", "", tree.name, "high")]
    return []


_LANDFALL_STATIC_LAND_DROP_MODES = frozenset(
    {"MayPlayAdditionalLand", "AdditionalLandDrop"}
)


def additional_land_play(tree: ConceptTree) -> bool:
    """A static/one-shot ``MayPlayAdditionalLand`` / ``AdditionalLandDrop`` MODE
    anywhere in the tree (Exploration, Azusa's "two additional lands", Summer
    Bloom — CR 305.2). ONE read, two consumers: the ``landfall`` lane below (an
    extra land drop is a landfall enabler) and the ``ramp`` preset's concept arm
    (``theme_presets._ramp_concept`` — an extra land drop is land acceleration,
    but ``landfall`` alone can't say so: the key also covers pure payoffs)."""
    for unit in tree.units:
        nodes = [c.node for c in unit.iter_concepts()]
        if unit.origin == "static":
            nodes.append(unit.node)
        if any(static_mode_tag(n) in _LANDFALL_STATIC_LAND_DROP_MODES for n in nodes):
            return True
    return False


# ADR-0038 W3 batch 4 (lands-and-ramp cluster): the "play lands from your
# graveyard" enabler (Crucible of Worlds, Ramunap Excavator — CR 305.1) is a
# ``GraveyardCastPermission`` static MODE whose ``affected`` filter names
# Land. ``TopOfLibraryCastPermission`` (Oracle of Mul Daya, Augur of Autumn —
# "play lands from the top of your library") is DELIBERATELY excluded: the
# legacy ``LANDFALL_REGEX`` has no top-of-library branch at all (corpus-
# verified — including it over-fired 8 commander-legal cards with no
# graveyard-recursion angle, e.g. Augur of Autumn, The Fourth Doctor).

# Last-resort word idioms (mechanism preference (d)): the residue phase's
# typed substrate leaves wholly unstructured. PER-CLAUSE scoped (period /
# colon / newline-delimited) so an unrelated sibling clause's "enters" or "a
# land" never cross-bleeds into this one (Caged Sun's own-ETB "As this
# artifact enters" bleeding into its SEPARATE "a land's ability" clause;
# Tameshi, Reality Architect's colon-joined "Return a land you control to
# its owner's hand: Return target artifact ... from your graveyard to the
# battlefield" bleeding the bounce-to-hand "land" into the artifact/
# enchantment recursion clause — an adjudicated SHED, CR 305.1: the land
# never goes from graveyard to battlefield here, it goes hand<->battlefield
# as an activation cost). Corpus-verified over the full commander-legal
# sweep: zero residual live_only beyond the Tameshi shed, zero new
# over-fires. CR 207.2c.
_LANDFALL_CLAUSE_RX = re.compile(r"(?<=[.!?:])\s+|\n+")
_LANDFALL_ETB_WORD_RX = re.compile(r"whenever a land.*enter", re.IGNORECASE | re.DOTALL)
_LANDFALL_GY_RETURN_WORD_RX = re.compile(
    r"\breturn\b[^.:]*\bland\b[^.:]*from your graveyard to the battlefield",
    re.IGNORECASE,
)


def _landfall_clauses(tree: ConceptTree) -> list[str]:
    """The card's own face oracle split into period/colon/newline clauses."""
    kept = _REMINDER_RX.sub(" ", tree.oracle or "")
    return _LANDFALL_CLAUSE_RX.split(kept)


def _landfall(tree: ConceptTree) -> list[Signal]:
    """A land ENTERING, or an enabler that fuels repeat land drops (Lotus Cobra,
    Crucible of Worlds, Exploration — CR 207.2c / 305.1 / 305.2 / 305.4 / 400.7 /
    603.6a). Six structural arms + a PER-CLAUSE last-resort word-idiom tail (no
    live_only beyond one adjudicated shed, corpus-verified):

    * a battlefield ``enters`` trigger watching a Land object (the ability-word
      "Landfall" payoff itself — Lotus Cobra, Tireless Tracker; CR 603.6a);
    * an ``EnteredThisTurn`` QTY CONDITION naming Land + you (the "Landfall — if
      you had a land enter the battlefield ... this turn" spell-mode gate —
      Searing Blaze, Groundswell, Rest for the Weary, Mysteries of the Deep, Tomb
      Hex, Wandering Troubadour — CR 207.2c);
    * a NESTED trigger def (:func:`iter_nested_trigger_defs` — a granted/token/
      emblem ability, mechanism (b)) whose derived shape is a battlefield-bound
      Land watcher (Ka-Zar's Zabu token, Gysahl Greens' Bird, Nissa's emblem —
      the created/granted PERMANENT carries its own landfall payoff, CR 603.6a);
    * a static/one-shot ``MayPlayAdditionalLand`` / ``AdditionalLandDrop`` MODE
      anywhere in the unit (Exploration, Azusa's "two additional lands", Kiora's
      one-shot loyalty grant, Sword of Forge and Frontier's equipment trigger —
      CR 305.2);
    * a ``GraveyardCastPermission`` MODE whose ``affected`` filter names Land
      (Crucible of Worlds, Ramunap Excavator, Hazezon's Desert-only variant,
      Zask/Yawgmoth's Agenda's "lands AND spells" conjunctions the legacy
      contiguous-phrase regex missed — beyond-legacy gains, CR 305.1);
    * a ``change_zone`` Graveyard→Battlefield effect naming Land (Splendid
      Reclamation, Titania; also catches the "put" (not "return") and
      "their"/generic-graveyard phrasings the legacy verb-locked regex missed —
      Restore, Soul of Windgrace, Fall of the Thran, Waking the Trolls,
      Realmbreaker, Wreck and Rebuild, Planar Birth — beyond-legacy gains, CR
      305.4 / 400.7).

    The last-resort tail catches the pure-text residue: The Lost and the
    Damned's compound OR-trigger (phase drops the Land branch's own filter
    onto a ``zone_change_clauses`` list whose clauses carry no type filter
    this arm reads — ``reads.trigger_zone_changes`` reads only their zones),
    Invader Parasite's "same name as the exiled card" comparison (an Unknown
    trigger mode phase's grammar cannot classify at all), and Werewolf
    Lightning Mage's Un-set Stickers gimmick (phase can't parse its {TK}
    placeholder text, but the raw oracle still literally says "Landfall —
    Whenever a land enters"). Scope "you" (forced, matching every arm above).
    """
    for unit in tree.units:
        if unit.trigger_event == "enters" and "Land" in trigger_subject(unit.node):
            return [Signal("landfall", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        for f in entered_this_turn_filters(unit.node):
            # None controller: the v0.32.0 entry-ledger shape scopes the
            # controller on the qty's own player field (the helper already
            # gates on it), leaving the filter's controller null.
            if "Land" in filter_core_types(f) and filter_controller(f) in (
                "You",
                None,
            ):
                return [Signal("landfall", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        for trig in iter_nested_trigger_defs(unit.node):
            if (
                getattr(trig, "mode", None) == "ChangesZone"
                and getattr(trig, "destination", None) == "Battlefield"
                and "Land" in trigger_subject(trig)
            ):
                return [Signal("landfall", "you", "", "", tree.name, "high")]
    if additional_land_play(tree):
        return [Signal("landfall", "you", "", "", tree.name, "high")]
    if any(plays_lands_from_graveyard(unit) for unit in tree.units):
        return [Signal("landfall", "you", "", "", tree.name, "high")]
    for c in tree.effect_concepts("change_zone"):
        origin, dest = change_zone_dirs(c.node)
        if origin == "Graveyard" and dest == "Battlefield" and "Land" in c.subject:
            return [Signal("landfall", "you", "", "", tree.name, "high")]
    for cl in _landfall_clauses(tree):
        if _LANDFALL_ETB_WORD_RX.search(cl) or _LANDFALL_GY_RETURN_WORD_RX.search(cl):
            return [Signal("landfall", "you", "", "", tree.name, "high")]
    return []


LANES = (
    _win_lose_game,
    _discard_makers,
    _spell_copy_makers,
    _token_maker,
    _draw_matters,
    _land_creatures_matter,
    _death_matters,
    _extra_turns,
    _lifegain_makers,
    _reanimator,
    _plus_one_makers,
    _pacify_makers,
    _single_target_neutralize,
    _type_changers,
    _chosen_type_matters,
    _damage_for_each,
    _keep_n_wrath,
    _spell_redirect,
    _direct_damage,
    _landfall,
)
