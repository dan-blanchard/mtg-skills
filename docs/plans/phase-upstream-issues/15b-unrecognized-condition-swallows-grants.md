# Tek: a chain of "X as long as you control a Y" clauses collapses into one `Unrecognized` condition

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Tek** (PLST):
> This creature gets +0/+2 as long as you control a Plains, has flying as long as you control an Island, gets +2/+0 as long as you control a Swamp, has first strike as long as you control a Mountain, and has trample as long as you control a Forest.

## Observed at v0.118.0

The first clause becomes a static with an `Unrecognized` condition holding all the later clauses' text; the keyword grants (flying, first strike, trample) and the +2/+0 are gone:

```json
{"mode": "Continuous", "affected": {"type": "SelfRef"}, "modifications": [{"type": "AddPower"}, {"type": "AddToughness", "value": 2}], "condition": {"type": "Unrecognized", "text": "you control a Plains, has flying as long as you control an Island, gets +2/+0 as long as you control a Swamp, has first strike as long as you control a Mountain, and has trample as long as you control a Forest"}}
```

## Expected

One static per clause, each with its own condition (`IsPresent` Plains / Island / Swamp / Mountain / Forest) and its own modification (`AddToughness 2`, `AddKeyword Flying`, `AddPower 2`, `AddKeyword FirstStrike`, `AddKeyword Trample`).

## Why it matters

The same shape appears on these cards, not re-quoted here: Tribal Golem, Altar of the Wretched ("The same is true for first strike, ..."), Evolved Spinoderm ("Otherwise, it has hexproof"). Four of the five clauses are dropped.
