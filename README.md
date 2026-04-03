# MTG Skills

Claude Code skills for Magic: The Gathering.

## Installation

```bash
npx skills add dan-blanchard/mtg-skills
```

## Available Skills

### commander-tuner

Structured process for analyzing and tuning MTG Commander/EDH decks. Emphasizes correctness by looking up actual card oracle text from Scryfall rather than relying on training data.

**Features:**
- Multi-format deck list parsing (Moxfield, MTGO, plain text, CSV)
- Card data hydration via local Scryfall bulk data with API fallback
- EDHREC commander recommendations via JSON endpoints
- Budget-aware swap recommendations with mana base validation
- Two-agent debate to stress-test proposals before presenting
- Strategy alignment check with the user before analysis

**Prerequisites:** Python 3.12+ and [uv](https://docs.astral.sh/uv/)

On first use, the skill will run `uv sync` to install Python dependencies and download Scryfall bulk data (~500MB).

## License

[0BSD](LICENSE)
