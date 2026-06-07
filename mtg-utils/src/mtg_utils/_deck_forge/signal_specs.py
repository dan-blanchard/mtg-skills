"""Signal specs: how each scoped signal maps to cards that FEED it.

For every signal the engine recognizes, a ``SignalSpec`` carries:
  - a human ``label`` + an ``avenue`` blurb (the exploration-avenue text),
  - a ``search`` fragment (``card_search`` kwargs that FIND enablers in-identity),
  - a ``serve`` regex (does a given card oracle feed this signal?).

Scope drives the discriminator that matters most: an *opponents'-graveyard* signal
is fed by milling opponents, not yourself — so self-mill does not register as
serving it. This is the deterministic encoding of the Tinybones guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS, SWEEP_LABELS
from mtg_utils.card_classify import get_oracle_text

_IC = re.IGNORECASE


@dataclass(frozen=True)
class Serve:
    """The precise classifier deciding whether a candidate card FEEDS a signal.

    Oracle-regex is the wrong surface for many characteristics — a "cantrip" is an
    Instant or Sorcery that draws (CR 601.2: what you cast is fixed by the card's
    type), prowess is a `keywords[]` entry (CR 702.108a), devotion/voltron live in
    structured fields. So a Serve ORs three precise dimensions over the full card:

      - ``oracle``: a regex on oracle text (the only signal for effects that truly
        live in prose — e.g. magecraft, an ability word with no rules meaning, CR
        207.2c),
      - ``types``: type-line words (lowercased substring, mirroring ``card_search``'s
        ``card_type``) — ``{"instant", "sorcery"}`` is the gate the bare ``draw a
        card`` regex was missing,
      - ``keywords``: authoritative Scryfall ``keywords`` (prowess, flying, …) —
        exact, never regex-guessed out of prose.

    A card serves iff ANY provided dimension matches (the canonical Spellslinger
    case is an OR). ``search(text)`` is a back-compat shim so the oracle regex is
    still directly testable."""

    oracle: re.Pattern[str] | None = None
    types: frozenset[str] = frozenset()
    keywords: frozenset[str] = frozenset()

    def search(self, text: str):
        """Back-compat: raw oracle-regex search over a string (legacy call sites)."""
        return self.oracle.search(text) if self.oracle is not None else None

    def matches(self, card: dict) -> bool:
        """True if the card feeds this signal on ANY structured/oracle dimension."""
        if self.oracle is not None and self.oracle.search(get_oracle_text(card) or ""):
            return True
        if self.types:
            type_line = (card.get("type_line") or "").lower()
            if any(t in type_line for t in self.types):
                return True
        if self.keywords:
            card_kw = {k.lower() for k in (card.get("keywords") or [])}
            if card_kw & self.keywords:
                return True
        return False

    def as_dict(self) -> dict:
        """Serialize for an avenue dict (JSON-safe), so ranking can re-apply the
        SAME precise predicate to candidates it surfaced."""
        out: dict = {}
        if self.oracle is not None:
            out["oracle"] = self.oracle.pattern
        if self.types:
            out["types"] = sorted(self.types)
        if self.keywords:
            out["keywords"] = sorted(self.keywords)
        return out


def serve_from_dict(data: dict) -> Serve:
    """Rebuild a Serve from an avenue dict's stored ``serve`` (or a bare ``search``
    fragment: ``oracle`` + ``card_type``). Used by ranking to classify candidates with
    the same predicate the spec serves on."""
    oracle = data.get("oracle")
    types = data.get("types")
    if types is None and data.get("card_type"):
        types = [data["card_type"]]
    try:
        pattern = re.compile(oracle, _IC) if oracle else None
    except re.error:
        pattern = None
    return Serve(
        oracle=pattern,
        types=frozenset(t.lower() for t in (types or ())),
        keywords=frozenset(k.lower() for k in (data.get("keywords") or ())),
    )


@dataclass(frozen=True)
class SubAvenue:
    """An additional, separately-searchable angle on the same signal. A theme like
    land-creatures has genuinely distinct buckets — be the land-creatures (manlands),
    reward them (payoffs), turn lands into creatures (animators) — each needing its
    own precise search, so one signal fans out into several explorable avenues.

    ``serve`` is the precise classifier for the sub-avenue; when None, ranking falls
    back to the sub-avenue's ``search`` (oracle + card_type), which is correct for the
    many sub-avenues whose effect genuinely only lives in oracle prose."""

    label: str
    avenue: str
    search: dict
    serve: Serve | None = None


@dataclass(frozen=True)
class SignalSpec:
    label: str
    avenue: str
    search: dict  # card_search kwargs fragment (oracle / preset_names / card_type)
    serve: Serve  # the precise classifier (type / keyword / oracle), CR-grounded
    extras: tuple[SubAvenue, ...] = ()  # additional precise sub-avenues (optional)


def _spec(
    label, avenue, search, serve, extras=(), *, serve_types=(), serve_keywords=()
):
    return SignalSpec(
        label=label,
        avenue=avenue,
        search=search,
        serve=Serve(
            oracle=re.compile(serve, _IC) if serve else None,
            types=frozenset(t.lower() for t in serve_types),
            keywords=frozenset(k.lower() for k in serve_keywords),
        ),
        extras=tuple(extras),
    )


# Spellslinger serve, shared by spellcast_matters and magecraft_matters (the SAME
# archetype — magecraft's reminder is "whenever you cast or copy an instant or sorcery
# spell", CR 207.2c). A card FEEDS it by TYPE (Instant/Sorcery — what you cast is fixed
# by the card's type, CR 601.2), by the prowess KEYWORD (CR 702.108a), or by a magecraft
# / cast-trigger in prose. Bare "draw a card" (mislabels ~1250 permanents) and bare
# "instant or sorcery" (mislabels counterspell-shelters like Boseiju and graveyard
# payoffs) are neither, so they are excluded.
_SLINGER_SERVE_ORACLE = (
    r"\bmagecraft\b|whenever you cast (?:an instant|a sorcery|a noncreature|your)"
)
_SLINGER_TYPES = ("instant", "sorcery")
_SLINGER_KEYWORDS = ("prowess",)
_SLINGER_SEARCH_ORACLE = (
    r"\bmagecraft\b|\bprowess\b"
    r"|whenever you cast (?:an instant|a sorcery|a noncreature|your)"
    r"|instant and sorcery spells you cast"
)


SPECS: dict[tuple[str, str], SignalSpec] = {
    ("creature_etb", "you"): _spec(
        "Creatures entering — yours",
        "cheap ways to flood your board with creatures",
        {
            "oracle": (
                r"create .*creature token"
                r"|put .*creature card.*onto the battlefield"
            )
        },
        (r"create .*creature token|put .*creature.*onto the battlefield"),
    ),
    # Serve was `opponent.*creature.*enters` — which requires "opponent" BEFORE
    # "creature", so it matched Bloodthirst ("an opponent was dealt damage … this
    # creature enters") and MISSED the real punisher, "a creature an opponent controls
    # enters" (creature before opponent). Align serve to the (correct) search anchor.
    ("creature_etb", "opponents"): _spec(
        "Creatures entering — opponents'",
        "punish creatures your opponents play",
        {"oracle": r"whenever a creature an opponent controls enters"},
        r"creature an opponent controls enters"
        r"|creatures? your opponents control enter",
    ),
    ("creatures_matter", "you"): _spec(
        "Go wide",
        "token swarms and anthems that scale with creature count",
        {"oracle": r"create .*creature token"},
        r"create .*creature token|creatures you control get",
    ),
    # Land-creatures theme (e.g. Jyoti, Moag Ancient). Three precise, disjoint
    # angles — proven clean against bulk so a Plant-token maker (Avenger) or a
    # clone (Silent Hallcreeper) is never surfaced:
    #   main   — creature-lands: a Land that "becomes a … creature" (manlands)
    #   extra  — payoffs: cards that reference "land creature(s)" (anthems)
    #   extra  — animators: effects that turn YOUR lands into creatures
    ("land_creatures_matter", "you"): _spec(
        "Creature-lands",
        "lands that are or become creatures — the backbone of a land-creatures deck",
        {"card_type": "Land", "oracle": r"becomes a [^.]*creature"},
        r"\bland creatures?\b",
        extras=(
            SubAvenue(
                "Land-creature payoffs",
                "anthems and abilities that specifically pump land creatures",
                {"oracle": r"\bland creatures?\b"},
            ),
            SubAvenue(
                "Animate your lands",
                "effects that turn lands you control into creatures",
                {"oracle": r"lands? you control[^.]*become[^.]*creature"},
            ),
        ),
    ),
    ("graveyard_matters", "opponents"): _spec(
        "Opponents' graveyards",
        "mill opponents and punish their graveyards (NOT self-mill)",
        {"oracle": r"each opponent mills|target opponent mills|opponent.*mills"},
        r"opponent[^.]*\bmill|mill[^.]*opponent|each opponent[^.]*graveyard",
    ),
    ("graveyard_matters", "you"): _spec(
        "Your graveyard",
        "self-mill and recursion fuel for your own graveyard",
        {"oracle": r"into your graveyard|surveil"},
        r"into your graveyard|from your graveyard|surveil\b|self-mill",
    ),
    # Lifegain. The bare `lifelink` oracle word matched any card listing it (Crystalline
    # Giant's random-counter menu, reminder text). Lifelink is a keyword (CR 702.15), so
    # gate on keywords[]; a card that GRANTS lifelink to the team still serves via the
    # grant oracle branch. Keep the actual gain-life clauses.
    ("lifegain_matters", "you"): _spec(
        "Lifegain",
        "incidental and repeatable lifegain",
        {"oracle": r"gain .* life"},
        r"gain \d+ life|gain x life|gains? [^.]*\blife\b"
        r"|whenever[^.]*gain[^.]*life"
        r"|(?:creatures? you control|enchanted creature|equipped creature|they)"
        r"[^.]*\blifelink\b|(?:gain|gains|have|has) lifelink",
        serve_keywords=("lifelink",),
    ),
    ("counters_matter", "any"): _spec(
        "+1/+1 counters",
        "counter generators and proliferate",
        {"oracle": r"\+1/\+1 counter"},
        r"\+1/\+1 counter|proliferate",
    ),
    # Hand spec (overrides the mined sweep detector) so the avenue can fan out a
    # dedicated "Flip fixing" sub-avenue. The flat coin-flip search returns ~60 generic
    # "flip a coin" payoffs and buries Krark's-Thumb-style fixers past the package cap,
    # even though fixing flips is the whole point of a coin-flip deck.
    ("coin_flip", "any"): _spec(
        "Coin flips",
        "coin-flip payoffs and outlets",
        {
            "oracle": (
                r"flip a coin|flip (?:two|three|\d+) coins"
                r"|flip (?:one or more|a number of) coins"
                r"|wins? (?:the|a) (?:coin )?flip|lose (?:the|a) (?:coin )?flip"
                r"|come up heads"
            )
        },
        (
            r"flip a coin|flip (?:two|three|\d+) coins"
            r"|flip (?:one or more|a number of) coins"
            r"|wins? (?:the|a) (?:coin )?flip|lose (?:the|a) (?:coin )?flip"
            r"|come up heads"
        ),
        extras=(
            # A flip FIXER either re-flips/ignores (the Krark's Thumb family) or
            # declaratively GRANTS the result ("come up heads AND you win", Edgar). The
            # bare branches `come up heads` / `you win … flip` (e21b7d6) wrongly caught
            # PAYOFFS that reference a flip result as a CONDITION: Mana Clash ("come up
            # heads on the same flip"), Two-Headed Giant ("if both come up heads"),
            # Squee's Revenge ("if you win all the flips, draw"). A regex can't separate
            # a grant from a condition, so we match only the declarative grant. Verified
            # against bulk: this yields EXACTLY {Krark's Thumb, Edgar}.
            SubAvenue(
                "Flip fixing",
                "cards that bias, repeat, or ignore unfavorable coin flips "
                "(Krark's Thumb effects)",
                {
                    "oracle": (
                        r"instead flip [^.]*coin|\breflip"
                        r"|flip [^.]*coins? again|flip an additional coin"
                        r"|come up heads and you win"
                    )
                },
            ),
        ),
    ),
    ("draw_matters", "you"): _spec(
        "Draw triggers / wheels",
        "draw-trigger payoffs and extra-draw engines (Nekusar / Chasm Skulker space)",
        {"oracle": r"whenever you draw|draw an additional card"},
        r"whenever you draw|draws? (?:your )?(?:second|an additional) card",
    ),
    # Spellslinger. A card FEEDS this iff casting it is "casting an instant or sorcery"
    # — fixed by its TYPE (CR 601.2), OR it has prowess (CR 702.108a, a keyword payoff),
    # OR it carries a magecraft / "whenever you cast a (noncreature|instant|sorcery)
    # spell" trigger (magecraft is an ability word — CR 207.2c — so it lives ONLY in
    # prose). Bare "draw a card" is none of these: it mislabeled ~1250 value permanents
    # (Rhystic Study, Esper Sentinel, The One Ring) as Spellslinger. Copies aren't cast
    # (CR 707.10), so spell-copy payoffs belong to spell_copy, not here.
    ("spellcast_matters", "you"): _spec(
        "Spellslinger",
        "cheap instants/sorceries plus magecraft/prowess payoffs to chain casts",
        {"oracle": _SLINGER_SEARCH_ORACLE},
        _SLINGER_SERVE_ORACLE,
        serve_types=_SLINGER_TYPES,
        serve_keywords=_SLINGER_KEYWORDS,
        extras=(
            SubAvenue(
                "Cheap instants (fuel)",
                "cheap instants to chain casts and trigger your payoffs",
                {"card_type": "Instant", "cmc_max": 3},
                serve=Serve(types=frozenset({"instant"})),
            ),
            SubAvenue(
                "Cheap sorceries (fuel)",
                "cheap sorceries to chain casts and trigger your payoffs",
                {"card_type": "Sorcery", "cmc_max": 3},
                serve=Serve(types=frozenset({"sorcery"})),
            ),
        ),
    ),
    # `create .*token` was type-blind — it served every Treasure/Clue/Food maker
    # (~428 in WBR), none of which are sacrifice fodder. Require the literal "creature
    # token" (CR 111.10 token types); and exclude "sacrifice a land" (fetchlands) from
    # the outlet branch.
    ("sacrifice_matters", "you"): _spec(
        "Sacrifice — fodder & outlets",
        "token fodder and free sacrifice outlets",
        {"oracle": r"create [^.]*creature token|sacrifice"},
        r"create [^.]*creature token|sacrifice (?:a|an|another)(?! land\b)",
    ),
    ("death_matters", "any"): _spec(
        "Aristocrats",
        "creatures dying as a resource — fodder plus drain payoffs",
        {"oracle": r"create [^.]*creature token|whenever .* dies"},
        r"create [^.]*creature token|sacrifice (?:a|an|another)(?! land\b)"
        r"|whenever .* dies",
    ),
    ("attack_matters", "you"): _spec(
        "Combat",
        "haste enablers and evasive/aggressive bodies",
        {"oracle": r"haste|create .*creature token"},
        r"haste|create .*creature token",
    ),
    # The bare `onto the battlefield` branch matched every cheat-into-play and
    # reanimation effect (Sneak Attack, Reanimate). Anchor it to a LAND card, mirroring
    # lands_matter (CR 305 — landfall fires on a land entering, not any permanent).
    ("landfall", "you"): _spec(
        "Landfall",
        "extra land drops and land fetch",
        {
            "oracle": (
                r"search your library for .*\bland\b"
                r"|play (?:an|one|two|\d+) additional lands?"
                r"|put .*\bland card.*onto the battlefield"
            )
        },
        (
            r"search your library for .*\bland\b"
            r"|play (?:an|one|two|\d+) additional lands?"
            r"|put .*\bland card.*onto the battlefield"
        ),
    ),
    # ── Archetype floor specs (whole themes the baseline was blind to) ──────────
    ("token_maker", "you"): _spec(
        "Token generators",
        "more cards that flood the board with creature tokens",
        {"oracle": r"create [^.]*creature token"},
        r"create [^.]*creature token",
    ),
    ("treasure_matters", "you"): _spec(
        "Treasure",
        "Treasure makers for ramp, fixing, and artifact synergy",
        {"oracle": r"create [^.]*treasure token|treasures? you control"},
        r"\btreasure\b",
    ),
    ("artifacts_matter", "you"): _spec(
        "Artifacts",
        "artifacts and artifact-count payoffs",
        {"card_type": "Artifact"},
        r"artifacts? you control|for each artifact|\bmetalcraft\b|\baffinity\b",
    ),
    ("enchantments_matter", "you"): _spec(
        "Enchantments",
        "enchantments and enchantment-count payoffs",
        {"card_type": "Enchantment"},
        r"enchantments? you control|for each enchantment|\bconstellation\b",
    ),
    ("tokens_matter", "you"): _spec(
        "Tokens matter",
        "token makers and payoffs that scale with tokens you control",
        {"oracle": r"create [^.]*token"},
        r"\btokens? you control\b|whenever .*token.*enters|\bpopulate\b",
    ),
    # The bare `your opponents` alternative matched any card that merely names opponents
    # (Edric's draw trigger, Telepathy's hand reveal). Serve the actual restriction/tax
    # SHAPES instead (CR 601.2f cost increases, prohibitions) — which also recovers the
    # symmetric taxes the old regex missed (Thalia: "Noncreature spells cost {1} more").
    ("stax_taxes", "opponents"): _spec(
        "Stax & taxes",
        "tax and restriction effects aimed at your opponents",
        {
            "oracle": (
                r"opponents? can't"
                r"|spells your opponents cast cost"
                r"|creatures your opponents control"
            )
        },
        r"opponents? can't"
        r"|(?:players?|that player|each player) can't (?:cast|activate|attack|block|"
        r"untap|search|draw|play)"
        r"|spells?[^.]*cost \{?\d+\}? more|noncreature spells?[^.]*cost \{?\d"
        r"|creatures your opponents control"
        r"|(?:your opponents control|nonbasic lands?) enters?"
        r"(?: the battlefield)? tapped",
    ),
    ("blink_flicker", "you"): _spec(
        "Blink / flicker",
        "exile-and-return effects to re-use enter-the-battlefield abilities",
        {"preset_names": ("blink",)},
        r"exile[^.]*?return[^.]*?battlefield",
    ),
    ("mill_matters", "any"): _spec(
        "Mill",
        "cards that mill — fuel a graveyard or grind a library",
        {"preset_names": ("mill",)},
        r"\bmills?\b",
    ),
    ("goad_matters", "opponents"): _spec(
        "Goad & politics",
        "goad and forced-attack effects that point creatures at your opponents",
        {"preset_names": ("goad",)},
        r"\bgoad",
    ),
    ("proliferate_matters", "you"): _spec(
        "Proliferate",
        "proliferate plus any-kind counter sources (poison/loyalty/charge/+1+1)",
        {"preset_names": ("proliferate",)},
        r"\bproliferate\b|(?:poison|loyalty|charge|oil|\+1/\+1) counter",
    ),
    # Same archetype + matcher as spellcast_matters (a magecraft commander triggers off
    # the same instants/sorceries as a prowess one). Was the canonical bug twice over:
    # a "draw a card" search and an "instant or sorcery" serve branch that credited
    # counterspell-shelters and graveyard payoffs.
    ("magecraft_matters", "you"): _spec(
        "Magecraft / spellslinger",
        "cheap instants and sorceries plus magecraft/prowess payoffs to chain casts",
        {"oracle": _SLINGER_SEARCH_ORACLE},
        _SLINGER_SERVE_ORACLE,
        serve_types=_SLINGER_TYPES,
        serve_keywords=_SLINGER_KEYWORDS,
    ),
    ("extra_combats", "you"): _spec(
        "Extra combats",
        "additional combat phases and the attackers to exploit them",
        {"oracle": r"additional combat phase|extra combat"},
        r"additional combat|extra combat",
    ),
    ("extra_turns", "you"): _spec(
        "Extra turns",
        "additional-turn effects",
        {"oracle": r"extra turn|additional turn|take an extra"},
        r"extra turn|additional turn",
    ),
    # ── Rules mined from the zero-signal commander tail ─────────────────────────
    # Serve the payoff trigger (CR 510 combat damage) + true-unblockable enablers. The
    # bare `\bmenace\b` matched every menace creature AND the menace/flying REMINDER
    # "can't be blocked except by …" — surfacing vanilla evasive bodies, not connect
    # payoffs. Drop it; gate `can't be blocked` against the "except" reminder.
    ("combat_damage_matters", "opponents"): _spec(
        "Combat damage",
        "evasive attackers and extra-combat enablers to keep connecting",
        {"oracle": r"can't be blocked|\bmenace\b|\bflying\b|additional combat"},
        r"deals combat damage to (?:a player|an opponent|one of your opponents"
        r"|each opponent)|can't be blocked(?! except)|\bunblockable\b",
    ),
    ("cost_reduction", "you"): _spec(
        "Cost reduction",
        "expensive bombs and X-spells that exploit the discount",
        {"oracle": r"\{x\}|with mana value"},
        r"\{x\}|mana value \d|\bstorm\b",
    ),
    ("cast_from_exile", "you"): _spec(
        "Impulse / cast-from-exile",
        "impulse-draw enablers and cast-from-exile payoffs",
        {"oracle": r"from the top of your library|from exile"},
        r"from the top of your library|from exile|\bplot\b",
        extras=(
            SubAvenue(
                "Top-of-library engines",
                "cards that let you play off the top of your library",
                {"oracle": r"from the top of your library"},
            ),
        ),
    ),
    ("discard_matters", "you"): _spec(
        "Discard",
        "loot/connive discard outlets and discard payoffs",
        {"oracle": r"discard (?:a|an|two|your hand)[^:.]*?:|draw [^.]*?then discard"},
        r"whenever you discard|discard (?:a|an|two|your hand)[^:.]*?:"
        r"|draw [^.]*then discard",
    ),
    # Drain. The serve required "opponent" adjacent to "loses", so it MISSED the
    # keystone aristocrats drains worded "target/that player loses N life" (Blood
    # Artist, Falkenrath Noble). Add the player-loses branch; "each player" is excluded
    # to keep symmetric self-damage out of the opponents-drain avenue.
    ("lifeloss_matters", "opponents"): _spec(
        "Drain",
        "repeatable life-drain and aristocrats payoffs",
        {"oracle": r"each opponent loses|target opponent loses|whenever .* dies"},
        r"opponent[^.]*loses [^.]*life|whenever an opponent loses life|\bextort\b"
        r"|(?:target player|that player|a player) loses? [^.]*\blife\b",
    ),
    ("lifeloss_matters", "you"): _spec(
        "Self life-loss",
        "ways to pay or lose life on demand to fuel your payoffs",
        {"oracle": r"you lose \d+ life|pay \d+ life|lose \d+ life"},
        r"whenever you lose life|you lose \d+ life|pay \d+ life",
    ),
    ("lands_matter", "you"): _spec(
        "Lands matter",
        "ramp, extra land drops, and recursion to maximize your land count",
        {
            "oracle": (
                r"search your library for .*land"
                r"|play an additional land"
                r"|put .*land card.*onto the battlefield"
            )
        },
        r"the number of lands you control|for each land you control"
        r"|play an additional land",
    ),
    # An ENGINE is recurring or bulk draw — NOT a one-shot cantrip. The serve's
    # `draw \w+ cards?` let \w+ eat the article in "draw a card", mislabeling ~753
    # one-shot cantrips (Remand, Cryptic Command) as engines — contradicting the
    # extractor's own _CARD_DRAW_RE. Mirror that: a recurring "at the beginning of …
    # draw" OR a bulk 2+ / additional draw. (Single-draw permanents like Rhystic Study
    # are surfaced by their own triggers' signals, not this avenue.)
    ("card_draw_engine", "you"): _spec(
        "Card-advantage engine",
        "protection, recursion, and payoffs for a repeatable draw engine",
        {"preset_names": ("card-draw",)},
        r"at the beginning of [^.]*\bdraws? "
        r"(?:a|an|two|three|four|five|six|seven|eight|nine|ten|x|\d+)[^.]*\bcard"
        r"|draws? (?:two|three|four|five|six|seven|eight|nine|ten|x|\d+) cards?"
        r"|draw cards equal to|draws? an additional card",
    ),
    ("card_draw_engine", "each"): _spec(
        "Group draw / wheel",
        "symmetric draw with punisher payoffs (Nekusar-style)",
        {"oracle": r"each player draws|whenever .* draws a card"},
        r"each player draws|draws? an additional card",
    ),
    ("direct_damage", "you"): _spec(
        "Burn / pingers",
        "repeatable direct damage — pingers, burn, and damage doublers",
        {"preset_names": ("burn",)},
        r"deals \d+ damage to any target|\{t\}[^.]*deals .*damage|double the damage",
    ),
    ("mana_amplifier", "you"): _spec(
        "Big mana",
        "mana doublers plus the X-spells and expensive bombs to spend it on",
        {"oracle": r"\{x\}|add .* mana|search your library for .*land"},
        r"tap.*for mana.*add|add .* mana of any|\{x\}",
    ),
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    ("voltron_matters", "you"): _spec(
        "Voltron / equipment & auras",
        "equipment, auras, equip-cost reducers, and tutors to suit up one creature",
        {"preset_names": ("equip",)},
        r"equipped creature|enchanted creature gets|equip \{"
        r"|attach [^.]*(?:equipment|aura)"
        r"|equipment you control|for each (?:equipment|aura)",
    ),
    ("vehicles_matter", "you"): _spec(
        "Vehicles",
        "Vehicle bodies plus crew payoffs, lords, and cheap creatures to crew them",
        {"preset_names": ("crew",)},
        r"\bvehicles? you control\b|\bcrew\b|create [^.]*vehicle artifact",
    ),
    ("scry_surveil_matters", "you"): _spec(
        "Scry / surveil matters",
        "scry and surveil to fire these payoffs — note surveil also fills your "
        "graveyard (see Your graveyard), while scry is pure top-of-library selection",
        {"oracle": r"\b(?:scry|surveil)\b"},
        r"\b(?:scry|surveil)\b",
    ),
    # ── Named-mechanic long tail ────────────────────────────────────────────────
    ("monarch_matters", "you"): _spec(
        "Monarch",
        "become and defend the monarch — evasion and combat-damage triggers",
        {"oracle": r"\bthe monarch\b|becomes? the monarch"},
        r"\bthe monarch\b",
    ),
    ("initiative_matters", "you"): _spec(
        "Initiative",
        "take and hold the initiative; venture through the Undercity",
        {"oracle": r"\bthe initiative\b|undercity"},
        r"\bthe initiative\b",
    ),
    ("ring_matters", "you"): _spec(
        "The Ring",
        "Ring-bearer payoffs and ways to tempt you with the Ring",
        {"oracle": r"ring tempts you|ring-bearer"},
        r"ring tempts you|ring-bearer",
    ),
    ("venture_matters", "you"): _spec(
        "Venture / dungeons",
        "venture enablers and dungeon-completion payoffs",
        {"oracle": r"venture into the dungeon|\bdungeon\b"},
        r"venture into the dungeon|\bdungeon\b",
    ),
    ("energy_matters", "you"): _spec(
        "Energy",
        "energy makers and energy sinks",
        {"oracle": r"\{e\}|energy counter"},
        r"\{e\}|energy counter",
    ),
    ("devotion_matters", "you"): _spec(
        "Devotion",
        "heavy colored pips to grow devotion and devotion payoffs",
        {"oracle": r"devotion to"},
        r"devotion to",
    ),
    ("superfriends_matters", "you"): _spec(
        "Superfriends",
        "planeswalkers plus proliferate and loyalty payoffs to protect them",
        {"oracle": r"planeswalker|loyalty"},
        r"planeswalkers? you control|loyalty counters?",
    ),
    ("historic_matters", "you"): _spec(
        "Historic",
        "artifacts, legendaries, and Sagas — the historic permanents that trigger it",
        {"oracle": r"\bhistoric\b|\blegendary\b|\bsaga\b"},
        r"\bhistoric\b",
    ),
    ("legends_matter", "you"): _spec(
        "Legends matter",
        "legendary creatures and the payoffs that reward a board of legends",
        {"oracle": r"\blegendary\b"},
        r"legendary creatures? you control|another legendary|for each legendary",
    ),
    ("big_hand_matters", "you"): _spec(
        "Big hand / no max hand size",
        "card draw and no-max-hand-size payoffs that reward a full grip",
        {"oracle": r"cards in your hand|no maximum hand size"},
        r"maximum hand size|cards in your hand",
    ),
    ("party_matters", "you"): _spec(
        "Party",
        "Clerics, Rogues, Warriors, and Wizards to assemble a full party",
        {"oracle": r"your party|assemble.*party|\bcleric|\brogue|\bwarrior|\bwizard"},
        r"\bparty\b",
    ),
    ("exile_matters", "you"): _spec(
        "Exile pile matters",
        "impulse/foretell exile enablers and payoffs for cards in exile",
        {"oracle": r"exile the top|in exile|from exile"},
        r"cards? (?:you own )?in exile|for each card[^.]*exile",
    ),
    ("experience_matters", "you"): _spec(
        "Experience counters",
        "ways to gain experience counters and scale with them",
        {"oracle": r"experience counter"},
        r"experience counter",
    ),
    ("poison_matters", "opponents"): _spec(
        "Poison / infect",
        "infect and toxic threats plus proliferate to finish with poison",
        {"oracle": r"\binfect\b|\btoxic\b|poison counter|proliferate"},
        r"poison counter|\binfect\b|\btoxic\b",
    ),
    ("modified_matters", "you"): _spec(
        "Modified",
        "counters, Auras, and Equipment to keep creatures modified",
        {"oracle": r"\bmodified\b|\+1/\+1 counter|aura or equipment"},
        r"\bmodified\b",
    ),
    ("mutate_matters", "you"): _spec(
        "Mutate",
        "mutate creatures and mutate-trigger payoffs",
        {"oracle": r"\bmutate\b"},
        r"\bmutate\b",
    ),
    ("food_matters", "you"): _spec(
        "Food",
        "Food makers plus sacrifice outlets and lifegain payoffs",
        {"oracle": r"\bfood token|foods? you control|sacrifice a food"},
        r"\bfood token|foods? you control|sacrifice a food",
    ),
    ("clue_matters", "you"): _spec(
        "Clues / investigate",
        "investigate enablers and artifact/draw payoffs for Clues",
        {"oracle": r"\bclue\b|investigate"},
        r"\bclue\b|investigate",
    ),
    ("blood_matters", "you"): _spec(
        "Blood tokens",
        "Blood makers plus rummage and sacrifice payoffs",
        {"oracle": r"blood token"},
        r"blood token",
    ),
    ("daynight_matters", "you"): _spec(
        "Day / Night",
        "daybound/nightbound creatures and day-night transition payoffs",
        {"oracle": r"\bdaybound\b|\bnightbound\b|\bday\b|\bnight\b"},
        r"daybound|nightbound|becomes night|becomes day",
    ),
    ("voting_matters", "each"): _spec(
        "Voting / council",
        "will-of-the-council and vote effects — multiplayer politics",
        {"oracle": r"\bvote\b|will of the council|council's dilemma"},
        r"\bvote\b|will of the council",
    ),
    ("coven_matters", "you"): _spec(
        "Coven",
        "creatures with different powers to turn on coven",
        {"oracle": r"\bcoven\b|different powers"},
        r"\bcoven\b",
    ),
    ("doubling_matters", "you"): _spec(
        "Doubling",
        "token/counter doublers and the payoffs that exploit doubled output",
        {"oracle": r"twice that many|double the (?:number|amount)"},
        r"twice that many|double the (?:number|amount)",
    ),
    # Serve is precise (the second-spell payoff). The SEARCH carried the same bare
    # "draw a card" FP; narrow it to the payoffs (second/third spell, multi-spell,
    # storm) so the avenue stops crediting every value permanent that draws.
    ("second_spell_matters", "you"): _spec(
        "Second-spell / storm-lite",
        "second-spell, multi-spell, and storm payoffs that reward chaining casts",
        {
            "oracle": (
                r"(?:second|third) spell you cast|cast your (?:second|third) spell"
                r"|cast two or more spells|\bstorm\b"
            )
        },
        r"(?:second|third) spell you cast|cast your (?:second|third) spell",
    ),
    # ── Mechanics recovered from the "rejected" families ────────────────────────
    ("token_copy_matters", "you"): _spec(
        "Token copies",
        "strong creatures to copy plus token-copy and populate engines",
        {"oracle": r"token that's a copy|tokens? that are copies|\bpopulate\b"},
        r"tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of|\bpopulate\b",
    ),
    ("specialize_matters", "you"): _spec(
        "Specialize",
        "specialize payoffs to swap a creature's stat/ability line "
        "(Backgrounds are a separate axis — see Partner / Background)",
        {"oracle": r"\bspecialize\b"},
        r"\bspecialize\b",
    ),
    ("dice_matters", "you"): _spec(
        "Dice rolling",
        "dice-rolling enablers and roll-result payoffs",
        {"oracle": r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|\bd20\b"},
        r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|whenever you roll",
    ),
    ("crimes_matter", "you"): _spec(
        "Crimes",
        "targeted removal and abilities that count as committing a crime",
        {"oracle": r"commit a crime|target (?:opponent|player)|target.*spell"},
        r"commit(?:s|ted)? a crime|whenever you commit",
    ),
    ("connive_matters", "you"): _spec(
        "Connive",
        "connive enablers and counter/discard payoffs",
        {"oracle": r"\bconnives?\b|draw a card, then discard"},
        r"\bconnives?\b",
    ),
    ("spell_copy_matters", "you"): _spec(
        "Spell copy",
        "impactful instants/sorceries plus copy effects to multiply your spells",
        {"oracle": r"copy (?:target|that)|instant or sorcery|\bstorm\b"},
        r"copy target (?:instant|sorcery|spell)|\bcopy that spell\b|\bstorm\b",
    ),
    # ── Effect-axis specs ───────────────────────────────────────────────────────
    ("ramp_matters", "you"): _spec(
        "Ramp / big mana",
        "mana rocks, dorks, and land ramp to accelerate into your payoffs",
        {"oracle": r"add \{|search your library for .*\bland\b"},
        r"\{t\}[^.]*:\s*add|add .* mana|search your library for .*\bland\b",
    ),
    ("removal_matters", "you"): _spec(
        "Removal / interaction",
        "destroy and burn removal — note indestructible/regeneration blank it",
        {"oracle": r"destroy target|deals .* damage to target"},
        r"destroy target|deals .* damage to target creature",
    ),
    ("exile_removal", "you"): _spec(
        "Exile removal",
        "exile-based removal that bypasses indestructible and stops recursion",
        {"oracle": r"exile target (?:creature|permanent|artifact|enchantment)"},
        r"exile target (?:creature|permanent|artifact|enchantment|nonland)",
    ),
    ("counter_control", "you"): _spec(
        "Counterspells / control",
        "counterspells and stack interaction",
        {"oracle": r"counter target"},
        r"counter target",
    ),
    ("team_buff", "you"): _spec(
        "Team keyword grants",
        "keyword grants and anthems for your board",
        {"oracle": r"creatures you control (?:gain|have)"},
        r"creatures? you control (?:gain|gains|have|has)",
    ),
    ("tutor_matters", "you"): _spec(
        "Tutors",
        "tutors to assemble your key pieces and combos",
        {"oracle": r"search your library for"},
        r"search your library for",
    ),
    ("untap_engine", "you"): _spec(
        "Untap engine",
        "untap effects to reuse tap abilities and generate value",
        {"oracle": r"untap (?:target|all|another|each)"},
        r"untap (?:target|all|another|each)",
    ),
    ("gain_control", "you"): _spec(
        "Theft",
        "steal effects and ways to keep or sacrifice what you take",
        {"oracle": r"gain control of"},
        r"gain control of",
    ),
    ("opponent_discard", "opponents"): _spec(
        "Hand attack",
        "forced discard and hand disruption aimed at opponents",
        {"oracle": r"opponent discards|each player discards|target player discards"},
        r"opponent[^.]*discards|each player discards|target player discards",
    ),
    # Bare `can't be blocked` matched the menace/flying REMINDER "can't be blocked
    # except by …" on vanilla evasive creatures (~673). Exclude the "except" form (a
    # conditional restriction, CR 509.1b, not true unblockable) and add landwalk.
    ("evasion_self", "you"): _spec(
        "Evasion / unblockable",
        "unblockable and evasion to keep connecting — strong for voltron",
        {"oracle": r"can't be blocked|\bunblockable\b"},
        r"can't be blocked(?! except)|\bunblockable\b"
        r"|\b(?:forest|island|mountain|plains|swamp)walk\b",
    ),
    ("clone_matters", "you"): _spec(
        "Clones / copies",
        "clone effects plus strong creatures worth copying",
        {"oracle": r"becomes a copy|copy of (?:target|another)"},
        r"becomes a copy|copy of (?:target|another)",
    ),
    ("cheat_into_play", "you"): _spec(
        "Cheat into play",
        "ways to put big creatures onto the battlefield from hand or library",
        {"oracle": r"onto the battlefield"},
        r"onto the battlefield from your (?:hand|library)"
        r"|put .*creature card.*onto the battlefield",
    ),
    ("bounce_tempo", "you"): _spec(
        "Bounce / tempo",
        "bounce effects for tempo and ETB re-use",
        {"oracle": r"return target .*to (?:its|their) owner's hand"},
        r"return target .*owner's hand",
    ),
    ("cascade_matters", "you"): _spec(
        "Cascade",
        "high-value spells to hit off cascade plus more cascade enablers",
        {"oracle": r"\bcascade\b"},
        r"\bcascade\b",
    ),
    ("regenerate_matters", "you"): _spec(
        "Regenerate / resilience",
        "regeneration and resilience to keep your threats around",
        {"oracle": r"\bregenerate\b"},
        r"\bregenerate\b",
    ),
    ("opponent_cast_matters", "opponents"): _spec(
        "Punish opponents' spells",
        "taxes and punishers that trigger when opponents cast",
        {"oracle": r"whenever an opponent casts|spells? your opponents cast"},
        r"whenever an opponent casts|opponents? cast",
    ),
    ("opponent_draw_matters", "opponents"): _spec(
        "Punish opponents' draw",
        "wheels and draw-denial punishers that trigger on opponents drawing",
        {"oracle": r"whenever an opponent draws|each opponent draws"},
        r"whenever an opponent draws|opponents? draws?",
    ),
    ("opponent_search_matters", "opponents"): _spec(
        "Punish opponents' tutors / selection",
        "stax and punishers for opponents who search, scry, or surveil",
        {"oracle": r"opponent[^.]*(?:search|scry|surveil)|search(?:es)? their library"},
        r"opponent[^.]*(?:scries|surveils|searches)|search their library",
    ),
    ("damage_to_opp_matters", "opponents"): _spec(
        "Damage to opponents",
        "evasion, pingers, and extra combats to keep connecting and fire these "
        "damage-to-opponent triggers (any damage, not just combat)",
        {"oracle": r"can't be blocked|\bmenace\b|\bflying\b|additional combat"},
        r"deals (?:noncombat )?damage to (?:a player|an opponent|one of your opponents"
        r"|that player|each opponent)|can't be blocked(?! except)|\bunblockable\b",
    ),
    ("permanent_etb", "you"): _spec(
        "Permanents entering",
        "cheap permanents, token makers, and flicker to repeatedly trigger your "
        "permanent enters-the-battlefield value engine",
        {"oracle": r"create [^.]*token|enters the battlefield"},
        r"create [^.]*token|put [^.]*onto the battlefield|enters the battlefield",
    ),
    # Serve was `…|\bequipment\b|whenever[^.]*attacks`, which matched any creature
    # that merely mentions equipment or attacks (~1104). The avenue is Equipment-for-a-
    # dasher: gate on the Equipment TYPE (CR 301.5 — the persistent buff) and the dash /
    # reconfigure KEYWORD (CR 702.109/702.151), plus a small oracle branch for cards
    # that move/cheat Equipment without the subtype.
    ("dash_matters", "you"): _spec(
        "Dash / hit-and-run Equipment",
        "Equipment — it stays on the battlefield when Dash returns the creature to "
        "your hand at end of turn (Auras and counters don't), so it's the resilient "
        "buff for a recurring haste attacker; plus haste enablers and cheap recursion",
        {"preset_names": ("equip",)},
        r"equip \{|attach [^.]*equipment",
        serve_types=("equipment",),
        serve_keywords=("dash", "reconfigure"),
    ),
}

# Subject-bearing signal keys: their spec is built dynamically from the captured
# subject (a Goblin lord and a Sliver lord must not share one static spec).
_SUBJECT_KEYS = signal_keys.SUBJECT_KEYS
# Two distinct sub-avenues are always offered for a subject: the *cards* (the tribe
# members, or the token-makers) and the *payoffs* (lords/anthems that reward a board of
# them). Keeping them clearly separate — and never folding "payoffs" into the cards
# avenue's blurb — is what stops "X tribal" / "X payoffs" reading as the same thing.
_SUBJECT_TEMPLATES = {
    signal_keys.TYPE_MATTERS: ("{s} tribal", "{s} creatures to grow the tribe"),
    signal_keys.TYPED_SPELLCAST: ("{s} spells", "{s} spells to cast"),
}


def _payoff_extra(subj: str, esc: str) -> SubAvenue:
    return SubAvenue(
        f"{subj} payoffs",
        f"lords and anthems that reward a board of {subj}s",
        {"oracle": rf"{esc}s? you control"},
    )


def _subject_spec(signal) -> SignalSpec:
    """Build a spec for a subject-bearing signal by interpolating the subject."""
    subj = signal.subject
    esc = re.escape(subj)
    # keyword-tribe: the subject is an ability keyword (Flying), not a creature type —
    # find creatures that HAVE the keyword (oracle), not a type-line match.
    if signal.key == signal_keys.KEYWORD_TRIBE:
        return SignalSpec(
            label=f"{subj} matters",
            avenue=f"creatures with {subj} plus anthems and payoffs that reward them",
            search={"oracle": rf"\b{esc.lower()}\b"},
            serve=Serve(oracle=re.compile(rf"\b{esc}\b", _IC)),
        )
    # token-maker: the deck CREATES {s} tokens, so find cards that *make* them (not the
    # tribe — searching the type line surfaced {s} creatures that don't make tokens).
    if signal.key == signal_keys.TOKEN_MAKER:
        token_re = rf"create\b[^.]*\b{esc}\b[^.]*token"
        return SignalSpec(
            label=f"{subj} tokens",
            avenue=f"cards that create {subj} tokens to go wide",
            search={"oracle": token_re},
            serve=Serve(oracle=re.compile(token_re, _IC)),
            extras=(_payoff_extra(subj, esc),),
        )
    # tribal (type_matters) / typed spellcast: the cards themselves (type-line match),
    # plus a distinct "{s} payoffs" sub-avenue for the lords/anthems that reward them.
    label_t, avenue_t = _SUBJECT_TEMPLATES.get(signal.key, ("{s}", "{s} synergies"))
    return SignalSpec(
        label=label_t.format(s=subj),
        avenue=avenue_t.format(s=subj),
        search={"card_type": subj},
        serve=Serve(oracle=re.compile(rf"\b{esc}s?\b", _IC)),
        extras=(_payoff_extra(subj, esc),),
    )


# Auto-register an avenue for every exhaustively-mined sweep key that doesn't
# already have a hand-written spec (the same-key widens reuse their existing spec).
def _humanize(key: str) -> str:
    base = key.replace("_matters", "").replace("_", " ").strip()
    return (base[:1].upper() + base[1:]) if base else key


_SPECCED_KEYS = {k for (k, _scope) in SPECS}
for _d in SWEEP_DETECTORS:
    if _d["key"] in _SPECCED_KEYS:
        continue  # hand-written spec already covers this axis
    _ident = (_d["key"], _d["scope"])
    if _ident in SPECS:
        continue
    _polished = SWEEP_LABELS.get(_d["key"])
    if _polished:
        _label, _avenue = _polished
    else:
        _label = _humanize(_d["key"])
        _avenue = f"support and payoffs for the {_label.lower()} axis"
    SPECS[_ident] = _spec(_label, _avenue, {"oracle": _d["regex"]}, _d["regex"])


def spec_for(signal) -> SignalSpec | None:
    """Resolve a spec. Subject-bearing signals build a per-subject spec; otherwise
    exact (key, scope) → (key, any) → first entry by key."""
    if signal.key in _SUBJECT_KEYS and signal.subject:
        return _subject_spec(signal)
    exact = SPECS.get((signal.key, signal.scope))
    if exact is not None:
        return exact
    any_scope = SPECS.get((signal.key, "any"))
    if any_scope is not None:
        return any_scope
    return next((spec for (key, _), spec in SPECS.items() if key == signal.key), None)


def serves(card: dict, signal) -> bool:
    """True if ``card`` feeds ``signal`` (scope-aware), on any structured/oracle
    dimension of the spec's precise ``Serve`` predicate — no longer oracle-only."""
    spec = spec_for(signal)
    if spec is None:
        return False
    return spec.serve.matches(card)


def search_filters(signal, *, color_identity: str, fmt: str) -> dict:
    """Build ``card_search`` kwargs to find cards that feed ``signal`` in-identity."""
    spec = spec_for(signal)
    base = dict(spec.search) if spec else {}
    base["color_identity"] = color_identity
    base["format"] = fmt
    return base


def _assert_every_producible_key_resolves() -> None:
    """Key-agreement gate (ADR-0014). Every subject-less key a detector can produce
    must resolve to a spec. A detector key with no spec used to be a silent no-avenue
    (extraction worked, ``spec_for`` returned None, the avenue was dropped); now it
    fails loudly at import — which ``app.py`` / ``ranking.py`` / every test trigger
    transitively. ``signals`` is imported lazily to keep the module import order
    one-way (signals never imports signal_specs)."""
    from mtg_utils._deck_forge.signals import Signal, producible_static_keys

    orphans = sorted(
        key
        for key in producible_static_keys()
        if spec_for(Signal(key=key, scope="any", subject="", text="", source=""))
        is None
    )
    if orphans:
        msg = (
            f"signal keys produced by a detector but resolved by no spec: {orphans} — "
            "add a SPECS entry (or sweep row), or exclude a subject key."
        )
        raise AssertionError(msg)


_assert_every_producible_key_resolves()
