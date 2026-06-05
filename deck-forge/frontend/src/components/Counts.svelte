<script>
  import { stats } from "../lib/store.js";
  $: s = $stats;
  $: tiles = [
    { label: "Lands", value: s?.land_count ?? 0 },
    { label: "Creatures", value: s?.creature_count ?? 0 },
    { label: "Ramp", value: s?.ramp_count ?? 0 },
    { label: "Avg CMC", value: s?.avg_cmc ?? 0 },
  ];
</script>

<div class="panel widget">
  <h3 class="panel-title">Composition</h3>
  <div class="grid">
    {#each tiles as t}
      <div class="tile">
        <div class="value">{t.value}</div>
        <div class="label">{t.label}</div>
      </div>
    {/each}
  </div>
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }
  .tile {
    background: rgba(0, 0, 0, 0.22);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    padding: 0.6rem;
    text-align: center;
  }
  .value {
    font-family: var(--display);
    font-size: 1.6rem;
    color: var(--brass-bright);
    line-height: 1;
  }
  .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
    margin-top: 0.3rem;
  }
</style>
