<script>
  import { api } from "../lib/api.js";
  import { applySnapshot } from "../lib/store.js";
  import CardTile from "./CardTile.svelte";

  let combos = [];
  let nearMisses = [];
  let loading = false;
  let error = "";
  let loaded = false;

  async function find() {
    loading = true;
    error = "";
    const r = await api.combos();
    loading = false;
    loaded = true;
    if (!r.ok) {
      error = r.data.error || `combo lookup failed (${r.status})`;
      return;
    }
    combos = r.data.combos || [];
    nearMisses = r.data.near_misses || [];
    if (r.data.error) error = r.data.error;
  }

  async function add(name, zone = "cards") {
    const r = await api.add(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }

  const missingOf = (c) => (c.card_views || []).filter((cv) => !cv.in_deck);

  async function addMissing(c) {
    let snap = null;
    for (const cv of missingOf(c)) {
      const r = await api.add(cv.name, "cards", 1);
      if (r.ok) snap = r.data;
    }
    if (snap) applySnapshot(snap);
  }
</script>

<div class="panel combos">
  <div class="top">
    <h3 class="panel-title">Combos · go infinite?</h3>
    <button class="btn" on:click={find} disabled={loading}>
      {loading ? "Consulting…" : "Find combos"}
    </button>
  </div>

  <div class="body">
    {#if error}
      <div class="notice">{error}</div>
    {:else if loading}
      <div class="notice">Querying Commander Spellbook…</div>
    {:else if loaded && combos.length === 0 && nearMisses.length === 0}
      <div class="notice">No catalogued combos in the deck yet.</div>
    {:else if loaded}
      {#each [{ label: "In your deck", list: combos, near: false }, { label: "Near misses — one card away", list: nearMisses, near: true }] as group}
        {#if group.list.length}
          <div class="group-head">{group.label} ({group.list.length})</div>
          {#each group.list as c}
            <section class="combo" class:near={group.near}>
              <div class="chead">
                <div class="result">→ {(c.result || []).join(", ") || "synergy"}</div>
                {#if missingOf(c).length}
                  <button class="btn add-missing" on:click={() => addMissing(c)}>
                    + Add {missingOf(c).length} missing
                  </button>
                {/if}
              </div>
              {#if c.card_views?.length}
                <div class="grid">
                  {#each c.card_views as cv (cv.name)}
                    <CardTile card={cv} onadd={add} />
                  {/each}
                </div>
              {:else}
                <div class="cards">{c.cards.join(" + ")}</div>
              {/if}
            </section>
          {/each}
        {/if}
      {/each}
    {:else}
      <div class="notice idle">
        A secondary lens: Commander Spellbook combos already in your deck, plus
        near-misses you're one card away from. Synergy packages are the headline —
        this is the "win out of nowhere" option.
      </div>
    {/if}
  </div>
</div>

<style>
  .combos {
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
  .group-head {
    font-family: var(--display);
    font-size: 0.74rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--brass);
    margin: 0.8rem 0 0.4rem;
  }
  .combo {
    border: 1px solid var(--hairline-soft);
    border-left: 3px solid var(--g);
    border-radius: var(--radius);
    padding: 0.55rem 0.7rem;
    margin-bottom: 0.5rem;
  }
  .combo.near {
    border-left-color: var(--warn);
  }
  .cards {
    font-size: 0.88rem;
    color: var(--parchment);
  }
  .chead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  .result {
    font-size: 0.82rem;
    color: var(--brass-bright);
    flex: 1;
  }
  .add-missing {
    font-size: 0.74rem;
    padding: 0.28rem 0.55rem;
    white-space: nowrap;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.5rem;
  }
  .missing {
    font-size: 0.74rem;
    color: var(--warn);
    margin-top: 0.15rem;
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
