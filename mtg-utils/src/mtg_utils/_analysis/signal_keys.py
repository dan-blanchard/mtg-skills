"""Canonical signal-key constants shared by the detector and the exploitation map.

A signal ``key`` is a contract between ``signals.py`` (which emits ``Signal(key=...)``)
and ``signal_specs.py`` (which maps ``(key, scope)`` to an avenue spec). It used to live
as a bare magic string in both, so a typo on either side was a *silent* no-avenue. These
constants give the cross-file keys a compile-time handle — a typo dies as an
``AttributeError`` at import instead of vanishing — and the key-agreement gate at the
bottom of ``signal_specs.py`` asserts every detector-produced key resolves to a spec.

Each constant's VALUE is exactly the on-the-wire key (``Signal.key`` / ``SPECS`` tuple
key / the SPA's JSON), so this is runtime-identical to the strings it replaces. Leaf
module — stdlib only, no deck-forge imports — so both files import it cycle-free.
"""

from __future__ import annotations

from typing import Final

# Subject-bearing keys: emitted WITH a captured subject and resolved dynamically by
# signal_specs._subject_spec (no static SPECS entry). These are the clearest hand↔hand
# keys — named in both the detectors (signals.py) and the subject dispatch
# (signal_specs.py), so they earn constants.
TYPE_MATTERS: Final = "type_matters"
TOKEN_MAKER: Final = "token_maker"
TYPED_SPELLCAST: Final = "typed_spellcast"
KEYWORD_TRIBE: Final = "keyword_tribe"
# Meld (CR 701.42): the subject is THIS card's own name; the one partner that melds
# with it names this card in its meld text, so the per-subject serve finds exactly it.
MELD_PAIR: Final = "meld_pair"
# Mass creature-type changers (ADR-0040 / task #96, CR 613.1d layer 4). Subject
# "" = the chosen type, "all" = every creature type, "<Type>" = a fixed subtype
# (Hivestone). Zone reach is modeled as sibling keys (CR 109.2: a bare
# "creatures you control" static is battlefield-only; the "The same is true for
# creature spells you control…" rider reaches the stack/hand/library/graveyard):
# an all-zone changer emits all three, a graveyard-only changer (Ashes of the
# Fallen) the graveyard key alone.
TYPE_CHANGERS: Final = "type_changers"
TYPE_CHANGERS_ALL_ZONES: Final = "type_changers_all_zones"
TYPE_CHANGERS_GRAVEYARD: Final = "type_changers_graveyard"

# Board-count damage (task B-2): one-shot damage scaling with YOUR board —
# DealDamage whose amount is an ObjectCount over creatures (subject "") or a
# vocabulary subtype (subject "<Type>") you control. The count is resolved-on-
# application game information (CR 608.2h), so a wide board turns these into
# finishers; X-cost damage (announcement-fixed mana, CR 107.3b) stays out.
DAMAGE_FOR_EACH: Final = "damage_for_each"

# Cheat into play (a card put onto the battlefield without being cast): the
# subject is the cheated card TYPE ("Creature" / "Planeswalker" / "Artifact" /
# "Enchantment" / "Battle"), one signal per type the put admits — Jace,
# Multiverse Architect's "creature or planeswalker card" emits two. Subject ""
# is a put with no single type (a named tutor, "a permanent card"); it keeps
# the static spec (signal_specs.core._cheat_subject_spec builds the rest).
CHEAT_INTO_PLAY: Final = "cheat_into_play"

# Animation (lanes.animate_land_types): an effect that makes noncreature
# permanents of a card type creatures (CR 613.1d) — Bello, Bard of the Brambles,
# March of the Machines, Ensoul Artifact, Opalescence. The subject is the
# animated card TYPE ("Artifact" / "Enchantment" / "Planeswalker" / "Battle"),
# spelled as CHEAT_INTO_PLAY's is, plus the mana-value floor the animated set
# carries when it has one, spelled ``<Type>>=<N>`` (Bello's "mana value 4 or
# greater": ``Artifact>=4``) — :func:`animate_subject` / :func:`split_animate_
# subject` are the one spelling. "" is an animation of "a permanent" (no one
# type).
ANIMATE_MAKERS: Final = "animate_makers"
_FLOOR_SEP: Final = ">="
#: The card types an animation can name as its subject, in emit order: the
#: noncreature permanent types other than Land (a land made a creature is the
#: land-creatures lane's). The lane emits them; the spec layer's untyped
#: subject ("a permanent") feeds on all of them.
ANIMATE_SUBJECT_TYPES: Final = ("Artifact", "Enchantment", "Planeswalker", "Battle")


def animate_subject(card_type: str, floor: int | None = None) -> str:
    """An ``ANIMATE_MAKERS`` subject: the card type, with ``>=<floor>`` appended
    when the animated set has a mana-value floor."""
    return f"{card_type}{_FLOOR_SEP}{floor}" if card_type and floor else card_type


def split_animate_subject(subject: str) -> tuple[str, int | None]:
    """``(card type, mana-value floor or None)`` of an ``ANIMATE_MAKERS``
    subject — the inverse of :func:`animate_subject`. A subject only
    :func:`animate_subject` spells, so a malformed floor is a bug and raises
    ``ValueError``."""
    card_type, sep, floor = subject.partition(_FLOOR_SEP)
    if not sep:
        return card_type, None
    if not (card_type and floor.isdigit() and int(floor) > 0):
        msg = f"malformed {ANIMATE_MAKERS} subject: {subject!r}"
        raise ValueError(msg)
    return card_type, int(floor)


# Land-type payoffs (lanes.animate_land_types): a card that counts, watches or
# grants to lands of one nonbasic land type (CR 205.3i) — Yuma, Proud
# Protector's Deserts, Gatebreaker Ram's Gates. The subject is the land type.
LAND_TYPE_MATTERS: Final = "land_type_matters"

# Combat puppeteers (task B-5): cards that transfer the combat DECLARATION
# choices — attackers (CR 508.1a, normally the active player's) and blockers
# (CR 509.1a, normally the defending player's) — to YOU (Master Warcraft,
# Brutal Hordechief's activated arm). Distinct from goad (the controller
# still chooses how to attack) and forced attack/block without choice.
COMBAT_CHOICE_MAKERS: Final = "combat_choice_makers"

# Spell redirection doers (task B-4): ChangeTargets over a stack SPELL —
# changing the ORIGINAL's targets (CR 115.7a/b: Wild Ricochet, Deflecting
# Swat, Bolt Bend), split from the target_redirect PAYOFF key (Shapers'
# Sanctuary's becomes-target draw) per the counter_control doer/payoff
# precedent. Copy-with-new-targets retargets only the COPY (CR 707.10c) and
# stays spell_copy_makers.
SPELL_REDIRECT: Final = "spell_redirect"

# Wildcard tribal payoffs (task B-1): cards that choose a creature type as
# they enter (CR 614.12 — the as-enters replacement choice) and PAY OFF the
# chosen type (Door of Destinies, Herald's Horn). NOT a subject key — the
# subject is chosen at runtime, always emitted "" — but named here because
# signal_specs' per-subject tribal serves reference it cross-file (every
# tribe's serve credits the wildcard payoffs).
CHOSEN_TYPE_MATTERS: Final = "chosen_type_matters"

SUBJECT_KEYS: Final = frozenset(
    {
        TYPE_MATTERS,
        TOKEN_MAKER,
        TYPED_SPELLCAST,
        KEYWORD_TRIBE,
        MELD_PAIR,
        TYPE_CHANGERS,
        TYPE_CHANGERS_ALL_ZONES,
        TYPE_CHANGERS_GRAVEYARD,
        DAMAGE_FOR_EACH,
        CHEAT_INTO_PLAY,
        ANIMATE_MAKERS,
        LAND_TYPE_MATTERS,
    }
)

# The subject of the floor's voltron tells: the commander is a body to suit up and
# win with by commander damage (CR 903.10a) — what it IS, not a payoff of Equipment
# and Auras.
VOLTRON_CARRIER: Final = "carrier"

# The ``(key, subject)`` idents the membership floor writes on a payoff key: the
# deck WANTS the theme without being a theme card itself. Each opens its avenue
# (``signal_specs.core.avenue_spec_for``) though the theme's serve never pages it.
MEMBERSHIP_SUBJECTS: Final = frozenset(
    {
        # a creature commander that carries gear
        ("voltron_matters", VOLTRON_CARRIER),
    }
)

# Each extra-step maker key's payoff key: the "at the beginning of [step]"
# triggers an added step repeats (``card_advantage._extra_upkeep_end``). A trigger
# opens no avenue of its own (``signal_specs.core.avenue_spec_for``): hundreds of
# commanders carry one (Atraxa's end-step proliferate), and the steps are a theme
# only for a deck that adds them. Under that deck the triggers are the extra-step
# avenue's carers (``_tuner.metrics._CARES_ALIASES``).
STEP_TRIGGER_KEYS: Final = {
    "extra_upkeep": "upkeep_triggers",
    "extra_draw_step": "draw_step_triggers",
    "extra_end_step": "end_step_triggers",
}

# The ``(key, subject)`` idents a theme's page counts that open no avenue of their
# own (``signal_specs.core.avenue_spec_for``): a one-shot step of another card's
# engine. A reanimation spell or a bounce-your-own creature re-delivers a self-ETB
# card (the ``self_etb_payload`` page) without being a recast engine itself, and a
# deck with three of them is no recast deck; a land recursion keeps an animated
# land (the ``land_protection`` page). Each is a doer too (below).
PAGE_ONLY_SUBJECTS: Final = frozenset(
    {
        # a permanent card put from a graveyard onto the battlefield (Sun Titan)
        ("permanent_recast", "reanimate"),
        # a permanent you control returned to your hand (Whitemane Lion)
        ("permanent_recast", "replay"),
        # a land card returned from your graveyard, or played from it (Crucible)
        ("permanent_recast", "land"),
        # a token copy of the card itself (Embalm, Pack Rat): a token entering
        ("token_copy_makers", "self"),
        # a card put onto the battlefield face down (manifest, cloak)
        ("facedown_makers", "manifest"),
        # a card put onto the battlefield under your control (Rampant Growth)
        ("permanent_etb", "put"),
        # a permanent you control returned to hand to replay, a land included
        ("permanent_etb", "replay"),
        # a land you control returned to hand to pay for an untap (Quirion Ranger)
        ("permanent_etb", "land_untap"),
        # two or more creature tokens made at once (Battle Screech): the go-wide
        # pages' depth, no theme of its own
        ("mass_token_makers", ""),
        # a creature that may block more than one attacker (Wall of Glare): the
        # prevention deck's soak, no theme of its own
        ("extra_blockers", ""),
        ("extra_blockers", "any"),
        # a permanent's own downside (Sea Serpent, Demonic Taskmaster): what an
        # ability strip turns off or a donate deck hands over, no theme of its own
        ("self_drawback", "restriction"),
        ("self_drawback", "harm"),
        # a land that is or makes itself a creature (Mutavault, Dryad Arbor)
        ("land_creatures_matter", "self"),
    }
)

# The ``(key, subject)`` idents that mark the DOER side of a payoff key that is
# not a subject key: each feeds the payoff, and the theme's serve counts it as
# depth, without caring about the theme (``_tuner.metrics.focus``'s carer read
# skips them).
DOER_SUBJECTS: Final = frozenset(
    {
        # an artifact-token maker (Thopters, Servos)
        ("artifacts_matter", "token"),
        # an enchantment-token maker (Roles, Shards)
        ("enchantments_matter", "token"),
        # a variable-target spell
        ("per_target_payoff", "variable"),
        # a can't-lose card
        ("life_payment_insurance", "cant_lose"),
        # a commander-to-hand effect
        ("lose_unless_hand", "command_to_hand"),
        # an enters-trigger silencer
        ("lose_unless_hand", "etb_silencer"),
        # a free activation that targets your own permanent
        ("target_own_payoff", "free_target"),
        # an extra draw at the beginning of your draw step
        ("draw_matters", "draw_step"),
        # a blink enabler
        ("blink_flicker", "enabler"),
        # a haste-for-activations grant or an activation-cost reducer
        ("activated_ability", "enabler"),
        # one-shot land destruction; the floor's repeatable LD is the carer
        ("land_destruction", "destroy"),
        ("land_destruction", "exile"),
        ("land_destruction", "bounce"),
        ("land_destruction", "tuck"),
        ("land_destruction", "sacrifice"),
        # an edict on a targeted player (Diabolic Edict): the crime it commits
        ("edict_makers", "target"),
        # a creature that sacrifices itself (Sakura-Tribe Elder): loop fuel
        ("sacrifice_outlets", "self"),
        # the page-only doers (above)
        *PAGE_ONLY_SUBJECTS,
    }
)
