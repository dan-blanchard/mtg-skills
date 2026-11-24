# Census of `Unimplemented` residue classes at v0.131.0 (request: type one more shape per class)

Phase tag: v0.131.0 (`card-data-v0.131.0.json`, 36,406 face records).

Counts are cards (records) with at least one `Unimplemented` effect of that `name`, over the whole card-data file (including cards not legal in any format, digital-only and silver-border). 3,073 records carry any `Unimplemented` node; 299 carry an `Unknown` trigger mode. Restricted to oracle ids whose record says `legalities.commander: legal`, the totals are 1,742 and 167. (The same count over `card-data-v0.118.0.json` gives 3,090 and 298 records, 1,746 and 158 commander-legal.) One exemplar per broad class (oracle text from MTGJSON; residue text from the record; every exemplar re-checked at v0.131.0):

| `Unimplemented.name` | records | exemplar and residue |
|---|---:|---|
| `unrecognized_clause_head` | 798 | Academic Probation: "Opponents can't cast spells with the chosen name until your next turn" -> residue `with the chosen name`; and `can't attack or block, and its activated abilities can't be activated` |
| `unparsed_verb_arguments` | 749 | Absolving Lammasu: "When this creature dies, you gain 3 life and suspect up to one target creature an opponent controls" -> residue `gain 3 life and suspect up to one target creature an opponent controls`; the "… this way" clauses of issue 35 |
| `unknown` | 398 | Aeon Chronicler: "Suspend X--{X}{3}{U}. X can't be 0." -> residue `Suspend X--{X}{3}{U}.` |
| `unparsed_quantity` | 284 | Aetheric Amplifier, Afterlife from the Loam, All Suns' Dawn (see issue 09) |
| `static_structure` | 230 | Aluren (see issue 23); +2 Mace; Angel of Eternal Dawn; the per-count cost reductions of issue 32 |
| `unparsed_condition` | 205 | Adrestia: "Whenever Adrestia attacks, if an Assassin crewed it this turn, draw a card. Adrestia becomes an Assassin in addition to its other types until end of turn." -> the whole trigger body is one residue |
| `unbound_subject` | 169 | Agent of Raffine: "It perpetually gains prismatic." -> residue `It perpetually gains prismatic` |
| `effect_structure` | 117 | Alloy Golem |
| `where_x_binding` | 58 | see issue 08 |
| `unparsed_replacement` | 55 | Abandoned Sarcophagus: "If a card that has a cycling ability would be put into your graveyard from anywhere and it wasn't cycled, exile it instead." |
| `put_counter_tail` | 51 | Aku Djinn: "put a +1/+1 counter on each creature each opponent controls" -> residue is the whole clause |
| `replacement_structure` | 50 | see issue 11 |
| `Unsupported unless clause` | 42 | Antagonism: "this enchantment deals 2 damage to that player unless one of their opponents was dealt damage this turn" -> `... (unless: one of their opponents was dealt damage this turn)` |
| `otherwise` | 38 | Blood Lust, Advice from the Fae (see issue 14) |
| `granter_reference_unreached` | 20 | see issues 07 and 24e |
| `prevent_damage_recipient_target_role` | 15 | Azorius Ploy, Chain of Silence, Encircling Fissure |

Between the two pins `unparsed_condition` fell by 46 records and `unparsed_verb_arguments` rose by 71. Among the new `unparsed_verb_arguments` records are clauses v0.118.0 typed with a qualifier dropped (issues 33 and 35).

## Expected

Each class is a request to type one more shape; the three broad ones (`unrecognized_clause_head`, `unparsed_verb_arguments`, `unparsed_condition`) hold most of the cards. Naming two or three exemplars per class is the practical way to triage; the numbered issues in this directory are the classes already narrowed to a shape.

## Why it matters

Since the v0.104.0 change to fail closed on what phase cannot represent, these cards are visibly unimplemented rather than silently wrong; typing the common shapes recovers them.
