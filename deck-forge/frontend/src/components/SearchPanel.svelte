<script>
  import { onMount } from "svelte";
  import { api } from "../lib/api.js";
  import { applySnapshot } from "../lib/store.js";
  import CardTile from "./CardTile.svelte";

  // [symbol, pip background]. C = colorless pseudo-symbol.
  const PIPS = [
    ["W", "#f7f3da"],
    ["U", "#a8d9f7"],
    ["B", "#bcb3ad"],
    ["R", "#f4a08a"],
    ["G", "#9bd0a6"],
    ["C", "#d6cfc6"],
  ];
  const CMC_MAX = 16; // top handle == "16+" (no upper bound)

  let f = { name: "", type: "", oracle: "", limit: 24, is_commander: false };
  let colors = new Set();
  let exactColors = false;
  let cmcMin = 0;
  let cmcMax = CMC_MAX;
  let allPresets = [];
  let selectedPresets = new Set();
  let presetsOpen = false;

  let collapsed = false;
  let results = [];
  let error = "";
  let loading = false;
  let searched = false;

  onMount(async () => {
    const r = await api.presets();
    if (r.ok) allPresets = r.data.presets;
  });

  function toggleColor(c) {
    colors.has(c) ? colors.delete(c) : colors.add(c);
    colors = new Set(colors);
  }
  function togglePreset(name) {
    selectedPresets.has(name)
      ? selectedPresets.delete(name)
      : selectedPresets.add(name);
    selectedPresets = new Set(selectedPresets);
  }
  function clean(v) {
    return v === "" ? null : v;
  }

  async function run(e) {
    e?.preventDefault();
    loading = true;
    error = "";
    searched = true;
    const payload = {
      name: clean(f.name.trim()),
      color_identity: colors.size ? [...colors].join("") : null,
      exact_colors: exactColors,
      type: clean(f.type.trim()),
      oracle: clean(f.oracle.trim()),
      cmc_min: cmcMin > 0 ? cmcMin : null,
      cmc_max: cmcMax < CMC_MAX ? cmcMax : null,
      presets: [...selectedPresets],
      limit: Number(f.limit) || 24,
      is_commander: f.is_commander,
      sort: "cmc-asc",
    };
    const r = await api.search(payload);
    loading = false;
    if (!r.ok) {
      error = r.data.error || `search failed (${r.status})`;
      results = [];
      return;
    }
    results = r.data.results;
    collapsed = true; // give the results room to scroll
  }

  async function add(name, zone) {
    const r = await api.add(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }

  $: cmcLabel =
    cmcMin === 0 && cmcMax === CMC_MAX
      ? "any"
      : `${cmcMin}${cmcMax > cmcMin ? `–${cmcMax === CMC_MAX ? "16+" : cmcMax}` : ""}`;
  $: fillL = (cmcMin / CMC_MAX) * 100;
  $: fillR = ((CMC_MAX - cmcMax) / CMC_MAX) * 100;
</script>

<div class="panel search">
  <div class="head">
    <h3 class="panel-title">Search the Vault</h3>
    <button class="toggle" type="button" on:click={() => (collapsed = !collapsed)}>
      {collapsed ? "▸ Filters" : "▾ Filters"}
    </button>
  </div>

  <form on:submit={run} class="filters">
    {#if !collapsed}
      <div class="grid">
        <label class="wide"
          >Name<input bind:value={f.name} placeholder="substring, case-insensitive" /></label
        >

        <div class="field wide">
          <span class="lbl">Color identity</span>
          <div class="pips">
            {#each PIPS as [c, bg]}
              <button
                type="button"
                class="pip"
                class:on={colors.has(c)}
                style="--pip:{bg}"
                title={c === "C" ? "Colorless" : c}
                on:click={() => toggleColor(c)}>{c}</button
              >
            {/each}
            <label class="exact" title="Match the color identity exactly, not as a subset">
              <input type="checkbox" bind:checked={exactColors} /> exact
            </label>
          </div>
        </div>

        <label>Type<input bind:value={f.type} placeholder="e.g. Creature" /></label>

        <div class="field">
          <span class="lbl">Presets</span>
          <div class="presets">
            <button class="dropbtn" type="button" on:click={() => (presetsOpen = !presetsOpen)}>
              {selectedPresets.size ? `${selectedPresets.size} selected` : "none"} ▾
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

        <label class="wide"
          >Oracle text (regex)<input bind:value={f.oracle} placeholder="e.g. create .* token" /></label
        >

        <div class="field wide">
          <span class="lbl">Mana value · {cmcLabel}</span>
          <div class="rangewrap">
            <div class="track"></div>
            <div class="fill" style="left:{fillL}%; right:{fillR}%"></div>
            <input
              type="range"
              min="0"
              max={CMC_MAX}
              step="1"
              bind:value={cmcMin}
              on:input={() => cmcMin > cmcMax && (cmcMin = cmcMax)}
            />
            <input
              type="range"
              min="0"
              max={CMC_MAX}
              step="1"
              bind:value={cmcMax}
              on:input={() => cmcMax < cmcMin && (cmcMax = cmcMin)}
            />
          </div>
        </div>

        <label>Limit<input type="number" min="1" max="100" bind:value={f.limit} /></label>
        <label class="check">
          <input type="checkbox" bind:checked={f.is_commander} />
          Commanders only
        </label>
      </div>
    {/if}
    <button class="btn btn-ember go" type="submit" disabled={loading}>
      {loading ? "Searching…" : "⚒ Search"}
    </button>
  </form>

  <div class="results">
    {#if error}
      <div class="notice">{error}</div>
    {:else if loading}
      <div class="notice">Stoking the forge…</div>
    {:else if searched && results.length === 0}
      <div class="notice">No cards matched. Loosen the filters.</div>
    {:else if results.length}
      <div class="grid-cards">
        {#each results as card (card.name)}
          <CardTile {card} onadd={add} />
        {/each}
      </div>
    {:else}
      <div class="notice idle">Set filters and search to surface candidates.</div>
    {/if}
  </div>
</div>

<style>
  .search {
    padding: 1rem;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .toggle {
    font-size: 0.72rem;
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline);
    border-radius: 999px;
    padding: 0.22rem 0.6rem;
    letter-spacing: 0.06em;
  }
  .toggle:hover {
    color: var(--brass-bright);
    border-color: var(--brass);
  }
  .filters {
    flex-shrink: 0;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 0.6rem;
    margin-top: 0.5rem;
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
  .lbl {
    font-size: 0.7rem;
  }
  label.wide,
  .field.wide {
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
  input {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    font-size: 0.88rem;
  }
  input:focus {
    outline: none;
    border-color: var(--brass);
    box-shadow: 0 0 0 1px rgba(200, 150, 75, 0.3);
  }
  /* color pips */
  .pips {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .pip {
    width: 1.7rem;
    height: 1.7rem;
    border-radius: 50%;
    border: 2px solid var(--hairline);
    background: rgba(0, 0, 0, 0.3);
    color: var(--muted);
    font-family: var(--display);
    font-weight: 700;
    font-size: 0.82rem;
    opacity: 0.5;
    transition: all 0.12s ease;
  }
  .pip.on {
    background: var(--pip);
    color: #1a1410;
    border-color: #fff;
    opacity: 1;
    box-shadow: 0 0 8px var(--pip);
  }
  .exact {
    flex-direction: row;
    align-items: center;
    gap: 0.3rem;
    text-transform: none;
    letter-spacing: 0;
    font-size: 0.74rem;
    color: var(--parchment-dim);
    margin-left: 0.3rem;
  }
  .exact input {
    width: auto;
  }
  /* presets dropdown */
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
  /* dual-thumb CMC range */
  .rangewrap {
    position: relative;
    height: 26px;
  }
  .track,
  .fill {
    position: absolute;
    top: 50%;
    height: 4px;
    transform: translateY(-50%);
    border-radius: 2px;
  }
  .track {
    left: 0;
    right: 0;
    background: var(--hairline);
  }
  .fill {
    background: var(--brass);
  }
  .rangewrap input[type="range"] {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 26px;
    margin: 0;
    padding: 0;
    background: none;
    -webkit-appearance: none;
    appearance: none;
    pointer-events: none;
  }
  .rangewrap input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    pointer-events: auto;
    width: 15px;
    height: 15px;
    border-radius: 50%;
    background: var(--brass-bright);
    border: 1px solid #000;
    cursor: pointer;
  }
  .rangewrap input[type="range"]::-moz-range-thumb {
    pointer-events: auto;
    width: 15px;
    height: 15px;
    border-radius: 50%;
    background: var(--brass-bright);
    border: 1px solid #000;
    cursor: pointer;
  }
  .rangewrap input[type="range"]::-webkit-slider-runnable-track {
    background: transparent;
  }
  .rangewrap input[type="range"]::-moz-range-track {
    background: transparent;
  }
  .go {
    width: 100%;
    margin-top: 0.7rem;
    font-family: var(--display);
    letter-spacing: 0.1em;
  }
  .results {
    margin-top: 0.9rem;
    flex: 1;
    overflow-y: auto;
  }
  .grid-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 0.6rem;
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
</style>
