<script>
  import { warnings } from "../lib/store.js";
</script>

{#if $warnings.length}
  <div class="panel widget warnings">
    <h3 class="panel-title">⚠ Warnings</h3>
    <ul>
      {#each $warnings as w}
        <li><span class="cat">{w.category.replace("_", " ")}</span>{w.message.replace(w.category.replace("_", " ") + ":", "")}</li>
      {/each}
    </ul>
  </div>
{/if}

<style>
  .warnings {
    border-left: 3px solid var(--fail);
  }
  .warnings :global(.panel-title) {
    color: var(--fail);
  }
  ul {
    margin: 0;
    padding-left: 0;
    list-style: none;
  }
  li {
    font-size: 0.82rem;
    color: var(--parchment-dim);
    padding: 0.3rem 0;
    border-bottom: 1px solid var(--hairline-soft);
  }
  li:last-child {
    border-bottom: none;
  }
  .cat {
    display: inline-block;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fail);
    margin-right: 0.4rem;
  }
</style>
