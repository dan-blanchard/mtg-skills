"""Swept detector set — mined exhaustively from real Scryfall oracle text.

Each entry is one ability-axis detector: a structural-anchor regex (validated
against bulk, never authored from memory — ADR-0009), a scope, and is_widen_of
(the existing key it extends, or "" for a brand-new axis). The extractor compiles
these into Detector records (_FLOOR_DETECTORS) and signal_specs auto-registers an
avenue per key.
Regenerate via the exhaustive-residual-sweep workflow. Two clause-scoped baseline
widens (creature_etb, death_matters) are intentionally excluded here — their
originals keep clause scope.
"""

# ruff: noqa: E501 — generated data module of long, bulk-validated regex literals
from __future__ import annotations

SWEEP_DETECTORS: tuple[dict, ...] = (
    {
        "key": "free_cast",
        "scope": "you",
        "is_widen_of": "",
        "regex": "rather than pay (?:its|their|the) mana cost|without paying (?:its|their) mana cost|may cast (?:it|that (?:card|spell)|those cards)[^.]*without paying",
    },
    {
        "key": "commander_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "commanders? you (?:control|own) (?:have|has|get|gets|gain|gains)|commander creatures? you (?:own|control)|whenever your commander\\b|whenever a commander\\b|your commander (?:has|have|deals|enters|attacks|gets|gains)|is your commander|it'?s your commander|while [^.]*your commander|it's a copy of your other commander|copy of any of your commanders|each commander you (?:control|own)|for each commander|commander damage|champions? of",
    },
    {
        "key": "variable_pt",
        "scope": "any",
        "is_widen_of": "",
        "regex": "power and toughness are each equal to(?: the (?:total )?number of)?|power(?: and toughness)? (?:is|are)(?: each)? equal to (?:twice )?the (?:total )?number of|equal to (?:twice )?the (?:total )?number of cards in (?:your|their|the|all) [^.]*hand|change [^.]*base power and toughness",
    },
    {
        "key": "scaling_pump",
        "scope": "you",
        "is_widen_of": "",
        "regex": "gets [+\\-][0-9x]/[+\\-][0-9x] for (?:each|every)",
    },
    {
        "key": "count_anthem",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:creatures you control get|each creature you control gets) [+]\\d+/[+]\\d+ for each",
    },
    {
        "key": "tapper_engine",
        "scope": "any",
        "is_widen_of": "",
        "regex": ":\\s*tap (?:target|up to (?:one|two|\\d+) target|all|each|two target|x target)|(?:at the beginning of|whenever)[^.:]*,[^.]*\\btap (?:up to (?:one|two|\\d+) target|target)|\\btap up to (?:one|two|\\d+) target (?:creature|permanent)\\b|when [^.]* enters, tap (?:up to )?(?:one|two|\\d+|target)|(?:doesn't|don't|does not) untap during (?:its|their|the)",
    },
    {
        "key": "tap_down",
        "scope": "opponents",
        "is_widen_of": "",
        "regex": "(?<!un)tap target (?:permanent|creature|land|nonland permanent)[^.]*(?:an opponent|that player) controls|skips? (?:their|his or her|its) next untap step|tap (?:up to )?\\w+ target permanents? (?:an opponent|that player) controls|\\bdetain\\b",
    },
    {
        "key": "tap_untap_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "whenever [^.]*becomes? (?:tapped|untapped)|becomes? untapped, put",
    },
    {
        "key": "ability_copy",
        "scope": "you",
        "is_widen_of": "",
        "regex": "copy (?:that|this|the|target) (?:activated |triggered |activated or triggered )?ability|you may copy (?:it|that ability)|has all activated abilities of|has the activated abilities of",
    },
    {
        "key": "affinity_type",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\baffinity\\b|spells you cast have affinity",
    },
    {
        "key": "flash_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "as though (?:it|they) (?:had|have) flash|have flash\\b",
    },
    {
        "key": "noncombat_damage_payoff",
        "scope": "you",
        # MV/card-value-SCALING burn engines ("deals damage equal to that spell's /
        # the exiled card's / that card's mana value" — Kaervek, Vial Smasher,
        # Hidetsugu) are the genuine noncombat payoffs here. The "deals double/triple
        # that damage" branch was removed: those are ALL-damage replacement effects
        # (Furnace of Rath, Fiery Emancipation) — combat damage too (CR 510 vs the
        # noncombat damage of 702.19a) — so they belong on damage_doubling, not a
        # "burn outside combat" lane.
        "is_widen_of": "",
        "regex": "noncombat damage|deals that much damage to (?:each opponent|any target|that creature)|deals exactly \\d+ damage|whenever (?:a|another) source you control deals [^.]*damage|deals damage equal to (?:that spell's|the exiled card's|that card's|that creature's) mana value",
    },
    {
        "key": "mass_removal",
        "scope": "you",
        "is_widen_of": "",
        "regex": "destroy all (?:other )?(?:nonland )?(?:permanents|creatures|artifacts|enchantments|other creatures)|deals? \\d+ damage to each (?:creature|nonlegendary creature|other creature)|exile all (?:creatures|permanents)|exile all (?:black|white|blue|red|green) creatures|all creatures get -\\d|destroy all [^.]*creatures except|destroy all other creatures",
    },
    {
        "key": "debuff_matters",
        "scope": "any",
        "is_widen_of": "",
        "regex": "(?:other [a-z]+ creatures|nonblack creatures|all creatures|creatures) get -\\d/-\\d|gets? -\\d/-\\d until end of turn|gets -0/-x|gets -x/-x|creatures? (?:[^.]{0,40})?get -[0-9x]/-[0-9x]|put a -1/-1 counter on target|put (?:a|one|two|x|\\d+) -1/-1 counters? on|creatures? (?:target player|an opponent|your opponents|each opponent)[^.]*controls?[^.]*base power and toughness [0-2]/[0-2]",
    },
    {
        "key": "coin_flip",
        "scope": "you",
        "is_widen_of": "",
        "regex": "flip a coin|flip (?:two|three|\\d+) coins|wins? (?:the|a) (?:coin )?flip|lose (?:the|a) (?:coin )?flip",
    },
    {
        "key": "topdeck_selection",
        "scope": "you",
        "is_widen_of": "",
        "regex": "look at the top (?:two|three|four|five|six|seven|eight|nine|ten|\\w+|x|\\d+) cards? of your library|reveal the top (?:two|three|four|five|six|seven|eight|nine|ten|\\w+|x|\\d+) cards? of your library|reveal cards from the top of your library until|put [^.]*from among them onto the battlefield",
    },
    {
        "key": "play_from_top",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:may )?play (?:the )?top card of (?:your|their) library|you may look at the top card of your library (?:any time|at any time)|play with the top card of your library revealed|(?:play|cast) (?:lands?|spells?|creature spells?)[^.]*from the top of your library",
    },
    {
        "key": "dig_until",
        "scope": "you",
        "is_widen_of": "",
        "regex": "exile cards? from the top of your library until|exile (?:the )?top[^.]*until you exile|reveal cards from the top of your library until",
    },
    {
        "key": "hand_disruption",
        "scope": "opponents",
        "is_widen_of": "",
        "regex": "look at (?:target player|that player|an opponent|each opponent|target opponent)'?s?'? hands?|plays? with (?:their|his or her) hands? revealed|reveals? (?:their|his or her) hands?|reveals? (?:\\w+ )?cards? (?:at random )?from (?:their|his or her|that player's) hand|reveals?[^.]*until you say stop",
    },
    {
        "key": "group_mana",
        "scope": "each",
        "is_widen_of": "",
        "regex": "each player adds \\{|that player adds \\{|the active player[^.]*adds? \\{|a player (?:loses?|losing)[^.]*mana[^.]*lose",
    },
    {
        "key": "secret_writedown",
        "scope": "you",
        "is_widen_of": "",
        "regex": "secretly (?:write|choose|name)|before the game begins[^.]*(?:write|name|choose)|from outside the game|your sideboard",
    },
    {
        "key": "fight_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bfights? (?:up to (?:one|two|\\d+) )?(?:other |another )?target\\b|\\bfights? (?:up to (?:one|two) )?(?:other )?creature|\\bfight each other\\b|\\bfights? it\\b|\\bfights? (?:another|each)",
    },
    {
        "key": "life_total_set",
        "scope": "any",
        "is_widen_of": "",
        "regex": "life total (?:becomes|equal to)|equal to half (?:that|your|a) (?:player'?s? )?life|exchange (?:your )?life total|exchange life totals?|set your life total to|double target player's life total",
    },
    {
        "key": "animate_artifact",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:target |each )?(?:noncreature )?artifact(?:s)? (?:you control )?(?:becomes?|are|become) (?:an? )?(?:artifact )?creature|becomes? an artifact creature|(?:artifact or land|target artifact|noncreature artifact|artifact you control)[^.]*becomes? a[^.]*creature",
    },
    {
        "key": "creature_ping",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:target |another target )?[A-Z][a-z]+ you control deals damage equal to its power to|deals damage equal to its power to (?:another )?target|deals damage to itself equal to its power|target creature deals damage [^.]*equal to its power",
    },
    {
        "key": "damage_equal_power",
        "scope": "you",
        "is_widen_of": "",
        "regex": "deals? damage[^.]*equal to (?:its|that creature.s|[^.]*) power[^.]*to (?:any target|target|each opponent|that player|target player)",
    },
    {
        "key": "power_double",
        "scope": "you",
        "is_widen_of": "",
        "regex": "double the power|doubles? the power and toughness|power(?: and toughness)? (?:is|are) doubled|double [A-Z][a-z']+ power|doubles? [^.]*power until end of turn",
    },
    {
        "key": "noncreature_cast_punish",
        "scope": "any",
        "is_widen_of": "",
        "regex": "whenever a player casts a noncreature spell|whenever an opponent casts a noncreature|whenever a player casts an (?:artifact|instant|sorcery)",
    },
    {
        "key": "combat_buff_engine",
        "scope": "you",
        "is_widen_of": "",
        "regex": "at the beginning of combat on your turn[^.]*creature[^.]*\\.?\\s*(?:until end of turn,? )?that creature gets \\+|whenever (?:this creature|[A-Z][a-z]+) attacks[^.]*(?:creature|it) gets \\+\\d/|whenever [\\w ]+ blocks(?: or becomes blocked)?[^.]*gets [+\\-]|whenever [\\w ]+ attacks[^.]*,? (?:it|[\\w ]+?) gets [+\\-]",
    },
    {
        "key": "opponent_exile_matters",
        "scope": "opponents",
        "is_widen_of": "exile_matters",
        "regex": "cards? (?:your opponents own|an opponent owns)[^.]*in exile|for each card your opponents own in exile|opponents own in exile|exile (?:target player's|target opponent's|each opponent's|that player's) graveyard|if a card would be put into an opponent's graveyard",
    },
    {
        "key": "opponent_counter_grant",
        "scope": "opponents",
        "is_widen_of": "",
        "regex": "put a (?:bounty|stun|[a-z]+) counter on target (?:creature|permanent) (?:an opponent controls|that opponent controls)|target creature an opponent controls[^.]*it has \\\"|creatures with [^.]*counters on them can't attack|put a [^.]*counter on target creature you don't control",
    },
    {
        "key": "counter_place_trigger",
        "scope": "you",
        "is_widen_of": "counters_matter",
        "regex": "whenever (?:you put|.*put) (?:one or more )?\\+1/\\+1 counters? on|whenever one or more \\+1/\\+1 counters? (?:are|is) put on|whenever you put (?:a|one or more|two|\\d+) [^.]*counters? on|whenever (?:a|one or more) [^.]*counters? (?:is|are) put on",
    },
    {
        "key": "counter_distribute",
        "scope": "you",
        "is_widen_of": "counters_matter",
        "regex": "put (?:a|one|two|\\d+|x) \\+1/\\+1 counters? on each (?:other )?creature you control|distribute \\+1/\\+1 counters|put (?:a |one or more |the same number[^.]*?)\\+1/\\+1 counters? on each of|enters with (?:a|an|one|two|three|x|\\d+)(?: additional)? \\+1/\\+1 counters? on|enters with that many additional",
    },
    {
        "key": "keyword_counter",
        # CR 122.1b is a CLOSED list of keyword counters that grant an ability via
        # layer 6 (613.1f). "stun" (122.1d) and "shield" (122.1c) counters create
        # replacement effects and grant NO keyword; "aegis" is not a CR counter at
        # all — so they don't belong on a keyword-grant lane. They were removed.
        "scope": "any",
        "is_widen_of": "",
        "regex": "(?:put|with|of an?)[^.]{0,60}?(?:flying|menace|trample|reach|haste|deathtouch|hexproof|indestructible|lifelink|vigilance) counter|enters with (?:a|an|one|two|\\d+)[^.]*?(?:flying|menace|trample|reach|haste|deathtouch|hexproof|indestructible|lifelink|vigilance) counter",
    },
    {
        "key": "counter_replace_bonus",
        "scope": "you",
        "is_widen_of": "counter_doubling",
        "regex": "that many plus (?:one|two|\\d+) [^.]*counters? are put|put that many plus|if (?:one or more )?\\+1/\\+1 counters? would be put on|one or more counters? would be (?:put|placed)[^.]*(?:that many plus|twice that many)",
    },
    {
        "key": "counter_move",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bmove (?:a|one|that|any number of|all|x|\\d+|one or more) [^.]{0,30}?counters?\\b (?:from|onto|to)",
    },
    {
        "key": "counter_manipulation",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:remove|move) (?:a|one|any number of|x|\\d+) (?:\\+1/\\+1|-1/-1) counters?|(?:remove|move) (?:a|one|any number of|x|\\d+) [^.]{0,20}?(?:\\+1/\\+1|-1/-1) counters?",
    },
    {
        "key": "self_counter_grow",
        "scope": "you",
        "is_widen_of": "counters_matter",
        "regex": "enters with (?:x|\\d+|a|an|one|two|three) \\+1/\\+1 counters? on (?:him|her|it|itself|this)|put (?:a|one|two|three|x|\\d+) \\+1/\\+1 counters? on (?:him|her|it|itself|this creature)\\b|put that many \\+1/\\+1 counters? on (?:him|her|it|itself|this creature)",
    },
    {
        "key": "facedown_matters",
        "scope": "you",
        # Also: turning a TARGET face-down creature face up (Kaust, Jalum Grifter) and
        # a "turned face up this turn" payoff — the lane keyed only on the self/pronoun
        # "turn it face up" form.
        "is_widen_of": "",
        "regex": "\\bmorph\\b|\\bmegamorph\\b|\\bmanifest\\b|\\bdisguise\\b|\\bcloak\\b|face-?down creatures?|as a 2/2 face-?down|turn (?:it|that creature|this creature|them|a permanent you control) face up|turn target [^.]*?face up|turned face up this turn",
    },
    {
        "key": "targeting_matters",
        "scope": "any",
        "is_widen_of": "",
        "regex": "becomes the target of a spell or ability|whenever [^.]{0,60}?becomes? the target of|\\bheroic\\b|whenever you cast (?:an instant or sorcery spell |a spell )?that targets",
    },
    {
        "key": "protection_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "gains? protection from|gains? (?:hexproof|shroud)\\b|target [^.]*gains? protection|can't be the target of (?:spells?|abilities)[^.]*your opponents control",
    },
    {
        "key": "conditional_self_protection",
        "scope": "you",
        "is_widen_of": "",
        "regex": "has hexproof (?:if|while|as long as|during)|during your turn,[^.]*has (?:hexproof|indestructible|protection)|has (?:hexproof|indestructible) if",
    },
    {
        "key": "keyword_grant_target",
        "scope": "you",
        "is_widen_of": "",
        "regex": "target creature (?:you control )?(?:gains?|gets [+\\-][0-9x]/[+\\-][0-9x] and gains?) (?:deathtouch|trample|flying|menace|vigilance|double strike|first strike|lifelink|haste|hexproof|indestructible|protection|reach|ward|shroud)",
    },
    {
        "key": "spell_keyword_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "spells you cast have (?:convoke|affinity|cascade|flash|trample|deathtouch|delve|undaunted|haste|lifelink|menace|ward|improvise|demonstrate|casualty|flashback)|(?:noncreature spells|creature spells|spells) you cast have (?:improvise|demonstrate|casualty|convoke|affinity|cascade|flashback)|spell you cast(?: each turn)? has casualty|creature spells you cast have",
    },
    {
        "key": "exhaust_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bexhaust\\b",
    },
    {
        "key": "partner_background",
        "scope": "you",
        "is_widen_of": "",
        "regex": "choose a background|partner with|\\bpartner\\b(?! with)|\\bfriends forever\\b|\\bdoctor's companion\\b",
    },
    {
        "key": "companion_keyword",
        "scope": "you",
        "is_widen_of": "",
        "regex": "companion —|each (?:creature |permanent )?card in your starting deck|your starting deck contains",
    },
    {
        "key": "lure_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "all creatures able to block [^.]*do so|must be blocked if able|all creatures (?:that could|able to) block|must be blocked(?: (?:by|if))?",
    },
    {
        "key": "bending_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\b(?:firebending|waterbending|earthbending|airbending|earthbend|waterbend|firebend|airbend)\\b",
    },
    {
        "key": "domain_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bdomain\\b|number of basic land types? (?:among|you)|basic land types? among",
    },
    {
        "key": "conjure_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bconjure\\b",
    },
    {
        "key": "saga_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "lore counter|on (?:a|target) saga you control",
    },
    {
        # Scope is "any": the row matches both self-wins ("you win the game") and
        # opponent-losses ("that player loses the game"), so a single forced scope can't
        # be correct — "any" avoids the old "opponents" mislabel of self-wincons. A true
        # per-branch scope split would need clause-scope extraction (the sweep table's
        # unique-key invariant forbids two win_lose_game rows).
        "key": "win_lose_game",
        "scope": "any",
        "is_widen_of": "",
        "regex": "you win the game|(?:that player|each opponent|target (?:player|opponent)) loses the game",
    },
    {
        "key": "target_player_draws",
        "scope": "any",
        "is_widen_of": "",
        "regex": "target player draws a card|target opponent draws",
    },
    {
        "key": "ltb_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "a permanent (?:you controlled )?left the battlefield (?:under your control )?this turn|whenever [^.]*(?:leaves the battlefield|leave the battlefield)|when [^.]* leaves the battlefield",
    },
    {
        "key": "each_mode_player",
        "scope": "each",
        "is_widen_of": "",
        "regex": "each mode must target a different player",
    },
    {
        "key": "toughness_combat",
        "scope": "you",
        "is_widen_of": "",
        "regex": "assigns? combat damage equal to its (?:toughness|mana value) rather than its power|deals damage equal to its toughness",
    },
    {
        "key": "donate_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:target opponent|another player|target player|that player|each opponent|each other player) gains control of[^.]*you control|target opponent (?:creates|draws|gains|puts)|(?:target opponent|another player|target player|that player) gains control of",
    },
    {
        "key": "attractions_matter",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\battraction\\b|open an attraction",
    },
    {
        "key": "extra_land_drop",
        "scope": "you",
        "is_widen_of": "",
        "regex": "put a land(?: card)? from your hand onto the battlefield|you may put a land [^.]*onto the battlefield",
    },
    {
        "key": "blocked_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "whenever [^.]*becomes blocked|\\bwhenever \\w[^.]*\\bblocks\\b",
    },
    {
        "key": "exile_until_leaves",
        "scope": "you",
        "is_widen_of": "",
        "regex": "exile [^.]*until [^.]*leaves the battlefield",
    },
    {
        "key": "damage_prevention",
        "scope": "you",
        "is_widen_of": "",
        "regex": "prevent the next (?:\\d+|x) damage|prevent (?:all|the next \\d+|x|all combat|all but \\d+|that) [^.]*damage|prevent that damage|prevent all damage|prevent [^.]*damage that would be dealt",
    },
    {
        "key": "damage_redirect",
        "scope": "you",
        "is_widen_of": "",
        "regex": "the next (?:\\d+|x) damage [^.]*would be dealt[^.]*(?:is )?dealt to [^.]*instead|that damage is dealt to [^.]*instead|deal that damage to [^.]*instead",
    },
    {
        "key": "damage_doubling",
        "scope": "you",
        "is_widen_of": "",
        # Covers double AND triple (Fiery Emancipation) all-damage replacement
        # effects, which were previously only caught by noncombat_damage_payoff.
        "regex": "deals? (?:double|triple) that damage|deals? twice that (?:much|damage)|prevent half that damage|double the (?:next )?damage|deals that much damage plus",
    },
    {
        "key": "symmetric_damage_each",
        "scope": "each",
        "is_widen_of": "",
        "regex": "deals \\d+ damage to each (?:player|opponent and|creature and each player)|deals \\d+ damage to each opponent|deals \\d+ damage to each player",
    },
    {
        "key": "damage_to_you_punish",
        "scope": "opponents",
        "is_widen_of": "",
        "regex": "whenever a source an opponent controls deals damage to you|whenever (?:a|an) (?:opponent|source[^.]*opponent)[^.]*deals (?:combat )?damage to you",
    },
    {
        "key": "damage_reflect",
        "scope": "you",
        "is_widen_of": "",
        "regex": "whenever [^.]*is dealt damage, (?:it|this creature) deals that much damage",
    },
    {
        "key": "excess_damage",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bexcess damage\\b",
    },
    {
        "key": "destroy_legendary",
        "scope": "any",
        "is_widen_of": "removal_matters",
        "regex": "destroy (?:up to one )?target legendary (?:permanent|creature)",
    },
    {
        "key": "anthem_static",
        "scope": "you",
        "is_widen_of": "team_buff",
        "regex": "(?:other [a-z]+ creatures|creatures you control|[a-z]+ creatures you control|nonblack creatures|other creatures) get \\+\\d/\\+\\d",
    },
    {
        "key": "all_creatures_kw_grant",
        "scope": "any",
        "is_widen_of": "",
        "regex": "all creatures have (?:haste|flying|trample|vigilance|menace|hexproof|deathtouch|first strike|double strike|reach|lifelink)",
    },
    {
        "key": "global_ability_grant",
        "scope": "any",
        "is_widen_of": "",
        "regex": 'all (?:artifacts|creatures|lands|permanents) have \\"|creatures? you (?:own|control) have \\"',
    },
    {
        "key": "aura_equip_kw_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:auras?|equipment) you control have (?:exalted|flying|trample|deathtouch|lifelink|vigilance|haste|first strike|double strike|hexproof|ward|menace|reach|indestructible)",
    },
    {
        "key": "counter_grants_kw",
        "scope": "you",
        "is_widen_of": "",
        "regex": "creature you control with a \\+1/\\+1 counter on it (?:has|have) (?:haste|flying|trample|menace|vigilance|lifelink)",
    },
    {
        "key": "typed_anthem_multi",
        "scope": "you",
        "is_widen_of": "",
        "regex": "each (?:other )?creature (?:you control )?that's (?:a |an )\\w+[^.]*(?:gets?|have|has|gains?)",
    },
    {
        "key": "unspent_mana",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bunspent mana\\b|don't lose unspent|lose unspent mana|\\bmana burn\\b|loses? (?:one or more )?unspent mana|don't lose (?:this |unspent )?(?:\\w+ )?mana as (?:steps|phases|those steps)",
    },
    {
        "key": "keyword_soup",
        "scope": "you",
        "is_widen_of": "",
        "regex": "if it has flying[^.]*first strike|the same is true for first strike, double strike|has flying[^.]*\\+1/\\+1",
    },
    {
        "key": "trigger_doubling",
        "scope": "you",
        "is_widen_of": "",
        "regex": "that ability triggers an additional time|triggers? an additional time|trigger an additional time",
    },
    {
        "key": "ninjutsu_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bninjutsu\\b",
    },
    {
        "key": "suspend_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bsuspend\\b",
    },
    {
        "key": "boast_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bboast\\b",
    },
    {
        "key": "soulbond_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bsoulbond\\b",
    },
    {
        "key": "pump_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "target (?:[a-z]+ )*creature(?: you control)? gets \\+[0-9x]/\\+[0-9x]|target [A-Z][a-z]+ you control gets \\+|target creature(?: you control)? gets \\+[\\dxX]",
    },
    {
        "key": "self_pump",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\{[^}]*\\}(?:, \\{t\\})?: [^.]* gets \\+[0-9x]/\\+[0-9x] until end of turn|\\{[wubrgc]\\}: [^.:]*gets \\+\\d+/\\+\\d+ until end of turn|\\{[^}]*\\}(?:, \\{t\\})?: put a \\+1/\\+1 counter on (?:it|this creature|[A-Z][a-z]+)",
    },
    {
        "key": "base_pt_set",
        "scope": "any",
        "is_widen_of": "",
        "regex": "base power (?:and toughness )?\\d|has base power|base toughness \\d|becomes a [^.]*with base power and toughness|becomes a [^.]* in addition to its other types|base power and toughness are each equal to|switch (?:each |target )?creature'?s'? power and toughness|switch [^.]{0,40}power and toughness|base power and toughness of each [^.]*become",
    },
    {
        "key": "playtest_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bplaytest cards?\\b",
    },
    {
        "key": "stickers_matter",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\{tk\\}|\\bstickers?\\b",
    },
    {
        "key": "starting_life_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:greater than|less than|above|below|equal to) your starting life total|life total is (?:greater|less|higher|lower)",
    },
    {
        "key": "miracle_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:cards?|spells?) (?:in your hand )?ha(?:s|ve) miracle",
    },
    {
        "key": "convoke_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bconvoke\\b",
    },
    {
        "key": "explore_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bexplores?\\b",
    },
    {
        "key": "changeling_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "is every creature type|\\bchangeling\\b",
    },
    {
        "key": "alt_cost_keyword",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bweb-slinging\\b|\\bsneak\\b|\\bmayhem\\b",
    },
    {
        "key": "flip_meld_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bflip this creature\\b|meld them into",
    },
    {
        "key": "legend_rule_off",
        "scope": "you",
        "is_widen_of": "",
        "regex": "the .legend rule. doesn't apply",
    },
    {
        "key": "cmdzone_ability",
        "scope": "you",
        "is_widen_of": "",
        "regex": "is (?:on the battlefield or )?in the command zone|activate this ability only if[^.]*command zone",
    },
    {
        "key": "mass_bounce",
        "scope": "any",
        "is_widen_of": "",
        "regex": "return each (?:other )?(?:nonland )?permanent[^.]*to (?:its|their) owner's hand|return each (?:other )?[^.]*?creatures?[^.]*?to (?:its|their) owner's hand|return all[^.]*to (?:its|their) owners' hands",
    },
    {
        "key": "activated_draw",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\{t\\}: draw a card",
    },
    {
        "key": "forced_attack",
        "scope": "any",
        "is_widen_of": "",
        "regex": "may attack only the nearest opponent|attacks? that player this combat if able|attacks? (?:each|every) combat if able",
    },
    {
        "key": "tribal_etb_multi",
        "scope": "you",
        "is_widen_of": "",
        "regex": "whenever [^.]*or another [A-Z][a-z]+(?:, [A-Z][a-z]+)*,? (?:or [A-Z][a-z]+ )?enters",
    },
    {
        "key": "typed_enters_punish",
        "scope": "you",
        "is_widen_of": "",
        "regex": "whenever another (?:outlaw|ally|\\w+) you control enters, [^.]*deals \\d+ damage to (?:target opponent|each opponent|any target)",
    },
    {
        "key": "topdeck_stack",
        "scope": "you",
        "is_widen_of": "",
        "regex": "put (?:two|three|\\w+) cards? from your hand on top of your library|on top of your library in any order",
    },
    {
        "key": "theft_matters",
        "scope": "opponents",
        "is_widen_of": "gain_control",
        # \bheist\b — the Arena keyword action that exiles cards from a target
        # opponent's library and lets you cast them (theft / cast-what-you-don't-own).
        "regex": "conjure a duplicate of[^.]*from an opponent's library|you may (?:play|cast)[^.]*from that player's hand|cast (?:spells )?from (?:that|target) (?:player|opponent)'s hand|play (?:with )?(?:lands and )?(?:spells )?from (?:that|target) (?:player|opponent)'s hand|(?:each player|each opponent|target opponent|that player)[^.]*exiles? cards from the top of their library|search (?:that player|target opponent|an opponent|each opponent)'?s? graveyard, hand,? and library|\\bheist\\b",
    },
    {
        "key": "cast_as_named_card",
        "scope": "you",
        "is_widen_of": "",
        "regex": "cast (?:creature )?cards? from your hand as though they were the card",
    },
    {
        "key": "evasion_denial",
        "scope": "opponents",
        "is_widen_of": "",
        "regex": "can be blocked as though (?:it|they) didn't have",
    },
    {
        "key": "named_permanent",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:permanent|creature|another permanent) named [A-Z]|a permanent you control named|control a (?:permanent|creature)[^.]*named",
    },
    {
        "key": "discard_outlet",
        "scope": "you",
        "is_widen_of": "discard_matters",
        "regex": "discard (?:a|an|another|two|three|your hand|x|\\d+) [^:.]{0,40}?:|, discard (?:a|an|another|two|three|x|\\d+) cards?:|discard (?:two|three|four|five|x|\\d+) cards? at random|discard all the cards in your hand|discard your hand|discard three cards at random|draw (?:two|three|\\w+|\\d+) cards?[^.]*\\.?\\s*then discard|draw [^.]*cards?,? then discard",
    },
    {
        # dies_recursion is the BROAD "creatures recur when they die" category — with
        # OR without counters. It is the SUPERSET of undying_persist_matters: undying
        # (CR 702.93a, +1/+1) and persist (CR 702.79a, -1/-1) ARE dies-recursion that
        # also place a counter, so the keywords are members here too; bare dies-return
        # grants (Feign Death / Supernatural Stamina) are dies_recursion only. The
        # keyword word survives reminder-text stripping (same as undying_persist_matters).
        "key": "dies_recursion",
        "scope": "you",
        "is_widen_of": "",
        "regex": "if [^.]* would die, instead exile it with [^.]*counters?|when [^.]* dies, return (?:it|her|him|them) to the battlefield|\\b(?:undying|persist)\\b",
    },
    {
        "key": "devour_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bdevour\\b",
    },
    {
        "key": "cant_block_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "target creature can't block",
    },
    {
        "key": "station_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bstation\\b|\\bspacecraft\\b",
    },
    {
        "key": "void_warp_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "void —|warp \\{|warp cost|warp—|for its warp cost|using its warp ability|cast (?:a |this )?(?:spell|card)[^.]*for its warp|target exiled card with warp",
    },
    {
        "key": "named_counter_mechanic",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\b(?:egg|divinity|rad|prey|bounty|bribery|page|study|knowledge|silver|gold|oil|ki|fade|fate|incubation|shield) counters?\\b",
    },
    {
        "key": "seek_matters",
        "scope": "you",
        "is_widen_of": "tutor_matters",
        "regex": "\\bseek\\b",
    },
    {
        "key": "powerup_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "power-up —",
    },
    {
        "key": "myriad_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "gains? myriad|\\bmyriad\\b",
    },
    {
        "key": "phasing_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "phase out|phases out|phased out",
    },
    {
        "key": "color_change",
        "scope": "you",
        "is_widen_of": "",
        "regex": "becomes the color of your choice|becomes? (?:the color|all colors)",
    },
    {
        "key": "timing_control",
        "scope": "opponents",
        "is_widen_of": "",
        "regex": "may end the turn|cast spells (?:and activate abilities )?only during their own|spells? only any time they could cast a sorcery|can cast spells only",
    },
    {
        "key": "sacrifice_protection",
        "scope": "you",
        "is_widen_of": "",
        "regex": "can't cause you to sacrifice|can't be sacrificed",
    },
    {
        "key": "draft_spellbook",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bdraft a card\\b|spellbook",
    },
    {
        "key": "stax_taxes",
        "scope": "opponents",
        "is_widen_of": "stax_taxes",
        "regex": "(?:target player|that player|each player|a player|that opponent)[^.]{0,90}?can't (?:cast|activate|attack|block|search|untap|draw)|must pay \\{?\\d?\\}?[^.]*additional|spells?[^.]*cost \\{?\\d+\\}? more to (?:cast|activate)|noncreature spells?[^.]*cost(?:s)? \\{?\\d|noncreature spells?[^.]*can't be cast|spells? with mana value \\d[^.]*can't be cast|players? can't cast|that player can't cast spells|spells can't be cast|can cast spells only|your opponents control enter(?:s)? tapped|nonbasic lands enter(?:s)? tapped|costs? players \\{?\\d+\\}? more|doing the chosen action costs|players? can't pay life or sacrifice nonland permanents",
    },
    {
        "key": "symmetric_stax",
        "scope": "each",
        "is_widen_of": "stax_taxes",
        "regex": "players? can't (?:cast|untap|attack|gain|search their|draw|play|activate)|other permanents enter (?:the battlefield )?tapped|(?:doesn't|don't|does not) untap during (?:its|their|the)",
    },
    {
        "key": "cheat_into_play",
        "scope": "you",
        "is_widen_of": "cheat_into_play",
        "regex": "put (?:a|that|those|up to (?:two|one|\\d+))[^.]*(?:permanent|creature|land|nonland)[^.]*cards?[^.]*onto the battlefield|put a permanent card[^.]*onto the battlefield|put [^.]*land cards?[^.]*onto the battlefield|put (?:an? )?artifact,? (?:creature,? )?(?:or land |and/or land )?card[^.]*from (?:your|their) hand onto the battlefield|put an? [^.]*card[^.]*(?:from your (?:hand|library)|from among them) onto the battlefield",
    },
    {
        "key": "draw_for_each",
        "scope": "you",
        "is_widen_of": "card_draw_engine",
        "regex": "draw a card for each|draw cards equal to the number of|draws? (?:a card |cards )?for each",
    },
    {
        "key": "clone_matters",
        "scope": "you",
        "is_widen_of": "clone_matters",
        "regex": "enter (?:the battlefield )?as a copy of|may have [^.]*enter as a copy|create a copy of the card|is a copy of (?:that|the chosen) card",
    },
    {
        "key": "cost_reduction",
        "scope": "you",
        "is_widen_of": "cost_reduction",
        "regex": "spells?[^.]*cost \\{[wubrg]\\}[^.]*less to cast|cost \\{w\\}, \\{u\\}, \\{b\\}, \\{r\\}, or \\{g\\} less|cost \\{[wubrgc\\d]\\}+ less to cast|cost \\{?\\d+\\}? less to activate|(?:cards you drew this turn|abilities you activate)[^.]{0,40}?cost \\{?\\d|costs? \\{?\\d+\\}? less to cast for each|cost \\{?\\d+\\}? less for each",
    },
    {
        "key": "impulse_top_play",
        "scope": "you",
        # Its own avenue ("Impulse draw (top)") — no longer folded into cast-from-exile,
        # which is now the distinct cast/play-from-exile payoff lane.
        "is_widen_of": "",
        "regex": "exile the top [^.]*card[^.]*(?:you may play|may play (?:it|that card|them))|until (?:your next end step|end of turn|the end of your next turn)[^.]*you may play|exile the top [^.]*card[^.]*your library[^.]*\\.?\\s*you may (?:play|cast)|you may play (?:that|the exiled|those|that card) cards?|you may (?:cast|play) (?:the|those|that) (?:exiled )?cards? this turn|you may (?:cast|play) (?:it|them|that card)[^.]*this turn|you may play (?:that card|those cards?|them) (?:this turn|until)|cast (?:up to two |a )?spells? from among|you may play those cards this turn|top card of your library is[^.]*you may[^.]*(?:cast|play)|play (?:lands? )?(?:and |or )?cast [^.]*from among cards you exiled|you may look at (?:it )?and (?:play|cast)",
    },
    {
        # Extra upkeep STEPS (Obeka, The Ninth Doctor) — each added upkeep step is
        # another instance every "at the beginning of your upkeep" ability triggers
        # in (CR 500.7 / 503 / 603.2), so the whole upkeep-payoff space is doubled.
        # A beginning phase (CR 501) contains the untap, upkeep, AND draw steps, so an
        # extra beginning phase (Sphinx of the Second Sun) re-triggers upkeep too.
        # Narrow OPEN regex; the hand-spec serves the broad upkeep-trigger pool.
        "key": "extra_upkeep",
        "scope": "you",
        "is_widen_of": "",
        "regex": "additional upkeep step|additional beginning phase",
    },
    {
        # Extra END STEPS (Y'shtola Rhul) re-trigger every "at the beginning of your
        # end step" ability (CR 513). An extra ENDING phase (CR 513) likewise contains
        # the end step. Combat / main-phase grants are NOT here — those co-occur as the
        # extra-combat package (Aggravated Assault) owned by extra_combats.
        "key": "extra_end_step",
        "scope": "you",
        "is_widen_of": "",
        "regex": "additional end step|additional ending phase",
    },
    {
        # Extra DRAW STEPS re-trigger "at the beginning of your draw step" abilities
        # (CR 504). Opened by a beginning-phase grant (CR 501 — untap/upkeep/draw) too.
        # The untap step has no triggered-ability payoff pool (its value is the untap
        # itself), so there is no extra_untap_step lane.
        "key": "extra_draw_step",
        "scope": "you",
        "is_widen_of": "",
        "regex": "additional draw step|additional beginning phase",
    },
    {
        "key": "tribe_damage_trigger",
        "scope": "you",
        "is_widen_of": "combat_damage_matters",
        "regex": "whenever (?:one or more|a|another) [A-Z][a-z]+s? you control deal[s]? (?:combat )?damage to (?:a player|an opponent|one of your opponents|each opponent)",
    },
    {
        "key": "combat_damage_to_creature",
        "scope": "any",
        "is_widen_of": "combat_damage_matters",
        "regex": "deals combat damage to (?:a|another|one or more) creatures?\\b|whenever [^.]*deals combat damage to (?:a|another) creature",
    },
    {
        "key": "combat_damage_to_opp",
        "scope": "opponents",
        "is_widen_of": "combat_damage_matters",
        "regex": "deals? combat damage to (?:a player|each opponent|an opponent|that player)",
    },
    {
        "key": "creature_cast_trigger",
        "scope": "any",
        "is_widen_of": "opponent_cast_matters",
        "regex": "whenever (?:you|a player|an opponent|each opponent) casts? a creature spell|whenever (?:a|another) creature spell is cast",
    },
    {
        "key": "spell_copy_matters",
        "scope": "you",
        "is_widen_of": "spell_copy_matters",
        "regex": "copy target (?:permanent|creature|artifact|enchantment|sorcery|instant)[^.]* spell|copy target [^.]*spell you (?:control|cast)|copy (?:it|that spell) (?:three|two|\\d+) times|\\bcasualty\\b|\\breplicate\\b|\\bstorm\\b|\\bconspire\\b|copy that (?:card|spell)[^.]*you may cast (?:the|that) copy",
    },
    {
        "key": "removal_matters",
        "scope": "you",
        "is_widen_of": "removal_matters",
        "regex": "destroy (?:up to (?:one|two|three) )?target (?:[a-z]+ )*(?:creature|permanent|artifact|enchantment|planeswalker|land|battle)|destroy target noncreature|destroy target enchanted creature|destroy (?:all|each)(?: non-?\\w+)? creatures?|deals? (?:\\d+|x) damage to target (?:[a-z]+ )*(?:creature|permanent|planeswalker)|deals? damage equal to [^.]* to target (?:[a-z]+ )*creature|deals? \\d+ damage divided[^.]*among [^.]*target|destroy up to (?:\\w+|x) target|destroy target (?:attacking|blocking|tapped|enchanted) [A-Za-z ]*creature|destroy target [A-Z][a-z]+\\b",
    },
    {
        "key": "exile_removal",
        "scope": "you",
        "is_widen_of": "exile_removal",
        "regex": "exile (?:up to (?:one|two|three|\\w+|x) )?(?:other )?target (?:[a-z]+ )*(?:creature|permanent|artifact|enchantment|planeswalker)|exile [^.]*and target (?:permanent|creature)",
    },
    {
        "key": "team_buff",
        "scope": "you",
        "is_widen_of": "team_buff",
        "regex": "(?:you and )?other \\w+ you control have (?:hexproof|flying|trample|indestructible|protection|ward|deathtouch|lifelink|menace|vigilance|haste|first strike|double strike|reach)|(?:each |all )?creatures? you control(?: that[^.]*?)? (?:gain|gains|have|has) (?:indestructible|protection|hexproof|flying|trample|menace|deathtouch|lifelink|double strike|first strike|vigilance|haste|ward|reach)",
    },
    {
        "key": "venture_matters",
        "scope": "you",
        "is_widen_of": "venture_matters",
        "regex": "\\bdungeons?\\b|room abilities",
    },
    {
        "key": "big_hand_matters",
        "scope": "you",
        "is_widen_of": "big_hand_matters",
        "regex": "(?:five|six|seven|eight) or more cards in (?:your )?hand|maximum hand size|(?:equal to|number of) [^.]*cards in your hand",
    },
    {
        "key": "lifeloss_matters",
        "scope": "opponents",
        "is_widen_of": "lifeloss_matters",
        "regex": "\\b(?:each opponent|each player|target opponent|target player|that player|an opponent|opponents|each of your opponents)(?: each)? loses? (?:exactly )?(?:\\d+ |x |that much )?life\\b",
    },
    {
        # Token-doubling and counter-doubling are inherently DIFFERENT properties — a
        # token doubler wants token MAKERS, a counter doubler wants counter SOURCES — so
        # they are separate lanes, not one coarse "doubling" bucket.
        "key": "token_doubling",
        "scope": "you",
        "is_widen_of": "token_doubling",
        "regex": "twice that many[^.]*tokens?|double the number of [^.]*tokens?",
    },
    {
        "key": "counter_doubling",
        "scope": "you",
        "is_widen_of": "counter_doubling",
        "regex": "that many plus one[^.]*counters?|one or more counters? would be put on|(?:put|placed?) (?:twice that many|that many plus (?:one|\\d+))[^.]*counters?|double the number of [^.]*counters?",
    },
    {
        "key": "dice_matters",
        "scope": "you",
        "is_widen_of": "dice_matters",
        "regex": "roll (?:a|one or more|two|\\d+) (?:[a-z\\-]+ )?(?:d\\d+|dice|die)|reroll (?:any|a|that) (?:die|dice)|result of (?:the|a|your) (?:roll|die)|whenever you roll",
    },
    {
        "key": "specialize_matters",
        "scope": "you",
        "is_widen_of": "specialize_matters",
        "regex": "\\bspecializes?\\b|\\bunspecialize",
    },
    {
        "key": "voltron_matters",
        "scope": "you",
        "is_widen_of": "voltron_matters",
        "regex": "create [^.]*\\bequipment\\b[^.]* token|create [^.]*\\bequipment\\b artifact",
    },
    {
        "key": "bounce_tempo",
        "scope": "you",
        "is_widen_of": "bounce_tempo",
        "regex": "return (?:x )?target (?:creatures?|permanents?|nonland permanents?)[^.]*to (?:its|their) owner.?s.? hands?|return target (?:spell or permanent|permanent or spell)|return [^.]*to (?:its|their) owners?.? hands?|return up to (?:one|two|\\w+) target (?:nonland )?(?:creature|permanent)[^.]*to (?:its|their) owner.?s.? hands?",
    },
    {
        "key": "edict_matters",
        "scope": "each",
        "is_widen_of": "sacrifice_matters",
        "regex": "each opponent sacrifices|whenever an opponent sacrifices|target opponent sacrifices|each player sacrifices|(?:each player|that player|each opponent|target player|target opponent) sacrifices? (?:a|an|two|\\d+|half)|that player sacrifices|controller sacrifices",
    },
    {
        "key": "artifacts_matter",
        "scope": "you",
        "is_widen_of": "artifacts_matter",
        "regex": "if you control an artifact|if you control (?:a|an|one or more) artifacts?",
    },
    {
        "key": "self_blink",
        "scope": "you",
        "is_widen_of": "blink_flicker",
        "regex": "exile (?:up to one |another |a |target )?(?:other )?target (?:creature|permanent)[^.]*\\.?\\s*return (?:that|those|it|the[^.]*)[^.]*to the battlefield|exile (?:any number of|all|each)[^.]*creatures[^.]*return|exile [A-Z][a-z']+\\.\\s*return (?:it|that card|them)[^.]*to the battlefield",
    },
    # type_matters_anthem deleted: its `\b(\w+?) creatures get [+]` was subject-LESS and
    # redundant — real typed anthems ("Goblins you control get +1/+1") are produced as
    # subject-bearing type_matters by the parametric detector, and its junk captures
    # ("all/attacking/color creatures get +") belong to anthem_static.
    {
        "key": "group_hug_draw",
        "scope": "each",
        "is_widen_of": "card_draw_engine",
        "regex": "each player (?:may )?draws?\\b|each player who drew",
    },
)


# Curated (label, avenue) prose per mined sweep axis. Data, not logic.
SWEEP_LABELS: dict[str, tuple[str, str]] = {
    "ability_copy": (
        "Ability copy",
        "ability-copy effects plus permanents with strong activated/triggered abilities to copy",
    ),
    "activated_draw": (
        "Repeatable draw",
        "repeatable activated card draw and ways to untap the source",
    ),
    "affinity_type": (
        "Affinity",
        "cheap artifacts/creatures of the affinity type to slash costs",
    ),
    "all_creatures_kw_grant": (
        "Global keyword grant",
        "symmetric keyword grants — pair with your own evasive board",
    ),
    "alt_cost_keyword": (
        "Alternative-cost keyword",
        "cards sharing the alternative-cost mechanic",
    ),
    "animate_artifact": (
        "Animate artifacts",
        "artifacts to animate plus artifact-creature payoffs",
    ),
    "anthem_static": ("Static anthem", "go-wide creatures to ride the anthem"),
    "attractions_matter": ("Attractions", "attraction openers and visit payoffs"),
    "aura_equip_kw_grant": (
        "Aura/Equipment keyword grant",
        "Auras and Equipment that gain keywords to suit up",
    ),
    "base_pt_set": (
        "Set base power/toughness",
        "set-P/T effects and creatures that exploit them",
    ),
    "bending_matters": ("Bending (Avatar)", "bending cards across the four elements"),
    "blocked_matters": (
        "Blocks matter",
        "combat triggers when creatures block or become blocked",
    ),
    "boast_matters": ("Boast", "boast creatures and ways to attack safely"),
    "cant_block_grant": ("Can't-block", "force blockers off to clear a path to attack"),
    "cast_as_named_card": ("Cast-as", "play cards as though they were another card"),
    "changeling_matters": (
        "Changeling / all types",
        "all-creature-type cards for tribal overlap",
    ),
    "cmdzone_ability": (
        "Command-zone ability",
        "command-zone activations and commander recursion",
    ),
    "coin_flip": ("Coin flips", "coin-flip payoffs plus flip-fixing"),
    "color_change": (
        "Color change",
        "color-changing effects for protection and devotion",
    ),
    "combat_buff_engine": ("Beginning-of-combat buff", "attackers to grow each combat"),
    "combat_damage_to_creature": (
        "Combat damage to creatures",
        "evasive/first-strike/deathtouch attackers that connect with creatures",
    ),
    "combat_damage_to_opp": (
        "Combat damage to opponents",
        "evasive attackers and extra combats to connect",
    ),
    "commander_matters": (
        "Commander matters",
        "cast-from-command-zone payoffs and commander protection",
    ),
    "conditional_self_protection": (
        "Conditional protection",
        "ways to satisfy the commander's protection condition",
    ),
    "conjure_matters": ("Conjure", "conjure effects (Alchemy)"),
    "convoke_matters": ("Convoke", "wide, cheap creatures to convoke out big spells"),
    "count_anthem": ("Count anthem", "go-wide creatures to scale the count-based pump"),
    "counter_distribute": (
        "Counter distribution",
        "spread +1/+1 counters across your whole board",
    ),
    "counter_grants_kw": (
        "Counters grant keywords",
        "+1/+1 counter sources to turn on the keyword grant",
    ),
    "counter_manipulation": (
        "Counter manipulation",
        "remove or relocate counters for value",
    ),
    "counter_move": ("Counter movement", "move counters between permanents"),
    "counter_place_trigger": (
        "Counter-placement triggers",
        "ways to put +1/+1 counters to fire the trigger",
    ),
    "counter_replace_bonus": (
        "Counter doubling",
        "counter-placement sources to double up",
    ),
    "token_doubling": (
        "Token doubling",
        "token MAKERS to multiply plus other token doublers and go-wide payoffs",
    ),
    "counter_doubling": (
        "Counter doubling",
        "+1/+1 counter SOURCES to multiply plus other counter doublers",
    ),
    "creature_cast_trigger": (
        "Creature-cast triggers",
        "cheap creatures to chain the cast trigger",
    ),
    "creature_ping": ("Power-based ping", "high-power creatures to ping with"),
    "damage_doubling": ("Damage doubling", "burn and big hits to double"),
    "damage_equal_power": (
        "Power-as-damage",
        "high-power creatures to fling as damage",
    ),
    "damage_prevention": (
        "Damage prevention / fog",
        "fogs and prevention to blank attacks and burn",
    ),
    "damage_redirect": ("Damage redirection", "redirect effects to protect and punish"),
    "damage_reflect": ("Damage reflection", "high-toughness bodies to reflect damage"),
    "damage_to_you_punish": (
        "Punish damage to you",
        "take damage and punish the source",
    ),
    "debuff_matters": (
        "-1/-1 / shrink",
        "minus-counter and toughness-shrink removal plus payoffs",
    ),
    "destroy_legendary": ("Legend removal", "targeted destruction of legends"),
    "devour_matters": ("Devour", "token fodder to devour"),
    "dies_recursion": (
        "Dies-recursion",
        "anything that makes creatures recur when they die — with or without counters "
        "(undying/persist plus bare dies-return like Feign Death)",
    ),
    "dig_until": ("Dig-until", "deep top-of-library digging effects"),
    "discard_outlet": (
        "Discard outlets",
        "loot/rummage outlets to fuel discard and graveyard payoffs",
    ),
    "domain_matters": ("Domain", "basic land types and fixing to grow domain"),
    "donate_matters": ("Donate", "give away downside permanents for advantage"),
    "draft_spellbook": (
        "Draft / spellbook",
        "draft-a-card and spellbook effects (Alchemy)",
    ),
    "draw_for_each": ("Scaling card draw", "grow the count your draw scales with"),
    "each_mode_player": ("Spread-the-modes", "modal effects that hit each player"),
    "edict_matters": (
        "Edicts / forced sacrifice",
        "edicts to make opponents sacrifice",
    ),
    "evasion_denial": (
        "Anti-landwalk defense",
        "strip an opponent's landwalk so you can block (CR 702.14)",
    ),
    "excess_damage": ("Excess damage", "trample and big hits to exploit excess damage"),
    "exhaust_matters": ("Exhaust", "exhaust abilities (once per game)"),
    "exile_until_leaves": ("O-Ring removal", "exile-until-leaves removal effects"),
    "explore_matters": ("Explore", "explore creatures plus counter/graveyard payoffs"),
    "extra_land_drop": (
        "Put lands into play",
        "lands to drop straight onto the battlefield",
    ),
    "facedown_matters": (
        "Face-down / morph",
        "morph/manifest/disguise creatures and flip payoffs",
    ),
    "fight_matters": ("Fight", "big creatures to fight with as removal"),
    "flash_grant": ("Flash", "flash enablers and instant-speed threats"),
    "flip_meld_matters": ("Flip / meld", "the pieces to flip or meld"),
    "forced_attack": ("Forced attacks / politics", "goad-style forced-attack effects"),
    "free_cast": ("Free / alternative cost", "expensive bombs to cast for free"),
    "global_ability_grant": (
        "Global ability grant",
        "a board that exploits the granted ability",
    ),
    "group_hug_draw": ("Group draw", "symmetric draw plus punisher payoffs"),
    "group_mana": ("Group ramp", "shared-mana effects and big payoffs to spend it"),
    "hand_disruption": ("Hand disruption", "peek-and-strip effects against opponents"),
    "impulse_top_play": ("Impulse draw (top)", "top-of-library exile-and-play engines"),
    "keyword_counter": (
        "Keyword counters",
        "keyword-ability counter sources and payoffs (CR 122.1b)",
    ),
    "keyword_grant_target": (
        "Targeted keyword grant",
        "creatures worth granting evasion/protection",
    ),
    "keyword_soup": ("Keyword soup", "many-keyword threats to buff together"),
    "legend_rule_off": (
        "Legend-rule off",
        "duplicate legends to abuse without the legend rule",
    ),
    "life_total_set": ("Life-total swing", "set/exchange-life effects and payoffs"),
    "ltb_matters": (
        "Leaves-the-battlefield",
        "sacrifice and blink fodder to trigger LTB",
    ),
    "lure_matters": ("Lure", "lure effects plus deathtouch/trample to punish blocks"),
    "mass_bounce": ("Mass bounce", "board-wide bounce and ETB re-use"),
    "mass_removal": ("Board wipes", "sweepers plus resilience to rebuild"),
    "miracle_grant": ("Miracle", "miracle support and top-deck setup"),
    "myriad_grant": ("Myriad", "attackers worth copying to each opponent"),
    "named_counter_mechanic": (
        "Named counters",
        "that named-counter mechanic's enablers and payoffs",
    ),
    "named_permanent": (
        "Named-card synergy",
        "the specific named cards this references",
    ),
    "ninjutsu_matters": (
        "Ninjutsu",
        "cheap unblockable creatures to ninja in value bombs",
    ),
    "noncombat_damage_payoff": (
        "Noncombat damage",
        "burn and mana-value-scaling damage outside combat",
    ),
    "noncreature_cast_punish": (
        "Punish noncreature spells",
        "stax and punishers for noncreature casts",
    ),
    "opponent_counter_grant": (
        "Mark opponents",
        "bounty/stun counters on opponents plus payoffs",
    ),
    "opponent_exile_matters": (
        "Opponents' exile",
        "exile opponents' cards and play them",
    ),
    "partner_background": (
        "Partner / Background",
        "a Partner or Background to pair as a second commander",
    ),
    "companion_keyword": (
        "Companion",
        "a companion whose deckbuilding restriction your deck already meets",
    ),
    "phasing_matters": ("Phasing", "phase-out effects for protection and resets"),
    "play_from_top": ("Play from the top", "top-of-library access plus reveal payoffs"),
    "playtest_matters": ("Playtest cards", "Mystery Booster playtest-card effects"),
    "power_double": ("Power doubling", "big creatures to double in power"),
    "powerup_matters": ("Power-up", "power-up counters and payoffs"),
    "protection_grant": (
        "Grant protection",
        "creatures worth protecting with hexproof/protection",
    ),
    "pump_matters": (
        "Combat tricks / pump",
        "instant-speed pump to win combat and push damage",
    ),
    "sacrifice_protection": (
        "Sacrifice protection",
        "key permanents to shield from sacrifice",
    ),
    "saga_matters": ("Sagas", "Sagas plus lore-counter manipulation"),
    "scaling_pump": ("Scaling pump", "go-wide/go-tall payoffs that scale a creature"),
    "secret_writedown": (
        "Wish / outside the game",
        "wishboard and name-a-card effects",
    ),
    "seek_matters": ("Seek", "seek effects (Alchemy tutoring)"),
    "self_blink": (
        "Blink / flicker",
        "your own ETB creatures to flicker for value",
    ),
    "self_counter_grow": (
        "Self +1/+1 growth",
        "counter doublers and ways to grow the commander",
    ),
    "self_pump": ("Firebreathing", "mana sinks to pump and close games"),
    "soulbond_matters": ("Soulbond", "creatures to pair via soulbond"),
    "spell_keyword_grant": (
        "Grant spells keywords",
        "instants/sorceries to give cascade/flashback/etc.",
    ),
    "starting_life_matters": (
        "Starting-life threshold",
        "lifegain/loss to cross the threshold",
    ),
    "station_matters": (
        "Station / Spacecraft",
        "ways to charge and station Spacecraft",
    ),
    "stickers_matter": ("Stickers", "name/ability/art sticker effects"),
    "suspend_matters": (
        "Suspend / time counters",
        "suspend cards plus time-counter manipulation",
    ),
    "symmetric_damage_each": (
        "Symmetric damage",
        "sweepers and pingers that hit everyone",
    ),
    "symmetric_stax": ("Symmetric stax", "asymmetry-breakers to dodge the lock"),
    "tap_down": (
        "Tap-down control",
        "repeatable tappers to lock opponents' permanents",
    ),
    "tap_untap_matters": (
        "Tap/untap triggers",
        "tap and untap effects to fire the trigger",
    ),
    "tapper_engine": ("Tappers / pacifism", "repeatable tappers to neutralize threats"),
    "target_player_draws": (
        "Targeted draw",
        "give-draw effects and the payoffs around them",
    ),
    "targeting_matters": (
        "Targeting / heroic",
        "cheap targeted spells to trigger target-matters",
    ),
    "theft_matters": ("Theft", "steal opponents' cards and cast them"),
    "timing_control": ("Timing control", "end-the-turn and timing-restriction effects"),
    "topdeck_selection": (
        "Top-deck selection",
        "scry and look-at-top to set up your draws (surveil also fills the graveyard)",
    ),
    "topdeck_stack": (
        "Top-deck stacking",
        "put-on-top effects plus play-from-top payoffs",
    ),
    "toughness_combat": (
        "Toughness as power",
        "high-toughness defenders to deal combat damage",
    ),
    "tribal_etb_multi": (
        "Multi-tribe ETB",
        "creatures of the relevant types to chain ETBs",
    ),
    "tribe_damage_trigger": (
        "Tribal combat damage",
        "evasive tribe members to connect",
    ),
    "trigger_doubling": (
        "Trigger doubling",
        "high-value triggered abilities to double",
    ),
    "typed_anthem_multi": ("Multi-type anthem", "creatures of the named types"),
    "typed_enters_punish": (
        "Typed-ETB punisher",
        "creatures of the type to chain the punish trigger",
    ),
    "unspent_mana": ("Unspent mana", "ways to use leftover mana each turn"),
    "variable_pt": (
        "Variable power/toughness",
        "fill the resource your */* scales with",
    ),
    "void_warp_matters": ("Void / warp", "void and warp cards (Edge of Eternities)"),
    "win_lose_game": (
        "Alternate win/lose",
        "alternate win conditions and ways to enable them",
    ),
}
