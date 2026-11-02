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
# add; any_added — at least one is; swaps=N — exactly N swaps; swaps>=N; no_ramp_trim —
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
    # A dry Merfolk page cost Explorers four swaps (26); the fallback gives
    # them back. 29 since batch 13: Ripples of Potential keeps its slot, the
    # protection page holding nothing that reads as well.
    _check("swaps>=29", "ExplorersOfTheDeep_LCC", batch="11, 13"),
    # batch 12 (the fresh 10 re-read, and the held-out decks it reached)
    # The flat band trimmed nine ramp pieces here; the curve-aware band trims
    # two (Chalice and a Talisman, over by 2 at 17-19). The theme's Spawn maker
    # and its doubler are the pieces a deckbuilder keeps.
    _check("no_trim", "EldraziIncursion_M3C", "Awakening Zone", batch="12, 14"),
    _check("cut", "EldraziIncursion_M3C", "Dreamstone Hedron", "Hedron Archive", batch="12"),
    _check("never", "EldraziIncursion_M3C",
           "Docent of Perfection // Final Iteration", batch="12"),
    _check("no_trim", "NecronDynasties_40K", "Illuminor Szeras", batch="12"),
    # Danitha (phase types only her cost reduction) stays an admissible Human.
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
    # batch 13 (the batch-12 re-read of the 25, the held-out 20 and the fresh 10)
    _check("any_added", "TrickyTerrain_M3C", "Roaming Throne", "Coat of Arms",
           "Lord of the Unreal", "Galerider Sliver", "Herald's Horn", "Vanquisher's Banner",
           "Imperious Perfect", "Elvish Warmaster", "Kindred Discovery", batch="13"),
    _check("never", "TrickyTerrain_M3C", "Talrand, Sky Summoner", "Aqueous Form",
           "Crashing Drawbridge", "Blade of Selves", batch="13"),
    _check("never", "DeathToll_DSC", "Fellwar Stone", batch="13"),
    _check("never", "JeskaiStriker_TDC", "Wayfarer's Bauble", batch="13"),
    # batch 14 (two deckbuilder reviews of every proposal in the three sets)
    _check("identity", "*", batch="14"),
    _check("swaps>=29", "TemurRoar_TDC", batch="14"),
    # Inspiring Call and Intangible Virtue were flagged dead by a reviewer, but
    # Animated Army, Tinker Time and Deep Clue Sea each hold six or more counter
    # or creature-token makers: fed. Living Energy holds fewer.
    _check("never", "LivingEnergy_DRC", "Inspiring Call", batch="14"),
    _check("never", "VirtueAndValor_WOC", "Brass Squire", batch="14"),
    _check("never", "DesertBloom_OTC", "Grinding Station", batch="14"),
    _check("never", "LoreholdSpirit_SOC", "Skirk Prospector", batch="14"),
    _check("never", "EndlessPunishment_DSC", "Scourge of Valkas", batch="14"),
    _check("never", "RidersOfRohan_LTC", "Sai, Master Thopterist", batch="14"),
    # Icon of Ancestry (Sliver Swarm) is a fill's cut where the deck's only
    # off-lane fringe cards are its choose-a-type cards: not pinned.
    # Vanquisher's Banner (Cavalry Charge) goes to another Knight payoff: not pinned.
    # Merfolk Mistbinder to Pyre of Heroes and Juniper Order Ranger to a combo
    # piece both keep the need the cut supplied: the reviewers' call, not a
    # structural flaw, so they are not pinned.
    _check("never", "SquirreledAway_BLC", "Oketra's Monument", batch="14"),
    # the second reviewers' pass over the final proposals
    _check("never", "AnimatedArmy_BLC", "Heroes' Podium", batch="14"),
    _check("never", "JeskaiStriker_TDC", "Open the Armory", batch="14"),
    _check("never", "MultiverseReforged_FRC", "Waste Not", "Dark Ritual", batch="14"),
    _check("never", "DeadlyDisguise_MKC", "Lotus Petal", batch="14"),
    _check("never", "LoreholdSpirit_SOC", "Simian Spirit Guide", batch="14"),
    _check("never", "LivingEnergy_DRC", "Talisman of Creativity", batch="14"),
    _check("never", "ExplorersOfTheDeep_LCC", "Pongify", batch="14"),
    # batch 15 (the closing reviews of the committed tree)
    _check("kept", "QuickDraw_OTC", "Niv-Mizzet, Parun", batch="15"),
    _check("never", "EldraziIncursion_M3C", "Inverter of Truth", batch="15"),
    _check("never", "MostWanted_OTC", "Monument to Endurance", batch="15"),
    _check("never", "BlameGame_MKC", "Vandalblast", batch="15"),
    _check("never", "DesertBloom_OTC", "Vandalblast", batch="15"),
    _check("never", "EndlessPunishment_DSC", "Vandalblast", batch="15"),
    _check("never", "TimeyWimey_WHO", "Vandalblast", batch="15"),
    _check("never", "FaeDominion_WOC", "Dark Ritual", batch="15"),
    _check("never", "QuickDraw_OTC", "Jeska's Will", batch="15"),
    _check("never", "RevenantRecon_MKC", "Cabal Ritual", batch="15"),
    _check("never", "FamilyMatters_BLC", "Ripples of Potential", batch="15"),
    _check("kept", "BloodRites_LCC", "Village Rites", batch="15"),
    # An upgrade keeps the broad need its cut supplies: Cast Out, an enchantment
    # Anikthea returns, never goes to a non-enchantment.
    _check("no_pair", "EnduringEnchantments_CMM", "Cast Out -> Assassin's Trophy", batch="15"),
    # A shared-type sweeper is no tribe payoff: Endemic Plague never joins a Vampire deck.
    _check("never", "BloodRites_LCC", "Endemic Plague", batch="15"),
    # A planeswalker's ultimate is not its job: Sorin is no interaction card to upgrade.
    _check("no_pair", "BloodRites_LCC", "Sorin, Lord of Innistrad -> Feed the Swarm", batch="15"),
    # A lone poison giver is no closer: one infect flier in a deck with no poison.
    _check("never", "CounterIntelligence_EOC", "Viral Drake", batch="15"),
    # Kinship pays off the card's own types: no Elf Shaman for a Squirrel deck.
    _check("never", "SquirreledAway_BLC", "Wolf-Skull Shaman", batch="16"),
    # A 50-life cost is no removal: Aetherflux Reservoir doesn't upgrade Duplicant.
    _check("no_pair", "LivingEnergy_DRC", "Duplicant -> Aetherflux Reservoir", batch="16"),
    # A sweep sparing the deck's Auras is one-sided there: Winds of Rath stays.
    _check("no_pair", "VirtueAndValor_WOC", "Winds of Rath -> Martial Coup", batch="16"),
    # Inspirit's charge counters: Titan Forge isn't traded for a mana rock.
    _check("no_pair", "CounterIntelligence_EOC", "Titan Forge -> Talisman of Creativity", batch="16"),
    _check("no_pair", "CounterIntelligence_EOC", "Fumigate -> Aetherize", batch="16b"),
    _check("never", "MostWanted_OTC", "Dawn-Blessed Pennant", batch="16b"),
    _check("never", "CavalryCharge_MOC", "Gleaming Overseer", "Chocobo Knights", batch="16b"),
    _check("never", "SquirreledAway_BLC", "Squirrel Squatters", batch="16b"),
    _check("never", "MostWanted_OTC", "Sanguine Bond", "Vito, Thorn of the Dusk Rose", batch="16c"),
    # A lane_ok fill takes a non-supplier from either fallback pool before a supplier.
    _check("no_pair", "VelociRampTor_LCC", "Descendants' Path -> Esper Sentinel", batch="16d"),
    # A punisher ("may sacrifice … if they don't") is no edict; a one-shot spell no job engine.
    _check("no_pair", "BloodRites_LCC", "Patron of the Vein -> Braids, Arisen Nightmare", batch="16e"),
    _check("no_pair", "CavalryCharge_MOC", "Vanquisher's Banner -> And They Shall Know No Fear", batch="16e"),
    # A commander resource need under the built floor is still kept.
    _check("no_pair", "EternalMight_DRC", "Archfiend of Ifnir -> Counterspell", batch="16g"),
    # A chosen-card-type sweep (artifact or enchantment) is no creature sweeper.
    _check("no_pair", "TinkerTime_MOC", "Junk Winder -> Season of Gathering", batch="16h"),
    _check("no_trim", "EldraziIncursion_M3C", "Forsaken Monument", batch="14"),
    _check("no_trim", "TrickyTerrain_M3C", "Mana Reflection", batch="14"),
]


def main(paths):
    runs = {}
    for p in paths:
        runs.update(json.load(open(pathlib.Path(p))))
    failures = 0
    for kind, deck, names, batch in CHECKS:
        if kind == "identity":
            # Every add inside its deck's color identity (recorded by misses.py).
            bad = {d: e["identity_violations"] for d, e in runs.items() if e.get("identity_violations")}
            ok = not bad
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {'every deck':26} [batch {batch}] identity"
                  + ("" if ok else f" — {bad}"))
            continue
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
        elif kind == "no_pair":
            # "Cut -> Add": that exact swap is never proposed.
            pairs = {f"{s[1]} -> {s[2]}" for s in swaps}
            bad = [n for n in names if n in pairs]
            ok, detail = not bad, f"proposed: {bad}"
        elif kind == "never":
            bad = [n for n in names if n in adds]
            ok, detail = not bad, f"added: {bad}"
        elif kind == "added":
            bad = [n for n in names if n not in adds]
            ok, detail = not bad, f"missing: {bad}"
        elif kind == "any_added":
            hit = [n for n in names if n in adds]
            ok, detail = bool(hit), f"none of {list(names)} added"
        elif kind.startswith("swaps>="):
            want = int(kind.split(">=")[1])
            ok, detail = len(swaps) >= want, f"{len(swaps)} swaps"
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
