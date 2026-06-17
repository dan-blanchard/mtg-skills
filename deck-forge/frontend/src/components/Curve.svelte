<script>
  // The full mana-curve chart. No longer a standing widget in the deck column — it lives
  // ONLY inside the status-bar curve sparkline's hover popover now (the sparkline is the
  // glanceable signal; this is the detail-on-hover, mirroring the slot-budgets popover).
  import { stats } from "../lib/store.js";
  import { bucketCurve, CURVE_BUCKETS } from "../lib/mana.js";

  $: buckets = bucketCurve($stats?.curve);
  $: max = Math.max(1, ...Object.values(buckets));
  $: avg = $stats?.avg_cmc ?? 0;
</script>

<div class="panel widget curve">
  <div class="head">
    <span class="ttl">Mana Curve</span>
    <span class="avg">avg&nbsp;<b>{avg}</b></span>
  </div>
  <div class="chart">
    {#each CURVE_BUCKETS as b (b)}
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
  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.7rem;
  }
  .ttl {
    font-family: var(--display);
    font-size: 0.66rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--parchment-dim);
  }
  .avg {
    font-size: 0.7rem;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .avg b {
    color: var(--brass-bright);
  }
  .chart {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 0.3rem;
    height: 84px;
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
    font-size: 0.7rem;
    color: var(--parchment-dim);
    font-variant-numeric: tabular-nums;
  }
  .lbl {
    text-align: center;
    font-size: 0.7rem;
    color: var(--muted);
    margin-top: 0.3rem;
    font-family: var(--display);
  }
</style>
