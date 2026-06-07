<script>
  import { stats } from "../lib/store.js";
  import { bucketCurve, CURVE_BUCKETS } from "../lib/mana.js";

  export let collapsed = false;

  $: buckets = bucketCurve($stats?.curve);
  $: max = Math.max(1, ...Object.values(buckets));
  $: avg = $stats?.avg_cmc ?? 0;
</script>

<div class="panel widget curve" class:collapsed>
  <button class="panel-title bar-toggle" on:click={() => (collapsed = !collapsed)}>
    Curve · avg {avg}
    <span class="caret">{collapsed ? "▸" : "▾"}</span>
  </button>
  {#if !collapsed}
    <div class="chart">
      {#each CURVE_BUCKETS as b}
        <div class="col">
          <div class="bar-track">
            <div
              class="bar"
              style="height: {(buckets[b] / max) * 100}%"
              class:zero={buckets[b] === 0}
            >
              {#if buckets[b] > 0}<span class="n">{buckets[b]}</span>{/if}
            </div>
          </div>
          <div class="lbl">{b === 7 ? "7+" : b}</div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  /* collapsed = just the title line: drop the widget padding and the panel-title's
     bottom margin (which only exists to separate the title from the chart). */
  .curve.collapsed {
    padding: 0.45rem 1rem;
  }
  .curve.collapsed .bar-toggle {
    margin-bottom: 0;
  }
  .bar-toggle {
    width: 100%;
    background: transparent;
    border: none;
    justify-content: flex-start;
    cursor: pointer;
    padding: 0;
  }
  .bar-toggle:hover {
    color: var(--brass-bright);
  }
  .caret {
    margin-left: 0.4rem;
    color: var(--muted);
    font-size: 0.7rem;
  }
  .chart {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 0.35rem;
    height: 96px;
    align-items: end;
  }
  .col {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .bar-track {
    flex: 1;
    display: flex;
    align-items: flex-end;
  }
  .bar {
    width: 100%;
    min-height: 2px;
    border-radius: 3px 3px 0 0;
    background: linear-gradient(180deg, var(--brass-bright), var(--ember-deep));
    box-shadow: 0 0 10px rgba(255, 106, 61, 0.25);
    position: relative;
    transition: height 0.35s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .bar.zero {
    background: var(--hairline-soft);
    box-shadow: none;
  }
  .n {
    position: absolute;
    top: -1.05rem;
    left: 0;
    right: 0;
    text-align: center;
    font-size: 0.72rem;
    color: var(--parchment-dim);
  }
  .lbl {
    text-align: center;
    font-size: 0.72rem;
    color: var(--muted);
    margin-top: 0.3rem;
    font-family: var(--display);
  }
</style>
