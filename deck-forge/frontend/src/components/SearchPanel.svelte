<script>
  import { api } from "../lib/api.js";
  import { applySnapshot } from "../lib/store.js";
  import CardTile from "./CardTile.svelte";

  let f = {
    color_identity: "",
    type: "",
    oracle: "",
    cmc_min: "",
    cmc_max: "",
    presets: "",
    limit: 24,
    is_commander: false,
  };
  let results = [];
  let error = "";
  let loading = false;
  let searched = false;

  function clean(v) {
    return v === "" ? null : v;
  }

  async function run(e) {
    e?.preventDefault();
    loading = true;
    error = "";
    searched = true;
    const payload = {
      color_identity: clean(f.color_identity.trim().toUpperCase()),
      type: clean(f.type.trim()),
      oracle: clean(f.oracle.trim()),
      cmc_min: f.cmc_min === "" ? null : Number(f.cmc_min),
      cmc_max: f.cmc_max === "" ? null : Number(f.cmc_max),
      presets: f.presets
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
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
  }

  async function add(name, zone) {
    const r = await api.add(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }
</script>

<div class="panel search">
  <h3 class="panel-title">Search the Vault</h3>

  <form on:submit={run} class="filters">
    <div class="grid">
      <label>Color identity<input bind:value={f.color_identity} placeholder="e.g. GW" /></label>
      <label>Type<input bind:value={f.type} placeholder="e.g. Creature" /></label>
      <label class="wide">Oracle text (regex)<input bind:value={f.oracle} placeholder="e.g. create .* token" /></label>
      <label>CMC ≥<input type="number" min="0" bind:value={f.cmc_min} /></label>
      <label>CMC ≤<input type="number" min="0" bind:value={f.cmc_max} /></label>
      <label class="wide">Presets (comma-sep)<input bind:value={f.presets} placeholder="tokens, ramp" /></label>
      <label>Limit<input type="number" min="1" max="100" bind:value={f.limit} /></label>
      <label class="check wide">
        <input type="checkbox" bind:checked={f.is_commander} />
        Commanders only — discover a commander by theme, not popularity
      </label>
    </div>
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
  .filters {
    flex-shrink: 0;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 0.6rem;
  }
  label {
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
