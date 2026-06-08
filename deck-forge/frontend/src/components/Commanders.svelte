<script>
  // Commander discovery (#2, ADR-0018): intent-ranked owned commanders from the active
  // Collection slot. Theme + colors filter; sort by Support depth (how much you already
  // own to support it) or Novelty (signal rarity). Never EDHREC popularity. Each result
  // shows its lanes + per-lane owned counts (transparent, like the rest of the engine).
  import { onMount } from "svelte";
  import { api } from "../lib/api.js";
  import { applySnapshot, collectionOpen } from "../lib/store.js";
  import { askForge } from "../lib/agent.js";
  import { hoverPreview } from "../lib/hover.js";
  import Mana from "./Mana.svelte";

  const PIPS = ["W", "U", "B", "R", "G", "C"];

  let sort = "support";
  let colors = new Set();
  let theme = "";
  let presets = [];
  let results = [];
  let activeSlot = "paper";
  let slotSize = 0;
  let loading = false;
  let ran = false;
  let error = ""; // e.g. the no-bulk 503 — distinct from an empty collection

  onMount(async () => {
    const r = await api.presets();
    if (r.ok) presets = r.data.presets;
    run();
  });

  async function run() {
    loading = true;
    ran = true;
    error = "";
    const r = await api.discoverCommanders({
      sort,
      colors: colors.size ? [...colors].join("") : null,
      theme: theme || null,
      limit: 24,
    });
    loading = false;
    if (r.ok) {
      results = r.data.results;
      activeSlot = r.data.active_slot;
      slotSize = r.data.slot_size;
    } else {
      // Surface the real cause (e.g. 503 "run download-bulk") instead of falling
      // through to the misleading empty-collection prompt.
      error = r.data.error || `discovery failed (${r.status})`;
      results = [];
    }
  }

  // Re-run when controls change (cheap; deterministic backend, no LLM).
  $: sortSig = sort;
  $: colorSig = [...colors].sort().join("");
  $: themeSig = theme;
  $: (sortSig, colorSig, themeSig, ran && run());

  function toggleColor(c) {
    colors.has(c) ? colors.delete(c) : colors.add(c);
    colors = new Set(colors);
  }

  async function setCommander(name) {
    const r = await api.add(name, "commanders", 1);
    if (r.ok) applySnapshot(r.data);
  }

  // The headline number per result: signal rarity for novelty, support depth otherwise.
  // A plain function (not a reactive `$:` one) — the {#each} re-renders whenever
  // `results` is replaced (every sort change re-runs the query), so it stays current.
  function headline(r) {
    return sort === "novelty" ? `✦ ${r.novelty}` : `⚒ ${r.support_depth}`;
  }
</script>

<div class="panel discover">
  <div class="controls">
    <div class="sortrow">
      <button
        class="seg"
        class:on={sort === "support"}
        on:click={() => (sort = "support")}
      >
        Most support
      </button>
      <button
        class="seg"
        class:on={sort === "novelty"}
        on:click={() => (sort = "novelty")}
      >
        Most unusual
      </button>
    </div>
    <div class="filterrow">
      <div class="pips">
        {#each PIPS as c (c)}
          <button
            type="button"
            class="pip"
            class:on={colors.has(c)}
            title={c === "C" ? "Colorless" : c}
            on:click={() => toggleColor(c)}
            ><Mana sym={c} size="1.1rem" /></button
          >
        {/each}
      </div>
      <select class="theme" bind:value={theme} title="Build-around theme">
        <option value="">Any theme</option>
        {#each presets as p (p.name)}<option value={p.name}>{p.name}</option
          >{/each}
      </select>
    </div>
  </div>

  <div class="results">
    {#if loading}
      <div class="notice">Reading your {activeSlot} shelf…</div>
    {:else if error}
      <div class="notice">{error}</div>
    {:else if slotSize === 0}
      <div class="notice empty">
        No <b>{activeSlot}</b> collection loaded. Import the cards you own to
        discover commanders you can build from your shelf.
        <button class="loadbtn" on:click={() => collectionOpen.set(true)}
          >📦 Import {activeSlot} collection</button
        >
      </div>
    {:else if results.length}
      <p class="lead">
        {sort === "novelty"
          ? "Your most unusual commanders you can actually build"
          : "Commanders your collection already supports best"} — {activeSlot} slot.
      </p>
      <div class="grid">
        {#each results as r (r.name)}
          <div class="ctile" use:hoverPreview={r}>
            <div class="art">
              {#if r.images?.art_crop}
                <img src={r.images.art_crop} alt={r.name} loading="lazy" />
              {:else}
                <div class="noart">{r.name}</div>
              {/if}
              <div class="ci">
                {#each PIPS.filter( (c) => (r.color_identity || []).includes(c), ) as c (c)}
                  <Mana sym={c} size="1rem" />
                {/each}
              </div>
              <span
                class="score"
                title={sort === "novelty"
                  ? "signal rarity"
                  : "owned-support depth"}>{headline(r)}</span
              >
            </div>
            <div class="body">
              <div class="name">{r.name}</div>
              <div class="lanes">
                {#each r.lanes.slice(0, 3) as lane (lane.label)}
                  <span class="lane">{lane.label} · <b>{lane.owned}</b></span>
                {/each}
                {#if !r.lanes.length}
                  <span class="lane none">no owned support yet</span>
                {/if}
              </div>
              <div class="actions">
                <button
                  class="btn btn-ember"
                  on:click={() => setCommander(r.name)}>★ Commander</button
                >
                <button
                  class="btn ask"
                  title="Ask the forge-friend about this commander"
                  on:click={() => askForge("explain", { card: r.name })}
                  >?</button
                >
              </div>
            </div>
          </div>
        {/each}
      </div>
    {:else if ran}
      <div class="notice">
        No commander-eligible cards match in your {activeSlot} collection. Loosen
        the color / theme filters{sort === "novelty"
          ? ", or switch to Most support (Most unusual hides commanders you own no support for)"
          : ""}.
      </div>
    {/if}
  </div>
</div>

<style>
  .discover {
    padding: 1rem;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .controls {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }
  .sortrow {
    display: flex;
    gap: 0.3rem;
  }
  .seg {
    flex: 1;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline-soft);
    color: var(--parchment-dim);
    border-radius: 999px;
    padding: 0.35rem 0.6rem;
    font-family: var(--display);
    font-size: 0.76rem;
    letter-spacing: 0.04em;
  }
  .seg.on {
    color: var(--brass-bright);
    border-color: var(--brass);
    background: rgba(200, 150, 75, 0.14);
  }
  .filterrow {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .pips {
    display: flex;
    gap: 0.2rem;
  }
  .pip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    border-radius: 50%;
    border: 2px solid transparent;
    background: rgba(0, 0, 0, 0.3);
    opacity: 0.45;
    filter: grayscale(0.55);
  }
  .pip.on {
    border-color: #fff;
    opacity: 1;
    filter: none;
  }
  .theme {
    flex: 1;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.35rem 0.5rem;
    font-size: 0.82rem;
  }
  .results {
    margin-top: 0.8rem;
    flex: 1;
    overflow-y: auto;
  }
  .lead {
    font-size: 0.78rem;
    color: var(--parchment-dim);
    margin-bottom: 0.6rem;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 0.6rem;
  }
  .ctile {
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    animation: rise 0.25s ease both;
  }
  .ctile:hover {
    border-color: var(--brass);
  }
  .art {
    position: relative;
    aspect-ratio: 16 / 9;
    background: #0d0a08;
  }
  .art img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .noart {
    width: 100%;
    height: 100%;
    display: grid;
    place-items: center;
    text-align: center;
    padding: 0.4rem;
    font-family: var(--display);
    color: var(--brass);
    font-size: 0.8rem;
  }
  .ci {
    position: absolute;
    top: 0.3rem;
    right: 0.35rem;
    display: flex;
    gap: 0.15rem;
  }
  .score {
    position: absolute;
    bottom: 0.3rem;
    left: 0.35rem;
    font-family: var(--display);
    font-size: 0.72rem;
    color: var(--brass-bright);
    background: rgba(0, 0, 0, 0.55);
    border-radius: 999px;
    padding: 0.05rem 0.45rem;
  }
  .body {
    padding: 0.5rem 0.55rem 0.55rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    flex: 1;
  }
  .name {
    font-size: 0.86rem;
    line-height: 1.15;
  }
  .lanes {
    display: flex;
    flex-wrap: wrap;
    gap: 0.2rem;
    flex: 1;
  }
  .lane {
    font-size: 0.62rem;
    color: var(--parchment-dim);
    background: rgba(200, 150, 75, 0.12);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.05rem 0.4rem;
  }
  .lane.none {
    background: transparent;
    font-style: italic;
    color: var(--muted);
  }
  .actions {
    display: flex;
    gap: 0.35rem;
  }
  .btn {
    border-radius: var(--radius);
    border: 1px solid var(--hairline);
    color: var(--parchment);
    font-family: var(--display);
    font-size: 0.74rem;
    padding: 0.35rem 0.4rem;
  }
  .btn-ember {
    flex: 1;
  }
  .btn.ask {
    width: 1.9rem;
  }
  .notice {
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid var(--hairline-soft);
    border-left: 3px solid var(--brass);
    border-radius: var(--radius);
    padding: 0.8rem 0.9rem;
    font-size: 0.85rem;
  }
  .notice.empty {
    border-left-color: var(--ember);
  }
  .loadbtn {
    display: block;
    margin-top: 0.7rem;
    padding: 0.45rem 1rem;
    background: rgba(255, 106, 61, 0.1);
    border: 1px solid var(--brass);
    border-radius: 999px;
    color: var(--brass-bright);
    font-family: var(--display);
    font-size: 0.8rem;
    cursor: pointer;
  }
  .loadbtn:hover {
    border-color: var(--brass-bright);
    background: rgba(255, 106, 61, 0.16);
  }
</style>
