<script>
  import { SYMBOL_ORDER } from "../lib/mana.js";
  import { askForge } from "../lib/agent.js";
  import { hoverPreview } from "../lib/hover.js";
  import Mana from "./Mana.svelte";
  import ManaCost from "./ManaCost.svelte";
  export let card;
  export let onadd;
  export let score = null;

  $: price = card.prices?.usd;
  // Iterate SYMBOL_ORDER (not the card's identity order) so symbols read C, then WUBRG.
  $: colors = SYMBOL_ORDER.filter((c) =>
    (card.color_identity || []).includes(c),
  );
  $: noListing = price == null;
  // Only legendary creatures / other commander-eligible cards (for the deck's current
  // format) can be set as commander — the backend computes this per format.
  $: canCommand = card.can_be_commander === true;
</script>

<div class="tile" use:hoverPreview={card}>
  <div class="art">
    {#if card.images?.art_crop}
      <img src={card.images.art_crop} alt={card.name} loading="lazy" />
    {:else if card.images?.small}
      <img src={card.images.small} alt={card.name} loading="lazy" />
    {:else}
      <div class="noart">{card.name}</div>
    {/if}
  </div>
  <!-- Anchored to the .tile (stable width), NOT .art: Safari doesn't stretch an
       aspect-ratio flex item to full width, which pushed symbols off .art's right. -->
  <div class="ci">
    {#each colors as c}<Mana sym={c} size="1.05rem" />{/each}
  </div>

  <div class="body">
    <div class="name">{card.name}</div>
    <div class="type">{card.type_line}</div>
    <div class="foot">
      <ManaCost cost={card.mana_cost} size="0.95rem" />
      <span class="price" class:nolisting={noListing}>
        {noListing ? "no listing" : "$" + price}
      </span>
    </div>
    {#if score && score.synergy_fit > 0}
      <div class="synergy" title={score.served.join(", ")}>
        <span class="spark">✦ {score.synergy_fit}</span>
        {#each score.served.slice(0, 2) as s}<span class="served">{s}</span
          >{/each}
      </div>
    {/if}
    <div class="actions">
      <button
        class="btn btn-ember add"
        on:click={() => onadd(card.name, "cards")}>+ Add</button
      >
      <button
        class="btn star"
        title={canCommand
          ? "Set as commander"
          : "Not commander-eligible in this format"}
        disabled={!canCommand}
        on:click={() => onadd(card.name, "commanders")}>★</button
      >
      <button
        class="btn star"
        title="Ask the forge-friend to explain"
        on:click={() => askForge("explain", { card: card.name })}>?</button
      >
    </div>
  </div>
</div>

<style>
  .tile {
    position: relative;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition:
      border-color 0.15s,
      transform 0.15s;
    animation: rise 0.25s ease both;
  }
  .tile:hover {
    border-color: var(--brass);
    transform: translateY(-2px);
  }
  .art {
    position: relative;
    width: 100%;
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
    padding: 0.5rem;
    font-family: var(--display);
    color: var(--brass);
    font-size: 0.85rem;
  }
  .ci {
    position: absolute;
    top: 0.35rem;
    /* Bound to BOTH edges and right-align so the symbols can never overflow the
       card's right edge (the old right-only anchor let the last pip get clipped);
       wrap downward if a card somehow has many symbols. */
    right: 0.4rem;
    left: 0.4rem;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0.2rem;
    pointer-events: none;
  }
  .body {
    padding: 0.55rem 0.6rem 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }
  .name {
    font-size: 0.9rem;
    font-weight: 500;
    line-height: 1.15;
  }
  .type {
    font-size: 0.72rem;
    color: var(--muted);
    flex: 1;
  }
  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
    min-height: 1.1rem;
    font-size: 0.76rem;
    color: var(--parchment-dim);
  }
  .price {
    margin-left: auto;
  }
  .price.nolisting {
    color: var(--warn);
    font-style: italic;
  }
  .synergy {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.25rem;
    margin-top: 0.1rem;
  }
  .spark {
    font-family: var(--display);
    font-size: 0.72rem;
    color: var(--brass-bright);
  }
  .served {
    font-size: 0.62rem;
    color: var(--parchment-dim);
    background: rgba(200, 150, 75, 0.12);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.05rem 0.4rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .actions {
    display: flex;
    gap: 0.35rem;
    margin-top: 0.3rem;
  }
  .add {
    flex: 1;
  }
  .star {
    width: 2rem;
    padding: 0.42rem 0;
  }
  .star:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
</style>
