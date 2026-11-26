<!-- Status: FILED 2026-11-25 as https://github.com/phase-rs/phase/issues/11360 (against phase v0.133.0, commit 890e1ee; verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Type filters carry subtype strings no card has ("Each Vehicle", "Eldrazi Spawn", "Historic", "Double-faced Artifact"), so they match nothing: Depala, Broodwarden, On the Shoulders of Giants, Tetzin

:robot: _AI text below_ :robot:

### Card(s)

Depala, Pilot Exemplar; Broodwarden; On the Shoulders of Giants; Tetzin, Gnome Champion

### Build/version

v0.133.0 890e1ee (release card-data `card-data-c747aa7d71f80ab3.json`, and the coverage export of the same build)

### Game mode

Unknown (found by reading the release card-data)

### Actual behavior

On each card, a phrase from the Oracle text is stored whole as one `{"Subtype": …}` entry in a `type_filters` list. No object has that subtype, so the filter matches nothing. The coverage export reports all four cards as supported. The existing subtype-lexicon check (`ParserMisfire:InvalidSubtype`) only reads `AddSubtype` modifications, so it does not catch these filters.

Depala, Pilot Exemplar ("Each Vehicle you control gets +1/+1 as long as it's a creature."):

```json
{"mode": "Continuous", "affected": {"type": "Typed", "type_filters": ["Creature", {"Subtype": "Each Vehicle"}], "controller": "You"}, "modifications": [{"type": "AddPower", "value": 1}, {"type": "AddToughness", "value": 1}], "condition": {"type": "RecipientMatchesFilter", "filter": {"type": "Typed", "type_filters": ["Creature"]}}}
```

Broodwarden ("Eldrazi Spawn creatures you control get +2/+1."):

```json
{"mode": "Continuous", "affected": {"type": "Typed", "type_filters": ["Creature", {"Subtype": "Eldrazi Spawn"}], "controller": "You"}, "modifications": [{"type": "AddPower", "value": 2}, {"type": "AddToughness", "value": 1}]}
```

On the Shoulders of Giants ("Historic creatures you control have flying."):

```json
{"mode": "Continuous", "affected": {"type": "Typed", "type_filters": ["Creature", {"Subtype": "Historic"}], "controller": "You"}, "modifications": [{"type": "AddKeyword", "keyword": "Flying"}]}
```

Tetzin, Gnome Champion ("Whenever Tetzin or another double-faced artifact you control enters, mill three cards. …"), the trigger's `valid_card`:

```json
{"type": "Or", "filters": [{"type": "SelfRef"}, {"type": "Typed", "type_filters": [{"Subtype": "Double-faced Artifact"}], "controller": "You", "properties": [{"type": "Another"}]}]}
```

The parse is the same at v0.66.0 for Depala and Broodwarden.

### Expected behavior

> CR 205.3g: Artifacts have their own unique set of subtypes; these subtypes are called artifact types. The artifact types are Attraction (see rule 718), Blood, Bobblehead, Book, Clue, Communicator, Contraption, Equipment (see rule 301.5), Food, Fortification (see rule 301.6), Gold, Heartwood, Incubator, Infinity, Junk, Lander, Map, Mutagen, Powerstone, Spacecraft, Stone, Treasure, Vehicle (see rule 301.7), and Vibranium.

> CR 700.6: The term historic refers to an object that has the legendary supertype, the artifact card type, or the Saga subtype.

CR 205.3m lists Eldrazi and Spawn as two separate creature types. Historic and double-faced are properties of an object, not subtypes.

By the parse, Depala's crewed Vehicles and Broodwarden's Eldrazi Spawn tokens get no bonus, On the Shoulders of Giants gives no creature flying, and Tetzin triggers only when Tetzin itself enters.

Expected parses:

- Depala: `{"Subtype": "Vehicle"}`. The same card's Dwarf anthem and its `Dig` filter already use `{"Subtype": "Dwarf"}` and `{"Subtype": "Vehicle"}`.
- Broodwarden: two entries, `{"Subtype": "Eldrazi"}` and `{"Subtype": "Spawn"}`.
- On the Shoulders of Giants: an `Or` of legendary, artifact, and Saga.
- Tetzin: an artifact filter that also requires the object to be double-faced.

A parse-time check that a filter's `Subtype` is a real subtype would catch this whole class. The confirmed-misparse census already holds three cards of the same kind unsupported: Ekthi, Contaminator Priest ("Each Equipment"), Kor Blademaster ("Equipped Warrior") and Skyline Savior ("non-angel").

Related: #9822 (open): Brood Birthing's `Subtype("If")` filter, the same class.

### Steps to reproduce

1. Control Depala, Pilot Exemplar and a Vehicle, and crew the Vehicle.
2. The Vehicle should be its printed size +1/+1. By the parse, no filter matches it, so it keeps its printed size.

### Logs/screenshots/game-state

Parse taken from the v0.133.0 release card-data. Each card's `supported: true` comes from the v0.133.0 coverage export (`coverage-data.json`, commit 890e1ee).

Outcome read from the v0.133.0 engine source, not played.
