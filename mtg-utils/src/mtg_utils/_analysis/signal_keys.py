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

import enum
from collections.abc import Mapping
from types import MappingProxyType
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

# The subject of the floor's artifact membership: the card IS an artifact (a card
# type, CR 205.2a), which the Artifacts theme counts by its type, not a card that cares
# about artifacts. Under its own subject an artifact commander still opens the
# avenue, but the payoff page's ``artifacts_matter|you|*`` never takes Sol Ring.
ARTIFACT_MEMBER: Final = "member"

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

# The keys only a theme's page reads, with no spec of their own: ``subtype_ref``
# (the subtypes a card's filters name — a tribe's pages read it per tribe),
# ``keyword_bodies`` (the keywords a card puts on bodies of yours — a keyword
# tribe's page reads it per keyword) and ``land_return_untap`` (a land you control
# returned to its owner's hand pays for an untap — Quirion Ranger, the
# land-animation page's untap engines). None opens an avenue
# (``signal_specs.core.spec_for`` has none to give), and the key-agreement gate
# leaves them out.
PAGE_ONLY_KEYS: Final = frozenset(
    {"subtype_ref", "keyword_bodies", "land_return_untap"}
)


class SubjectRole(enum.Enum):
    """What a subject on a key that is no subject key says about its signal
    (:data:`SUBJECT_ROLES`)."""

    #: The membership floor's subject on a payoff key: the deck WANTS the theme
    #: without being a theme card itself. It opens its avenue
    #: (``signal_specs.core.avenue_spec_for``), but no ``key|scope|*`` wildcard
    #: counts it (:func:`wildcard_counts`): the theme's page never takes it as a
    #: payoff (Sol Ring's ``artifacts_matter|you|member``).
    MEMBERSHIP = "membership"
    #: The DOER side of a payoff key: it feeds the payoff, and the theme's serve
    #: counts it as depth, without caring about the theme
    #: (``_tuner.metrics.focus``'s carer read and ``ranking``'s clause role skip
    #: it).
    DOER = "doer"
    #: A doer only a theme's page counts: a one-shot step of another card's
    #: engine, which opens no avenue — or plan — of its own (:func:`is_page_only`).
    PAGE_ONLY = "page_only"


# Every ``(key, subject)`` with a role, the one table the role sets below, the serve
# and preset wildcards (:func:`wildcard_counts`), ``avenue_spec_for`` and the voltron
# floor's plan read take their answers from.
SUBJECT_ROLES: Final[Mapping[tuple[str, str], SubjectRole]] = MappingProxyType(
    {
        # ── membership: what the card IS ──
        # a creature commander that carries gear
        ("voltron_matters", VOLTRON_CARRIER): SubjectRole.MEMBERSHIP,
        # an artifact (an artifact commander)
        ("artifacts_matter", ARTIFACT_MEMBER): SubjectRole.MEMBERSHIP,
        # ── doers ──
        # an artifact-token maker (Thopters, Servos)
        ("artifacts_matter", "token"): SubjectRole.DOER,
        # an enchantment-token maker (Roles, Shards)
        ("enchantments_matter", "token"): SubjectRole.DOER,
        # an Aura that can go on a creature, yours or an opponent's
        ("aura_matters", "aura"): SubjectRole.DOER,
        # a variable-target spell
        ("per_target_payoff", "variable"): SubjectRole.DOER,
        # a can't-lose card
        ("life_payment_insurance", "cant_lose"): SubjectRole.DOER,
        # a commander-to-hand effect
        ("lose_unless_hand", "command_to_hand"): SubjectRole.DOER,
        # an enters-trigger silencer
        ("lose_unless_hand", "etb_silencer"): SubjectRole.DOER,
        # a free activation that targets your own permanent
        ("target_own_payoff", "free_target"): SubjectRole.DOER,
        # an extra draw at the beginning of your draw step
        ("draw_matters", "draw_step"): SubjectRole.DOER,
        # a blink enabler
        ("blink_flicker", "enabler"): SubjectRole.DOER,
        # a haste-for-activations grant or an activation-cost reducer
        ("activated_ability", "enabler"): SubjectRole.DOER,
        # one-shot land destruction; the floor's repeatable LD is the carer
        ("land_destruction", "destroy"): SubjectRole.DOER,
        ("land_destruction", "exile"): SubjectRole.DOER,
        ("land_destruction", "bounce"): SubjectRole.DOER,
        ("land_destruction", "tuck"): SubjectRole.DOER,
        ("land_destruction", "sacrifice"): SubjectRole.DOER,
        # an edict on a targeted player (Diabolic Edict): the crime it commits
        ("edict_makers", "target"): SubjectRole.DOER,
        # a creature that sacrifices itself (Sakura-Tribe Elder): loop fuel
        ("sacrifice_outlets", "self"): SubjectRole.DOER,
        # ── page-only doers: a theme's page counts them, no avenue opens. A
        # reanimation spell or a bounce-your-own creature re-delivers a self-ETB
        # card (the ``self_etb_payload`` page) without being a recast engine itself,
        # and a deck with three of them is no recast deck; a land recursion keeps
        # an animated land (the ``land_protection`` page). ──
        # a permanent card put from a graveyard onto the battlefield (Sun Titan)
        ("permanent_recast", "reanimate"): SubjectRole.PAGE_ONLY,
        # a permanent you control returned to your hand (Whitemane Lion)
        ("permanent_recast", "replay"): SubjectRole.PAGE_ONLY,
        # a land card returned from your graveyard, or played from it (Crucible)
        ("permanent_recast", "land"): SubjectRole.PAGE_ONLY,
        # a token copy of the card itself (Embalm, Pack Rat): a token entering
        ("token_copy_makers", "self"): SubjectRole.PAGE_ONLY,
        # a card put onto the battlefield face down (manifest, cloak)
        ("facedown_makers", "manifest"): SubjectRole.PAGE_ONLY,
        # a card put onto the battlefield under your control (Rampant Growth)
        ("permanent_etb", "put"): SubjectRole.PAGE_ONLY,
        # a permanent you control returned to hand to replay, a land included
        ("permanent_etb", "replay"): SubjectRole.PAGE_ONLY,
        # two or more creature tokens made at once (Battle Screech): the go-wide
        # pages' depth, no theme of its own
        ("mass_token_makers", ""): SubjectRole.PAGE_ONLY,
        # a creature that may block more than one attacker (Wall of Glare): the
        # prevention deck's soak, no theme of its own
        ("extra_blockers", ""): SubjectRole.PAGE_ONLY,
        ("extra_blockers", "any"): SubjectRole.PAGE_ONLY,
        # a permanent's own downside (Sea Serpent, Demonic Taskmaster): what an
        # ability strip turns off or a donate deck hands over, no theme of its own
        ("self_drawback", "restriction"): SubjectRole.PAGE_ONLY,
        ("self_drawback", "harm"): SubjectRole.PAGE_ONLY,
        # a land that is or makes itself a creature (Mutavault, Dryad Arbor)
        ("land_creatures_matter", "self"): SubjectRole.PAGE_ONLY,
    }
)


def subject_role(key: str, subject: str) -> SubjectRole | None:
    """The role :data:`SUBJECT_ROLES` gives ``(key, subject)``, or ``None``."""
    return SUBJECT_ROLES.get((key, subject))


def _with_role(*roles: SubjectRole) -> frozenset[tuple[str, str]]:
    return frozenset(ks for ks, role in SUBJECT_ROLES.items() if role in roles)


#: The membership floor's ``(key, subject)`` idents (:attr:`SubjectRole.MEMBERSHIP`).
MEMBERSHIP_SUBJECTS: Final = _with_role(SubjectRole.MEMBERSHIP)
#: The page-only doers (:attr:`SubjectRole.PAGE_ONLY`).
PAGE_ONLY_SUBJECTS: Final = _with_role(SubjectRole.PAGE_ONLY)
#: Every doer, the page-only doers among them: a page-only doer feeds a payoff too.
DOER_SUBJECTS: Final = _with_role(SubjectRole.DOER, SubjectRole.PAGE_ONLY)


def wildcard_counts(key: str, subject: str) -> bool:
    """Whether a ``key|scope|*`` wildcard — a serve's, a preset's, a pair read's —
    counts a signal of ``(key, subject)``: every subject but a membership one,
    what a card IS rather than what it does (:attr:`SubjectRole.MEMBERSHIP`)."""
    return subject_role(key, subject) is not SubjectRole.MEMBERSHIP


def is_page_only(key: str, subject: str) -> bool:
    """Whether a signal only feeds a theme's page and opens no avenue — or plan
    — of its own: a page-only key (:data:`PAGE_ONLY_KEYS`) or a page-only doer
    (:attr:`SubjectRole.PAGE_ONLY`)."""
    return key in PAGE_ONLY_KEYS or subject_role(key, subject) is SubjectRole.PAGE_ONLY
