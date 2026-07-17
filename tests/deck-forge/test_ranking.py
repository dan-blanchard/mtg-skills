"""Tests for transparent multi-axis candidate ranking (D6)."""

from mtg_utils._deck_forge.ranking import (
    _ability_is_payoff,
    _clause_role,
    _clause_role_regex,
    rank_candidates,
    score_candidate,
)
from mtg_utils._deck_forge.signals import Signal
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Trigger
from mtg_utils.testkit import test_card_ir


# ── Depth-over-breadth synergy (synergy_score) ───────────────────────────────
# The unweighted lane-count rewards generically-splashy cards: a card whose one
# property (makes a token) is wanted by six lanes outscores the deck's actual
# payoff. synergy_score clusters served lanes by the oracle clause that matched
# them (one property = one credit) and weights payoff > enabler > structural, so
# a real death-payoff beats a token-equipment even when both touch many lanes.
def _sig(key: str, scope: str = "you") -> Signal:
    return Signal(key, scope, "", "", "cmd")


# An aristocrats deck's active lanes (subset of the real Joel+Ellie signals).
_ARI_SIGNALS = [
    _sig("death_matters", "you"),
    _sig("death_matters", "opponents"),
    _sig("death_matters", "any"),
    _sig("sacrifice_outlets", "you"),
    _sig("lifeloss_matters", "opponents"),
    _sig("lifegain_matters", "you"),
    _sig("creature_etb", "you"),
    _sig("creatures_matter", "you"),
    _sig("voltron_matters", "you"),
    _sig("artifacts_matter", "you"),
    _sig("token_doubling", "you"),
    _sig("edict_makers", "each"),
    _sig("attack_matters", "you"),
    _sig("attack_matters", "any"),
]
_ARI_FOCUS = {
    "viable": {"Aristocrats", "Combat", "Artifacts"},
    "emerging": {"Voltron / equipment & auras"},
    "stranded": {"Edicts / forced sacrifice", "Token doubling"},
}

# Real card props (full oracle text — fixtures must embed real cards).
_BASTION = {
    "name": "Bastion of Remembrance",
    "type_line": "Enchantment",
    "cmc": 3.0,
    "oracle_text": (
        "When this enchantment enters, create a 1/1 white Human Soldier "
        "creature token.\nWhenever a creature you control dies, each opponent "
        "loses 1 life and you gain 1 life."
    ),
    "prices": {"usd": "1.50"},
}
_BLOOD_ARTIST = {
    "name": "Blood Artist",
    "type_line": "Creature — Vampire",
    "cmc": 2.0,
    "oracle_text": (
        "Whenever this creature or another creature dies, target player loses "
        "1 life and you gain 1 life."
    ),
    "prices": {"usd": "2.00"},
}
_MIDNIGHT_REAPER = {
    "name": "Midnight Reaper",
    "type_line": "Creature — Zombie Knight",
    "cmc": 3.0,
    "oracle_text": (
        "Whenever a nontoken creature you control dies, this creature deals 1 "
        "damage to you and you draw a card."
    ),
    "prices": {"usd": "2.00"},
}
_ELVEN_BOW = {
    "name": "Elven Bow",
    "type_line": "Artifact — Equipment",
    "cmc": 1.0,
    "oracle_text": (
        "When this Equipment enters, you may pay {2}. If you do, create a 1/1 "
        "green Elf Warrior creature token, then attach this Equipment to it.\n"
        "Equipped creature gets +1/+2 and has reach.\nEquip {3}"
    ),
    "prices": {"usd": "0.20"},
}
_FLAYER_HUSK = {
    "name": "Flayer Husk",
    "type_line": "Artifact — Equipment",
    "cmc": 1.0,
    "oracle_text": (
        "Living weapon (When this Equipment enters, create a 0/0 black "
        "Phyrexian Germ creature token, then attach this to it.)\nEquipped "
        "creature gets +1/+1.\nEquip {2}"
    ),
    "prices": {"usd": "0.30"},
}


def _score(card: dict) -> float:
    return score_candidate(card, active_signals=_ARI_SIGNALS, focus_sets=_ARI_FOCUS)[
        "synergy_score"
    ]


def test_real_payoff_outscores_token_equipment():
    # The crux: Bastion (count 10) and Elven Bow (count 10) tie on raw count, but
    # Bastion is a genuine death payoff and Elven Bow is all incidental.
    assert _score(_BASTION) > _score(_ELVEN_BOW)
    assert _score(_BLOOD_ARTIST) > _score(_ELVEN_BOW)
    assert _score(_MIDNIGHT_REAPER) > _score(_FLAYER_HUSK)


def test_ranking_puts_payoffs_above_box_tickers():
    ranked = rank_candidates(
        [_ELVEN_BOW, _FLAYER_HUSK, _BASTION, _BLOOD_ARTIST, _MIDNIGHT_REAPER],
        active_signals=_ARI_SIGNALS,
        focus_sets=_ARI_FOCUS,
    )
    names = [r["card"]["name"] for r in ranked]
    # Every real payoff ranks above both box-tickers.
    last_payoff = max(
        names.index(n)
        for n in ("Bastion of Remembrance", "Blood Artist", "Midnight Reaper")
    )
    first_box = min(names.index(n) for n in ("Elven Bow", "Flayer Husk"))
    assert last_payoff < first_box, names


def test_synergy_score_is_deck_relative():
    # A pure token-maker keeps full weight when Go-wide IS the plan, but is
    # discounted when tokens are only an incidental/stranded lane — the fix is
    # deck-relative, not "tokens are always bad".
    token_maker = {
        "name": "Goblin Wave",
        "type_line": "Sorcery",
        "cmc": 4.0,
        "oracle_text": "Create three 1/1 red Goblin creature tokens.",
        "prices": {"usd": "0.25"},
    }
    sigs = [_sig("creatures_matter", "you"), _sig("creature_etb", "you")]
    go_wide = score_candidate(
        token_maker,
        active_signals=sigs,
        focus_sets={"viable": {"Go wide"}, "emerging": set(), "stranded": set()},
    )["synergy_score"]
    incidental = score_candidate(
        token_maker,
        active_signals=sigs,
        focus_sets={"viable": set(), "emerging": set(), "stranded": {"Go wide"}},
    )["synergy_score"]
    assert go_wide > incidental


# ── Quality frontier: activated payoffs + unmet tribal gates ─────────────────
_WALKING_BALLISTA = {
    "name": "Walking Ballista",
    "type_line": "Artifact Creature — Construct",
    "cmc": 0.0,
    "oracle_text": (
        "This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 "
        "counter on this creature.\nRemove a +1/+1 counter from this creature: "
        "It deals 1 damage to any target."
    ),
    "prices": {"usd": "7.50"},
}
_HIRED_CLAW = {
    "name": "Hired Claw",
    "type_line": "Creature — Lizard Mercenary",
    "cmc": 1.0,
    "oracle_text": (
        "Whenever you attack with one or more Lizards, this creature deals 1 "
        "damage to target opponent.\n{1}{R}: Put a +1/+1 counter on this "
        "creature. Activate only if an opponent lost life this turn and only "
        "once each turn."
    ),
    "prices": {"usd": "0.70"},
}
_BURN_SIGNALS = [
    _sig("direct_damage", "you"),
    _sig("attack_matters", "you"),
    _sig("attack_matters", "any"),
    _sig("plus_one_matters", "you"),
]
_BURN_FOCUS = {
    "viable": {"Burn / pingers", "Combat"},
    "emerging": set(),
    "stranded": set(),
}


def test_activated_ability_payoff_is_recognized():
    # Walking Ballista's "Remove a +1/+1 counter: deals 1 damage" is a payoff even
    # though it has no trigger word (an activated cost + a board-impacting reward).
    sc = score_candidate(
        _WALKING_BALLISTA, active_signals=_BURN_SIGNALS, focus_sets=_BURN_FOCUS
    )
    assert any(c["role"] == "payoff" for c in sc["clusters"]), sc["clusters"]


def test_unmet_tribal_gate_downweights_payoff():
    # Hired Claw's "attack with one or more Lizards" payoff is near-dead in a deck
    # with no Lizards, but full in a Lizard deck — deck-relative, not a blanket cut.
    no_liz = score_candidate(
        _HIRED_CLAW,
        active_signals=_BURN_SIGNALS,
        focus_sets=_BURN_FOCUS,
        deck_tribes=frozenset({"human", "zombie"}),
    )["synergy_score"]
    with_liz = score_candidate(
        _HIRED_CLAW,
        active_signals=_BURN_SIGNALS,
        focus_sets=_BURN_FOCUS,
        deck_tribes=frozenset({"lizard"}),
    )["synergy_score"]
    assert no_liz < with_liz


def test_real_activated_pinger_beats_dead_tribal_gate():
    # In a deck with no Lizards, a real activated pinger (Walking Ballista) outscores
    # the Lizard-gated one (Hired Claw) — the residual the user flagged.
    tribes = frozenset({"human", "vampire"})
    wb = score_candidate(
        _WALKING_BALLISTA,
        active_signals=_BURN_SIGNALS,
        focus_sets=_BURN_FOCUS,
        deck_tribes=tribes,
    )["synergy_score"]
    hc = score_candidate(
        _HIRED_CLAW,
        active_signals=_BURN_SIGNALS,
        focus_sets=_BURN_FOCUS,
        deck_tribes=tribes,
    )["synergy_score"]
    assert wb > hc


# ── Same-role stacking decay + lane-breadth credit (2026-07-16 study) ────────
# The linear cluster sum let TEXT WALLS win discovery: every activated/triggered
# clause reads role=payoff, clusters summed linearly, so a four-payoff-clause
# value engine the Krenko crowd never plays (Fires of Mount Doom) outranked the
# on-plan staples (Siege-Gang Lieutenant, an EDHREC Krenko synergy target, sat
# at rank ~120). Two mechanism fixes, validated on the 20-commander EDHREC
# study (recall@100 4.3%→6.2%, recall@250 7.1%→9.3%, median target rank
# 3741→3345):
#   1. Same-role cluster contributions decay geometrically (sorted desc,
#      x0.35^i): a card fills ONE slot, so its best property defines its job —
#      a fourth payoff clause is gravy, not 4x the card.
#   2. Each cluster earns a lane-breadth credit: one physical property the deck
#      wants for K distinct reasons beats a property wanted for one, in
#      proportion to the deck's own interest (0.25 x Σ prominence of each lane
#      beyond the cluster's best).
_KRENKO_SIGNALS = [
    _sig("type_matters", "you"),
    _sig("typed_spellcast", "you"),
    _sig("token_maker", "you"),
    _sig("creatures_matter", "you"),
    _sig("creature_etb", "you"),
    _sig("death_matters", "any"),
    _sig("sacrifice_outlets", "you"),
    _sig("direct_damage", "you"),
    _sig("activated_ability", "you"),
    _sig("legends_matter", "you"),
    _sig("impulse_top_play", "you"),
    _sig("cost_reduction", "you"),
    _sig("attack_matters", "you"),
    _sig("removal", "you"),
]
# The tribal signals carry the Goblin subject (per-subject dynamic specs).
for _i, _s in enumerate(_KRENKO_SIGNALS):
    if _s.key in ("type_matters", "typed_spellcast", "token_maker"):
        _KRENKO_SIGNALS[_i] = Signal(_s.key, _s.scope, "Goblin", "", "cmd")
# The real Krenko average-deck focus tiers (study harness, 2026-07-16).
_KRENKO_FOCUS = {
    "viable": {
        "Goblin tribal",
        "Activated-ability engine",
        "Burn / pingers",
        "Legends matter",
    },
    "emerging": set(),
    "stranded": set(),
}
# Real cards (full oracle text). Siege-Gang Lieutenant: ONE payoff clause
# serving seven lanes (sac-outlet pinger tribal piece) + a wide token clause.
# Fires of Mount Doom: four stacked narrow payoff clauses (the text wall).
_SIEGE_GANG_LT = {
    "name": "Siege-Gang Lieutenant",
    "type_line": "Creature — Goblin",
    "cmc": 4.0,
    "oracle_text": (
        "Lieutenant — At the beginning of combat on your turn, if you control "
        "your commander, create two 1/1 red Goblin creature tokens. Those "
        "tokens gain haste until end of turn.\n{2}, Sacrifice a Goblin: This "
        "creature deals 1 damage to any target."
    ),
    "prices": {"usd": "2.88"},
}
_FIRES_OF_MOUNT_DOOM = {
    "name": "Fires of Mount Doom",
    "type_line": "Legendary Enchantment",
    "cmc": 3.0,
    "oracle_text": (
        "When Fires of Mount Doom enters, it deals 2 damage to target creature "
        "an opponent controls. Destroy all Equipment attached to that "
        "creature.\n{2}{R}: Exile the top card of your library. You may play "
        "that card this turn. When you play a card this way, Fires of Mount "
        "Doom deals 2 damage to each player."
    ),
    "prices": {"usd": "1.88"},
}
_EMPTY_THE_WARRENS = {
    "name": "Empty the Warrens",
    "type_line": "Sorcery",
    "cmc": 4.0,
    "oracle_text": (
        "Create two 1/1 red Goblin creature tokens.\nStorm (When you cast "
        "this spell, copy it for each spell cast before it this turn.)"
    ),
    "prices": {"usd": "0.19"},
}
_ASHNODS_ALTAR = {
    "name": "Ashnod's Altar",
    "type_line": "Artifact",
    "cmc": 3.0,
    "oracle_text": "Sacrifice a creature: Add {C}{C}.",
    "prices": {"usd": "14.38"},
}


def _krenko_sc(card: dict) -> dict:
    return score_candidate(
        card, active_signals=_KRENKO_SIGNALS, focus_sets=_KRENKO_FOCUS
    )


def test_on_plan_breadth_beats_stacked_payoff_wall():
    # The study's flagship flip: the EDHREC Krenko staple must outrank the
    # text wall (previously Fires ranked #1 in the whole 7k pool, the staple
    # #120). Depth in the deck's real plan > stacked one-dimensional value.
    assert (
        _krenko_sc(_SIEGE_GANG_LT)["synergy_score"]
        > _krenko_sc(_FIRES_OF_MOUNT_DOOM)["synergy_score"]
    )


def test_same_role_stacking_decays_geometrically():
    # Fires's three top payoff clusters must contribute sub-linearly. With
    # x0.35^i decay the payoff rows sum below max x 1/(1-0.35) ≈ 1.54 (plus
    # a small breadth term); the linear sum was 3x max.
    sc = _krenko_sc(_FIRES_OF_MOUNT_DOOM)
    payoff = [c["weight"] for c in sc["clusters"] if c["role"] == "payoff"]
    assert payoff, sc["clusters"]
    assert sum(payoff) < max(payoff) * 1.6, sc["clusters"]


def test_wide_cluster_earns_prominence_weighted_breadth():
    # Empty the Warrens' one token clause serves 8 lanes (Goblin tribal viable
    # + 7 default-prominence lanes): its cluster row must carry the breadth
    # credit above the bare enabler weight (1.0), and the wide token clause
    # must beat the narrow sac-outlet clause (Ashnod's Altar) decisively.
    sc = _krenko_sc(_EMPTY_THE_WARRENS)
    widest = max(sc["clusters"], key=lambda c: len(c["lanes"]))
    assert len(widest["lanes"]) >= 8, sc["clusters"]
    assert widest["weight"] > 1.0, sc["clusters"]
    assert sc["synergy_score"] > _krenko_sc(_ASHNODS_ALTAR)["synergy_score"]


ETB = Signal("creature_etb", "you", "", "", "cmd")
LIFE = Signal("lifegain_matters", "you", "", "", "cmd")

TOKEN_MAKER = {
    "name": "Token Maker",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "oracle_text": "Create three 1/1 Soldier creature tokens.",
    "prices": {"usd": "0.50"},
}
DUAL_PURPOSE = {
    "name": "Lifegain Tokens",
    "type_line": "Sorcery",
    "cmc": 4.0,
    "oracle_text": "Create two 1/1 creature tokens. You gain 3 life.",
    "prices": {"usd": "2.00"},
}
NO_LISTING = {
    "name": "Rare Token Maker",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "oracle_text": "Create four 1/1 creature tokens.",
    "prices": {},
}


def test_synergy_fit_counts_served_signals():
    score = score_candidate(TOKEN_MAKER, active_signals=[ETB, LIFE])
    assert score["synergy_fit"] == 1
    assert any("Creatures entering" in s for s in score["served"])


def test_dual_purpose_card_serves_two_signals():
    score = score_candidate(DUAL_PURPOSE, active_signals=[ETB, LIFE])
    assert score["synergy_fit"] == 2


def test_score_exposes_price_and_cmc():
    score = score_candidate(TOKEN_MAKER, active_signals=[ETB])
    assert score["cmc"] == 3.0
    assert score["price"] == 0.5
    assert score_candidate(NO_LISTING, active_signals=[ETB])["price"] is None


def test_avenues_contribute_to_synergy_fit():
    avenues = [
        {"label": "Land creatures", "search": {"oracle": "becomes a .*creature"}}
    ]
    manland = {
        "name": "Manland",
        "type_line": "Land",
        "cmc": 0.0,
        "oracle_text": "Mishra's Factory becomes a 2/2 Assembly-Worker creature.",
        "prices": {"usd": "0.50"},
    }
    score = score_candidate(manland, active_signals=[], avenues=avenues)
    assert score["synergy_fit"] == 1
    assert "Land creatures" in score["served"]


def test_serving_a_signal_and_an_avenue_stacks():
    avenues = [{"label": "Land creatures", "search": {"oracle": "land creature"}}]
    # Serves creature_etb (makes a creature token) AND the land-creature avenue.
    card = {
        "name": "Land Token Maker",
        "type_line": "Sorcery",
        "cmc": 3.0,
        "oracle_text": "Create a 1/1 green land creature token.",
        "prices": {"usd": "1.00"},
    }
    score = score_candidate(card, active_signals=[ETB], avenues=avenues)
    assert score["synergy_fit"] == 2


def test_avenue_card_type_constraint_excludes_wrong_types():
    # A "creature-lands" avenue (type=Land) must not credit a clone that merely
    # says "becomes a ... creature" but isn't a land (the Silent Hallcreeper bug).
    avenues = [
        {
            "label": "Creature-lands",
            "search": {"card_type": "Land", "oracle": "becomes a .*creature"},
        }
    ]
    manland = {
        "name": "Mishra's Factory",
        "type_line": "Land",
        "cmc": 0.0,
        "oracle_text": "{T}: Add {C}.\n{1}: This land becomes a 2/2 Assembly-Worker artifact creature until end of turn. It's still a land.\n{T}: Target Assembly-Worker creature gets +1/+1 until end of turn.",
        "prices": {"usd": "1"},
    }
    clone = {
        "name": "Silent Hallcreeper",
        "type_line": "Enchantment Creature — Horror",
        "cmc": 5.0,
        "oracle_text": "This creature can't be blocked.\nWhenever this creature deals combat damage to a player, choose one that hasn't been chosen —\n• Put two +1/+1 counters on this creature.\n• Draw a card.\n• This creature becomes a copy of another target creature you control.",
        "prices": {"usd": "1"},
    }
    assert (
        "Creature-lands"
        in score_candidate(manland, active_signals=[], avenues=avenues)["served"]
    )
    assert (
        "Creature-lands"
        not in score_candidate(clone, active_signals=[], avenues=avenues)["served"]
    )


def test_rank_sorts_by_synergy_then_price_with_no_listing_last():
    ranked = rank_candidates(
        [TOKEN_MAKER, DUAL_PURPOSE, NO_LISTING], active_signals=[ETB, LIFE]
    )
    names = [r["card"]["name"] for r in ranked]
    # DUAL_PURPOSE (synergy 2) first; then the two synergy-1 cards by price asc,
    # with the no-listing card last.
    assert names[0] == "Lifegain Tokens"
    assert names.index("Token Maker") < names.index("Rare Token Maker")


# ── Partner color widening (ADR-0019) ────────────────────────────────────────
_ENTERS_AVENUE = [{"label": "Enters", "search": {"oracle": "enters"}}]


def _partner(name: str, identity: list[str], oracle: str) -> dict:
    return {
        "name": name,
        "type_line": "Legendary Creature — Human",
        "cmc": 3.0,
        "color_identity": identity,
        "oracle_text": oracle,
        "prices": {"usd": "1.00"},
    }


def test_color_widening_zero_without_a_base():
    # Off the partner avenue (no base), the axis is inert: 0 for everyone, and the
    # legacy synergy→price→cmc order is unchanged.
    score = score_candidate(TOKEN_MAKER, active_signals=[ETB])
    assert score["color_widening"] == 0


def test_partner_widening_dominates_synergy():
    # Mono-blue deck. A four-color opener with ZERO synergy must outrank a perfect-
    # synergy same-color partner — colors before synergy, strictly (ADR-0019).
    wide = _partner("Wide Opener", ["W", "B", "R", "G"], "")  # +4 colors, no synergy
    on_color = _partner("On-Color", ["U"], "a creature enters")  # +0 colors, synergy 1
    ranked = rank_candidates(
        [on_color, wide],
        active_signals=[],
        avenues=_ENTERS_AVENUE,
        widening_base="U",
    )
    assert [r["card"]["name"] for r in ranked] == ["Wide Opener", "On-Color"]
    assert ranked[0]["score"]["color_widening"] == 4
    assert ranked[1]["score"]["color_widening"] == 0
    assert ranked[1]["score"]["synergy_fit"] == 1  # higher synergy, still ranked below


def test_partner_widening_synergy_breaks_ties_within_a_widening_tier():
    # Two partners each widen by exactly one color; synergy then orders them.
    adds_g = _partner("Adds G + synergy", ["G"], "whenever a creature enters")
    adds_w = _partner("Adds W only", ["W"], "")
    ranked = rank_candidates(
        [adds_w, adds_g],
        active_signals=[],
        avenues=_ENTERS_AVENUE,
        widening_base="U",
    )
    assert [r["card"]["name"] for r in ranked] == ["Adds G + synergy", "Adds W only"]
    assert {r["score"]["color_widening"] for r in ranked} == {1}


# ── Card IR role clustering (ADR-0027, A3) ───────────────────────────────────
# The synthetic dict fixtures above carry no oracle_id, so they exercise the
# regex fallback (``ir is None``). These tests exercise the IR path by injecting a
# constructed ``Card`` IR via ``_ir_resolved`` — the same join ``rank_candidates``
# does by oracle_id at runtime. They assert the structured classifier mirrors the
# regex tiers where both agree, and is strictly MORE accurate where the regex
# over-/under-fires (the ADR's "adjudicated correctness, not regex parity").


def _ir(*abilities: Ability) -> Card:
    """A single-face Card IR carrying the given abilities."""
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=abilities),))


def _your_creatures(**kw) -> Filter:
    return Filter(card_types=("Creature",), controller="you", **kw)


def test_ir_triggered_reward_is_a_payoff():
    # Blood-Artist shape: a death trigger draining each opponent — a reward.
    drain = Ability(
        kind="triggered",
        trigger=Trigger(event="dies"),
        effects=(
            Effect(category="lose_life", scope="any", raw="target player loses 1 life"),
            Effect(category="gain_life", scope="any", raw="you gain 1 life"),
        ),
    )
    assert _ability_is_payoff(drain) is True


def test_ir_token_maker_is_an_enabler_not_a_payoff():
    # CR 111.1: creating a creature token is generative fodder, not a reward.
    etb_token = Ability(
        kind="triggered",
        trigger=Trigger(event="etb"),
        effects=(
            Effect(
                category="make_token",
                subject=Filter(card_types=("Creature",), subtypes=("Soldier",)),
                raw="create a 1/1 Soldier creature token",
            ),
        ),
    )
    assert _ability_is_payoff(etb_token) is False


def test_ir_activated_strong_reward_is_a_payoff_but_self_pump_is_not():
    # Walking Ballista: "Remove a counter: deal 1 damage" — activated strong reward.
    ping = Ability(
        kind="activated",
        cost="removecounter",
        effects=(Effect(category="damage", raw="deals 1 damage to any target"),),
    )
    # A bare self-pump activation ("{4}: put a +1/+1 counter on this") is NOT a payoff.
    self_pump = Ability(
        kind="activated",
        cost="mana",
        effects=(Effect(category="place_counter", counter_kind="p1p1", raw="..."),),
    )
    assert _ability_is_payoff(ping) is True
    assert _ability_is_payoff(self_pump) is False


def test_ir_static_team_anthem_is_a_payoff_across_ability_kinds():
    # A static anthem over YOUR creatures, and the same buff off a planeswalker
    # loyalty (activated) ability — both are anthem payoffs (Sorin's +1).
    static_anthem = Ability(
        kind="static",
        effects=(
            Effect(
                category="pump",
                subject=_your_creatures(),
                raw="Creatures you control get +1/+1.",
            ),
        ),
    )
    loyalty_anthem = Ability(
        kind="activated",
        effects=(
            Effect(
                category="grant_keyword",
                counter_kind="lifelink",
                subject=_your_creatures(),
                raw="creatures you control get +1/+0 and gain lifelink",
            ),
        ),
    )
    # An EQUIPMENT buff ("Equipped creature gets …", controller 'any') is NOT an
    # anthem — it pumps one creature, so it stays an enabler.
    equip_buff = Ability(
        kind="static",
        effects=(
            Effect(
                category="pump",
                subject=Filter(card_types=("Creature",), controller="any"),
                raw="Equipped creature gets +1/+2.",
            ),
        ),
    )
    assert _ability_is_payoff(static_anthem) is True
    assert _ability_is_payoff(loyalty_anthem) is True
    assert _ability_is_payoff(equip_buff) is False


def test_ir_clause_role_credits_tribal_anthem_the_regex_misses():
    # "Sliver creatures you control have vigilance" — a real typed anthem the
    # regex (_STATIC_PAYOFF_RE, which needs "creatures you control get/…") misses.
    clause = "Sliver creatures you control have vigilance."
    sliver_anthem = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="grant_keyword",
                    counter_kind="vigilance",
                    subject=_your_creatures(subtypes=("Sliver",)),
                    raw=clause,
                ),
            ),
        )
    )
    payoff_raws = ["sliver creatures you control have vigilance"]
    assert _clause_role_regex(clause) == "enabler"  # regex under-fires
    assert _clause_role(clause, sliver_anthem, payoff_raws) == "payoff"


def test_ir_path_does_not_scramble_ranked_order():
    # The injected IR path must keep the aristocrats order the regex path produces
    # (payoffs above box-tickers) — equivalent-or-better, never scrambled. Both IRs
    # are the REAL projected Card IR (Bastion: etb make_token + dies drain payoff;
    # Elven Bow: etb make_token + equip pump enabler), injected via _ir_resolved
    # exactly as rank_candidates joins by oracle_id at runtime.
    bastion = score_candidate(
        _BASTION,
        active_signals=_ARI_SIGNALS,
        focus_sets=_ARI_FOCUS,
        _ir_resolved=(test_card_ir("Bastion of Remembrance"),),
    )["synergy_score"]
    elven_bow = score_candidate(
        _ELVEN_BOW,
        active_signals=_ARI_SIGNALS,
        focus_sets=_ARI_FOCUS,
        _ir_resolved=(test_card_ir("Elven Bow"),),
    )["synergy_score"]
    # The real death-payoff outscores the incidental token-equipment (the crux),
    # exactly as the regex path does — the IR clusters by structured ability.
    #
    # ADR-0039 step 5.5 fix: the ACTUAL mechanism was Effect.raw, not
    # Effect.scope (ranking.py never reads .scope at all — grep-verified).
    # Bastion's "dies" trigger chains a LoseLife effect (direct child of the
    # trigger's execute wrapper) with a GainLife effect reached via
    # sub_ability; NEITHER node carries its own `description` — only the
    # owning TRIGGER does ("Whenever a creature you control dies, each
    # opponent loses 1 life and you gain 1 life.") — so both effects'
    # Effect.raw was empty, `ranking._ir_payoff_raws` skipped them (it only
    # appends a NON-empty raw), and the "dies" clause fell back to "enabler"
    # instead of "payoff". _card_ir.compat._unit_raw now threads the owning
    # ability/trigger's own description down to any effect whose own node
    # carries none, mirroring project.py's `_collect_effects(node,
    # default_raw)` recursion exactly. (Effect.scope for this shape was ALSO
    # tightened to match project.py's own "any" default for an unresolved
    # lose_life/gain_life recipient — a real but separately-measured fidelity
    # gap that turned out not to move this particular test either way, since
    # ranking.py is scope-blind.)
    assert bastion > elven_bow


def test_bastion_drain_raw_and_scope_match_legacy_shape():
    # Field-level pin for the ADR-0039 step 5.5 fix (see the test above for
    # the consumer-visible symptom this closes). Bastion of Remembrance's
    # "dies" trigger: "Whenever a creature you control dies, each opponent
    # loses 1 life and you gain 1 life." — a LoseLife effect chained to a
    # GainLife via sub_ability, neither carrying its own description.
    ir = test_card_ir("Bastion of Remembrance")
    dies_effects = [
        e
        for ab in ir.all_abilities()
        if ab.trigger is not None and ab.trigger.event == "dies"
        for e in ab.effects
    ]
    cats = {e.category for e in dies_effects}
    assert cats == {"lose_life", "gain_life"}
    # raw: threaded from the owning trigger's own description (project.py's
    # _collect_effects(node, default_raw) precedent) — no longer empty.
    for e in dies_effects:
        assert e.raw
        assert "each opponent loses 1 life" in e.raw
    # scope: matches project.py's OWN read for this exact shape ("any" on
    # both sides — project.py never resolves the opponent/you direction for
    # a LoseLife/GainLife pair chained this way either; verified against
    # test_legacy_card_ir("Bastion of Remembrance") separately), never the
    # generic crosswalk "you" default a bare drain/punisher payoff would
    # otherwise get.
    assert {e.scope for e in dies_effects} == {"any"}
