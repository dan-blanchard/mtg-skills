<script>
  import { applySnapshot, exploreAvenue, deck } from "../lib/store.js";
  import { api } from "../lib/api.js";
  import CardTile from "./CardTile.svelte";

  let packages = [];
  let exploring = null; // single-avenue result: {label, search, candidates, hasMore}
  let loading = false;
  let loadingMore = false;
  let error = "";
  let loaded = false;
  let lastExploredId = null;

  // Singleton: drop candidates already in the deck. These reactive derivations
  // reference $deck DIRECTLY so they re-run the instant a card is added (a filter
  // hidden inside a helper called from the template would only re-run on re-search).
  $: inDeck = new Set(
    [...$deck.commanders, ...$deck.cards, ...$deck.sideboard].map((c) => c.name),
  );
  $: filteredExploring = exploring
    ? exploring.candidates.filter((c) => !inDeck.has(c.name))
    : [];
  $: filteredPackages = packages
    .map((p) => ({
      ...p,
      candidates: p.candidates.filter((c) => !inDeck.has(c.name)),
    }))
    .filter((p) => p.candidates.length);

  // React when the user clicks an avenue (in the Avenues panel) to explore it here.
  $: maybeExplore($exploreAvenue);

  async function maybeExplore(av) {
    if (!av || (av.id === lastExploredId && exploring)) return;
    lastExploredId = av.id;
    loading = true;
    error = "";
    exploring = null;
    packages = [];
    const r = await api.explore(av.label, av.search, 0);
    loading = false;
    if (!r.ok) {
      error = r.data.error || `explore failed (${r.status})`;
      return;
    }
    const pkg = r.data.package;
    exploring = {
      label: av.label,
      search: av.search,
      candidates: pkg.candidates,
      hasMore: pkg.has_more,
    };
  }

  async function loadMoreExplore() {
    if (!exploring || loadingMore) return;
    loadingMore = true;
    // Offset by raw candidates already fetched (exploring.candidates is the raw page,
    // not the in-deck-filtered view) so the server returns the next ranked slice.
    const r = await api.explore(
      exploring.label,
      exploring.search,
      exploring.candidates.length,
    );
    loadingMore = false;
    if (r.ok) {
      const pkg = r.data.package;
      exploring = {
        ...exploring,
        candidates: [...exploring.candidates, ...pkg.candidates],
        hasMore: pkg.has_more,
      };
    }
  }

  async function discoverAll() {
    exploreAvenue.set(null);
    exploring = null;
    lastExploredId = null;
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

  function clearExplore() {
    exploreAvenue.set(null);
    exploring = null;
    lastExploredId = null;
  }

  async function add(name, zone) {
    const r = await api.add(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }
</script>

<div class="panel synergies">
  <div class="top">
    <h3 class="panel-title">Synergy Packages</h3>
    <button class="btn btn-ember" on:click={discoverAll} disabled={loading}>
      {loading ? "Forging…" : "✦ Discover all"}
    </button>
  </div>

  <div class="body">
    {#if error}
      <div class="notice">{error}</div>
    {:else if loading}
      <div class="notice">Searching real cards that feed this avenue…</div>
    {:else if exploring}
      <div class="explore-head">
        <span class="ptitle">{exploring.label}</span>
        <button class="clear" on:click={clearExplore}>× clear</button>
      </div>
      {#if filteredExploring.length}
        <div class="grid">
          {#each filteredExploring as c (c.name)}
            <CardTile card={c} score={c.score} onadd={add} />
          {/each}
        </div>
        {#if exploring.hasMore}
          <button class="more" on:click={loadMoreExplore} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Show more"}
          </button>
        {/if}
      {:else}
        <div class="notice">No fresh candidates for this avenue — you may already run the best ones.</div>
      {/if}
    {:else if filteredPackages.length}
      {#each filteredPackages as pkg}
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
        Click an <b>Avenue</b> (top of the deck column) to explore it here, or hit
        <b>Discover all</b>. Every candidate is a real Scryfall card — never invented.
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
  .explore-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-left: 3px solid var(--ember);
    padding-left: 0.6rem;
    margin-bottom: 0.6rem;
  }
  .clear {
    background: transparent;
    border: 1px solid var(--hairline-soft);
    color: var(--parchment-dim);
    border-radius: 999px;
    padding: 0.15rem 0.6rem;
    font-size: 0.74rem;
  }
  .clear:hover {
    border-color: var(--fail);
    color: var(--fail);
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
</style>
