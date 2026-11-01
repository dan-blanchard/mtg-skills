"""``signal_specs.avenue_spec_for``: the avenue a deck signal opens.

A subject on a key that is not a subject key refines one lane, and every subject
resolves to the key's one ``SPECS`` entry. Where that entry's serve reads the
key's own idents it decides which subjects are the theme's, so a card opens the
avenue exactly when the serve counts it. Real cards via ``mtg_utils.testkit``
(ADR-0056).
"""

from mtg_utils._analysis.ranking import score_candidate
from mtg_utils._analysis.signal_specs import avenue_spec_for, spec_for
from mtg_utils.testkit import test_card, test_signals


def _card(name):
    """The real record, its trees memo seeded (``test_signals``) so the serve's
    ident arm reads the card's real idents."""
    test_signals(name)
    return test_card(name)


def _opened(name):
    """The avenue labels *name*'s own signals open."""
    return {spec.label for sig in test_signals(name) if (spec := avenue_spec_for(sig))}


def _served(name, label):
    """Whether the spec labelled *label* (any of *name*'s resolvable signals)
    serves *name*."""
    card = _card(name)
    specs = {spec.label: spec for sig in test_signals(name) if (spec := spec_for(sig))}
    return specs[label].serve.matches(card)


def test_lightning_greaves_opens_and_serves_the_equipment_keyword_grant_avenue():
    # "Equipped creature has shroud and haste": only subject-bearing grants
    # (aura_equip_kw_grant|you|haste, |shroud). The avenue it opens counts it.
    sigs = {(s.key, s.subject) for s in test_signals("Lightning Greaves") if s.subject}
    assert ("aura_equip_kw_grant", "haste") in sigs
    label = "Aura/Equipment keyword grant"
    assert label in _opened("Lightning Greaves")
    assert _served("Lightning Greaves", label)


def test_rafiq_opens_and_serves_the_team_keyword_grant_avenue():
    # A lone attacker gains double strike: team_buff|you|double strike only.
    assert "Team keyword grants" in _opened("Rafiq of the Many")
    assert _served("Rafiq of the Many", "Team keyword grants")


def test_impulse_draw_does_not_open_cast_from_exile():
    # cast_from_exile|you|impulse: the Cast-from-exile serve leaves impulse draw
    # out (its own avenue), so the signal opens nothing there and serves nothing.
    sigs = [
        s
        for s in test_signals("Act on Impulse")
        if s.key == "cast_from_exile" and s.subject
    ]
    assert sigs
    assert all(avenue_spec_for(s) is None for s in sigs)
    assert "Cast-from-exile" not in _opened("Act on Impulse")
    spec = spec_for(sigs[0])
    assert not spec.serve.matches(_card("Act on Impulse"))
    # The tuner classifies a card by the avenues its deck's signals open
    # (``score_candidate``): impulse cards do not read as cast-from-exile cards.
    served = score_candidate(
        _card("Act on Impulse"), active_signals=test_signals("Act on Impulse")
    )["served"]
    assert "Cast-from-exile" not in served


def test_a_partial_evasion_body_does_not_open_the_evasion_avenue():
    # "Can't be blocked by Walls" (evasion_self|you|partial): a restriction
    # that still leaves blockers, which the evasion serve leaves out.
    subjects = {
        s.subject for s in test_signals("Juggernaut") if s.key == "evasion_self"
    }
    assert subjects == {"partial"}
    assert "Evasion / unblockable" not in _opened("Juggernaut")
    assert not _served("Juggernaut", "Evasion / unblockable")


def test_a_menace_body_opens_the_evasion_avenue_it_serves():
    # Menace is an evasion ability (CR 509.1b; 702.111b: "can't be blocked
    # except by two or more creatures"), one of the keywords the evasion serve
    # names: a menace body opens the avenue and counts toward it, both or neither.
    menace = [
        s
        for s in test_signals("Boggart Brute")
        if (s.key, s.subject) == ("evasion_self", "menace")
    ]
    assert menace
    assert avenue_spec_for(menace[0]) is not None
    assert _served("Boggart Brute", "Evasion / unblockable")


def test_a_fuel_serve_opens_for_every_subject():
    # Creature recursion's serve is the loop FUEL, not the recursion engines, so
    # it reads no creature_recursion ident: every destination (the subject)
    # opens it.
    sigs = [
        s
        for s in test_signals("Alesha, Who Smiles at Death")
        if s.key == "creature_recursion"
    ]
    assert sigs
    assert all(s.subject for s in sigs)
    assert {avenue_spec_for(s).label for s in sigs} == {"Creature recursion"}


def test_one_role_table_feeds_every_subject_set():
    """``signal_keys.SUBJECT_ROLES`` is the one ``(key, subject)`` role table:
    the membership, page-only and doer sets are its views (a page-only doer is a
    doer too), and a ``key|scope|*`` wildcard counts every subject but a
    membership one."""
    from mtg_utils._analysis import signal_keys as sk

    roles = sk.SUBJECT_ROLES
    assert {
        ks for ks, r in roles.items() if r is sk.SubjectRole.MEMBERSHIP
    } == sk.MEMBERSHIP_SUBJECTS
    assert sk.PAGE_ONLY_SUBJECTS <= sk.DOER_SUBJECTS
    assert not sk.MEMBERSHIP_SUBJECTS & sk.DOER_SUBJECTS
    assert set(roles) == sk.DOER_SUBJECTS | sk.MEMBERSHIP_SUBJECTS
    assert sk.wildcard_counts("artifacts_matter", sk.ARTIFACT_MEMBER) is False
    assert sk.wildcard_counts("artifacts_matter", "token") is True
    assert sk.wildcard_counts("artifacts_matter", "") is True


def test_a_preset_wildcard_leaves_a_membership_subject_out():
    """A preset's ``key|scope|*`` reads the role table as a serve's does: Sol
    Ring IS an artifact (``artifacts_matter|you|member``), no artifacts payoff."""
    from mtg_utils.theme_presets import Preset

    preset = Preset(
        name="artifact payoffs (test)",
        description="",
        signal_idents=("artifacts_matter|you|*",),
    )
    test_signals("Sol Ring")
    assert "artifacts_matter|you|member" in {
        f"{s.key}|{s.scope}|{s.subject}" for s in test_signals("Sol Ring")
    }
    assert not preset.matches(test_card("Sol Ring"))
