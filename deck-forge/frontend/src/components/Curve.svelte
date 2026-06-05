<script>
  import { stats } from "../lib/store.js";
  import { bucketCurve, CURVE_BUCKETS } from "../lib/mana.js";

  $: buckets = bucketCurve($stats?.curve);
  $: max = Math.max(1, ...Object.values(buckets));
  $: avg = $stats?.avg_cmc ?? 0;
</script>

<div class="panel widget">
  <h3 class="panel-title">Curve · avg {avg}</h3>
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
</div>

<style>
  .chart {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 0.35rem;
    height: 140px;
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
