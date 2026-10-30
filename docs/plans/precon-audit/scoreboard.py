"""The audit's scoreboard from a misses.py run: swaps, guide cuts and adds matched,
near-misses, and the consensus cards matched (docs/plans/precon-audit-2026-10-18.md,
"The scoreboard"). Post-processing only: it reads the run's JSON, never tunes.

    cd mtg-utils && uv run python ../docs/plans/precon-audit/scoreboard.py MISSES ROOT
        [--json OUT.json] [--diff BASE.json] [--pairs] [--loose] [Name ...]

MISSES is the misses.json a misses.py run wrote; ROOT is the root that run read
(decks/<Name>/deck.json, articles/<Name>.md). Run it under the cache the run used
(MTG_SKILLS_CACHE_DIR): it reads the card pool, the signals index and the job
reads. Prints one row per precon and the TOTAL line; ``--json`` also writes the
numbers (and every near-miss pair) for a later ``--diff``; ``--diff BASE.json``
prints each precon's change from that earlier ``--json``; ``--pairs`` lists the
near-miss pairs; ``--loose`` scores the first, looser definition (below).

The columns:

- swaps; guide cuts the tuner cut, of the cuttable ones (in the deck, not a land
  or a commander); guide adds the tuner added, of the in-scope ones (misses.py's
  "out of scope" left out). The exact matches, as misses.py counts them.
- near-misses: tuner adds no guide names that stand in for a guide add the tuner
  missed in the same deck. Reported, not a gate. A pair holds when
  - JOB: both cards do the same template job by the tuner's own read
    (``upgrade_job(role_of(card, deck_mana=...))``: interaction, card draw,
    ramp, board wipe, protection), the same subtype of it (``job_subtype``: the
    kind of card, and what a removal or wipe answers and how, what a ramp card
    makes, what fires a draw engine, whom a protection card covers), and, when
    both carry non-generic signal idents, they share one; or
  - THEME: neither does a job, and the two share a strongest deck signal and
    one more non-generic ident. A card's strongest deck signals: of its
    non-generic idents (``GENERIC`` drops permanent ETB, the plain artifact and
    enchantment type keys, own keywords, self-ETB, activated abilities,
    creatures-matter and the template-role keys; ``COMMON`` the idents more than
    5% of the pool carry) that at least ``MIN_SHARE`` of the deck's own nonland
    cards carry, the ones the deck carries most against their base rate in the
    pool (ties all count).
  ``--loose`` is the first definition: a job pair by job alone; a theme pair when
  the add carries the guide card's ident that the most deck cards carry. The
  /rules-lawyer check (the audit doc, "The scoreboard") held 5 of 20 of its
  pairs, 13 of 20 of this one's.
  A tuner add first printed after the precon's latest guide date (the newest date
  in its Sources section, an update included; a month or year reads as its last
  day) is left out: no guide could name it. Each missed guide add pairs with at
  most one tuner add and each tuner add with at most one guide add (a maximum
  matching, so the count doesn't depend on order).
- consensus adds / cuts: the guide cards two or more of the precon's guides name
  (the rows' "Source #"), and how many of those the tuner matched — of the
  in-scope adds and the cuttable cuts.
"""
import argparse, calendar, collections, json, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from misses import norm  # noqa: E402

#: Signal keys too common to say what a deck is about (2026-10-29, w27's analysis):
#: a prefix match on the ident ``key|scope|subject``. The plain artifact and
#: enchantment type keys only: ``artifacts_matter|you|<subject>`` stays.
GENERIC = ("permanent_etb|", "self_etb_payload|", "activated_ability|", "creatures_matter|",
           "keyword_bodies|", "ramp|", "removal|", "exile_removal|", "mass_removal|",
           "card_draw_engine|", "board_protection|")
GENERIC_EXACT = {"artifacts_matter|you|", "enchantments_matter|you|"}
#: The fewest of the deck's nonland cards a signal needs to be a deck signal.
MIN_SHARE = 3
#: The tight rule's cap: an ident more than this share of the pool's
#: signal-carrying cards hold (graveyard_matters|you|, 10%) says no more about a
#: card than the generic keys do.
COMMON = 0.05
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTH_RE = "|".join(sorted({*calendar.month_name[1:], *calendar.month_abbr[1:], "Sept"}, key=len, reverse=True))


def generic(ident):
    return ident in GENERIC_EXACT or ident.startswith(GENERIC)


def section(md, header):
    sec = md.split(f"## {header}", 1)
    return sec[1].split("\n## ", 1)[0] if len(sec) > 1 else ""


def guide_counts(md, header):
    """norm(card) -> how many of the precon's guides name it in ``header``'s table
    (the distinct numbers of its rows' last cell, before any parenthesis)."""
    srcs = collections.defaultdict(set)
    for line in section(md, header).splitlines():
        if not line.startswith("|") or "---" in line or line.lower().startswith("| card"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        n = set(re.findall(r"\d+", cells[-1].split("(")[0])) or {"?"}
        for name in re.split(r"\s*(?:;|(?<!/)/(?!/))\s*", cells[0]):
            if name.strip():
                srcs[norm(name.strip())] |= n
    return {k: len(v) for k, v in srcs.items()}


def guide_date(md):
    """The newest date in the Sources section (URLs dropped), a partial date read
    as the last day of its month or year; ``None`` when it states none."""
    text = re.sub(r"https?://\S+", "", section(md, "Sources"))
    dates = []

    def last_day(y, m):
        return (int(y), int(m), calendar.monthrange(int(y), int(m))[1])

    def take(pattern, read):
        nonlocal text
        for m in re.finditer(pattern, text):
            if (d := read(*m.groups())) is not None:
                dates.append(d)
        text = re.sub(pattern, " ", text)  # a token read once, not again as a bare year

    take(r"\b(20\d\d)-(\d\d)/(\d\d)\b", lambda y, _m, m2: last_day(y, m2))  # 2023-11/12
    take(r"\b(20\d\d)-(\d\d)-(\d\d)\b", lambda y, m, d: (int(y), int(m), int(d)))
    take(r"\b(20\d\d)-(\d\d)\b", last_day)
    take(rf"(?<![A-Za-z])({_MONTH_RE})\.? (?:\d\d?, )?(20\d\d)(?!\d)", lambda mon, y: last_day(y, _MONTHS[mon[:3].lower()]))
    take(r"\b(20\d\d)\b", lambda y: (int(y), 12, 31))
    return "%04d-%02d-%02d" % max(dates) if dates else None


class Cards:
    """Per-card facts the near-miss rule reads, memoized: the pool record, its first
    printing's date, its signal idents (the signals index), its job and subtype."""

    def __init__(self):
        from mtg_utils._analysis.signals_index import load_signals_index
        from mtg_utils.bulk_loader import default_bulk_path
        from mtg_utils.card_pool import CardPool

        self.pool = CardPool.load(None)
        self.idx = load_signals_index(default_bulk_path()) or {}
        #: How many of the pool's cards carry each ident: a deck signal's base rate.
        self.freq = collections.Counter(i for ids in self.idx.values() for i in ids)
        self._jobs = {}

    def rec(self, name):
        return self.pool.by_name.get(name) or self.pool.by_name.get(name.split(" // ")[0])

    def key(self, name):
        rec = self.rec(name)
        return norm(rec["name"] if rec else name)

    def first(self, rec):
        # A reprint printing carries its set's date (MTGO's promo set dates every
        # card 2002-06-24), so only originals date a card, unless all are reprints.
        prs = self.pool.printings_by_oracle.get(rec.get("oracle_id") or "") or [rec]
        prs = [p for p in prs if not p.get("reprint")] or prs
        return min((p.get("released_at") or "9999") for p in prs)

    def idents(self, rec):
        return set(self.idx.get(rec.get("oracle_id"), ()) or ())

    def job(self, rec, deck, deck_mana):
        """(job, subtype): the tuner's job read in ``deck`` (the add's own
        ``upgrade_job(role_of(..., deck_mana=...))``), and its subtype."""
        from mtg_utils._analysis.roles import role_of
        from mtg_utils._tuner.issues import upgrade_job

        k = (rec["name"], deck)
        if k not in self._jobs:
            job = upgrade_job(role_of(rec, deck_mana=deck_mana), rec)
            self._jobs[k] = (job, job_subtype(rec, job, self.idents(rec)) if job else None)
        return self._jobs[k]


#: A removal answer's mode (``job_quality.removal``), grouped by what it does to
#: the permanent: exiled or put into its library (no death, no indestructible
#: escape), destroyed, sacrificed, damaged or shrunk, returned to hand.
_REMOVAL_MODE = {"exile": "exile", "tuck": "exile", "destroy": "destroy", "edict": "edict",
                 "damage": "damage", "fight": "damage", "shrink": "damage", "counters": "damage",
                 "bounce": "bounce"}


def job_subtype(rec, job, idents):
    """What a job card does within its job: the kind of card that does it (an
    instant or sorcery, a creature, a planeswalker, another permanent — its front
    face's type line), then what it does, read off the job read's own features and
    answers (``_analysis/job_quality``) and the card's signal keys, never its text.
    Two cards of one job are the same subtype when all of it agrees:

    - interaction: a removal answer's mode (``_REMOVAL_MODE``) and reach
      (creatures only, planeswalkers and battles with them; no creatures; or
      both) — the answer the removal read rates best; a counterspell; else other.
    - board wipe: whether it sweeps creatures, returns to hand rather than kills,
      deals or shrinks too little to kill everything, spares the caster's side or
      a class, sweeps again.
    - ramp: lands (put onto the battlefield, or an extra land drop), a mana
      creature, a mana rock, another permanent's mana each turn, else one-shot.
    - card draw: a wheel; an engine, by what fires it (opponents' plays, the
      deck's own, combat, an activation, fodder); else a one-shot.
    - protection: whom it covers (the team, one permanent, the player) and how
      (attack taxes and bans, a fog, a redirect, else its hard grants:
      hexproof-like, indestructible-like)."""
    from mtg_utils._analysis.job_quality import READS, removal
    from mtg_utils._analysis.lanes.removal_tutors import removal_edict_answers

    on = {k for k, v in (READS[job].features(rec) or {}).items() if v}
    types = set((rec.get("type_line") or "").split("//")[0].replace("—", " ").split())
    vehicle = ("spell" if types & {"Instant", "Sorcery"} else "creature" if "Creature" in types
               else "planeswalker" if "Planeswalker" in types else "permanent")
    return (vehicle, *_what(rec, job, idents, on, types, removal, removal_edict_answers))


def _what(rec, job, idents, on, types, removal, removal_edict_answers):
    if job == "interaction":
        # The answer the removal read rates best (``removal.features``' order:
        # breadth, then a hard mode), with the types that answer reaches.
        found = [(c, t, False) for c, t in removal_edict_answers(rec, "removal", soft=True)]
        found += [(c, t, True) for c, t in removal_edict_answers(rec, "edict")]
        answers = [(removal._breadth(t), removal._mode(c, edict=e), set(t)) for c, t, e in found
                   if (removal.tag_of(c.node) or "") not in removal.MASS_TAGS]
        if not answers:
            return ("counter",) if any(i.startswith("counter_control|") for i in idents) else ("other",)
        _b, mode, reach = max(answers, key=lambda a: (a[0], a[1] in ("exile", "destroy", "tuck", "edict")))
        if "Any" in reach:
            reach |= {"Creature", "Planeswalker"}
        wide = "Permanent" in reach or bool(reach & {"Artifact", "Enchantment", "Land"})
        span = "any" if wide and ("Creature" in reach or "Permanent" in reach) else "noncreature" if wide else "creature"
        return (_REMOVAL_MODE.get(mode, mode), span)
    if job == "board_wipe":
        return tuple(sorted(on & {"creatures", "bounce", "small", "one_sided", "spares", "repeat"}))
    if job == "ramp":
        if "land" in on:
            return ("land",)
        if "extra_land" in on:
            return ("extra land drop",)
        if "dork" in on:
            return ("dork",)
        if "per_turn" in on:  # a mana rock, else another permanent's mana each turn
            return ("rock",) if "Artifact" in types and "Creature" not in types else ("engine",)
        return ("one-shot",)
    if job == "card_draw":
        if "wheel" in on:
            return ("wheel",)
        if "engine" in on or any(i.startswith("card_draw_engine|") for i in idents):
            fuel = [f for f in ("opp_fuel", "self_fuel", "combat", "act_engine", "fodder") if f in on]
            return ("engine", fuel[0] if fuel else "other")
        return ("one-shot",)
    if job == "protection":
        scope = "team" if on & {"team", "team_narrow", "wipe_proof"} else "player" if "player_only" in on else "one"
        how = ("pillow" if on & {"pillow_tax", "pillow_other"} else "fog" if "fog" in on
               else "redirect" if "redirect_wide" in on
               else "+".join(sorted(on & {"target_proof", "indestructible"})) or "soft")
        return (scope, how)
    return ()


def matching(edges):
    """Maximum bipartite matching over ``edges`` (left -> sorted rights)."""
    owner = {}

    def augment(u, seen):
        for v in edges[u]:
            if v in seen:
                continue
            seen.add(v)
            if v not in owner or augment(owner[v], seen):
                owner[v] = u
                return True
        return False

    for u in sorted(edges):
        augment(u, set())
    return {u: v for v, u in owner.items()}


def score_deck(cards, root, name, entry, tight=True):
    from mtg_utils.deck_cli import acquire_for_cli

    md = (root / "articles" / f"{name}.md").read_text()
    deck_path = root / "decks" / name / "deck.json"
    hd = acquire_for_cli(deck_path, None)
    dm = hd.deck_mana
    deck = json.loads(deck_path.read_text())
    n_adds, n_cuts = guide_counts(md, "Recommended adds"), guide_counts(md, "Recommended cuts")
    gdate = guide_date(md)

    cuttable = [(g, w) for g, w in entry["cuts"] if w != "land / commander"]
    in_scope = [(g, w) for g, w in entry["adds"] if w != "out of scope"]
    row = {
        "swaps": len(entry["swaps"]),
        "cuts": sum(w == "cut" for _g, w in cuttable), "cuttable": len(cuttable),
        "adds": sum(w == "added" for _g, w in in_scope), "in_scope": len(in_scope),
        "cons_cuts": sum(w == "cut" for g, w in cuttable if n_cuts.get(norm(g), 0) >= 2),
        "cons_cuttable": sum(n_cuts.get(norm(g), 0) >= 2 for g, _w in cuttable),
        "cons_adds": sum(w == "added" for g, w in in_scope if n_adds.get(norm(g), 0) >= 2),
        "cons_in_scope": sum(n_adds.get(norm(g), 0) >= 2 for g, _w in in_scope),
        "guide_date": gdate,
    }

    # The deck's own nonland cards' idents, for each signal's share.
    share = collections.Counter()
    for c in deck["cards"]:
        rec = cards.rec(c["name"])
        if rec and "Land" not in (rec.get("type_line") or "").split("//")[0]:
            share.update(i for i in cards.idents(rec) if not generic(i))

    def specific(rec):
        """The card's non-generic idents: what it does beyond its template job."""
        return {i for i in cards.idents(rec) if not generic(i)}

    def strongest(rec):
        """The card's strongest deck signals: of its non-generic idents that at
        least MIN_SHARE of the deck's nonland cards carry (and, tight, no more
        than COMMON of the pool), the ones the deck carries most — tight, against
        the ident's base rate in the pool; loose, by count. Ties all count."""
        sig = {i: (share[i] / cards.freq[i] if tight else share[i]) for i in specific(rec)
               if share[i] >= MIN_SHARE and (not tight or cards.freq[i] <= COMMON * len(cards.idx))}
        best = max(sig.values(), default=None)
        return {i for i, n in sig.items() if n == best}

    guide_keys = {cards.key(g) for g, _w in entry["adds"]}
    missed = {}  # guide name -> (job, subtype, strongest deck signals, non-generic idents)
    for g, w in in_scope:
        rec = cards.rec(g)
        if w != "added" and rec is not None:
            job, sub = cards.job(rec, name, dm)
            missed[rec["name"]] = (job, sub, strongest(rec) if job is None else set(), specific(rec))
    late, edges, why = [], {}, {}
    for _issue, _cut, add, _reason in entry["swaps"]:
        rec = cards.rec(add)
        if rec is None or cards.key(add) in guide_keys or rec["name"] in edges:
            continue
        if gdate and cards.first(rec) > gdate:
            late.append(rec["name"])
            continue
        job, sub = cards.job(rec, name, dm)
        mine = specific(rec)
        # Tight, the add's own strongest deck signals; loose, every ident it carries.
        ids = strongest(rec) if tight else cards.idents(rec)
        hits = []
        for g, (gjob, gsub, top, theirs) in missed.items():
            shared = mine & theirs
            if job is not None and gjob == job and (not tight or (
                    sub == gsub and (shared or not mine or not theirs))):
                why[(rec["name"], g)] = f"job {job}" + (f" {list(sub)}" if tight else "") + (
                    f" sharing {' '.join(sorted(shared))}" if tight and shared else "")
            elif job is None and gjob is None and ids & top and (not tight or len(shared) >= 2):
                why[(rec["name"], g)] = "theme " + " ".join(sorted(ids & top))
            else:
                continue
            hits.append(g)
        if hits:
            edges[rec["name"]] = sorted(hits)
    pairs = matching(edges)
    row["near"] = len(pairs)
    row["near_job"] = sum(why[(a, g)].startswith("job") for a, g in pairs.items())
    row["near_theme"] = row["near"] - row["near_job"]
    row["late"] = late
    row["pairs"] = [[a, g, why[(a, g)]] for a, g in sorted(pairs.items())]
    return row


FIELDS = ("swaps", "cuts", "adds", "near", "near_job", "near_theme", "cons_cuts", "cons_adds")


def line(r):
    return (f"swaps {r['swaps']} | guide cuts {r['cuts']} of {r['cuttable']} | guide adds {r['adds']} of {r['in_scope']}"
            f" | near-misses {r['near']} (job {r['near_job']}, theme {r['near_theme']})"
            f" | consensus adds {r['cons_adds']} of {r['cons_in_scope']} | consensus cuts {r['cons_cuts']} of {r['cons_cuttable']}")


def total(rows):
    keys = FIELDS + ("cuttable", "in_scope", "cons_cuttable", "cons_in_scope")
    return {k: sum(r[k] for r in rows.values()) for k in keys}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("misses", type=pathlib.Path)
    ap.add_argument("root", type=pathlib.Path)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--json", type=pathlib.Path, help="write the scoreboard here")
    ap.add_argument("--diff", type=pathlib.Path, help="an earlier --json to diff against")
    ap.add_argument("--pairs", action="store_true", help="list the near-miss pairs")
    ap.add_argument("--loose", action="store_true", help="the first definition: a job pair by job alone, a theme signal by deck count alone")
    a = ap.parse_args()
    misses = json.loads(a.misses.read_text())
    cards = Cards()
    rows = {n: score_deck(cards, a.root, n, misses[n], tight=not a.loose)
            for n in sorted(a.names or misses)}
    print(f"| precon | {' | '.join(FIELDS)} | late adds left out |")
    print("|---" * (len(FIELDS) + 2) + "|")
    for n, r in rows.items():
        print(f"| {n} | {' | '.join(str(r[k]) for k in FIELDS)} | {len(r['late'])} |")
    tot = total(rows)
    print("\nTOTAL", line(tot))
    if a.pairs:
        for n, r in rows.items():
            for add, g, why in r["pairs"]:
                print(f"  {n}: {add}  ~  {g}  ({why})")
    if a.json:
        a.json.write_text(json.dumps({"total": tot, "decks": rows}, indent=1))
    if a.diff:
        base = json.loads(a.diff.read_text())
        print(f"\nchanges from {a.diff}:")
        for n, r in rows.items():
            b = base["decks"].get(n)
            if b is None:
                print(f"  {n}: new"); continue
            d = {k: r[k] - b[k] for k in FIELDS if r[k] != b[k]}
            if d:
                print(f"  {n}: " + ", ".join(f"{k} {v:+d}" for k, v in d.items()))
            gone = {(x[0], x[1]) for x in b["pairs"]} - {(x[0], x[1]) for x in r["pairs"]}
            new = {(x[0], x[1]) for x in r["pairs"]} - {(x[0], x[1]) for x in b["pairs"]}
            for p in sorted(new):
                print(f"      + {p[0]} ~ {p[1]}")
            for p in sorted(gone):
                print(f"      - {p[0]} ~ {p[1]}")
        print("  TOTAL: " + ", ".join(f"{k} {tot[k] - base['total'][k]:+d}" for k in FIELDS))


if __name__ == "__main__":
    main()
