<script>
  // The live faceting widget (A4), shared by Find (narrows search results) and DeckList
  // (narrows the current deck). Pure UI over bound state — the parent owns the values and
  // applies `facetOk` from lib/filter.js. `showName` adds a client-side name box (the deck
  // view wants it; Find keeps its own server-side name input, so it passes showName=false).
  import {
    TYPE_FACETS,
    CMC_FACETS,
    PRICE_FACETS,
    RARITY_FACETS,
  } from "../lib/filter.js";

  export let name = "";
  export let facetType = "";
  export let facetCmc = "";
  export let facetPrice = "";
  export let facetRarity = "";
  export let facetOwned = false;
  export let digital = false;
  export let showName = false;
  export let showOwned = true;
</script>

<div class="facets">
  {#if showName}
    <input class="namefilter" bind:value={name} placeholder="Filter by name…" />
  {/if}
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
    {#if digital}
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
    {#if showOwned}
      <span class="fsep"></span>
      <button
        class="fc"
        class:on={facetOwned}
        title="Only cards in your active collection"
        on:click={() => (facetOwned = !facetOwned)}>✓ Owned</button
      >
    {/if}
  </div>
</div>

<style>
  .facets {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .namefilter {
    width: 100%;
    box-sizing: border-box;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.35rem 0.5rem;
    font-size: 0.85rem;
  }
  .namefilter:focus {
    outline: none;
    border-color: var(--brass);
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
</style>
