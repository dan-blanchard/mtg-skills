<script>
  import { stats } from "../lib/store.js";
  import { COLOR_ORDER, COLOR_LABEL } from "../lib/mana.js";

  $: sources = $stats?.color_sources ?? {};
  $: present = COLOR_ORDER.filter((c) => sources[c]);
</script>

<div class="panel widget">
  <h3 class="panel-title">Color Sources</h3>
  {#if present.length}
    <div class="pips">
      {#each present as c}
        <div class="src" title={COLOR_LABEL[c]}>
          <span class="pip pip-{c}">{c}</span>
          <span class="cnt">{sources[c]}</span>
        </div>
      {/each}
    </div>
  {:else}
    <p class="empty">No colored sources yet.</p>
  {/if}
</div>

<style>
  .pips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.7rem;
  }
  .src {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .cnt {
    font-family: var(--display);
    color: var(--parchment);
    font-size: 0.95rem;
  }
  .empty {
    color: var(--muted);
    font-style: italic;
    font-size: 0.85rem;
  }
</style>
