<script>
  // The unified Find surface (ADR-0015): one panel that replaces the old Search +
  // Synergies tabs. Focused avenues (pinned in the Avenues panel) OR-drive a flat
  // ✦-ranked candidate list via /api/find; the filter row refines the server query;
  // Type/CMC/Price chips facet the returned list client-side (instant, no round-trip).
  import { onMount } from "svelte";
  import { api } from "../lib/api.js";
  import { applySnapshot, deck, avenues } from "../lib/store.js";
  import CardTile from "./CardTile.svelte";
  import Mana from "./Mana.svelte";

  const PIPS = ["W", "U", "B", "R", "G", "C"];
  const PAGE = 60;

  // server filters
  let name = "";
  let oracle = "";
  let colors = new Set();
  let exactColors = false;
  let commandersOnly = false;
  let allPresets = [];
  let selectedPresets = new Set();
  let presetsOpen = false;
  let advanced = false;

  // client-side facets (narrow the returned list without a round-trip)
  let facetType = "";
  let facetCmc = "";
  let facetPrice = "";
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

  // Singleton: drop a card the instant it's added, plus apply the client facets.
  $: inDeck = new Set(
    [...$deck.commanders, ...$deck.cards, ...$deck.sideboard].map(
      (c) => c.name,
    ),
  );
  function facetOk(c) {
    if (facetType && !new RegExp(facetType, "i").test(c.type_line || ""))
      return false;
    if (facetCmc) {
      const v = c.cmc ?? 0;
      if (facetCmc === "0-2" && v > 2) return false;
      if (facetCmc === "3" && v !== 3) return false;
      if (facetCmc === "4" && v !== 4) return false;
      if (facetCmc === "5+" && v < 5) return false;
    }
    if (facetPrice) {
      const p = c.prices?.usd == null ? Infinity : Number(c.prices.usd);
      if (p > Number(facetPrice)) return false;
    }
    if (facetOwned && !c.owned) return false;
    return true;
  }
  $: visible = results.filter((c) => !inDeck.has(c.name) && facetOk(c));
</script>

<div class="panel find">
  <form class="filters" on:submit|preventDefault={run}>
    <div class="row1">
      <input class="name" bind:value={name} placeholder="Search by name…" />
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
          <span class="lbl">Presets</span>
          <div class="presets">
            <button
              class="dropbtn"
              type="button"
              on:click={() => (presetsOpen = !presetsOpen)}
            >
              {selectedPresets.size
                ? `${selectedPresets.size} selected`
                : "none"} ▾
            </button>
            {#if presetsOpen}
              <div class="dropdown">
                {#each allPresets as p (p.name)}
                  <label class="opt" title={p.description}>
                    <input
                      type="checkbox"
                      checked={selectedPresets.has(p.name)}
                      on:change={() => togglePreset(p.name)}
                    />
                    <span>{p.name}</span>
                  </label>
                {/each}
              </div>
            {/if}
          </div>
        </div>
        <label class="check">
          <input type="checkbox" bind:checked={exactColors} /> exact colors
        </label>
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
        {#each PRICE_FACETS as [v, lbl] (v)}
          <button
            class="fc"
            class:on={facetPrice === v}
            on:click={() => (facetPrice = v)}>{lbl}</button
          >
        {/each}
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
    gap: 0.5rem;
  }
  .name {
    flex: 1;
    min-width: 0;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.45rem 0.55rem;
    font-size: 0.9rem;
  }
  .name:focus {
    outline: none;
    border-color: var(--brass);
    box-shadow: 0 0 0 1px rgba(200, 150, 75, 0.3);
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
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 0.6rem;
    margin-top: 0.55rem;
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
    max-height: 240px;
    overflow-y: auto;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 0.3rem;
  }
  .opt {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.4rem;
    padding: 0.25rem 0.35rem;
    border-radius: var(--radius);
    text-transform: none;
    letter-spacing: 0;
    font-size: 0.8rem;
    color: var(--parchment);
  }
  .opt:hover {
    background: rgba(255, 220, 160, 0.06);
  }
  .opt input {
    width: auto;
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
