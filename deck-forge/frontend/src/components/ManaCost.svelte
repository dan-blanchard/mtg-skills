<script>
  // Render a Scryfall mana-cost string ("{3}{W}{U}") as a row of official symbols.
  // Replaces bare "CMC n" readouts (#1): a real cost tells you colors AND amount at a
  // glance, the way a printed card does. Empty cost (lands, some tokens) renders nothing.
  import { parseManaCost } from "../lib/mana.js";
  import Mana from "./Mana.svelte";
  export let cost = "";
  export let size = "0.95rem";
  $: symbols = parseManaCost(cost);
</script>

{#if symbols.length}
  <span class="cost">
    {#each symbols as s}<Mana sym={s} {size} />{/each}
  </span>
{/if}

<style>
  .cost {
    display: inline-flex;
    align-items: center;
    gap: 0.12rem;
    flex-shrink: 0;
  }
</style>
