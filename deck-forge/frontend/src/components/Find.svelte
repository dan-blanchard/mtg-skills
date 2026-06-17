<script>
  // The unified Find surface (ADR-0015): one panel that replaces the old Search +
  // Synergies tabs. Focused avenues (pinned in the Avenues panel) OR-drive a flat
  // ✦-ranked candidate list via /api/find; the filter row refines the server query;
  // Type/CMC/Price chips facet the returned list client-side (instant, no round-trip).
  import { onMount } from "svelte";
  import { api } from "../lib/api.js";
  import {
    applySnapshot,
    deck,
    avenues,
    isDigital,
    partnerOpen,
  } from "../lib/store.js";
  import { facetOk } from "../lib/filter.js";
  import CardTile from "./CardTile.svelte";
  import Mana from "./Mana.svelte";
  import FilterWidget from "./FilterWidget.svelte";

  const PIPS = ["W", "U", "B", "R", "G", "C"];
  const PAGE = 60;

  // Result density: "list" is the compact row (default — fits ~4× the cards on
  // screen); "grid" is the art-forward CardTile. Persisted so the choice sticks
  // across sessions.
  const VIEW_KEY = "forge.findView";
  let view =
    (typeof localStorage !== "undefined" && localStorage.getItem(VIEW_KEY)) ||
    "list";
  function setView(v) {
    view = v;
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* private mode — fall back to in-memory only */
    }
  }

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
  // When a lane is NEWLY pinned, also wipe the user's refining filters first so the
  // focused lane drives a clean candidate list (not one narrowed by a stale search).
  let prevFocusIds = new Set();
  function onFocusChange() {
    const ids = new Set(focused.map((a) => a.id));
    const newlyPinned = [...ids].some((id) => !prevFocusIds.has(id));
    prevFocusIds = ids;
    if (newlyPinned) clearFilters();
    run();
  }
  $: (focusSig, onFocusChange());

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

  // A5: with an active commander, lock the pips to its color identity — you can't run an
  // off-identity card. Colorless ({C}) is always legal (empty identity ⊆ any). The lock
  // lifts when a partner slot is open (a 2nd commander can widen identity) or when you're
  // explicitly searching the commander pool (commandersOnly) for that partner.
  $: identityColors = new Set(
    ($deck.commanders || []).flatMap((c) => c.color_identity || []),
  );
  $: colorLocked =
    ($deck.commanders || []).length > 0 && !$partnerOpen && !commandersOnly;
  function colorAllowed(c) {
    return !colorLocked || c === "C" || identityColors.has(c);
  }
  // The off-identity pips to LOCK, as a reactive value Svelte tracks — the `disabled` /
  // `locked` template bindings read this so they update when the commander changes. A
  // bare `colorAllowed(c)` call in the template isn't tracked (Svelte can't trace reactive
  // deps through a function call), so `disabled` wouldn't react to the deck loading.
  $: lockedColors = new Set(
    colorLocked ? PIPS.filter((c) => c !== "C" && !identityColors.has(c)) : [],
  );
  // Prune any selected pip that falls outside a freshly-locked identity, so a stale
  // off-color selection can't silently keep filtering (and can't be un-clicked once
  // disabled).
  $: if (colorLocked) {
    const kept = new Set([...colors].filter(colorAllowed));
    if (kept.size !== colors.size) colors = kept;
  }
  function toggleColor(c) {
    if (!colorAllowed(c)) return;
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
  // Reset every refining control (server filters + client facets) to its default. Called
  // when a lane is newly focused (A2) so the pinned lane drives an unfiltered list.
  function clearFilters() {
    name = "";
    oracle = "";
    colors = new Set();
    exactColors = false;
    selectedPresets = new Set();
    commandersOnly = false;
    facetType = "";
    facetCmc = "";
    facetPrice = "";
    facetRarity = "";
    facetOwned = false;
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
  // Apply the shared client facets (lib/filter.js). The facet values are read into the
  // inline object HERE (not closed over) ON PURPOSE: Svelte's dependency analysis
  // traverses the inline arrow in the reactive statement, so referencing the facets here
  // makes `visible` recompute on every facet toggle (not only on Find/add).
  $: visible = results.filter(
    (c) =>
      !inDeck.has(c.name) &&
      facetOk(
        c,
        {
          type: facetType,
          cmc: facetCmc,
          price: facetPrice,
          rarity: facetRarity,
          owned: facetOwned,
        },
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
              class:locked={lockedColors.has(c)}
              disabled={lockedColors.has(c)}
              title={lockedColors.has(c)
                ? `${c} is outside your commander's color identity`
                : c === "C"
                  ? "Colorless"
                  : c}
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
    <div class="facetbar">
      <div class="facetfill">
        <FilterWidget
          bind:facetType
          bind:facetCmc
          bind:facetPrice
          bind:facetRarity
          bind:facetOwned
          digital={$isDigital}
        />
      </div>
      <div class="viewtoggle" role="group" aria-label="Result density">
        <button
          class="vt"
          class:on={view === "list"}
          title="Compact list"
          aria-label="Compact list"
          on:click={() => setView("list")}>☰</button
        >
        <button
          class="vt"
          class:on={view === "grid"}
          title="Art grid"
          aria-label="Art grid"
          on:click={() => setView("grid")}>▦</button
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
      <!-- One keyed each-block for BOTH densities: toggling `view` only flips the
           `dense` prop, so each card's component instance (and its remote-SVG <img>s)
           persists — the layout reflows via CSS instead of being torn down and
           refetched. The container class drives grid vs single-column flow. -->
      <div class:grid={view === "grid"} class:list={view === "list"}>
        {#each visible as card (card.name)}
          <CardTile
            {card}
            score={card.score}
            onadd={add}
            dense={view === "list"}
          />
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
  /* off-identity pip with an active commander (A5): not selectable */
  .pip.locked {
    opacity: 0.15;
    filter: grayscale(1);
    cursor: not-allowed;
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
  /* facet chips now live in the shared FilterWidget (A4); the density toggle sits
     to its right on the same band */
  .facetbar {
    margin-top: 0.7rem;
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
  }
  .facetfill {
    flex: 1;
    min-width: 0;
  }
  .viewtoggle {
    display: flex;
    flex-shrink: 0;
    gap: 0.2rem;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.12rem;
  }
  .vt {
    width: 1.7rem;
    height: 1.5rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: none;
    border-radius: 999px;
    background: transparent;
    color: var(--muted);
    font-size: 0.9rem;
    line-height: 1;
    transition:
      color 0.12s,
      background 0.12s;
  }
  .vt:hover {
    color: var(--brass-bright);
  }
  .vt.on {
    color: var(--brass-bright);
    background: rgba(200, 150, 75, 0.18);
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
  .list {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
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
