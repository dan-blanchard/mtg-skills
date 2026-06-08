<script>
  // A list of card names rendered as hover-preview chips. Long lists collapse behind a
  // "N cards ▸" toggle (resolved lazily only when opened); short lists show inline.
  import { api } from "../lib/api.js";
  import CardChip from "./CardChip.svelte";

  export let names = [];
  export let label = ""; // text before the count toggle, e.g. "protection "
  export let showCount = true; // append the count to the label (off when label has it)
  export let inline = false; // always show chips (for short, always-relevant lists)
  export let open = false;

  let resolved = {};
  const inflight = new Set();
  async function resolve(n) {
    if (!n || n in resolved || inflight.has(n)) return;
    inflight.add(n);
    const r = await api.card(n);
    resolved = { ...resolved, [n]: r.ok && r.data ? r.data.card : null };
    inflight.delete(n);
  }

  $: shown = inline || open;
  $: if (shown) names.forEach(resolve);
</script>

{#if names.length}
  {#if !inline}
    <button class="toggle" on:click={() => (open = !open)}>
      {label}{#if showCount}{names.length}{/if}
      <span class="caret">{open ? "▾" : "▸"}</span>
    </button>
  {/if}
  {#if shown}
    <div class="chips">
      {#each names as n (n)}
        <CardChip name={n} card={resolved[n] ?? null} clickable={false} />
      {/each}
    </div>
  {/if}
{/if}

<style>
  .toggle {
    background: none;
    border: none;
    color: var(--parchment-dim);
    font-size: 0.82rem;
    cursor: pointer;
    padding: 0;
    font-family: inherit;
  }
  .toggle:hover {
    color: var(--brass-bright);
  }
  .caret {
    color: var(--brass);
    font-size: 0.7rem;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin: 0.35rem 0 0.2rem;
  }
</style>
