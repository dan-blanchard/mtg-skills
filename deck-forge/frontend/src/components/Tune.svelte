<script>
  import { api } from "../lib/api.js";

  // The deterministic Tune surface (ADR-0023): diagnose → cut candidates → budgeted
  // swaps, all from the pure deterministic core (works with no session attached).
  let budget = ""; // "" → owned-only zero-spend pass
  let maxSwaps = 5;
  let shapeOverride = ""; // "" → inferred
  let suggestCommander = false;
  let loading = false;
  let applying = false;
  let error = "";
  let result = null;

  const SHAPES = ["aggro", "midrange", "control", "combo"];

  async function run() {
    loading = true;
    error = "";
    const body = {
      max_swaps: Number(maxSwaps) || 0,
      shape_override: shapeOverride || null,
      suggest_commander: suggestCommander,
    };
    if (budget !== "" && !Number.isNaN(Number(budget)))
      body.budget = Number(budget);
    const r = await api.tune(body);
    if (!r.ok) {
      const hint =
        r.status === 404 || r.status === 405
          ? " — restart the hub to load the Tune route"
          : "";
      error =
        (r.data && r.data.error) || `Tune failed (HTTP ${r.status})${hint}`;
      result = null;
    } else {
      result = r.data;
    }
    loading = false;
  }

  async function applySwap(s) {
    applying = true;
    await api.remove(s.cut.name);
    await api.add(s.add.name);
    applying = false;
    await run(); // re-diagnose on the new deck (partial accept → re-plan)
  }

  async function applyAll() {
    applying = true;
    for (const s of result.swaps) {
      await api.remove(s.cut.name);
      await api.add(s.add.name);
    }
    applying = false;
    await run();
  }

  const pct = (x) => Math.round((x || 0) * 100);
  const cost = (a) =>
    a.owned ? "owned" : a.cost === 0 ? "free" : `$${a.cost}`;
</script>

<div class="tune">
  <div class="panel widget controls">
    <h3 class="panel-title">Deterministic Tune</h3>
    <p class="sub">
      Evaluate efficiency, template fit &amp; focus — then propose budgeted
      swaps. No session needed.
    </p>
    <div class="grid">
      <label
        >Budget ($)
        <input
          type="number"
          min="0"
          bind:value={budget}
          placeholder="owned-only"
        />
      </label>
      <label
        >Swaps
        <input type="number" min="0" max="25" bind:value={maxSwaps} />
      </label>
      <label
        >Shape
        <select bind:value={shapeOverride}>
          <option value="">inferred</option>
          {#each SHAPES as s (s)}<option value={s}>{s}</option>{/each}
        </select>
      </label>
      <label class="check">
        <input type="checkbox" bind:checked={suggestCommander} />
        Suggest a better commander
      </label>
    </div>
    <button class="run" on:click={run} disabled={loading || applying}>
      {loading ? "Tuning…" : "Run Tune"}
    </button>
    {#if error}<p class="err">{error}</p>{/if}
  </div>

  {#if result}
    {@const sc = result.scorecard}
    <div class="panel widget">
      <div class="shape-row">
        <span class="chip shape">{sc.shape.value}</span>
        <span class="meta">{sc.shape.inferred ? "detected" : "override"}</span>
        <span class="evidence">{sc.shape.evidence.join(" · ")}</span>
      </div>

      {#if sc.top_issues.length}
        <ul class="issues">
          {#each sc.top_issues as i (i.kind + i.message)}
            <li><span class="sev">●</span>{i.message}</li>
          {/each}
        </ul>
      {:else}
        <p class="clean">No issues found — the deck reads clean.</p>
      {/if}
    </div>

    <div class="panel widget metrics">
      <div class="metric">
        <span class="m-name">Efficiency</span>
        <span class="m-verdict" class:ok={sc.efficiency.verdict === "ok"}>
          {sc.efficiency.verdict}
        </span>
        <span class="m-detail">
          avg MV {sc.efficiency.avg_mv.value} (band {sc.efficiency.avg_mv
            .band[0]}–{sc.efficiency.avg_mv.band[1]}) · ramp {sc.efficiency.ramp
            .have}/{sc.efficiency.ramp.want} · top-end {sc.efficiency.top_end
            .have}
        </span>
      </div>
      <div class="metric">
        <span class="m-name">Template</span>
        <span
          class="m-verdict"
          class:ok={sc.template.verdict === "on-template"}
        >
          {sc.template.verdict}
        </span>
        <span class="m-detail">
          {#each Object.entries(sc.template.short) as [role, b] (role)}
            <em>{role.replace("_", " ")} {b.current}/{b.min}</em>
          {/each}
          {#if !Object.keys(sc.template.short).length}all roles in band{/if}
        </span>
      </div>
      <div class="metric">
        <span class="m-name">Focus</span>
        <span
          class="m-verdict"
          class:ok={sc.focus.verdict === "FOCUSED" ||
            sc.focus.verdict === "SPINE-LED"}
        >
          {sc.focus.verdict}
        </span>
        <span class="m-detail">
          {sc.focus.viable_avenues.length} viable · engine {sc.focus
            .engine_pool} · filler {pct(sc.focus.filler_rate)}%
          {#each sc.focus.viable_avenues as a (a.label)}
            <em>{a.label} {a.depth}</em>
          {/each}
        </span>
      </div>

      <div class="flags">
        <span class="flag" class:warn={sc.wincons.status === "low"}>
          ≈{sc.wincons.count} closers (wants {sc.wincons.target[0]}–{sc.wincons
            .target[1]})
        </span>
        {#if sc.protection.wants_protection}
          <span class="flag" class:warn={sc.protection.status === "low"}>
            {sc.protection.count} protection (~{sc.protection.target})
          </span>
        {/if}
        {#if sc.commander_fit.misfit}
          <span class="flag warn">commander misfit</span>
        {/if}
      </div>
    </div>

    {#if result.swaps.length}
      <div class="panel widget">
        <div class="swap-head">
          <h3 class="panel-title">Proposed swaps</h3>
          <button class="apply-all" on:click={applyAll} disabled={applying}>
            Apply all ({result.swaps.length})
          </button>
        </div>
        {#each result.swaps as s (s.cut.name + s.add.name)}
          <div class="swap">
            <div class="pair">
              <span class="cut">− {s.cut.name}</span>
              <span class="arrow">→</span>
              <span class="add">+ {s.add.name}</span>
              <span class="tag">{cost(s.add)}</span>
            </div>
            <div class="swap-meta">
              <span class="why">{s.reason}</span>
              <button on:click={() => applySwap(s)} disabled={applying}
                >Apply</button
              >
            </div>
          </div>
        {/each}
        <p class="spent">Spend: ${result.spent}</p>
      </div>
    {/if}
    {#if result.swaps_note}<p class="note">{result.swaps_note}</p>{/if}

    {#if result.commander_suggestions && result.commander_suggestions.length}
      <div class="panel widget">
        <h3 class="panel-title">Better-fit commanders</h3>
        {#each result.commander_suggestions as c (c.name)}
          <div class="cmd">
            <span class="cmd-name">{c.name}</span>
            <span class="tag">{c.owned ? "owned" : "buy"}</span>
            <span class="cmd-meta">
              serves {c.serves.join(", ")} · {c.identity_cost_count} cards fall out
            </span>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .tune {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    overflow-y: auto;
    height: 100%;
  }
  .sub {
    font-size: 0.72rem;
    color: var(--muted);
    margin: 0 0 0.6rem;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 0.7rem;
  }
  label {
    display: flex;
    flex-direction: column;
    font-size: 0.7rem;
    color: var(--parchment-dim);
    gap: 0.15rem;
  }
  label.check {
    flex-direction: row;
    align-items: center;
    gap: 0.35rem;
    grid-column: 1 / -1;
  }
  input,
  select {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: 4px;
    color: var(--parchment);
    padding: 0.25rem 0.4rem;
    font-size: 0.8rem;
  }
  label.check input {
    width: auto;
  }
  .run,
  .apply-all,
  button {
    background: var(--brass);
    color: #1a1206;
    border: none;
    border-radius: 5px;
    padding: 0.35rem 0.7rem;
    font-family: var(--display);
    font-size: 0.78rem;
    cursor: pointer;
  }
  .run {
    margin-top: 0.7rem;
    width: 100%;
    padding: 0.5rem;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .err {
    color: var(--fail, #d66);
    font-size: 0.75rem;
  }
  .shape-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .chip.shape {
    background: var(--brass);
    color: #1a1206;
    border-radius: 999px;
    padding: 0.1rem 0.6rem;
    font-family: var(--display);
    text-transform: capitalize;
  }
  .meta {
    font-size: 0.68rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .evidence {
    font-size: 0.7rem;
    color: var(--parchment-dim);
  }
  .issues {
    list-style: none;
    margin: 0.6rem 0 0;
    padding: 0;
  }
  .issues li {
    font-size: 0.78rem;
    color: var(--parchment);
    padding: 0.18rem 0;
  }
  .sev {
    color: var(--brass-bright, #e0a);
    margin-right: 0.4rem;
    font-size: 0.6rem;
  }
  .clean {
    color: var(--pass);
    font-size: 0.8rem;
  }
  .metric {
    display: grid;
    grid-template-columns: 5.5rem auto;
    gap: 0.1rem 0.5rem;
    margin-bottom: 0.5rem;
    align-items: baseline;
  }
  .m-name {
    font-family: var(--display);
    color: var(--brass);
    font-size: 0.8rem;
  }
  .m-verdict {
    color: var(--fail, #d66);
    font-size: 0.78rem;
    text-transform: capitalize;
  }
  .m-verdict.ok {
    color: var(--pass);
  }
  .m-detail {
    grid-column: 1 / -1;
    font-size: 0.7rem;
    color: var(--muted);
  }
  .m-detail em {
    color: var(--parchment-dim);
    font-style: normal;
    margin-right: 0.5rem;
  }
  .flags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.3rem;
  }
  .flag {
    font-size: 0.68rem;
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.1rem 0.5rem;
    color: var(--parchment-dim);
  }
  .flag.warn {
    border-color: var(--brass);
    color: var(--brass-bright, #e0a);
  }
  .swap-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .swap {
    border-top: 1px solid var(--hairline-soft);
    padding: 0.4rem 0;
  }
  .pair {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.8rem;
    flex-wrap: wrap;
  }
  .cut {
    color: var(--fail, #d66);
  }
  .add {
    color: var(--pass);
  }
  .arrow {
    color: var(--muted);
  }
  .tag {
    font-size: 0.62rem;
    background: rgba(0, 0, 0, 0.3);
    border-radius: 4px;
    padding: 0 0.35rem;
    color: var(--parchment-dim);
  }
  .swap-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 0.2rem;
  }
  .why {
    font-size: 0.68rem;
    color: var(--muted);
  }
  .swap-meta button {
    padding: 0.15rem 0.5rem;
    font-size: 0.68rem;
  }
  .spent {
    font-size: 0.72rem;
    color: var(--parchment-dim);
    margin: 0.4rem 0 0;
  }
  .note {
    font-size: 0.7rem;
    color: var(--muted);
    font-style: italic;
  }
  .cmd {
    border-top: 1px solid var(--hairline-soft);
    padding: 0.35rem 0;
    font-size: 0.78rem;
  }
  .cmd-name {
    color: var(--brass);
  }
  .cmd-meta {
    display: block;
    font-size: 0.68rem;
    color: var(--muted);
  }
</style>
