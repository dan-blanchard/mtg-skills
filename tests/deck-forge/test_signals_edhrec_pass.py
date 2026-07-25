"""EDHREC blind-spot pass: recover zero-signal commanders whose archetype EDHREC
revealed AND whose own oracle text deterministically implies it (ADR-0009 — EDHREC
is a diagnostic, never a ranking input; detectors key off oracle text, not memory).

Single-clause widens vs full-text detectors (the extractor splits clauses on '.', so
trigger→payoff patterns spanning a sentence boundary need a full-text pass).

Every assertion runs the production ``extract_signals`` over a real card from
the committed snapshot (``mtg_utils.testkit``) — a synthetic no-``oracle_id`` dict
plus a hand-built ``Card``/``Ability``/``Effect`` shape can no longer reach the
crosswalk at all post-ADR-0039 (no concept tree resolves for it), so every fixture
here is a real card carrying the same grammatical shape the original synthetic
fixture modeled. Where the exact original commander (Gogo/Grond/Sensei/Veldrane/
Xantcha/Haktos/Aurelia/Alpharael) isn't yet snapshot-resident, a different real card
exhibiting the identical grammatical construction stands in; only Grond's specific
"you control an Army" word order had no snapshot substitute at all.
"""


from mtg_utils.testkit import test_signals


# ── clone via bare infinitive "become(s) a copy of" ──
def test_bare_infinitive_become_a_copy_fires_clone():
    # Oko, the Ringleader — "Oko becomes a copy of up to one target creature you
    # control until end of turn" is the bare-infinitive clone shape (same
    # construction as Gogo, Mysterious Mime, not yet snapshot-resident).
    assert "clone_makers" in {s.key for s in test_signals("Oko, the Ringleader")}


def test_token_copy_still_not_clone():
    # Helm of the Host: "create a token that's a copy of equipped creature" is
    # token_copy_makers, never clone_makers (a NEW object, not this one becoming a
    # copy).
    keys = {s.key for s in test_signals("Helm of the Host")}
    assert "token_copy_makers" in keys
    assert "clone_makers" not in keys


# ── Army tribal via "you control an Army" word order + vocab ──
def test_grond_army_tribal():
    sigs = test_signals("Grond, the Gatebreaker")
    assert any(s.key == "type_matters" and s.subject == "Army" for s in sigs)


# ── tribal type grant: "becomes a <Type> in addition to its other (creature) types" ──
def test_becomes_a_type_in_addition_tribal():
    # Clavileño, First of the Blessed — "target attacking Vampire that isn't a Demon
    # becomes a Demon in addition to its other types" is the same granted-type
    # construction as Sensei Golden-Tail's "becomes a Samurai in addition to its
    # other creature types" (not yet snapshot-resident).
    sigs = test_signals("Clavileño, First of the Blessed")
    assert any(s.key == "type_matters" and s.subject == "Demon" for s in sigs)


# ── landwalk = conditional evasion ──
def test_landwalk_is_evasion():
    # Cold-Eyed Selkie carries the plain Islandwalk keyword.
    assert "evasion_self" in {s.key for s in test_signals("Cold-Eyed Selkie")}


# ── forced-attack "attacks each combat if able" ──
def test_ruric_thar_forced_attack():
    assert "forced_attack" in {s.key for s in test_signals("Ruric Thar, the Unbowed")}


def test_zurgo_helmsmasher_forced_attack():
    assert "forced_attack" in {s.key for s in test_signals("Zurgo Helmsmasher")}


# ── self-blink (full text — exile-by-name + cross-sentence return) ──
def test_norin_self_blink():
    assert "self_blink" in {s.key for s in test_signals("Norin the Wary")}


def test_no_blink_without_exile_return():
    # a self-referential attack trigger that isn't an exile-and-return is not a
    # blink: Sophina attacks and investigates, no exile/return at all.
    assert "self_blink" not in {
        s.key for s in test_signals("Sophina, Spearsage Deserter")
    }


# ── beginning-of-combat single-target pump (full text, spans period) ──
def test_begin_combat_single_target_pump_is_combat_buff_engine():
    # Leinore, Autumn Sovereign — "At the beginning of combat on your turn, put a
    # +1/+1 counter on up to one target creature you control" is the same
    # begin-combat single-target pump shape as Aurelia, Exemplar of Justice (not
    # yet snapshot-resident).
    assert "combat_buff_engine" in {s.key for s in test_signals("Leinore, Autumn Sovereign")}


def test_static_anthem_not_combat_buff():
    # No combat trigger → not a combat-buff engine: Glorious Anthem is a bare static
    # pump, not a triggered ability.
    assert "combat_buff_engine" not in {s.key for s in test_signals("Glorious Anthem")}


# ── loot/rummage across a sentence boundary ──
def test_cross_sentence_loot_is_discard():
    # Katara, Waterbending Master — "you may draw a card for each experience
    # counter you have. If you do, discard a card." is a draw→discard outlet split
    # across a sentence boundary by the conditional "If you do,".
    assert "discard_makers" in {s.key for s in test_signals("Katara, Waterbending Master")}
