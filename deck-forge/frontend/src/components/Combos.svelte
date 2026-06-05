<script>
  import { api } from "../lib/api.js";

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
      {#if combos.length}
        <div class="group-head">In your deck ({combos.length})</div>
        {#each combos as c}
          <div class="combo">
            <div class="cards">{c.cards.join(" + ")}</div>
            <div class="result">→ {(c.result || []).join(", ")}</div>
          </div>
        {/each}
      {/if}
      {#if nearMisses.length}
        <div class="group-head">Near misses — one card away ({nearMisses.length})</div>
        {#each nearMisses as c}
          <div class="combo near">
            <div class="cards">{c.cards.join(" + ")}</div>
            <div class="result">→ {(c.result || []).join(", ")}</div>
            {#if c.missing_card}<div class="missing">missing: {c.missing_card}</div>{/if}
          </div>
        {/each}
      {/if}
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
  .result {
    font-size: 0.78rem;
    color: var(--brass-bright);
    margin-top: 0.15rem;
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
