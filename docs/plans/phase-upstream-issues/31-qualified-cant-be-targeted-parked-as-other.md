# Fiendslayer Paladin, Dense Foliage, Tomik and others: "can't be the target of [some] spells or abilities" parked as `mode: {Other: text}`

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Fiendslayer Paladin** (M14):
> First strike (This creature deals combat damage before creatures without first strike.)
> Lifelink (Damage dealt by this creature also causes you to gain that much life.)
> This creature can't be the target of black or red spells your opponents control.

**Dense Foliage** (6ED):
> Creatures can't be the targets of spells.

**Tomik, Distinguished Advokist** (WAR):
> Flying
> Lands on the battlefield and land cards in graveyards can't be the targets of spells or abilities your opponents control.
> Your opponents can't play land cards from graveyards.

**Autumn's Veil** (M12):
> Spells you control can't be countered by blue or black spells this turn, and creatures you control can't be the targets of blue or black spells this turn.

## Observed at v0.131.0

Each static is a `mode: {"Other": "<the line>"}` with only `affected` typed. Fiendslayer Paladin (marked `confirmed_misparse: "dropped_qualifier"`):

```json
{"mode": {"Other": "~ can't be the target of black or red spells your opponents control."}, "affected": {"type": "SelfRef"}}
```

Dense Foliage (marked `confirmed_misparse: "wrong_object"`):

```json
{"mode": {"Other": "Creatures can't be the targets of spells."}, "affected": {"type": "Typed", "type_filters": ["Creature"]}}
```

Tomik (no `affected` at all):

```json
{"mode": {"Other": "Lands on the battlefield and land cards in graveyards can't be the targets of spells or abilities your opponents control."}}
```

The same `Other` static on these cards (all legal in Commander; the restriction each names in parentheses):

- **Anti-Magic Aura** (enchanted creature; spells), **Spectral Shield** (enchanted creature; spells; its "+0/+2" is a separate typed `Continuous` static, but the `Other` text repeats the whole line), **Artifact Ward** (enchanted creature; abilities from artifact sources)
- **Bartel Runeaxe**, **Tetsuo Umezawa** (Aura spells)
- **Gaea's Revenge** (nongreen spells or abilities from nongreen sources), **Thrun, Breaker of Silence** (the same, controlled by opponents)
- **Karplusan Strider** (blue or black spells)
- **Mercenary Informer** (black), **Rebel Informer** and **Raiding Party** (white), **Suq'Ata Firewalker** (red): spells, or abilities from sources, of that color
- **Spellbane Centaur** (creatures you control; blue spells or abilities from blue sources)
- **Shanna, Sisay's Legacy** (abilities your opponents control)
- **Species 8472** (abilities from artifact sources your opponents control)
- **Lurker** (spells, unless it attacked or blocked this turn)
- **Wall of Shadows** (spells or abilities that can target only Walls)

At v0.118.0 these were typed, though lossily: most as `mode: CantBeTargeted` with the qualifier dropped (Dense Foliage and Spellbane Centaur also with `affected: SelfRef`), and Fiendslayer Paladin, Shanna, Thrun and Tomik as a `Continuous` `AddKeyword Hexproof` on `SelfRef`.

The same restriction granted until end of turn by a spell is parked as `unrecognized_clause_head`: Autumn's Veil ("Spells you control can't be countered by blue or black spells this turn, and creatures you control can't be the targets of blue or black spells", marked `missing_effect`) and Display of Dominance's second mode ("Permanents you control can't be the targets of blue or black spells your opponents control", marked `extra_effect`). At v0.118.0 both were a `GenericEffect` granting `Shroud` (Autumn's Veil) or `Hexproof` (Display of Dominance).

## Expected

The `CantBeTargeted` static mode phase already has (`{"CantBeTargeted": {"who": "Opponents"}}` for Canopy Cover, `{"who": "AllPlayers"}` for Ground Seal), widened with a filter on the targeting source: its kind (spell, ability, or both), its color or type (black or red; nongreen; artifact; Aura), and its controller. For Tomik, `affected` covering lands on the battlefield and land cards in graveyards; for Lurker, the attacked-or-blocked condition. The spell forms as a `GenericEffect` carrying the same static until end of turn.

## Why it matters

An `Other` mode carries no meaning a consumer can read: these permanents are as targetable as any other, and the spells protect nothing. 20 legal cards carry the static at v0.131.0; v0.118.0 gave each of them but Species 8472 (not in that card-data) at least an untargetability mode or keyword.
