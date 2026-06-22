"""Card IR signal detection — the ADR-0027 structural path.

``extract_signals_ir`` derives ``Signal`` facts from the structured Card IR
(phase-rs projection) instead of oracle-text regexes, plus its IR data tables
(``_DOER_EFFECT_KEYS`` / ``_PAYOFF_TRIGGER_KEYS`` / ``_IR_KEYWORD_MAP`` /
``_IR_KEPT_DETECTORS`` / ``_IR_FLOOR_LANES`` / ``IR_SLICE_KEYS``) and helpers.
Imports shared parsing primitives from :mod:`_signals_regex` (one-directional).
Split out of ``signals.py`` (behavior-neutral, 2026-06-21).

NOTE (floor-disable seam): the no-flood floor gate lives here as
``_IR_FLOOR_LANES``. To disable it in a harness, monkeypatch
``_signals_ir._IR_FLOOR_LANES = frozenset()`` (NOT ``signals._IR_FLOOR_LANES`` —
that re-export binding no longer reaches the reader after the split).
"""

from __future__ import annotations

import re

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._signals_regex import (
    _DIRECT_KEYWORD_SIGNALS,
    _EVERGREEN_CK,
    _FLOOR_DETECTORS,
    _IMPULSE_TOP_PLAY_SWEEP_RE,
    _PRESET_KEYWORD_SIGNALS,
    _SELF_BLINK_SWEEP_RE,
    _XSPELL_HOOK_RE,
    _XSPELL_VETO_RE,
    Signal,
    _clauses,
    _detect_direct_keywords,
    _detect_keyword_presets,
    _detect_self_blink_fulltext,
    _detect_voltron_payoff_ir,
    _resolve_subject,
    _type_hoser_clause,
    self_power_scale_match,
)
from mtg_utils._deck_forge._subtypes import (
    CLASS_TRIBES,
    CREATURE_SUBTYPES,
    TRIBAL_SUBTYPES,
)
from mtg_utils._deck_forge._sweep_detectors import (
    ABILITY_COPY_REGEX,
    COLOR_CHANGE_REGEX,
    COMBAT_DAMAGE_TO_CREATURE_REGEX,
    COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX,
    COMBAT_DAMAGE_TO_OPP_REGEX,
    CREATURE_PING_REGEX,
    DAMAGE_EQUAL_POWER_REGEX,
    DAMAGE_TO_OPP_MATTERS_REGEX,
    DEBUFF_MAHA_REGEX,
    DEBUFF_SWEEP_REGEX,
    GAIN_CONTROL_REGEX,
    KEYWORD_COUNTER_REGEX,
    KEYWORD_GRANT_TARGET_REGEX,
    LTB_MATTERS_SWEEP_REGEX,
    NONCREATURE_CAST_PUNISH_REGEX,
    PUMP_MATTERS_REGEX,
    TOKEN_COPY_MATTERS_REGEX,
    TOUGHNESS_COMBAT_REGEX,
    TRIBE_DAMAGE_TRIGGER_REGEX,
)
from mtg_utils.card_classify import get_oracle_text, is_creature
from mtg_utils.card_ir import Card, Condition, Effect, Filter, Quantity

# ── IR-backed signal extraction (Milestone A2 — 5-key vertical slice) ──────────
# extract_signals_ir derives the same Signal(key, scope, subject, …) from the
# structured Card IR instead of regexes, so the two paths can be diffed and the IR
# eventually replaces the regex bag (A4). The slice covers five keys spanning the
# hard axes: a scaling lane (creatures_matter), a payoff lane (lifegain_matters), a
# scoped lane (graveyard_matters), a subject-bearing lane (token_maker), and a
# trigger lane (death_matters). Fan-out to the full vocabulary follows.
# Batch 2b — effect.category → (signal key, fixed scope | None). The CROSSWALK
# "doer" set: a card that DOES X (makes the resource), keyed off the effect.
# None scope = derive from the effect's own scope.
_DOER_EFFECT_KEYS: dict[str, tuple[str, str | None]] = {
    # ADR-0027: untap is NOT a blanket doer — every "untap it/that/this" incidental
    # untap (Act of Treason's threaten, Abduction's enchant, Amulet of Vigor) and the
    # "doesn't untap" INVERSION (Basalt Monolith) fired untap_engine through the doer
    # loop. The lane wants a deliberate untap ENGINE (untap target/all/each — Seedborn
    # Muse, Kiora), so it now fires from a GATED arm (cat=="untap" + _UNTAP_ENGINE_RAW
    # or a mass untap) instead of this entry. See extract_signals_ir.
    "proliferate": ("proliferate_matters", "you"),
    "topdeck_select": ("topdeck_selection", "you"),
    # ADR-0027: gain_control is NOT a blanket doer — the blanket fire mislabeled DONATE
    # (you give your own permanent away — Donate, Bazaar Trader) and RETURN-CONTROL
    # resets (Brooding Saurian) as theft. gain_control now fires from a GATED arm
    # (cat=="gain_control", excluding donate + Owned-subject return) in
    # extract_signals_ir.
    "mill": ("mill_matters", "any"),
    "tutor": ("tutor_matters", "you"),
    # Batch P — phase-native mechanic effects.
    "monarch": ("monarch_matters", "you"),
    "suspect": ("suspect_matters", "you"),
    "speed": ("speed_matters", "you"),
    "station": ("station_matters", "you"),
    "venture": ("venture_matters", "you"),
    "connive": ("connive_matters", "you"),
    "damage_prevention": ("damage_prevention", "you"),
    "detain": ("tap_down", "opponents"),
    "seek": ("seek_matters", "you"),  # Alchemy Seek (DD3) — phase parses it
    # Batch 0 — v0.1.60 effect types newly projected (see project.py _EFFECT_CATEGORY).
    "coin_flip": ("coin_flip", "you"),
    "end_the_turn": ("end_the_turn", "you"),
    "extra_turn": ("extra_turns", "you"),
    "set_life": ("life_total_set", "any"),  # scope-agnostic build-around marker
    # reveal_hand → hand_disruption is scope-GATED below (only an opponent-reveal is
    # disruption; "reveal cards in your hand" is a self-reveal, scope "any").
    "regenerate": ("regenerate_matters", "you"),
    # Face-down 2/2 mechanics (CR 701.40 manifest / 701.58 cloak / 708) and the
    # turn-face-up payoff all feed the existing facedown_matters lane — manifest is
    # NOT a token_maker (CR 122.1), so it no longer pollutes that lane.
    "manifest": ("facedown_matters", "you"),
    "cloak": ("facedown_matters", "you"),
    "turn_face_up": ("facedown_matters", "you"),
    "ring_tempt": ("ring_matters", "you"),
    # Explore (CR 701.44) → its dedicated lane (was topdeck_select, but explore is a
    # reveal-top + land/counter mechanic, not a Brainstorm-style stacker).
    "explore": ("explore_matters", "you"),
    "energy": ("energy_matters", "you"),
    # Player-counter givers (GivePlayerCounter, split by kind in project.py — CR
    # 122.1). poison/rad land on opponents (a kill clock / penalty); experience is
    # a personal resource. ticket/unknown player counters stay lane-less (niche).
    "poison": ("poison_matters", "opponents"),
    "experience_counter": ("experience_matters", "you"),
    "rad_counter": ("rad_counter_matters", "opponents"),
    "phasing": ("phasing_matters", "you"),
    # ADR-0027 restriction-narrow markers (project._narrow_mechanic_refs): a
    # "becomes saddled"/"you saddle" grant (CR 702.171) and a "paired with a
    # creature with soulbond" reference (CR 702.95) phase folds into a generic
    # carrier are appended as precise saddle/soulbond marker effects → their lanes.
    "saddle": ("saddle_matters", "you"),
    "soulbond": ("soulbond_matters", "you"),
    # ADR-0027 trigger-other raw-markers (project._narrow_trigger_other_refs): a
    # named-mechanic PAYOFF trigger phase flattened to event='other', surviving only
    # in the effect raw, is appended as a precise marker effect → its lane. coin_flip
    # / ring_tempt / explore are already mapped above (their effect categories were
    # already read); these are the remaining payoff anchors. discover/ninjutsu reach
    # A-B==0 and migrate; boast/exhaust/scry_surveil close their event='other' tail
    # but a static-grant / delayed-trigger / scry-replacement remainder keeps them on
    # regex (see ADR-0027). CR 701.57 discover, 702.49 ninjutsu, 702.142 boast,
    # 702.177 exhaust, 701.22/701.25 scry/surveil.
    "discover": ("discover_matters", "you"),
    "ninjutsu": ("ninjutsu_matters", "you"),
    "boast": ("boast_matters", "you"),
    "exhaust": ("exhaust_matters", "you"),
    "scry_surveil": ("scry_surveil_matters", "you"),
    # ADR-0027 conferred-keyword re-parse markers (project._narrow_conferred_keyword
    # _refs): a keyword GRANTED to a class of objects (affinity for X / has madness /
    # has foretell), surviving only in a grant carrier's raw, is appended as a precise
    # marker effect → its lane. The card's OWN printed keyword still rides the Scryfall
    # keyword array (_IR_KEYWORD_MAP); these markers add the keyword-LESS conferred
    # granters. CR 702.41 affinity, 702.35 madness, 702.143 foretell. (devour / connive
    # / counter_spell / evasion_denial / damage_reflect markers are read elsewhere —
    # devour's multi-lane fan-out, connive above, counter_spell/evasion_denial/
    # damage_reflect their own per-effect reads.)
    "affinity": ("affinity_type", "you"),
    "madness": ("madness_matters", "you"),
    "foretell": ("foretell_matters", "you"),
    # ADR-0027 keyword-conditioned payoff markers (project._narrow_payoff_condition
    # _refs) + dropped-static face markers (project._dropped_static_markers): a
    # mutate cast-payoff / scavenge graveyard-grant phase left only in a non-grant
    # carrier raw or dropped entirely (surviving on the face oracle text) is appended
    # as a precise marker effect → its lane. The keyword-bearing makers ride the
    # Scryfall keyword array (_IR_KEYWORD_MAP); these add the keyword-LESS payoff /
    # granter residual. CR 702.139 mutate, 702.97 scavenge.
    "mutate": ("mutate_matters", "you"),
    "scavenge": ("scavenge_fuel", "you"),
    # ADR-0027 condition-form crime marker (project._dropped_static_markers): a
    # "(if|as long as) you've committed a crime this turn" payoff phase has no
    # condition kind for. The TRIGGER form ("Whenever you commit a crime") rides
    # phase's commit_crime trigger event (_PAYOFF_TRIGGER_KEYS); this is the
    # keyword-less condition-form payoff half (CR 701.49).
    "crime": ("crimes_matter", "you"),
    # ADR-0027 repeatable-pay-life marker (project._dropped_static_markers): a
    # "Pay N life:" activated-ability cost phase misparses (Arco-Flagellant,
    # Hibernation Sliver) or drops inside a conferred quoted ability (Underworld
    # Connections, the volvers). The structural paylife COST rides "paylife" in
    # cost_parts below; this is the misparse/conferred-ability residual (CR 118).
    "life_payment": ("life_payment_insurance", "you"),
    "roll_die": ("dice_matters", "you"),
    "dig_until": ("dig_until", "you"),
    # ADR-0027 sweep markers (project._dropped_static_markers / _narrow_trigger_other
    # _refs): a payoff/reference phase left only on the face oracle text or in an
    # event='other' carrier raw is appended as a precise marker effect → its lane.
    # starting_life ← "starting life total" compare (CR 103.4); mass_death ←
    # "creatures that died this turn" count operand (CR 700.4); cycling ← a
    # "cycle or discard" payoff trigger (CR 702.29). roll_die above already maps the
    # dice marker (same category as phase's native roll_die effect).
    "starting_life": ("starting_life_matters", "you"),
    "mass_death": ("mass_death_payoff", "you"),
    "cycling_payoff": ("cycling_matters", "you"),
    # ADR-0027 sweep batch 2 conferred/dropped-static markers — the keyword-less
    # granter / anthem / reference phase folds into a carrier raw or drops onto the
    # face oracle. The card's OWN printed cascade/undying/persist/changeling rides the
    # Scryfall keyword array (_IR_KEYWORD_MAP); these add the keyword-LESS form.
    "cascade": ("cascade_matters", "you"),
    "undying_persist": ("undying_persist_matters", "you"),
    "changeling": ("changeling_matters", "you"),
    # creature_cast ← the face-only-drop creature-cast reference (Blink's quoted token
    # ability, Glimpse of Nature's delayed trigger); scope "any" mirrors the regex.
    "creature_cast": ("creature_cast_trigger", "any"),
    # saga ← a lore-counter manipulation/payoff face reference (the chapter-advancement
    # build-around; a vanilla Saga's own reminder-only lore mention doesn't fire).
    "saga": ("saga_matters", "you"),
    # Batch 14 — extra-phase / type-change / mass-goad effect categories.
    "extra_combat": ("extra_combats", "you"),
    "extra_upkeep": ("extra_upkeep", "you"),
    "extra_draw": ("extra_draw_step", "you"),
    "extra_end": ("extra_end_step", "you"),
    "goad_all": ("goad_matters", "opponents"),
    "counter_move": ("counter_move", "you"),  # Batch 7 — MoveCounters effect
    # DEFERRED: type_change — SetCardTypes is kept as accurate IR but the lane
    # fires 0 in commander-legal (the regex's 25 are mostly static "is also a..."
    # which phase models differently); the lane waits for that shape.
    # clone_matters + per-type copy lanes are wired in extract_signals_ir from the
    # BecomeCopy "clone" category's COPIED type (creature-only for clone_matters;
    # the broad regex's token/spell-copy belong to their own lanes).
    # topdeck_stack is wired in extract_signals_ir (not here): _library_position_
    # effect now carries the WHERE (top/bottom/nth) in counter_kind, and the lane
    # fires only on a top-ish position with YOUR moved cards (excludes Bottom puts +
    # bounce-to-top removal). Resolves the deferred +421 flood.
    # NB: place_counter -> counters_matter is deferred until the projection
    # captures counter KIND (+1/+1 vs loyalty/charge/oil) — firing on every
    # counter placement floods the lane (planeswalkers, one-off charge counters).
    # direct_damage is special-cased below (doer scope "you", offensive only).
}

# Batch 2c — trigger.event → (signal key, fixed scope | None). The CROSSWALK
# "payoff" set: a card that CARES when X happens, keyed off the trigger.
_PAYOFF_TRIGGER_KEYS: dict[str, tuple[str, str | None]] = {
    "cast_spell": ("spellcast_matters", "you"),
    # ADR-0027 β — `combat_damage` is INTENTIONALLY absent: it used to map to
    # combat_damage_to_opp here, but that fired UNCONDITIONALLY on every
    # combat_damage trigger, including the "deals combat damage to a CREATURE"
    # recipient (Ohran Viper's destroy-at-end-of-combat trigger). phase drops
    # valid_target's recipient TYPE onto the Trigger, so the structural payoff
    # arm cannot tell creature- from player-recipient; combat_damage_to_opp
    # (player recipient) and combat_damage_to_creature (creature recipient) are
    # both served by the byte-identical _IR_KEPT_DETECTORS mirrors below
    # (anchored on "to a player/opponent" vs "to a creature"), which DO
    # discriminate. combat_damage_matters (the base lane, NOT migrated) still
    # fires from the unconditional `ev in ("combat_damage","deals_damage")` arm.
    "attacks": ("attack_matters", "you"),
    "counter_added": ("counters_matter", "you"),
    # Batch 1 — payoff trigger events newly projected in _trigger_event.
    "commit_crime": ("crimes_matter", "you"),
    "scried": ("scry_surveil_matters", "you"),
    "surveiled": ("scry_surveil_matters", "you"),
    # cycled → cycling_matters is scope-GATED below (a SelfRef "when you cycle THIS"
    # bonus is scope "you" and not a cycling-theme payoff). excess_damage DEFERRED:
    # the ExcessDamageAll trigger covers only 4 cards (the regex lane is ~28, mostly
    # trample-excess) — the event mapping stays for accurate IR, but no lane yet.
}

# Batch K — Scryfall keyword (lowercased) → the signal keys it fires. A clean
# structured-field lookup (card["keywords"]), NOT oracle regex, so it survives
# into the IR-native world. One keyword may open several lanes; several keywords
# may open one (poison ← infect/toxic/poisonous; evasion ← menace/fear/…).
_IR_KEYWORD_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    "boast": (("boast_matters", "you"),),
    "cascade": (("cascade_matters", "you"),),
    # Casualty (CR 702.153) sacrifices a creature as a cost to copy the spell — the
    # printed KEYWORD is the structural anchor for the sac cost phase folds into the
    # Casualty parse (no sacrifice Effect / cost token survives). Mirrors the regex
    # `\bcasualty\b` → sacrifice_matters. It ALSO copies the spell, so it opens
    # spell_copy_matters too (ADR-0027). The GRANTER (Anhelo — "has casualty 2") is
    # keyword-less and is recovered by a cast_with_keyword raw marker below.
    "casualty": (("sacrifice_matters", "you"), ("spell_copy_matters", "you")),
    "changeling": (("changeling_matters", "you"),),
    "companion": (("companion_keyword", "you"),),
    # Connive (CR 701.50) as the printed KEYWORD — covers the keyword-LESS GRANTER
    # (Security Bypass's Aura grants the enchanted creature "it connives", which
    # phase swallows into the Enchant parse so no connive effect is emitted). The
    # native connive EFFECT already covers self-conniving cards via _DOER_EFFECT_KEYS;
    # Scryfall tags the granter with the keyword too, so this lifts it cleanly.
    "connive": (("connive_matters", "you"),),
    "convoke": (("convoke_matters", "you"),),
    # Devour (CR 702.82) enters with +1/+1 counters per sacrificed creature — a
    # definitional +1/+1 source, so the printed keyword opens counters_matter too
    # (mirrors the `devour` EFFECT-category fan-out; covers Preyseizer Dragon, whose
    # devour rides the keyword + a board_count, not a `devour` effect). CR 122.1.
    "devour": (("devour_matters", "you"), ("counters_matter", "any")),
    "discover": (("discover_matters", "you"),),
    # Explore (CR 701.44) as the printed KEYWORD — the Scryfall-authoritative path
    # covers explore cards whose explore lives in a granted ability / replacement
    # clause / Map-token grant (Topography Tracker, Glowcap Lantern, Get Lost, …)
    # and so emit NO explore EFFECT node. The explore EFFECT category (doers + the
    # event='other' payoff trigger) opens it via _DOER_EFFECT_KEYS; this opens it
    # from the keyword the card actually carries (53 ⊇ the 44 regex hits).
    "explore": (("explore_matters", "you"),),
    "foretell": (("foretell_matters", "you"),),
    "madness": (("madness_matters", "you"),),
    # ADR-0027 counters_matter migration: the +1/+1-counter keyword block MOVED here
    # from _DIRECT_KEYWORD_SIGNALS (the shared regex/IR keyword path). counters_matter
    # is migrated, so it must leave the regex-readable _DIRECT_KEYWORD_SIGNALS; but the
    # IR path STILL needs the keyword for cards whose place_counter phase emits with a
    # blank counter_kind + a reminder-stripped raw (no "+1/+1" in the structural text —
    # Anafenza Kin-Tree's bolster, Goblin Glory Chaser's renown, Pteramander's adapt),
    # which the structural place_counter→counters_matter edge misses. _IR_KEYWORD_MAP
    # is IR-only (extract_signals doesn't read it), so this is the saddle-style move.
    # Each is definitionally a +1/+1-counter mechanic (CR 702.x). devour is mapped
    # above (it also sacs).
    # (scavenge and undying are mapped lower in this dict — counters_matter is merged
    # into their existing entries there to avoid a duplicate key.)
    "mentor": (("counters_matter", "any"),),
    "training": (("counters_matter", "any"),),
    "modular": (("counters_matter", "any"),),
    "bolster": (("counters_matter", "any"),),
    "evolve": (("counters_matter", "any"),),
    "outlast": (("counters_matter", "any"),),
    "renown": (("counters_matter", "any"),),
    "adapt": (("counters_matter", "any"),),
    "dethrone": (("counters_matter", "any"),),
    "graft": (("counters_matter", "any"),),
    "riot": (("counters_matter", "any"),),
    "bloodthirst": (("counters_matter", "any"),),
    "fabricate": (("counters_matter", "any"),),
    "sunburst": (("counters_matter", "any"),),
    "tribute": (("counters_matter", "any"),),
    "unleash": (("counters_matter", "any"),),
    "ravenous": (("counters_matter", "any"),),
    "reinforce": (("counters_matter", "any"),),
    # Phasing (CR 702.26) as the printed KEYWORD — Teferi's Imp, Ertai's Familiar,
    # and reminder-only phasers (Sandbar Crocodile) whose only "phases out" sits in
    # the stripped reminder text the regex floor misses. The phasing EFFECT category
    # (phase-out/in actions, project._narrow_mechanic_refs) opens the lane via
    # _DOER_EFFECT_KEYS; this opens it from the keyword the card actually carries.
    "phasing": (("phasing_matters", "you"),),
    # Graveyard-cast + graveyard-payoff keyword family — a card with any of these
    # uses ITS OWN / your graveyard as a resource (cast-from-GY: flashback/escape/
    # disturb/embalm/eternalize/encore/aftermath/retrace/jump-start/recover/unearth;
    # GY-payoff: dredge/delve/scavenge), so it cares about graveyards (scope you).
    # NOT graveyard HATE (exile from an opponent's GY) — that's a different lane.
    "flashback": (("graveyard_matters", "you"),),
    "escape": (("graveyard_matters", "you"),),
    "disturb": (("graveyard_matters", "you"),),
    "embalm": (("graveyard_matters", "you"),),
    "eternalize": (("graveyard_matters", "you"),),
    "encore": (("graveyard_matters", "you"),),
    "aftermath": (("graveyard_matters", "you"),),
    "retrace": (("graveyard_matters", "you"),),
    "jump-start": (("graveyard_matters", "you"),),
    "recover": (("graveyard_matters", "you"),),
    "unearth": (("graveyard_matters", "you"),),
    "dredge": (("graveyard_matters", "you"),),
    "delve": (("graveyard_matters", "you"),),
    "mutate": (("mutate_matters", "you"),),
    "myriad": (("myriad_grant", "you"),),
    "ninjutsu": (("ninjutsu_matters", "you"),),
    "commander ninjutsu": (("ninjutsu_matters", "you"),),
    # Sneak (the TMNT/Marvel ninjutsu-on-a-spell variant — Karai's Technique, Elektra,
    # New Generation's Technique) — the bounce-replay engine that recasts a cheap
    # creature to re-fire its ETB. ADR-0027: the Scryfall `sneak` keyword (28 cards)
    # is the structured detector for recast_etb, dropping the four `\bsneak\b`-regex
    # over-fires (Cheatyface, Lightfoot Rogue, etc.). Ninjutsu proper is the distinct
    # ninjutsu_matters lane above, so recast_etb keys on Sneak specifically.
    # ADR-0027 t2b4a-B: Sneak ALSO anchors the alt_cost_keyword lane (it pays an
    # alternative cost), alongside web-slinging and mayhem below — all three are
    # Scryfall keyword abilities that carry the alternative-cost ability, so the
    # keyword-array membership is exact (no over-fire vs the old `\bsneak\b`-style
    # regex, which risked reminder/flavor false positives). CR 118.9.
    "sneak": (("recast_etb", "you"), ("alt_cost_keyword", "you")),
    # web-slinging (Marvel) / mayhem (alt-cast-from-graveyard) — the other two
    # alternative-cost Scryfall keywords. Spellings match the lowercased Scryfall
    # array ("Web-slinging", "Mayhem"). ADR-0027 t2b4a-B.
    "web-slinging": (("alt_cost_keyword", "you"),),
    "mayhem": (("alt_cost_keyword", "you"),),
    # Partner family (CR 702.124 partner / partner with, 702.123 background,
    # Doctor's companion, Friends forever) — a commander built around a SECOND
    # commander wants the partner-card pool (drives the color-widening avenue,
    # ADR-0019). ADR-0027 t2b4a-B: the Scryfall keyword array carries the whole
    # family cleanly and is MORE precise than the old regex, which over-fired on
    # card-name self-references with a comma ("Lava, Axe", "Gather, the Townsfolk")
    # via its `\bpartner\b`/"friend" arms. Scryfall truncates "Friends forever" to
    # the keyword "Friends". `companion` is the SEPARATE companion_keyword lane (a
    # deckbuild constraint, not partner) — deliberately NOT mapped here.
    "partner": (("partner_background", "you"),),
    "partner with": (("partner_background", "you"),),
    "choose a background": (("partner_background", "you"),),
    "doctor's companion": (("partner_background", "you"),),
    "friends": (("partner_background", "you"),),
    "infect": (("poison_matters", "opponents"),),
    "toxic": (("poison_matters", "opponents"),),
    "poisonous": (("poison_matters", "opponents"),),
    # Saddle (CR 702.171) — moved here from _DIRECT_KEYWORD_SIGNALS for the ADR-0027
    # migration so the keyword detection lives on the IR-only path (the regex
    # `extract_signals` must no longer emit a migrated key); the `saddle` effect
    # marker (project._narrow_mechanic_refs → _DOER_EFFECT_KEYS) covers the
    # keyword-less "becomes saddled" granters.
    "saddle": (("saddle_matters", "you"),),
    # scavenge (CR 702.91) exiles a card from your GY to put that many +1/+1 counters
    # — a +1/+1 source, so it ALSO opens counters_matter (ADR-0027 migration merge).
    "scavenge": (
        ("scavenge_fuel", "you"),
        ("graveyard_matters", "you"),
        ("counters_matter", "any"),
    ),
    # Spectacle (CR 702.111) — "cast cheaper if an opponent lost life this turn" is a
    # life-loss PAYOFF (it cares about opponents having lost life), but the condition
    # lives entirely in reminder text that the structural projection strips, so the IR
    # fires no lose_life. Moved here from _DIRECT_KEYWORD_SIGNALS for the ADR-0027
    # lifeloss_matters migration so the keyword route stays on the IR path (extort /
    # afflict already fire lifeloss STRUCTURALLY and need no keyword entry).
    "spectacle": (("lifeloss_matters", "opponents"),),
    "soulbond": (("soulbond_matters", "you"),),
    "specialize": (("specialize_matters", "you"),),
    "suspend": (("suspend_matters", "you"),),
    # undying (CR 702.92) returns with a +1/+1 counter — a +1/+1 source, so it ALSO
    # opens counters_matter (ADR-0027 migration merge). persist returns with a -1/-1
    # counter (its own minus lane), so it is NOT given counters_matter.
    "undying": (
        ("undying_persist_matters", "you"),
        ("dies_recursion", "you"),
        ("counters_matter", "any"),
    ),
    "persist": (("undying_persist_matters", "you"), ("dies_recursion", "you")),
    "affinity": (("affinity_type", "you"),),
    # Investigate (CR 701.27) IS "create a Clue token" — a colorless ARTIFACT (CR
    # 205.3g). phase tags the keyword but drops the Clue subtype off the make_token
    # subject (the keyword-action's reminder text isn't structured — Deduce, Bygone
    # Bishop, Angelic Sleuth all carry make_token subject=None), so the keyword is the
    # structural anchor that the Clues feed an artifacts deck (affinity / metalcraft /
    # Academy Manufactor). The dedicated clue_matters lane reads investigate off its own
    # regex floor; this opens artifacts_matter, which has no other tell for these.
    "investigate": (("artifacts_matter", "you"),),
    "islandwalk": (("island_matters", "you"),),
    "enlist": (("enlist_matters", "you"),),
    "exalted": (("exalted_lone_attacker", "you"),),
    "exhaust": (("exhaust_matters", "you"),),
    # NB: cycling/crew/curse are NOT here — having Cycling ≠ a cycling-MATTERS
    # payoff, having Crew ≠ a Vehicle-tribal payoff, being a Curse ≠ curses-matter.
    # Those derive from triggers / Filter subtypes in later batches.
    "menace": (("evasion_self", "you"),),
    "fear": (("evasion_self", "you"),),
    "intimidate": (("evasion_self", "you"),),
    "skulk": (("evasion_self", "you"),),
    "horsemanship": (("evasion_self", "you"),),
    "shadow": (("evasion_self", "you"),),
    # Spell-copy keywords (CR 702.40 storm, 702.108 replicate, 702.78 conspire) —
    # each COPIES the spell, the printed-keyword path for spell_copy_matters that the
    # structural CopySpell effect misses (the copy rides the keyword, not a CopySpell
    # node). Distinct from the deleted regex's `\bstorm\b`, which over-fired on every
    # card NAMED "… Storm" (Comet Storm, Arrow Storm — burn, not the keyword); the
    # Scryfall keyword array carries Storm-the-mechanic only. Casualty is mapped above
    # (it sacs AND copies). CR 702.153.
    "storm": (("spell_copy_matters", "you"),),
    "replicate": (("spell_copy_matters", "you"),),
    "conspire": (("spell_copy_matters", "you"),),
    # Power-up (Marvel Universes Beyond) — a REAL ability word on expansion/commander
    # cards (Extremis Elite, Thanos, Abomination — set_type expansion/commander, NOT
    # funny; CR 207.2c). ADR-0027 t2b5-C: the Scryfall `Power-up` keyword array is exact
    # and 1:1 with the deleted `power-up —` ability-word regex (37 keyword carriers ==
    # 37 regex hits, 0 residual either direction over the full corpus). phase DROPS the
    # Power-up keyword from IR Face.keywords (Extremis Elite IR has keywords=()), so
    # this MUST read the Scryfall card['keywords'] array via _IR_KEYWORD_MAP — the same
    # keyword-array lookup path — not IR Face.keywords. The payoff granter (Wonder Man,
    # "each power-up ability … can be activated an additional time") also carries the
    # keyword, so it is captured too. These cards currently show commander:not_legal
    # only because the recent set's legalities have not propagated in the bulk.
    "power-up": (("powerup_matters", "you"),),
}

# ADR-0027 β — cost_reduction structural-arm gates (a BUILD-AROUND reducer = an effect
# that makes a CLASS of OTHER spells/abilities you cast cheaper — Goblin Electromancer,
# Ruby Medallion, Helm of Awakening, Urza's Incubator; a SELF-discount "this spell costs
# {X} less" is NOT in the lane, CR 601.2f/118.7). project.py carries two cat==
# "cost_reduction" forms: the static ModifyCost{Reduce} (subject = the spell_filter,
# scope "you", already SelfRef-gated + direction-correct) and the named
# `reducenextspellcost` effect (subject None, scope from the effect) which is NOT
# direction- or SelfRef-gated — phase mis-routes BOTH cost-INCREASE text ("cost {1}
# more", "cost an additional", a mana-floor) AND "this spell costs ... less" self-
# discounts into it. The arm trusts a non-None subject (static, gated) and screens the
# subject-None named effects: each must carry a genuine "cost(s) ... less" reduction and
# neither a self-discount nor a cost-increase tell.
#
# _COST_SELF_DISCOUNT — "this spell/ability/this costs ... less", the SelfRef the named
# path leaks (Cavern-Hoard Dragon / Marshmist Titan / the Avatars). Rules-excluded.
_COST_SELF_DISCOUNT = re.compile(
    r"\bthis spell costs\b|\bthis ability costs\b|\bthis costs\b", re.IGNORECASE
)
# _COST_LESS_REDUCER — a genuine "cost(s) ... less" reduction clause (the in-lane tell).
_COST_LESS_REDUCER = re.compile(r'\bcosts?\b[^."]{0,40}?\bless\b', re.IGNORECASE)
# _COST_INCREASE — a cost-INCREASE the named path mis-tags as cost_reduction: "cost ...
# more", "cost an additional", or Trinisphere's "would cost less than N ... costs N".
_COST_INCREASE = re.compile(
    r"\bcost(?:s)?[^.\"]{0,30}?\b(?:more|an additional)\b|would cost less than",
    re.IGNORECASE,
)

# ADR-0027 β — cost_reduction kept-mirror (a NARROWED, NOT byte-identical, mirror of the
# deleted regex). The structural arm in extract_signals_ir fires from the projection's
# static + named cost_reduction Effects; this mirror recovers the genuine build-around
# reducers the projection drops because they're not a static ModifyCost{Reduce} and not
# a clean named `reducenextspellcost`: ability-cost reducers ("Activated abilities of
# creatures you control cost {2} less to activate" — Biomancer's Familiar, Power
# Artifact, Training Grounds; equip/boast/ninjutsu/loyalty ability costs), conditional
# spell reducers ("Those spells cost {C} less" — the Defiler cycle), granted/property-
# filtered spell reducers ("Spells with the chosen name cost {1} less" — Cheering
# Fanatic), donor reducers ("spells that player casts cost {2} less" — Will Kenrith),
# named special-cost reducers ("Blitz costs you pay cost {2} less" — Henzie / Catalyst
# Stone), and the Chapter-3 / empty-raw projection tail ("The next Giant spell you cast
# ... costs {2} less" — Invasion of the Giants, whose IR effect raw is just
# "Chapter 3"). NARROWED (vs the byte-identical mirrors of clean migrations): the
# deleted regex was
# direction-AGNOSTIC and self-blind, so a byte-identical copy would re-introduce the 14
# cost-increase + 92 self-discount over-fires the lane correctly drops. Every arm
# requires a "cost(s) ... less" reduction of OTHER spells/abilities and structurally
# excludes "this spell costs" (self) and "... more"/"an additional" (increase). Verified
# over the commander-legal corpus: as a plain .search over the reminder-stripped oracle
# it has ZERO cost-increase-only false positives, and the floor-disabled IR-vs-regex
# residual is regex_only == 92 = 100% self-discount over-fire (correctly dropped), 0
# genuine miss. add() dedups the overlap with the structural arm. CR 601.2f / 118.7.
_COST_REDUCER_MIRROR = re.compile(
    # A. ability-cost reducers: "<class of> abilities ... cost {N} less to activate".
    r"\babilities[^.]{0,70}?\bcost\b[^.]{0,30}?\bless\b[^.]{0,12}?to activate"
    # B. conditional spell reducer: "those spells cost {C} less" (the Defiler cycle).
    r"|\bthose spells cost \{[wubrgc0-9x]+\}[^.]{0,20}?less to cast"
    # C. a spell CLASS (NOT "this spell") you cast made cheaper. Allows a tribal/type
    # adjective between "spell" and "you cast" (Invasion's "next Giant spell you cast",
    # Momo's "creature spell with flying you cast"); the (?<!this ) guard keeps a self-
    # discount out.
    r"|(?<!this )\bspells?\b[^.]{0,40}?\byou cast\b[^.]{0,40}?"
    r"\bcosts? \{?[wubrgc0-9x]+\}?[^.]{0,20}?less to cast"
    # D. a donor reducer: "spells <a player> casts cost {N} less" (Will Kenrith).
    r"|\bspells (?:that player|those players|that opponent|each player)[^.]{0,30}?"
    r"casts? cost \{[wubrgcx0-9]+\}[^.]{0,15}?less to cast"
    # E. a named special cost: "Blitz costs you pay cost {N} less" (Henzie / Catalyst).
    r"|\b(?:blitz|cycling|kicker|flashback|escape|ninjutsu) costs[^.]{0,30}?"
    r"cost \{[wubrgcx0-9]+\}[^.]{0,15}?less"
    # F. a granted/property-filtered spell class made cheaper, no "you cast" ("Spells
    # with the chosen name cost {1} less to cast" — Cheering Fanatic).
    r"|\bspells with [^.]{0,40}?\bcost \{?[wubrgc0-9x]+\}?[^.]{0,15}?less to cast",
    re.IGNORECASE,
)

# Kept narrow mechanic-word detectors: REAL mechanics (rules-lawyer-verified —
# voting CR 701.38, firebending CR 702.189, …) that phase v0.1.19 doesn't yet
# STRUCTURE (too recent/niche → Unimplemented). These are narrow keyword-WORD
# regexes (not the brittle "for each Y" kind the IR replaces), so the IR path
# KEEPS them — they survive A4 like the keyword-array / type_line lookups. Grow
# this as more mis-skipped mechanics are rules-lawyer-verified.
_IR_KEPT_DETECTORS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # Voting (CR 701.38). The supplement structures the vote clause into an
    # accurate Effect(category="vote") node where phase emits one, but the LANE
    # stays a kept oracle-scan detector for full coverage: phase leaves some
    # voting cards entirely unparsed (Ballot Broker, The Valeyard) or carries the
    # vote only in a trigger condition (Grudge Keeper), which an IR-only pass
    # can't reach. `\bvotes?\b` (vs the old `\bvote\b`) also catches the plural —
    # e.g. "each player secretly votes" (Trap the Trespassers), which the regex
    # _DETECTORS path still misses.
    (
        "voting_matters",
        re.compile(
            r"will of the council|council's dilemma|each player[^.]*votes?|\bvotes?\b",
            re.IGNORECASE,
        ),
        "each",
    ),
    # The four bending keywords are SEPARATE mechanics (rules-lawyer-verified;
    # no unifying "bending ability" rule exists, no card references the set), so
    # each gets its own lane rather than one conflated bending_matters: airbend
    # (CR 701.65), earthbend (CR 701.66), waterbend (CR 701.67), firebending
    # (CR 702.189). These mirror the same-named _sweep_detectors regexes.
    ("airbend_matters", re.compile(r"\bairbend(?:ing|s)?\b", re.IGNORECASE), "you"),
    ("earthbend_matters", re.compile(r"\bearthbend(?:ing|s)?\b", re.IGNORECASE), "you"),
    ("waterbend_matters", re.compile(r"\bwaterbend(?:ing|s)?\b", re.IGNORECASE), "you"),
    (
        "firebending_matters",
        re.compile(r"\bfirebend(?:ing|s)?\b", re.IGNORECASE),
        "you",
    ),
    # Batch 16 — recent-set mechanics phase v0.1.60 doesn't structure
    # (rules-lawyer-verified): celebration + coven (ability words, CR 207.2c),
    # outlaw (a creature-type group), plot (CR 702.170), miracle (CR 702.94),
    # lessons (a subtype), kicked (CR 702.33). Narrow word detectors, kept for A4.
    ("celebration_matters", re.compile(r"\bcelebration\b", re.IGNORECASE), "you"),
    ("coven_matters", re.compile(r"\bcoven\b", re.IGNORECASE), "you"),
    ("outlaw_matters", re.compile(r"\boutlaws?\b", re.IGNORECASE), "you"),
    ("lessons_matter", re.compile(r"\blessons?\b", re.IGNORECASE), "you"),
    # snow is a real supertype (CR 205.4), NOT a skip — the analysis workflow
    # wrongly listed it. A snow-matters payoff cares about snow permanents/mana.
    ("snow_matters", re.compile(r"\bsnow\b", re.IGNORECASE), "you"),
    # facedown_matters is a CARES-ABOUT lane: it must fire for face-down PAYOFFS
    # (Ixidor "face-down creatures get +1/+1", Secret Plans, Trail of Mystery), not
    # just the makers (morph/manifest/cloak/disguise). Those payoffs have no
    # structural IR form, so mirror the full same-named sweep regex here for parity
    # (the makers' IR categories + keywords also feed the lane; add() dedups).
    (
        "facedown_matters",
        re.compile(
            r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
            r"|face-?down creatures?|as a 2/2 face-?down"
            r"|turn (?:it|that creature|this creature|them|a permanent you control) "
            r"face up|turn target [^.]*?face up|turned face up this turn",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 (q2-D3) — flash_matters: the GRANT half binds structurally in
    # extract_signals_ir (cast_with_keyword{flash}); this mirror is the FULL deleted
    # _HAND_FLOOR regex (both branches), recovering (a) the ACTIVATED flash-grant phase
    # folds into grant_keyword with an EMPTY counter_kind (Winding Canyons {2}{T},
    # Teferi Time Raveler +1) and (b) the opponent-turn cast payoff phase leaves textual
    # ("whenever you cast a spell during an opponent's turn"). add() dedups the overlap
    # with the structural arm. CR 702.8.
    (
        "flash_matters",
        re.compile(
            r"cast[^.]{0,60}spells?[^.]{0,30}as though they had flash"
            r"|whenever you cast (?:a |your first )?spells? "
            r"during (?:an|each|any) opponent",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 (q2-D3) — noncreature_cast_punish SYMMETRIC half: the opponent-punisher
    # half binds structurally in extract_signals_ir (a cast_spell trigger scope=='opp'
    # with a noncreature subject). This mirror is the SYMMETRIC "a player casts a
    # noncreature spell" branch of the deleted SWEEP regex (Niv-Mizzet Parun,
    # Mirrorwing Dragon, Eye of the Storm, Hive Mind) — phase collapses these to
    # scope=='any', indistinguishable from prowess, so the regex (anchored on "a
    # player"/"an opponent", which prowess "you cast" never matches) is the precise
    # recall here. add() dedups with the opp structural arm. CR 603.2.
    (
        "noncreature_cast_punish",
        re.compile(NONCREATURE_CAST_PUNISH_REGEX, re.IGNORECASE),
        "any",
    ),
    # ADR-0027 β — tribe_damage_trigger: phase leaves the combat_damage trigger subject
    # = None (no structure to read — the `tsub_kinds` arm in extract_signals_ir was DEAD
    # CODE, never firing on a combat-damage trigger), so this is a byte-identical KEPT
    # MIRROR of the deleted SWEEP regex, not a projection. Under re.IGNORECASE the
    # `[A-Z][a-z]+` ALSO matches a generic "creature", so the lane is really "your
    # creatures connect for combat damage → reward" (Toski, Reconnaissance Mission,
    # Coastal Piracy, Bident of Thassa), not strictly tribal. Scope 'you' (the deleted
    # SWEEP row's scope). Reuses the shared regex so serve / mirror never drift.
    (
        "tribe_damage_trigger",
        re.compile(TRIBE_DAMAGE_TRIGGER_REGEX, re.IGNORECASE),
        "you",
    ),
    # ADR-0027 β — combat_damage_to_creature + combat_damage_to_opp (both
    # is_widen_of combat_damage_matters). phase DOES structure the combat_damage
    # trigger event but NOT the RECIPIENT TYPE: Ohran Viper's two DamageDone
    # triggers differ in raw card-data (valid_target Typed[Creature] vs Player),
    # yet project.py uses valid_target only for its `controller` (scope), dropping
    # its TYPE — so both project to scope='any', subject=None, byte-identical. The
    # recipient discriminator survives in the joined-face oracle ("to a creature"
    # vs "to a player/an opponent/each opponent"), which is exactly what these
    # byte-identical KEPT MIRRORS of the deleted SWEEP regexes anchor on — so they
    # DO split the two lanes the structural payoff arm cannot. The deleted regexes
    # only ever matched single clauses (the connect phrase never holds `.`/`;`/
    # `\n`), so the flat-text mirror reproduces the per-clause regex firing set
    # exactly (commander-legal corpus: regex==mirror, 0 lost, 0 over-fire;
    # creature=33 / opp=757 + 3 double-strike-grant; the 2 cards with BOTH a
    # creature- and a player-recipient trigger — Ohran Viper, Phage the
    # Untouchable — fire BOTH lanes). CR 510.1c / 510.2.
    (
        "combat_damage_to_creature",
        re.compile(COMBAT_DAMAGE_TO_CREATURE_REGEX, re.IGNORECASE),
        "any",
    ),
    (
        "combat_damage_to_opp",
        re.compile(COMBAT_DAMAGE_TO_OPP_REGEX, re.IGNORECASE),
        "opponents",
    ),
    # NB: the LOW-confidence double-strike-grant producer of combat_damage_to_opp
    # is handled as a dedicated inline mirror in extract_signals_ir (NOT a row
    # here): the kept-detector loop emits HIGH confidence, but the deleted producer
    # fired LOW and so never fed has_other_plan — firing its 3 cards (Raphael,
    # Blade Historian, Berserkers' Onslaught — power-2 voltron-eligible bodies) at
    # HIGH would spuriously SILENCE their commander-damage voltron tell. The inline
    # mirror preserves the LOW confidence.
    # ADR-0027 β — damage_to_opp_matters (is_widen_of combat_damage_matters): the
    # GENERAL (any-source, ANY damage — not the literal "combat damage") "deals damage
    # to a PLAYER / opponent" connect-payoff (Hypnotic Specter, Curiosity, Goblin
    # Lackey, Fungal Shambler). The STRUCTURAL arm in extract_signals_ir already fires
    # the 69 phase-typed DamageDone player-recipient triggers (via the SIDECAR v13
    # DamageToPlayer marker). This BYTE-IDENTICAL kept mirror of the deleted HAND_FLOOR
    # regex recovers the textual tail phase can't structure as a DamageDone trigger: a
    # trigger QUOTED inside a GrantAbility ("creatures you control gain 'whenever this
    # creature deals damage to an opponent, draw' " — Snake Umbra, Helm of the
    # Ghastlord, Serpent Generator, Arm with Aether), an ETB / set-in-motion BURST
    # ("when ~ enters, it deals damage to each opponent" — Fanatic of Mogis, Meria's
    # Outrider), and other-event consequences (Magebane Lizard's spellcast-punish). The
    # deleted regex matched single clauses (`[^.]*?` never crosses `.`), so the flat
    # mirror over reminder-stripped kept_oracle reproduces the per-clause regex firing
    # set exactly. add() dedups vs the structural arm; the union is +recall over the
    # deleted regex. Same HIGH confidence the deleted HAND_FLOOR producer fired (scope
    # 'opponents'). Distinct from combat_damage_to_opp (the literal-"combat" recipient —
    # this regex's `deals (?:noncombat )?damage` never matches "deals combat damage").
    # CR 119.3.
    (
        "damage_to_opp_matters",
        re.compile(DAMAGE_TO_OPP_MATTERS_REGEX, re.IGNORECASE),
        "opponents",
    ),
    # ADR-0027 β — keyword_grant_target: a keyword grant to a SINGLE TARGET creature
    # ("target creature gains menace until end of turn"). The STRUCTURAL arm in
    # extract_signals_ir fires the single-target spell/ability grants via the SIDECAR
    # v14 single_target_grant marker (project._single_target_keyword_grant_markers).
    # This
    # BYTE-IDENTICAL kept mirror of the deleted SWEEP regex recovers the textual tail
    # phase can't structure as a spell/ability GenericEffect grant: the grant QUOTED
    # inside a GrantAbility on an Aura / land / planeswalker ("Enchanted land has '{T}:
    # Target creature gains haste'" — Racecourse Fury, Skygames, Footfall Crater;
    # Rowan's Talent's quoted loyalty grant), a MODAL/choose grant ("• Target creature
    # gains flying" — Balloon Stand, Adaptive Sporesinger, Retreat to Hagra, Feroc
    # ification, Appa), and a compound grant carrying a quoted ability (Infuse with
    # Vitality "gains deathtouch and '<dies trigger>'"). The deleted regex is clause-
    # local (no `[^.]` spans a sentence), so the flat mirror over reminder-stripped
    # kept_oracle reproduces the per-clause regex firing set exactly. add() dedups vs
    # the structural arm; the union is +recall over the deleted regex (the "It gains X"
    # idiom + protection/ward single-target grants the structural arm adds, which the
    # regex missed). Same HIGH confidence + scope "you" the deleted SWEEP producer
    # fired. CR 700.2.
    (
        "keyword_grant_target",
        re.compile(KEYWORD_GRANT_TARGET_REGEX, re.IGNORECASE),
        "you",
    ),
    # ADR-0027 — cares-about lanes phase v0.1.19 doesn't structure as a payoff
    # (rules-lawyer-verified: no card-property reference shape in the parse), moved
    # here from _IR_FLOOR_LANES so the lane fires from a dedicated IR-path word mirror
    # instead of the reused production floor Detector (floor-mirror-dep -> 0). Each
    # retains its EXISTING structural bind in extract_signals_ir too (add() dedups):
    #   • devotion_matters  ← amount.op=="devotion" count operand (the scaling payoffs);
    #     this mirror adds the cost-reduction / counterspell-tax / mana forms
    #     ("devotion to <color>") phase doesn't make a count operand. CR 700.5.
    #   • party_matters     ← amount.op=="party" count operand; this mirror adds the
    #     "full party" CONDITION + "creatures in your party" non-count refs. CR 700.6.
    #   • historic_matters  ← the "Historic" subject-Filter predicate; this mirror adds
    #     the cost-reduction / "play a historic" / type-group refs phase leaves textual
    #     (artifacts, legendaries, and Sagas are historic — CR 702.18-style group).
    #   • multicolor / colorless ← the ColorCount subject-Filter predicates (the
    #     "multicolored/colorless <permanent> you control" build-arounds); this mirror
    #     adds the "cast a multicolored spell" TRIGGER + "colorless spell/creature"
    #     cost-reduction / cast-restriction refs that aren't a structured subject.
    #   • initiative_matters / attractions_matter ← recent named designations (CR
    #     720 / 717) phase doesn't structure at all — the word IS the build-around tell.
    ("devotion_matters", re.compile(r"devotion to \w", re.IGNORECASE), "you"),
    (
        "party_matters",
        re.compile(
            r"\byour party\b|members? of your party|full party"
            r"|assemble[^.]*party|creatures? in your party",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("historic_matters", re.compile(r"\bhistoric\b", re.IGNORECASE), "you"),
    (
        "multicolor_matters",
        re.compile(
            r"for each color pair|exactly those colors|cast a multicolored"
            r"|multicolored (?:creature|permanent|spell)s? you",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "colorless_matters",
        re.compile(r"colorless (?:creature|spell|permanent)", re.IGNORECASE),
        "you",
    ),
    ("initiative_matters", re.compile(r"\bthe initiative\b", re.IGNORECASE), "you"),
    (
        "attractions_matter",
        re.compile(r"\battraction\b|open an attraction", re.IGNORECASE),
        "you",
    ),
    # ADR-0027 batch — cares-about / payoff lanes phase v0.1.19 scatters across
    # categories it doesn't unify (a count operand it drops, a trigger flattened to
    # event='other', a grant whose subject it folds), so each fires from a dedicated
    # IR-path word mirror (the deleted regex producer) alongside its EXISTING structural
    # bind (add() dedups). Each mirror reproduces the deleted regex exactly (regex-only
    # residual == 0). rules-lawyer-verified boundaries:
    #   • minus_counters_matter ← place_counter(m1m1) is the maker; the "-1/-1 counter"
    #     references (remove / cost / ward / "with a -1/-1 counter on it" / prevention)
    #     are the cares-about payoffs phase leaves textual (CR 122 / 702.80 Wither).
    #   • exalted_lone_attacker ← the `exalted` keyword is the bearer; "attacks alone"
    #     payoff triggers + "X have exalted" grants are textual (CR 702.83).
    #   • speed_matters ← phase's `speed` doer is the changer; "Start your engines!" /
    #     "max speed" / "your speed" payoffs are unstructured (CR 702.178/702.179).
    #   • tap_untap_matters ← phase's `taps` (tap-for-mana) trigger is structured; the
    #     "becomes tapped/untapped" trigger (Inspired) flattens to event='other'.
    #   • domain_matters ← amount.op=='domain' is the scaler; cost-reduction /
    #     conditions / the "Domain —" ability word are textual (CR 700.3).
    #   • commander_matters ← the IsCommander subject-Filter predicate is structured;
    #     Background grants ("Commander creatures you own have …") + "commander damage"
    #     / "your commander costs less" are textual (CR 903).
    #   • hand_disruption ← the opp-reveal trigger is structured; "look at … hand" /
    #     "play with hands revealed" / modal reveal-and-discard are textual.
    #   • team_evasion_grant ← phase structures the generic creatures-you-control
    #     keyword grant; the subtype/color-scoped grants ("Sliver creatures you control
    #     have flying", "Blue creatures you control can't be blocked") are the broader
    #     team-evasion forms (CR 702.13/702.14/509).
    #   • opponent_exile_matters ← GRAVEYARD HATE (CR 406), scattered across exile/
    #     cheat_play/pump categories phase doesn't unify; the lane is the kept mirror
    #     alone (the old permanent-exile arm mis-fired on Path-to-Exile removal).
    (
        "minus_counters_matter",
        re.compile(r"-1/-1 counter", re.IGNORECASE),
        "you",
    ),
    (
        "exalted_lone_attacker",
        re.compile(r"attacks alone|\bexalted\b", re.IGNORECASE),
        "you",
    ),
    (
        "speed_matters",
        re.compile(r"start your engines|max speed|your speed", re.IGNORECASE),
        "you",
    ),
    (
        "tap_untap_matters",
        re.compile(
            r"whenever [^.]*becomes? (?:tapped|untapped)|becomes? untapped, put",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "domain_matters",
        re.compile(
            r"\bdomain\b|number of basic land types? (?:among|you)"
            r"|basic land types? among",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "commander_matters",
        re.compile(
            r"commanders? you (?:control|own) (?:have|has|get|gets|gain|gains)"
            r"|commander creatures? you (?:own|control)|whenever your commander\b"
            r"|whenever a commander\b"
            r"|your commander (?:has|have|deals|enters|attacks|gets|gains)"
            r"|is your commander|it'?s your commander|while [^.]*your commander"
            r"|it's a copy of your other commander|copy of any of your commanders"
            r"|each commander you (?:control|own)|for each commander|commander damage",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "hand_disruption",
        re.compile(
            r"look at (?:target player|that player|an opponent|each opponent"
            r"|target opponent)'?s?'? hands?"
            r"|plays? with (?:their|his or her) hands? revealed"
            r"|reveals? (?:their|his or her) hands?"
            r"|reveals? (?:\w+ )?cards? (?:at random )?from "
            r"(?:their|his or her|that player's) hand"
            r"|reveals?[^.]*until you say stop",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    (
        "team_evasion_grant",
        re.compile(
            r"(?:other |attacking )?creatures you control (?:gain|have)\b"
            r"[^.]{0,40}?\b(?:menace|fear|intimidate|shadow|horsemanship|skulk"
            r"|flying|can't be blocked)\b"
            r"|(?:other |attacking )?creatures you control[^.]*can't be blocked",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "opponent_exile_matters",
        re.compile(
            r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
            r"|for each card your opponents own in exile|opponents own in exile"
            r"|exile (?:target player's|target opponent's|each opponent's"
            r"|that player's) graveyard"
            r"|if a card would be put into an opponent's graveyard",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # opp_top_exile (ADR-0027 q2-D2) — the name-lock / peek subset phase under-parses:
    # phase scopes Circu's "exile the top card of target player's library" as
    # scope=='any' (no opp), Scrib Nibblers likewise, and Predators' Hour grants the
    # clause to other creatures (no own exile effect). These never reach the structural
    # extract_signals_ir arm (exile scope=='opp' + cast_from_zone/in:library), so the
    # lane fires from this byte-identical mirror of the deleted "exile the top card of
    # <opponent>" regex producer (regex-only residual == 0; mirror flood beyond the
    # deleted producer == 0). Scope 'you' (the engine controller), matching the deleted
    # producer. The structural arm adds the 50 broader steal-and-cast cards the regex
    # never reached (CR 406 — exile is a public zone these commanders mine).
    (
        "opp_top_exile",
        re.compile(
            r"exile the top card of (?:target player|each opponent|that player"
            r"|an opponent|target opponent)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 SWEEP batch — Group B cares-about lanes that phase v0.1.19 leaves
    # TEXTUAL (rules-lawyer + oracle verified): each had a load-bearing floor mirror
    # (floor-mirror-dep > 0 in the commander-legal corpus), so it MOVES from
    # _IR_FLOOR_LANES (a reused production floor Detector) to a dedicated IR-path word
    # mirror here — the sanctioned home (bending / voting / facedown). Each KEEPS its
    # existing structural / keyword IR bind too (add() dedups); the mirror reproduces
    # the deleted _HAND_FLOOR regex exactly (regex-only residual == 0):
    #   • legends_matter ← the HasSupertype:Legendary subject-Filter predicate (the
    #     "whenever a legendary … you control" / count subjects); the mirror adds the
    #     cost-reduction "for each legendary creature you control", "target legendary",
    #     "cast legendary spells", and library-search refs phase leaves textual (CR
    #     205.4a). Two _HAND_FLOOR rows merged.
    #   • lands_matter ← the amount.subject=Land count operand (the structured
    #     scalers); the mirror adds the "P/T equal to the number of lands you control"
    #     (Dakkon / Molimo — phase emits characteristic_pt/pump_target but DROPS the
    #     count operand) and "for each land you control" pumps phase flattens to a bare
    #     effect (CR 305).
    #   • poison_matters ← the infect/toxic/poisonous Scryfall keywords (the bearers);
    #     the mirror adds the GRANTERS ("Enchanted creature has infect", "gains infect",
    #     "All Sliver creatures have poisonous 1") + "poison counter" / "has toxic"
    #     references phase folds into a grant carrier's raw (CR 122 / 702.90 Infect).
    #   • suspend_matters ← the Scryfall `suspend` keyword (the bearers); the mirror
    #     adds the keyword-LESS suspend grants ("It gains suspend", As Foretold) + the
    #     whole time-counter superstructure (time travel CR 701.56, Vanishing 702.63,
    #     Impending) phase doesn't structure as suspend. SWEEP \bsuspend\b folded in.
    (
        "legends_matter",
        re.compile(
            r"search your library for a legendary"
            r"|target legendary (?:creature|permanent)"
            r"|legendary (?:creatures?|permanents?|spells?) you (?:control|cast)"
            r"|(?:number of|other) legendary"
            r"|whenever (?:a|another|one or more) legendary "
            r"(?:permanents?|creatures?)"
            r"[^.]*(?:enters|dies|put into a graveyard|leaves the battlefield"
            r"|you control)"
            r"|whenever you cast a legendary|for each legendary "
            r"(?:creature|permanent)"
            r"|cast legendary|legendary spells?",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "lands_matter",
        re.compile(
            r"(?:the number of|for each) (?:basic )?lands? you control",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "poison_matters",
        re.compile(
            r"poison counters?|\bpoisonous\b|\btoxic\b|\binfect\b", re.IGNORECASE
        ),
        "opponents",
    ),
    (
        "suspend_matters",
        re.compile(
            r"\bsuspend\b|time counter|time travel|\bvanishing\b|\bimpending\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 — exert_matters (the Johan namesake): "attacking doesn't cause
    # creatures you control to tap" neutralizes exert's "won't untap" downside, but
    # phase projects it to a restriction whose clause survives only in raw (no mode
    # token on the Effect), so a kept word mirror covers this single card. The TEAM-
    # vigilance enablers (Heliod, Brave the Sands, Always Watching) are served
    # STRUCTURALLY by the grant_keyword/vigilance arm in extract_signals_ir.
    (
        "exert_matters",
        re.compile(
            r"attacking doesn'?t cause (?:creatures|them)[^.]*to tap", re.IGNORECASE
        ),
        "you",
    ),
    # ADR-0027 counter_manipulation cost tail — the IR recovers the +1/+1/-1/-1
    # MOVE (counter_move) and remove-as-EFFECT (remove_counter) halves structurally,
    # but the remove-as-COST form ("Remove a +1/+1 counter from ~:" — Walking
    # Ballista, Fertilid, Quillspike, Devoted Druid) is an Ability.cost phase leaves
    # in raw, unreachable from the structured IR. This mirror is byte-identical to
    # the deleted SWEEP_DETECTORS row so the hybrid reproduces its firings exactly
    # (A-B==0; the IR additionally catches Graft's counter MOVE). CR 122.1 / 122.6.
    (
        "counter_manipulation",
        re.compile(
            r"(?:remove|move) (?:a|one|any number of|x|\d+) (?:\+1/\+1|-1/-1) "
            r"counters?|(?:remove|move) (?:a|one|any number of|x|\d+) "
            r"[^.]{0,20}?(?:\+1/\+1|-1/-1) counters?",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-C — extra_land_drop tail. The structural arms (cheat_play /
    # topdeck_select with a Land subject) cover the bulk; this YOUR-anchored mirror
    # recovers the cards phase leaves textual: an empty-raw modal Confluence
    # (Riveteers), a cascade-from-exile put (Averna), a library/exile dig phase
    # mis-zoned to to:hand (Aminatou's Augury, Planar Genesis, Journey to the Lost
    # City), and a hand-put phase dropped entirely (Contaminant Grafter). The
    # "from your hand|among them|among those/the exiled cards" source clause EXCLUDES
    # the graveyard-source put (Wreck and Rebuild, Soul of Windgrace), which phase
    # correctly routes to reanimate (a graveyard-lands engine, a different shape) —
    # the deleted regex's broad arm over-matched into that graveyard source. CR 305.9.
    (
        "extra_land_drop",
        re.compile(
            r"you may put (?:a |up to \w+ )?lands? cards? "
            r"from (?:your hand|among them|among those cards"
            r"|among the exiled cards)[^.]*onto the battlefield",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 exile_until_leaves Saga tail — _is_exile_until_leaves recovers the
    # one-ability inline form (raw phrase) and the two-ability O-Ring form
    # structurally, but a SAGA CHAPTER exile collapses its per-effect raw to a
    # "Chapter N" stub (Trial of a Time Lord, Summon: Ixion), losing the inline
    # "until ~ leaves" phrase. The joined-face oracle text still carries it, so this
    # mirror (byte-identical to the deleted SWEEP_DETECTORS row) recovers the tail
    # (A-B==0; the IR additionally catches the linked-return O-Rings — Oblivion Ring,
    # Detention Sphere — the inline regex missed). CR 714.2.
    (
        "exile_until_leaves",
        re.compile(r"exile [^.]*until [^.]*leaves the battlefield", re.IGNORECASE),
        "you",
    ),
    # ADR-0027 tranche2-C — keyword_counter tail. The structural arm (place_counter /
    # remove_counter with a CR-122.1b keyword counter_kind) covers the bulk; this kept
    # mirror reuses the shared KEYWORD_COUNTER_REGEX to recover the choice/multi/quoted-
    # grant cards phase drops counter_kind on ("your choice of a flying OR a hexproof
    # counter" — Wingfold Pteron, T-45 Power Armor, Vivien). scope 'any' (these counter
    # sources appear on either side). CR 122.1b.
    ("keyword_counter", re.compile(KEYWORD_COUNTER_REGEX, re.IGNORECASE), "any"),
    # ADR-0027 keyword_soup tail. The structural arm (>=5 distinct evergreen
    # grant_keyword counter_kinds in one ability) catches the genuine granters
    # (Odric, Akroma's Memorial, Cairn Wanderer). phase parses the "the same is true
    # for X, Y, …" keyword-absorb idiom INCONSISTENTLY — it expands some cards
    # (Cairn Wanderer -> 9 grants) but collapses others to a single flying grant
    # (Indominus Rex, Urborg Scavengers), so this mirror (byte-identical to the
    # deleted SWEEP row) recovers that under-parse tail. A-B==0. CR 702.
    (
        "keyword_soup",
        re.compile(
            r"if it has flying[^.]*first strike"
            r"|the same is true for first strike, double strike"
            r"|has flying[^.]*\+1/\+1",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 land_creatures_matter tail. The structural arms (Land+Creature
    # subject anthems/makers + the animate/base_pt_set/type_set animator) catch the
    # bulk (174 cards, +127 manlands the regex missed), but phase drops some
    # self-animate manland clauses ({cost}: this land becomes a creature) entirely
    # and routes a few animators through non-animate categories (Druid Class's
    # characteristic_pt, Sage of the Maze's restriction). This mirror (byte-identical
    # to the deleted _HAND_FLOOR row) recovers that tail. A-B==0. CR 305 + CR 110.1.
    (
        "land_creatures_matter",
        re.compile(
            r"\bland creatures?\b|lands? you control (?:are|become)\b"
            r"|all lands[^.]*become[^.]*creature"
            r"|target land[^.]*becomes? a[^.]*creature"
            r"|(?:it's|becomes?) a forest land",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 land_protection tail. The structural animator arm catches the
    # mass land-animation commanders, but phase drops the self-animate clause on most
    # manlands (Creeping Tar Pit / Raging Ravine / the Restless lands), so this mirror
    # (byte-identical to the deleted _HAND_FLOOR row) recovers those 17 manlands the
    # structural read misses. A-B==0. CR 305 + CR 110.1.
    (
        "land_protection",
        re.compile(
            r"land[^.]*becomes? a[^.]*creature|lands? you control are[^.]*creatures"
            r"|that land becomes",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-B (t2b3-B) — power_tap_engine tail. The structural arm (an
    # ACTIVATED ability cost~'tap' + a power-scaling effect raw) covers the card's OWN
    # engine (Marwyn, Selvala, Staff of Domination). This kept mirror — byte-identical
    # to the deleted _HAND_FLOOR regex — recovers the CONFERRED form, where the
    # power-scaling "{T}: … equal to its power" engine is GRANTED to a creature via a
    # quoted Aura / equipment / one-turn grant (Predatory Urge, Burning Anger, Dragon
    # Throne of Tarkir, Gruesome Slaughter) or rides a DFC back face (Arlinn, Hadana's
    # Climb) — phase folds the granted ability into a grant carrier, losing the
    # Ability.cost='tap' anchor, so it survives only in the joined-face oracle. CR 602.
    (
        "power_tap_engine",
        re.compile(
            r"\{t\}:[^.]*(?:equal to|where x is|x is)[^.]*\bpower\b", re.IGNORECASE
        ),
        "you",
    ),
    # ADR-0027 tranche2-B (t2b3-B) — opponent_cast_matters symmetric-punish tail. The
    # structural arm (a cast_spell trigger scope='opp') covers the explicit "whenever an
    # opponent casts" half (Lavinia, Nekusar). This kept mirror — the deleted
    # _HAND_FLOOR regex with its OVER-BROAD bare "whenever a player casts a spell" arm
    # DROPPED (the IR is more precise than the regex here) — recovers the SYMMETRIC-
    # PUNISHER half, where phase collapses "whenever a player casts" to scope='any'
    # indistinguishable from a self-cast spellslinger payoff. The "that player" / "they
    # lose/discard/sacrifice" punish anchor (the spell's caster punished as a third
    # party — Ruric Thar "6 damage to that player", Mai, Eidolon of the Great Revel,
    # Ash Zealot) is the discriminator that excludes the spellslinger over-fire (Kessig
    # Flamebreather "damage to each opponent", Extort) the bare arm caused. The
    # explicit-opponent arm is kept too for joined-face DFC robustness (add() dedups vs
    # the structural scope='opp' arm). CR 603.2.
    (
        "opponent_cast_matters",
        re.compile(
            r"whenever an opponent casts|whenever an opponent cast"
            r"|whenever (?:a|another) player casts[^.]*(?:(?:they|that player) "
            r"(?:loses?|discards?|sacrifices?)|deals? \d+ damage to that player)",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # ADR-0027 tranche2-batch-4 (t2b4-C) — three kept_detector lanes phase v0.1.60
    # CANNOT structure (rules-lawyer / spec verified: the discriminant is DROPPED in
    # the parse), so each fires from a dedicated IR-path word mirror reproducing the
    # deleted SWEEP / _HAND_FLOOR regex EXACTLY (full-text == per-clause over the
    # commander-legal corpus — each regex is clause-safe, A-B==0). floor-mirror-dep == 0
    # by construction (the kept mirror is not a floor detector).
    #   • damage_to_you_punish ← phase captures the deals_damage event but DROPS both
    #     discriminants: the source filter (subject=None, not 'opp') and the player-
    #     recipient ("to you" has no IR field) — event='deals_damage'/scope='any' can't
    #     be told from any "whenever ~ deals damage" trigger. The literal "deals
    #     (combat) damage to you" from an opponent-controlled source is the only tell.
    #   • excess_damage ← the 4 clean "is dealt excess damage" payoffs bind structurally
    #     (a Trigger event=='excess_damage'), but 29/33 references ride an intervening
    #     "if ~ was dealt excess damage" clause on a regular trigger or live in spell
    #     text — phase inlines that into Effect.raw, NOT a structured Condition. This
    #     residual word mirror recovers them. Serve stays serve_keywords=("trample",)
    #     (CR 702.19 enablers).
    #   • tap_down_blockers ← the "can't be blocked unless all creatures defending
    #     player controls block it" clause is 100% DROPPED by phase (Tromokratis's IR
    #     carries only the hexproof grant). No structural shape; the phrase is the tell.
    (
        "damage_to_you_punish",
        re.compile(
            r"whenever a source an opponent controls deals damage to you"
            r"|whenever (?:a|an) (?:opponent|source[^.]*opponent)[^.]*deals "
            r"(?:combat )?damage to you",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    ("excess_damage", re.compile(r"\bexcess damage\b", re.IGNORECASE), "you"),
    (
        "tap_down_blockers",
        re.compile(r"can'?t be blocked unless all", re.IGNORECASE),
        "you",
    ),
    # win_lose_game (ADR-0027 t2b4a-B) — the IR arm reads Effect.category in
    # {win_game, lose_game} (the broad terminal-outcome pool — 54+43 cards, far past
    # the narrow deleted regex). phase loses the outcome on a GRANTED / quoted ability
    # ("create tokens with 'that player loses the game'" — Vraska the Unseen / Vraska,
    # Golgari Queen; Frodo's granted "loses the game if the Ring tempted you"), folding
    # the quote into the grant carrier so no own-card win_game/lose_game Effect
    # survives. This mirror reproduces the deleted SWEEP regex EXACTLY (scope 'any', the
    # row's behavior-neutral choice — it matched both self-wins and player-losses)
    # so those conferred-ability cards keep firing. CR 104.2.
    (
        "win_lose_game",
        re.compile(
            r"you win the game|(?:that player|each opponent"
            r"|target (?:player|opponent)) loses the game",
            re.IGNORECASE,
        ),
        "any",
    ),
    # curse_matters cares-about (ADR-0027 t2b4a-B) — the IR arm reads Filter.subtypes
    # =='Curse' on a trigger/effect subject (Lynde, Bitterheart Witch, Witchbane Orb),
    # but phase under-parses a "search your library for a Curse card that doesn't have
    # the same name as …" subject (Curse of Misfortunes) so no Curse Filter survives.
    # This mirror reproduces the deleted cares-about regex EXACTLY (anchored on Curse-
    # as-a-mechanic — "a/target/each/another/your Curse", "Curse spells/cards",
    # "Curses you cast/control/own" — so a bare card NAME "Connors's Curse" never
    # qualifies; CR 205.3 / 702.39 Aura — Curse). The membership half (a card that IS
    # a Curse) stays REGEX-ONLY at A4 like TYPE_MATTERS membership — the regex never
    # fired it, so the type_line subtype read is deferred to avoid a 42-card flood.
    (
        "curse_matters",
        re.compile(
            r"curse spells?|curses? you (?:cast|control|own)"
            r"|(?:\ba|target|each|another|your) curse\b|curse cards?",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-A) — 5 kept_detector lanes phase v0.1.60 CANNOT
    # structure (rules-lawyer / spec verified: the discriminant is un-CR digital
    # vocabulary, a per-mode target-legality constraint, an inconsistently-parsed
    # Kamigawa flip, a cost-rewrite phase doesn't model, or a grant-direction phase
    # folds into a carrier). Each fires from a dedicated IR-path WORD MIRROR
    # reproducing the deleted SWEEP / _HAND_FLOOR regex EXACTLY (the mirror reads the
    # joined-face oracle, so it is byte-identical — A-B==0). floor-mirror-dep == 0 by
    # construction (none is a floor detector).
    #   • draft_spellbook ← Arena/Alchemy digital mechanics (draft-a-card / spellbook)
    #     NOT in the CR with NO phase effect category (phase leaves them
    #     category='other'). The literal phrasing is the only signal; all matching
    #     cards are games:['arena'], so the lane is correctly inert in paper formats.
    #   • each_mode_player ← phase captures the modal head (Effect.category=='choose')
    #     but has NO field for the spread-the-modes CONSTRAINT; a bare 'choose' marker
    #     over-fires 1364:8 (every modal card). The literal phrase is the discriminator.
    #   • flip_self ← phase parses the Kamigawa flip (CR 710) INCONSISTENTLY (transform
    #     / reanimate / buried in raw), so no single structured category is reliable;
    #     "flip this creature" is a coined term on exactly the 7 flip creatures.
    #   • free_plot ← no IR structure for the Plot alt-cost rewrite (phase routes
    #     Fblthp's plot-cost clause to a subjectless topdeck_select). The phrase is
    #     literally unique to one card (Fblthp, Lost on the Range) — zero over-fire.
    #     (NB: the broad "\bplot\b" the old DEFERRED note warned against is NOT this
    #     producer — the _HAND_FLOOR regex was already the tight unique-phrase form.)
    #   • miracle_grant ← a card that GRANTS miracle to OTHER cards in hand; phase folds
    #     the grant into a carrier (category grant_keyword/other). The "cards/spells in
    #     your hand have/has miracle" phrasing is the granting DIRECTION (an intrinsic
    #     miracle card carries a "Miracle {cost}" keyword line, so the mirror excludes
    #     it). CR 702.94.
    (
        "draft_spellbook",
        re.compile(r"\bdraft a card\b|spellbook", re.IGNORECASE),
        "you",
    ),
    (
        "each_mode_player",
        re.compile(r"each mode must target a different player", re.IGNORECASE),
        "each",
    ),
    ("flip_self", re.compile(r"\bflip this creature\b", re.IGNORECASE), "you"),
    (
        "free_plot",
        re.compile(r"plot cost is equal to its mana cost", re.IGNORECASE),
        "you",
    ),
    (
        "miracle_grant",
        re.compile(
            r"(?:cards?|spells?) (?:in your hand )?ha(?:s|ve) miracle",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-B) — five kept_detector lanes phase v0.1.60
    # CANNOT structure (spec / rules-lawyer verified: the discriminant is DROPPED in
    # the parse — a cost-reduction-per-target operand, a protective-vs-stax restriction
    # split, the out-of-game zone, or a becomes-target trigger flattened to
    # event='other'). Each fires from a dedicated IR-path word mirror reproducing the
    # deleted _HAND_FLOOR / SWEEP regex (the secret_writedown mirror INTENTIONALLY
    # drops the deleted regex's "|your sideboard" arm — companion reminder text owned
    # by companion_keyword, not a wishboard build-around — so it is a NARROWER, correct
    # A-B, not a regression). floor-mirror-dep == 0 by construction (none is a floor
    # detector). All scope 'you'.
    #   • per_target_payoff   ← Hinata's YOUR-arm cost reduction scaling with target
    #     count; the IR has no mana_cost / cost-reduction model and no per-spell
    #     target-count operand, so the arm is dropped entirely (CR 601 / 118).
    #   • sacrifice_protection ← phase parses only ~21/39 as a generic restriction
    #     (indistinguishable from a STAX restriction — Ghostly Prison) and drops ~18/39
    #     buried in a quoted/granted ability; the two literal protective phrases are
    #     the only full-coverage tell (CR 701.16).
    #   • secret_writedown    ← the out-of-game zone (CR 408.1 Wish) + pre-game secret
    #     name/choose; phase's in-game battlefield IR models neither.
    #   • target_own_payoff   ← Monk Gyatso's becomes-target may-reaction on YOUR
    #     creatures; the becomes-target event flattens to event='other' (no
    #     becomestarget trigger mode), so the may-clause survives only in raw.
    #   • target_redirect     ← Rayne's becomes-target-of-opponent → draw payoff;
    #     same event='other' flattening (the redirect SERVE pool is structural via
    #     category=='redirect' but the DETECTION payoff is not). CR 603.
    (
        "per_target_payoff",
        re.compile(r"less (?:to cast )?for each (?:of those )?target", re.IGNORECASE),
        "you",
    ),
    (
        "sacrifice_protection",
        re.compile(r"can't cause you to sacrifice|can't be sacrificed", re.IGNORECASE),
        "you",
    ),
    (
        "secret_writedown",
        re.compile(
            r"secretly (?:write|choose|name)"
            r"|before the game begins[^.]*(?:write|name|choose)"
            r"|from outside the game",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "target_own_payoff",
        re.compile(
            r"creature you control becomes the target[^.]*you may", re.IGNORECASE
        ),
        "you",
    ),
    (
        "target_redirect",
        re.compile(
            r"becomes? the target of a spell or ability an opponent controls[^.]*draw",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-C) — four kept_detector lanes phase v0.1.19
    # CANNOT structure (spec / rules-lawyer verified: the discriminant is DROPPED or
    # only partially structured), so each fires from a dedicated IR-path word mirror
    # reproducing the deleted regex EXACTLY (full-text == per-clause over the commander-
    # legal corpus — each regex is clause-safe, A-B==0). floor-mirror-dep == 0 by
    # construction (the kept mirror is not a floor detector).
    #   • targeting_matters ← phase structures the HEROIC / cast-that-targets half as a
    #     Targets predicate on the cast_spell trigger subject, but the BECOMES-TARGET
    #     trigger flattens to event='other' (no becomestarget mode). Mirroring the whole
    #     deleted SWEEP regex (heroic + becomes-target + cast-that-targets) is byte-
    #     identical (A-B==0) and simplest; the becomes-target half is the irreducible
    #     part. CR 702.83 (heroic) / 115.6 (targeting). Serve hand-registered.
    #   • theft_protection ← Kira's granted "for the first time each turn, counter" ride
    #     phase parses as a grant carrier + a counter_spell effect, but the once-per-
    #     turn becomes-target gate is NOT structured. The exact phrasing survives only
    #     on the oracle. Single/dual-card sticky-theft shield. CR 702.x.
    #   • villainous_choice ← a real, printed keyword action (AFR/WHO/Marvel) phase
    #     routes to a GENERIC 'choose' Effect (too broad to key on); the literal phrase
    #     is the only clean discriminator. The Valeyard DOUBLES them; Davros/Missy
    #     present them. Scanning oracle text (not just effect.raw) covers the dropped-
    #     parse tail (Genesis of the Daleks). CR 701.x.
    #   • named_counter_misc ← the closed named-counter set (egg/divinity/prey/bounty/
    #     bribery/page/study/knowledge/silver/gold/fate/incubation). phase's structured
    #     counter_kind field covers 32 of 34 cards, but a place/remove-as-COST or
    #     replacement form (Mazemind Tome's "Put a page counter" cost, Pursuit of
    #     Knowledge's "Remove three study counters" cost / "may put a study counter
    #     instead" replacement) folds the counter into the consuming ability and DROPS
    #     counter_kind — a genuine 2-card recall gap. So mirror the exact deleted regex
    #     (byte-identical, no recall gap) rather than ride the partial structural field.
    #     CR 122.1 (same-NAME counters interchange — the kind IS the discriminant).
    (
        "targeting_matters",
        re.compile(
            r"becomes the target of a spell or ability"
            r"|whenever [^.]{0,60}?becomes? the target of|\bheroic\b"
            r"|whenever you cast (?:an instant or sorcery spell |a spell )?"
            r"that targets",
            re.IGNORECASE,
        ),
        "any",
    ),
    (
        "theft_protection",
        re.compile(r"for the first time each turn, counter", re.IGNORECASE),
        "you",
    ),
    ("villainous_choice", re.compile(r"villainous choice", re.IGNORECASE), "you"),
    (
        "named_counter_misc",
        re.compile(
            r"\b(?:egg|divinity|prey|bounty|bribery|page|study|knowledge"
            r"|silver|gold|fate|incubation) counters?\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    # cmdzone_ability (ADR-0027) — the STATIC-Eminence half phase drops the
    # condition for (The Ur-Dragon: "As long as ~ is in the command zone … cost {1}
    # less"). The triggered/activated halves fire structurally in extract_signals_ir
    # (the 'command' ability-zone / condition-zone arm); this mirror reproduces the
    # exact deleted SWEEP regex over the joined face so the static cost-reducer/
    # anthem still opens the lane. The struct arm plus this mirror is byte-identical
    # to the deleted regex on the commander-legal corpus (0 gap, 0 over-fire).
    # CR 702.107.
    (
        "cmdzone_ability",
        re.compile(
            r"is (?:on the battlefield or )?in the command zone"
            r"|activate this ability only if[^.]*command zone",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 β — edict_matters. The structural opp/each `sacrifice` arm in
    # extract_signals_ir is broader-and-correct (it reads Annihilator's reminder-only
    # "defending player sacrifices" and the modal "those players sacrifice", +28 over
    # the regex), but phase under-parses a 76-card tail (a sacrifice clause it folds
    # into a categoryless / mis-scoped effect, a DFC back face). Recover it from the
    # EXACT deleted SWEEP regex over the joined-face oracle. The arms never cross a
    # sentence (`[^.]`-only), so full-text search == per-clause (verified diff=0 vs the
    # deleted floor path); the add() dedup unions this with the structural arm. scope
    # "each" matches the deleted SWEEP row so the firing identity is byte-identical.
    (
        "edict_matters",
        re.compile(
            r"each opponent sacrifices|whenever an opponent sacrifices"
            r"|target opponent sacrifices|each player sacrifices"
            r"|(?:each player|that player|each opponent|target player"
            r"|target opponent) sacrifices? (?:a|an|two|\d+|half)"
            r"|that player sacrifices|controller sacrifices",
            re.IGNORECASE,
        ),
        "each",
    ),
    # DEFERRED: kicked_spell_matters (\bkicked\b matches every "if kicked" card,
    # +171 — the lane is the PAYOFF "whenever you cast a kicked spell", not having
    # kicker). Needs a narrower payoff/keyword source.
    # ADR-0027 β — legend_rule_off: phase's `legend_exempt` Effect is a strict SUBSET
    # of the regex (2 of 8: only the unbounded "the legend rule doesn't apply" —
    # Mirror Gallery, Brothers Yamazaki). The bounded-scope variant ("doesn't apply
    # to permanents/tokens/Slivers/Spiders you control" — Mirror Box, Cadric, Sliver
    # Gravemother, Spider-Verse, The Master, Sakashima) is DROPPED by phase entirely,
    # so there is NO structural form to read. A byte-identical kept mirror of the
    # exact deleted SWEEP regex recovers all 8 (commander-legal corpus: regex==mirror
    # ==8, 0 lost, 0 over-fire). CR 704.5j.
    (
        "legend_rule_off",
        re.compile(r"the .legend rule. doesn't apply", re.IGNORECASE),
        "you",
    ),
    # ADR-0027 β — timing_control: phase drops the cast-timing statics ("cast spells
    # only any time they could cast a sorcery" — Teferi; "cast spells only during
    # their own turns" — City of Solitude; Fires of Invention) entirely (it keeps
    # only the flash-grant), so there is NO structural form to read. A byte-identical
    # kept mirror of the exact deleted SWEEP regex recovers all 5 (commander-legal
    # corpus: regex==mirror==5, 0 lost, 0 over-fire). scope "any" matches the deleted
    # SWEEP row so the firing identity is byte-identical. CR 117.1a / 307.1.
    (
        "timing_control",
        re.compile(
            r"cast spells (?:and activate abilities )?only during their own"
            r"|spells? only any time they could cast a sorcery"
            r"|can cast spells only",
            re.IGNORECASE,
        ),
        "any",
    ),
    # ADR-0027 β — creature_ping + damage_equal_power kept mirrors. The structural
    # recipient/doer arm in extract_signals_ir (the op="power" damage anchor) is the
    # broader-and-correct producer; these byte-identical mirrors of the EXACT deleted
    # SWEEP regexes recover the projection-gap tail phase can't reach (emblem-quoted
    # grants, dungeon-room rows, "Chapter 3" / empty-raw effects, cards with no
    # op="power" projected). Verified byte-identical over the commander-legal corpus:
    # the mirror (full-text over kept_oracle) reproduces the regex path's firing set
    # exactly (creature_ping 120==120, damage_equal_power 173==173, full-only==0,
    # regex-only==0; per-clause is also exact, the regexes' `[^.]*` arms never cross a
    # sentence). scope "you" matches the deleted SWEEP rows so the firing identity is
    # byte-identical. add() dedups the overlap with the structural arm. CR 119.3.
    (
        "creature_ping",
        re.compile(CREATURE_PING_REGEX, re.IGNORECASE),
        "you",
    ),
    (
        "damage_equal_power",
        re.compile(DAMAGE_EQUAL_POWER_REGEX, re.IGNORECASE),
        "you",
    ),
    # ADR-0027 β — cost_reduction NARROWED kept-mirror (see _COST_REDUCER_MIRROR above).
    # The structural arm fires from the projection's cost_reduction Effects; this mirror
    # recovers the genuine build-around reducers project.py drops (ability-cost
    # reducers, the Defiler conditional cycle, granted/donor reducers, named special-
    # cost reducers, and the Chapter-3 / empty-raw tail). NOT byte-identical: the
    # deleted regex was
    # direction-agnostic + self-blind, so the mirror is narrowed to only genuine "cost
    # ... less" reducers of OTHER spells/abilities (0 cost-increase false positives; the
    # 92 "this spell costs ... less" self-discounts stay correctly dropped). scope "you"
    # matches the deleted producer; add() dedups the overlap with the structural arm.
    (
        "cost_reduction",
        _COST_REDUCER_MIRROR,
        "you",
    ),
    # ADR-0027 β — debuff_matters byte-identical kept-mirror (two rows, one per deleted
    # producer). The structural arm fires from the projection's negative-pump / m1m1
    # Effects (recall GAIN), but the big "gets -N/-N until end of turn" / "-X/-X" tail
    # projects as a pump / pump_target Effect with amount==None (the value only in raw),
    # so there is no structural number to read. These two mirrors reproduce the deleted
    # regex path EXACTLY: as a full-text .search over the reminder-stripped joined-face
    # oracle they fire on the identical 613-card commander-legal set the per-clause
    # regex path did (0 drift both directions). scope matches each deleted producer
    # (SWEEP "any", Maha "you"); add() dedups the overlap with the structural arm.
    (
        "debuff_matters",
        re.compile(DEBUFF_SWEEP_REGEX, re.IGNORECASE),
        "any",
    ),
    (
        "debuff_matters",
        re.compile(DEBUFF_MAHA_REGEX, re.IGNORECASE),
        "you",
    ),
    # ADR-0027 β — pump_matters byte-identical kept-mirror. Unlike debuff_matters (a
    # sign-discriminated `pump` factor<0 structural arm + a tail mirror), pump_matters
    # has NO structural arm: the v9 projection drops the value of every target-creature
    # pump to amount==None (the +N/+N lives only in the raw) and carries no temporal
    # marker, so a +N/+N combat trick is structurally indistinguishable from a -1/-1
    # debuff and a permanent buff. The only clean positive-single-target structural form
    # phase carries (a positive-factor pump on an EnchantedBy/EquippedBy subject) is the
    # SEPARATE voltron/suit-up lane, so a structural arm would be 100% scope-creep. So
    # this single mirror IS the lane: a full-text .search over the reminder-stripped
    # joined-face oracle reproduces the deleted per-clause SWEEP path EXACTLY (the regex
    # arms are all clause-local, so full-text == per-clause; 0 drift both directions →
    # ir_only == 0, regex_only == 0). scope "you" matches the deleted SWEEP row.
    (
        "pump_matters",
        re.compile(PUMP_MATTERS_REGEX, re.IGNORECASE),
        "you",
    ),
)

# Cares-about floor lanes the IR path also runs. A `<mechanic>_matters` lane means
# "this card cares about / combos with X", so it must fire for PAYOFFS, not just the
# doers — and those payoffs are textual references with no structural IR form (Ixidor
# "face-down creatures get +1/+1", a Clue payoff, "creatures you control with a
# counter"). So reuse the production floor Detector objects for this CURATED subset
# (the facedown_matters fix, generalized — see feedback memory). DELIBERATELY EXCLUDES
# the broad foundational / doer lanes (graveyard/counters/removal/pump/ramp/draw/…):
# their regex-only is genuine IR-STRUCTURING work the signal_diff harness must keep
# surfacing, not textual cares-about gaps. add() dedups overlap with IR categories.
_IR_FLOOR_LANES: frozenset[str] = frozenset(
    {
        # token-type synergy
        "clue_matters",
        # food_matters / treasure_matters removed — ADR-0027 migrated them to the Card
        # IR (the generalized blood_matters widening: Food/Treasure-subtype make_token
        # makers incl. the die-roll/vote/choice branch + Aftermath-DFC recovery, a
        # "Sacrifice a Food/Treasure" SAC PAYOFF, and a `token_subtype_ref` "Foods/
        # Treasures you control" cares-about marker). Removed from _IR_FLOOR_LANES;
        # floor-mirror-dep == 0. Their _HAND_FLOOR detectors are deleted; serve specs
        # survive. clue_matters keeps its floor (its "investigate" arm has no structural
        # IR form yet).
        # blood_matters removed — ADR-0027 migrated it to the Card IR (Blood-subtype
        # makers + the sacrifice-Effect/Trigger subject widening + the choose-list /
        # granted-ability maker recovery), so it fires from the STRUCTURAL IR alone
        # and no longer needs the floor mirror. Its _HAND_FLOOR detector is deleted.
        # counter-type synergy (distinct from the +1/+1 counters_matter doer lane)
        # poison_matters removed — ADR-0027 migrated it to the Card IR (the
        # infect/toxic/poisonous Scryfall keywords + a kept word mirror for the
        # GRANTERS / "poison counter" / "has toxic" refs phase folds into a grant
        # carrier's raw). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR gone.
        # oil_counter_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # place_counter(counter_kind='oil') placer + an `_OIL_REF` payoff marker for the
        # count-operand/condition phase drops). Its SWEEP_DETECTORS row is deleted.
        "shield_counter_matters",
        # rad_counter_matters removed — ADR-0027 migrated it to the Card IR (the
        # `rad_counter` effect / rad place_counter + a "rad counter(s)" face marker).
        # resource / devotion
        # energy_matters removed — ADR-0027 migrated it to the Card IR (phase's `energy`
        # effect + a {e} face marker for the sinks/payoffs/doublers phase loses).
        # devotion_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="devotion" count operand + a "devotion to <color>" kept word
        # mirror for the cost-reduction / counterspell-tax forms phase doesn't make a
        # count operand). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR gone.
        # type / tribe / permanent-shape synergy
        "vehicles_matter",
        "island_matters",
        # legends_matter removed — ADR-0027 migrated it to the Card IR (the
        # HasSupertype:Legendary subject-Filter predicate + a kept word mirror merging
        # both _HAND_FLOOR rows for the cost-reduction / target-legendary / cast-
        # legendary / search refs phase leaves textual). Moved floor->kept (floor-
        # mirror-dep -> 0); both _HAND_FLOOR producers deleted.
        # changeling_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # changeling keyword + a "changeling" / "is every creature type" marker). Its
        # SWEEP_DETECTORS row is deleted.
        # colorless_matters / multicolor_matters removed — ADR-0027 migrated them to the
        # Card IR (the ColorCount subject-Filter predicate build-arounds +
        # _IR_KEPT_DETECTORS word mirrors for the "cast a multicolored spell" trigger /
        # "colorless spell/creature" cost-reduction refs that aren't a structured
        # subject). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR rows deleted.
        # lands_matter removed — ADR-0027 migrated it to the Card IR (the
        # amount.subject=Land count operand + a kept word mirror for the "P/T equal to
        # the number of lands you control" / "for each land you control" forms phase
        # emits as characteristic_pt/pump_target but DROPS the count operand). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        "superfriends_matters",
        "modified_matters",
        # low_power_matters removed — ADR-0027 migrated it to the Card IR (the
        # Power:LE/LT predicate read + a `_LOW_POWER_REF` marker rebuilding the dropped
        # subject from "creatures you control with power N or less").
        "power_matters",
        # historic_matters removed — ADR-0027 migrated it to the Card IR (the
        # "Historic" subject-Filter predicate + a "\bhistoric\b" kept word mirror for
        # the cost-reduction / "play a historic" / type-group refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # domain_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="domain" count operand + a "\bdomain\b|basic land types" kept word
        # mirror for the cost-reduction / condition / ability-word refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); SWEEP row deleted.
        # party_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="party" count operand + a _IR_KEPT_DETECTORS word mirror for the
        # "full party" CONDITION + "creatures in your party" non-count refs). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # commander_matters removed — ADR-0027 migrated it to the Card IR (the
        # IsCommander subject-Filter predicate + a kept word mirror for the Background
        # grants / "commander damage" / "your commander costs less" refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); SWEEP row deleted.
        # mechanic / keyword synergy
        "arcane_matters",
        "daynight_matters",
        # saga_matters removed — ADR-0027 migrated it to the Card IR (a `_SAGA_REF`
        # "lore counter" / "Saga you control" dropped-static face marker; the reminder-
        # stripped anchor excludes a vanilla Saga's intrinsic advancement, mirroring the
        # deleted SWEEP regex). Its SWEEP_DETECTORS row is deleted.
        # initiative_matters removed — ADR-0027 migrated it to the Card IR (a
        # "\bthe initiative\b" _IR_KEPT_DETECTORS word mirror; phase v0.1.19 doesn't
        # structure the CR 720 initiative designation). Moved floor->kept
        # (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # cycling_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `cycled` trigger + a `cycling_payoff` marker for the "cycle or discard" payoff
        # phase flattens to event='other' or truncates the trigger off entirely). Its
        # _HAND_FLOOR detector is deleted.
        "station_matters",
        "void_warp_matters",
        # speed_matters removed — ADR-0027 migrated it to the Card IR (phase's `speed`
        # doer + a "start your engines|max speed|your speed" kept word mirror; phase
        # v0.1.19 doesn't structure the CR 702.178/702.179 Speed designation). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        "stickers_matter",
        # attractions_matter removed — ADR-0027 migrated it to the Card IR (a
        # "\battraction\b|open an attraction" kept word mirror; phase v0.1.19 doesn't
        # structure the CR 717 Attraction designation). Moved floor->kept
        # (floor-mirror-dep -> 0); its SWEEP_DETECTORS row is deleted (serve stays).
        # suspect_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `suspect` effect + a verb/"suspected" face marker; the marker's "(?! counter)"
        # excludes Investigator's Journal's "suspect counter" same-named counter type).
        # venture_matters removed — ADR-0027 migrated it to the Card IR (the venture/
        # take-initiative effect + a completedadungeon/isinitiative condition read +
        # a trigger_doubling-over-dungeons read + a venture/complete-a-dungeon marker).
        # foretell_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # foretell keyword + the "has foretell"/"you foretell" marker, plus the
        # Foretold-predicate payoff bind (Niko) and the "to foretell" enabler marker
        # (Karfell)), so it no longer needs the regex floor (its _HAND_FLOOR detector
        # is deleted).
        # phasing_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # phasing keyword + the phase-out/in DOER markers, plus the event='other'
        # "permanents phase out" payoff-trigger marker (The War Doctor)), so it no
        # longer needs the regex floor (its SWEEP_DETECTORS row is deleted).
        # ring_matters removed — ADR-0027 migrated it to the Card IR (structural
        # ring_tempt effect, including the event='other' tempt trigger + the
        # Ring-bearer raw-scan), so it no longer needs the regex floor (its
        # _HAND_FLOOR detector is deleted).
        # convoke_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # convoke keyword + cast_with_keyword counter_kind='convoke' granters +
        # grant_spell_ability/cast-trigger convoke-raw markers), so it no longer needs
        # the regex floor (its SWEEP_DETECTORS row is deleted).
        # affinity_type removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # affinity keyword + an `affinity` marker effect for the conferred "spells you
        # cast have affinity for X" granters), so it no longer needs the regex floor
        # (its SWEEP_DETECTORS row is deleted).
        # cascade_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # cascade keyword + a `_CASCADE_GRANT` conferral/reference marker). Its
        # _HAND_FLOOR detector is deleted.
        # undying_persist_matters removed — ADR-0027 migrated it to the Card IR (the
        # Scryfall undying/persist keywords + a `_UNDYING_PERSIST_GRANT` grant marker);
        # the "\bundying\b" floor over-fired on the "Undying Flames" card NAME, which
        # the structural IR correctly drops. Its _HAND_FLOOR detector is deleted.
        # myriad_grant removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # myriad keyword + grant_keyword counter_kind='myriad' granters + a copy-
        # exception conferred marker), so it no longer needs the regex floor (its
        # SWEEP_DETECTORS row is deleted; the "\bmyriad\b" floor over-fired on the
        # "The Myriad Pools" card NAME, which the IR correctly drops).
        # suspend_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # `suspend` keyword + a kept word mirror folding in the SWEEP \bsuspend\b and
        # widening to the time-counter superstructure — time travel / Vanishing /
        # Impending — phase doesn't structure). Moved floor->kept (floor-mirror-dep
        # -> 0); _HAND_FLOOR row + SWEEP_DETECTORS \bsuspend\b row deleted.
        # monarch_matters removed — ADR-0027 migrated it to the Card IR (structural
        # monarch effect + ismonarch condition), so it no longer needs the regex
        # floor (its _HAND_FLOOR detector is deleted).
        # madness_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # madness keyword + the "has madness" grant marker + the "if it has madness"
        # payoff marker (Anje)); the "\bmadness\b" floor over-fired on the "Crown of
        # Madness" ability word (CR 207.2c — Bloodboil Sorcerer), which the structural
        # IR correctly excludes. Its _HAND_FLOOR detector is deleted.
        # dice_matters removed — ADR-0027 migrated it to the Card IR (phase's native
        # roll_die effect + a `roll_die` marker for the "whenever you roll" payoff
        # trigger / "Roll two d6 and choose" spell / "Roll a d8:" cost / "reroll" phase
        # keeps only in raw). Its _HAND_FLOOR + SWEEP_DETECTORS rows are deleted.
        # exalted_lone_attacker removed — ADR-0027 migrated it to the Card IR (the
        # Scryfall `exalted` keyword + an "attacks alone|\bexalted\b" kept word mirror
        # for the attacks-alone payoff triggers + "X have exalted" grants phase leaves
        # textual; CR 702.83). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR
        # row deleted.
        # crimes_matter removed — ADR-0027 migrated it to the Card IR (phase's
        # commit_crime trigger event + a `crime` condition-form marker for the
        # "(if|as long as) you've committed a crime" payoff phase has no kind for).
        # scry_surveil_matters removed — ADR-0027 migrated it to the Card IR (the
        # scried/surveiled trigger events + the event='other' scry/surveil payoff
        # marker, plus the "if you would scry a number of cards" replacement marker
        # (Kenessos, Eligeth)), so it no longer needs the regex floor (its _HAND_FLOOR
        # detector is deleted).
        # regenerate_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `regenerate` effect + a `_REGENERATE_REF` granted/quoted/replacement marker).
        # Its _HAND_FLOOR detector is deleted.
        # spell-pattern / count payoffs
        "second_spell_matters",
        "kicked_spell_matters",
        "big_hand_matters",
        "cast_from_exile",
        "exile_matters",
        # starting_life_matters removed — ADR-0027 migrated it to the Card IR (a
        # `_STARTING_LIFE_REF` "starting life total" compare marker, CR 103.4). The
        # broad regex over-fired on unrelated life thresholds (Elderscale Wurm,
        # Sigarda's Splendor), which the tight IR marker drops. Its SWEEP row is gone.
        "theft_matters",
        # mass_death_payoff removed — ADR-0027 migrated it to the Card IR (a
        # `_MASS_DEATH_REF` "creatures that died this turn" count-operand marker). Its
        # _HAND_FLOOR detector is deleted.
        "noncombat_damage_payoff",
        "land_sacrifice_matters",
    }
)

# Keys the keyword-array detectors emit (reused verbatim by the IR path, same
# Scryfall source as the regex path → perfect parity).
_IR_KEYWORD_KEYS: frozenset[str] = (
    frozenset(key for key, _scope in _PRESET_KEYWORD_SIGNALS.values())
    | frozenset(key for key, _scope in _DIRECT_KEYWORD_SIGNALS.values())
    | frozenset(k for pairs in _IR_KEYWORD_MAP.values() for k, _s in pairs)
)

IR_SLICE_KEYS: frozenset[str] = (
    frozenset(
        {
            "creatures_matter",
            "lifegain_matters",
            "graveyard_matters",
            signal_keys.TOKEN_MAKER,
            "death_matters",
            # Batch 1 (aristocrats/recursion):
            "self_death_payoff",
            "reanimator",
            # Batch 2b (special-cased doer):
            "direct_damage",
            # Batch 3 (tribal — oracle-ability subjects; type_line membership is a
            # structured-field lookup reused at A4, so REGEX_ONLY here = membership):
            signal_keys.TYPE_MATTERS,
            # Batch K (type_line membership):
            "artifacts_matter",
            "enchantments_matter",
            # Batch E (effect-category lanes):
            "counters_matter",
            "minus_counters_matter",
            "oil_counter_matters",
            "shield_counter_matters",
            "rad_counter_matters",
            "ki_counter_matters",
            "counter_control",
            "fight_matters",
            "ramp_matters",
            "group_mana",
            "blink_flicker",
            "draw_for_each",
            "group_hug_draw",
            "symmetric_damage_each",
            "opponent_discard",
            "sacrifice_matters",
            "donate_matters",
            "land_exchange",
            "land_destruction",
            "kill_engine",
            "removal_matters",
            "exile_removal",
            "opponent_exile_matters",
            "tap_down",
            "scaling_pump",
            "lands_matter",
            "treasure_matters",
            "clue_matters",
            "food_matters",
            "blood_matters",
            "creature_recursion",
            # Batch T (trigger-event lanes):
            "tap_untap_matters",
            "discard_matters",
            "draw_matters",
            "creature_etb",
            "combat_damage_matters",
            # ADR-0027 β — tribe_damage_trigger (is_widen_of combat_damage_matters):
            # a byte-identical _IR_KEPT_DETECTORS mirror of the deleted SWEEP regex
            # ("your creatures connect for combat damage → reward").
            "tribe_damage_trigger",
            # ADR-0027 β — combat_damage_to_creature + combat_damage_to_opp (both
            # is_widen_of combat_damage_matters): byte-identical _IR_KEPT_DETECTORS
            # mirrors of the deleted SWEEP regexes, recipient-discriminated by the
            # joined-face oracle ("to a creature" vs "to a player/opponent") since
            # phase drops valid_target's recipient TYPE onto the combat_damage trigger.
            "combat_damage_to_creature",
            "combat_damage_to_opp",
            # ADR-0027 β — damage_to_opp_matters (is_widen_of combat_damage_matters):
            # the GENERAL (any-source, ANY damage) "deals damage to a player/opponent"
            # connect-payoff. A STRUCTURAL arm reads project's DamageToPlayer recipient
            # marker (SIDECAR v13) PLUS a byte-identical _IR_KEPT_DETECTORS mirror of
            # the deleted HAND_FLOOR regex for the granted-ability / ETB-burst tail.
            "damage_to_opp_matters",
            "creature_cast_trigger",
            signal_keys.TYPED_SPELLCAST,
            # Batch P (phase-native mechanic effects):
            "monarch_matters",
            "suspect_matters",
            "venture_matters",
            "connive_matters",
            "damage_prevention",
            # Batch ST (static restriction → stax):
            "stax_taxes",
            "symmetric_stax",
            # Batch R (v0.1.60 replacement-effect doublers, split by event):
            "token_doubling",
            "counter_doubling",
            "damage_doubling",  # Batch 10
            # Batch 0 — scope-gated lane (not in the _DOER table):
            "hand_disruption",
            # Batch 1 — scope-gated cycling payoff (not in _PAYOFF_TRIGGER_KEYS):
            "cycling_matters",
            # Batch 14 — landfall (a land-ETB trigger; CR 207.2c ability word):
            "landfall",
            # Batch 9 — cheat a creature into play (library/hand → battlefield):
            "cheat_into_play",
            # Batch 2 — cost-based + Filter-predicate lanes:
            "life_payment_insurance",
            "legends_matter",
            "historic_matters",
            "commander_matters",  # Batch 15
            # Digital mechanic that was mis-skipped — phase parses Seek (Alchemy
            # DD3, now in rules-lawyer's digital supplement).
            "seek_matters",
            # Kept narrow detectors — real mechanics phase doesn't structure
            # (rules-lawyer-verified): voting (CR 701.38); the four distinct
            # bending keywords (airbend CR 701.65, earthbend 701.66, waterbend
            # 701.67, firebending 702.189) — each its own lane, never conflated.
            "voting_matters",
            "airbend_matters",
            "earthbend_matters",
            "waterbend_matters",
            "firebending_matters",
            # Batch 16 — recent-set kept-detectors (rules-lawyer-verified):
            "celebration_matters",
            "coven_matters",
            "outlaw_matters",
            "lessons_matter",
            "snow_matters",  # Batch 18 — real (CR 205.4), not a skip
            # Batch 8 — named scaling-operand lanes:
            "devotion_matters",
            "party_matters",
            "domain_matters",
            # Batch 11 — opponent-draw punisher (player-event scope):
            "opponent_draw_matters",
            # Batch 6 — grant_keyword team-anthem lanes (gated; flash_grant deferred):
            "team_evasion_grant",
            "protection_grant",
            "all_creatures_kw_grant",
            # ADR-0027 β — keyword_grant_target: a keyword grant to a SINGLE TARGET
            # creature (the v14 single_target_grant marker — project._single_target_
            # keyword_grant_markers). Distinct from the team/anthem grant lanes above.
            "keyword_grant_target",
            # ADR-0027 β — activated_ability: a card whose engine is a MEANINGFUL
            # activated ability (the {T}:/{Q}: or generic-mana-cost ability). The arm
            # gates on is_mana_ability (Mana effect → 'ramp', dropped) + the SIDECAR-v15
            # 'genericmana' cost token so the land/rock/dork flood is impossible.
            "activated_ability",
            # Batch 2 (per-lane) — discard OUTLET cost (self-discard split out):
            "discard_outlet",
            # Batch 2 (per-lane) — top-of-library stacking (position-gated):
            "topdeck_stack",
            # Batch 5 — predicate-enriched color/power build-around lanes:
            "multicolor_matters",
            "colorless_matters",
            "power_matters",
            "low_power_matters",
            "color_hoser",
            # Batch 12 — negation/disjunction composite-filter lanes
            # (noncreature_cast_punish DEFERRED — phase scope can't split it from
            # prowess; see the cast_spell arm):
            "nonhuman_attackers",
            "typed_anthem_multi",
            # Batch 13 — combat-forcing statics (split out of stax):
            "forced_attack",
            "cant_block_grant",
            "lure_matters",
            # Batch 17 — DoubleTriggers static (Yarok / Panharmonicon):
            "trigger_doubling",
            # Batch 6 (unblocked) — flash_grant via CastWithKeyword{Flash}:
            "flash_grant",
            # Batch 5 (unblocked) — named-permanent via deck_copy_limit:
            "named_permanent",
            # Deferred-sweep: evasion-denial (IgnoreLandwalk); clone_matters still
            # deferred (regex 1611 vs IR 70 — needs the 1541 audited first):
            "evasion_denial",
            "base_pt_set",
            # Co-occurrence lanes (trigger + effect in one ability):
            "combat_buff_engine",
            "damage_reflect",
            # Clone hierarchy: creature-copy (clone_matters) + per-permanent-type
            # copy lanes (a Permanent copy fans out to all of these + copy_permanent):
            "clone_matters",
            "copy_artifact",
            "copy_enchantment",
            "copy_land",
            "copy_planeswalker",
            "copy_permanent",
            # Spell-copy (Twincast/Fork) — separate from clone:
            "spell_copy_matters",
            # ADR-0027 tranche2-C — structural IR-arm lanes (recast_etb also rides
            # the Scryfall `sneak` keyword via _IR_KEYWORD_KEYS):
            #   exert_matters   ← grant_keyword/vigilance over a generic creature board
            #                     (the team-vigilance enabler) + the Johan kept mirror.
            #   self_pump       ← an ACTIVATED pump_target / place_counter(p1p1) on the
            #                     self (firebreathing / Walking Ballista mana sink).
            #   tapper_engine   ← a tap Effect with a target subject + a "doesn't
            #                     untap" restriction raw (the repeatable tapper).
            #   count_anthem    ← a team +N/+N anthem scaling with a board count
            #                     (Hold the Gates / Commander's Insignia).
            "exert_matters",
            "self_pump",
            "tapper_engine",
            "count_anthem",
            # ADR-0027 tranche2 (t2b2-A) — structural grant/bounce/exile IR arms:
            #   aura_equip_kw_grant   ← grant_keyword of an evergreen kw over a YOUR
            #                           Aura/Equipment subgroup subject (Rashel).
            #   counter_grants_kw     ← grant_keyword over a YOUR-creature subject with
            #                           the `Counters` predicate (Bramblewood Paragon).
            #   conditional_self_protection ← a STATIC ability with a condition
            #                           granting a protective kw to ITSELF (Ojutai,
            #                           Zurgo, Kaito).
            #   control_exchange      ← exile a YOU-OWN subject paired with a
            #                           to:battlefield return (Meneldor, Neutrinos,
            #                           Aminatou) — inverse of the exile_removal Owned
            #                           exclusion.
            #   bounce_tempo          ← a `bounce` Effect, no graveyard zone, subject
            #                           not controller='you' (Boomerang…Cyclonic Rift).
            "aura_equip_kw_grant",
            "counter_grants_kw",
            "conditional_self_protection",
            "control_exchange",
            "bounce_tempo",
            # ADR-0027 tranche2-B (counters / O-Ring lanes):
            #   counter_manipulation ← counter_move/remove_counter effect (p1p1/m1m1)
            #                          + a kept cost-clause word mirror.
            #   counter_place_trigger ← a counter_added TRIGGER (scope!=opp, non-Saga).
            #   counter_replace_bonus ← the counter_doubling replacement category
            #                           (+ the place_counter(plus) temporary tail).
            #   exile_until_leaves   ← _is_exile_until_leaves (inline phrase OR the
            #                          two-ability linked-return shape) + Saga mirror.
            "counter_manipulation",
            "counter_place_trigger",
            "counter_replace_bonus",
            "exile_until_leaves",
            # ADR-0027 tranche2-C (batch C) — structural IR-arm lanes:
            #   extra_land_drop      ← cheat_play / topdeck_select with a Land subject
            #                          + a YOUR-anchored kept word mirror.
            #   free_creature_payoff ← an ETB trigger whose condition tree carries a
            #                          manaspentcondition (Satoru the Infiltrator).
            #   keyword_counter      ← a place/remove of a CR-122.1b keyword counter
            #                          + a kept word mirror for the choice/multi tail.
            "extra_land_drop",
            "free_creature_payoff",
            "keyword_counter",
            # ADR-0027 tranche2-batch-3-A — land-animation + keyword-soup lanes:
            #   land_denial          ← phasing Effect, Land/you subject (Taniwha).
            #   keyword_soup         ← >=5 distinct evergreen grant_keyword cks/ability
            #                          + a kept oracle mirror for the under-parse tail.
            #   land_creatures_matter / land_protection ← the shared land-animator
            #                          predicate + Land+Creature anthem/maker subjects
            #                          + a kept oracle mirror for the dropped manlands.
            "land_denial",
            "keyword_soup",
            "land_creatures_matter",
            "land_protection",
            # ADR-0027 tranche2-B-3 (batch C) — structural IR-arm lanes:
            #   spell_keyword_grant  ← the whole cast_with_keyword category (umbrella
            #                          over flash_grant / convoke_matters).
            #   target_player_draws  ← a draw effect with scope=='any' (directed/forced
            #                          draw, not a self-cantrip).
            # (self_counter_grow was DEFERRED — a genuine floor-disabled IR-vs-regex
            # recall gap, not 100% over-fire: it drops 14 subjNone p1p1 placements whose
            # raw lacks the self-anchor — Saga chapters, adapt/monstrosity.
            # timing_control and token_copy_matters later MIGRATED via byte-identical
            # kept-mirrors: phase drops the 2 Teferi cast-timing statics wholesale, and
            # its structural CopyTokenOf/Populate effect 100%-over-fires the token-copy
            # lane with reminder-text self-copies (Embalm/Eternalize/Offspring/Double-
            # team) the reminder-stripped regex excludes, so both ride the exact deleted
            # regex.)
            "spell_keyword_grant",
            "target_player_draws",
            # ADR-0027 tranche2-B (t2b3-B) — structural IR-arm lanes:
            #   lose_unless_hand       ← an etb trigger scope=you + a lose_game effect
            #                            (Phage the Untouchable).
            #   opponent_cast_matters  ← a cast_spell trigger scope=opp OR a symmetric
            #                            scope=any/each cast trigger with a punish
            #                            co-effect (Ruric Thar, Mai, Lavinia).
            #   opponent_counter_grant ← a place_counter(bounty/stun) on an opponent's
            #                            permanent — direct opp subject or a co-tap
            #                            effect carrying the opp filter (Mathas, Freeze
            #                            in Place).
            #   power_tap_engine       ← an ACTIVATED ability cost~'tap' + a power-
            #                            scaling effect raw (Marwyn, Selvala, Staff of
            #                            Domination).
            # pump_matters migrated as a byte-identical kept-mirror (UNSTRUCTURABLE: the
            # IR pump/pump_target categories drop the +N/+N value to amount==None and
            # carry no temporal marker, so a positive combat trick can't be told apart
            # from a -1/-1 debuff or a permanent buff structurally; the one clean
            # positive form — EnchantedBy/EquippedBy auras/equipment — is the separate
            # voltron/suit-up lane). See _IR_KEPT_DETECTORS pump_matters row.
            "lose_unless_hand",
            "opponent_cast_matters",
            "opponent_counter_grant",
            "power_tap_engine",
            # ADR-0027 tranche2-batch-4 (t2b4-C) — kept_detector lanes phase v0.1.60
            # cannot structure, each fired from a dedicated IR-path word mirror (the
            # exact deleted regex):
            #   damage_to_you_punish / excess_damage / tap_down_blockers ← flat
            #     _IR_KEPT_DETECTORS rows (clause-safe full-text mirrors).
            #   self_blink ← name-aware _detect_self_blink_fulltext + the
            #     _SELF_BLINK_SWEEP_RE single-target regex run per-clause (both
            #     reproduced byte-identically; no clean structural IR form).
            #   type_change ← the _type_hoser_clause subtype-gated word detector over
            #     the joined oracle (phase drops the protection subtype argument).
            "damage_to_you_punish",
            "excess_damage",
            "self_blink",
            "tap_down_blockers",
            "type_change",
            # ADR-0027 tranche2-batch-4 (t2b4a-A) — structural ETB / predicate arms:
            #   tribal_etb_multi ← an etb trigger with a creature-subtype subject.
            #   typed_enters_punish ← an etb trigger whose consequence burns opponents.
            #   vanilla_matters ← the HasNoAbilities subject-Filter predicate.
            "tribal_etb_multi",
            "typed_enters_punish",
            "vanilla_matters",
            # ADR-0027 tranche2-batch-4a (t2b4a-B) — two structural keys
            # (alt_cost_keyword + partner_background ride _IR_KEYWORD_KEYS below):
            #   win_lose_game  ← win_game/lose_game Effect categories + a kept regex
            #     mirror (scope 'any') for the conferred/quoted-ability tail.
            #   xspell_matters ← HasXInManaCost predicate on a cast_spell trigger
            #     subject + a kept effect-raw hook mirror for the dropped-predicate
            #     tail.
            #   curse_matters  ← a trigger/effect subject Filter subtypes=='Curse' +
            #     a kept regex mirror for the "search for a Curse card" under-parse.
            "win_lose_game",
            "xspell_matters",
            "curse_matters",
            # ADR-0027 tranche2-batch-5 (t2b5-A) — 5 kept_detector lanes phase v0.1.60
            # cannot structure, each fired from a dedicated IR-path word mirror (the
            # exact deleted SWEEP / _HAND_FLOOR regex; the mirror reads the joined-face
            # oracle, so it is byte-identical — A-B==0):
            #   draft_spellbook ← un-CR digital mechanics (draft-a-card / spellbook).
            #   each_mode_player ← the spread-the-modes target-legality constraint phase
            #     drops (a bare 'choose' marker over-fires 1364:8).
            #   flip_self ← the Kamigawa flip phase parses inconsistently.
            #   free_plot ← the Plot alt-cost rewrite (phrase unique to Fblthp).
            #   miracle_grant ← a card that GRANTS miracle to other cards in hand.
            "draft_spellbook",
            "each_mode_player",
            "flip_self",
            "free_plot",
            "miracle_grant",
            # ADR-0027 tranche2-batch-5 (t2b5-B) — kept_detector lanes phase v0.1.60
            # cannot structure; each fires from a dedicated _IR_KEPT_DETECTORS word
            # mirror (the exact deleted regex; secret_writedown drops the companion
            # "your sideboard" arm):
            #   per_target_payoff / sacrifice_protection / secret_writedown /
            #   target_own_payoff / target_redirect.
            "per_target_payoff",
            "sacrifice_protection",
            "secret_writedown",
            "target_own_payoff",
            "target_redirect",
            # ADR-0027 tranche2-batch-5 (t2b5-C) — four kept_detector lanes phase
            # v0.1.19 cannot structure, each fired from a dedicated IR-path word mirror
            # (the exact deleted regex; clause-safe full-text mirrors, A-B==0):
            #   targeting_matters / theft_protection / villainous_choice ← flat
            #     _IR_KEPT_DETECTORS rows.
            #   named_counter_misc ← a flat _IR_KEPT_DETECTORS row (the structural
            #     counter_kind field has a 2-card place/remove-as-cost recall gap, so
            #     the byte-identical word mirror is the migratable home).
            # (powerup_matters rides _IR_KEYWORD_KEYS below — the Scryfall Power-up
            # keyword array, _IR_KEYWORD_MAP['power-up'].)
            "targeting_matters",
            "theft_protection",
            "villainous_choice",
            "named_counter_misc",
            # ADR-0027 cmdzone — an Eminence / command-zone-gated ability. The
            # triggered/activated halves fire from the structural 'command'
            # ability-zone / condition-zone arm; the static cost-reducer half (The
            # Ur-Dragon) rides the byte-identical _IR_KEPT_DETECTORS word mirror.
            # struct plus mirror == the deleted SWEEP regex (0 residual). CR 702.107.
            "cmdzone_ability",
            # ADR-0027 q2-D2 — opp_top_exile: the structural arm (exile scope=='opp' +
            # cast_from_zone scope=='opp', OR exile scope=='opp' + 'in:library') adds 50
            # steal-and-cast cards the regex never reached; a _IR_KEPT_DETECTORS word
            # mirror (the exact deleted regex) covers the name-lock / peek subset phase
            # under-parses (Circu scope=='any'; Scrib Nibblers; granted clauses). The
            # deleted _HAND_FLOOR producer fired scope 'you'.
            "opp_top_exile",
            # ADR-0027 (q2-D3) half-migrations: the GRANT half of flash_matters
            # (cast_with_keyword{flash}) + the OPPONENT-punisher half of
            # noncreature_cast_punish (cast_spell trig scope=='opp' + noncreature
            # subject) bind structurally; the remaining halves ride _IR_KEPT mirrors.
            "flash_matters",
            "noncreature_cast_punish",
            # ADR-0027 β — impulse_top_play: a TEMPORARY exile-the-top-then-play engine.
            # The structural arm (a NON-static cast_from_zone Effect carrying the
            # recovered 'from:library' zone) adds 105 real impulse cards the deleted
            # SWEEP regex never reached (legitimate breadth); a per-clause
            # _IMPULSE_TOP_PLAY_SWEEP_RE mirror (the exact deleted regex) covers the
            # follow-through tail phase folds into a categoryless effect. The ab.kind!=
            # 'static' gate splits it from the SIBLING play_from_top (the static ongoing
            # permission — Future Sight, Bolas's Citadel — which stays DEFERRED on
            # regex: phase's supplement creates that cast_from_zone AFTER the zone-
            # recovery pass, so from:library never lands on the static shape).
            "impulse_top_play",
            # ADR-0027 β — edict_matters: a FORCED player sacrifice (CR 701.16). The
            # structural opp/each `sacrifice` arm (gated by _ir_effect_is_edict to drop
            # 6 leaked-scope self/you-sac over-fires) adds 28 real edicts the deleted
            # SWEEP regex never reached (Annihilator's reminder-only "defending player
            # sacrifices", the modal "those players sacrifice", empty-raw modes); a flat
            # _IR_KEPT_DETECTORS mirror (the exact deleted regex) covers the tail phase
            # folds into a categoryless / mis-scoped effect. struct + mirror reproduces
            # the regex firing set byte-identically (regex_only == 0).
            "edict_matters",
            # ADR-0027 β — legend_rule_off + timing_control: phase emits NOTHING
            # structural for either (legend_exempt covers only 2 of 8; the cast-timing
            # statics are dropped wholesale), so each rides a byte-identical
            # _IR_KEPT_DETECTORS mirror of the exact deleted regex (commander-legal
            # corpus: regex==mirror, 0 lost, 0 over-fire). NOT in _IR_FLOOR_LANES
            # (floor-mirror-dep == 0). CR 704.5j / 117.1a.
            "legend_rule_off",
            "timing_control",
            # ADR-0027 β — token_copy_matters: phase structures CopyTokenOf/Populate
            # (421 cards) but the 80-card struct-only delta is 100% reminder-text SELF-
            # copies (Embalm/Eternalize/Offspring/Double-team) the reminder-stripped
            # regex excludes, so the lane rides a byte-identical _TOKEN_COPY_MATTERS_
            # MIRROR of the exact deleted _HAND_FLOOR regex (commander-legal corpus:
            # regex==mirror, 0 lost, 0 over-fire). NOT in _IR_FLOOR_LANES (floor-mirror-
            # dep == 0). CR 702.95 / 707.
            "token_copy_matters",
            # ADR-0027 β — color_change: phase parses the "becomes the color of your
            # choice / all colors" clause INCONSISTENTLY (20 AddChosenColor mods + 4
            # Unimplemented "become"s) and the only shared IR category (animate)
            # 90%-over-fires (256 vs 24), so the lane rides a byte-identical
            # _COLOR_CHANGE_MIRROR of the exact deleted SWEEP regex (commander-legal
            # corpus: regex==mirror, 0 lost, 0 over-fire). NOT in _IR_FLOOR_LANES
            # (floor-mirror-dep == 0). CR 105 / 613.
            "color_change",
            # ADR-0027 β — toughness_combat: TOUGHNESS matters for combat (the Doran
            # combat-redirect) + as a value (the broader payoff half). phase parses the
            # Doran clause as an AssignDamageFromToughness modification but project
            # drops it on every multi-ability face, so the `combat_damage_mod` category
            # fires on only 21 (MISSES 129/133, no form for the 111 value-payoffs) and
            # over-fires 81% on "deal damage equal to its POWER" punches. So the lane
            # rides a byte-identical _TOUGHNESS_COMBAT_MIRROR — the EXACT OR
            # of the two deleted producers (commander-legal corpus: regex==mirror, 0
            # lost, 0 over-fire). NOT in _IR_FLOOR_LANES (floor-mirror-dep == 0).
            # CR 510.1c / 122 / 604.3.
            "toughness_combat",
            # ADR-0027 β — ability_copy: the "Ability copy" build-around (copy an
            # activated/triggered ability — Strionic, Lithoform, Rings, Bracers — plus
            # the "has all activated abilities of" granters — Necrotic Ooze, Experiment
            # Kraj, Mairsil). phase emits ONE undifferentiated `spell_copy` Effect
            # category for spell-copy AND ability-copy alike (no copy-target tag), so a
            # `spell_copy` arm over-fires 90% (303 vs the 51-card lane — Twincast/
            # Reverberate/Fork) and still MISSES the granters (grant_keyword). Splitting
            # needs a phase projection this parallel batch can't make, so the lane rides
            # a byte-identical _ABILITY_COPY_MIRROR of the exact deleted SWEEP regex
            # (commander-legal corpus: regex==mirror, 51==51, 0 lost, 0 over-fire). NOT
            # in _IR_FLOOR_LANES (floor-mirror-dep == 0). CR 706.10 / 113.2 / 706.2.
            "ability_copy",
            # ADR-0027 β — gain_control (THEFT). The gated structural arm below
            # (cat=='gain_control', excl donate / Owned-return / give-away) is a
            # recall-GAINING superset of the deleted `gain control of` regex (+85
            # commander-legal: Control Magic / Mind Control / Enslave "you control
            # enchanted creature", Mindslaver "control target player", exchange-control)
            # while dropping 4 regex over-fires (you-own reset, can't-gain protection,
            # own-recovery). A NARROWED _GAIN_CONTROL_MIRROR recovers the 9 genuine
            # theft cards phase emits no gain_control category for; signals.py
            # reconciles the 13 LOW-conf "don't own" cross-opens. NOT in _IR_FLOOR_LANES
            # (floor-mirror-dep == 0). CR 800.4a / 720.1.
            "gain_control",
            # ADR-0027 β — ltb_matters (leaves-the-battlefield payoffs — sac/blink/
            # bounce fodder). A STRUCTURAL `leaves`-trigger arm below (phase's
            # LeavesBattlefield mode, projected event=='leaves' @ SIDECAR v11, with an
            # OTHER-permanent subject leaving the battlefield) is a +9 recall gain over
            # the deleted regex (DFC back faces Luminous Phantom / Aang at the
            # Crossroads; bounce payoffs Azorius Aethermage / Warped Devotion / Tameshi
            # the front-face-only regex missed), PLUS a NARROWED _LTB_MATTERS_MIRROR
            # (the exact regex run per-clause for the Revolt "a permanent left the
            # battlefield this turn" conditions + self-LTB payoffs phase leaves as a
            # SelfRef trigger / static condition), VETOED per-clause by the O-Ring
            # self-LTB-EXILE form
            # ("exile … until ~ leaves the battlefield" — Banishing Light / Static
            # Prison, 93 over-fires dropped, already routed to exile_until_leaves). NOT
            # in _IR_FLOOR_LANES (floor-mirror-dep == 0). CR 603.6e / 700.4 (leaves ⊃
            # dies).
            "ltb_matters",
            # ADR-0027 β — self_counter_grow (a creature that puts +1/+1 counters on
            # ITSELF to grow). A STRUCTURAL arm below (a place_counter carrying the
            # SelfRef self-anchor marker project recovers @ SIDECAR v12 — adapt/
            # monstrosity/renown + "put a +1/+1 counter on ~/this creature/it") is a
            # +503 recall gain over the deleted pronoun-only regex (it catches by-name
            # self-grow — "put a +1/+1 counter on Lazav / Garza Zol"), PLUS a NARROWED
            # _SELF_COUNTER_GROW_MIRROR (the deleted regex's self-anchored arms MINUS
            # the
            # loose "on it" arm that over-fired onto OTHER-creature placements — 103
            # over-fires dropped: Ordeal of Purphoros, Defy Death, The Great Henge; the
            # SelfRef gate excludes them) for the 14 phase-parse-gap self-growers + the
            # self-power-scaling commander cross-open. NOT in _IR_FLOOR_LANES (floor-
            # mirror-dep == 0). CR 122.1 / 614.12.
            "self_counter_grow",
        }
    )
    # Batch 2a (keyword-array signals — same source as regex, full parity):
    | _IR_KEYWORD_KEYS
    # Cares-about floor lanes the IR path now mirrors from production (synergy
    # payoffs with no structural form) — track their convergence in the harness:
    | _IR_FLOOR_LANES
    # Batch 2b/2c (effect-doer + trigger-payoff lanes):
    | frozenset(key for key, _scope in _DOER_EFFECT_KEYS.values())
    | frozenset(key for key, _scope in _PAYOFF_TRIGGER_KEYS.values())
)

# IR scope vocab ("opp") → Signal scope vocab ("opponents").
_IR_TO_SIGNAL_SCOPE = {"you": "you", "opp": "opponents", "each": "each", "any": "any"}


def _ir_scope(scope: str) -> str:
    return _IR_TO_SIGNAL_SCOPE.get(scope, "any")


# "Your graveyard" / "this card from … graveyard" (self-recursion) is a self-graveyard
# engine (you); "an opponent's / their / each player's graveyard" is interaction/hate
# (opponents); a bare "a/the graveyard" carries no controller (auto = the structural
# scope). phase scopes a recursion-TARGET effect 'any' (the affected object carries no
# controller) even when the raw says "your graveyard", so the structural scope alone
# under-attributes self-graveyard cards to the 'any' avenue. Mirror the regex producer
# (signals.py "your graveyard"→you, opponent-library-mill→opponents) by reading the
# effect raw FIRST, falling back to the structural scope (ADR-0027 graveyard scope
# fidelity). CR 400.7 — a graveyard is a player's zone.
_GY_YOUR = re.compile(r"\byour graveyard\b", re.IGNORECASE)
_GY_OPP = re.compile(
    r"\b(?:opponent'?s?|their|each (?:player|opponent)'?s?|that player'?s?"
    r"|target (?:player|opponent)'?s?) graveyard\b",
    re.IGNORECASE,
)


def _gy_scope(e: Effect) -> str:
    """Resolve which player's graveyard an effect cares about (graveyard scope
    fidelity, ADR-0027). 'you' for a "your graveyard" reference (or an already-you
    structural scope); 'opponents' for an opponent's / their / each player's graveyard
    (or a structural opp scope); else the structural scope. A "your graveyard" tell
    wins over a co-mentioned opponent (Araumi's encore tokens "attack that opponent" is
    still a self-graveyard engine), matching the regex's self-first rule."""
    raw = e.raw or ""
    if e.scope == "you" or _GY_YOUR.search(raw):
        return "you"
    if e.scope == "opp" or _GY_OPP.search(raw):
        return "opponents"
    return _ir_scope(e.scope)


def _is_generic_creature_filter(f: object) -> bool:
    """A GENERIC 'creatures you control' filter (no tribe) — the creatures_matter
    anthem/scaling shape. A tribal filter (subtypes set) is type_matters, not this."""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and not f.subtypes
        and f.controller == "you"
    )


# ADR-0027 land-animation lanes (land_creatures_matter / land_protection): one
# shared predicate. A Land+Creature dual-type subject is the anthem/maker side
# (Sylvan Advocate's pump, Timber Protector's grant, Jyoti's land-creature token);
# a Land subject under an animate/base_pt_set/type_set effect is the animator side
# (Living Plane, Life and Limb, manlands). phase frequently drops the animate
# subject to None and splits "target land becomes a 0/0 creature" across effects, so
# the subject=None case checks the WHOLE ability's joined raw for a land reference
# (Noyan Dar, Llanowar Loamspeaker) while this effect's raw must say creature/becomes
# (CR 305 land + CR 110.1 creature). Phase outright drops many self-animate manland
# clauses ({cost}: this land becomes a creature) — those ride the kept oracle mirror.
def _has_land_creature_types(f: object) -> bool:
    """A Land+Creature dual-type own-board subject (the anthem/maker shape)."""
    return (
        isinstance(f, Filter) and "Land" in f.card_types and "Creature" in f.card_types
    )


def _is_land_subject(f: object, controllers: tuple[str, ...]) -> bool:
    """A Land subject controlled by one of ``controllers`` (the animator shape)."""
    return (
        isinstance(f, Filter) and "Land" in f.card_types and f.controller in controllers
    )


def _none_animate_land(ab: object, e: object) -> bool:
    """A subject=None animate whose own raw says creature/becomes AND whose ABILITY-
    level raw mentions a land (phase splits the land subject off the animate clause)."""
    if getattr(e, "subject", "") is not None:
        return False
    er = (getattr(e, "raw", "") or "").lower()
    if "becomes" not in er and "creature" not in er:
        return False
    ab_raw = " ".join((x.raw or "") for x in getattr(ab, "effects", ())).lower()
    return bool(re.search(r"\bland", ab_raw))


def _is_land_animator(ab: object, e: object, controllers: tuple[str, ...]) -> bool:
    """An animate/base_pt_set/type_set effect that turns a land into a creature —
    either a Land subject (controllers-gated) or the subject=None raw fallback."""
    return getattr(e, "category", "") in ("animate", "base_pt_set", "type_set") and (
        _is_land_subject(getattr(e, "subject", None), controllers)
        or _none_animate_land(ab, e)
    )


# Permanent-type "matters" lanes whose go-wide DOER is a COUNT operand over your
# permanents of that type ("for each artifact you control", affinity per CR 702.41)
# or a TYPE trigger (cast / enters that type). The count operand is the strongest
# care signal — CR 604.3: the value is determined by that type's population (Nim
# Lasher's power IS the artifact count). Creature is handled separately (it has the
# anthem + token-maker + over-fire boundary the others lack). Scope-gated to YOU —
# a count over an opponent's permanents is not your build-around.
_TYPE_MATTERS_LANE: dict[str, str] = {
    "Artifact": "artifacts_matter",
    "Enchantment": "enchantments_matter",
}


def _generic_board_subject(f: object) -> object:
    """``f`` itself when it is a GENERIC own-board filter (controller you, NO subtypes)
    that includes Artifact or Enchantment — the mass-anthem/grant shape over the whole
    artifact/enchantment board. Else None. The no-subtype gate excludes a subtyped buff
    ("Equipment you control", an Aura-subtype grant) which is a narrower tribal care,
    and a single-target buff (controller 'any'/SelfRef). 'Artifact creatures you
    control have flying' (Workshop Elders) carries ('Creature','Artifact') with no
    subtype, so it passes and fires artifacts_matter (the artifact population is
    buffed); a bare 'creatures you control' buff has no Artifact/Enchantment type, so
    it never leaks into these lanes (it stays creatures_matter)."""
    if (
        isinstance(f, Filter)
        and f.controller == "you"
        and not f.subtypes
        and ("Artifact" in f.card_types or "Enchantment" in f.card_types)
    ):
        return f
    return None


def _typed_matters_lanes(f: object) -> list[str]:
    """The artifacts/enchantments lane(s) for a YOUR-permanents filter, in order. A
    COMPOSITE subject — a count/grant/trigger over the (Artifact AND/OR Enchantment)
    board (Nettlecyst's "for each artifact and/or enchantment you control", Open the
    Vaults, Fountain Watch) — carries BOTH card types, so it fires BOTH lanes (each
    permanent type's population is a care). Excludes Creature (its own go-wide rules)
    and opponent-controlled sets."""
    if not isinstance(f, Filter) or f.controller == "opp":
        return []
    return [
        lane
        for card_type, lane in _TYPE_MATTERS_LANE.items()
        if card_type in f.card_types
    ]


# Predefined ARTIFACT token subtypes (CR 111.10 / 205.3g): Treasure / Clue / Food /
# Powerstone / Gold / Map / Junk / Incubator / Blood / Lander / Mutagen are all
# artifact tokens, so a maker / sac-payoff over one feeds artifacts_matter (affinity,
# metalcraft, Academy Manufactor) even when phase carries only the subtype and drops
# the Artifact card-type (Emissary Green, Giant Opportunity). NOT a bare token go-wide
# subtype (Servo/Thopter artifact CREATURE tokens are a tokens deck — those carry the
# Artifact card-type explicitly, read off card_types, not this subtype set).
_ARTIFACT_TOKEN_SUBTYPES: frozenset[str] = frozenset(
    {
        "treasure",
        "clue",
        "food",
        "powerstone",
        "gold",
        "map",
        "junk",
        "incubator",
        "blood",
        "lander",
        "mutagen",
    }
)


def _is_artifact_subject(f: object) -> bool:
    """True when ``f`` is an Artifact subject — the Artifact card-type, OR an
    artifact-token subtype (Treasure/Clue/Food/…) phase carries with an empty
    card_types tuple. The artifact-token branch fires the artifacts lane off a
    resource-token maker / sac-payoff (CR 205.3g)."""
    if not isinstance(f, Filter):
        return False
    return "Artifact" in f.card_types or bool(
        _fsubs_lower(f) & _ARTIFACT_TOKEN_SUBTYPES
    )


# ── Generalized type-payoff shapes (ADR-0027) ─────────────────────────────────
# A FAMILY of effect-shape detectors that, given an effect over a card-type-filtered
# subject, return the matters-lane(s) the effect is a PAYOFF for. They read only the
# subject's card_types (via _typed_matters_lanes) plus the effect's category/marker,
# so they are type-parameterized — the same shapes transfer to a future
# graveyard/counters/spellcast matters lane by extending _TYPE_MATTERS_LANE. Each
# encodes one settled rules discriminator (see ADR-0027).


def _type_tutor_lanes(e: object) -> list[str]:
    """A TUTOR / DIG of a card-type (CR 701.23) → that type's matters-lane(s).

    A search/dig whose target FILTER is the card type ("search your library for an
    enchantment/artifact card" — Idyllic Tutor, Fabricate; "look at the top N, you may
    put an artifact into your hand" — Glint-Nest Crane) is a build-around enabler for
    that permanent type, so it fires the lane. A COMPOSITE filter ("an artifact OR
    enchantment card" — Enlightened Tutor) fires BOTH lanes.

    GATE (the over-fire boundary): the target filter's ``subtypes == ()``. A SUBTYPE
    tutor ("search for an Aura/Equipment card" — Three Dreams, Steelshaper's Gift,
    Stoneforge Mystic) carries ``subtypes=('Aura'/'Equipment',)`` — that is a NARROWER
    voltron/aura care, not the broad type lane, so it is excluded. A CMC-restricted
    any-of-type tutor (Trophy/Treasure/Tribute Mage — ``subtypes=()`` with a Cmc
    predicate) is STILL an any-artifact tutor, so it fires (correctly — it fetches the
    deck's artifacts). A generic-permanent tutor (Wargate — card_types ('Permanent',))
    carries neither Artifact nor Enchantment, so _typed_matters_lanes returns []."""
    if not isinstance(e, Effect) or e.category not in ("tutor", "topdeck_select"):
        return []
    sub = e.subject
    if not isinstance(sub, Filter) or sub.subtypes:
        return []
    return _typed_matters_lanes(Filter(card_types=sub.card_types, controller="you"))


def _type_recursion_lanes(e: object) -> list[str]:
    """A TYPE-RESTRICTED graveyard recursion of a card-type → that type's lane(s).

    SETTLED RULE (CR 115.1 single-target / 115.10 mass): the discriminator is the
    target FILTER's card-TYPE, NOT mass-vs-single. A reanimate / graveyard-recursion /
    graveyard→hand bounce / graveyard→library recursion whose target is FILTERED to a
    card type fires that type's lane whether it returns ONE ("return target enchantment
    card" — Auramancer, Monk Idealist, Skull of Orm; "return target artifact card" —
    Refurbish, Argivian Archaeologist) or ALL ("return all enchantment cards" — Crystal
    Chimes, Replenish; "return all artifact and enchantment cards" — Open the Vaults,
    Dance of the Manse). Type-gating = only useful in a deck full of that type. A
    COMPOSITE ("artifact OR enchantment card" — Argivian Find, Open the Vaults) fires
    BOTH lanes.

    GATE (the over-fire boundary): the target must be TYPE-restricted. A GENERIC-target
    recursion ("return target card" / "return target permanent card" — Regrowth,
    Eternal Witness, Pull from Eternity) is NOT type-gated, so it fires nothing here. An
    Aura-SUBTYPE recursion ("return target Aura" — Dowsing Shaman) is the narrower
    voltron/aura care, routed to a LOOSE enchantments_matter member (no dedicated Aura
    lane exists). Removal/reset (destroy/exile/counter) is a different category and
    never reaches here."""
    if not isinstance(e, Effect):
        return []
    if e.category not in (
        "reanimate",
        "graveyard_recursion",
        "bounce",
        "cast_from_zone",
        "topdeck_stack",
    ):
        return []
    sub = e.subject
    if not isinstance(sub, Filter) or sub.controller == "opp":
        return []
    # graveyard-sourced only: a battlefield mass bounce (BounceAll board wipe) or a
    # hand/library move is not graveyard recursion of the type as a resource.
    if "from:graveyard" not in e.zones and "in:graveyard" not in e.zones:
        return []
    lanes = _typed_matters_lanes(Filter(card_types=sub.card_types, controller="you"))
    # Aura-SUBTYPE recursion → a loose enchantments_matter member (CR 205.3 — Auras are
    # enchantments), only when no broader card-type lane already fired for it.
    if not lanes and "aura" in _fsubs_lower(sub):
        return ["enchantments_matter"]
    return lanes


# Batch 6 — grant_keyword lanes. The granted keyword rides in Effect.counter_kind.
# Evasion abilities per CR (702.9a flying / 702.13a intimidate / 702.28a shadow /
# 702.31a horsemanship / 702.36a fear / 702.111a menace / 702.118a skulk; landwalk
# is parameterized, not a bare granted keyword). Protective keywords: hexproof
# (702.11) / shroud (702.18) / indestructible (702.12) / ward (702.21) / protection
# (702.16). flash_grant is DEFERRED: flash-granting is CastWithKeyword (a cast-time
# permission), not a battlefield AddKeyword — see deferrals.md.
_EVASION_GRANT_KW: frozenset[str] = frozenset(
    {"flying", "intimidate", "shadow", "horsemanship", "fear", "menace", "skulk"}
)
_PROTECTION_GRANT_KW: frozenset[str] = frozenset(
    {"hexproof", "shroud", "indestructible", "ward", "protection"}
)


def _is_team_creature_grant(f: object) -> bool:
    """The team-anthem grant shape: GENERIC creatures YOU control, no subtypes AND
    no predicates. The no-predicates gate is what _is_generic_creature_filter lacks
    (it ignores predicates), and it excludes equipment/aura (EquippedBy), conditional
    self-grants (SelfRef), and single targets — the source of the naive +2197 flood."""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and f.controller == "you"
        and not f.subtypes
        and not f.predicates
    )


def _is_all_creatures_grant(f: object) -> bool:
    """The SYMMETRIC 'all creatures have X' shape (Concordant Crossroads) — a
    generic creature filter controlled by ANY player (not just yours), no subtypes,
    no predicates. Scope 'any' (the lane's convention) — it is an unscoped global
    grant that buffs opponents' creatures too, not a your-team anthem."""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and f.controller == "any"
        and not f.subtypes
        and not f.predicates
    )


# ADR-0027 team_buff — the full evergreen team-keyword anthem set. team_buff is the
# BROAD union of keyword anthems ("creatures you control have/gain <keyword>"); it
# intentionally overlaps team_evasion_grant (the evasion subset) + protection_grant
# (the protective subset) — the seen-set dedups within a lane. (CR: evergreen
# keyword abilities granted to your whole creature board.)
_TEAM_BUFF_GRANT_KW: frozenset[str] = frozenset(
    {
        "flying",
        "trample",
        "menace",
        "hexproof",
        "indestructible",
        "protection",
        "deathtouch",
        "lifelink",
        "doublestrike",
        "firststrike",
        "vigilance",
        "haste",
        "ward",
        "reach",
    }
)
# Predicates an anthem subject may carry while still being a GENERIC your-team
# anthem (not a tribal / single-target narrowing): Always Watching's "Nontoken
# creatures you control have vigilance" and Tam-style "Each OTHER creature you
# control …" stay in. A subtype (tribal), a HasColor / Attacking / EquippedBy /
# Cmc narrowing, or an opp/single controller fails the gate. (ADR-0027.)
_TEAM_BUFF_OK_PREDS: frozenset[str] = frozenset({"NonToken", "Another", "Other"})


def _is_team_buff_grant(f: object) -> bool:
    """The team_buff anthem shape: GENERIC creatures YOU control (no subtypes) whose
    only predicates are in ``_TEAM_BUFF_OK_PREDS`` (NonToken/Another/Other). Broader
    than ``_is_team_creature_grant`` (which tolerates NO predicates) so the genuine
    Always Watching / "each other creature you control" anthems land — kept SEPARATE
    so relaxing it never perturbs team_evasion_grant / protection_grant. (ADR-0027.)"""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and f.controller == "you"
        and not f.subtypes
        and set(f.predicates) <= _TEAM_BUFF_OK_PREDS
    )


# ADR-0027 aura_equip_kw_grant — the evergreen keyword set the deleted regex
# enumerated, normalized to phase's spaceless counter_kind spelling (firststrike /
# doublestrike). The allowlist is the over-fire boundary: it excludes "equip {0}" /
# "crew 1" grants (Syr Gwyn, Puresteel Paladin, Astor), which phase emits as a
# different cost/effect, never grant_keyword of an evergreen keyword. (See ADR-0027.)
_AURA_EQUIP_GRANT_KW: frozenset[str] = frozenset(
    {
        "exalted",
        "flying",
        "trample",
        "deathtouch",
        "lifelink",
        "vigilance",
        "haste",
        "firststrike",
        "doublestrike",
        "hexproof",
        "ward",
        "menace",
        "reach",
        "indestructible",
    }
)


def _is_aura_equip_grant(f: object) -> bool:
    """The aura/equipment anthem shape: a grant subject that is YOUR Aura or
    Equipment subgroup ("Auras you control have flying", "Equipment you control have
    deathtouch" — Rashel). The subtype tells it apart from a generic team grant
    (_is_team_creature_grant requires NO subtypes, so there's no double-fire), and
    controller=='you' keeps it the player's own subgroup, not a symmetric grant."""
    return (
        isinstance(f, Filter)
        and f.controller == "you"
        and any(st.lower() in ("aura", "equipment") for st in f.subtypes)
    )


# ADR-0027 conditional_self_protection — the PROTECTIVE keyword subset a conditional
# self-grant confers ("during your turn ~ has indestructible", "has hexproof unless
# tapped"). This subset is the over-fire boundary vs an ordinary conditional self
# anthem (a "during your turn ~ has flying/trample" combat buff is NOT protection).
_SELF_PROTECTION_GRANT_KW: frozenset[str] = frozenset(
    {"hexproof", "indestructible", "protection", "shroud", "ward"}
)


# Batch E — counter KIND → (signal key, scope). NB: p1p1 is deliberately ABSENT
# — +1/+1 counters are ubiquitous, so place_counter→counters_matter floods the
# lane (1552 IR_ONLY); counters_matter derives from the counter_added trigger +
# the +1/+1-keyword set instead. The off-+1/+1 kinds are precise.
_COUNTER_KIND_KEYS: dict[str, tuple[str, str]] = {
    "m1m1": ("minus_counters_matter", "you"),
    "oil": ("oil_counter_matters", "you"),
    "shield": ("shield_counter_matters", "you"),
    "rad": ("rad_counter_matters", "opponents"),
    "ki": ("ki_counter_matters", "you"),
    # NB: lore counters do NOT map here — saga_matters fires from a `saga` marker
    # (project._dropped_static_markers, the "lore counter" / "Saga you control" face
    # reference), NOT every lore placement (a vanilla Saga's intrinsic chapter
    # advancement is not a build-around tell — the reminder is stripped, matching the
    # regex).
}

# keyword_counter (ADR-0027 tranche2-C) — the CLOSED CR-122.1b keyword-counter set:
# a counter that grants a keyword ability via layer 6 (CR 613.1f). phase tags the
# granted keyword KIND directly in Effect.counter_kind on a place_counter /
# remove_counter (verified across the corpus). Distinct from the p1p1/m1m1/charge/oil/
# shield/rad/ki standard counters (those are stat/resource counters, not ability
# grants). DELIBERATELY excludes stun (CR 122.1d) and shield (122.1c) — they create
# REPLACEMENT effects and grant NO keyword — and aegis (not a CR counter). The
# no-space form is phase's emission ('firststrike', 'doublestrike').
_KEYWORD_COUNTER_KINDS: frozenset[str] = frozenset(
    {
        "flying",
        "menace",
        "trample",
        "reach",
        "haste",
        "deathtouch",
        "hexproof",
        "indestructible",
        "lifelink",
        "vigilance",
        "firststrike",
        "doublestrike",
    }
)

# opponent_counter_grant (ADR-0027): counter kinds that BENEFIT the recipient, so a
# placement on an opponent's permanent is the WRONG direction for the detrimental-mark
# punish lane — exclude them. p1p1 (a +1/+1 buff — Hunter of Eyeblights places one to
# enable its own counter-removal, not to punish), shield (a damage-soak), and every
# keyword counter (flying/indestructible/… — CR 122.1b grants an ability) all help the
# opponent. Everything else placed on an opponent (bounty/stun/m1m1/slime/bribery/
# rejection/…) is a detrimental mark. CR 122.1d.
_OPP_COUNTER_BENEFICIAL: frozenset[str] = (
    frozenset({"p1p1", "shield"}) | _KEYWORD_COUNTER_KINDS
)

_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker", "Battle"}
)

# removal_matters subtype-only destroy gate (ADR-0027): "destroy target Wall"
# destroys a CREATURE; phase parses it as destroy(subject card_types=(),
# subtypes=('Wall',)) so the _PERMANENT_TYPES card-type gate misses it. Fire on a
# non-empty SUBTYPE subject UNLESS every subtype is a LAND subtype — "destroy target
# Island / nonbasic land" is land_destruction, NOT removal (the lane's discriminator,
# CR 305.6). Basics + the common nonbasic land-type words that appear as subtypes.
_LAND_SUBTYPES: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "wastes",
        "desert",
        "gate",
        "lair",
        "locus",
        "urza's",
        "mine",
        "power-plant",
        "tower",
        "cave",
        "sphere",
    }
)

# land_exchange (ADR-0027): phase parses "exchange control of target X and target Y"
# as a gain_control effect with subject=None (it never binds the land-typed object
# onto the effect's Filter), so the "Land" in ftypes gate misses. Fall back to the
# effect raw for the exchange-with-land phrase — the lane's own serve regex, so the
# detector and serve stay consistent. Covers Gauntlets' "artifact, creature, or land"
# (raw has "…or land…") and excludes Sharkey (no gain_control effect at all).
_LAND_EXCHANGE_RAW = re.compile(r"exchange control of[^.]*\bland\b", re.IGNORECASE)

# extra_land_drop controller='any' recovery (ADR-0027 tranche2-C): a "from your hand
# OR graveyard" put-into-play (Bonny Pall, Riveteers Confluence, Dread Tiller) makes
# phase drop the source to controller='any' (the disjunction defeats the YOUR pin),
# so the structural controller=='you' gate misses it. Mirror the deleted regex's
# YOUR-anchor on the effect raw — "you may put a land … onto the battlefield" — and
# EXCLUDE the symmetric group-hug forms (Show and Tell / Braids / Kynaios /
# Hypergenesis / Tempting Wurm: "each player / that player / each opponent may put"),
# which the YOUR-anchored deleted regex never matched (they are group ramp, not your
# extra land drop). CR 305.9.
_EXTRA_LAND_DROP_YOU_RAW = re.compile(
    r"you may put (?:a |any number of )?lands? card", re.IGNORECASE
)
_EXTRA_LAND_DROP_GROUP_RAW = re.compile(
    r"each player|that player|each opponent|their hands?", re.IGNORECASE
)

# mass_removal (ADR-0027): a BOARD WIPE — the counter_kind=='all' "each/all"
# discriminator on a destroy/exile/damage of a battlefield permanent type, or a
# negative all-creatures pump (Languish/Toxic Deluge). The battlefield-type gate
# (NOT Land-only, NOT a graveyard Card/None subject) separates a real sweep from
# land destruction (Armageddon → land_destruction) and graveyard exile (delve /
# GY-hate). CR 115.10. The pump arm needs the negative-pump raw because phase drops
# the -X/-X amount (amount=None), so the "all creatures get -" raw is the only
# discriminator vs the 1000+ positive all-creatures anthems (Glorious Anthem).
_MASS_REMOVAL_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker"}
)
_MASS_DEBUFF_RAW = re.compile(r"all .*creatures? .*get -", re.IGNORECASE)

# donate_matters (ADR-0027): a control CHANGE that gives a permanent YOU control to
# ANOTHER player (CR 701.12 — Donate, Harmless Offering, Zedruu). phase parses these
# as gain_control with scope='any' (the RECIPIENT — an opponent/other player — is
# dropped from the typed shape), so read the effect raw for the giving-away phrasing.
# The recipient discriminator ("<target/another/that player|opponent|its owner> gains
# control") is what separates donate (you give away) from theft (you take). Mirrors
# the lane's own (deleted) serve regex; reproduces it exactly (residual 0). "gains"
# (not "gain") keeps the subjunctive "have an opponent GAIN control" outside the same
# clause but matches the indicative donate clause the regex caught.
_DONATE_RAW = re.compile(
    r"(?:target opponent|another player|target player|that player|each opponent"
    r"|each other player|the player with|its owner) gains control of",
    re.IGNORECASE,
)
# GIVE-control-AWAY drawback (ADR-0027 gain_control exclusion): a card whose control-
# change effect GIVES a permanent to an OPPONENT / redistributes to EACH player — a
# drawback (Akroan Horse, Rainbow Vale, Crag Saurian) or chaos (Scrambleverse), NOT
# theft. phase maps these GiveControl effects to the gain_control category, so the
# theft lane must exclude the give-away direction. Broader than _DONATE_RAW (adds
# "an opponent" / "each player" / "that creature's controller / source's controller")
# and gain_control-only (NOT wired to donate_matters, a separate migrated lane).
_GIVE_CONTROL_AWAY = re.compile(
    r"(?:an opponent|each player|that (?:creature's|permanent's|source's) controller"
    r"|target opponent|another player|that player|each opponent|its owner"
    r"|the (?:attacking|defending) player|the player with(?: the)?)"
    r" (?:[a-z ]*? )?gains control of",
    re.IGNORECASE,
)

# reanimate subject-recovery (ADR-0027): phase emits cat='reanimate' but DROPS the
# creature subject (subject=None) on the pay-{X}/"when you do" nesting (Isareth) and
# many "return target creature card from a graveyard to the battlefield" shapes
# (Beacon of Unrest, Liliana Death's Majesty, Coffin Queen). Recover the creature-card
# reanimation from the effect raw so _reanimates_creature stays true to its docstring
# (creature reanimation = the archetype). Gated to cat='reanimate' so it can never
# reach flashback / escape / unearth (distinct categories — CR 702.34 casting ≠
# reanimation putting onto the battlefield).
_REANIMATE_CREATURE_RAW = re.compile(
    r"(?:return|put)[^.]*\bcreature cards?\b[^.]*\bgraveyard\b[^.]*\bbattlefield\b",
    re.IGNORECASE,
)

# sacrifice_matters edict exclusion (ADR-0027): a FORCED sacrifice phase mis-scoped
# to "any" (it dropped the opponent/each-player controller — Malfegor, Barter in
# Blood, Plaguecrafter), so the structural opp/each edict split missed it. The raw
# still names the sacrificing party ("<each opponent / each player / target player /
# defending player / an opponent> ... sacrifices"), the 3rd-person forced form that
# distinguishes an edict from a you-sacrifice ("you ... sacrifice"). Kept out of the
# you-sac sacrifice_matters lane (it stays an edict_matters / removal effect).
_SAC_EDICT_RAW = re.compile(
    r"\b(?:each opponent|each player|each of your opponents|target opponent"
    r"|target player|that player|an opponent|defending player|enchanted player"
    r"|opponents?)\b[^.]{0,70}?\bsacrifices?\b",
    re.IGNORECASE,
)

# edict_matters IR-arm discriminators (ADR-0027 β). The structural opp/each sacrifice
# split over-fires when phase leaks scope='opp'/'each' onto a sacrifice from a SIBLING
# clause: a self-permanent sac ("sacrifice ~ and target opponent discards" — Brink of
# Madness, Helm of Obedience, Thought Dissector) or a you-sac ("you may sacrifice a
# creature … target player reveals" — Cabal Therapist, Reno and Rude; "Sacrifice it at
# the beginning of the next end step" after a steal — Treacherous Urge). An edict is a
# FORCED 3rd-person PLAYER sacrifice (CR 701.16). _EDICT_PLAYER_SAC is the affirmative
# tell — a player-noun anywhere before "sacrifice(s)" in the same sentence (broader gap
# than _SAC_EDICT_RAW so "Each player … then sacrifices half their creatures" — Pox,
# Fraying Omnipotence — and "those players sacrifice" — Vaevictis — still match).
_EDICT_PLAYER_SAC = re.compile(
    r"\b(?:each opponent|each player|each of your opponents|target opponent"
    r"|target player|that player|those players|an opponent|any opponent"
    r"|defending player|enchanted player|opponents?|players?)\b"
    r"[^.]*?\bsacrifices?\b",
    re.IGNORECASE,
)
# The leaked-scope over-fire tell: a self-permanent sac ("sacrifice ~/it/this/that" —
# the ~ is the SelfRef substitution, no trailing \b since it is followed by punctuation)
# or a you-sac ("you (may/do/then) sacrifice"). When neither a player-sac nor this tell
# names the actor (an empty / amount-only raw — Will of the Abzan), the structural
# opp/each scope alone is trusted (it is a real forced sacrifice).
_EDICT_LEAKED_SAC = re.compile(
    r"\bsacrifice (?:~|it\b|this\b|that\b)|\byou (?:may |do |then )?sacrifice\b",
    re.IGNORECASE,
)


def _ir_effect_is_edict(e: Effect) -> bool:
    """True if a structural opp/each ``sacrifice`` Effect is a genuine edict (a forced
    PLAYER sacrifice), not a self/you-sac whose scope leaked from a sibling clause."""
    raw = e.raw or ""
    if _EDICT_PLAYER_SAC.search(raw):
        return True
    return not _EDICT_LEAKED_SAC.search(raw)


# sacrifice_matters subject-less / modal fallback (ADR-0027): a YOU-sacrifice of a
# NON-land permanent surviving only in a sacrifice/choose effect raw phase left
# subjectless ("sacrifice any number of creatures" — Dracoplasm, Shimatsu; "sacrifice
# … unless you sacrifice a creature" pay-or-die — Phyrexian Dreadnought, Contamination;
# a "you may sacrifice an artifact or discard" modal collapsed to `choose` — Chandra,
# Gearbane). The lazy gap admits a count + adjective; the type list excludes a bare
# "sacrifice a land" and a self-sac ("sacrifice it/this/~/<Name>") carries no type, so
# it never matches. The edict guard (_SAC_EDICT_RAW) runs alongside this at the call.
_SAC_OUTLET_RAW = re.compile(
    r"\bsacrifice (?:a|an|another|two|three|any number of|x|\d+)\b[^.]*?\b"
    r"(?:creature|artifact|permanent|enchantment|nonland|nontoken|token"
    r"|food|treasure|clue|blood|planeswalker)s?\b",
    re.IGNORECASE,
)

# convoke_matters (ADR-0027): the keyword-LESS convoke GRANTERS + PAYOFFS phase keeps
# only in a carrier raw — Wand of the Worldsoul's grant_spell_ability ("the next spell
# you cast this turn has convoke", counter_kind dropped) and the "spell that has
# convoke" payoff trigger (Saint Traft, Joyful Stormsculptor). The structured static
# granters ("<type> spells you cast have convoke") carry counter_kind='convoke' and
# need no raw scan. The card's OWN printed convoke rides the keyword array.
_CONVOKE_RAW = re.compile(r"\bconvoke\b", re.IGNORECASE)

# power_tap_engine (ADR-0027): a {T}-activated ability whose output SCALES with a
# creature's power (Marwyn "{T}: Add {G} equal to ~'s power"; Selvala "where X is the
# greatest power"; Staff of Domination). The discriminator is the CONJUNCTION of the
# structured tap activation cost (Ability.cost ~ 'tap') and this power-scaling output
# phrase in an effect raw — a bare "equal to its power" damage/draw with NO tap cost
# (Soul's Majesty, Berserk) is one-off power-scaling, not a repeatable {T} engine. The
# power numeric need not be a Quantity; the word-mirror on the activated ability's
# effect raw is the precise tell. Byte-identical to the deleted _HAND_FLOOR regex's
# "(?:equal to|where x is|x is)[^.]*power" clause. CR 602.
_POWER_SCALING_RAW = re.compile(
    r"(?:equal to|where x is|x is)[^.]*\bpower\b|greatest power", re.IGNORECASE
)

# ADR-0027 β — power-as-damage cluster discriminators (creature_ping vs
# damage_equal_power), applied to a cat=="damage" Effect whose amount.op=="power" (the
# d6620ac projection unlock). The empirical Effect.subject↔recipient mapping (verified
# on Fling / Soul's Fire / Rabid Bite and 250 effect rows): the damage Effect's subject
# IS the RECIPIENT (Rabid Bite c=opp Creature; None for "any target"/player), and the
# DOER lives in a SEPARATE target_only Effect (you-controller Creature subject). When
# phase drops the recipient subject to None, these raw mirrors disambiguate.
#
# _POWER_PLAYER_RECIP — the recipient reaches a PLAYER / any target (damage_equal_power,
# the burn/finisher half, incl. Fling's "sacrificed creature's power to any target").
_POWER_PLAYER_RECIP = re.compile(
    r"to (?:any target|target player|each opponent|that player|target opponent"
    r"|target player or planeswalker|each of your opponents"
    r"|that player or planeswalker|you\b|its controller|any other target"
    r"|defending player|target battle)|its controller",
    re.IGNORECASE,
)
# _POWER_SELF_RECIP — a self-fight ("deals damage to itself equal to its power" —
# Justice Strike, Wave of Reckoning) is a creature_ping (a creature dealing its own
# power).
_POWER_SELF_RECIP = re.compile(r"to itself|deals damage to itself", re.IGNORECASE)
# _POWER_ITS_OWN_DOER — an actor dealing ITS OWN power ("deals damage equal to its
# power"), the creature_ping doer tell. Deliberately requires "its power" (the doer's
# own), so a fling source ("the sacrificed/exiled creature's power", "that spell's
# power") naming a DIFFERENT object never matches — those are damage_equal_power, where
# the spell / sacrificed creature is the source, not a controlled-creature ping.
_POWER_ITS_OWN_DOER = re.compile(r"deals damage equal to its power", re.IGNORECASE)

# creature_cast_trigger (ADR-0027): phase parses "Whenever you cast a creature spell"
# into a cast_spell trigger but DROPS the spell-type subject (subject=None), OR keeps
# only a `place_counter`/`emblem`/granted-token effect whose raw carries the trigger
# (Wildgrowth Archaic's enters-with replacement, Garruk's emblem, Volo's Journal /
# Blink granted token, Glimpse of Nature's delayed trigger). The "creature spell"
# cast reference survives only in some effect's raw, so a face-level scan over EVERY
# effect raw catches them. Mirrors the regex (scope "any" — a creatures-being-cast
# lane regardless of who casts). The qualifier is unambiguous (a real creature-cast
# payoff), and the typed-subject trigger path still binds what phase DID structure.
_CREATURE_SPELL_RAW = re.compile(
    r"\bwhen(?:ever)? (?:you|a player|an opponent|each opponent|another player)"
    r" casts? (?:a|an|another)\b[^.]*?\bcreature spell\b"
    r"|\bwhen(?:ever)? (?:a|another) creature spell is cast\b",
    re.IGNORECASE,
)

# ADR-0027 β — combat_damage_to_opp LOW-confidence double-strike-grant mirror
# (Raphael, Blade Historian, Berserkers' Onslaught). Fired separately from the
# _IR_KEPT_DETECTORS loop because that loop emits HIGH confidence; the deleted regex
# producer fired LOW (never feeding has_other_plan), so the inline mirror keeps it LOW.
_COMBAT_DAMAGE_TO_OPP_DS_GRANT = re.compile(
    COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX, re.IGNORECASE
)

# fight_matters (ADR-0027): a face-level fallback for an Aftermath DFC whose "Fight"
# back face phase never projects into the IR (Prepare // Fight) — the fight survives
# only on the combined face oracle. Mirrors the project `_FIGHT_REF` / fight_matters
# regex shapes (the fight VERB with a target/creature/each-other object).
_FIGHT_RAW = re.compile(
    r"\bfights? (?:up to (?:one|two|\d+) )?(?:other |another )?target\b"
    r"|\bfights? (?:up to (?:one|two) )?(?:other )?creature"
    r"|\bfight each other\b|\bfights? it\b|\bfights? (?:another|each)\b",
    re.IGNORECASE,
)

# token-subtype (ADR-0027): a face-level fallback for an Aftermath DFC whose
# "create … <Subtype> token" back face phase never projects into the IR (Indulge //
# Excess) — the maker survives only on the combined face oracle. Anchored on a creation
# verb + "<Subtype> token" so a "discard a Blood token" outlet doesn't false-fire.
_TOKEN_SUBTYPE_RAW = re.compile(
    r"\bcreates?\b[^.]*?\b(blood|clue|food|treasure) tokens?\b", re.IGNORECASE
)

# group_mana (ADR-0027): symmetric/shared mana added to players OTHER than just the
# controller. The Effect dataclass has no recipient field — phase flattens every
# mana-recipient phrasing ("each player … adds {G}", "that player adds {B}{R}{G}",
# "the active player adds {C}") into ramp/any, identical to controller-only "you add"
# ramp. The non-controller recipient survives only in e.raw, so this discriminator
# (a non-you player adding mana) separates group ramp (Magus of the Vineyard, Yurlok,
# Valleymaker, Tangleroot) from your-own ramp (Sol Ring, Llanowar).
_GROUP_MANA_RAW = re.compile(
    r"(?:each|that|the active|chosen) player[^.]*adds \{", re.IGNORECASE
)

# venture_matters (ADR-0027): a dungeon-DOUBLING payoff phase keeps as a
# trigger_doubling effect whose raw names rooms/dungeons ("Room abilities of dungeons
# you own trigger an additional time" — Hama Pashar, Dungeon Delver). The dungeon
# qualifier survives only in raw, so anchor on it rather than firing on every
# trigger_doubling (Panharmonicon is NOT a venture card).
_DUNGEON_RAW = re.compile(r"\broom abilit|\bdungeon", re.IGNORECASE)

# Goad-style political force (CR 701.38): a SINGLE-TARGET "target creature … attacks
# … if able" (Boiling Blood, Incite, Basandra, Alluring Siren) is the goad mechanic's
# doer — it forces ONE creature (usually an opponent's) to attack, the political
# redirect engine that wants goad payoffs. phase types these as a `force_attack`
# effect (the same category as the self/team "attacks each combat" compulsion), so the
# IR routes the force_attack effect to forced_attack by default; this raw anchor lifts
# the TARGETED form to goad_matters too. The self/team "each combat if able" static
# (the forced_attack lane proper) never says "target creature", so it stays
# forced_attack-only.
_GOAD_STYLE_FORCE = re.compile(
    r"target creature[^.]*attacks?[^.]*\bif able\b", re.IGNORECASE
)

# Scaling-count discriminator (ADR-0027 count-operand cluster): draw_for_each /
# scaling_pump want a value that SCALES with a board count ("for each creature you
# control", "equal to the number of …"), NOT a bare X-spell ("draw X cards", "pump
# +X/+X") whose X is the cast/activation cost. phase emits op='count' for BOTH (X is a
# count too), so the count op alone over-fires the lanes onto Braingeyser / Champion
# of Wits. A genuine scaling-count carries a counted SUBJECT (Shamanic Revelation's
# creature set) OR names the count in raw ("for each" / "equal to the number of"); a
# bare X-spell has neither. CR 107.3.
_FOR_EACH_RAW = re.compile(r"\bfor each\b|\bequal to the number of\b", re.IGNORECASE)


# The named count ops that are ALWAYS a "for each <X>" scale (CR 700.3 domain, CR
# 107.x devotion/party, CR 122 counters/experience) — distinct from the generic
# `count` op, which also covers bare X-spells. A pump/draw scaling on any of these is
# genuine (Kalemne's +1/+1 per experience, Atreus's draw-per-experience). experience
# also routes to experience_matters (a correct co-fire), not stolen from it.
_NAMED_SCALE_OPS = frozenset({"counters", "domain", "devotion", "party", "experience"})


# untap_engine discriminator (ADR-0027 β): the lane wants a DELIBERATE untap engine —
# "untap target/another target/all/each/two/up to <permanent>" (Seedborn Muse,
# Kiora, Murkfiend Liege) — NOT an incidental "untap it/this/that" rider (Act of
# Treason's threaten, Abduction, Amulet of Vigor) nor the "doesn't untap" INVERSION
# (Basalt Monolith). Mirrors the deleted regex's anchor; a mass untap (counter_kind
# =='all', the structured "untap all") also opens it even when the raw is empty.
_UNTAP_ENGINE_RAW = re.compile(
    r"\buntap (?:target|another target|all|each|two|up to)", re.IGNORECASE
)
# Single-permanent untap RIDER veto (ADR-0027 β): "untap enchanted/equipped <thing>"
# is a one-off Aura/Equipment untap (Crab Umbra, Pemmin's Aura, Freed from the Real),
# the incidental "untap it/this/that" rider the lane explicitly excludes — not the
# deliberate target/mass engine. Vetoes the structural subject-Filter branch only.
_UNTAP_ATTACH_VETO = re.compile(r"untap (?:enchanted|equipped)\b", re.IGNORECASE)
# Opponent-untap over-fire veto (ADR-0027 β): "Untap target creature you don't control"
# is an incidental untap of an ENEMY permanent for combat/theft (Provoke the card,
# Spinal Embrace, provoke-keyword combat) — anti-synergy with an untap engine, NOT one.
# The deleted regex over-fired on both; the IR (structural arm + mirror) correctly
# drops them. Used to veto the mirror and the structural raw branch (the subject branch
# already gates on controller!='opp').
_UNTAP_ENGINE_OPP_VETO = re.compile(
    r"untap target creature you don't control", re.IGNORECASE
)
# untap_engine mirror (ADR-0027 β): the EXACT deleted _HAND_FLOOR regexes (the
# target/all/each/two/up-to engine + the Ashaya creatures-are-lands synergy) the
# structural arm misses because phase routes their untap into a choose / target_only /
# cost / type_set carrier, not a `cat=='untap'` Effect (Captain of the Mists, Turnabout,
# Faces of the Past, All-Out Assault, Teferi Who Slows the Sunset, Crackleburr, Halo
# Fountain, Ohabi Caleria, Zariel, Tideforce Elemental, Ashaya). Run reminder-stripped
# (kept_oracle) like the deleted floor Detectors, with the opp-untap veto so it drops
# the same Provoke / Spinal Embrace over-fires the structural arm does.
_UNTAP_ENGINE_MIRROR_RAW = re.compile(
    r"\buntap (?:target|another target|all|each|two|up to)\b", re.IGNORECASE
)
_UNTAP_ENGINE_MIRROR_LANDS = re.compile(
    r"(?:nontoken )?creatures you control are[^.]*\blands\b", re.IGNORECASE
)
# variable_pt NARROWED mirror (ADR-0027 β): the */* characteristic-defining tail phase
# CANNOT structure as a self-CDA static — a TOKEN-borne */* ("This token's power and
# toughness are each equal to …" — Seize the Storm, Elephant Resurgence, Vernal
# Sovereign, Bonny Pall, Hallowed Haunting, Ajani Goldmane's Avatar, Mordenkainen's
# Construct), and the TRIGGERED "change <Name>'s/this creature's base power and
# toughness" self-set phase routes through a non-CDA shape (Halfdane, Eldrazi Mimic,
# Shape Stealer). The core CDA phrase + a NAMED-self change-base, MINUS the over-firing
# reach the deleted SWEEP regex had: a draw/damage scaling with "cards in your/their
# hand|library" (Spiraling Embers, Enter the Infinite, Sword of War and Peace — a burn/
# draw lane, NOT a */* body) and a "change the base power and toughness OF all/each/
# other/target/the … creatures" mass-debuff (Brine Hag, Exuberant Wolfbear). Run on the
# reminder-stripped kept_oracle; vetoed so it drops the same over-fires the structural
# arm does. CR 604.3.
_VARIABLE_PT_MIRROR = re.compile(
    r"power and toughness are each equal to"
    r"|power(?: and toughness)? (?:is|are)(?: each)? equal to (?:twice )?"
    r"the (?:total )?number of"
    r"|change (?:this creature's|[a-z' ]{1,20}'s) base power and toughness",
    re.IGNORECASE,
)
_VARIABLE_PT_MIRROR_VETO = re.compile(
    r"\bdeals? [^.]*damage[^.]*equal to[^.]*number of cards in (?:your|their) "
    r"(?:hand|library)"
    r"|\bdraws? cards? equal to[^.]*number of cards in"
    r"|change the base power and toughness of (?:all|each|other|target|up to|the)",
    re.IGNORECASE,
)
# token_copy_matters BYTE-IDENTICAL kept mirror (ADR-0027 β): the lane fires from the
# EXACT deleted _HAND_FLOOR regex (pinned as TOKEN_COPY_MATTERS_REGEX) over the
# reminder-stripped kept_oracle — a token-COPY maker ("create a token that's a copy of
# …"), populate (CR 702.95, a token copy), or a token DOUBLER ("twice that many …
# tokens" — Adrix and Nev, Mondrak, which fork token-copy spells). NOT a structural
# CopyTokenOf/Populate arm: phase structures those (421 cards) but the 80-card struct-
# only delta is 100% reminder-text SELF-copies (Embalm/Eternalize/Offspring/Double-
# team) this reminder-stripped regex deliberately excludes. No veto needed (the regex
# is precise — it never fired on the reminder-text self-copies because they live inside
# parens). CR 702.95.
_TOKEN_COPY_MATTERS_MIRROR = re.compile(TOKEN_COPY_MATTERS_REGEX, re.IGNORECASE)
# color_change BYTE-IDENTICAL kept mirror (ADR-0027 β): the lane fires from the EXACT
# deleted SWEEP regex (pinned as COLOR_CHANGE_REGEX) over the reminder-stripped
# kept_oracle — a card that CHANGES a permanent's/spell's COLOR ("becomes the color of
# your choice", "becomes the color", "becomes all colors"). NOT a structural arm: phase
# parses these 24 INCONSISTENTLY (20 as a nested AddChosenColor modification, 4 as a
# bare Unimplemented "become"), and the only IR category they share — cat=='animate' —
# fires on 256 commander-legal cards (every man-land / animate-land anthem / "becomes a
# 4/4") vs the 24 genuine color-changers, a ~90% over-fire. The deleted oracle regex is
# precise (24/24 genuine), so the lane rides it byte-identically. No veto needed (the
# phrase "becomes the color/all colors" is unambiguous). CR 105 / 613.
_COLOR_CHANGE_MIRROR = re.compile(COLOR_CHANGE_REGEX, re.IGNORECASE)
# toughness_combat BYTE-IDENTICAL kept mirror (ADR-0027 β): the lane fires from the
# EXACT OR of two deleted producers (pinned TOUGHNESS_COMBAT_REGEX) over the reminder-
# stripped kept_oracle — the Doran / Assault Formation / High Alert combat
# redirect ("assigns combat damage equal to its toughness rather than power"), PLUS
# the broader toughness-as-VALUE payoff half ("X is … toughness", "equal to … toughness"
# — gain life / deal damage / draw / X/X token / lose life keyed on a creature's
# toughness; Geralf, Last March of the Ents, Angelic Chorus). NOT a structural
# `combat_damage_mod` arm: phase parses the Doran clause as an AssignDamageFromToughness
# modification but project._project_static_mods drops it on every multi-ability face, so
# the category fires on only 21 commander-legal (MISSES 129/133, no structural form for
# the 111 value-payoffs) and over-fires 81% on "deal damage equal to its POWER" combat
# punches (Laccolith *, Master of Cruelties). The deleted regexes are precise (133/133
# genuine), so the lane rides their OR byte-identically. Both arms are clause-local (no
# `[^.]` crossing a sentence), so this full-text scan == the deleted per-clause union
# (commander-legal: regex==mirror, 0 lost, 0 over-fire). The value-payoff arm's
# `(?! are each)` veto keeps a set-base */* ("power and toughness are each equal to …" —
# variable_pt) off the lane. CR 510.1c / 122 / 604.3.
_TOUGHNESS_COMBAT_MIRROR = re.compile(TOUGHNESS_COMBAT_REGEX, re.IGNORECASE)
# ability_copy BYTE-IDENTICAL kept mirror (ADR-0027 β): the "Ability copy" build-around
# fires from the EXACT deleted SWEEP regex (pinned ABILITY_COPY_REGEX) over the
# reminder- stripped kept_oracle — copy an activated/triggered ability (Strionic
# Resonator, Lithoform Engine, Rings of Brighthearth, Illusionist's/Battlemage's
# Bracers, Kurkesh) or a "you may copy it" spell/adventure self-copy (Chancellor of
# Tales, Tawnos), PLUS the ability-GRANTERS that import another permanent's whole
# activated suite ("has all/the activated abilities of …" — Necrotic Ooze, Experiment
# Kraj, Mairsil, Myr Welder). NOT a structural `spell_copy` arm: phase emits ONE
# undifferentiated `spell_copy` category for spell-copy AND ability-copy alike (the copy
# target — spell vs ability — is dropped), so the arm fires on 303 commander-legal —
# over-firing 90% on the spell-copy half NOT in this lane (Twincast, Reverberate, Fork)
# — and STILL misses the granters (phase parses them grant_keyword/board_grant). The
# deleted regex is precise (51/51 genuine), so the lane rides it byte-identically. Every
# arm is clause-local (no `[^.]` crossing a sentence), so this full-text scan == the
# deleted per-clause SWEEP union (commander-legal: regex==mirror, 51==51, 0 lost, 0
# over-fire). CR 706.10 / 113.2 / 706.2.
_ABILITY_COPY_MIRROR = re.compile(ABILITY_COPY_REGEX, re.IGNORECASE)
# gain_control NARROWED kept mirror (ADR-0027 β): the structural arm below
# (cat=='gain_control', excl donate / Owned-return / give-away) is broad and correct,
# but phase emits NO gain_control category for 9 genuine theft cards — Seize the
# Spotlight, Power of Persuasion, Invert Polarity (steal a SPELL on the stack), Wake the
# Dragon (the granted token's "gain control" trigger), Expropriate, Midnight Crusader
# Shuttle, Captivating Glance, Herald of Leshrac, Risky Move. Recover them with the
# deleted producer's `gain control of` (pinned GAIN_CONTROL_REGEX) over the reminder-
# stripped kept_oracle, run PER-CLAUSE and VETOED per-clause by the give-away / reset /
# protection over-fires the structural arm correctly drops: a reset-to-self ("gain
# control of all permanents you OWN" — Gruul Charm, Brand), a give-away ("<a/that/each/
# another/target> player gains control" — Risky Move's symmetric clause, Herald's leave-
# reset), and a protection ("can't / cannot gain control" — Guardian Beast). PER-CLAUSE
# (not flat) so one clause's veto can't kill another clause's genuine theft —
# Captivating Glance ("if you win, gain control …" / "Otherwise, that player gains
# control …") and
# Herald (upkeep theft / leave-reset) each keep their theft sentence. A byte-identical
# full-text mirror would re-introduce the 4 over-fires the structural arm dropped, so
# this is narrowed rather than byte-identical. CR 800.4a / 720.1.
_GAIN_CONTROL_MIRROR = re.compile(GAIN_CONTROL_REGEX, re.IGNORECASE)
_GAIN_CONTROL_MIRROR_VETO = re.compile(
    r"can(?:'t|not) gain control"
    r"|gain control of (?:all |each )?[^.]*\byou own\b"
    r"|(?:a|that|each|another|target) player gains control",
    re.IGNORECASE,
)
# ltb_matters NARROWED kept mirror (ADR-0027 β): the structural `leaves`-trigger arm
# below catches phase's structured "whenever ANOTHER permanent leaves the battlefield"
# payoffs (+9 recall: DFC back faces, bounce payoffs), but phase leaves the bulk of
# the lane textual — the Revolt "a permanent left the battlefield this turn" condition
# is a static check (no trigger), and the self-LTB payoff ("when ~ leaves the
# battlefield, create a token" — Walker of the Grove, Sengir Autocrat, Skyclave
# Apparition) is a SelfRef trigger (subject=None, gated out of the structural arm).
# Recover them with the deleted producer's exact regex (pinned LTB_MATTERS_SWEEP_REGEX)
# over the reminder-stripped kept_oracle, run PER-CLAUSE and VETOED per-clause by the
# O-Ring self-LTB-EXILE form ("exile … until ~ leaves the battlefield" — Banishing
# Light / Static Prison / Assimilation Aegis): that clause's "until ~ leaves" is the
# END of a removal LOCK, NOT a leaves-MATTERS payoff (it already routes to
# exile_until_leaves). PER-CLAUSE (not flat) so the veto on the "exile … until ~
# leaves" clause can't kill a co-printed genuine leave payoff (Skyclave Apparition
# keeps its "when ~ leaves … create a token" sentence). The regex's `when [^.]* leaves
# the battlefield` arm spans a whole "When ~ enters, exile … until ~ leaves" clause, so
# the veto and the match share one clause and the 93 O-Ring over-fires drop (100%
# over-fire vs Scryfall, 0 genuine payoff lost). A byte-identical full-text mirror would
# re-introduce them, so this is narrowed. CR 603.6e / 700.4.
_LTB_MATTERS_MIRROR = re.compile(LTB_MATTERS_SWEEP_REGEX, re.IGNORECASE)
_LTB_MATTERS_MIRROR_VETO = re.compile(
    r"exile [^.]*until [^.]*leaves the battlefield", re.IGNORECASE
)
# self_counter_grow NARROWED kept mirror (ADR-0027 β): the structural arm above fires on
# a place_counter carrying the SelfRef self-anchor marker (project @ SIDECAR v12), a
# +503
# recall gain over the deleted regex (it catches by-name self-grow — "put a +1/+1
# counter
# on Lazav / Garza Zol / Kyler" — the pronoun-only regex missed). But phase drops the
# self-anchor on a small structural tail (the Adversary multi-pay "put that many on this
# creature", Stormwild Capridor's damage-prevention static, Scarlet Spider's
# ParentTarget
# branch) — 14 self-growers the regex caught via its SELF-ANCHORED text arms. Recover
# them
# with a NARROWED version of the deleted regex: the EXACT self-anchored arms (on him /
# her
# / itself / this creature) MINUS the loose "on it" arm, which the deleted regex used
# and
# which 100%-over-fired onto OTHER-creature counter placements ("enchanted creature
# attacks, put a +1/+1 on it" — Ordeal of Purphoros; "if it's an Angel, put two +1/+1 on
# it" — Defy Death; the go-wide counter anthems The Great Henge / Railway Brawler;
# combat
# payoffs Necropolis Regent / Stensia Masquerade — 103 over-fires, the SelfRef IR gate
# correctly excludes them). Run PER-CLAUSE over the reminder-stripped kept_oracle. A
# byte-identical full-text mirror would re-introduce the 103 over-fires, so this is
# narrowed. The self-power-scaling commander cross-open ("X is ~'s power") rides
# self_power_scale_match (re-homed from the deleted _DETECTORS add). CR 122.1 / 614.12.
_SELF_COUNTER_GROW_MIRROR = re.compile(
    "enters with (?:x|\\d+|a|an|one|two|three) \\+1/\\+1 counters? on "
    "(?:him|her|itself|this)"
    "|put (?:a|one|two|three|x|\\d+) \\+1/\\+1 counters? on "
    "(?:him|her|itself|this creature)\\b"
    "|put that many \\+1/\\+1 counters? on (?:him|her|itself|this creature)",
    re.IGNORECASE,
)


# typed_enters_punish opponent-recipient discriminator (ADR-0027): phase scopes
# Purphoros / Witty Roastmaster's damage effect 'any' (the "each opponent" recipient
# survives only in raw), so the lane reads the raw for an opponent recipient when the
# structural scope / subject controller doesn't already mark it.
_TYPED_ENTERS_OPP_RAW = re.compile(
    r"each opponent|target opponent|your opponents|any target", re.IGNORECASE
)


# ADR-0027 power_double — the word-mirror discriminator. phase does NOT set
# Quantity(op='multiply') for P/T DOUBLING (Unleash Fury / Mr. Orfeo / Unnatural
# Growth all have amount=None on the pump), so a x2 power-double is category-
# indistinguishable from a flat +X pump by structure alone — the raw "double …
# power" / "power … doubled" phrasing IS the discriminator. (Keying off the Scryfall
# `Double` keyword would over-fire: most Double cards double DAMAGE / counters /
# tokens, not power.)
_POWER_DOUBLE_RAW = re.compile(r"double[^.]*power|power[^.]*doubled", re.IGNORECASE)


def _is_scaling_count(amount: Quantity | None, raw: str) -> bool:
    """True when an operand is a genuine BOARD-COUNT scaler ("for each <X>"), not a
    bare X-spell whose X is the cast cost. A NAMED count op (counters / domain /
    devotion / party) is always a scale; the generic `count`/`multiply` op is a scale
    only with a counted SUBJECT or a "for each" / "number of" raw (a bare X-spell —
    Braingeyser — has neither). Gates draw_for_each / scaling_pump off X-spells."""
    if amount is None:
        return False
    if amount.op in _NAMED_SCALE_OPS:
        return True
    if amount.op not in ("count", "multiply"):
        return False
    return amount.subject is not None or bool(_FOR_EACH_RAW.search(raw or ""))


# typed_anthem_multi (ADR-0027): phase drops the typed subject entirely on some pump
# anthems (subject=None), so neither the AnyOf nor the 2+-subtypes structural guard
# can see the disjunction. Recover from the pump effect's raw: "that's a X[, a Y]…,?
# or a Z" — 2+ comma/"or"-separated subtype tokens (single-type stays type_matters).
# Requires the leading "that's a/an" so a single-target pump can't match.
_TYPED_ANTHEM_MULTI_RAW = re.compile(
    r"that's (?:an? )?[A-Z][a-z]+(?:,? (?:an? )?[A-Z][a-z]+)*,? or (?:an? )?[A-Z][a-z]+"
)

# Batch E — made artifact-token subtype → (signal key, scope).
_TOKEN_SUBTYPE_KEYS: dict[str, tuple[str, str]] = {
    "treasure": ("treasure_matters", "you"),
    "clue": ("clue_matters", "you"),
    "food": ("food_matters", "you"),
    "blood": ("blood_matters", "you"),
}


# ADR-0027 (q2-D3) noncreature_cast_punish — the card-type set a "noncreature spell"
# cast-trigger subject may carry (phase encodes "noncreature spell" either as the
# NotType:Creature predicate or as the explicit type list "an artifact, instant, or
# sorcery spell"). Creature must be ABSENT for the noncreature gate. CR 603.2.
_NONCREATURE_SPELL_TYPES: frozenset[str] = frozenset(
    {"Instant", "Sorcery", "Artifact", "Enchantment", "Planeswalker", "Battle"}
)


def _ftypes(f: object) -> frozenset[str]:
    return frozenset(f.card_types) if isinstance(f, Filter) else frozenset()


def _is_self_counter_marker(f: object) -> bool:
    """True for the ADR-0027 β self-anchor marker project.py stamps on a +1/+1 counter
    PLACEMENT a creature puts on ITSELF (adapt/monstrosity/renown + "put a +1/+1
    counter on ~/this creature/it" — project._SELF_COUNTER_MARKER, a Filter carrying
    only the ``SelfRef`` predicate). The self_counter_grow lane reads this to split
    self-grow from a "+1/+1 counter on TARGET / another creature" doer; self_pump treats
    it as the self shape it already fired on (subject=None at the regex base). CR
    122.1 / 614.12."""
    return isinstance(f, Filter) and f.predicates == ("SelfRef",)


def _is_permanent_subtype_destroy(f: object) -> bool:
    """True when ``f`` is a destroy/damage subject naming a permanent by SUBTYPE only
    (card_types empty) and that subtype is NOT a land — "destroy target Wall /
    Equipment / Aura" is removal (ADR-0027 removal_matters shape 2), while "destroy
    target Island" is land_destruction. Any non-land subtype qualifies (creature
    subtypes, Equipment/Aura/Vehicle/Room permanent subtypes); a subject that is ALL
    land subtypes returns False."""
    if not isinstance(f, Filter) or not f.subtypes:
        return False
    return any(s.lower() not in _LAND_SUBTYPES for s in f.subtypes)


# ADR-0027 destroy_legendary — phase stamps this exact predicate on a destroy
# subject only for an explicitly legendary-restricted target (Bounty Agent, Tsabo
# Tavoc). NB: match the EXACT string, NOT a "legendary" substring — `NotSupertype:
# Legendary` ("destroy target NONlegendary creature" — Cast Down, One Ring) is the
# OPPOSITE and must NOT fire. (CR 205.4a.)
_LEGENDARY_DESTROY_PRED = "HasSupertype:Legendary"

# ADR-0027 mass_bounce — the predicates a board-wide bounce subject may carry while
# still being a full board sweep (vs a single-target rider): "all OTHER permanents",
# "all NONLAND permanents". A graveyard-recursion subject ("return all creature
# cards from graveyards" — Garna, Empty the Catacombs) carries InZone/Owned and is
# EXCLUDED — that is recursion, not a board bounce.
_MASS_BOUNCE_ZONE_PREDS = frozenset({"InZone", "Owned"})


def _is_mass_bounce_subject(f: object) -> bool:
    """The board-wide bounce subject (ADR-0027 mass_bounce): a generic Creature /
    Permanent card-type sweep, EXCLUDING graveyard/library recursion (an InZone /
    Owned predicate, which marks "all <type> cards from graveyards" — recursion, not
    a board bounce). Color / CMC / token / power-threshold predicates are KEPT — a
    "return all green permanents" / "all attacking creatures" sweep is still mass
    bounce. The mass discriminator (counter_kind=='all') is applied by the caller."""
    if not isinstance(f, Filter):
        return False
    if _MASS_BOUNCE_ZONE_PREDS & set(f.predicates):
        return False
    return "Creature" in f.card_types or "Permanent" in f.card_types


def _filter_controller(f: object) -> str:
    return f.controller if isinstance(f, Filter) else "any"


def _fsubs_lower(f: object) -> frozenset[str]:
    return (
        frozenset(s.lower() for s in f.subtypes)
        if isinstance(f, Filter)
        else frozenset()
    )


def _has_predicate(f: object, pred: str) -> bool:
    return isinstance(f, Filter) and pred in f.predicates


def _hoses_a_color(f: object) -> bool:
    """A filter selecting a SPECIFIC color to remove (HasColor:Red) — "destroy target
    blue creature" / "destroy all black creatures" actively hoses that color (Blue
    Elemental Blast, Cleanse). NotColor ("destroy NONblack creature") is restricted
    removal sparing your own color, NOT a hoser — excluded, exactly as the regex omits
    it (its contiguous "{color} creature" can't match "nonblack creature"). The
    NotColor-anthem hoser (Evincar's "nonblack creatures get -1/-1") is a separate
    pump-debuff form the regex still covers; not captured here. NOT 'any color
    mention' — the lane also requires a removal effect context."""
    return isinstance(f, Filter) and any(
        p.startswith("HasColor:") for p in f.predicates
    )


# Copy/clone lanes by the COPIED permanent type. clone_matters = a CREATURE copy
# (Clone, Spark Double); the rest are per-permanent-type copy lanes. A copy of a
# generic "Permanent" (Crystalline Resonance) counts toward EVERY type lane AND the
# generic copy_permanent — the hierarchy Dan asked for (anything that can target
# permanents shows up for permanents AND each permanent type). Spell-copy (instant/
# sorcery) is a SEPARATE concern (spell_copy_matters), not a clone.
_COPY_TYPE_LANES: dict[str, str] = {
    "Creature": "clone_matters",
    "Artifact": "copy_artifact",
    "Enchantment": "copy_enchantment",
    "Land": "copy_land",
    "Planeswalker": "copy_planeswalker",
}


def _clone_copy_lanes(f: object, vocab: frozenset[str]) -> tuple[str, ...]:
    """The copy lanes a clone effect feeds, from the COPIED filter's types. A generic
    Permanent copy fans out to copy_permanent + every per-type lane; a creature SUBTYPE
    (Dinosaur, Ally) with no card type is still a creature copy → clone_matters."""
    if not isinstance(f, Filter):
        return ()
    types = set(f.card_types)
    lanes: set[str] = set()
    if "Permanent" in types:
        lanes.add("copy_permanent")
        lanes.update(_COPY_TYPE_LANES.values())
    for t in types:
        if t in _COPY_TYPE_LANES:
            lanes.add(_COPY_TYPE_LANES[t])
    if any(_resolve_subject(s, vocab) for s in f.subtypes):
        lanes.add("clone_matters")  # a creature subtype (Dinosaur, Ally) → creature
    return tuple(sorted(lanes))


def _is_multicolor_pred(p: str) -> bool:
    """A ColorCount predicate selecting MULTICOLORED objects (CR: 2+ colors) — GE>=2
    or EQ>=2/3. (ColorCount GE:1 = 'is colored', EQ:0 = colorless, EQ:1 = mono.)"""
    parts = p.split(":")
    if len(parts) != 3 or parts[0] != "ColorCount" or not parts[2].isdigit():
        return False
    n = int(parts[2])
    return (parts[1] == "GE" and n >= 2) or (parts[1] == "EQ" and n >= 2)


def _predicate_build_around_lanes(f: object) -> list[str]:
    """Batch 5 — color / power BUILD-AROUND lane keys from a subject filter's enriched
    predicates. Gated on controller='you' (a removal TARGET — "destroy target creature
    with power 4 or greater" — is controller 'any', and the regex lanes avoid those
    the same way via a "you control" anchor), except colorless, which the regex reads
    unscoped too (Ancient Stirrings reveals a colorless card). A dynamic power
    comparison (":*", e.g. "power less than this creature's") is a fight-style relative
    check, not a fixed theme threshold, so it never fires."""
    if not isinstance(f, Filter):
        return []
    you = f.controller == "you"
    out: list[str] = []
    for p in f.predicates:
        if p == "ColorCount:EQ:0" and f.controller in ("you", "any"):
            out.append("colorless_matters")
        elif you and _is_multicolor_pred(p):
            out.append("multicolor_matters")
        elif (
            you
            and not p.endswith(":*")
            and p.startswith(("PtComparison:Power:GE:", "PtComparison:Power:GT:"))
        ):
            out.append("power_matters")
        elif (
            you
            and not p.endswith(":*")
            and p.startswith(("PtComparison:Power:LE:", "PtComparison:Power:LT:"))
        ):
            out.append("low_power_matters")
        # vanilla_matters (ADR-0027): the HasNoAbilities subject-Filter predicate —
        # a payoff that pumps / triggers off creatures with no abilities (Ruxa,
        # Muraganda Petroglyphs). The predicate is its own discriminator (a card
        # merely BEING vanilla never carries it — it's a property of OTHER cards'
        # Filters), so only true vanilla payoffs fire. Gate to controller in
        # {'you','any'} (a shared-board static like Muraganda is 'any'); an
        # opponent-side "destroy a creature with no abilities" stays out. CR 113.3.
        elif p == "HasNoAbilities" and f.controller in ("you", "any"):
            out.append("vanilla_matters")
    return out


def _reanimates_creature(e: object) -> bool:
    """A reanimate effect that returns CREATURE cards (matches the regex detector,
    which requires 'creature cards' — a Permanent-card return like Sun Titan is a
    separate recursion engine, not the reanimator archetype).

    ADR-0027: phase drops the creature subject (subject=None) on the pay-{X}/"when
    you do" nesting (Isareth) and many "return target creature card from a graveyard
    to the battlefield" shapes (Beacon of Unrest, Liliana Death's Majesty). Fall back
    to the effect raw so the creature-card reanimation is still recognized."""
    f = getattr(e, "subject", None)
    if isinstance(f, Filter) and "Creature" in f.card_types:
        return True
    if f is not None:
        return False
    return bool(_REANIMATE_CREATURE_RAW.search(getattr(e, "raw", "") or ""))


def _kindred_subjects(f: object, vocab: frozenset[str]) -> list[str]:
    """Resolved creature-subtype subjects of a YOUR-controlled (or unscoped) Filter
    — the tribal payoff axis ("Goblins you control", "for each Goblin you control").
    An opponent-controlled tribe is not your tribal build-around, so it's dropped."""
    if not isinstance(f, Filter) or f.controller == "opp":
        return []
    return [s for s in (_resolve_subject(x, vocab) for x in f.subtypes) if s]


def _token_kindred_subject(f: object, vocab: frozenset[str]) -> str | None:
    """A creature-token filter → its resolved kindred subject ("" if none); None for
    a non-creature token (which token_maker does not cover). Matches the regex
    detector's 'last creature subtype' choice."""
    if not isinstance(f, Filter) or "Creature" not in f.card_types:
        return None
    for raw in reversed(f.subtypes):
        subject = _resolve_subject(raw, vocab)
        if subject:
            return subject
    return ""


# exile_until_leaves (ADR-0027) — the "exile until ~ leaves the battlefield"
# bounce-removal idiom (Oblivion Ring, Fiend Hunter, Banisher Priest, Glorious
# Protector). A plain exile-removal (Path to Exile, Swords to Plowshares) has no
# linked return and no "until ~ leaves" phrase, so it does not fire — that phrase
# / the linked return IS the discriminator vs permanent exile.
_EXILE_UNTIL_LEAVES_RAW = re.compile(
    r"until [^.]*leaves the battlefield", re.IGNORECASE
)


# ADR-0027 β — activated_ability arm tuning constants (see extract_signals_ir).
# Effect categories that mark a NON-engine activated ability: 'ramp' (phase's Mana
# effect — the {T}: Add / mana-dork flood — is_mana_ability, CR 605.1a) and 'attach'
# (equip, an Attach the deleted regex never matched). An activated ability whose every
# effect is one of these is NOT the meaningful engine the lane wants.
_ACTIVATED_ABILITY_DROP_EFFECTS: frozenset[str] = frozenset({"ramp", "attach"})
# Additional-cost tokens (CR 601.2g) that EXCLUDE a generic-mana-cost ability from the
# arm's mana branch: the deleted regex's generic branch ({(?:\d+|x)\}[^.\n]{0,18}:) had
# an 18-char window that dropped one-shots with a sac/discard/exile/etc additional cost
# ("{3}{B}, Sacrifice this: …"). A 'tap'/'untap' anchor OVERRIDES this (the regex's
# {T}:/{Q}: branch fired regardless of an extra cost — Arcum's {T}, Crackleburr's {Q}).
_ACTIVATED_ABILITY_EXTRA_COSTS: frozenset[str] = frozenset(
    {
        "sacrifice",
        "sacself",
        "discard",
        "discardself",
        "exile",
        "exilegrave",
        "paylife",
        "removecounter",
        "mill",
        "return",
        "reveal",
    }
)


def _is_exile_until_leaves(ir: Card) -> bool:
    """True for either O-Ring shape: (A) a TWO-ABILITY card — an `exile` effect
    sending to:exile co-occurring with a SECOND ability whose trigger is dies/leaves
    and whose effect is a `reanimate` to:battlefield (the linked return); or (B) a
    ONE-ABILITY INLINE card — an `exile`/`blink` effect whose raw carries the
    "until ~ leaves the battlefield" phrase (the return is textual, not structured).
    phase coerces O-Ring's "leaves" trigger to event=='dies', so both events count."""
    has_exile_to_exile = False
    has_linked_return = False
    for ab in ir.all_abilities():
        trig = ab.trigger
        for e in ab.effects:
            # Branch B — inline "exile/blink … until ~ leaves the battlefield".
            if e.category in ("exile", "blink") and _EXILE_UNTIL_LEAVES_RAW.search(
                e.raw or ""
            ):
                return True
            # Branch A — collect the two halves across abilities.
            if e.category == "exile" and "to:exile" in e.zones:
                has_exile_to_exile = True
            if (
                trig is not None
                and trig.event in ("dies", "leaves")
                and e.category == "reanimate"
                and "to:battlefield" in e.zones
            ):
                has_linked_return = True
    return has_exile_to_exile and has_linked_return


def _condition_has_kind(cond: object, kind: str) -> bool:
    """True if ``cond`` (or any node in its nested And/Or/Not tree) has ``kind``.
    phase nests a manaspentcondition under wrapper kinds (Satoru the Infiltrator's
    'or' wraps it alongside a 'not'>'wascast'), so the recursion is required. (ADR-0027
    tranche2-C free_creature_payoff.)"""
    if not isinstance(cond, Condition):
        return False
    if cond.kind == kind:
        return True
    return any(_condition_has_kind(n, kind) for n in cond.nested)


def _condition_has_zone(cond: object, zone: str) -> bool:
    """True if ``cond`` (or any node in its nested And/Or/Not tree) references
    ``zone``. phase nests a sourceinzone('command') under a wrapper 'or' alongside
    a sourceinzone('battlefield') for the on-battlefield-OR-command-zone eminence
    gate (Edgar Markov, Arahbo), so the recursion is required. (ADR-0027 cmdzone.)"""
    if not isinstance(cond, Condition):
        return False
    if zone in cond.zones:
        return True
    return any(_condition_has_zone(n, zone) for n in cond.nested)


def extract_signals_ir(
    card: dict,
    ir: Card | None,
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    include_membership: bool = True,
) -> list[Signal]:
    """Derive the A2 slice of Signals from the structured Card IR (5 keys).

    Same Signal contract as ``extract_signals``, restricted to ``IR_SLICE_KEYS`` so
    the two paths can be diffed key-for-key. Returns ``[]`` when the card has no IR
    (not yet projected / brand-new set) so a dispatcher can fall back to regexes.

    ``include_membership`` mirrors ``extract_signals``: it gates the signals derived
    from what the card *is* (own card-type / own subtype tribal membership), so the
    deck-aggregate path (``include_membership=False`` for the 99) doesn't flood the
    avenues with every creature's race and type — only the commander's. Threaded so
    ``extract_signals_hybrid`` can reproduce a membership-bearing key IDENTICALLY to
    ``extract_signals`` for a given ``include_membership`` (ADR-0027)."""
    if ir is None:
        return []
    name = card.get("name", "")
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def add(key: str, scope: str, subject: str, raw: str, conf: str = "high") -> None:
        ident = (key, scope, subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(Signal(key, scope, subject, raw, name, conf))

    # A self-cast-from-graveyard card (flashback / escape / disturb …) cares about
    # its own graveyard.
    if "graveyard" in ir.castable_zones:
        add("graveyard_matters", "you", "", "")

    # lifeloss_matters paylife VETO (ADR-0027): a card whose ONLY pay-life ability is
    # mana fixing is a painland/fetchland/shockland, not a life-as-resource engine —
    # phase types those COST[paylife,tap]→ramp identically. Mirror the regex's land
    # VETO so a paylife mana-source never opens the lane.
    card_is_land = "land" in (card.get("type_line") or "").lower()
    # A Saga / lore-counter card: phase types its chapter trigger as the same
    # counter_added event a +1/+1-counter payoff carries (ADR-0027 — see
    # counter_place_trigger below). CR 714.2.
    _is_lore_counter_card = (
        "saga" in (card.get("type_line") or "").lower()
        or "lore counter" in (card.get("oracle_text") or "").lower()
    )

    # exile_until_leaves (ADR-0027) — a card-level shape (the two-ability O-Ring
    # form spans abilities), so it is decided once over the whole IR.
    if _is_exile_until_leaves(ir):
        add("exile_until_leaves", "you", "", "")

    for ab in ir.all_abilities():
        # cmdzone_ability (ADR-0027) — an ability that functions FROM the command
        # zone (Eminence) or gates on the source being there: phase exposes the
        # command-zone permission either as a zone the ability operates in
        # (``ab.zones`` carries 'command' for an activate-from-CZ ability) or as a
        # Condition whose recursive zone set contains 'command' (the triggered-
        # Eminence build-arounds — Oloro's sourceinzone('command'); Edgar/Arahbo's
        # 'or'-wrapped sourceinzone('command') + sourceinzone('battlefield')). The
        # 'command' zone in the condition tree is the unambiguous discriminator —
        # command-zone references are rare and always intentional build-arounds, so
        # there is no over-fire (commander-legal IR-vs-regex over-fire == 0). The
        # STATIC-Eminence half (The Ur-Dragon's cost-reducer) drops the condition in
        # phase's parse, so it rides the byte-identical _IR_KEPT_DETECTORS word
        # mirror (the exact deleted SWEEP regex) instead. CR 702.107 / 903.6.
        if "command" in ab.zones or _condition_has_zone(ab.condition, "command"):
            add("cmdzone_ability", "you", "", "")
        # curse_matters cares-about half (ADR-0027 t2b4a-B) — a card that REFERENCES
        # the Curse subtype: a trigger narrowed to Curses (Lynde, Cheerful Tormentor:
        # Trigger(event='dies', subject=Filter(subtypes=('Curse',)))) or an effect
        # acting on a Curse subject (a "return target Curse" recursion). The literal
        # 'Curse' subtype string is the precise anchor — inherently name-immune (a card
        # NAMED "...Curse" that is not an Aura — Curse and references no Curse subtype
        # carries no 'Curse' in any Filter.subtypes), strictly cleaner than the regex.
        # Curse is an Aura subtype that enchants a player (CR 205.3 / 702.39), NOT a
        # creature subtype, so the CREATURE_SUBTYPES vocab gate does NOT apply. Scope:
        # controller you/any (Lynde's is 'you'; a "target Curse" removal is 'any').
        if (
            ab.trigger is not None
            and ab.trigger.subject is not None
            and "Curse" in ab.trigger.subject.subtypes
        ):
            add("curse_matters", "you", "", "")
        for e in ab.effects:
            if e.subject is not None and "Curse" in getattr(e.subject, "subtypes", ()):
                add("curse_matters", "you", "", e.raw or "")
        # xspell_matters (ADR-0027 t2b4a-B) — the {X}-spells payoff lane. PRIMARY:
        # phase encodes printed-{X}-in-cost (CR 202.1) as the `HasXInManaCost`
        # predicate on a `cast_spell` trigger's subject Filter (Zaxara, Nev, Zimone,
        # Anina, …, 9 clean payoffs). A precise structured predicate — no over-fire.
        # KEPT MIRROR: phase DROPS the predicate on a couple forms (Unbound
        # Flourishing's permanent-spell cast trigger; Rosheen Meanderer's "costs that
        # contain {X}" mana-enabler folded to a bare ramp effect), so scan the effect
        # raw with the same hook the deleted _DETECTORS row used, MINUS the hoser veto
        # ("can't be cast" — Gaddock Teeg, naturally already excluded from the
        # predicate arm since a ban is a restriction effect, not a payoff trigger).
        if (
            ab.trigger is not None
            and ab.trigger.event == "cast_spell"
            and (
                ab.trigger.subject is not None
                and "HasXInManaCost" in ab.trigger.subject.predicates
            )
        ):
            add("xspell_matters", "you", "", "")
        for e in ab.effects:
            r = e.raw or ""
            if _XSPELL_HOOK_RE.search(r) and not _XSPELL_VETO_RE.search(r):
                add("xspell_matters", "you", "", r)
        # keyword_soup (ADR-0027): a keyword-stacking granter — Odric / Akroma's
        # Memorial / Rayami emit one grant_keyword Effect PER keyword from a single
        # ability (the counter_kind carries each). >=5 DISTINCT evergreen keywords in
        # ONE ability isolates the genuine team-share/absorb soup (Odric, Concerted
        # Effort, Cairn Wanderer) from a single-creature 3-4-keyword bundle (Sword of
        # Vengeance). Per-ability (not per-card) so two separate 3-keyword grants don't
        # falsely sum to 6. The "the same is true for X, Y, …" idiom phase under-parses
        # to a single grant on a few cards (Indominus Rex, Urborg Scavengers) rides the
        # kept oracle mirror below. CR 702 evergreen keywords.
        _soup_cks = {
            (e.counter_kind or "").replace(" ", "").lower()
            for e in ab.effects
            if e.category == "grant_keyword"
        }
        if len(_soup_cks & _EVERGREEN_CK) >= 5:
            add("keyword_soup", "you", "", "")
        # power_tap_engine (ADR-0027) — ability-level: an ACTIVATED ability whose cost
        # contains 'tap' AND some effect's raw scales with a creature's power. The
        # repeatable {T} power-scaling engine (Marwyn, Selvala, Staff of Domination).
        if (
            ab.kind == "activated"
            and "tap" in (ab.cost or "")
            and any(_POWER_SCALING_RAW.search(e.raw or "") for e in ab.effects)
        ):
            add("power_tap_engine", "you", "", "")
        # opp_top_exile (ADR-0027 q2-D2) — ability-level: a name-lock / impulse-cast
        # engine that exiles from an OPPONENT's zone AND lets a card be PLAYED from
        # there (the commander wants to SEE/steal opponents' tops). Two structural
        # sub-shapes:
        #   (A) impulse-cast — an exile Effect scope=='opp' co-occurring (same ability)
        #       with a cast_from_zone Effect scope=='opp' (the "you may cast it" /
        #       "they may play it" follow-through) — Ragavan, Gonti, Villainous Wealth,
        #       Wrexial, Diluvian Primordial (combat-damage / ninjutsu / graveyard-cast
        #       steal). 50 of these the deleted "exile the top card of <opponent>"
        #       regex never reached — legitimate breadth, not over-fire (each carries
        #       the cast_from_zone play-it clause; none is bare exile-as-removal).
        #   (B) library-tag — an exile Effect scope=='opp' carrying an 'in:library'
        #       zone (Brainstealer Dragon, Ulamog the Defiler) — phase tagged the
        #       library origin directly.
        # The cast_from_zone / in:library anchor is what separates this from opponent-
        # targeted exile-as-REMOVAL (Path to Exile, Agonizing Remorse): a bare exile
        # scope=='opp' NEVER fires here. Scope is the engine controller 'you' (matching
        # the deleted regex), NOT the opp scope of the exiled object. The name-lock /
        # peek subset phase under-parses (Circu's exile scope=='any'; Scrib Nibblers; a
        # GRANTED "exile the top card" on Predators' Hour) rides the _IR_KEPT_DETECTORS
        # word mirror below (the exact deleted regex), so net recall ≥ regex.
        _exile_opp = False
        _exile_opp_lib = False
        _cfz_opp = False
        for e in ab.effects:
            if e.category == "exile" and e.scope == "opp":
                _exile_opp = True
                if "in:library" in e.zones:
                    _exile_opp_lib = True
            elif e.category == "cast_from_zone" and e.scope == "opp":
                _cfz_opp = True
        if _exile_opp_lib or (_exile_opp and _cfz_opp):
            add("opp_top_exile", "you", "", "")
        # impulse_top_play (ADR-0027 β) — ability-level: a TEMPORARY exile-the-top-then-
        # play engine that casts from the top of YOUR library. The structural anchor is
        # a NON-static cast_from_zone Effect carrying the recovered 'from:library' zone
        # (project._recover_library_zones, SIDECAR_VERSION 4): a spell / triggered /
        # activated ability — Light Up the Stage (spell), Ragavan (triggered), Chandra,
        # Torch of Defiance (activated), Etali, Narset, Collected Conjuring. The ab.kind
        # split is the discriminator vs the SIBLING play_from_top lane: a STATIC
        # cast_from_zone+from:library is an ONGOING top-play permission (Future Sight,
        # Bolas's Citadel) and belongs to play_from_top, NOT here — so this arm gates on
        # ab.kind != 'static'. (Today phase's supplement creates the static-permission
        # cast_from_zone AFTER the zone-recovery pass, so the static shape never carries
        # from:library and play_from_top stays DEFERRED on regex; the non-static gate
        # here is the correct, future-proof split regardless.) The 105 cards this arm
        # adds over the deleted regex are all real impulse engines (legitimate breadth).
        # The tail phase under-parses (the "you may play it this turn" follow-through
        # folded into a categoryless effect, the modal "from among" clause) rides the
        # per-clause _IMPULSE_TOP_PLAY_SWEEP_RE mirror below (the EXACT deleted regex).
        # CR 601.3b.
        for e in ab.effects:
            if (
                e.category == "cast_from_zone"
                and "from:library" in e.zones
                and ab.kind != "static"
            ):
                add("impulse_top_play", "you", "", e.raw or "")
                break
        # opponent_counter_grant (ADR-0027) — ability-level: a DETRIMENTAL counter
        # (CR 122.1d) placed on an OPPONENT's permanent (the tap-down / detrimental-mark
        # punish lane). Two recipient shapes: (A) a place_counter whose own
        # subject.controller=='opp' — bounty (Mathas, Chevill), stun (Referee Squad),
        # plus the custom detrimental marks (bribery — Gwafa Hazid, slime — Toxrill,
        # rejection — Tolarian Contempt, m1m1 — Ifnir Deadlands); (B) the "tap target
        # ... and put a stun counter on IT" shape (Freeze in Place), where phase loses
        # the place_counter subject to the "it" pronoun — recovered by a co-occurring
        # tap Effect in the SAME ability whose subject.controller=='opp'. The
        # counter_kind must be DETRIMENTAL: exclude beneficial +1/+1 grants (p1p1 —
        # Hunter of Eyeblights places one to enable its own counter-removal, the wrong
        # direction) and beneficial keyword/shield counters, which would help the
        # opponent. Self-stun drawbacks (Pugnacious Hammerskull "stun counter on it" =
        # on itself) have no opp recipient and no co-tap, so they never fire. Breadth
        # over the bounty/stun regex is legitimate gain (CR 122.1d — these are all real
        # opponent-detrimental-counter cards), not over-fire.
        _opp_tap_here = any(
            e.category == "tap" and _filter_controller(e.subject) == "opp"
            for e in ab.effects
        )
        for e in ab.effects:
            if e.category != "place_counter":
                continue
            if e.counter_kind in _OPP_COUNTER_BENEFICIAL:
                continue
            recip_opp = _filter_controller(e.subject) == "opp"
            stun_via_tap = e.counter_kind == "stun" and _opp_tap_here
            if recip_opp or stun_via_tap:
                add("opponent_counter_grant", "opponents", "", "")
        # win_lose_game (ADR-0027 t2b4a-B) — the terminal-outcome lane: a win_game or
        # lose_game Effect category (Thassa's Oracle / Laboratory Maniac win_game,
        # Door to Nothingness / Triskaidekaphobia lose_game, Felidar Sovereign's
        # upkeep-conditional win). These are precise alt-win/loss categories with no
        # over-fire surface (CR 104.2). Scope 'any' to match the deleted SWEEP row,
        # which matched BOTH self-wins ("you win the game", e.scope=='you') and
        # opponent-losses ("that player loses the game") under one forced scope — the
        # behavior-neutral choice. "Don't lose for having 0 life" (Phyrexian Unlife)
        # is correctly cat=='lose_game' too (a lose-prevention combo enabler IN the
        # lane). The per-effect e.scope is available if a future split is wanted.
        for e in ab.effects:
            if e.category in ("win_game", "lose_game"):
                add("win_lose_game", "any", "", e.raw or "")
        # ADR-0027 β — cost_reduction (a BUILD-AROUND reducer: an effect that makes a
        # CLASS of OTHER spells/abilities you cast cheaper — Goblin Electromancer, Ruby
        # Medallion, Helm of Awakening, Urza's Incubator). project.py carries two cat==
        # "cost_reduction" Effect forms (see the _COST_* discriminators above):
        #   • static ModifyCost{Reduce} (subject = the spell_filter) — already
        #     direction-correct + SelfRef-gated in project.py, so a non-None subject
        #     is trusted.
        #   • the named `reducenextspellcost` effect (subject None) — NOT direction- or
        #     SelfRef-gated, so phase mis-routes BOTH cost-INCREASE text ("cost {1}
        #     more" / "cost an additional" / a mana-floor) AND "this spell costs ...
        #     less" self-discounts (Cavern-Hoard Dragon / the Avatars) into it. Screen
        #     those: keep only a genuine "cost(s) ... less" reduction that is not a
        #     self-discount and not a cost-increase. The lane fires scope "you" (the
        #     build-around's owner), matching the deleted regex's firing identity.
        #     CR 601.2f / 118.7.
        for e in ab.effects:
            if e.category != "cost_reduction":
                continue
            if e.subject is not None:
                add("cost_reduction", "you", "", e.raw or "")
                continue
            raw = e.raw or ""
            if _COST_SELF_DISCOUNT.search(raw):
                continue
            if not _COST_LESS_REDUCER.search(raw):
                continue
            if _COST_INCREASE.search(raw):
                continue
            add("cost_reduction", "you", "", raw)
        # ADR-0027 β — debuff_matters structural arm (a -1/-1 / toughness-shrink
        # removal-and-payoff lane). Two projected Effect forms anchor it:
        #   • a `pump` Effect with amount.factor < 0 — the NEGATIVE factor IS the
        #     debuff signal. phase folds a static -N/-N onto an extracted Quantity
        #     (Dead Weight → pump, factor=-2; Weakness → factor=-2), so a self-
        #     shrinking creature ("This creature gets -1/-1 for each card in your
        #     hand" — Dread Slag) and an aura ("Enchanted creature gets -2/-2") both
        #     read structurally. A mixed-sign combat trick (Nameless Inversion's
        #     +3/-3) projects factor=+3 (the POWER side), so factor<0 correctly leaves
        #     it OUT — it's a trick, not a pure debuff.
        #   • a `place_counter` Effect with counter_kind=="m1m1" that is NOT a self-
        #     enter-with drawback. A real debuff puts -1/-1 counters on OTHER/target
        #     creatures (Skinrender, Blight Rot, the scope=="any"/"opp" placements);
        #     the 62-card self-drawback tail (persist/undying riders + "~ enters with
        #     N -1/-1 counters" — Kitchen Finks, Carnifex Demon) projects scope=="you"
        #     and is gated out. CR 122.1b / CR 613.
        for e in ab.effects:
            amt = e.amount
            is_neg_pump = (
                e.category == "pump"
                and amt is not None
                and isinstance(getattr(amt, "factor", None), int | float)
                and amt.factor < 0
            )
            is_other_m1m1 = (
                e.category == "place_counter"
                and e.counter_kind == "m1m1"
                and e.scope != "you"
            )
            if is_neg_pump or is_other_m1m1:
                add("debuff_matters", "any", "", e.raw or "")
        # ADR-0027 β — global_ability_grant (a card that grants a QUOTED activated /
        # triggered / static ability to your whole CREATURE board or to an
        # ALL-permanents set — "Creatures you control have '{T}: …'", "All artifacts
        # have '…'"; the QUOTE is the tell that splits it from a bare keyword anthem,
        # which is grant_keyword). The v9 projection emits the structural marker as a
        # board_grant Effect carrying counter_kind=="grant_ability" (a GrantAbility /
        # GrantTrigger / GrantStaticAbility static over a creature board controller you
        # or a bare all-permanents set controller any; opponent-only and single-
        # permanent Aura/Equipment grants excluded — see project._global_ability_grant_
        # markers). Fire scope "any" — the deleted SWEEP detector hard-fired scope "any"
        # for ALL matches (its firing identity), so the migrated arm matches it exactly.
        # CR 113.3 / 604.3.
        for e in ab.effects:
            if e.category == "board_grant" and e.counter_kind == "grant_ability":
                add("global_ability_grant", "any", "", e.raw or "")
        # ADR-0027 β — power-as-damage cluster (creature_ping + damage_equal_power).
        # The d6620ac projection unlock (op="power" recovery in project._quantity)
        # makes a power-scaling damage effect a STRUCTURAL anchor: a cat=="damage"
        # Effect with amount.op=="power". The damage Effect's subject IS the RECIPIENT
        # (verified on Fling / Soul's Fire / Rabid Bite: a Creature Filter for a
        # creature recipient — Rabid Bite c=opp; None for "any target"/player). The DOER
        # ("target creature you control deals …") lives in a SEPARATE target_only Effect
        # (you-controller Creature subject). The split (both may fire — Soul's Fire's
        # "your creature → any target" is BOTH a ping and a power-burn, matching the
        # deleted regexes' overlap):
        #   creature_ping ← a creature is the doer of ITS OWN power: recipient subject
        #     is a Creature, OR a self-fight ("to itself"), OR a creature-doer sibling
        #     target_only/fight, OR raw "deals damage equal to its power" (the doer's
        #     OWN power; a fling source naming the "sacrificed/exiled creature's power"
        #     is EXCLUDED by requiring "its power").
        #   damage_equal_power ← the recipient reaches a PLAYER / any target (subject
        #     is a Player Filter, OR raw player-reach — "to any target", "to (target)
        #     player", "to each opponent", "to its controller", "to you", "any other
        #     target", "player or planeswalker"). Fling-style sac-to-power fires this,
        #     not creature_ping. The byte-identical _IR_KEPT_DETECTORS mirror recovers
        #     the projection-gap tail (emblems, dungeon rooms, empty raw, no-op cards).
        # CR 119.3 (damage) / 120.6 (life loss) / 701.12 (fight).
        _has_creature_doer_sibling = any(
            e2.category in ("target_only", "fight")
            and isinstance(e2.subject, Filter)
            and "Creature" in e2.subject.card_types
            for e2 in ab.effects
        )
        for e in ab.effects:
            if not (
                e.category == "damage"
                and e.amount is not None
                and e.amount.op == "power"
            ):
                continue
            raw = e.raw or ""
            recip = e.subject
            recip_creature = (
                isinstance(recip, Filter) and "Creature" in recip.card_types
            )
            recip_player = isinstance(recip, Filter) and "Player" in recip.card_types
            if (
                recip_creature
                or _POWER_SELF_RECIP.search(raw)
                or _has_creature_doer_sibling
                or _POWER_ITS_OWN_DOER.search(raw)
            ):
                add("creature_ping", "you", "", raw)
            if recip_player or _POWER_PLAYER_RECIP.search(raw):
                add("damage_equal_power", "you", "", raw)
        for e in ab.effects:
            # creatures_matter = a go-wide/scaling lane: a count operand over your
            # creatures (any effect), OR an anthem buffing them (a pump's affected
            # set). NOT a single reanimate/destroy TARGET that happens to be a
            # creature you control — gate the affected-set case on the pump shape.
            amount_subject = e.amount.subject if e.amount is not None else None
            # Batch 8 — an effect scaling with a named deck-wide count.
            if e.amount is not None:
                if e.amount.op == "devotion":
                    add("devotion_matters", "you", "", e.raw)
                elif e.amount.op == "party":
                    add("party_matters", "you", "", e.raw)
                elif e.amount.op == "domain":
                    add("domain_matters", "you", "", e.raw)
                # Batch 3 — "for each +1/+1 counter on ~" → counters payoff. (The
                # Power operand is a lane ONLY for the power-as-damage cluster handled
                # above — a cat=="damage" Effect with amount.op=="power" opens
                # creature_ping / damage_equal_power, ADR-0027 β. For every OTHER
                # category, "equal to its power" stays ubiquitous one-off scaling, not a
                # power build-around, so it is intentionally NOT a lane here.)
                elif e.amount.op == "counters":
                    add("counters_matter", "you", "", e.raw)
                # ADR-0027 — "for each experience counter you have" → experience
                # payoff SCALER (Atreus's draw-X, Azula's pump-X). The experience
                # GAINERS ride the GivePlayerCounter -> experience_counter category
                # (_DOER_EFFECT_KEYS); this is the count-operand scaler side phase
                # collapsed to a bare op (CR 122.1).
                elif e.amount.op == "experience":
                    add("experience_matters", "you", "", e.raw)
            # creatures_matter go-wide DOERs (over-fire-gated per rules-lawyer /
            # CR 604.3): a COUNT operand over your creatures (any effect — the value
            # scales with the population), OR a TEAM ANTHEM buffing them — a pump
            # (+N/+N) or a keyword grant ("creatures you control have/gain <kw>") over
            # the GENERIC creature set. A SUBTYPE filter (Sliver/Goblin) is tribal
            # (type_matters per CR 205.3), excluded by _is_generic_creature_filter's
            # no-subtype gate. A single reanimate/destroy/bounce TARGET that happens to
            # be "a creature you control" is NOT an anthem/count → it never reaches
            # these arms (its effect is reanimate/exile/bounce, not pump/grant_keyword,
            # and its subject is the affected object, not a value operand).
            if (
                _is_generic_creature_filter(amount_subject)
                or (
                    # A team ANTHEM over the GENERIC creature set: a +N/+N pump, a
                    # keyword grant ("creatures you control have/gain <kw>"), or a mass
                    # base-P/T SET ("creatures you control have base power and toughness
                    # X/X" — Biomass Mutation: the whole board's stat line is rewritten,
                    # a go-wide reset/anthem). A single-target base-P/T set ("target
                    # creature becomes 0/1") has controller 'any', failing the generic
                    # gate, so it never reaches here.
                    e.category in ("pump", "grant_keyword", "base_pt_set")
                    and _is_generic_creature_filter(e.subject)
                )
                # MASS UNTAP ("untap ALL creatures you control" — Aggravated Assault,
                # Reveille Squad): a go-wide untap engine (multiple-attacker / pseudo-
                # vigilance / extra-combat payoff). counter_kind=="all" gates out a
                # single-target untap (scope Single) which is a one-off untapper, not
                # a board-wide care.
                or (
                    e.category == "untap"
                    and e.counter_kind == "all"
                    and _is_generic_creature_filter(e.subject)
                )
            ):
                add("creatures_matter", "you", "", e.raw)
            # land_creatures_matter (ADR-0027): a land-creatures build wants its lands
            # turned into / counted as creatures. The PAYOFF/anthem side is a pump /
            # keyword-grant / base-P/T over a Land+Creature dual-type subject (Sylvan
            # Advocate, Timber Protector, Jyoti); the MAKER side is a make_token of a
            # land-creature (Jyoti's Forest Dryad); the ANIMATOR side turns your lands
            # into creatures (Living Plane, Noyan Dar). The kept oracle mirror below
            # recovers the self-animate manlands phase drops. land_protection rides the
            # SAME animator (you/any lands becoming creatures need keeping alive vs
            # removal); add() dedups the co-fire. CR 305 + CR 110.1.
            if (
                e.category in ("pump", "grant_keyword", "base_pt_set")
                and _has_land_creature_types(e.subject)
            ) or (e.category == "make_token" and _has_land_creature_types(e.subject)):
                add("land_creatures_matter", "you", "", e.raw)
            if _is_land_animator(ab, e, ("you",)):
                add("land_creatures_matter", "you", "", e.raw)
            # land_protection (ADR-0027): a commander that animates MANY of your lands
            # (you- OR any-controlled) wants them kept alive — indestructible / hexproof
            # lands / land recursion. Shares the animator predicate with
            # land_creatures_matter (full regex parity = fire on any land-animate); the
            # kept oracle mirror recovers the self-animate manlands phase drops.
            if _is_land_animator(ab, e, ("you", "any")):
                add("land_protection", "you", "", e.raw)
            # land_denial (ADR-0027): a self-land-phasing commander (Taniwha: "all lands
            # you control phase out") wants asymmetric land-bounce/sac stax punishers —
            # its own lands phase back while opponents' stay gone. phase v0.1.19 emits a
            # dedicated `phasing` Effect; the controller=='you' Land subject is the
            # narrow tell (Reality Ripple's one-shot any-controller phase-out is
            # excluded). CR 702.26.
            if e.category == "phasing" and _is_land_subject(e.subject, ("you",)):
                add("land_denial", "you", "", e.raw)
            # artifacts_matter / enchantments_matter go-wide DOER: a COUNT operand
            # over YOUR artifacts/enchantments (affinity CR 702.41, "for each artifact
            # you control" — Nim Lasher, Storm-Kiln, Tuvasa). The value scales with
            # that permanent type's population (CR 604.3), so the deck cares about it.
            # A COMPOSITE count ("for each artifact and/or enchantment you control" —
            # Nettlecyst, Shambling Suit) fires BOTH lanes (each population is a care).
            for typed_lane in _typed_matters_lanes(amount_subject):
                add(typed_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter TUTOR/DIG DOER (CR 701.23): a
            # search/dig whose target filter IS the card type — "search your library for
            # an enchantment/artifact card" (Idyllic Tutor, Fabricate), "look at the top
            # N, you may put an artifact into your hand" (Glint-Nest Crane), composite
            # "an artifact OR enchantment card" (Enlightened Tutor → both). A SUBTYPE
            # tutor (Aura/Equipment — Steelshaper's Gift) is gated out (narrower care);
            # a generic-permanent tutor (Wargate) carries neither type. See
            # _type_tutor_lanes for the settled discriminator.
            for tutor_lane in _type_tutor_lanes(e):
                add(tutor_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter STATIC anthem/grant DOER: a mass
            # buff or keyword/type/ability grant over the GENERIC own-board artifact or
            # enchantment set ("Artifacts you control have hexproof" — Padeem; "Artifact
            # creatures you control have flying" — Workshop Elders; "Enchantment
            # creatures you control have deathtouch…" — Zur Eternal Schemer; "Artifacts
            # and enchantments you control have shroud" — Fountain Watch, composite).
            # The granted permission/buff ranges over the whole board of that type
            # (CR 604.3 / continuous static), so the deck cares about the population.
            # Gated to YOUR generic set (no subtype, controller you) — a single-target
            # buff/removal has a different subject shape and never reaches here. A
            # composite (Artifact AND Enchantment) subject fires BOTH lanes.
            # ADR-0027 β: the global_ability_grant marker (a board_grant carrying
            # counter_kind=="grant_ability") is a quoted-ability grant over a creature /
            # all-permanents board — its OWN lane, not an artifacts/enchantments anthem;
            # exclude it so an "Artifact creatures you control have '<quoted>'" grant
            # (carrying Artifact in card_types) never leaks here off the new marker.
            if (
                e.category in ("grant_keyword", "pump", "base_pt_set", "board_grant")
                and e.counter_kind != "grant_ability"
            ):
                gsub = _generic_board_subject(e.subject)
                for grant_lane in _typed_matters_lanes(gsub):
                    add(grant_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter BECOMES-TYPE DOER: a "becomes a/an
            # artifact|enchantment (creature)" type-grant (Sydri, Karn's Touch animate
            # your artifacts; Argent Mutation, Titania's Song grant the artifact type
            # for affinity/combo). phase drops the granted type to a subject=None
            # carrier; project._becomes_type_markers recovers it as a `becomes_type`
            # marker whose subject carries the granted card-type.
            if e.category == "becomes_type":
                for bt_lane in _typed_matters_lanes(e.subject):
                    add(bt_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter token + sac-payoff DOER. A
            # make_token of an Artifact subject — incl. a Treasure/Clue/Food/Powerstone
            # resource-token maker phase carries by SUBTYPE with an empty card_types
            # (CR 205.3g; Beza, Atsushi, Emissary Green) — feeds affinity/metalcraft, so
            # it fires artifacts_matter; an Enchantment-token maker ("create a Role/Aura
            # enchantment token" — Gylwain, Ellivere; Enchantment-creature tokens) fires
            # enchantments_matter. The SAC PAYOFF is symmetric: a `sacrifice` of an
            # artifact/enchantment (Atog-style outlet, "sacrifice two Foods" — Giant
            # Opportunity) values having that type's permanents as fodder (CR 701.16),
            # so it opens the lane too — the same maker+sac-payoff pairing the
            # token-subtype lanes (clue/food/treasure) read. Scoped to YOU (a
            # make_token scope you/any; a sacrifice over a non-opp subject/scope).
            esub = e.subject
            if e.category == "make_token" and e.scope in ("you", "any"):
                if _is_artifact_subject(esub):
                    add("artifacts_matter", "you", "", e.raw)
                if isinstance(esub, Filter) and "Enchantment" in esub.card_types:
                    add("enchantments_matter", "you", "", e.raw)
            if (
                e.category == "sacrifice"
                and isinstance(esub, Filter)
                and esub.controller != "opp"
                and e.scope != "opp"
            ):
                if _is_artifact_subject(esub):
                    add("artifacts_matter", "you", "", e.raw)
                if "Enchantment" in esub.card_types:
                    add("enchantments_matter", "you", "", e.raw)
            # artifacts_matter / enchantments_matter TYPE-RECURSION DOER: a graveyard
            # recursion (reanimate / graveyard→hand bounce / graveyard→library) whose
            # target is FILTERED to the card type — SINGLE-target ("return target
            # enchantment card" — Auramancer, Monk Idealist; "return target artifact
            # card" — Refurbish, Argivian Archaeologist) OR MASS ("return all
            # enchantment cards" — Crystal Chimes, Open the Vaults). The discriminator
            # is the TYPE, not mass-vs-single (CR 115.1/115.10) — type-gating = useful
            # in that type's deck. Composite fires both; generic-target ("return target
            # card" — Regrowth) fires nothing; Aura-subtype → loose enchantments member.
            for rec_lane in _type_recursion_lanes(e):
                add(rec_lane, "you", "", e.raw)
            if e.category == "gain_life" and e.scope in ("you", "any"):
                add("lifegain_matters", "you", "", e.raw)
            # graveyard_recursion (soulshift, GY→hand per CR 702.46) is a graveyard
            # payoff but NOT reanimation — it feeds graveyard_matters without the
            # reanimator / creature_recursion lanes (those are GY→battlefield).
            if e.category in ("reanimate", "mill", "graveyard_recursion"):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # GY-recursion at the TARGET's scope (ADR-0027 scope-gate fix): a bounce /
            # cast-from-zone / reanimate / blink whose target is restricted IN the
            # graveyard ('in:graveyard') is graveyard recursion — Raise Dead / Monk
            # Idealist / World Breaker / Grim Captain's Call return a card FROM a
            # graveyard. phase assigns these scope='any' (the affected OBJECT is the
            # recursion target, which carries no controller), so the old "==you" gate
            # below dropped them. Fire at _ir_scope(e.scope): 'your graveyard' stays
            # you, 'from a graveyard' / an opponent's GY (Spurnmage, scope='opp')
            # becomes the GY-hate/any avenue the scope-split already serves. A
            # battlefield→graveyard 'dies' is from:battlefield (excluded) and isn't a
            # recursion category, so it never reaches here (CR 700.4).
            if (
                e.category in ("bounce", "cast_from_zone", "reanimate", "blink")
                and "in:graveyard" in e.zones
                and "from:battlefield" not in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # GY→battlefield cheat (ADR-0027 scope-gate fix, extended): a cheat_play /
            # reanimate whose ORIGIN includes a graveyard ('from:graveyard') puts a
            # card onto the battlefield from a graveyard — reanimation. Dakkon's "from
            # your hand or graveyard onto the battlefield" carries from:graveyard after
            # the per-effect zone recovery; the disjunction's graveyard source is a
            # genuine GY payoff (the hand source is incidental).
            if (
                e.category in ("cheat_play", "reanimate")
                and "from:graveyard" in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Graveyard-cast payoff (ADR-0027): an effect that LETS YOU cast cards from
            # a graveyard (Finale of Promise's CastFromZone, Laelia, Jaya's emblem
            # marker) — the recovered 'from:graveyard' zone or a bare cast_from_zone
            # category. The keyworded self-cast (flashback/escape) rides castable_zones
            # above; this is the effect that grants the casting.
            if e.category == "cast_from_zone" and (
                not e.zones or "from:graveyard" in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # GY-recursion / GY-search at the 'from:graveyard' ORIGIN (ADR-0027 pass 2):
            # a bounce that returns a card FROM a graveyard to hand ("Return all instant
            # and sorcery cards from your graveyard to your hand" — Metallurgic
            # Summonings; the GY→hand recursion phase tags from:graveyard, not
            # in:graveyard) or a multi-zone TUTOR whose search reaches a graveyard
            # (Boonweaver scope you, Dispossess scope opp — the from:graveyard the
            # tutor zone-recovery restored). reanimate / cheat_play / cast_from_zone /
            # exile / blink from:graveyard fire above; shuffle/draw from:graveyard is
            # the "shuffle your graveyard INTO your library" branch (empties the GY,
            # anti-synergy), deliberately NOT in this set.
            if e.category in ("bounce", "tutor") and "from:graveyard" in e.zones:
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Self-mill / fill-the-yard (ADR-0027): an effect that DEPOSITS cards into a
            # graveyard ('to:graveyard') — Mulch puts the non-lands in, Atris/Marchesa
            # bin a separated pile — fuels GY payoffs. Mirrors the trigger-dimension
            # policy below: the battlefield→graveyard 'dies' movement (from:battlefield)
            # is death, not self-mill, so it's excluded. Your/any scope only (an
            # opponent-only bin is mill against them, a different lane).
            if (
                "to:graveyard" in e.zones
                and "from:battlefield" not in e.zones
                and _ir_scope(e.scope) in ("you", "any")
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Graveyard-HATE (ADR-0027): an exile EFFECT whose ORIGIN/TARGET is a
            # graveyard — 'from:graveyard' (Farewell's exile-all-graveyards mode,
            # Consecrate / Jack-o'-Lantern / Heated Argument's exile-as-cost) or
            # 'in:graveyard' (a card targeted IN a graveyard then exiled — Boneyard
            # Parley "exile … creature cards from graveyards", Disposal Mummy /
            # Deadly Cover-Up exile a card from an opponent's graveyard). The lane's
            # intent includes GY hate; _gy_scope discriminates (an opponent's GY =
            # hate, your own = escape/delve self-exile fuel; a bare "graveyards" = any).
            # Gated to a graveyard zone tag, so a to:exile-only removal (Farewell's
            # battlefield modes, Eradicate's creature exile) stays out.
            if e.category in ("exile", "blink") and (
                "from:graveyard" in e.zones or "in:graveyard" in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Zone-aware graveyard_matters (structural projection): an effect that
            # targets/counts/copies cards IN a graveyard (delve, "creature card in
            # your graveyard", a count-operand over cards-in-GY — Enigma Drake /
            # Pteramander markers, a copy-of-a-card-in-GY recursion — Feldon, a
            # return-the-target-in-GY — Brilliance Unleashed) cares about graveyards.
            # Fired at _ir_scope(e.scope) (ADR-0027 scope-gate): a 'your graveyard'
            # reference stays you; a 'a graveyard' reference (no controller) becomes
            # any, which the scope-split serves as its own avenue. exile/blink already
            # fire above via the GY-hate hook (origin=graveyard→exile). The count
            # marker carries scope you, so the count-operand path stays you-scoped.
            if "in:graveyard" in e.zones and e.category not in ("exile", "blink"):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # An effect that scales with YOUR hand size (ZoneCardCount(Hand) — "draw
            # cards equal to the number of cards in your hand") cares about a big hand.
            if "in:hand" in e.zones and _ir_scope(e.scope) == "you":
                add("big_hand_matters", "you", "", e.raw)
            # token_maker only when the token goes to YOU — "destroy target
            # creature, its controller makes a Beast" (scope opp) is removal.
            if e.category == "make_token" and e.scope in ("you", "any"):
                subject = _token_kindred_subject(e.subject, vocab)
                if subject is not None:
                    add(signal_keys.TOKEN_MAKER, "you", subject, e.raw)
            # ADR-0027 β: token_copy_matters MIGRATED via a kept-mirror, NOT a
            # structural arm here. phase DOES structure the copy detail — `CopyTokenOf`
            # (394 cards) and `Populate` (27) effect types — but
            # project._copy_token_effect / _EFFECT_CATEGORY['populate'] both collapse
            # them to a plain make_token Effect (the cat=='make_token' arm above, the
            # vanilla-token lane). A structural CopyTokenOf/Populate arm was REJECTED:
            # the 80-card struct-only delta over the deleted reminder-stripped regex is
            # 100% OVER-FIRE — reminder-text SELF-copies (Embalm/Eternalize "(…create a
            # token that's a copy of it…)", Offspring "(…a 1/1 token copy of it…)",
            # Double-team — phase even mis-structures "conjure a duplicate into your
            # hand" as CopyTokenOf), none a genuine token-copy payoff. So the lane rides
            # _TOKEN_COPY_MATTERS_MIRROR (the EXACT deleted regex over
            # reminder-stripped kept_oracle) in the kept-detector pass below. CR 702.95.
            # reanimator (the ARCHETYPE) is a creature that actively returns
            # creatures from a graveyard to the battlefield — a commander, not a
            # one-shot spell (those stay enablers the avenue finds).
            if (
                e.category == "reanimate"
                and is_creature(card)
                and _reanimates_creature(e)
            ):
                add("reanimator", "you", "", e.raw)
            # Batch 2b — effect-category "doer" lanes (the CROSSWALK doer set).
            doer = _DOER_EFFECT_KEYS.get(e.category)
            if doer is not None:
                key, fixed_scope = doer
                add(key, fixed_scope or _ir_scope(e.scope), "", e.raw)
            # direct_damage is a doer (scope "you" = you control the source);
            # gate out incidental SELF-damage (painlands, talismans target you).
            if e.category == "damage" and e.scope != "you":
                add("direct_damage", "you", "", e.raw)
            # Batch 3 — tribal type_matters: a subtype anthem/count over YOUR
            # creatures (Goblin lord, "for each Goblin you control"). The token
            # TYPE a token_maker makes is token_maker, not type_matters.
            for sub in _kindred_subjects(amount_subject, vocab):
                add(signal_keys.TYPE_MATTERS, "you", sub, e.raw)
            if e.category != "make_token":
                for sub in _kindred_subjects(e.subject, vocab):
                    add(signal_keys.TYPE_MATTERS, "you", sub, e.raw)
            # Filter-PREDICATE lanes — an effect restricted to tapped / attacking
            # creatures, or permanents WITH a counter, is a payoff for that state
            # ("tapped creatures you control get…", "attacking creatures get +1/+0",
            # "creatures you control with a +1/+1 counter have trample"). _predicate
            # captures ~all phase filter properties as Filter.predicates; lanes read
            # color/PT/AnyOf/InZone + (here) Tapped/Attacking/Counters. Still unread:
            # EnchantedBy/EquippedBy (aura/equipment/voltron), WithKeyword
            # (keyword-tribal), Cmc (mana-value threshold).
            esub = e.subject
            if esub is not None:
                # Tapped / Attacking gate to YOUR permanents — "your tapped/attacking
                # creatures get …" is the payoff; "destroy target ATTACKING creature"
                # (controller any) is removal, not an aggro lane.
                if esub.controller == "you":
                    # Gate tapped to a creature (or untyped generic) subject — "return
                    # a tapped LAND you control" (Living Twister) is a mana-bounce, not
                    # a tapped-creatures aggro payoff.
                    if "Tapped" in esub.predicates and (
                        "Creature" in esub.card_types or not esub.card_types
                    ):
                        add("tapped_matters", "you", "", e.raw)
                    if "Attacking" in esub.predicates:
                        add("attack_matters", "you", "", e.raw)
                # "a creature with a +1/+1 counter" payoff isn't controller-bound.
                if esub.controller != "opp" and "Counters" in esub.predicates:
                    add("counters_matter", "you", "", e.raw)
            # counters_matter (ADR-0027) — the COUNT-FORM counter-HAVE payoff: an
            # effect whose VALUE counts "creatures you control WITH a +1/+1 counter"
            # ("draw a card for each creature you control with a +1/+1 counter on it" —
            # Inspiring Call, Armorcraft Judge, Hamza's cost reduction). The Counters
            # predicate rides amount.subject (the counted set), not e.subject, so the
            # e.subject read above misses it — a counters PAYOFF the lane wants.
            if (
                amount_subject is not None
                and amount_subject.controller != "opp"
                and "Counters" in amount_subject.predicates
            ):
                add("counters_matter", "you", "", e.raw)
            # ADR-0027 — the COUNT-FORM tapped payoff: an effect whose VALUE counts
            # your tapped creatures ("each opponent loses life equal to the number of
            # tapped creatures you control" — Throne of the God-Pharaoh; Crash the
            # Party / Dragonscale General / Harvest Season). The Tapped filter rides
            # amount.subject, not e.subject, so the predicate read above misses it.
            if (
                amount_subject is not None
                and amount_subject.controller == "you"
                and "Tapped" in amount_subject.predicates
            ):
                add("tapped_matters", "you", "", e.raw)
            # ADR-0027 — a FORETOLD-card reference: an effect (or its count operand)
            # acting on / scaling with foretold cards you own is a foretell PAYOFF
            # (Niko Defies Destiny — "2 life for each foretold card you own in
            # exile"). The Foretold predicate is the structural discriminator phase
            # keeps on the counted subject Filter; the foretell makers ride the
            # keyword, the granters ride the foretell marker (CR 702.143).
            for fsub in (e.subject, amount_subject):
                if fsub is not None and "Foretold" in fsub.predicates:
                    add("foretell_matters", "you", "", e.raw)
            # ── Batch E — effect-category lanes ──
            cat = e.category
            ftypes = _ftypes(e.subject)
            # variable_pt (ADR-0027 β) — a */* characteristic-defining P/T: a creature
            # whose power and/or toughness is "equal to <something>" (Nightmare = */*
            # equal to Swamps; Pack Rat; Serra Avatar = */* equal to your life;
            # Cultivator Colossus; Tarmogoyf; Lhurgoyf). phase carries the clause two
            # ways: an oracle-text CDA it left as `other` (Tarmogoyf —
            # supplement._CDA_PT → characteristic_pt) AND a fully-structured self-CDA
            # static it then dropped (Nightmare — re-surfaced as a characteristic_pt
            # marker by project._self_cda_marker, SIDECAR v10). Both land here as a
            # `characteristic_pt` Effect; this arm reads it (scope 'any', matching the
            # sweep). The */* tail phase can't structure as a self-CDA — the TOKEN-borne
            # */* ("This token's power and toughness are each equal to"), the "change
            # Halfdane's base power and toughness" self-set — rides the narrowed
            # _VARIABLE_PT_MIRROR below. CR 604.3.
            if cat == "characteristic_pt":
                add("variable_pt", "any", "", e.raw)
            # ADR-0027 — self_pump: a firebreathing mana-sink — an ACTIVATED pump or
            # +1/+1-counter placement on the SELF ("{R}: ~ gets +1/+0" — Shivan Dragon;
            # "{4}: Put a +1/+1 counter on ~" — Walking Ballista, Crystalline Crawler).
            # phase maps single-target pump to category 'pump_target' and leaves
            # subject=None when the pump targets the source; the activated-counter
            # branch (place_counter/p1p1/subjNone) is the same self shape. The ab.kind==
            # 'activated' gate is the regex's anchor (the activation prefix that
            # separates a mana-sink from a static anthem or a one-shot spell pump), and
            # it excludes manlands (animate/ramp categories) whose {cost}: prefix the
            # regex matched. subject is None (self) — a granter ("target creature
            # gets…", Pia Nalaar / Kjeldoran Elite Guard) carries a subject and is
            # counter_distribute / keyword_grant_target, NOT self_pump. Serve pairs
            # self_pump with _POWER_FLING_EXTRA (firebreathing → fling), hand-spec'd.
            # ADR-0027 β: a self-targeted p1p1 placement now carries the SelfRef
            # self-anchor marker (project @ SIDECAR v12) instead of subject=None, so
            # accept it here too — it IS the self shape this arm fires on (Walking
            # Ballista's "{4}: Put a +1/+1 counter on ~" is the canonical self_pump
            # mana-sink). Treating the marker as self keeps self_pump byte-identical to
            # the regex base. CR 122.1.
            if (
                ab.kind == "activated"
                and (e.subject is None or _is_self_counter_marker(e.subject))
                and (
                    cat == "pump_target"
                    or (cat == "place_counter" and e.counter_kind == "p1p1")
                )
            ):
                add("self_pump", "you", "", e.raw)
            # ADR-0027 β: pump_matters has NO structural arm here. Its lane is "positive
            # single-target combat-trick BUFF of another creature" ("target creature
            # gets +N/+N"), but the projection cannot express it: a target-creature
            # pump_target drops its value to amount==None (the +N/+N lives only in the
            # raw) and carries no temporal marker, so a +3/+3 combat trick (Giant
            # Growth) is the SAME pump_target/subj=Creature/amt=None shape as a -1/-1
            # DEBUFF (Festering Goblin) and a permanent buff — there is no sign or
            # single-target signal to read (debuff_matters reads factor<0 only on the
            # static-fold auras/anthems, NOT these amt=None target pumps). The one clean
            # positive-single-target structural form — a positive-factor pump on an
            # EnchantedBy/EquippedBy subject (auras/equipment) — is the SEPARATE
            # voltron/suit-up lane, so firing it here would be 100% scope-creep. So
            # pump_matters rides a byte-identical _IR_KEPT_DETECTORS mirror of the exact
            # deleted regex
            # (PUMP_MATTERS_REGEX); the regex IS the discriminator. See
            # _IR_KEPT_DETECTORS. CR 122.1b / 903.10a.
            if cat == "place_counter" and e.counter_kind in _COUNTER_KIND_KEYS:
                ck_key, ck_scope = _COUNTER_KIND_KEYS[e.counter_kind]
                add(ck_key, ck_scope, "", e.raw)
            # keyword_counter (ADR-0027 tranche2-C) — a place/remove of a CR-122.1b
            # keyword counter (a counter that grants a keyword ability via CR 613.1f).
            # phase tags the granted keyword in counter_kind on a place_counter /
            # remove_counter; membership in the closed _KEYWORD_COUNTER_KINDS set is the
            # discriminator vs the p1p1/m1m1/oil/shield/rad/ki stat-and-resource
            # counters. scope 'any' (these counter sources appear on either side),
            # matching the sweep. The choice/multi/quoted-grant tail (Wingfold Pteron's
            # "a flying OR a hexproof counter", Oozeavite's concatenated kinds,
            # Klement's quoted enter-with grant) — where phase drops counter_kind to
            # '' — is caught by the kept word mirror (signal_specs reuses the regex).
            if (
                cat in ("place_counter", "remove_counter")
                and e.counter_kind in _KEYWORD_COUNTER_KINDS
            ):
                add("keyword_counter", "any", "", e.raw)
            # counters_matter (ADR-0027 shape 1+2a) — a +1/+1 counter PLACEMENT is the
            # lane's core engine (Forgotten Ancient, Hardened Scales, every etb /
            # upkeep / combat / activated / spell +1/+1 source). place_counter with
            # counter_kind=='p1p1' is the discriminator phase already isolates from
            # loyalty / oil / shield / rad placements (those route to their own lanes
            # via _COUNTER_KIND_KEYS); the enters-with self-counter rides the projected
            # Moved→Battlefield replacement (kind p1p1) and the count-scaled placement
            # (amount.op in count/counters) lands here too. A counter_kind=='' blank
            # placement whose raw names "+1/+1 counter" is the enters-with / modal-
            # kicker form phase stripped the kind from (Endless One, Orzhov Advokist) —
            # gated on the raw so a NON-+1/+1 blank placement (a named-counter card)
            # stays out. CR 122.1 / 614.12.
            if cat == "place_counter" and (
                e.counter_kind == "p1p1"
                or (not e.counter_kind and "+1/+1 counter" in (e.raw or ""))
            ):
                add("counters_matter", "you", "", e.raw)
            # ADR-0027 β — self_counter_grow STRUCTURAL arm. A +1/+1 counter PLACEMENT a
            # creature puts on ITSELF to GROW (adapt CR 701.43 / monstrosity 701.13 /
            # renown 702.111 / Saga chapter "put N +1/+1 on ~" / "enters with / put a
            # +1/+1 counter on this creature" / empty-raw modal self-pump). phase emits
            # a
            # place_counter with target=={type:SelfRef} (or implies it for the keyworded
            # adapt/monstrosity/renown nodes), which the projection re-surfaces as the
            # SelfRef self-anchor marker (project._SELF_COUNTER_MARKER @ SIDECAR v12).
            # The
            # MARKER is the discriminator: a generic place_counter(p1p1, subject=None)
            # would conflate self-grow with "put a +1/+1 counter on TARGET / another
            # creature" (counter_distribute / a doubler's "on it"), the exact ambiguity
            # that DEFERRED this lane — the raw dropped the anchor on ~14 bodies. The
            # enters-with REPLACEMENT form is gated at projection time on the
            # replacement's valid_card so the OTHER-creature "each other creature enters
            # with …" grant (Master Biomancer, Giada) is NOT marked self. counter_kind
            # is
            # '' for the adapt/monstrosity/renown keyword nodes (their +1/+1 lives in
            # the
            # mechanic, not a counter_type), so the marker — not the kind — gates here.
            # NB: counters_matter (the broad lane above) still co-fires on the p1p1
            # placements; self_counter_grow is the NARROWER self-grow build-around
            # (is_widen_of counters_matter). A NARROWED _SELF_COUNTER_GROW_MIRROR below
            # recovers the TriggeringSource heroic self-grow (Sage of Hours / Fabled
            # Hero
            # — phase's "put a +1/+1 on it" with target=TriggeringSource, ambiguous at
            # the
            # corpus level so NOT marked) + the self-power-scaling commander tell. scope
            # 'you'. CR 122.1 / 614.12.
            if cat == "place_counter" and _is_self_counter_marker(e.subject):
                add("self_counter_grow", "you", "", e.raw)
            # counters_matter (ADR-0027 pass 2) — a "has/with a +1/+1 counter"
            # PAYOFF reference phase dropped to a restriction / draw / damage /
            # cost_reduction carrier, recovered as a counters_have_ref marker
            # (project._narrow_counter_refs): "creatures you control with a +1/+1
            # counter can't be blocked" (Herald), "if that creature has a +1/+1
            # counter" (Bring Low), "for each +1/+1 counter on creatures you
            # control" (Deepwood Denizen), "power greater than its base power"
            # (Kutzil/Baird, the counters-on-it idiom). The marker is the structural
            # boundary phase kept only in raw; a deck running these cares about the
            # counter (the "_matters = cares-about" rule). CR 122.1 / 122.6.
            if cat == "counters_have_ref":
                add("counters_matter", "you", "", e.raw)
            # counters_matter (ADR-0027 shape 4) — proliferate is definitionally a
            # counters mechanic (CR 701.27: add another counter of each kind already
            # there). A direct category→lane edge, zero discriminator needed.
            if cat == "proliferate":
                add("counters_matter", "you", "", e.raw)
            # counters_matter (ADR-0027) — a +1/+1 counter MOVE ("move +1/+1 counters
            # from … onto …" — Bioshift, Aetherborn Marauder, Nesting Grounds): the
            # counter_move category already opens the dedicated counter_move lane; a
            # p1p1 move is also a +1/+1 counters payoff (it relocates the engine's
            # counters), so it opens counters_matter too. The kind gate keeps a
            # non-+1/+1 move out (CR 122.1; minus_counters stays its own lane).
            if cat == "counter_move" and e.counter_kind == "p1p1":
                add("counters_matter", "you", "", e.raw)
            # counter_manipulation (ADR-0027) — +1/+1 or -1/-1 counter MOVE or
            # remove-as-EFFECT (The Ozolith, Power Conduit, Nesting Grounds move;
            # Carnifex Demon, Retribution of the Ancients, Festercreep remove). The
            # counter_kind gate ({p1p1,m1m1}) is the +1/+1-vs-charge/oil/loyalty
            # discriminator. The remove-as-COST tail ("Remove a +1/+1 counter from
            # ~:" — Walking Ballista, Fertilid, Quillspike, Devoted Druid) is an
            # Ability.cost the IR does not structure, so it stays on a kept word
            # mirror (_IR_KEPT_DETECTORS). CR 122.1 / 122.6.
            if (cat == "counter_move" and e.counter_kind in ("p1p1", "m1m1")) or (
                cat == "remove_counter" and e.counter_kind in ("p1p1", "m1m1")
            ):
                add("counter_manipulation", "you", "", e.raw)
            if cat == "counter_spell":
                add("counter_control", "you", "", e.raw)
            if cat == "fight":
                add("fight_matters", "you", "", e.raw)
            if cat == "ramp":
                add("ramp_matters", "you", "", e.raw)
                # ADR-0027 — group_mana: a non-controller mana RECIPIENT in the ramp
                # raw (phase emits scope='each' for ZERO ramp effects; the recipient
                # survives only in raw — _GROUP_MANA_RAW is the discriminator).
                if e.scope == "each" or _GROUP_MANA_RAW.search(e.raw or ""):
                    add("group_mana", "each", "", e.raw)
            if cat == "blink":
                add("blink_flicker", "you", "", e.raw)
            # clone_matters (creatures) + per-permanent-type copy lanes. The copied
            # type (from BecomeCopy's target, incl. an Or-composite like Spark Double's
            # Creature-or-Planeswalker) drives the hierarchy: a generic Permanent copy
            # feeds copy_permanent + every type lane. Spell-copy is a separate lane.
            if cat == "clone":
                for key in _clone_copy_lanes(e.subject, vocab):
                    add(key, "you", "", e.raw)
            # spell-copy (Twincast, Fork — "copy target spell") is a SEPARATE lane
            # from clone (which is creatures-on-the-battlefield only), per Dan.
            if cat == "spell_copy":
                add("spell_copy_matters", "you", "", e.raw)
            # evasion_denial: IgnoreLandwalkForBlocking (Great Wall) — block through
            # an opponent's landwalk evasion. Also fires off the ADR-0027 conferred
            # marker for the generic-landwalk umbrella (Staff of the Ages), which phase
            # routes to grant_keyword (project._narrow_conferred_keyword_refs).
            if cat == "evasion_denial":
                add("evasion_denial", "opponents", "", e.raw)
            # damage_reflect: the ADR-0027 conferred marker for a quoted/granted
            # reflection ability (Spiteful Sliver — 'Slivers you control have "when ~
            # is dealt damage, ~ deals that much damage to ..."'), which phase swallows
            # into grant_keyword. The on-card reflectors fire via the trigger-based
            # co-occurrence below (damage_received event + a damage effect).
            if cat == "damage_reflect":
                add("damage_reflect", "you", "", e.raw)
            # base_pt_set: a static that SETS base P/T (Lignify, Ovinize, Kenrith's
            # Transformation, animate-to-X/X). scope "any" (matches the regex —
            # spans neutralize-removal, self/land animate, switch).
            if cat == "base_pt_set":
                add("base_pt_set", "any", "", e.raw)
            # Batch 6 — grant_keyword lanes (the AddKeyword category, +3.8% parse).
            # Gated to avoid the naive +2197 flood: team lanes fire ONLY on a generic
            # creatures-you-control grant (no subtypes, no predicates — excludes
            # equipment/aura/self/single-target); the symmetric "all creatures have X"
            # grant is its own each-scope lane (it buffs opponents too).
            if cat == "grant_keyword":
                if _is_team_creature_grant(e.subject):
                    if e.counter_kind in _EVASION_GRANT_KW:
                        add("team_evasion_grant", "you", "", e.raw)
                    if e.counter_kind in _PROTECTION_GRANT_KW:
                        add("protection_grant", "you", "", e.raw)
                elif _is_all_creatures_grant(e.subject):
                    add("all_creatures_kw_grant", "any", "", e.raw)
                # team_buff (ADR-0027): the BROAD union anthem — a generic
                # "creatures you control have/gain <evergreen keyword>" grant
                # (Akroma's Memorial, Brave the Sands, Always Watching). phase emits
                # one grant_keyword Effect per keyword with the granted keyword in
                # counter_kind; the summary ck=='mass_grant' roll-up is IGNORED (a
                # duplicate). The over-fire boundary is _is_team_buff_grant: a tribal
                # ("Sliver creatures you control", subtypes), color ("Red creatures",
                # HasColor), attacking ("Attacking creatures", Attacking), or single-
                # target ("target creature you control gains", controller 'any')
                # grant fails the gate and stays out. It intentionally co-fires with
                # team_evasion_grant / protection_grant (the subsets) — the seen-set
                # dedups within a lane. (Kira's quoted-ability grant is a grant_keyword
                # carrier of a quoted ABILITY, ck not a bare keyword, correctly out.)
                if e.counter_kind in _TEAM_BUFF_GRANT_KW and _is_team_buff_grant(
                    e.subject
                ):
                    add("team_buff", "you", "", e.raw)
                # ADR-0027 — myriad_grant: a card that GRANTS myriad (CR 702.115) to a
                # creature/team (Blade of Selves, Legion Loyalty, Duke Ulder, Corporeal
                # Projection) or confers it via a copy-exception (Muddle's project.py
                # marker). phase stamps counter_kind='myriad' on the grant_keyword
                # effect — the discriminator that separates a GRANTER (no `myriad` in
                # the keyword array) from a card that prints myriad itself
                # (_IR_KEYWORD_MAP['myriad'], the makers).
                if e.counter_kind == "myriad":
                    add("myriad_grant", "you", "", e.raw)
                # ADR-0027 — exert_matters: a TEAM-VIGILANCE enabler grants vigilance
                # to your generic creature board (Heliod, Always Watching, Brave the
                # Sands). Team vigilance neutralizes exert's only downside ("won't
                # untap next turn"), so the deck wants exert creatures. counter_kind==
                # 'vigilance' is the structured discriminator; _is_generic_creature_
                # filter (controller you, no subtypes — but predicate-tolerant, so
                # Heliod's `Another` / Always Watching's `NonToken` board still counts)
                # excludes the subtype-scoped Golem/Sliver/Warrior grants (which carry
                # the subtype on this vigilance effect) and the single-target self-
                # grant. Two grant_keyword effects appear per card (one real
                # 'vigilance', one duplicate 'mass_grant'); this reads the 'vigilance'
                # one. The serve pool is the Scryfall `exert` keyword (hand-spec).
                if e.counter_kind == "vigilance" and _is_generic_creature_filter(
                    e.subject
                ):
                    add("exert_matters", "you", "", e.raw)
                # ADR-0027 — aura_equip_kw_grant: an evergreen keyword granted to YOUR
                # Aura/Equipment subgroup ("Auras you control have flying", "Equipment
                # you control have deathtouch" — Rashel). The subtyped subject Filter
                # (Aura/Equipment, controller you) is the discriminator vs a generic
                # team grant; the _AURA_EQUIP_GRANT_KW allowlist excludes equip{0}/crew
                # cost grants (phase emits those as a different effect, not an evergreen
                # grant_keyword). Broader-and-correct over the 1-card literal regex.
                if e.counter_kind in _AURA_EQUIP_GRANT_KW and _is_aura_equip_grant(
                    e.subject
                ):
                    add("aura_equip_kw_grant", "you", "", e.raw)
                # ADR-0027 — counter_grants_kw: a keyword granted to YOUR creatures that
                # HAVE A COUNTER ("creatures you control with a +1/+1 counter have
                # trample" — Bramblewood Paragon). The `Counters` predicate on the grant
                # subject (phase collapses counters={type:P1P1} to bare 'Counters'; in
                # practice every counter-conditioned keyword grant is the +1/+1 case) is
                # the discriminator vs an ordinary team keyword grant; controller=='you'
                # excludes opponent-creature grants. Broader than the closed-kw regex.
                if (
                    isinstance(e.subject, Filter)
                    and "Counters" in e.subject.predicates
                    and e.subject.controller == "you"
                ):
                    add("counter_grants_kw", "you", "", e.raw)
                # ADR-0027 — conditional_self_protection: a STATIC ability with a
                # condition (during your turn / unless tapped / as-long-as) granting a
                # PROTECTIVE keyword to ITSELF (subj None = SelfRef) — Dragonlord Ojutai
                # (not tapped → hexproof), Zurgo (during your turn → indestructible),
                # Kaito (during your turn + loyalty → hexproof). TWO discriminators: (1)
                # ab.condition is not None (the conditional gate vs an unconditional
                # anthem); (2) subj None (SelfRef) excludes team/aura/equipment grants.
                # The protective subset keeps a conditional combat buff (flying/trample)
                # out. Intrinsic hexproof rides the keyword array, never grant_keyword.
                if (
                    ab.kind == "static"
                    and ab.condition is not None
                    and e.subject is None
                    and e.counter_kind in _SELF_PROTECTION_GRANT_KW
                ):
                    add("conditional_self_protection", "you", "", e.raw)
            # ADR-0027 β — keyword_grant_target (formerly DEFERRED): a SPELL/ability
            # that grants a keyword to a SINGLE TARGET creature ("target creature gains
            # menace until end of turn" — Accelerate, Adamant Will, Madcap Skills's
            # spell siblings, the combat-trick / evasion enablers). phase collapsed
            # that to grant_keyword(subject=None) — indistinguishable from a self-grant
            # ("~ gains haste") and a subject-dropped team/anthem grant (subject=None
            # FLOODS +2236). The v14 projection re-surfaces the target as a dedicated
            # single_target_grant Effect whose subject is the resolved creature target +
            # a "SingleTarget" predicate (project._single_target_keyword_grant_markers —
            # the ParentTarget affected on a spell/ability GenericEffect is the
            # single-target tell; the predicate guards it out of every team/anthem
            # grant_keyword gate). Fire scope "you" — the deleted SWEEP detector hard-
            # fired scope "you" for ALL matches (its firing identity), so the migrated
            # arm matches it exactly. Distinct from TEAM grants (grant_keyword team
            # lanes / anthem keyword lanes) and aura/equipment grants (aura_equip_kw_
            # grant). +recall over the word-order regex: the "It gains X" idiom ("Untap
            # target creature. It gains reach" — Aim High; "Gain control of target
            # creature … It gains haste" — Act of Treason) and protection/ward grants
            # (Benevolent Bodyguard, Eldritch Immunity) the regex missed. CR 700.2.
            if cat == "single_target_grant":
                add("keyword_grant_target", "you", "", e.raw)
            # Batch 9 — cheat a CREATURE into play (a land into play is ramp).
            if cat == "cheat_play" and "Creature" in ftypes:
                add("cheat_into_play", "you", "", e.raw)
            # extra_land_drop (ADR-0027 tranche2-C) — "put a land card from your hand
            # onto the battlefield" (Burgeoning, Gretchen Titchwillow, Exploration-
            # adjacent put-into-play). phase emits cat=='cheat_play' with a Land-typed
            # YOUR subject (the InZone predicate confirms a hand/library origin, not a
            # generic permanent drop). The Land subject discriminates from a generic
            # cheat-into-play (Sneak Attack / reanimator put a creature) — those carry
            # 'Creature' and fire cheat_into_play above. A land TUTOR to hand
            # (cat=='tutor', to:hand) is a different shape and never reaches here. The
            # extra-land STATIC (Azusa/Exploration "play N additional lands") is a
            # separate cat=='extra_land' mechanic the deleted regex did NOT target, so
            # it's intentionally out of this faithful put-onto-battlefield migration.
            if (
                cat == "cheat_play"
                and isinstance(e.subject, Filter)
                and "Land" in e.subject.card_types
                and (
                    e.subject.controller == "you"
                    # controller='any' recovery: the "from hand OR graveyard"
                    # disjunction defeats phase's YOUR pin — recover via the deleted
                    # regex's YOUR-anchored raw, excluding the symmetric group forms.
                    or (
                        e.subject.controller == "any"
                        and _EXTRA_LAND_DROP_YOU_RAW.search(e.raw or "")
                        and not _EXTRA_LAND_DROP_GROUP_RAW.search(e.raw or "")
                    )
                )
            ):
                add("extra_land_drop", "you", "", e.raw)
            # extra_land_drop (ADR-0027 tranche2-C, dig-into-play) — "look at the top N,
            # put a land card onto the battlefield" (Elvish Rejuvenator, Cavalier of
            # Thorns, Animist's Awakening, Cartographer's Survey). phase types these
            # cat=='topdeck_select' with a Land subject and a to:battlefield zone — the
            # land lands in play, not in hand. The to:battlefield gate excludes the
            # dig-to-HAND form (Planar Genesis: zones=('to:hand',)), which is card
            # selection, not a land drop. This is the dig variant of the same put-into-
            # play engine the deleted regex's "you may put a land … onto the
            # battlefield" arm captured. CR 305.9.
            if (
                cat == "topdeck_select"
                and isinstance(e.subject, Filter)
                and "Land" in e.subject.card_types
                and "to:battlefield" in (e.zones or ())
            ):
                add("extra_land_drop", "you", "", e.raw)
            # Batch 2 (per-lane) — topdeck_stack: stack the TOP of YOUR library to
            # control draws (Brainstorm; graveyard-/hand-to-top recursion). Gate out
            # Bottom puts (cleanup) AND bounce-to-top removal (a targeted permanent,
            # controller "any") by requiring a top-ish position + YOUR moved cards.
            if (
                cat == "topdeck_stack"
                and e.counter_kind != "bottom"
                and _filter_controller(e.subject) == "you"
            ):
                add("topdeck_stack", "you", "", e.raw)
            if cat == "draw":
                # draw_for_each = a draw that SCALES with a board count, NOT a bare
                # "draw X cards" X-spell (Braingeyser). The scaling-count gate keeps
                # the X-spells (op='count', no subject, no "for each") out.
                if _is_scaling_count(e.amount, e.raw or ""):
                    add("draw_for_each", "you", "", e.raw)
                if e.scope == "each":
                    add("group_hug_draw", "each", "", e.raw)
                # target_player_draws (ADR-0027 tranche2-B-3) — a DIRECTED / forced
                # draw ("target player draws", "target opponent draws", "that player
                # draws") parses scope=='any' (the affected player carries no
                # controller); a self-cantrip and the symmetric "each player draws"
                # both parse scope=='you'/'each' (group_hug_draw takes 'each'). So
                # scope=='any' cleanly isolates the player-directed draw from the
                # self-cantrip — Ancestral Recall, Dimir Guildmage, Bloodgift Demon,
                # Howling Mine, Font of Mythos, Sphinx of Enlightenment (the latter's
                # 'target opponent' subset also carries subject controller='opp', still
                # scope='any'). CR 120.2 (draw is a player action).
                if e.scope == "any":
                    add("target_player_draws", "any", "", e.raw)
            if cat == "damage" and e.scope == "each":
                add("symmetric_damage_each", "each", "", e.raw)
            if cat == "discard" and e.scope == "opp":
                add("opponent_discard", "opponents", "", e.raw)
            # ADR-0027 lifeloss_matters — a structured life-LOSS effect. phase emits a
            # `lose_life` category distinct from gain_life / set_life, so the lane reads
            # it directly. scope splits the half: a drain ("each opponent / target
            # player / that player loses N life") is scope opp/any → opponents; a self
            # life-loss cost/payoff ("you lose N/X life") is scope you → you. lifeGAIN
            # and combat damage are sibling categories that never reach here. CR 119.3.
            if cat == "lose_life":
                add(
                    "lifeloss_matters",
                    "you" if e.scope == "you" else "opponents",
                    "",
                    e.raw,
                )
            # A `life_payment` marker (project._dropped_static_markers: a "Pay N life:"
            # cost phase misparsed — Arco-Flagellant — or dropped inside a conferred
            # quoted ability — Hibernation Sliver, Underworld Connections) is a self
            # life-as-resource engine, so it opens lifeloss_matters too. (It already
            # opens life_payment_insurance via _DOER_EFFECT_KEYS.) Not a Land card.
            if cat == "life_payment" and not card_is_land:
                add("lifeloss_matters", "you", "", e.raw)
            # An edict forces OPPONENTS / each player to sacrifice — gate on an
            # explicit opp/each scope (an unscoped sacrifice effect is ambiguous,
            # often a self-sac inside a larger effect, so don't call it an edict).
            # _ir_effect_is_edict additionally drops the 6 leaked-scope over-fires
            # (a self/you-sac phase mis-scoped opp from a sibling target-opponent
            # clause — Brink of Madness, Cabal Therapist, Helm of Obedience, Reno and
            # Rude, Thought Dissector, Treacherous Urge). A sac OUTLET is a COST
            # (handled per-ability below).
            if (
                cat == "sacrifice"
                and e.scope in ("opp", "each")
                and _ir_effect_is_edict(e)
            ):
                add("edict_matters", _ir_scope(e.scope), "", e.raw)
            # ADR-0027 sacrifice_matters — a YOU-sacrifice effect (the dominant gap):
            # "you may sacrifice a creature/artifact", "sacrifice another creature",
            # the additional-cost-to-cast sac marker (Altar's Reap, Fling). phase
            # emits scope "any" even for a clearly-you sacrifice, so fire on scope NOT
            # opp/each (the edict split above takes those). Three discriminators keep
            # the over-fire out: (1) a real subject Filter that is NOT land-ONLY — a
            # subjectless SelfRef "sacrifice THIS" is a downside payoff, not a
            # sac-theme outlet, and a land-ONLY subject is the land_sacrifice lane
            # (Excavating Anurid, Serendib Djinn); a mixed "creature or land" subject
            # (Reprocess, Harvester Troll) stays — it IS a creature/artifact sac
            # outlet. (2) the raw must not name a FORCED opponent/each-player sacrifice
            # phase mis-scoped to "any" (Malfegor, Barter in Blood — phase dropped the
            # opponent controller; the raw still reads "<player> sacrifices"). CR
            # 701.16.
            # A sacrifice whose SUBJECT Filter is controller "you" is a you-sac even
            # when the effect scope leaked opp from a downstream target-player clause
            # (Cabal Therapist's "you may sacrifice a creature … then target player
            # reveals" — the supplement's possessive scope pass stamps the ability
            # opp). The subject controller is the truth for who sacrifices.
            _sac_subject_you = (
                isinstance(e.subject, Filter) and e.subject.controller == "you"
            )
            if (
                cat == "sacrifice"
                and (e.scope not in ("opp", "each") or _sac_subject_you)
                and e.subject is not None
                and e.subject.card_types != ("Land",)
                and not _SAC_EDICT_RAW.search(e.raw or "")
            ):
                add("sacrifice_matters", "you", "", e.raw)
            # Subject-less / modal fallback: phase parsed a sacrifice or a `choose`
            # whose typed subject it dropped ("sacrifice any number of creatures" —
            # Dracoplasm; "sacrifice it unless you sacrifice a creature" pay-or-die;
            # "you may sacrifice an artifact or discard a card" → choose). The raw
            # naming a non-land non-self sac IS the discriminator (a bare "sacrifice
            # it/this/~" carries no type and never matches); the edict guard keeps a
            # forced opponent sac out.
            if (
                cat in ("sacrifice", "choose")
                and _SAC_OUTLET_RAW.search(e.raw or "")
                and not _SAC_EDICT_RAW.search(e.raw or "")
            ):
                add("sacrifice_matters", "you", "", e.raw)
            if cat == "gain_control":
                # donate_matters (ADR-0027): you GIVE a permanent you control to
                # another player. phase drops the recipient (scope='any'), so read
                # the raw for the recipient-is-another-player phrasing.
                is_donate = bool(_DONATE_RAW.search(e.raw or ""))
                if is_donate:
                    add("donate_matters", "you", "", e.raw)
                if "Land" in ftypes or (
                    e.subject is None and _LAND_EXCHANGE_RAW.search(e.raw or "")
                ):
                    add("land_exchange", "you", "", e.raw)
                # gain_control = THEFT (you take an opponent's/any permanent). EXCLUDE
                # (ADR-0027): a DONATE (you GIVE your own permanent away — Donate,
                # Bazaar Trader, Conjured Currency); and a RETURN-CONTROL reset ("each
                # player gains control of permanents they own" — Brooding Saurian),
                # which the Owned-subject tell marks. The old blanket _DOER_EFFECT_KEYS
                # entry fired gain_control on those give-away/reset directions; this
                # gated arm replaces it.
                returns_own = (
                    isinstance(e.subject, Filter) and "Owned" in e.subject.predicates
                )
                gives_away = bool(_GIVE_CONTROL_AWAY.search(e.raw or ""))
                if not is_donate and not returns_own and not gives_away:
                    add("gain_control", "you", "", e.raw)
            if cat == "destroy":
                if "Land" in ftypes:
                    add("land_destruction", "you", "", e.raw)
                if "Creature" in ftypes and ab.kind in ("activated", "triggered"):
                    add("kill_engine", "you", "", e.raw)
                # removal_matters: a SINGLE-TARGET destroy whose subject is a
                # permanent TYPE, or (ADR-0027) a subtype-ONLY subject that names a
                # permanent — "destroy target Wall/Equipment/Aura" (card_types=(),
                # subtypes set) is removal of a creature / artifact / enchantment.
                # Land-subtype-only destroys ("destroy target Island") route to
                # land_destruction above and are excluded here (CR 305.6 — the lane's
                # discriminator). The MASS form ("destroy ALL creatures" — DestroyAll,
                # counter_kind=="all") is a BOARD WIPE, not single-target removal (CR
                # 115.10 vs 115.1) — it is a distinct build axis and the regex lane
                # (anchored on "destroy target …") excludes it, so the IR must too.
                if e.counter_kind != "all" and (
                    (ftypes & _PERMANENT_TYPES)
                    or _is_permanent_subtype_destroy(e.subject)
                ):
                    add("removal_matters", "you", "", e.raw)
                # destroy_legendary (ADR-0027): a destroy whose subject is restricted
                # to legendary permanents (Bounty Agent, Tsabo Tavoc, Hero's Demise;
                # the mass form "destroy each legendary creature" — Invasion of Fiora —
                # rides counter_kind=="all" but carries the same predicate). The exact
                # HasSupertype:Legendary predicate IS the discriminator — a generic
                # "destroy target creature" (Hero's Downfall, predicates=()) lacks it,
                # and "destroy target NONlegendary creature" (Cast Down, One Ring)
                # carries NotSupertype:Legendary, the OPPOSITE, so neither fires. Scope
                # 'any' (the regex forces it). is_widen_of removal_matters is preserved
                # — it stays a destroy effect, which opened removal_matters above where
                # it qualifies. (CR 205.4a.) See ADR-0027.
                if (
                    isinstance(e.subject, Filter)
                    and _LEGENDARY_DESTROY_PRED in e.subject.predicates
                ):
                    add("destroy_legendary", "any", "", e.raw)
            # mass_bounce (ADR-0027): a BOARD-WIDE bounce — counter_kind=="all" (the
            # mass discriminator, the same convention as the mass-untap arm above) on
            # a generic Creature/Permanent subject (Evacuation, River's Rebuke,
            # Devastation Tide). counter_kind=="" is a single-target bounce (Cyclonic
            # Rift's base mode, "return target creature") — correctly excluded. A
            # graveyard-recursion subject ("return all creature cards from graveyards"
            # — Garna, Empty the Catacombs, Wrenn and Seven) carries an InZone/Owned
            # predicate and is excluded by _is_mass_bounce_subject (that is recursion,
            # CR 404, not a board bounce). Scope 'any' (the sweep convention — symmetric
            # vs one-sided follows the subject; Evacuation is symmetric). KEPT RESIDUAL:
            # Cyclonic Rift's OVERLOAD 'each' mode is a phase modal-alt-cost parse drop;
            # artifact/enchantment-only sweeps (Rebuild, Reduce to Dreams) are scoped
            # out (the lane's subject is Creature/Permanent, CR 115.10). See ADR-0027.
            if (
                cat == "bounce"
                and e.counter_kind == "all"
                and _is_mass_bounce_subject(e.subject)
                and not any("graveyard" in z or "library" in z for z in e.zones)
            ):
                add("mass_bounce", "any", "", e.raw)
            # bounce_tempo (ADR-0027): a battlefield→hand bounce as tempo (Boomerang,
            # Unsummon, Man-o'-War, Cyclonic Rift). TWO discriminators turn the raw
            # bounce category into the tempo lane: (1) EXCLUDE bounces touching a
            # graveyard zone — those are GY→hand recursion already routed to
            # graveyard_matters above (CR 404); (2) EXCLUDE subject.controller=='you'
            # (self-bounce for value/blink — Aviary Mechanic, karoo lands — is NOT
            # tempo). The breadth over the narrow regex (mass + flexible bounce) is
            # legitimate bounce signal, not over-fire. A mass bounce can co-fire its own
            # each-scope mass_bounce lane above — both are real bounce signals.
            if (
                cat == "bounce"
                and not any("graveyard" in z for z in e.zones)
                and not (
                    isinstance(e.subject, Filter) and e.subject.controller == "you"
                )
            ):
                add("bounce_tempo", "you", "", e.raw)
            # removal_matters (ADR-0027): a SINGLE-TARGET DAMAGE effect to a creature /
            # permanent (cat=='damage', subject a creature or other permanent type, or
            # a permanent subtype) is removal — Flame Slash, Crossbow Infantry, Nin
            # (op=count), Surgehacker (op=multiply), Hobbit's Sting (X). The regex
            # routed this only to direct_damage; the lane was never wired to damage.
            # Discriminators vs over-fire: (1) the damage SUBJECT must be a creature /
            # permanent (its card_types intersect _PERMANENT_TYPES OR it has a
            # permanent subtype) — a player/PW-only burn ("deal 3 to any target",
            # subject=None or {Player}/{Planeswalker}) stays direct_damage; (2) the MASS
            # form ("deals N damage to EACH creature" — DamageAll, counter_kind=="all")
            # is a board wipe, NOT the single-target burn the lane wants (CR 115.10 vs
            # 115.1), and the regex lane (anchored on "to target creature/permanent")
            # excludes it, so the IR must too.
            if (
                cat == "damage"
                and e.counter_kind != "all"
                and (
                    (ftypes & _PERMANENT_TYPES)
                    or _is_permanent_subtype_destroy(e.subject)
                )
            ):
                add("removal_matters", "you", "", e.raw)
            # control_exchange (ADR-0027): exile a permanent/creature YOU OWN, then
            # return it to the battlefield (under your control) — Meneldor, The
            # Neutrinos, Aminatou's -1. This is the INVERSE of the exile_removal Owned-
            # exclusion below: the `Owned` predicate ("you own", not "you control") is
            # the control-exchange tell (donate a dud, keep their bomb, reclaim your
            # own — Puca's Mischief loop). Requiring the to:battlefield return in the
            # SAME ability keeps a bare exile-you-own from leaking. Distinct from a
            # plain blink (which says "you control" → no Owned predicate) and from
            # gain_control theft (a sibling lane).
            if (
                cat == "exile"
                and isinstance(e.subject, Filter)
                and "Owned" in e.subject.predicates
                and any("to:battlefield" in z for sib in ab.effects for z in sib.zones)
            ):
                add("control_exchange", "you", "", e.raw)
            # exile_removal = genuine targeted EXILE of a permanent (CR 406). EXCLUDE
            # (ADR-0027): (1) BLINK — exiling YOUR OWN permanent to flicker it ("Exile
            # another target creature you own. Return it" — Charming Prince, Aminatou,
            # Angel of Condemnation's first mode); the `Owned` predicate / controller-
            # you subject is the tell, and the return makes it ETB-value, not removal.
            # (2) GY-HATE — exiling a card FROM a graveyard (zones in:/from: graveyard),
            # which is opponent_exile_matters, not permanent removal. Keep the genuine
            # opponent/any-target permanent exile.
            if (
                cat == "exile"
                and ftypes & _PERMANENT_TYPES
                and not (
                    isinstance(e.subject, Filter)
                    and (
                        "Owned" in e.subject.predicates or e.subject.controller == "you"
                    )
                )
                and not any("graveyard" in z for z in e.zones)
            ):
                add("exile_removal", "you", "", e.raw)
            # mass_removal (ADR-0027): a BOARD WIPE (CR 115.10) — three arms, all
            # keyed on the counter_kind=='all' "each/all" mass discriminator phase
            # isolates from single-target removal. (1) DESTROY/EXILE sweep over a
            # battlefield permanent type (Wrath, Day of Judgment, Merciless Eviction's
            # per-mode exile/all, Bane of Progress, In Garruk's Wake, Plague Wind) —
            # gated to _MASS_REMOVAL_TYPES so "destroy all LANDS" (Armageddon →
            # land_destruction) and an exile-all over a graveyard Card/None subject
            # (delve / GY-hate) stay out. (2) DAMAGE sweep over a Creature/Permanent
            # subject (Pyroclasm, Blasphemous Act) — a player-subject "deal N to each
            # opponent" group burn carries no creature subject and is excluded. (3)
            # the -X/-X DEBUFF sweep is the pump arm below (amount dropped to None).
            if (
                cat in ("destroy", "exile")
                and e.counter_kind == "all"
                and (ftypes & _MASS_REMOVAL_TYPES)
                # GY-hate / mass reanimation exclusion (mirrors exile_removal): an
                # "exile all <type> cards from graveyards" (Living Death, Living End,
                # Gerrard, Scrap Mastery) touches a graveyard zone — that is GY
                # recursion / hate, NOT a battlefield board wipe (CR 406), excluded.
                and not any("graveyard" in z for z in e.zones)
            ):
                add("mass_removal", "you", "", e.raw)
            if (
                cat == "damage"
                and e.counter_kind == "all"
                and (ftypes & {"Creature", "Permanent"})
            ):
                add("mass_removal", "you", "", e.raw)
            # mass_removal -X/-X DEBUFF sweep (Languish, Toxic Deluge): phase emits a
            # pump over a Creature subject but DROPS the negative amount (amount=None),
            # so the "all creatures get -" raw is the discriminator vs the positive
            # all-creatures ANTHEM (anthem_static, 1000+ cards). Gate on a creature
            # subject + the negative-pump raw.
            if (
                cat == "pump"
                and "Creature" in ftypes
                and _MASS_DEBUFF_RAW.search(e.raw or "")
            ):
                add("mass_removal", "you", "", e.raw)
            # opponent_exile_matters (ADR-0027): GRAVEYARD HATE, not permanent removal —
            # fires from the _IR_KEPT_DETECTORS word mirror (the deleted sweep regex)
            # because phase scatters its forms across categories phase doesn't unify
            # (graveyard-zone exile → cat='exile' subject=None; Leyline's replacement →
            # cat='cheat_play'; Umbris's "cards opponents own in exile" → cat='pump').
            # The old permanent-exile arm here mis-fired the lane on Path-to-Exile-style
            # removal (scope='opp', permanent subject) and is removed.
            # Batch 5 — color_hoser: destroy/exile/counter keyed on a SPECIFIC color
            # ("destroy target blue permanent", "counter target red spell") — the
            # Painter toolbox's payoff. Gate on a removal EFFECT context (not any color
            # mention), so a color-tribal anthem ("red creatures get +1/+0") stays out.
            # bounce is excluded: it also covers graveyard→hand recursion of YOUR own
            # colored cards (Revive, Xiahou Dun), which is not hosing.
            if cat in ("destroy", "exile", "counter_spell") and _hoses_a_color(
                e.subject
            ):
                add("color_hoser", "you", "", e.raw)
            if cat == "tap" and e.scope == "opp":
                add("tap_down", "opponents", "", e.raw)
            # ADR-0027 — tapper_engine: a repeatable TAPPER (Icy Manipulator,
            # Opposition, Master Decoy) — a tap Effect with a real TARGET/all/each
            # subject (a Filter). Every tap effect carrying a subject is a target tap;
            # tap-AS-COST lives in Ability.cost=='tap' and emits no tap Effect, so
            # `e.subject is not None` excludes pure-cost taps and self-untaps without
            # leaking. Scope 'any' (the lane wants the broad any-controller target tap
            # — do NOT reuse the tap_down opp-gate, which would massively under-fire
            # here). tap_down can co-fire on the same card (different lane/scope) — OK.
            if cat == "tap" and e.subject is not None:
                add("tapper_engine", "any", "", e.raw)
            # ADR-0027 — tapper_engine "doesn't untap" branch: a Frost-Titan / Kismet-
            # style can't-untap static projects to a restriction whose untap text
            # survives only in raw (no mode token on the Effect), so a raw /untap/
            # substring on a restriction opens the lane. Raw-gated so a generic stax
            # restriction (can't attack / can't cast) stays out.
            if cat == "restriction" and re.search(r"untap", e.raw or "", re.IGNORECASE):
                add("tapper_engine", "any", "", e.raw)
            # untap_engine (ADR-0027 β): a DELIBERATE untap engine — a mass untap
            # (counter_kind=='all', the structured "untap all creatures/permanents" —
            # Seedborn Muse, Early Harvest, Sands of Time, Godo), a raw "untap target/
            # all/each/two/up to <permanent>" (Kiora, Murkfiend Liege), OR a multi/X-
            # target untap whose subject is a real permanent TYPE you can control
            # (Candelabra "Untap X target lands", Synod Artificer "Untap X target
            # noncreature artifacts", Reality Spasm "Untap X target permanents" — phase
            # structures the effect but drops the "X target" engine raw). Gated against
            # three over-fires: (1) an opponent-untap (subject controller=='opp' OR a
            # "you don't control" raw — Provoke/Spinal Embrace untap an ENEMY permanent
            # for combat/theft, anti-synergy with an untap engine, NOT one); (2) a
            # PROVOKE combat keyword (a `force_block` sibling effect in the same ability
            # — provoke's "untap target creature defending player controls" rides the
            # de-reminded raw, but it untaps the blocker, not your board); (3) the
            # single-permanent "untap enchanted/equipped <thing>" RIDER (Crab Umbra,
            # Pemmin's Aura — the incidental rider the lane excludes). The deleted regex
            # over-fired on (1) (it ran reminder-stripped but couldn't read "you don't
            # control"); the structural arm + the kept mirror both correctly drop it.
            _opp_untap = (
                isinstance(e.subject, Filter) and e.subject.controller == "opp"
            ) or _UNTAP_ENGINE_OPP_VETO.search(e.raw or "")
            _is_provoke = any(s.category == "force_block" for s in ab.effects)
            if (
                cat == "untap"
                and not _opp_untap
                and not _is_provoke
                and (
                    e.counter_kind == "all"
                    or _UNTAP_ENGINE_RAW.search(e.raw or "")
                    or (
                        isinstance(e.subject, Filter)
                        and bool(e.subject.card_types)
                        and e.subject.controller != "opp"
                        and not _UNTAP_ATTACH_VETO.search(e.raw or "")
                    )
                )
            ):
                add("untap_engine", "you", "", e.raw)
            # anthem_static (ADR-0027): a STATIC +N/+N over a creature GROUP — the
            # team buff you build go-wide to ride (CR 611, continuous). Two structural
            # discriminators vs over-fire: (1) ab.kind=='static' excludes the one-shot
            # / until-end-of-turn pump (Charge, Overcome — k='spell'); a temporary pump
            # is never a static ability. (2) factor>=0 AND scope!='opp' excludes the
            # DEBUFF half of a split anthem (Elesh Norn's "creatures opponents control
            # get -2/-2" projects as a SEPARATE pump, factor=-2 scope='opp'). factor>=0
            # (NOT >0) KEEPS the toughness-only anthems +0/+N (Veteran Armorer, Castle)
            # whose Quantity.factor encodes the POWER bonus (0) only. The subject must
            # be a creature GROUP: 'Creature' card_type AND (controller=='you' OR
            # 'Another' OR a subtype) — a single-target pump (controller 'any', no
            # Another/subtype) fails the group test and stays out. (widen of team_buff.)
            if (
                ab.kind == "static"
                and e.category == "pump"
                and e.amount is not None
                and e.amount.factor >= 0
                and e.scope != "opp"
                and isinstance(e.subject, Filter)
                and "Creature" in e.subject.card_types
                and (
                    e.subject.controller == "you"
                    or "Another" in e.subject.predicates
                    or bool(e.subject.subtypes)
                )
            ):
                add("anthem_static", "you", "", e.raw)
            if cat == "pump" and e.amount is not None:
                # scaling_pump = a +X/+X that SCALES with a board count ("for each
                # creature", "for each +1/+1 counter", domain/devotion/party), NOT a
                # bare "gets +X/+X" X-pump (firebreathing X). _is_scaling_count keeps
                # the bare-X pumps out and admits the NAMED scale ops (counters/domain/
                # devotion/party) phase routes off the generic `count`.
                if _is_scaling_count(e.amount, e.raw or ""):
                    add("scaling_pump", "you", "", e.raw)
                # counters_matter (ADR-0027 shape 6) — the counter-COUNT payoff reaches
                # the IR as a PUMP whose value counts counters on a permanent ("Humans
                # you control get +1/+1 for each counter on ~" — Kyler; High Sentinels).
                # Gated to the count-bearing ops + a "counter" raw (op alone is too
                # broad — a count counts anything; a fixed pump mentioning "counter" in
                # an unrelated clause must not leak).
                if (
                    e.amount.op in ("count", "multiply", "counters")
                    and "counter" in (e.raw or "").lower()
                ):
                    add("counters_matter", "you", "", e.raw)
                # ADR-0027 — count_anthem: a TEAM anthem whose +N/+N SCALES with a
                # board count ("Creatures you control get +0/+1 for each Gate you
                # control" — Hold the Gates; Commander's Insignia; Boon of the Spirit
                # Realm). The team-subject discriminator (a generic creature Filter you
                # control) separates this from single-target firebreathing scaling_pump
                # (subject single/None) and from Coat-of-Arms-style "EACH creature
                # gets" (subject controller='any', a symmetric global). _is_scaling_
                # count keeps bare "gets +X/+X" X-pumps out — only a real board-count
                # scale qualifies. count_anthem is the team-subject subset of the
                # scaling_pump superset; a card may legitimately open both (add()
                # dedups). The serve pool is hand-registered in signal_specs.py.
                if (
                    e.amount.op in ("count", "multiply", "counters")
                    and _is_scaling_count(e.amount, e.raw or "")
                    and _is_generic_creature_filter(e.subject)
                ):
                    add("count_anthem", "you", "", e.raw)
            # power_double (ADR-0027): a P/T-DOUBLING effect. phase does NOT set a
            # multiply quantity for power doubling (Unleash Fury / Mr. Orfeo /
            # Unnatural Growth all carry amount=None), so the raw word-mirror "double
            # … power" / "power … doubled" IS the discriminator — keyed off the
            # pump/pump_target category, NOT the over-firing Scryfall `Double` keyword
            # (which mostly doubles DAMAGE / counters / tokens). Single-target doublers
            # (Unleash Fury) land in pump_target; mass doublers (Unnatural Growth,
            # Zopandrel) land in pump with a you-controller subject. NB: outside the
            # `e.amount is not None` block above — power-doublers have no amount.
            # Scope 'you' (the doubling payoff is your own beater). See ADR-0027.
            if cat in ("pump", "pump_target") and _POWER_DOUBLE_RAW.search(e.raw or ""):
                add("power_double", "you", "", e.raw)
            # Batch 12 — typed_anthem_multi: a pump over creatures of MULTIPLE named
            # types ("each creature that's an Assassin, Mercenary, or Pirate gets ...")
            # — an AnyOf-of-subtypes on a creature filter (single-type is type_matters).
            # ADR-0027: phase parses some disjunctions as a FLAT subtypes tuple instead
            # of an AnyOf node (Brenard Food/Golem, Howlpack Resurgence Wolf/Werewolf,
            # Auriok Steelshaper Soldier/Knight), so also fire when the Filter names 2+
            # subtypes — a structurally clean discriminator (single-subtype anthem stays
            # type_matters at len==1). The pump-only gate excludes Paladin Danse (a
            # one-shot keyword GRANT via grant_keyword, not a +X/+X anthem).
            if (
                cat == "pump"
                and "Creature" in ftypes
                and isinstance(e.subject, Filter)
                and (
                    any(p.startswith("AnyOf:") for p in e.subject.predicates)
                    or len(e.subject.subtypes) >= 2
                )
            ):
                add("typed_anthem_multi", "you", "", e.raw)
            # CAUSE 1 (ADR-0027): phase dropped the typed subject (subject=None) — the
            # multi-type disjunction survives only in the pump raw (Kaheera, Immerwolf,
            # Lovisa, Sporecrown). Recover from "that's a X … or a Y" (2+ subtypes).
            if (
                cat == "pump"
                and e.subject is None
                and _TYPED_ANTHEM_MULTI_RAW.search(e.raw or "")
            ):
                add("typed_anthem_multi", "you", "", e.raw)
            if amount_subject is not None and "Land" in _ftypes(amount_subject):
                add("lands_matter", "you", "", e.raw)
            # Token-subtype synergy (clue/food/treasure/blood). The maker opens the
            # lane via a make_token subject carrying the token subtype; the SACRIFICE
            # PAYOFF (Wedding Security "sacrifice a Blood token", artifact-token
            # sac-fuel) opens it via a `sacrifice` Effect whose subject Filter carries
            # the same subtype — both are the lane's stated intent ("makers plus
            # sacrifice payoffs"). One general scan over both maker + sacrifice
            # subjects (the trigger-side "whenever you sacrifice a <Subtype> token"
            # payoff is read in the trigger loop below).
            if cat in ("make_token", "sacrifice"):
                for st in _fsubs_lower(e.subject):
                    if st in _TOKEN_SUBTYPE_KEYS:
                        tk, ts = _TOKEN_SUBTYPE_KEYS[st]
                        add(tk, ts, "", e.raw)
            # ADR-0027 token_subtype_ref marker (project._dropped_static_markers): a
            # cares-about reference to a named token subtype ("Foods you control", "was
            # a Treasure") — the subtype rides counter_kind → its food/treasure/clue/
            # blood lane (the "_matters = cares-about" payoff side).
            if cat == "token_subtype_ref" and e.counter_kind in _TOKEN_SUBTYPE_KEYS:
                tk, ts = _TOKEN_SUBTYPE_KEYS[e.counter_kind]
                add(tk, ts, "", e.raw)
            # An artifact-token-subtype cares-about ref ("Treasures you control", "Clues
            # you control") also feeds artifacts_matter (CR 205.3g — those tokens are
            # artifacts; Confront the Unknown, Academy Manufactor payoffs).
            if (
                cat == "token_subtype_ref"
                and e.counter_kind in _ARTIFACT_TOKEN_SUBTYPES
            ):
                add("artifacts_matter", "you", "", e.raw)
            # Modal keyword mechanics — own CR-accurate category fanning to EVERY mode
            # it touches, instead of being flattened into a single facet. The keyword
            # maps already fire the primary lane (amass→tokens_matter,
            # fabricate→counters_matter, devour→sacrifice_matters); these add the IR
            # side (→ BOTH) plus the previously-dropped mode.
            if cat == "amass":  # CR 701.47 — grow an Army (+1/+1) or make an Army token
                add("tokens_matter", "you", "", e.raw)
                add("counters_matter", "any", "", e.raw)
            if cat == "fabricate":  # CR 702.123 — Servo tokens OR +1/+1 counters
                add("tokens_matter", "you", "", e.raw)
                add("counters_matter", "any", "", e.raw)
            if cat == "devour":  # CR 702.82 — sacrifice creatures, enter with counters
                add("devour_matters", "you", "", e.raw)
                add("sacrifice_matters", "you", "", e.raw)
                add("counters_matter", "any", "", e.raw)
            if cat == "reanimate" and "Creature" in ftypes:
                add("creature_recursion", "you", "", e.raw)
            if cat == "animate" and "Artifact" in ftypes:
                add("animate_artifact", "you", "", e.raw)
            # Stax: a static restriction hobbling OPPONENTS (stax_taxes) or
            # everyone symmetrically (symmetric_stax).
            if cat == "restriction":
                if e.scope == "opp":
                    add("stax_taxes", "opponents", "", e.raw)
                elif e.scope == "each":
                    add("symmetric_stax", "each", "", e.raw)
                # ADR-0027 tranche2-B-3: timing_control DEFERRED — phase drops the
                # Teferi-style "cast spells only any time they could cast a sorcery"
                # cast-timing static entirely (it keeps only the flash-grant), a genuine
                # 2-card recall gap, not 100% over-fire. Not migrated; the
                # SWEEP_DETECTORS row stays as the producer.
            # Batch 13 — combat-forcing statics (split out of stax): force the table
            # to attack (Fumiko), force a path by denying blocks, or lure blockers (a
            # creature that must be blocked). All scope "you" (you wield the engine).
            # A force/can't-block static that hobbles OPPONENTS is ALSO a pillowfort
            # tax, so it still feeds stax (the split must not regress stax coverage).
            # forced_attack is scope "any" to match the sweep detector that catches
            # the same "attacks each combat if able" compulsion (a symmetric/table
            # force, not a you-only payoff).
            if cat == "force_attack":
                add("forced_attack", "any", "", e.raw)
                # Goad-style single-target political force (CR 701.38): "target
                # creature … attacks … if able" wants goad payoffs, so it also opens
                # the goad lane. The self/team "each combat" force never names a
                # target, so it stays forced_attack-only.
                if _GOAD_STYLE_FORCE.search(e.raw or ""):
                    add("goad_matters", "opponents", "", e.raw)
            if cat == "cant_block":
                add("cant_block_grant", "you", "", e.raw)
            if cat == "lure":
                add("lure_matters", "you", "", e.raw)
            if cat in ("force_attack", "cant_block"):
                if e.scope == "opp":
                    add("stax_taxes", "opponents", "", e.raw)
                elif e.scope == "each":
                    add("symmetric_stax", "each", "", e.raw)
            # Batch 17 — DoubleTriggers static (Yarok, Panharmonicon): the
            # trigger-doubling engine ("a triggered ability triggers an extra time").
            if cat == "trigger_doubling":
                add("trigger_doubling", "you", "", e.raw)
                # ADR-0027 — venture_matters DUNGEON-DOUBLING payoff: the trigger
                # doubler is scoped to room/dungeon abilities (Hama Pashar, Dungeon
                # Delver), so it's also a dungeon-completion payoff.
                if _DUNGEON_RAW.search(e.raw or ""):
                    add("venture_matters", "you", "", e.raw)
            # Batch 6 (flash_grant) — CastWithKeyword{Flash}: a flash ENABLER (cast
            # spells as though they had flash — Teferi, Yeva, Alchemist's Refuge).
            # ADR-0027 (q2-D3): flash_matters rides the SAME node — the GRANT half of
            # the lane is exactly this cast_with_keyword{flash} static (Leyline of
            # Anticipation, Vivien). The opponent-turn cast payoff + the activated
            # flash-grant (empty counter_kind) are recovered by the kept _IR_KEPT
            # mirror. CR 702.8.
            if cat == "cast_with_keyword" and e.counter_kind == "flash":
                add("flash_grant", "you", "", e.raw)
                add("flash_matters", "you", "", e.raw)
            # ADR-0027 — convoke_matters GRANTER: "<type> spells you cast have convoke"
            # (CR 702.51, Fallaji Wayfarer, Chief Engineer) carries counter_kind=
            # 'convoke' on the cast_with_keyword effect — a pure structured read. The
            # activated "next spell … has convoke" granter (Wand of the Worldsoul)
            # lands in grant_spell_ability with the keyword only in raw.
            if cat == "cast_with_keyword" and e.counter_kind == "convoke":
                add("convoke_matters", "you", "", e.raw)
            if cat == "grant_spell_ability" and _CONVOKE_RAW.search(e.raw or ""):
                add("convoke_matters", "you", "", e.raw)
            # spell_keyword_grant (ADR-0027 tranche2-B-3) — the UMBRELLA lane: a card
            # that grants ANY keyword to the spells you cast ("spells you cast have
            # convoke/cascade/improvise/delve/demonstrate/flash", a casualty granter
            # with a BLANK counter_kind — Anhelo). The cast_with_keyword category is a
            # precise structured read (no over-fire), so fire for the WHOLE category
            # regardless of counter_kind — it co-fires with flash_grant /
            # convoke_matters on those subsets (Chief Engineer is both). Ordered AFTER
            # the flash/convoke special-cases so all the lanes fire. Cost-reduction
            # granters (Goblin Electromancer → cost_reduction) and spell-COPY (Galvanic
            # Iteration → spell_copy) are different categories and correctly excluded.
            # CR 702 (keyword abilities) / 601.3e (cast with an added keyword).
            if cat == "cast_with_keyword":
                add("spell_keyword_grant", "you", "", e.raw)
            # Doubling replacements (v0.1.60's `replacements`), split by event —
            # a token doubler and a counter doubler are different archetypes.
            if cat == "token_doubling":
                add("token_doubling", "you", "", e.raw)
            if cat == "counter_doubling":
                add("counter_doubling", "you", "", e.raw)
                # counter_replace_bonus (ADR-0027) — is_widen_of counter_doubling,
                # FULLY SUBSUMED by it: a counter-placement REPLACEMENT that
                # INCREASES the count (Hardened Scales "that many plus one",
                # Branching Evolution "twice that many", Conclave / Winding
                # Constrictor "plus one") is exactly phase's counter_doubling
                # category (project: event=='addcounter' + qmod in _INCREASE_MODS).
                # A counter-REDUCING replacement is excluded by the increase gate,
                # so neither lane over-fires. Co-fires (a doubler is both lanes).
                add("counter_replace_bonus", "you", "", e.raw)
            # counter_replace_bonus tail (ADR-0027) — a TEMPORARY activated
            # replacement ("until end of turn, if you would put … put that many plus
            # one instead" — Prairie Dog) phase types as place_counter(kind='plus')
            # rather than a static counter_doubling, since it is not a permanent
            # replacement. The 'plus' kind is exact (1 card corpus-wide), so it
            # recovers the tail with zero over-fire. CR 614 (replacement effects).
            if cat == "place_counter" and e.counter_kind == "plus":
                add("counter_replace_bonus", "you", "", e.raw)
            if cat == "damage_doubling":  # Batch 10 — DamageDone replacement doubler
                add("damage_doubling", "you", "", e.raw)
            # hand_disruption only when an OPPONENT reveals (a self-reveal — "reveal
            # cards in your hand" — is scope "any" and not disruption).
            if cat == "reveal_hand" and e.scope == "opp":
                add("hand_disruption", "opponents", "", e.raw)
        # ── Condition-gated lanes (the conditions projection) ──
        cond = ab.condition
        if cond is not None:
            # free_creature_payoff (ADR-0027 tranche2-C) — an ETB-triggered ability
            # conditioned on "no mana was spent to cast it/them" rewards creatures that
            # enter for free, so the deck wants 0-cost creatures (Ornithopter, Memnite).
            # phase exposes the condition as a manaspentcondition nested in the
            # condition tree (Satoru the Infiltrator nests it under an 'or' alongside a
            # 'not'>'wascast'); recurse to find it. The Trigger.event=='etb' gate is the
            # discriminator that excludes the 4 cast_spell-triggered manaspentcondition
            # cards — Lavinia / Boromir / Roiling Vortex / Vexing Bauble — which COUNTER
            # or TAX opponents' free spells (an anti-free-spell punisher, the opposite
            # lane). 'wascast' alone is NOT the tell (a 0-cost creature IS cast for no
            # mana — the mana-spent half is the discriminator). CR 712 / 601.2h.
            if (
                ab.trigger is not None
                and ab.trigger.event == "etb"
                and _condition_has_kind(cond, "manaspentcondition")
            ):
                add("free_creature_payoff", "you", "", "")
            # Graveyard gate — "if a creature card is in your graveyard"
            # (threshold/delirium), "if ~ is in your graveyard", a graveyard count.
            if "graveyard" in cond.zones:
                add("graveyard_matters", "you", "", "")
            # Gate on a TYPE you control/count (ControlsType / "control three or more
            # artifacts" = metalcraft/affinity / a tribal gate) → that type matters.
            # Skip the generic Creature/Permanent gates (≈ every creature deck) and
            # any opponent-controlled gate (a removal condition, not your synergy).
            csub = cond.subject
            if (
                csub is not None
                and cond.kind
                in ("controlstype", "quantitycomparison", "quantitycheck", "ispresent")
                and csub.controller != "opp"
            ):
                cft = _ftypes(csub)
                if "Artifact" in cft:
                    add("artifacts_matter", "you", "", "")
                if "Enchantment" in cft:
                    add("enchantments_matter", "you", "", "")
                if "Planeswalker" in cft:
                    add("superfriends_matters", "you", "", "")
                for st in _kindred_subjects(csub, vocab):
                    add(signal_keys.TYPE_MATTERS, "you", st, "")
                # ADR-0027 — the THRESHOLD-GATE tapped payoff: "if you control two or
                # more tapped creatures, …" (Vaultguard Trooper, Sami Ship's Engineer).
                # The Tapped filter rides the condition subject, read here off the same
                # in-hand csub the type gates use. Gated to a Creature subject — a
                # "no tapped LANDS" negative gate (Nantuko Shaman, Martyr's Soul) is a
                # mana check, not a tapped-creatures aggro payoff.
                if "Tapped" in csub.predicates and "Creature" in cft:
                    add("tapped_matters", "you", "", "")
            # Gate on a COUNTER kind ("if ~ has a +1/+1 counter", oil/ki/m1m1/…) →
            # the counter lane (mirrors the place_counter counter_kind dispatch).
            if cond.kind == "hascounters":
                if cond.counter_kind == "p1p1":
                    add("counters_matter", "you", "", "")
                elif cond.counter_kind in _COUNTER_KIND_KEYS:
                    ck_key, ck_scope = _COUNTER_KIND_KEYS[cond.counter_kind]
                    add(ck_key, ck_scope, "", "")
            # ADR-0027 — a triggered/static ability GATED on being the monarch
            # ("if you're the monarch …", CR 725): Throne Warden, Garrulous
            # Sycophant. The monarch reference lives in the condition, not an
            # effect category, so the doer projection (_DOER_EFFECT_KEYS['monarch'])
            # misses it; this lifts the ismonarch gate into the monarch lane.
            if cond.kind == "ismonarch":
                add("monarch_matters", "you", "", "")
            # ADR-0027 — venture_matters condition-kind PAYOFFS: a dungeon-completion
            # ("as long as you've completed a dungeon" — Gloom Stalker) or initiative
            # ("if you have the initiative" — Imoen, Safana) gate. phase has a stable
            # enum kind for these; the venture verb lives in no effect category, so the
            # condition gate is the structural anchor (CR 701.46 / 720).
            if cond.kind in ("completedadungeon", "isinitiative"):
                add("venture_matters", "you", "", "")
        # Trigger-gated graveyard_matters (the trigger-dimension projection): a
        # trigger on cards ENTERING the graveyard from a non-battlefield zone
        # (mill / "put into your graveyard from anywhere" — Syr Konrad) or LEAVING
        # the graveyard cares about graveyards. The battlefield→graveyard case is
        # `dies` (death_matters, not graveyard synergy), so it's gated out — exactly
        # the Effect.zones policy, now on the trigger's zone movement.
        trg = ab.trigger
        if trg is not None and (
            "from:graveyard" in trg.zones
            or ("to:graveyard" in trg.zones and "from:battlefield" not in trg.zones)
        ):
            add("graveyard_matters", "you", "", "")
        # Cost-based lanes (Ability.cost — a sacrifice OUTLET vs a sac effect).
        if ab.cost:
            cost_parts = set(ab.cost.split(","))
            if "sacrifice" in cost_parts:
                add("sacrifice_matters", "you", "", "")
            # activated_draw (ADR-0027): a TAP-to-DRAW activated engine — the
            # repeatable card-advantage source you want to untap (Arch of Orazca,
            # Bonders' Enclave, Arcane Encyclopedia, Niv-Mizzet). The {T} gate is the
            # cost field carrying 'tap'; the draw is an Effect category=='draw'. Use
            # the LOOSER 'tap' in cost (catches the {N}{T}: draw rocks/lands the literal
            # regex {T}-only anchor missed) — a tap-to-draw engine with an extra mana
            # cost is still the same engine. A sacself/discardself-cost draw (Forgotten
            # Cave cycling, cost='discardself,mana') lacks 'tap' → correctly excluded;
            # a paylife-draw (Erebos, cost='mana,paylife') likewise lacks 'tap'.
            if (
                ab.kind == "activated"
                and "tap" in cost_parts
                and any(e.category == "draw" for e in ab.effects)
            ):
                add("activated_draw", "you", "", "")
            # Batch 2 — a repeatable pay-life COST wants lifegain insurance.
            if "paylife" in cost_parts:
                add("life_payment_insurance", "you", "", "")
                # ADR-0027 lifeloss_matters — a pay-life ACTIVATION COST that buys a
                # real engine effect (Beledros paylife→untap-all-lands, Cauldron
                # paylife→reanimate, Sentry paylife→regenerate) is a life-as-resource
                # payoff. Gate hard against the lane's land trap: a paylife ability
                # whose ONLY effects are mana fixing (`ramp`) is a painland/fetch/
                # shockland (Horizon Canopy, Boseiju), excluded by the non-ramp gate;
                # a Land card is excluded defensively (Eumidian Hatchery rides a
                # place_counter past the ramp gate but is still mana fixing). CR 118.
                if not card_is_land and any(e.category != "ramp" for e in ab.effects):
                    add("lifeloss_matters", "you", "", "")
            # A discard OUTLET ("Discard a card: ...") pitches fodder for value —
            # madness/reanimator fuel. The cost projection splits self-discard
            # (Cycling's "discardself") out, so this no longer floods on alt-costs.
            if "discard" in cost_parts:
                add("discard_outlet", "you", "", "")
            # A graveyard-FUEL cost ("Exile this card from your graveyard" — Renew /
            # escape, Boneyard Mycodrax; "Exile the top card of your graveyard" —
            # Alms): the ability is powered by spending graveyard cards, a self-GY
            # payoff (CR 702.55a / Renew). The cost projection tags this `exilegrave`
            # (a battlefield/hand exile cost stays generic `exile`), so it never fires
            # on a non-graveyard exile cost.
            if "exilegrave" in cost_parts:
                add("graveyard_matters", "you", "", "")
            # counters_matter (ADR-0027 shape 5) — a recurring ability whose COST
            # spends counters ("Remove a +1/+1 counter from ~: …" — Triskelion pings,
            # Crystalline Crawler, Ulasht) is a +1/+1 counter sink/outlet, the engine
            # the lane wants. The cost field is a generic 'removecounter' with NO kind,
            # so gate on the card's oracle naming "+1/+1 counter": the 258 non-+1/+1
            # removecounter cards (ki / depletion / quest / spore / charge / page /
            # wish / loyalty sinks) route to their own lanes and must stay out (CR
            # 122.1). minus_counters_matter (m1m1) stays separate via its kind path.
            if "removecounter" in cost_parts and "+1/+1 counter" in (
                card.get("oracle_text") or ""
            ):
                add("counters_matter", "you", "", "")
            # ADR-0027 β — activated_ability (formerly a bare-cost _DETECTORS regex):
            # a card whose engine is a MEANINGFUL activated ability — the {T}:/{Q}:
            # or generic-mana-cost ability ({2}{U}{B}: …, {8}:, {X}: …) a tap-engine
            # commander deck supports with cost reducers (Training Grounds), untappers
            # + haste-for-abilities (Thousand-Year Elixir), and ability copiers (Rings
            # of Brighthearth). The deleted regex fired on the COST SHAPE alone, which
            # FLOODED on every land/rock/dork's "{T}: Add {mana}" mana ability (Forest,
            # Sol Ring, Llanowar Elves all matched `{t}:`). Two structural
            # discriminators kill the flood WITHOUT a recall loss:
            #   1. is_mana_ability — phase's Mana effect projects to category 'ramp',
            #      so a mana ability has ONLY ramp/attach effects; gating on >=1
            #      NON-ramp, NON-attach effect drops the mana flood (and equip, an
            #      Attach the regex never matched). CR 605.1a (mana ability).
            #   2. genericmana (SIDECAR v15) — the `mana`-only branch fires only on a
            #      cost carrying a GENERIC numeral / {0} / {X}, never a
            #      colored-/hybrid-/snow-ONLY firebreathing cost ({R}: +1/+0), which
            #      the regex's generic branch ({(?:\d+|x)\}) excluded (firebreathing
            #      has its own pump lane). An additional sac/discard/exile cost on the
            #      mana branch is excluded too — the regex's 18-char window dropped
            #      those one-shots ({3}{B}, Sacrifice this: …); a 'tap'/'untap' cost
            #      overrides (the {T}:/{Q}: anchor fired regardless). CR 602.1a.
            # Fire scope "you" — the deleted high-confidence _DETECTORS row hard-forced
            # scope "you" for ALL matches (its firing identity). +recall over the
            # word-order regex: generic-mana engines past the 18-char window (the
            # Moonfolk land-bounce cycle — Meloku, Soratami/Oboro/Uyo; the Eldrazi
            # processors — Oracle of Dust, Void Attendant; tap-untapped-creatures value
            # — Sigil Tracer, Volrath's Gardens; Tenth District Hero, Rootha, Zareth
            # San). NO kept mirror: a byte-identical mirror re-floods on dorks; the
            # quoted-board-grant tail ("Creatures you control have '{T}: …'" — Magma
            # Sliver, Ghired) is the sibling global_ability_grant lane's concern (most
            # already fire it). CR 602.1a.
            _aa_cost = cost_parts
            _aa_tapish = bool(_aa_cost & {"tap", "untap"})
            _aa_genmana = "genericmana" in _aa_cost and not (
                _aa_cost & _ACTIVATED_ABILITY_EXTRA_COSTS
            )
            if (
                ab.kind == "activated"
                and not card_is_land
                and (_aa_tapish or _aa_genmana)
                and any(
                    e.category not in _ACTIVATED_ABILITY_DROP_EFFECTS
                    for e in ab.effects
                )
            ):
                add("activated_ability", "you", "", "")
        # aoe_ping (ADR-0027): a REPEATABLE "damage to each creature" board ping — with
        # deathtouch on the source every ping is lethal (CR 702.2b), a recurring
        # one-sided wipe (Pestilence, Pyrohemia, Tibor and Lumia). The damage half is
        # the counter_kind=='all' damage over a Creature subject; the REPEATABLE-FRAME
        # gate is the precision discriminator. Repeatable = (a) an activated ability
        # whose cost has 'tap' or 'mana' but NOT 'sacself'/'sacrifice' (a one-shot
        # sac-self pinger — Bloodfire Colossus cost='mana,sacself' — can't be suited up
        # before it fires, excluded), OR (b) a triggered ability on upkeep / end_step /
        # cast_spell. A one-shot ETB sweep (Chaos Maw, event='etb') is NOT repeatable
        # and stays out — the lane's whole point is gearing up the source first.
        _ap_cost = set(ab.cost.split(",")) if ab.cost else set()
        _ap_repeatable = (
            ab.kind == "activated"
            and not ({"sacself", "sacrifice"} & _ap_cost)
            and bool({"tap", "mana"} & _ap_cost)
        ) or (
            ab.kind == "triggered"
            and ab.trigger is not None
            and ab.trigger.event in ("upkeep", "end_step", "cast_spell")
        )
        if _ap_repeatable:
            for e in ab.effects:
                if (
                    e.category == "damage"
                    and e.counter_kind == "all"
                    and isinstance(e.subject, Filter)
                    and "Creature" in e.subject.card_types
                ):
                    add("aoe_ping", "you", "", e.raw)
        trig = ab.trigger
        if trig is not None:
            # counters_matter (ADR-0027) — a counter-HAVE TRIGGER: "whenever a creature
            # you control WITH a +1/+1 counter on it dies / deals combat damage …"
            # (Laid to Rest, Bred for the Hunt, Meltstrider Eulogist). The Counters
            # predicate rides the trigger's subject Filter (the effect-subject read
            # above only sees effect subjects, not the trigger condition's subject).
            tsub = trig.subject
            if (
                isinstance(tsub, Filter)
                and tsub.controller != "opp"
                and "Counters" in tsub.predicates
            ):
                add("counters_matter", "you", "", "")
            # death_matters is the ARISTOCRATS payoff — OTHER creatures dying. A
            # "when this dies" self-death trigger (SelfRef → no subject filter) is
            # self_death_payoff, a different lane, so gate on a real subject.
            if trig.event == "dies" and trig.subject is not None:
                add("death_matters", _ir_scope(trig.scope), "", "")
            # The complement: a true SELF-death trigger (SelfRef → scope "you")
            # that produces a recognized payoff (Kokusho, Solemn, Festering Goblin)
            # — wants sac outlets + recursion. Gating on SelfRef excludes
            # "equipped creature dies" (Skullclamp, AttachedTo → scope "any"); the
            # recognized-effect gate drops unparsed "other"-only death triggers.
            elif (
                trig.event == "dies"
                and trig.scope == "you"
                and any(e.category != "other" for e in ab.effects)
            ):
                add("self_death_payoff", "you", "", "")
            # ADR-0027 β — ltb_matters STRUCTURAL arm. A `leaves` trigger (phase's
            # LeavesBattlefield mode, projected event=='leaves' @ SIDECAR v11 — broader
            # than `dies`: any battlefield→elsewhere, CR 603.6e) on an OTHER permanent
            # leaving the battlefield is the leaves-MATTERS payoff (the aristocrats /
            # blink / bounce engine — Luminous Phantom, Dour Port-Mage, Nadier's
            # Nightblade; bounce payoffs Azorius Aethermage / Warped Devotion). Gate on
            # (a) a real subject (subject=None is a SelfRef self-LTB — the card's OWN
            # leave — which rides the narrowed mirror, not here, mirroring the
            # death/self_death split) and (b) a BATTLEFIELD-leave: from:battlefield in
            # zones, OR no directional from/to zone (the bare LeavesBattlefield mode
            # phase emits without an explicit destination). This EXCLUDES the graveyard-
            # arrival "put into a graveyard from anywhere" ChangesZone triggers the
            # projection also tags `leaves` (to:graveyard with no from:battlefield —
            # Compost, Countryside Crusher; those are graveyard_matters, not leaves-the-
            # battlefield). scope per the trigger. CR 603.6e / 700.4.
            if trig.event == "leaves" and trig.subject is not None:
                _z = set(trig.zones)
                _from_bf = "from:battlefield" in _z
                _has_dir = any(t.startswith(("from:", "to:")) for t in _z)
                if _from_bf or not _has_dir:
                    add("ltb_matters", _ir_scope(trig.scope), "", "")
            if trig.event == "life_gained":
                add("lifegain_matters", "you", "", "")
            # ADR-0027 lifeloss_matters — the pure life-loss PAYOFF: a trigger that
            # fires when a player loses life ("whenever an opponent loses life" →
            # Exquisite Blood, Mindcrank, Bloodthirsty Conqueror; "whenever you lose
            # life" → Vilis). phase parses it as Trigger(event='life_lost') — a
            # cares-about payoff that combos with the drain, so it opens the lane. An
            # opp-scoped trigger is the drain payoff (opponents); else you/any.
            if trig.event == "life_lost":
                add(
                    "lifeloss_matters",
                    "opponents" if trig.scope == "opp" else "you",
                    "",
                    "",
                )
            # ADR-0027 lose_unless_hand — the cast-from-hand-or-lose drawback (Phage
            # the Untouchable): an ETB trigger scoped to YOU whose consequence is a
            # lose_game effect ("when ~ enters, if you didn't cast it from your hand,
            # you lose the game"). The etb + scope=you + lose_game shape is unique to
            # Phage out of 41 lose_game cards — it cleanly excludes the extra-turn
            # self-lose drawbacks (Final Fortune, Glorious End — lose_game on an
            # end-step / delayed trigger), the opponent-lose payoffs (Door to Nothing —
            # scope any/opp), and the static lose-prevention engines (Lich, Lab Maniac).
            # phase emits a dedicated lose_game category, so the cast-zone CONDITION
            # need not be separately structured. CR 104.3a.
            if (
                trig.event == "etb"
                and trig.scope == "you"
                and any(e.category == "lose_game" for e in ab.effects)
            ):
                add("lose_unless_hand", "you", "", "")
            # ADR-0027 sacrifice_matters — the pure SAC PAYOFF: a trigger that fires
            # on the act of sacrificing ("whenever you sacrifice a creature/artifact"
            # → reward; Gleaming Geardrake's "sacrificed" trigger → +1/+1 counter).
            # phase parses this as Trigger(event='sacrificed') — unambiguously a sac
            # payoff, so no discriminator is needed. CR 701.16.
            if trig.event == "sacrificed":
                add("sacrifice_matters", "you", "", "")
            # Batch 2c — trigger-event "payoff" lanes.
            payoff = _PAYOFF_TRIGGER_KEYS.get(trig.event)
            if payoff is not None:
                key, fixed_scope = payoff
                add(key, fixed_scope or _ir_scope(trig.scope), "", "")
            # counter_place_trigger (ADR-0027) — is_widen_of counters_matter, but a
            # DISTINCT lane: a "whenever one or more counters are put on …" TRIGGER
            # (Shalai and Hallar, Generous Pup, Scurry Oak, Flourishing Defenses,
            # Nest of Scarabs). phase types these as event=='counter_added'. The
            # _PAYOFF_TRIGGER_KEYS row above co-opens counters_matter; this opens the
            # place-trigger lane too (both correct). Gate scope!='opp' so an opponent-
            # side punisher ("counters on a creature you DON'T control" — Kros,
            # Generous Patron, scope='opp') does not open a YOUR-counters build-around.
            # EXCLUDE Sagas / lore-counter cards: phase types a Saga CHAPTER trigger
            # ("add a lore counter", CR 714.2) as the SAME counter_added(scope='you',
            # subj=None) event a legit +1/+1 payoff (Scurry Oak, Generous Pup) carries
            # — 202 Sagas would over-fire otherwise. The Saga supertype / lore-counter
            # reminder is the only discriminator (the trigger carries no kind). NOTE:
            # the TRIGGER form — distinct from the place_counter EFFECT doers
            # (counter_distribute / self_counter_grow); Cathars' Crusade / Experiment
            # Twelve (an effect that PLACES counters) must NOT fire here.
            if (
                trig.event == "counter_added"
                and trig.scope != "opp"
                and not _is_lore_counter_card
            ):
                add("counter_place_trigger", "you", "", "")
            # Batch 1 — cycling_matters: a "whenever you cycle a card" payoff (valid
            # card null → scope "any"), NOT a SelfRef "when you cycle THIS" bonus
            # (scope "you" — having cycling ≠ a cycling-theme payoff).
            if trig.event == "cycled" and trig.scope != "you":
                add("cycling_matters", "you", "", "")
            # Batch 3 — tribal trigger ("whenever a Goblin you control enters").
            for sub in _kindred_subjects(trig.subject, vocab):
                add(signal_keys.TYPE_MATTERS, "you", sub, "")
            # ── Batch T — trigger-event lanes ──
            ev = trig.event
            tsubs = _ftypes(trig.subject)
            tsub_kinds = _fsubs_lower(trig.subject)
            # combat_buff_engine: a begin-combat trigger that PUMPS (Additive
            # Evolution — "at the beginning of combat on your turn, put a +1/+1
            # counter ..."). A co-occurrence: the trigger event + a pump/counter
            # effect in the SAME ability (the flat per-effect pass can't see this).
            if ev == "begin_combat" and any(
                e.category in ("pump", "place_counter") for e in ab.effects
            ):
                add("combat_buff_engine", "you", "", "")
            # damage_reflect: a "when this is dealt damage" trigger that DEALS damage
            # back (Boros Reckoner, Brash Taunter, Coalhauler Swine). Co-occurrence:
            # DamageReceived event + a damage effect (excludes the fight/lifeloss/
            # counter "when dealt damage" cards, which aren't reflectors).
            if ev == "damage_received" and any(
                e.category == "damage" for e in ab.effects
            ):
                add("damage_reflect", "you", "", "")
            if ev == "taps":
                add("tap_untap_matters", "you", "", "")
            if ev == "discarded":
                add("discard_matters", "you", "", "")
            # Token-subtype sacrifice PAYOFF (trigger side): "whenever you sacrifice
            # one or more <Subtype> tokens, ..." (Blood Hypnotist). The token subtype
            # rides the trigger subject Filter — the same token-subtype synergy
            # pattern the effect loop scans for makers + sacrifice-effect payoffs.
            if ev == "sacrificed":
                for st in tsub_kinds:
                    if st in _TOKEN_SUBTYPE_KEYS:
                        tk, ts = _TOKEN_SUBTYPE_KEYS[st]
                        add(tk, ts, "", "")
            if ev == "drawn":
                add("draw_matters", "you", "", "")
                # Batch 11 — "whenever an OPPONENT draws" (Nekusar / Notion Thief).
                if trig.scope == "opp":
                    add("opponent_draw_matters", "opponents", "", "")
            # creature_etb (ETB-VALUE) — cares when OTHER creatures enter (a Typed
            # subject; a self-ETB SelfRef→None is a one-shot, not this lane). Scope
            # tracks WHOSE entering creature triggers it (yours = value, an
            # opponent's = punisher), as the regex forces.
            if ev == "etb" and "Creature" in tsubs:
                add(
                    "creature_etb",
                    "opponents" if _filter_controller(trig.subject) == "opp" else "you",
                    "",
                    "",
                )
            # tribal_etb_multi (ADR-0027): a tribal ETB-chain payoff — an `etb`
            # trigger whose subject Filter names a CREATURE SUBTYPE ("whenever this or
            # another Zombie you control enters" — Noxious Ghoul, Goblin Assassin,
            # Fludge). The vocab-gated subtype is the discriminator vs a generic
            # creature/permanent ETB (Serum Tank's Artifact subject, River Kelpie's
            # "permanent from a graveyard" carry no creature subtype → excluded). The
            # broad read (any tribal-ETB trigger) is the lane's intent — it surfaces
            # every tribal-ETB chain, overlapping creature_etb + type_matters (which
            # the trigger-subject _kindred_subjects pass already opens). CR 603.
            if ev == "etb" and _kindred_subjects(trig.subject, vocab):
                add("tribal_etb_multi", "you", "", "")
            # typed_enters_punish (ADR-0027): a per-ability co-occurrence — an `etb`
            # trigger on a YOUR-controlled creature/typed-thing ("another <X> you
            # control enters") whose consequence BURNS the opponents (Purphoros, Witty
            # Roastmaster, Vial Smasher). The discriminator vs plain creature_etb
            # (ETB-value) is the damage-to-OPPONENT payoff: a damage Effect whose
            # recipient is an opponent — subject Filter controller=='opp' (Vial
            # Smasher), scope in ('opp','each'), OR raw naming "each/target/your
            # opponent(s)" / "any target" (Purphoros / Witty — phase scopes the effect
            # 'any' but the raw says "each opponent"). NOT subtype-gated — the lane is
            # "another creature/typed-thing enters → burn", the damage payoff IS the
            # tell. CR 603.
            if (
                ev == "etb"
                and _filter_controller(trig.subject) == "you"
                and any(
                    e.category == "damage"
                    and (
                        _filter_controller(e.subject) == "opp"
                        or e.scope in ("opp", "each")
                        or _TYPED_ENTERS_OPP_RAW.search(e.raw or "")
                    )
                    for e in ab.effects
                )
            ):
                add("typed_enters_punish", "you", "", "")
            # permanent_etb (ADR-0027): the GENERIC permanent-ETB value engine —
            # "whenever a/another permanent you control enters" (Amareth, Cloudstone
            # Curio, Kodama of the East Tree, Yoshimaru, Builder's Talent). The
            # discriminator vs creature_etb is the subject card_type: 'Permanent' (NOT
            # 'Creature' — that is creature_etb) and the controller-you gate (an
            # opponent-scoped permanent-ETB punisher is excluded; a self-ETB
            # SelfRef→None never has card_types=='Permanent', so it can't false-fire).
            # The IR is BROADER-and-correct vs the narrow word-order regex (it catches
            # "a/another permanent you control enters" variants the regex missed; +12
            # genuine recall, all generic-permanent-ETB engines). (CR 603.)
            if (
                ev == "etb"
                and "Permanent" in tsubs
                and _filter_controller(trig.subject) == "you"
            ):
                add("permanent_etb", "you", "", "")
            # ADR-0027 — recast_etb SERVE (the aggressive-ETB payoff a Sneak engine
            # recasts): an etb trigger whose consequence BLEEDS each opponent — a
            # discard / lose_life / sacrifice effect whose raw names "each opponent"
            # (Liliana's Specter "each opponent discards", Skirmish Rhino "each
            # opponent loses 2 life"). phase tags the controller scope, not the
            # recipient, so "each opponent" is recovered from raw. The raw-mirror
            # inside an etb-bleed effect distinguishes the recast payoff from any
            # random etb creature (the lane's whole point — not goodstuff).
            if ev == "etb" and any(
                e.category in ("discard", "lose_life", "sacrifice")
                and "each opponent" in (e.raw or "").lower()
                for e in ab.effects
            ):
                add("recast_etb", "you", "", "")
            # Batch 14 — landfall: a land ENTERING (etb trigger w/ Land subject) is
            # the bulk of landfall; the LandPlayed "play a land" trigger (_PAYOFF)
            # catches the rest.
            if ev == "etb" and "Land" in tsubs:
                add("landfall", "you", "", "")
            # artifacts_matter / enchantments_matter type-ETB DOER: "whenever an
            # artifact/enchantment (you control) enters" (constellation — Tuvasa /
            # Eidolon of Blossoms; artifact-ETB engines — Leonin Elder, Disciple of the
            # Vault). The any/you-controller symmetric form ("whenever an artifact
            # enters" — phase controller=null→'any') is the common own-payoff in a
            # type-flood deck, so it fires; an opponent-only set (controller opp — a
            # punisher, "whenever an artifact an opponent controls enters") is excluded
            # by _typed_matters_lanes' opp gate. A "Creature" co-type (artifact
            # creature) still counts (the artifact entering is what triggers it).
            if ev == "etb":
                for etb_lane in _typed_matters_lanes(trig.subject):
                    add(etb_lane, "you", "", "")
            # artifacts_matter / enchantments_matter "leaves the battlefield" DOER:
            # "whenever a(n) (nontoken) artifact/enchantment you control is put into a
            # graveyard from the battlefield" (Farid — artifact-attrition engine;
            # Starfield Mystic, Ashiok's Reaper — the enchantment-sac payoff). phase
            # parses this as a `dies` trigger over an Artifact/Enchantment-you-control
            # subject. A repeatable engine keyed on YOUR permanents of that type cycling
            # through the graveyard cares about having many of them (CR 603). A
            # composite subject fires both lanes; an opponent-scoped dies trigger
            # (removal punish) is excluded by the controller-you gate.
            if ev == "dies" and _filter_controller(trig.subject) == "you":
                for dies_lane in _typed_matters_lanes(trig.subject):
                    add(dies_lane, "you", "", "")
            # artifacts_matter / enchantments_matter ABILITY-PAYOFF DOER: "whenever you
            # activate an ability of an artifact, … copy it" (Kurkesh, Artificer Class).
            # phase tags the ability-activation trigger as event='other' but keeps the
            # ACTIVATED-OBJECT type on the trigger subject Filter. A deck rewarding its
            # own artifact activations cares about running many (CR 602/113). Gated on a
            # type-filtered subject scoped !=opp — an OPPONENT-activates punisher (Harsh
            # Mentor, Immolation Shaman, "ability of an artifact, creature, or land")
            # collapses to subject=None and never fires.
            if ev == "other" and trig.scope != "opp":
                for abil_lane in _typed_matters_lanes(trig.subject):
                    add(abil_lane, "you", "", "")
            if ev in ("combat_damage", "deals_damage"):
                add("combat_damage_matters", "opponents", "", "")
                # ADR-0027 β damage_to_opp_matters — a NON-COMBAT "deals damage to a
                # PLAYER / opponent" connect-payoff (Hypnotic Specter, Curiosity,
                # Goblin Lackey, Fungal Shambler). project._project_trigger stamps the
                # DamageToPlayer recipient marker on the trigger subject (the player
                # recipient phase keeps on valid_target but the Trigger otherwise drops
                # — scope reads only the controller, collapsing a {type:Player,
                # controller:null} recipient to scope='any'). Fire on the marker, not on
                # the lossy scope, so the player-typed recipients the old scope=='opp'
                # arm missed (Hypnotic Specter's {type:Player,null}) now fire. combat-
                # ONLY recipients never carry the marker (combat_damage_to_opp, already
                # migrated 42f6d81). +recall over the deleted regex: structural
                # placement catches "deals 6 or more damage to an opponent" (Deus of
                # Calamity), "deal damage to a player" plural (Francisco / Dragonborn
                # Champion), "another player" (Night Dealings) — the word-order/pronoun
                # regex missed. The granted-ability / ETB-burst tail phase can't
                # structure rides the narrowed _DAMAGE_TO_OPP_MATTERS_MIRROR. CR 119.3.
                if trig.subject is not None and (
                    "DamageToPlayer" in trig.subject.predicates
                ):
                    add("damage_to_opp_matters", "opponents", "", "")
                # ADR-0027 β — tribe_damage_trigger's dead `if tsub_kinds:` arm is
                # removed: phase leaves a combat_damage trigger's subject = None, so
                # tsub_kinds is always empty here and the arm never fired. The lane is
                # now served by the byte-identical _IR_KEPT_DETECTORS mirror.
            if ev == "cast_spell":
                # ADR-0027 opponent_cast_matters — the explicit scope=opp half
                # ("whenever an opponent casts a spell" — Lavinia, Nekusar). The
                # SYMMETRIC-PUNISH half (Ruric Thar, Mai, Eidolon of the Great Revel)
                # is NOT structurally separable here: phase reports BOTH "whenever a
                # player casts" (a punisher) AND "whenever YOU cast" (a self-cast
                # spellslinger payoff — Kessig Flamebreather, Thief of Hope, Extort) as
                # scope='any', so an effect-category punish gate would over-fire every
                # spellslinger that drains/burns each opponent. The symmetric-punisher's
                # discriminator survives only in raw ("…deals N damage to THAT PLAYER" /
                # "THAT PLAYER loses/discards/sacrifices" — the caster punished as a
                # third party), so it is recovered by an _IR_KEPT_DETECTORS word mirror
                # over the joined face, NOT a scope='any' structural arm. CR 603.2.
                if trig.scope == "opp":
                    add("opponent_cast_matters", "opponents", "", "")
                if "Creature" in tsubs:
                    add("creature_cast_trigger", "any", "", "")
                # ADR-0027 — convoke_matters PAYOFF: "Whenever you cast a spell that
                # has convoke, …" (Saint Traft, Joyful Stormsculptor). The "that has
                # convoke" qualifier survives only in the consequence effect raw (phase
                # tags a bare cast_spell trigger), so anchor on it rather than firing on
                # every spellcast trigger.
                if any(_CONVOKE_RAW.search(e.raw or "") for e in ab.effects):
                    add("convoke_matters", "you", "", "")
                # ADR-0027 (q2-D3) — noncreature_cast_punish OPPONENT-punisher half: a
                # cast_spell trigger scope=='opp' over a NONCREATURE subject (Kambal,
                # Mystic Remora, Esper Sentinel, Citanul Druid). The discriminator is
                # the subject Filter — a NotType:Creature predicate OR card_types
                # intersecting the noncreature set with Creature absent. Clean and
                # migratable (verified 0 over-fire on scope=='opp'). The SYMMETRIC "a
                # player casts a noncreature spell" half (Niv-Mizzet Parun, Mirrorwing)
                # collapses to scope=='any' and is INDISTINGUISHABLE from prowess in
                # phase v0.1.19, so it stays on the kept _IR_KEPT mirror (anchored on
                # "a player"/"an opponent" prowess "you cast" never matches). CR 603.2.
                if (
                    trig.scope == "opp"
                    and isinstance(trig.subject, Filter)
                    and (
                        "NotType:Creature" in trig.subject.predicates
                        or (
                            (set(trig.subject.card_types) & _NONCREATURE_SPELL_TYPES)
                            and "Creature" not in trig.subject.card_types
                        )
                    )
                ):
                    add("noncreature_cast_punish", "any", "", "")
                for sub in _kindred_subjects(trig.subject, vocab):
                    add(signal_keys.TYPED_SPELLCAST, "you", sub, "")
                # artifacts_matter / enchantments_matter cast-trigger DOER:
                # "whenever you cast an artifact/enchantment spell" (Mishra, Sythis,
                # Saheeli's "Artificer or artifact spell"). Gated on scope != "opp":
                # phase reports "you cast"/"a player casts" as scope "any" but an
                # OPPONENT-cast PUNISHER ("whenever an opponent casts an artifact
                # spell" — Citanul Druid, Infested Roothold) as scope "opp", which is
                # NOT a type deck. The subject co-typing with Creature (artifact
                # creature spell) still counts.
                if trig.scope != "opp":
                    for cast_lane in _typed_matters_lanes(trig.subject):
                        add(cast_lane, "you", "", "")
            # Batch 12 — nonhuman_attackers (Winota): an attack trigger whose
            # attacking subject is a non-Human creature you control.
            if (
                ev == "attacks"
                and _has_predicate(trig.subject, "NotSubtype:Human")
                and _filter_controller(trig.subject) == "you"
            ):
                add("nonhuman_attackers", "you", "", "")

    # Batch 2 — card-level Filter-predicate lanes: an effect/trigger that cares
    # about a Legendary / Historic object (the predicate is on its subject Filter).
    ir_predicates: set[str] = set()
    for ab in ir.all_abilities():
        subs: list[object] = [e.subject for e in ab.effects]
        subs += [e.amount.subject for e in ab.effects if e.amount is not None]
        if ab.trigger is not None:
            subs.append(ab.trigger.subject)
        for f in subs:
            if isinstance(f, Filter):
                ir_predicates.update(f.predicates)
                # Batch 5 — color/power build-around lanes (controller-gated).
                for key in _predicate_build_around_lanes(f):
                    add(key, "you", "", "")
    if "HasSupertype:Legendary" in ir_predicates:
        add("legends_matter", "you", "", "")
    if "Historic" in ir_predicates:
        add("historic_matters", "you", "", "")
    if "IsCommander" in ir_predicates:  # Batch 15 — cares about your commander
        add("commander_matters", "you", "", "")
    # named_permanent: the CR 100.2a copy-limit exception (a deck runs many copies of
    # one name — Relentless Rats, Hare Apparent, Seven Dwarves). The authoritative
    # signal is the deck_copy_limit field, NOT an oracle regex or a fuzzy named-count
    # heuristic (which would wrongly catch a 4-of graveyard-spell-count like
    # Accumulated Knowledge). These cards want every other copy of their name.
    if ir.many_copies:
        add("named_permanent", "you", "", "")

    # Voltron PAYOFF (ADR-0027) — the structural Aura/Equipment build-around, read
    # from phase's IR (attach action / cast-an-Aura trigger / Aura-Equipment tutor /
    # attachment-state subject) instead of the oracle-regex floor+sweep rows. This is
    # the *payoff* half only — the commander-damage MEMBERSHIP fallback stays on the
    # regex path (it's gated on `not has_other_plan` over the full signal set, which
    # the IR slice can't reproduce; see ADR-0027 deferral). Not membership-gated,
    # matching the regex producer (the payoff fires from a card's text, not its type).
    if _detect_voltron_payoff_ir(ir):
        add("voltron_matters", "you", "", "", "low")

    # creatures_matter mass-token-maker DOER (cross-open): a token_maker that makes
    # CREATURE tokens (a captured creature subject — Darien makes Soldiers, Jinnie
    # Fay Cats) is a go-wide creatures deck; it wants anthems / per-creature-ETB
    # payoffs / Cathars' Crusade the bare token_maker lane never serves. Mirrors the
    # regex SWEEP cross-open (`token_maker and s.subject`) — non-creature token
    # makers (Treasure/Clue) never set a token_maker subject, so they stay out. Low
    # confidence. (Done here, after the per-effect loop has collected token_maker.)
    if not any(s.key == "creatures_matter" for s in out) and any(
        s.key == signal_keys.TOKEN_MAKER and s.subject for s in out
    ):
        add("creatures_matter", "you", "", "", "low")

    # ADR-0027 creature_cast_trigger (face-level): a "casts a creature spell" reference
    # phase keeps only in some effect raw — a cast_spell trigger whose spell-type
    # subject was dropped (subject=None), an enters-with replacement place_counter, an
    # emblem / granted-token quoted ability. The lane is a creatures-being-cast payoff
    # (scope "any"), so one scan over every effect raw recovers them (the typed-subject
    # trigger path above already binds what phase structured).
    if not any(s.key == "creature_cast_trigger" for s in out) and any(
        _CREATURE_SPELL_RAW.search(e.raw or "")
        for ab in ir.all_abilities()
        for e in ab.effects
    ):
        add("creature_cast_trigger", "any", "", "")

    # Keyword-array signals (Batch 2a): authoritative Scryfall keyword lookups,
    # NOT oracle regex — they already survive into the IR-native world, so reuse
    # the existing detectors. Same source as the regex path → perfect parity.
    for key, scope in _detect_keyword_presets(card):
        add(key, scope, "", "")
    for key, scope in _detect_direct_keywords(card):
        add(key, scope, "", "")
    # Kept narrow mechanic-word detectors (real mechanics phase doesn't structure).
    kept_oracle = re.sub(r"\([^)]*\)", " ", get_oracle_text(card) or "")
    for key, pat, scope in _IR_KEPT_DETECTORS:
        if pat.search(kept_oracle):
            add(key, scope, "", "")
    # ADR-0027 β — combat_damage_to_opp double-strike-grant tail: a LOW-confidence
    # mirror of the deleted narrow regex producer (kept out of the HIGH-confidence
    # _IR_KEPT_DETECTORS loop so Raphael / Blade Historian / Berserkers' Onslaught keep
    # their commander-damage voltron tell). add() dedups vs the main opp mirror.
    if _COMBAT_DAMAGE_TO_OPP_DS_GRANT.search(kept_oracle):
        add("combat_damage_to_opp", "opponents", "", "", "low")
    # ADR-0027 t2b4-C — self_blink kept detector. No clean structural IR form (the
    # `~`-substituted exile raw can't be told from cost-exile / other-target exile), so
    # reproduce BOTH regex-path producers byte-identically: the name-aware cross-
    # sentence fulltext detector + the single-target SWEEP regex run per-clause (its
    # `[^.]*\.?\s*` arms span sentences over the whole oracle, so it must scan _clauses,
    # not flat text).
    if _detect_self_blink_fulltext(kept_oracle, name) is not None or any(
        _SELF_BLINK_SWEEP_RE.search(cl) for cl in _clauses(kept_oracle)
    ):
        add("self_blink", "you", "", "")
    # ADR-0027 β — impulse_top_play kept mirror. The structural cast_from_zone+
    # from:library arm above is broader-and-correct, but phase under-parses a tail (the
    # "you may play it this turn" follow-through it folds into a categoryless effect,
    # the modal "from among" clause). Recover it from the EXACT deleted SWEEP regex run
    # PER-CLAUSE — its `[^.]*\.?\s*` arms span a sentence over the whole oracle (+39
    # over-fire flat), so it must scan _clauses, not flat kept_oracle (matching the
    # deleted SWEEP path byte-identically; un-lowered clauses + IGNORECASE == clause.
    # lower(), so A-B==0). The add() dedup unions this with the structural arm.
    if any(_IMPULSE_TOP_PLAY_SWEEP_RE.search(cl) for cl in _clauses(kept_oracle)):
        add("impulse_top_play", "you", "", "")
    # ADR-0027 β — gain_control NARROWED kept mirror. The gated structural arm above
    # (cat=='gain_control', excl donate / Owned-return / give-away) is a recall-gaining
    # superset of the deleted `gain control of` regex, but phase emits NO gain_control
    # category for 9 genuine theft cards (Seize the Spotlight, Power of Persuasion,
    # Invert Polarity steal-a-spell, Wake the Dragon token, Expropriate, Midnight
    # Crusader Shuttle, Captivating Glance, Herald of Leshrac, Risky Move). Recover them
    # with the deleted producer's `gain control of` run PER-CLAUSE, vetoed per-clause by
    # the give-away / reset / protection forms the structural arm drops (you-own reset,
    # "<player> gains control" give-away, "can't gain control" protection). PER-CLAUSE
    # (not flat) so one clause's veto can't kill another clause's genuine theft —
    # Captivating Glance / Herald each keep their theft sentence. scope 'you' (the
    # deleted producer's forced scope). add() dedups vs the structural arm. CR 800.4a /
    # 720.1.
    if any(
        _GAIN_CONTROL_MIRROR.search(cl) and not _GAIN_CONTROL_MIRROR_VETO.search(cl)
        for cl in _clauses(kept_oracle)
    ):
        add("gain_control", "you", "", "")
    # ADR-0027 β — ltb_matters NARROWED kept mirror. The structural `leaves`-trigger
    # arm above catches phase's "whenever ANOTHER permanent leaves the battlefield"
    # payoffs, but phase leaves the bulk textual: the Revolt "a permanent left the
    # battlefield this turn" condition is a static check (no trigger), and the self-LTB
    # payoff ("when ~ leaves the battlefield, …" — Walker of the Grove, Sengir Autocrat,
    # Skyclave Apparition) is a SelfRef trigger (subject=None, gated out of the
    # structural arm). Recover them with the deleted producer's exact regex run
    # PER-CLAUSE, VETOED per-clause by the O-Ring self-LTB-EXILE form ("exile … until ~
    # leaves the battlefield" — Banishing Light / Static Prison) so the 93 over-fires
    # drop (already exile_until_leaves; 100% over-fire vs Scryfall, 0 genuine payoff
    # lost). PER-CLAUSE so the veto on the "exile … until ~ leaves" clause can't kill a
    # co-printed genuine leave payoff. scope 'you' (the deleted producer's forced
    # scope). add() dedups vs the structural arm. CR 603.6e / 700.4.
    if any(
        _LTB_MATTERS_MIRROR.search(cl) and not _LTB_MATTERS_MIRROR_VETO.search(cl)
        for cl in _clauses(kept_oracle)
    ):
        add("ltb_matters", "you", "", "")
    # ADR-0027 β — self_counter_grow NARROWED kept mirror. The structural arm above
    # fires
    # on a place_counter carrying the SelfRef self-anchor marker (project @ SIDECAR
    # v12),
    # but phase drops the anchor on a small structural tail (the Adversary multi-pay
    # "put
    # that many +1/+1 counters on this creature", Stormwild Capridor's damage-prevention
    # static, Scarlet Spider's ParentTarget branch — 14 self-growers the deleted regex
    # caught via its SELF-ANCHORED text arms). Recover them with the NARROWED regex (the
    # self-anchored arms only — "on him/her/itself/this creature", MINUS the loose "on
    # it"
    # arm that 100%-over-fired onto OTHER-creature placements; the SelfRef IR gate
    # already
    # excludes those, and a byte-identical full-text mirror would re-introduce the 103
    # over-fires). PLUS the self-power-scaling commander cross-open ("X is ~'s power" →
    # wants +1/+1 sources — Mona Lisa, Esper Sentinel, Velomachus), re-homed from the
    # deleted low-confidence _DETECTORS add. scope 'you' (the deleted producer's forced
    # scope). add() dedups vs the structural arm. CR 122.1 / 614.12.
    if any(
        _SELF_COUNTER_GROW_MIRROR.search(cl) for cl in _clauses(kept_oracle)
    ) or self_power_scale_match(kept_oracle, name):
        add("self_counter_grow", "you", "", "")
    # ADR-0027 β — untap_engine NARROWED kept mirror. The structural arm above reads
    # `cat=='untap'` Effects, but phase routes ~11 genuine engines into a choose /
    # target_only / cost / type_set carrier with NO cat=='untap' Effect (Captain of the
    # Mists & Tideforce Elemental — modal "tap or untap target"; Turnabout & Faces of
    # the Past — "tap-all OR untap-all" choose; All-Out Assault — mass-untap-own-board
    # folded into extra_combat; Teferi Who Slows the Sunset & Zariel — emblem untap in
    # an effect raw; Crackleburr & Halo Fountain — "untap two tapped … you control" as a
    # COST; Ohabi Caleria — "untap all Archers you control" static phase drops; Ashaya —
    # the creatures-are-lands synergy). Recover them with the EXACT deleted _HAND_FLOOR
    # regexes (the target/all/each/two/up-to engine + the creatures-are-lands marker)
    # over the reminder-stripped kept_oracle, byte-identical to the deleted floor
    # Detectors — BUT vetoed by the opp-untap anti-pattern so it drops the same
    # incidental enemy-untap over-fires the structural arm does (Provoke / Spinal
    # Embrace "Untap target creature you don't control", which the deleted regex
    # incorrectly caught because it ran reminder-stripped and couldn't read "you don't
    # control").
    # Net residual vs the deleted regex: regex_only == {Provoke, Spinal Embrace}, 100%
    # over-fire (CR 701.16 / 903.10a). add() dedups the overlap with the structural arm.
    if not _UNTAP_ENGINE_OPP_VETO.search(kept_oracle) and (
        _UNTAP_ENGINE_MIRROR_RAW.search(kept_oracle)
        or _UNTAP_ENGINE_MIRROR_LANDS.search(kept_oracle)
    ):
        add("untap_engine", "you", "", "")
    # ADR-0027 β — variable_pt NARROWED kept mirror. The structural arm above reads a
    # `characteristic_pt` Effect (the self-CDA — Nightmare — and the oracle-text CDA —
    # Tarmogoyf), but phase can't structure the TOKEN-borne */* ("This token's power and
    # toughness are each equal to" — Seize the Storm, Ajani Goldmane's Avatar) or the
    # TRIGGERED "change <Name>'s base power and toughness" self-set (Halfdane, Eldrazi
    # Mimic, Shape Stealer) as a self-CDA static. Recover them with the core CDA phrase
    # over the reminder-stripped kept_oracle, vetoed by the burn/draw "cards in hand|
    # library" and "change … of all/each/other … creatures" over-fires the deleted SWEEP
    # regex had (Spiraling Embers / Enter the Infinite / Sword of War and Peace — burn/
    # draw, not a */* body; Brine Hag / Exuberant Wolfbear — a mass-debuff on OTHERS).
    # add() dedups vs the structural arm. CR 604.3.
    if _VARIABLE_PT_MIRROR.search(kept_oracle) and not _VARIABLE_PT_MIRROR_VETO.search(
        kept_oracle
    ):
        add("variable_pt", "any", "", "")
    # ADR-0027 β — token_copy_matters BYTE-IDENTICAL kept mirror. The structural arm
    # (cat=='make_token') is the vanilla-token lane; phase DOES carry the copy detail
    # (CopyTokenOf/Populate) but the projection collapses both to make_token AND a
    # structural copy-arm would 100%-over-fire with reminder-text SELF-copies (Embalm/
    # Eternalize/Offspring/Double-team). So recover the lane with the EXACT deleted
    # _HAND_FLOOR regex over the reminder-stripped kept_oracle (scope 'you', matching
    # the deleted producer). add() dedups. CR 702.95 / 707.
    if _TOKEN_COPY_MATTERS_MIRROR.search(kept_oracle):
        add("token_copy_matters", "you", "", "")
    # ADR-0027 β — color_change BYTE-IDENTICAL kept mirror. phase parses the "becomes
    # the color of your choice / all colors" clause INCONSISTENTLY (20 cards as a nested
    # AddChosenColor modification, 4 as a bare Unimplemented "become"), and the only IR
    # category they share — cat=='animate' — 90%-over-fires (256 commander-legal cards
    # vs the 24 genuine color-changers). So recover the lane with the EXACT deleted
    # SWEEP regex over the reminder-stripped kept_oracle (scope 'you', matching the
    # deleted producer). add() dedups. CR 105 / 613.
    if _COLOR_CHANGE_MIRROR.search(kept_oracle):
        add("color_change", "you", "", "")
    # ADR-0027 β — toughness_combat BYTE-IDENTICAL kept mirror. TWO deleted producers
    # feed the key — the SWEEP combat-redirect ("assigns combat damage equal to its
    # toughness rather than its power" — Doran / Assault Formation / High Alert) and
    # the inline _DETECTORS value-payoff ("X is … toughness", "equal to … toughness"
    # — Geralf, Last March of the Ents). phase parses the Doran clause as an
    # AssignDamageFromToughness modification but project drops it on every multi-ability
    # face, so the structural `combat_damage_mod` category fires on only 21 commander-
    # legal (MISSES 129/133, no form for the 111 value-payoffs) and over-fires 81% on
    # "deal damage equal to its POWER" punches. So recover the lane with the EXACT OR of
    # the two deleted regexes over the reminder-stripped kept_oracle (scope 'you',
    # matching the deleted producers). The `(?! are each)` veto keeps set-base */*
    # (variable_pt) off. add() dedups. CR 510.1c / 122 / 604.3.
    if _TOUGHNESS_COMBAT_MIRROR.search(kept_oracle):
        add("toughness_combat", "you", "", "")
    # ADR-0027 β — ability_copy BYTE-IDENTICAL kept mirror. The "Ability copy" build-
    # around — copy an activated/triggered ability (Strionic, Lithoform, Rings, Bracers,
    # Kurkesh) or a "you may copy it" self-copy (Chancellor of Tales, Tawnos), plus the
    # "has all activated abilities of" granters (Necrotic Ooze, Experiment Kraj,
    # Mairsil, Myr Welder). phase emits ONE undifferentiated `spell_copy` category for
    # spell-copy AND ability-copy alike (no copy-target tag), so a `spell_copy` arm
    # over-fires 90% (303 vs 51 — Twincast/Reverberate) and STILL misses the granters
    # (grant_keyword); splitting needs a phase projection this batch can't make. So
    # recover the lane with the EXACT deleted SWEEP regex over the reminder-stripped
    # kept_oracle (scope 'you', matching the deleted producer). add() dedups. CR 706.10
    # / 113.2 / 706.2.
    if _ABILITY_COPY_MIRROR.search(kept_oracle):
        add("ability_copy", "you", "", "")
    # ADR-0027 t2b4-C — type_change kept detector. phase DROPS the protection ARGUMENT
    # (the subtype): "protection from Salamanders" survives only as a bare keyword with
    # no argument, and Gor Muldrak's own static is dropped entirely. So mirror the
    # _type_hoser_clause word detector (re `protection from (\w+)` gated against the
    # lowercase CREATURE_SUBTYPES vocab) over the joined oracle — clause-safe (full-text
    # == per-clause). LOWERCASED to match the regex path, which feeds it clause.lower().
    if _type_hoser_clause(kept_oracle.lower()):
        add("type_change", "you", "", "")
    # Cares-about floor lanes (synergy payoffs with no structural IR form) — reuse
    # the production floor Detector objects for the curated cares-about subset.
    for det in _FLOOR_DETECTORS:
        if det.key in _IR_FLOOR_LANES and det.pattern.search(kept_oracle):
            add(det.key, det.scope, "", "")

    # ADR-0027 fight_matters (face-level fallback): an Aftermath DFC whose "Fight" back
    # face phase never projects into the IR (Prepare // Fight) keeps the fight only on
    # the combined face oracle. Gated to faces with no structural fight effect/marker —
    # the project `_FIGHT_REF` dropped-static marker covers the single-face drops; this
    # is the back-face-not-projected residual. Reminder already stripped (kept_oracle).
    if not any(s.key == "fight_matters" for s in out) and _FIGHT_RAW.search(
        kept_oracle
    ):
        add("fight_matters", "you", "", "")

    # ADR-0027 token-subtype (face-level fallback): an Aftermath DFC whose "<Subtype>
    # token" back face phase never projects into the IR (Indulge // Excess) keeps the
    # maker only on the combined face oracle. One scan over kept_oracle per migrated
    # subtype, gated to subtypes not already opened by a structural maker/sac/ref.
    for tm in _TOKEN_SUBTYPE_RAW.finditer(kept_oracle):
        st = tm.group(1).lower()
        if st in _TOKEN_SUBTYPE_KEYS:
            tk, ts = _TOKEN_SUBTYPE_KEYS[st]
            if not any(s.key == tk for s in out):
                add(tk, ts, "", "")

    # Batch K — additional keyword-array lanes + type_line membership (clean
    # structured-field lookups; membership is low-confidence, as in the regex path).
    card_kws = {k.lower() for k in (card.get("keywords") or [])}
    for kw, pairs in _IR_KEYWORD_MAP.items():
        if kw in card_kws:
            for key, scope in pairs:
                add(key, scope, "", "")
    type_line = (card.get("type_line") or "").lower()
    # Membership signals (what the card IS): own card-type and own-subtype tribal.
    # Gated on include_membership, mirroring extract_signals — the deck-aggregate
    # path passes False for the 99 so every creature's race/type doesn't flood the
    # avenues (only the commander's membership opens a lane).
    if include_membership:
        if "artifact" in type_line:
            add("artifacts_matter", "you", "", "", "low")
        if "enchantment" in type_line:
            add("enchantments_matter", "you", "", "", "low")
        # Own-subtype tribal membership (a creature's own race) + named-token
        # tribes — a clean type_line / all_parts field-lookup. Class tribes
        # (Soldier/Cleric) open only behind a go-wide signal; race tribes open
        # unconditionally (CR 205.3).
        keys_now = {s.key for s in out}
        go_wide = bool(
            keys_now & {"creatures_matter", "attack_matters", "anthem_static"}
        )
        if "creature" in type_line and "—" in type_line:
            for tok in type_line.split("—", 1)[1].split():
                sub = tok.strip().lower()
                if sub in TRIBAL_SUBTYPES or (sub in CLASS_TRIBES and go_wide):
                    add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), "", "low")
        for part in card.get("all_parts") or []:
            if part.get("component") != "token":
                continue
            tl = (part.get("type_line") or "").lower()
            if "creature" not in tl or "—" not in tl:
                continue
            for tok in tl.split("—", 1)[1].split():
                sub = tok.strip().lower()
                if sub in CREATURE_SUBTYPES and sub != "human":
                    add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), "", "low")
    return out
