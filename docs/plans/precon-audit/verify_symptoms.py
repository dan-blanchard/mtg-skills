"""The card-level symptom checks of the 25-precon deckbuilder pass, over a run's
``misses.json`` files (``misses.py``'s output for the 25, the held-out 20 and
the fresh 10):

    python3 docs/plans/precon-audit/verify_symptoms.py ALL.json HELDOUT.json FRESH.json

Each check names the deck, the flaw a batch fixed, and the card-level fact the
fix shows on the run (a card kept, a card never added, a card added, a swap
count). The score is a yardstick; these are what a deckbuilder reading the
proposals asked for (docs/plans/backlog.md, "From the 25-precon deckbuilder
pass"). Exits 1 on any failure. Pure stdlib, no card data.
"""

import json
import pathlib
import sys

RAMP_TRIM = "ramp over"


def _check(kind, deck, *names, batch=""):
    return (kind, deck, names, batch)


# (kind, deck, names, batch). Kinds: kept — none of the names is a cut;
# no_trim — none is cut as surplus (role_over) or dead weight, an upgrade of it
# being the play-rate's call; never — none is an add; added — every name is an
# add; any_added — at least one is; swaps=N — exactly N swaps; no_ramp_trim —
# no role_over swap trims ramp.
CHECKS = [
    # batch 10 / 11 (the 25 and the held-out 20)
    _check("never", "AnimatedArmy_BLC", "Banner of Kinship", "Vanquisher's Banner",
           "Coat of Arms", "Door of Destinies", "Hammer of Nazahn", batch="8, 10"),
    _check("added", "AnimatedArmy_BLC", "Asceticism", batch="8"),
    _check("swaps=30", "EndlessPunishment_DSC", batch="5"),
    _check("never", "EndlessPunishment_DSC", "Guttersnipe", "Dragon Tempest",
           "Sword of Fire and Ice", batch="5, 7, 10"),
    _check("no_trim", "EndlessPunishment_DSC", "Blood Seeker", "Harsh Mentor",
           "Stormfist Crusader", batch="5"),
    _check("kept", "BloodRites_LCC", "Living Death", batch="3"),
    _check("kept", "EternalMight_DRC", "Living Death", batch="3"),
    _check("kept", "SquirreledAway_BLC", "Squirrel Nest", "Deep Forest Hermit", batch="4"),
    _check("any_added", "SquirreledAway_BLC", "Chatterfang, Squirrel General",
           "Deranged Hermit", "Drey Keeper", "Scurry Oak", "Squirrel Sovereign",
           "Chatter of the Squirrel", "Nut Collector", "Toski, Bearer of Secrets",
           batch="4"),
    _check("kept", "DesertBloom_OTC", "Oracle of Mul Daya", batch="4"),
    _check("kept", "AbzanArmor_TDC", "Zetalpa, Primal Dawn", batch="10"),
    _check("never", "EnduringEnchantments_CMM", "Hardened Scales",
           "Branching Evolution", batch="9"),
    _check("kept", "VelociRampTor_LCC",
           "Etali, Primal Conqueror // Etali, Primal Sickness", batch="11"),
    _check("no_trim", "DanceOfTheElements_ECC", "Cavalier of Thorns", batch="6"),
    _check("no_trim", "PeaceOffering_BLC", "Kwain, Itinerant Meddler", batch="6"),
    _check("swaps=30", "CounterIntelligence_EOC", batch="11"),
    _check("never", "CreativeEnergy_M3C", "Dragon Tempest", batch="7"),
    _check("added", "CallForBackup_MOC", "Doubling Season", "Hardened Scales",
           "Evolution Sage", "Ozolith, the Shattered Spire", batch="10"),
    _check("swaps=30", "ExplorersOfTheDeep_LCC", batch="11"),
    # batch 12 (the fresh 10 re-read, and the held-out decks it reached)
    _check("no_trim", "EldraziIncursion_M3C", "Talisman of Impulse",
           "Talisman of Resilience", "Talisman of Curiosity", "Awakening Zone",
           "Forsaken Monument", batch="12"),
    _check("cut", "EldraziIncursion_M3C", "Dreamstone Hedron", "Hedron Archive", batch="12"),
    _check("never", "EldraziIncursion_M3C",
           "Docent of Perfection // Final Iteration", batch="12"),
    _check("no_trim", "NecronDynasties_40K", "Illuminor Szeras", batch="12"),
    # Sai (an activated draw) and Danitha (phase types only her cost reduction)
    # stay admissible Humans by design.
    _check("never", "RidersOfRohan_LTC", "Puresteel Paladin", batch="12"),
    _check("never", "PartyTime_CLB", "Death Baron", "Kor Spiritdancer",
           "Starfield Mystic", batch="12"),
    _check("never", "DanceOfTheElements_ECC", "Rust Elemental", "Desecration Elemental",
           batch="12"),
    _check("never", "TrickyTerrain_M3C", "Cyberdrive Awakener", batch="12"),
    _check("never", "FamilyMatters_BLC", "Rising of the Day", batch="12"),
    _check("no_ramp_trim", "TemurRoar_TDC", batch="12"),
    _check("no_ramp_trim", "PrismariArtistry_SOC", batch="12"),
    _check("no_ramp_trim", "NecronDynasties_40K", batch="12"),
]


def main(paths):
    runs = {}
    for p in paths:
        runs.update(json.load(open(pathlib.Path(p))))
    failures = 0
    for kind, deck, names, batch in CHECKS:
        entry = runs.get(deck)
        if entry is None:
            print(f"SKIP  {deck}: not in these runs")
            continue
        swaps = entry["swaps"]
        cuts = {s[1] for s in swaps}
        adds = {s[2] for s in swaps}
        trimmed = {s[1] for s in swaps if s[0] in ("role_over", "dead_weight")}
        if kind == "kept":
            bad = [n for n in names if n in cuts]
            ok, detail = not bad, f"cut: {bad}"
        elif kind == "no_trim":
            bad = [n for n in names if n in trimmed]
            ok, detail = not bad, f"trimmed: {bad}"
        elif kind == "cut":
            bad = [n for n in names if n not in cuts]
            ok, detail = not bad, f"not cut: {bad}"
        elif kind == "never":
            bad = [n for n in names if n in adds]
            ok, detail = not bad, f"added: {bad}"
        elif kind == "added":
            bad = [n for n in names if n not in adds]
            ok, detail = not bad, f"missing: {bad}"
        elif kind == "any_added":
            hit = [n for n in names if n in adds]
            ok, detail = bool(hit), f"none of {list(names)} added"
        elif kind.startswith("swaps="):
            want = int(kind.split("=")[1])
            ok, detail = len(swaps) == want, f"{len(swaps)} swaps"
        elif kind == "no_ramp_trim":
            trims = [s[1] for s in swaps if s[0] == "role_over" and RAMP_TRIM in str(s[3])]
            ok, detail = not trims, f"ramp trims: {trims}"
        else:
            raise ValueError(kind)
        failures += not ok
        label = f"{kind} {', '.join(names)}" if names else kind
        print(f"{'PASS' if ok else 'FAIL'}  {deck:26} [batch {batch}] {label}"
              + ("" if ok else f" — {detail}"))
    print(f"{len(CHECKS) - failures} / {len(CHECKS)} checks pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
