<script>
  import { stats, bracket } from "../lib/store.js";
  $: s = $stats;
  $: b = $bracket;
  $: tiles = [
    { label: "Lands", value: s?.land_count ?? 0 },
    { label: "Creatures", value: s?.creature_count ?? 0 },
    { label: "Ramp", value: s?.ramp_count ?? 0 },
    { label: "Avg CMC", value: s?.avg_cmc ?? 0 },
  ];
  // Mechanical bracket evidence → short factor chips.
  $: factors = b
    ? [
        b.game_changers?.length
          ? `${b.game_changers.length} game changer${b.game_changers.length > 1 ? "s" : ""}`
          : null,
        b.mass_land_denial?.length ? "mass land denial" : null,
        b.fast_curve ? "fast curve" : null,
      ].filter(Boolean)
    : [];
</script>

<div class="panel widget">
  <h3 class="panel-title">Composition</h3>

  {#if b}
    <div
      class="bracket b-{b.bracket}"
      title="Mechanical estimate from game changers, mass land denial, and curve speed (brackets 2–4)"
    >
      <span class="bnum">Bracket {b.bracket}</span>
      <span class="bname">{b.name}</span>
      <span class="bnote">est.</span>
    </div>
    {#if factors.length}
      <div class="factors">
        {#each factors as f}<span class="chip">{f}</span>{/each}
      </div>
    {/if}
  {/if}

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
  .bracket {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.5rem 0.7rem;
    margin-bottom: 0.5rem;
    border: 1px solid var(--hairline-soft);
    border-left: 3px solid var(--brass);
    border-radius: var(--radius);
    background: rgba(0, 0, 0, 0.22);
  }
  .bracket.b-4 {
    border-left-color: var(--ember);
  }
  .bnum {
    font-family: var(--display);
    font-size: 1.05rem;
    color: var(--brass-bright);
  }
  .bname {
    font-size: 0.82rem;
    color: var(--parchment);
    flex: 1;
  }
  .bnote {
    font-size: 0.66rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .factors {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin-bottom: 0.6rem;
  }
  .chip {
    font-size: 0.68rem;
    color: var(--parchment-dim);
    background: rgba(200, 150, 75, 0.12);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.08rem 0.5rem;
  }
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
