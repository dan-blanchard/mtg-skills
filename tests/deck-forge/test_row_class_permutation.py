"""Rate v2 S1 — the same-row slot permutation (design note 2.6, approved).

After the total-order sort, within each (color_widening, 0.25-depth-
bucket) stratum, each row class permutes the slots of the cards it OWNS
(a card's owner = the lexicographically first pair_id among its matched
rows), ONE PARALLEL PASS against the pre-pass snapshot. Keys: cantrip
rider (provenance-attributed) first, then mana value ascending, then
name. Invariants (CI, from the gate-b cycle-6 fix):

* zero-class candidates keep their exact index;
* any candidate pair with NO shared class keeps relative order — the
  anti-chaining assertion (sequential-pass designs fail it via a
  shared-member ferry; the parallel-pass design cannot).
"""

from __future__ import annotations

from mtg_utils._deck_forge.ranking import apply_row_class_permutation


def _r(name, pairs, depth=4.0, cmc=2, *, rider=False, widening=0):
    return {
        "card": {"name": name, "cmc": cmc},
        "score": {
            "color_widening": widening,
            "synergy_score": depth,
            "pair_score": 0.0,
            "cmc": cmc,
            "pairs": [{"pair": p} for p in pairs],
        },
        "_test_rider": rider,
    }


def _rider_fn(r):
    return r.get("_test_rider", False)


def test_rider_outranks_riderless_within_class():
    scored = [
        _r("Bare Pump", ["row_a"], rider=False),
        _r("Cantrip Pump", ["row_a"], rider=True),
    ]
    out = apply_row_class_permutation(scored, rider_fn=_rider_fn)
    assert [r["card"]["name"] for r in out] == ["Cantrip Pump", "Bare Pump"]


def test_zero_class_candidates_keep_exact_index():
    scored = [
        _r("Classless One", [], rider=True),
        _r("B Member", ["row_a"], rider=False),
        _r("Classless Two", []),
        _r("A Member", ["row_a"], rider=True),
    ]
    out = apply_row_class_permutation(scored, rider_fn=_rider_fn)
    names = [r["card"]["name"] for r in out]
    assert names[0] == "Classless One"
    assert names[2] == "Classless Two"
    # class members swapped among slots 1 and 3
    assert names[1] == "A Member"
    assert names[3] == "B Member"


def test_anti_chaining_no_shared_class_pairs_never_reorder():
    # The cycle-6 trace: Y (class A only), X (A and B), Z (B only), all in
    # one bucket. X is OWNED by class A (lexicographic first), so class B
    # treats X as fixed — Y and Z (no shared class) must keep relative
    # order no matter the keys.
    scored = [
        _r("Y", ["row_a"], rider=False, cmc=5),
        _r("X", ["row_a", "row_b"], rider=True, cmc=1),
        _r("Z", ["row_b"], rider=True, cmc=1),
    ]
    out = apply_row_class_permutation(scored, rider_fn=_rider_fn)
    names = [r["card"]["name"] for r in out]
    assert names.index("Y") < names.index("Z"), names

    # And generally: every no-shared-class pair preserves order.
    def classes(r):
        return {p["pair"] for p in r["score"]["pairs"]}

    before = [r["card"]["name"] for r in scored]
    by_name = {r["card"]["name"]: r for r in scored}
    for a in before:
        for b in before:
            if before.index(a) < before.index(b) and not (
                classes(by_name[a]) & classes(by_name[b])
            ):
                assert names.index(a) < names.index(b), (a, b, names)


def test_bucket_boundary_blocks_permutation():
    # Depth 4.0 vs 3.7 are different 0.25 buckets — no swap even with a
    # rider advantage.
    scored = [
        _r("High Riderless", ["row_a"], depth=4.0, rider=False),
        _r("Low Rider", ["row_a"], depth=3.7, rider=True),
    ]
    out = apply_row_class_permutation(scored, rider_fn=_rider_fn)
    assert [r["card"]["name"] for r in out] == ["High Riderless", "Low Rider"]


def test_color_widening_strata_never_mix():
    scored = [
        _r("Widening Riderless", ["row_a"], rider=False, widening=1),
        _r("Plain Rider", ["row_a"], rider=True, widening=0),
    ]
    out = apply_row_class_permutation(scored, rider_fn=_rider_fn)
    assert [r["card"]["name"] for r in out] == [
        "Widening Riderless",
        "Plain Rider",
    ]


def test_deterministic_name_final_key():
    scored = [
        _r("Zeta", ["row_a"], cmc=2),
        _r("Alpha", ["row_a"], cmc=2),
    ]
    out = apply_row_class_permutation(scored, rider_fn=_rider_fn)
    assert [r["card"]["name"] for r in out] == ["Alpha", "Zeta"]


def test_pass_is_default_off_in_rank_candidates():
    # The flag ships OFF until the S1 slice measurement accepts (2.6).
    import inspect

    from mtg_utils._deck_forge.ranking import rank_candidates

    sig = inspect.signature(rank_candidates)
    assert sig.parameters["row_class_permutation"].default is False
