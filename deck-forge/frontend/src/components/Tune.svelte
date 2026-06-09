<script>
  import { api } from "../lib/api.js";
  import { isDigital } from "../lib/store.js";
  import { WC_TIERS } from "../lib/mana.js";
  import CardChip from "./CardChip.svelte";
  import CardList from "./CardList.svelte";

  // The deterministic Tune surface (ADR-0023): diagnose → cut candidates → budgeted
  // swaps, all from the pure deterministic core (works with no session attached).
  let budget = ""; // "" → owned-only zero-spend pass
  // Digital builds spend wildcards, not dollars — the buy pool is opened by a toggle
  // (owned-only vs. allow-crafting) rather than a USD cap, which Arena has no concept of.
  let allowCraft = false;
  let maxSwaps = 5;
  let shapeOverride = ""; // "" → inferred
  let suggestCommander = false;
  let loading = false;
  let applying = false;
  let error = "";
  let result = null;

  const SHAPES = ["aggro", "midrange", "control", "combo"];

  // Resolve the single cards we render directly (swap cut/add, commander suggestions).
  let resolved = {};
  const inflight = new Set();
  async function resolveOne(n) {
    if (!n || n in resolved || inflight.has(n)) return;
    inflight.add(n);
    const r = await api.card(n);
    resolved = { ...resolved, [n]: r.ok && r.data ? r.data.card : null };
    inflight.delete(n);
  }
  $: if (result) {
    for (const s of result.swaps) {
      if (s.cut) resolveOne(s.cut.name); // fills have no cut (pure add into an open slot)
      resolveOne(s.add.name);
    }
    for (const c of result.commander_suggestions || []) resolveOne(c.name);
  }

  async function run() {
    loading = true;
    error = "";
    const body = {
      max_swaps: Number(maxSwaps) || 0,
      shape_override: shapeOverride || null,
      suggest_commander: suggestCommander,
    };
    if ($isDigital) {
      // No dollar cap for Arena: allow-crafting opens the full buy pool (each unowned
      // add costs one wildcard of its rarity); otherwise stay an owned-only pass.
      if (allowCraft) body.budget = 1e9;
    } else if (budget !== "" && !Number.isNaN(Number(budget))) {
      body.budget = Number(budget);
    }
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
    if (s.cut) await api.remove(s.cut.name); // a fill only adds
    await api.add(s.add.name);
    applying = false;
    await run();
  }

  async function applyAll() {
    applying = true;
    for (const s of result.swaps) {
      if (s.cut) await api.remove(s.cut.name);
      await api.add(s.add.name);
    }
    applying = false;
    await run();
  }

  const pct = (x) => Math.round((x || 0) * 100);
  const WC_LETTER = { mythic: "M", rare: "R", uncommon: "U", common: "C" };

  // Cost tag for a swap/commander entry. Paper: owned / free / $X. Digital: owned, or
  // the wildcard the unowned card costs ("1R") — rarity rides the swap add (backend), or
  // the resolved card as a fallback. `digital` and `resolvedCard` are passed in (not
  // closed over) so the {costTag(...)} markup expression tracks them as dependencies and
  // re-renders when the medium toggles — Svelte doesn't trace a function body's reads.
  function costTag(entry, digital, resolvedCard) {
    if (entry.owned) return "owned";
    if (digital) {
      // || not ??: the backend sends "" (not null) for a missing rarity, and no valid
      // rarity is ever falsy — so empty-string must also fall through to the resolved card.
      const rarity = entry.rarity || resolvedCard?.rarity;
      const letter = WC_LETTER[rarity];
      return letter ? `1${letter}` : "craft";
    }
    if (entry.cost == null) return "buy"; // commander suggestion carries no $ cost
    return entry.cost === 0 ? "free" : `$${entry.cost}`;
  }

  // Wildcards the proposed swaps would cost, by tier (digital only) — one wildcard per
  // unowned add of its rarity. Reactive on `resolved` so it firms up as cards hydrate.
  $: wcSpend = (() => {
    const t = { mythic: 0, rare: 0, uncommon: 0, common: 0 };
    if (!result) return t;
    for (const s of result.swaps) {
      if (s.add.owned) continue;
      // || not ??: "" (the backend's missing-rarity default) must fall through too.
      const rarity = s.add.rarity || resolved[s.add.name]?.rarity;
      if (rarity in t) t[rarity] += 1;
    }
    return t;
  })();
  $: wcSpendTiers = WC_TIERS.filter(([k]) => wcSpend[k]).map(
    ([k, label, cls]) => ({ label, cls, n: wcSpend[k] }),
  );
</script>

<div class="tune">
  <div class="panel widget">
    <h3 class="panel-title">Deterministic Tune</h3>
    <p class="sub">
      Evaluate efficiency, template fit &amp; focus, then propose budgeted
      swaps.
    </p>
    <div class="grid">
      {#if $isDigital}
        <label class="check">
          <input type="checkbox" bind:checked={allowCraft} />
          Allow crafting cards you don't own (costs wildcards)
        </label>
      {:else}
        <label
          >Budget ($)
          <input
            type="number"
            min="0"
            bind:value={budget}
            placeholder="owned-only"
          />
        </label>
      {/if}
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
      </div>
      <div class="evidence">
        {#each sc.shape.evidence as ev (ev.label)}
          {#if ev.cards && ev.cards.length}
            <CardList
              names={ev.cards}
              label={`${ev.label} `}
              showCount={false}
            />
          {:else}
            <span class="ev-flat">{ev.label}</span>
          {/if}
        {/each}
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

    <div class="panel widget">
      <!-- Efficiency -->
      <div class="metric">
        <div class="m-head">
          <span class="m-name">Efficiency</span>
          <span class="m-verdict" class:ok={sc.efficiency.verdict === "ok"}>
            {sc.efficiency.verdict}
          </span>
        </div>
        <div class="m-line">
          avg MV <b>{sc.efficiency.avg_mv.value}</b>
          (band {sc.efficiency.avg_mv.band[0]}–{sc.efficiency.avg_mv.band[1]})
        </div>
        <div class="m-line">
          ramp <b>{sc.efficiency.ramp.have}</b>/{sc.efficiency.ramp.want}
          <CardList names={sc.efficiency.ramp.cards} label="" />
        </div>
        <div class="m-line">
          top-end <b>{sc.efficiency.top_end.have}</b>
          <CardList names={sc.efficiency.top_end.cards} label="" />
        </div>
      </div>

      <!-- Template -->
      <div class="metric">
        <div class="m-head">
          <span class="m-name">Template</span>
          <span
            class="m-verdict"
            class:ok={sc.template.verdict === "on-template"}
          >
            {sc.template.verdict}
          </span>
        </div>
        <div class="m-line">
          {#each Object.entries(sc.template.short) as [role, b] (role)}
            <span class="role-gap"
              >{role.replace("_", " ")} <b>{b.current}</b>/{b.min}</span
            >
          {/each}
          {#each Object.entries(sc.template.over) as [role, b] (role)}
            <span class="role-gap over"
              >{role.replace("_", " ")} <b>{b.current}</b> (max {b.max})</span
            >
          {/each}
          {#if !Object.keys(sc.template.short).length && !Object.keys(sc.template.over).length}
            all roles in band
          {/if}
        </div>
      </div>

      <!-- Focus -->
      <div class="metric">
        <div class="m-head">
          <span class="m-name">Focus</span>
          <span
            class="m-verdict"
            class:ok={sc.focus.verdict === "FOCUSED" ||
              sc.focus.verdict === "SPINE-LED"}
          >
            {sc.focus.verdict}
          </span>
        </div>
        <div class="m-line">
          engine <b>{sc.focus.engine_pool}</b> · filler
          <b>{pct(sc.focus.filler_rate)}%</b>
          <CardList names={sc.focus.filler_cards || []} label="" />
        </div>
        {#if sc.focus.viable_avenues.length}
          <div class="m-sub">themes</div>
          {#each sc.focus.viable_avenues as a (a.label)}
            <div class="m-line avenue">
              <span class="tier {a.tier}">{a.tier}</span>
              {a.label} <b>{a.depth}</b>
              <CardList names={a.cards || []} label="" />
            </div>
          {/each}
        {/if}
        {#if sc.focus.emerging && sc.focus.emerging.length}
          <div class="m-sub">under-supported — commit or cut</div>
          {#each sc.focus.emerging as a (a.label)}
            <div class="m-line avenue">
              <span class="tier emerging">emerging</span>
              {a.label} <b>{a.depth}</b>
              <CardList names={a.cards || []} label="" />
            </div>
          {/each}
        {/if}
      </div>

      <!-- Tier-2 advisory flags -->
      <div class="flag-block">
        <div class="flag-row" class:warn={sc.wincons.status === "low"}>
          <span
            >≈{sc.wincons.count} closers (wants {sc.wincons.target[0]}–{sc
              .wincons.target[1]})</span
          >
          <CardList names={sc.wincons.cards || []} label="" />
        </div>
        {#if sc.protection.wants_protection}
          <div class="flag-row" class:warn={sc.protection.status === "low"}>
            <span
              >{sc.protection.count} protection (wants ~{sc.protection
                .target})</span
            >
            <CardList names={sc.protection.cards || []} label="" />
          </div>
        {/if}
        {#if sc.commander_fit.misfit}
          <div class="flag-row warn">
            <span
              >commander serves {sc.commander_fit.serves_viable.length}/{sc
                .commander_fit.viable_count} viable avenues</span
            >
          </div>
        {/if}
      </div>
    </div>

    {#if result.swaps.length}
      <div class="panel widget">
        <div class="swap-head">
          <h3 class="panel-title">Proposed changes</h3>
          <button class="apply-all" on:click={applyAll} disabled={applying}>
            Apply all ({result.swaps.length})
          </button>
        </div>
        {#each result.swaps as s ((s.cut?.name ?? "") + "→" + s.add.name)}
          <div class="swap">
            <div class="pair">
              <!-- A fill has no cut: it's a pure add into an open slot, shown as just "+ Card". -->
              {#if s.cut}
                <span class="pm cut">−</span>
                <CardChip
                  name={s.cut.name}
                  card={resolved[s.cut.name] ?? null}
                  clickable={false}
                />
                <span class="arrow">→</span>
              {/if}
              <span class="pm add">+</span>
              <CardChip
                name={s.add.name}
                card={resolved[s.add.name] ?? null}
                clickable={false}
              />
              <span class="tag"
                >{costTag(s.add, $isDigital, resolved[s.add.name])}</span
              >
            </div>
            <div class="swap-meta">
              <span class="why">{s.reason}</span>
              <button on:click={() => applySwap(s)} disabled={applying}
                >Apply</button
              >
            </div>
          </div>
        {/each}
        {#if $isDigital}
          <p class="spent">
            Wildcards:
            {#each wcSpendTiers as t (t.cls)}
              <span class="wc-{t.cls}">{t.n}{t.label}</span>
            {:else}
              <span class="wc-owned">none — all owned</span>
            {/each}
          </p>
        {:else}
          <p class="spent">Spend: ${result.spent}</p>
        {/if}
      </div>
    {/if}
    {#if result.swaps_note}<p class="note">{result.swaps_note}</p>{/if}

    {#if result.commander_suggestions && result.commander_suggestions.length}
      <div class="panel widget">
        <h3 class="panel-title">Better-fit commanders</h3>
        {#each result.commander_suggestions as c (c.name)}
          <div class="cmd">
            <div class="cmd-top">
              <CardChip
                name={c.name}
                card={resolved[c.name] ?? null}
                clickable={false}
              />
              <span class="tag">{costTag(c, $isDigital, resolved[c.name])}</span
              >
            </div>
            <div class="cmd-meta">serves {c.serves.join(", ")}</div>
            {#if c.identity_cost && c.identity_cost.length}
              <CardList
                names={c.identity_cost}
                label="cards that fall out of identity: "
              />
            {/if}
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
    font-size: 0.82rem;
    color: var(--parchment-dim);
    margin: 0 0 0.7rem;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.6rem 0.8rem;
  }
  label {
    display: flex;
    flex-direction: column;
    font-size: 0.8rem;
    color: var(--parchment);
    gap: 0.2rem;
  }
  label.check {
    flex-direction: row;
    align-items: center;
    gap: 0.4rem;
    grid-column: 1 / -1;
  }
  input,
  select {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: 4px;
    color: var(--parchment);
    padding: 0.35rem 0.45rem;
    font-size: 0.9rem;
  }
  label.check input {
    width: auto;
  }
  button {
    background: var(--brass);
    color: #1a1206;
    border: none;
    border-radius: 5px;
    padding: 0.4rem 0.8rem;
    font-family: var(--display);
    font-size: 0.85rem;
    cursor: pointer;
  }
  .run {
    margin-top: 0.8rem;
    width: 100%;
    padding: 0.55rem;
    font-size: 0.95rem;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .err {
    color: var(--fail, #e07a5f);
    font-size: 0.85rem;
    margin-top: 0.6rem;
  }

  /* Shape */
  .shape-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .chip.shape {
    background: var(--brass);
    color: #1a1206;
    border-radius: 999px;
    padding: 0.18rem 0.8rem;
    font-family: var(--display);
    font-size: 1rem;
    text-transform: capitalize;
  }
  .meta {
    font-size: 0.72rem;
    color: var(--parchment-dim);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .evidence {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    margin: 0.55rem 0;
  }
  .ev-flat {
    font-size: 0.82rem;
    color: var(--parchment-dim);
  }

  .issues {
    list-style: none;
    margin: 0.7rem 0 0;
    padding: 0;
  }
  .issues li {
    font-size: 0.9rem;
    color: var(--parchment);
    padding: 0.25rem 0;
    line-height: 1.4;
  }
  .sev {
    color: var(--brass-bright, #e8b04b);
    margin-right: 0.45rem;
    font-size: 0.7rem;
    vertical-align: middle;
  }
  .clean {
    color: var(--pass);
    font-size: 0.9rem;
  }

  /* Metrics */
  .metric {
    margin-bottom: 0.85rem;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid var(--hairline-soft);
  }
  .m-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.3rem;
  }
  .m-name {
    font-family: var(--display);
    color: var(--brass-bright, #e8b04b);
    font-size: 1rem;
  }
  .m-verdict {
    color: var(--fail, #e07a5f);
    font-size: 0.9rem;
    font-weight: 600;
    text-transform: capitalize;
  }
  .m-verdict.ok {
    color: var(--pass);
  }
  .m-line {
    font-size: 0.85rem;
    color: var(--parchment);
    line-height: 1.5;
  }
  .m-line b {
    color: var(--brass-bright, #e8b04b);
    font-weight: 700;
  }
  .m-sub {
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--parchment-dim);
    margin-top: 0.4rem;
  }
  .avenue {
    margin-top: 0.15rem;
  }
  .tier {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-radius: 4px;
    padding: 0.02rem 0.35rem;
    margin-right: 0.35rem;
    vertical-align: middle;
  }
  .tier.main {
    background: var(--brass);
    color: #1a1206;
  }
  .tier.sub {
    border: 1px solid var(--hairline);
    color: var(--parchment-dim);
  }
  .tier.emerging {
    border: 1px dashed var(--brass);
    color: var(--brass);
  }
  .role-gap {
    margin-right: 0.7rem;
  }
  .role-gap.over b {
    color: var(--fail, #e07a5f);
  }

  /* Tier-2 flags */
  .flag-block {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.2rem;
  }
  .flag-row {
    font-size: 0.85rem;
    color: var(--parchment-dim);
  }
  .flag-row.warn {
    color: var(--brass-bright, #e8b04b);
  }

  /* Swaps */
  .swap-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .swap {
    border-top: 1px solid var(--hairline-soft);
    padding: 0.55rem 0;
  }
  .pair {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex-wrap: wrap;
  }
  .pm {
    font-weight: 700;
    font-size: 1rem;
  }
  .pm.cut {
    color: var(--fail, #e07a5f);
  }
  .pm.add {
    color: var(--pass);
  }
  .arrow {
    color: var(--parchment-dim);
    margin: 0 0.15rem;
  }
  .tag {
    font-size: 0.7rem;
    background: rgba(0, 0, 0, 0.3);
    border-radius: 4px;
    padding: 0.05rem 0.4rem;
    color: var(--parchment-dim);
  }
  .swap-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 0.35rem;
  }
  .why {
    font-size: 0.78rem;
    color: var(--parchment-dim);
  }
  .swap-meta button {
    padding: 0.2rem 0.6rem;
    font-size: 0.78rem;
  }
  .spent {
    font-size: 0.82rem;
    color: var(--parchment-dim);
    margin: 0.5rem 0 0;
  }
  /* Wildcard tier chips in the spend total — layout only; .wc-* globals tint them. */
  .spent span {
    margin-left: 0.4rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .note {
    font-size: 0.8rem;
    color: var(--parchment-dim);
    font-style: italic;
  }

  /* Commander suggestions */
  .cmd {
    border-top: 1px solid var(--hairline-soft);
    padding: 0.5rem 0;
  }
  .cmd-top {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .cmd-meta {
    font-size: 0.8rem;
    color: var(--parchment-dim);
    margin: 0.25rem 0;
  }
</style>
