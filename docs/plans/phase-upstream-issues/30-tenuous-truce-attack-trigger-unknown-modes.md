# Tenuous Truce: "When you attack enchanted opponent … or when they attack you …" split into two `Unknown` trigger modes

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Tenuous Truce** (BLC):
> Enchant opponent
> At the beginning of enchanted opponent's end step, you and that player each draw a card.
> When you attack enchanted opponent or a planeswalker they control or when they attack you or a planeswalker you control, sacrifice this Aura.

## Observed at v0.131.0

The third line is cut at "or" into two triggers, each with an `Unknown` mode; the second has lost its subject ("When a planeswalker they control or when they attack you …"). Both bodies are typed:

```json
[{"mode": {"Unknown": "When you attack enchanted opponent"}, "execute": {"effect": {"type": "Sacrifice", "target": {"type": "SelfRef"}, "count": {"type": "Fixed", "value": 1}}}, "description": "When you attack enchanted opponent, sacrifice ~."}, {"mode": {"Unknown": "When a planeswalker they control or when they attack you or a planeswalker you control"}, "execute": {"effect": {"type": "Sacrifice", "target": {"type": "SelfRef"}, "count": {"type": "Fixed", "value": 1}}}, "description": "When a planeswalker they control or when they attack you or a planeswalker you control, sacrifice ~."}]
```

At v0.118.0 the first half was typed (`mode: YouAttack`, the same `Sacrifice` body), with no recipient filter; the split and the second `Unknown` were there too.

## Expected

One trigger over two attack events: you attack the enchanted player or a planeswalker they control (`YouAttack` with a recipient filter of the enchanted player or their planeswalkers), and the enchanted player attacks you or a planeswalker you control. If the grammar can't join two events on one trigger (issue 02 asks the same for Ranar), two triggers with those typed modes would do.

## Why it matters

With `Unknown` modes the Aura is never sacrificed, so it reads as a free card every turn with no way for either player to end the truce.
