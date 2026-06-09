<script>
  // The unified Find surface (ADR-0015): one panel that replaces the old Search +
  // Synergies tabs. Focused avenues (pinned in the Avenues panel) OR-drive a flat
  // ✦-ranked candidate list via /api/find; the filter row refines the server query;
  // Type/CMC/Price chips facet the returned list client-side (instant, no round-trip).
  import { onMount } from "svelte";
  import { api } from "../lib/api.js";
  import { applySnapshot, deck, avenues, isDigital } from "../lib/store.js";
  import { RARITY_RANK } from "../lib/mana.js";
  import CardTile from "./CardTile.svelte";
  import Mana from "./Mana.svelte";

  const PIPS = ["W", "U", "B", "R", "G", "C"];
  const PAGE = 60;

  // server filters
  let name = "";
  let nameInput; // bound <input> so the clear-✕ can refocus it
  let oracle = "";
  let colors = new Set();
  let exactColors = false;
  let commandersOnly = false;
  let allPresets = [];
  let selectedPresets = new Set();
  let presetsOpen = false;
  let presetFilter = ""; // narrows the 138-preset list inside the dropdown (client-side)
  let advanced = false;

  // client-side facets (narrow the returned list without a round-trip)
  let facetType = "";
  let facetCmc = "";
  let facetPrice = ""; // paper: USD ceiling. digital uses facetRarity instead.
  let facetRarity = ""; // digital: max wildcard rarity (a card costs 1 WC of its rarity)
  let facetOwned = false; // "Owned only" — candidates already in your active collection
  const TYPE_FACETS = [
    ["", "All"],
    ["creature", "Creatures"],
    ["instant|sorcery", "Inst/Sorc"],
    ["artifact", "Artifacts"],
    ["enchantment", "Enchant."],
    ["planeswalker", "PWs"],
    ["land", "Lands"],
  ];
  const CMC_FACETS = [
    ["", "Any"],
    ["0-2", "≤2"],
    ["3", "3"],
    ["4", "4"],
    ["5+", "5+"],
  ];
  const PRICE_FACETS = [
    ["", "Any"],
    ["1", "≤$1"],
    ["5", "≤$5"],
    ["20", "≤$20"],
  ];
  // Digital builds cost wildcards, not dollars. Wildcards aren't interchangeable and
  // common/uncommon are plentiful while rare/mythic are scarce — so the cost facet is
  // "≤U" (the cheap, abundant pool: commons + uncommons) then the two scarce tiers R and
  // M on their own. ["leU" is a ceiling; "rare"/"mythic" match that exact rarity.]
  const RARITY_FACETS = [
    ["", "Any"],
    ["leU", "≤U"],
    ["rare", "R"],
    ["mythic", "M"],
  ];

  let results = [];
  let offset = 0;
  let hasMore = false;
  let loading = false;
  let loadingMore = false;
  let error = "";
  let ran = false;

  onMount(async () => {
    const r = await api.presets();
    if (r.ok) allPresets = r.data.presets;
  });

  // The focused-avenue set is server state surfaced on each avenue; re-run Find the
  // instant it changes (pinning a lane in the Avenues panel updates the list here).
  $: focused = $avenues.filter((a) => a.focused);
  $: focusSig = focused
    .map((a) => a.id)
    .sort()
    .join(",");
  // Re-run Find whenever the focused-set signature changes. Svelte value-compares the
  // focusSig assignment (safe_not_equal), so this fires only on a real change — not on
  // every unrelated $avenues update (e.g. each card add) — no manual guard needed.
  $: (focusSig, run());

  function payload(off) {
    return {
      name: name.trim() || null,
      oracle: oracle.trim() || null,
      color_identity: colors.size ? [...colors].join("") : null,
      exact_colors: exactColors,
      presets: [...selectedPresets],
      is_commander: commandersOnly,
      limit: PAGE,
      offset: off,
    };
  }

  async function run() {
    loading = true;
    error = "";
    ran = true;
    const r = await api.find(payload(0));
    loading = false;
    if (!r.ok) {
      error = r.data.error || `find failed (${r.status})`;
      results = [];
      hasMore = false;
      return;
    }
    results = r.data.results;
    offset = r.data.results.length;
    hasMore = r.data.has_more;
  }

  async function loadMore() {
    if (loadingMore) return;
    loadingMore = true;
    const r = await api.find(payload(offset));
    loadingMore = false;
    if (r.ok) {
      results = [...results, ...r.data.results];
      offset += r.data.results.length;
      hasMore = r.data.has_more;
    }
  }

  async function add(cardName, zone) {
    const r = await api.add(cardName, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }

  function toggleColor(c) {
    colors.has(c) ? colors.delete(c) : colors.add(c);
    colors = new Set(colors);
  }
  function togglePreset(n) {
    selectedPresets.has(n) ? selectedPresets.delete(n) : selectedPresets.add(n);
    selectedPresets = new Set(selectedPresets);
  }
  function clearName() {
    name = "";
    nameInput?.focus();
  }
  // The 138-preset list, narrowed live by the in-dropdown filter (matches name OR
  // description, so "sacrifice" surfaces edict/exploit presets by their blurb too).
  $: filteredPresets = presetFilter.trim()
    ? allPresets.filter((p) => {
        const q = presetFilter.toLowerCase();
        return (
          p.name.toLowerCase().includes(q) ||
          (p.description || "").toLowerCase().includes(q)
        );
      })
    : allPresets;

  // Singleton: drop a card the instant it's added, plus apply the client facets.
  $: inDeck = new Set(
    [...$deck.commanders, ...$deck.cards, ...$deck.sideboard].map(
      (c) => c.name,
    ),
  );
  // Pure facet test. The facet values are passed in (not closed over) ON PURPOSE: the
  // `visible` reactive below must REFERENCE them so Svelte tracks them as dependencies.
  // Svelte's dependency analysis traverses the inline arrow inside the reactive
  // statement but NOT a separately-declared function's body — so reading the facets only
  // inside this function (the old shape) left `visible` recomputing solely on Find/add,
  // and facet toggles silently did nothing until the next Find.
  function facetOk(c, fType, fCmc, fPrice, fRarity, fOwned, digital) {
    if (fType && !new RegExp(fType, "i").test(c.type_line || "")) return false;
    if (fCmc) {
      const v = c.cmc ?? 0;
      if (fCmc === "0-2" && v > 2) return false;
      if (fCmc === "3" && v !== 3) return false;
      if (fCmc === "4" && v !== 4) return false;
      if (fCmc === "5+" && v < 5) return false;
    }
    if (digital) {
      // Wildcard cost filter. "leU" is a ceiling (commons + uncommons, the cheap pool);
      // "rare"/"mythic" match that exact scarce tier. Unknown-rarity cards always pass.
      if (fRarity && c.rarity) {
        if (fRarity === "leU") {
          if (RARITY_RANK[c.rarity] > RARITY_RANK.uncommon) return false;
        } else if (c.rarity !== fRarity) {
          return false;
        }
      }
    } else if (fPrice) {
      const p = c.prices?.usd == null ? Infinity : Number(c.prices.usd);
      if (p > Number(fPrice)) return false;
    }
    if (fOwned && !c.owned) return false;
    return true;
  }
  $: visible = results.filter(
    (c) =>
      !inDeck.has(c.name) &&
      facetOk(
        c,
        facetType,
        facetCmc,
        facetPrice,
        facetRarity,
        facetOwned,
        $isDigital,
      ),
  );
</script>

<div class="panel find">
  <form class="filters" on:submit|preventDefault={run}>
    <div class="row1">
      <div class="namewrap">
        <input
          class="name"
          bind:value={name}
          bind:this={nameInput}
          placeholder="Search by name…"
        />
        {#if name}
          <button
            type="button"
            class="clear"
            title="Clear search"
            aria-label="Clear search"
            on:click={clearName}>✕</button
          >
        {/if}
      </div>
      <!-- color identity pips + Exact, kept together (#5: Exact belongs by the colors) -->
      <div class="colorgroup">
        <div class="pips">
          {#each PIPS as c (c)}
            <button
              type="button"
              class="pip"
              class:on={colors.has(c)}
              title={c === "C" ? "Colorless" : c}
              on:click={() => toggleColor(c)}
              ><Mana sym={c} size="1.2rem" /></button
            >
          {/each}
        </div>
        <button
          type="button"
          class="exact"
          class:on={exactColors}
          class:dim={!colors.size}
          title="Exact colors — match this color identity exactly, no broader pools"
          on:click={() => (exactColors = !exactColors)}>⊜ Exact</button
        >
      </div>
      <button class="btn btn-ember go" type="submit" disabled={loading}>
        {loading ? "…" : "⚒ Find"}
      </button>
      <button class="adv" type="button" on:click={() => (advanced = !advanced)}>
        {advanced ? "▾" : "▸"} Adv
      </button>
    </div>

    {#if advanced}
      <div class="row2">
        <label class="wide"
          >Oracle (regex)<input
            bind:value={oracle}
            placeholder="e.g. create .* token"
          /></label
        >
        <div class="field">
          <span class="lbl">Theme presets</span>
          {#if selectedPresets.size}
            <div class="selchips">
              {#each [...selectedPresets] as n (n)}
                <button
                  type="button"
                  class="selchip"
                  title="Remove {n}"
                  on:click={() => togglePreset(n)}>{n} <em>✕</em></button
                >
              {/each}
              <button
                type="button"
                class="clearpresets"
                on:click={() => (selectedPresets = new Set())}>clear all</button
              >
            </div>
          {/if}
          <div class="presets">
            <button
              class="dropbtn"
              type="button"
              on:click={() => (presetsOpen = !presetsOpen)}
            >
              {selectedPresets.size
                ? `${selectedPresets.size} selected — add more`
                : "Choose theme presets"} ▾
            </button>
            {#if presetsOpen}
              <div class="dropdown">
                <input
                  class="presearch"
                  type="search"
                  placeholder="Filter {allPresets.length} presets…"
                  bind:value={presetFilter}
                />
                <div class="optlist">
                  {#each filteredPresets as p (p.name)}
                    <label class="opt" class:sel={selectedPresets.has(p.name)}>
                      <input
                        type="checkbox"
                        checked={selectedPresets.has(p.name)}
                        on:change={() => togglePreset(p.name)}
                      />
                      <span class="opt-text">
                        <span class="opt-name">{p.name}</span>
                        <span class="opt-desc">{p.description}</span>
                      </span>
                    </label>
                  {/each}
                  {#if !filteredPresets.length}
                    <div class="opt-empty">
                      No preset matches “{presetFilter}”.
                    </div>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        </div>
        <label class="check">
          <input type="checkbox" bind:checked={commandersOnly} /> commanders only
        </label>
      </div>
    {/if}
  </form>

  {#if focused.length}
    <div class="focusbar">
      <span class="flit"
        >✦ {focused.length} lane{focused.length > 1 ? "s" : ""} focused</span
      >
      {#each focused as a (a.id)}<span class="ftag">{a.label}</span>{/each}
    </div>
  {/if}

  {#if results.length}
    <div class="facets">
      <div class="frow">
        {#each TYPE_FACETS as [v, lbl] (v)}
          <button
            class="fc"
            class:on={facetType === v}
            on:click={() => (facetType = v)}>{lbl}</button
          >
        {/each}
      </div>
      <div class="frow">
        {#each CMC_FACETS as [v, lbl] (v)}
          <button
            class="fc"
            class:on={facetCmc === v}
            on:click={() => (facetCmc = v)}>{lbl}</button
          >
        {/each}
        <span class="fsep"></span>
        {#if $isDigital}
          {#each RARITY_FACETS as [v, lbl] (v)}
            <button
              class="fc"
              class:on={facetRarity === v}
              title="Max wildcard rarity — a card costs one wildcard of its rarity"
              on:click={() => (facetRarity = v)}>{lbl}</button
            >
          {/each}
        {:else}
          {#each PRICE_FACETS as [v, lbl] (v)}
            <button
              class="fc"
              class:on={facetPrice === v}
              on:click={() => (facetPrice = v)}>{lbl}</button
            >
          {/each}
        {/if}
        <span class="fsep"></span>
        <button
          class="fc"
          class:on={facetOwned}
          title="Only cards in your active collection"
          on:click={() => (facetOwned = !facetOwned)}>✓ Owned</button
        >
      </div>
    </div>
  {/if}

  <div class="results">
    {#if error}
      <div class="notice">{error}</div>
    {:else if loading}
      <div class="notice">Stoking the forge…</div>
    {:else if visible.length}
      <div class="grid">
        {#each visible as card (card.name)}
          <CardTile {card} score={card.score} onadd={add} />
        {/each}
      </div>
      {#if hasMore}
        <button class="more" on:click={loadMore} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Show more"}
        </button>
      {/if}
    {:else if ran && results.length}
      <div class="notice">Every match is filtered out — loosen the facets.</div>
    {:else if ran}
      <div class="notice">
        No candidates. Pin an avenue, or set filters and Find.
      </div>
    {:else}
      <div class="notice idle">
        Pin <b class="lit">✦</b> avenues (top of the deck column) to surface ranked
        candidates, or search by name / filters. Every card is a real Scryfall card
        — never invented.
      </div>
    {/if}
  </div>
</div>

<style>
  .find {
    padding: 1rem;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .filters {
    flex-shrink: 0;
  }
  .row1 {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .namewrap {
    position: relative;
    flex: 1;
    min-width: 8rem;
    display: flex;
  }
  .name {
    width: 100%;
    min-width: 0;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.45rem 1.9rem 0.45rem 0.55rem;
    font-size: 0.9rem;
  }
  .name:focus {
    outline: none;
    border-color: var(--brass);
    box-shadow: 0 0 0 1px rgba(200, 150, 75, 0.3);
  }
  /* clear-✕ overlaid at the input's right edge; only rendered when there's text */
  .clear {
    position: absolute;
    right: 0.3rem;
    top: 50%;
    transform: translateY(-50%);
    width: 1.3rem;
    height: 1.3rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.35);
    color: var(--muted);
    font-size: 0.7rem;
    line-height: 1;
    cursor: pointer;
    transition:
      color 0.12s,
      background 0.12s;
  }
  .clear:hover {
    color: var(--parchment);
    background: rgba(212, 69, 47, 0.4);
  }
  .pips {
    display: flex;
    gap: 0.2rem;
  }
  .pip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.55rem;
    height: 1.55rem;
    padding: 0;
    border-radius: 50%;
    border: 2px solid transparent;
    background: rgba(0, 0, 0, 0.3);
    opacity: 0.45;
    filter: grayscale(0.55);
    transition: all 0.12s ease;
    cursor: pointer;
  }
  .pip.on {
    border-color: #fff;
    opacity: 1;
    filter: none;
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.4);
  }
  /* pips + Exact travel together; Exact dims when no colors are chosen (#5) */
  .colorgroup {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .exact {
    font-size: 0.72rem;
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.3rem 0.55rem;
    white-space: nowrap;
    cursor: pointer;
    transition:
      color 0.12s,
      border-color 0.12s,
      opacity 0.12s;
  }
  .exact:hover {
    color: var(--brass-bright);
    border-color: var(--brass);
  }
  .exact.on {
    color: var(--brass-bright);
    border-color: var(--brass);
    background: rgba(200, 150, 75, 0.18);
    box-shadow: 0 0 8px rgba(232, 181, 99, 0.16);
  }
  .exact.dim {
    opacity: 0.5;
  }
  .go {
    font-family: var(--display);
    letter-spacing: 0.06em;
    white-space: nowrap;
  }
  .adv {
    font-size: 0.72rem;
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline);
    border-radius: 999px;
    padding: 0.3rem 0.55rem;
    white-space: nowrap;
  }
  .adv:hover {
    color: var(--brass-bright);
    border-color: var(--brass);
  }
  .row2 {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin-top: 0.6rem;
  }
  label,
  .field {
    display: flex;
    flex-direction: column;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    gap: 0.22rem;
  }
  label.wide {
    grid-column: 1 / -1;
  }
  label.check {
    flex-direction: row;
    align-items: center;
    gap: 0.45rem;
    text-transform: none;
    letter-spacing: 0;
    color: var(--parchment-dim);
    font-size: 0.78rem;
  }
  label.check input {
    width: auto;
  }
  .row2 input:not([type]) {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    font-size: 0.88rem;
  }
  .lbl {
    font-size: 0.7rem;
  }
  /* selected presets surface as removable chips, visible without opening the list */
  .selchips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    text-transform: none;
    letter-spacing: 0;
  }
  .selchip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.74rem;
    color: var(--brass-bright);
    background: rgba(200, 150, 75, 0.16);
    border: 1px solid var(--brass);
    border-radius: 999px;
    padding: 0.12rem 0.55rem;
    cursor: pointer;
  }
  .selchip em {
    font-style: normal;
    color: var(--parchment-dim);
  }
  .selchip:hover {
    background: rgba(212, 69, 47, 0.25);
    border-color: rgba(212, 69, 47, 0.6);
    color: var(--parchment);
  }
  .clearpresets {
    font-size: 0.72rem;
    color: var(--muted);
    background: none;
    border: none;
    text-decoration: underline;
    cursor: pointer;
    padding: 0.12rem 0.3rem;
  }
  .clearpresets:hover {
    color: var(--parchment-dim);
  }
  .presets {
    position: relative;
  }
  .dropbtn {
    width: 100%;
    text-align: left;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    font-size: 0.82rem;
    text-transform: none;
    letter-spacing: 0;
  }
  .dropdown {
    position: absolute;
    z-index: 30;
    top: 110%;
    left: 0;
    right: 0;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 0.35rem;
  }
  /* search pinned above the scrolling list so 138 presets are findable, not scrolled */
  .presearch {
    width: 100%;
    box-sizing: border-box;
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    font-size: 0.82rem;
    margin-bottom: 0.35rem;
  }
  .presearch:focus {
    outline: none;
    border-color: var(--brass);
  }
  .optlist {
    max-height: 260px;
    overflow-y: auto;
  }
  .opt {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    gap: 0.45rem;
    padding: 0.3rem 0.35rem;
    border-radius: var(--radius);
    text-transform: none;
    letter-spacing: 0;
    color: var(--parchment);
  }
  .opt:hover {
    background: rgba(255, 220, 160, 0.06);
  }
  .opt.sel {
    background: rgba(200, 150, 75, 0.12);
  }
  .opt input {
    width: auto;
    margin-top: 0.18rem;
  }
  .opt-text {
    display: flex;
    flex-direction: column;
    gap: 0.05rem;
    min-width: 0;
  }
  .opt-name {
    font-size: 0.82rem;
    color: var(--parchment);
  }
  .opt-desc {
    font-size: 0.7rem;
    line-height: 1.25;
    color: var(--muted);
  }
  .opt-empty {
    padding: 0.5rem 0.4rem;
    font-size: 0.78rem;
    color: var(--muted);
    text-transform: none;
    letter-spacing: 0;
  }
  /* focused-lanes echo */
  .focusbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
    margin-top: 0.7rem;
    padding-left: 0.6rem;
    border-left: 3px solid var(--ember);
  }
  .flit {
    color: var(--ember);
    font-family: var(--display);
    font-size: 0.78rem;
    letter-spacing: 0.04em;
  }
  .ftag {
    font-size: 0.7rem;
    color: var(--parchment-dim);
    background: rgba(255, 106, 61, 0.1);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.05rem 0.5rem;
  }
  /* facet chips */
  .facets {
    margin-top: 0.7rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .frow {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem;
  }
  .fc {
    font-size: 0.72rem;
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.16rem 0.6rem;
  }
  .fc:hover {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .fc.on {
    background: rgba(200, 150, 75, 0.18);
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .fsep {
    width: 1px;
    height: 1rem;
    background: var(--hairline-soft);
    margin: 0 0.25rem;
  }
  .results {
    margin-top: 0.9rem;
    flex: 1;
    overflow-y: auto;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 0.6rem;
  }
  .more {
    margin: 0.8rem auto 0;
    display: block;
    padding: 0.45rem 1.4rem;
    background: transparent;
    border: 1px solid var(--hairline);
    border-radius: 999px;
    color: var(--brass-bright);
    font-family: var(--display);
    font-size: 0.8rem;
    letter-spacing: 0.04em;
    cursor: pointer;
  }
  .more:hover {
    border-color: var(--brass);
  }
  .more:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .notice {
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid var(--hairline-soft);
    border-left: 3px solid var(--brass);
    border-radius: var(--radius);
    padding: 0.7rem 0.85rem;
    font-size: 0.85rem;
  }
  .notice.idle {
    border-left-color: var(--hairline);
    font-style: italic;
    color: var(--muted);
  }
  .lit {
    color: var(--ember);
  }
</style>
