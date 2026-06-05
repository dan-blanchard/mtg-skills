<script>
  import { api } from "../lib/api.js";
  import { applySnapshot } from "../lib/store.js";
  import CardTile from "./CardTile.svelte";

  let packages = [];
  let loading = false;
  let error = "";
  let loaded = false;

  async function discover() {
    loading = true;
    error = "";
    const r = await api.packages();
    loading = false;
    loaded = true;
    if (!r.ok) {
      error = r.data.error || `discovery failed (${r.status})`;
      packages = [];
      return;
    }
    packages = r.data.packages.filter((p) => p.candidates.length);
  }

  async function add(name, zone) {
    const r = await api.add(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }
</script>

<div class="panel synergies">
  <div class="top">
    <h3 class="panel-title">Synergy Packages</h3>
    <button class="btn btn-ember" on:click={discover} disabled={loading}>
      {loading ? "Forging…" : "✦ Discover"}
    </button>
  </div>

  <div class="body">
    {#if error}
      <div class="notice">{error}</div>
    {:else if loading}
      <div class="notice">Searching real cards that feed each avenue…</div>
    {:else if loaded && packages.length === 0}
      <div class="notice">No fresh synergy candidates — add a commander, or you may already run the best ones.</div>
    {:else if packages.length}
      {#each packages as pkg}
        <section class="pkg">
          <header>
            <span class="ptitle">{pkg.signal.label}</span>
            <span class="pavenue">{pkg.signal.avenue}</span>
          </header>
          <div class="grid">
            {#each pkg.candidates as c (c.name)}
              <CardTile card={c} score={c.score} onadd={add} />
            {/each}
          </div>
        </section>
      {/each}
    {:else}
      <div class="notice idle">
        Discover real cards that feed your deck's avenues — ranked by synergy, then price.
        Every candidate is a real Scryfall card, never invented.
      </div>
    {/if}
  </div>
</div>

<style>
  .synergies {
    padding: 1rem;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
  }
  .top .panel-title {
    margin: 0;
    flex: 1;
  }
  .body {
    margin-top: 0.9rem;
    flex: 1;
    overflow-y: auto;
  }
  .pkg {
    margin-bottom: 1.2rem;
  }
  .pkg header {
    display: flex;
    flex-direction: column;
    margin-bottom: 0.5rem;
    border-left: 3px solid var(--brass);
    padding-left: 0.6rem;
  }
  .ptitle {
    font-family: var(--display);
    color: var(--brass-bright);
    font-size: 0.95rem;
    letter-spacing: 0.04em;
  }
  .pavenue {
    font-size: 0.74rem;
    color: var(--muted);
    font-style: italic;
  }
  .grid {
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
