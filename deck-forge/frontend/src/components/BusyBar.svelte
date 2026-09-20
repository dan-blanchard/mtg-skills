<script>
  // The progress meter for the hub's one long job in flight: the first-launch
  // card-signal index build (~2-4 min over the whole card database, cached
  // afterwards), or a cold commander-discovery sweep (every lane's pool density,
  // recomputed after a database refresh or a change to the signal sources). Fed by
  // the `busy` store (snapshots + SSE). What the count counts, and what waits on
  // the job, follow the job id.
  import { busy } from "../lib/store.js";

  const JOBS = [
    {
      prefix: "signals-index",
      unit: "cards",
      note:
        "A one-time pass, cached for every later launch. Find with a theme preset " +
        "and commander discovery wait on it; everything else works meanwhile.",
    },
    {
      prefix: "discovery",
      unit: "commanders",
      note:
        "Cached once done. The Commanders panel waits on it; everything else " +
        "works meanwhile.",
    },
  ];
  $: kind = JOBS.find((j) => ($busy?.job || "").startsWith(j.prefix)) ?? {
    unit: "",
    note: "",
  };
  $: pct =
    $busy && $busy.total
      ? Math.min(100, Math.round((100 * $busy.done) / $busy.total))
      : 0;
  $: left = eta($busy?.eta_s);
  function eta(s) {
    if (s == null) return "estimating time left…";
    if (s < 60) return "under a minute left";
    const m = Math.round(s / 60);
    return `about ${m} minute${m === 1 ? "" : "s"} left`;
  }
  const fmt = (n) => (n ?? 0).toLocaleString();
</script>

{#if $busy}
  <div class="busy" role="status" aria-live="polite">
    <div class="row">
      <span class="label">{$busy.label}</span>
      <span class="count"
        >{fmt($busy.done)} / {fmt($busy.total)} cards · {left}</span
      >
    </div>
    <div class="track" aria-hidden="true">
      <div class="fill" style="width: {pct}%"></div>
    </div>
    <p class="note">{kind.note}</p>
  </div>
{/if}

<style>
  .busy {
    margin: 0 1rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--brass);
    border-radius: var(--radius);
    background: rgba(200, 150, 75, 0.1);
    font-size: 0.82rem;
  }
  .row {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .label {
    color: var(--brass-bright);
  }
  .count {
    color: var(--parchment-dim);
    font-variant-numeric: tabular-nums;
  }
  .track {
    height: 6px;
    margin-top: 0.4rem;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.35);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--brass);
    transition: width 0.4s ease;
  }
  .note {
    margin: 0.35rem 0 0;
    font-size: 0.74rem;
    color: var(--muted);
  }
</style>
