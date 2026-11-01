# Monstrous Rage: a Role token has no ability ("Enchanted creature gets +1/+1 and has trample")

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Monstrous Rage** (SOA):
> Target creature gets +2/+0 until end of turn. Create a Monster Role token attached to it. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)

## Observed at v0.118.0

The `Token` is typed `[Enchantment, Aura, Role]` with `attach_to: ParentTarget`, and carries no `static_abilities`/`keywords`:

```json
{"type": "Token", "name": "Monster Role", "power": {"type": "Fixed"}, "toughness": {"type": "Fixed"}, "types": ["Enchantment", "Aura", "Role"], "count": {"type": "Fixed", "value": 1}, "owner": {"type": "Controller"}, "attach_to": {"type": "ParentTarget"}}
```

## Expected

The Role's static (`Continuous` over `EnchantedBy`, `AddPower 1`, `AddToughness 1`, `AddKeyword Trample`), as the predefined-token table (`known-tokens.toml`) has for other predefined tokens.

## Why it matters

The same applies to 11 Role-making cards (Become Brutes among them, not re-quoted here): the Role does nothing.
