<!-- Status: FILED 2026-11-25 as https://github.com/phase-rs/phase/issues/11361 (against phase v0.133.0, commit 890e1ee; verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Variable Solutions: the "If X is 1/2/3" heads are dropped, so the X=1 and X=2 lines run unconditionally as one chain and the edict loses "each opponent"

:robot: _AI text below_ :robot:

### Card(s)

Variable Solutions (Alchemy: Secrets of Strixhaven)

### Build/version

v0.133.0 890e1ee (release card-data `card-data-c747aa7d71f80ab3.json`)

### Game mode

Unknown (found by reading the release card-data)

### Actual behavior

Oracle text ({X}{G} sorcery):

> If X is 1, seek a basic land card and put it onto the battlefield tapped.
> If X is 2, each opponent sacrifices an artifact of their choice.
> If X is 3, conjure a random creature card with mana value X onto the battlefield.
> If X is 4 or more, you gain 2 life. Then do all of the above.

Only the fourth line keeps its "If X is …" head (`QuantityCheck` of `CostXPaid` `GE 4`). The first two lines lose theirs and are chained into a single unconditional ability. The second line also loses its subject ("each opponent"), which leaves a `Sacrifice` with no `player_scope` and no `controller`. The third line is a residue with no condition either:

```json
[{"effect": {"type": "Seek", "filter": {"type": "Typed", "type_filters": ["Land"], "properties": [{"type": "HasSupertype", "value": "Basic"}]}, "count": {"type": "Fixed", "value": 1}, "destination": "Hand"}, "sub_ability": {"effect": {"type": "ChangeZone", "destination": "Battlefield", "target": {"type": "ParentTarget"}, "enter_tapped": true}, "sub_ability": {"effect": {"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Artifact"]}, "count": {"type": "Fixed", "value": 1}}, "sub_link": "SequentialSibling"}}},
 {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "conjure a random creature card with mana value X onto the battlefield"}},
 {"effect": {"type": "GainLife", "amount": {"type": "Fixed", "value": 2}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "do all of the above"}, "sub_link": "SequentialSibling"}, "condition": {"type": "QuantityCheck", "lhs": {"type": "Ref", "qty": {"type": "CostXPaid"}}, "comparator": "GE", "rhs": {"type": "Fixed", "value": 4}}}]
```

The same shape is in every release card-data checked, from v0.66.0 to v0.133.0.

### Expected behavior

> CR 107.3: Many objects use the letter X as a placeholder for a number that needs to be determined. Some objects have abilities that define the value of X; the rest let their controller choose the value of X.

> CR 608.2c: The controller of the spell or ability follows its instructions in the order written. …

Each line happens only for its own value of X, and the second line's sacrifice is made by each opponent. By the parse, the seek and the sacrifice run for any X, and the sacrifice names no opponent.

Expected parse: one ability per line, each gated the way the fourth line already is, with `QuantityCheck` of `CostXPaid` `EQ 1`, `EQ 2` and `EQ 3`. The edict should be the "each opponent sacrifices" form phase gives Sheoldred's Edict: `Sacrifice` of `Typed[Artifact] controller: You` with `player_scope: {"type": "Opponent"}`.

### Steps to reproduce

1. Control an artifact. Cast Variable Solutions with X = 1.
2. You should seek a basic land and put it onto the battlefield tapped, and nothing else should happen.
3. As parsed, a sacrifice also resolves, made by you rather than by each opponent.

### Logs/screenshots/game-state

Parse taken from the v0.133.0 release card-data.

Outcome read from the v0.133.0 engine source, not played.
