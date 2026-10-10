<script>
  // The Meta panel (ADR-0059): Untapped.gg's Arena ladder meta for this build's
  // queue — the field you'll face, the ranking by Wilson lower bound, the deck's
  // meta archetype with its core cards (the ones the deck lacks marked), and the
  // published lists the active Collection can build within the wildcard budget
  // (the store Tune spends — the player's Arena wildcards when the hub read them,
  // else a labelled default; editable here too). The hub serves the cached report;
  // Refresh is the one fetch (a headless browser, seconds).
  import { onMount, onDestroy } from "svelte";
  import { api } from "../lib/api.js";
  import { tryAdd } from "../lib/adds.js";
  import {
    deck,
    isDigital,
    metaArchetype,
    wildcardBudget,
  } from "../lib/store.js";
  import { displayName, matchLabel, pct1 } from "../lib/cards.js";
  import { WC_TIERS } from "../lib/mana.js";
  import { timeAgo } from "../lib/time.js";
  import Mana from "./Mana.svelte";
  import WildcardBudget from "./WildcardBudget.svelte";

  const RANKS = [
    ["platinum+", "Platinum+"],
    ["diamond+", "Diamond+"],
    ["mythic", "Mythic"],
    ["all", "All ranks"],
  ];
  let ranks = "platinum+";

  let data = null;
  let loading = false;
  let refreshing = false;
  let error = "";
  let signInNeeded = false;
  let loginStarted = false;

  // Responses can land out of order (a format switch mid-load); only the latest
  // request's answer is kept.
  let seq = 0;
  async function load() {
    const mine = ++seq;
    loading = true;
    const r = await api.meta({
      archetype: $metaArchetype,
      ranks,
      wildcards: $isDigital ? $wildcardBudget : null,
    });
    if (mine !== seq) return;
    loading = false;
    if (r.ok) {
      data = r.data;
      error = "";
      autoRefresh();
    } else error = r.data.error || `meta lookup failed (${r.status})`;
  }

  // Once per queue, fetch on its own when signed in and the cache is missing or
  // over 24 hours old (the hub fetches only when stale — `force: false`).
  let autoTried = "";
  function autoRefresh() {
    if (!data?.available || !data.signed_in || autoTried === data.event) return;
    if (data.cached && !data.stale) return;
    autoTried = data.event;
    refresh(false);
  }

  // Re-read on open (mount) and whenever the report could move: the format /
  // medium pick the queue, the deck's cards drive the match and the core's marks
  // (the hub reads a memoized cache, so a re-read is cheap), the budget the
  // buildable fits. A string key, so an unchanged snapshot doesn't refetch.
  $: deckKey = [
    $deck.format,
    $deck.medium,
    ...["commanders", "cards", "sideboard"].flatMap((z) =>
      ($deck[z] || []).map((c) => `${z}:${c.name}`),
    ),
  ].join("|");
  // A budget edit re-reads once typing pauses, not per keystroke (the first read
  // goes straight through).
  $: budgetKey = JSON.stringify($wildcardBudget);
  let settledBudget = null;
  let budgetTimer;
  function settleBudget(key) {
    clearTimeout(budgetTimer);
    if (settledBudget === null) settledBudget = key;
    else budgetTimer = setTimeout(() => (settledBudget = key), 400);
  }
  onDestroy(() => clearTimeout(budgetTimer));
  $: settleBudget(budgetKey);
  // (The arguments only name the dependencies; load reads the picks itself.)
  $: load(deckKey, settledBudget, ranks, $metaArchetype);

  async function refresh(force = true) {
    refreshing = true;
    error = "";
    const r = await api.metaRefresh({ force });
    refreshing = false;
    if (!r.ok) {
      error = r.data.error || `refresh failed (${r.status})`;
      signInNeeded = !!r.data.sign_in;
      return;
    }
    signInNeeded = false;
    loginStarted = false;
    // The refresh answers with the default ranks / the matched archetype; re-read
    // with this panel's picks.
    await load();
  }

  async function signIn() {
    const r = await api.metaLogin();
    if (r.ok) loginStarted = true;
    else error = r.data.error || "couldn't open the sign-in window";
  }

  let addError = "";
  async function add(name) {
    addError = await tryAdd(name, "cards");
  }

  $: report = data?.report ?? null;
  $: showSignIn = data?.available && (signInNeeded || !data.signed_in);
  // Every archetype the report names, for the "pin an archetype" picker.
  $: archetypeNames = [
    ...new Set(
      [...(report?.ranking ?? []), ...(report?.field ?? [])].map((r) => r.name),
    ),
  ].sort();
  $: matchHow = matchLabel(report?.match);
  // A published list's lines: its commanders, then the main deck.
  const listRows = (list) => [
    ...(list.commanders || []).map((name) => ({ name, quantity: 1 })),
    ...(list.main || []),
  ];
  // How old the cached snapshot is, from its fetch time (the hub's rounded
  // age_hours when that doesn't parse); `now` ticks so the label stays current.
  let now = Date.now();
  onMount(() => {
    const tick = setInterval(() => (now = Date.now()), 60000);
    return () => clearInterval(tick);
  });
  function fetchedAgo(fetchedAt, ageHours, at) {
    const t = Date.parse(fetchedAt ?? "");
    if (!Number.isNaN(t)) return timeAgo(at - t);
    return ageHours === null || ageHours === undefined
      ? ""
      : timeAgo(ageHours * 3600000);
  }
  $: ago = fetchedAgo(report?.fetched_at, data?.age_hours, now);

  // A Mythic win rate is only as good as its sample: none reads "—", and one
  // under the Mythic floor (thresholds.mythic_min_matches) shows dimmed. The
  // tooltip gives the 95% Wilson interval's half-width, in points.
  const halfWidth = (p, n, z = 1.96) =>
    (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) /
    (1 + (z * z) / n);
  const mythicThin = (r) =>
    r.mythic.matches < report.thresholds.mythic_min_matches;
  function mythicTitle(r) {
    const n = r.mythic?.matches;
    if (!n) return "No Mythic games";
    const rate = `${pct1(r.mythic.winrate)} ± ${(100 * halfWidth(r.mythic.winrate, n)).toFixed(1)} points over ${n} Mythic games`;
    return mythicThin(r)
      ? `${rate} — under the ${report.thresholds.mythic_min_matches}-game floor, too few to read`
      : rate;
  }

  const needText = (need) =>
    WC_TIERS.filter(([k]) => need?.[k]).map(([k, letter]) => [
      k,
      `${need[k]}${letter}`,
    ]);
</script>

<div class="panel metapanel">
  <div class="top">
    <h3 class="panel-title">Meta · the ladder</h3>
    {#if data?.available}
      {#if showSignIn}
        <button
          class="btn"
          on:click={signIn}
          title="Open a browser window to sign in to Untapped.gg"
          >Sign in to Untapped</button
        >
      {/if}
      <button
        class="btn btn-ember"
        on:click={() => refresh()}
        disabled={refreshing}
      >
        {refreshing ? "Fetching…" : "Refresh"}
      </button>
    {/if}
  </div>

  <div class="body">
    {#if loginStarted}
      <div class="notice">
        A browser window opened — sign in, close it, then Refresh.
      </div>
    {/if}
    {#if error}<div class="err">{error}</div>{/if}
    {#if addError}<div class="err">{addError}</div>{/if}

    {#if !data}
      <div class="notice idle">{loading ? "Reading the meta cache…" : ""}</div>
    {:else if !data.available}
      <div class="notice idle">{data.reason}</div>
    {:else if !data.cached}
      <div class="notice">
        No meta cached for <b>{data.event}</b> yet. Refresh fetches it from Untapped.gg
        (a few seconds).
      </div>
    {:else}
      <p class="lead">
        <b>{report.event}</b>
        {#if report.period?.description}· {report.period.description}{/if}
        · {report.ranks.join(", ")}
        {#if ago}
          · fetched {ago}{#if data.stale}
            <span class="stale">stale</span>{/if}
        {/if}
      </p>
      <div class="picks">
        {#if report.ranked}
          <select bind:value={ranks} aria-label="Ranks">
            {#each RANKS as [id, label] (id)}<option value={id}>{label}</option
              >{/each}
          </select>
        {/if}
        <select bind:value={$metaArchetype} aria-label="Meta archetype">
          <option value="">Match my deck</option>
          {#each archetypeNames as n (n)}<option value={n}>{n}</option>{/each}
        </select>
      </div>

      {#if report.match}
        <p class="match">
          Your deck reads as <b>{report.match.archetype}</b> ({matchHow}).
        </p>
      {:else if !$metaArchetype}
        <p class="match dim">No meta archetype matches this deck.</p>
      {/if}

      {#if report.core}
        <h4>
          Core of {report.core.archetype}
          <span class="hint"
            >≥ {pct1(report.thresholds.core_share)} of {report.core.lists}
            lists · {report.core.matches} matches</span
          >
        </h4>
        {#if !report.core.tuned}
          <p class="match dim">
            A thin sample: shown for reference, but Tune doesn't read it (it
            needs 250 Platinum+ matches across the published lists).
          </p>
        {/if}
        <table class="rows">
          <tbody>
            {#each report.core.cards as c (c.name)}
              <tr class:lacking={!c.in_deck}>
                <td class="num">{pct1(c.share)}</td>
                <td class="num">{c.avg_copies.toFixed(1)}×</td>
                <td class="name">
                  {displayName(c.name)}
                  {#if c.land}<span class="tag">land</span>{/if}
                </td>
                <td class="act">
                  {#if c.in_deck}
                    <span class="have" title="In the deck">✓</span>
                  {:else}
                    <button
                      class="addbtn"
                      on:click={() => add(c.name)}
                      title="Not in the deck — add it">+ add</button
                    >
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      <h4>
        The field <span class="hint"
          >≥ {pct1(report.thresholds.field_share)} of matches</span
        >
      </h4>
      <table class="rows">
        <thead>
          <tr><th>share</th><th class="l">archetype</th><th>win</th></tr>
        </thead>
        <tbody>
          {#each report.field as r (r.id)}
            <tr>
              <td class="num">{pct1(r.share)}</td>
              <td class="name">
                {#each [...(r.colors || "")] as c (c)}<Mana
                    sym={c}
                    size="0.85rem"
                  />{/each}
                {r.name}
              </td>
              <td class="num">{pct1(r.winrate)}</td>
            </tr>
          {/each}
        </tbody>
      </table>

      <h4>
        Ranking <span class="hint"
          >Wilson lower bound, ≥ {report.thresholds.min_matches} matches</span
        >
      </h4>
      <table class="rows">
        <thead>
          <tr>
            <th>#</th><th class="l">archetype</th><th>win</th><th>lower</th><th
              >games</th
            >
            {#if report.ranked}<th
                title="Win rate at Mythic, with its game count">mythic</th
              >{/if}
          </tr>
        </thead>
        <tbody>
          {#each report.ranking as r, i (r.id)}
            <tr class:mine={r.name === (report.core?.archetype ?? "")}>
              <td class="num">{i + 1}</td>
              <td class="name">
                {#each [...(r.colors || "")] as c (c)}<Mana
                    sym={c}
                    size="0.85rem"
                  />{/each}
                {r.name}
              </td>
              <td class="num">{pct1(r.winrate)}</td>
              <td class="num">{pct1(r.wilson_lower)}</td>
              <td class="num">{r.matches}</td>
              {#if report.ranked}
                <td
                  class="num"
                  class:thin={r.mythic?.matches && mythicThin(r)}
                  title={mythicTitle(r)}
                >
                  {#if r.mythic?.matches}{pct1(r.mythic.winrate)}<span
                      class="games">{r.mythic.matches}</span
                    >{:else}—{/if}
                </td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>

      {#if report.buildable}
        <h4>
          Lists you can build <span class="hint"
            >fits the budget first, then cheapest</span
          >
        </h4>
        <div class="budget">
          <span class="blabel">Budget</span>
          <WildcardBudget layout="inline" />
        </div>
        {#each report.buildable as b, i (i)}
          <details class="list" class:fits={b.fits}>
            <summary>
              <span class="mark">{b.fits ? "✓" : "·"}</span>
              <span class="lname">{b.archetype}</span>
              <span class="lstat">{pct1(b.winrate)} / {b.matches}</span>
              <span class="need">
                {#each needText(b.wildcards_needed) as [k, t] (k)}
                  <span class="wc-{k}">{t}</span>
                {:else}
                  <span class="dim">all owned</span>
                {/each}
              </span>
            </summary>
            <ul>
              {#each listRows(b.list) as c, j (j)}
                <li>{c.quantity} {displayName(c.name)}</li>
              {/each}
            </ul>
          </details>
        {/each}
      {:else if !$isDigital}
        <p class="dim small">
          Buildable lists show for a digital build (Arena wildcards).
        </p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .metapanel {
    padding: 1rem;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .top {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .top .panel-title {
    margin: 0;
    flex: 1;
  }
  .top .btn {
    font-size: 0.78rem;
    padding: 0.3rem 0.6rem;
    white-space: nowrap;
  }
  .body {
    margin-top: 0.8rem;
    flex: 1;
    overflow-y: auto;
  }
  .lead,
  .match {
    font-size: 0.82rem;
    color: var(--parchment-dim);
    margin: 0 0 0.5rem;
  }
  .stale {
    color: var(--warn);
  }
  .picks {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.6rem;
  }
  .picks select {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    color: var(--parchment);
    font-size: 0.8rem;
    padding: 0.2rem 0.4rem;
    min-width: 0;
  }
  .picks select:last-child {
    flex: 1;
  }
  h4 {
    font-family: var(--display);
    font-size: 0.74rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--brass);
    margin: 0.9rem 0 0.35rem;
  }
  .hint {
    font-family: var(--body);
    text-transform: none;
    letter-spacing: 0;
    font-size: 0.72rem;
    color: var(--muted);
  }
  .rows {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }
  .rows th,
  .rows td {
    padding: 0.16rem 0.35rem;
    text-align: right;
    border-bottom: 1px solid var(--hairline-soft);
  }
  .rows th {
    color: var(--muted);
    font-weight: normal;
    white-space: nowrap;
  }
  .rows th.l,
  .rows td.name {
    text-align: left;
    width: 100%;
  }
  .rows td.num {
    white-space: nowrap;
    color: var(--parchment-dim);
  }
  .rows td.name {
    color: var(--parchment);
  }
  tr.lacking td.name {
    color: var(--warn);
  }
  tr.mine td {
    background: rgba(232, 181, 99, 0.08);
  }
  .tag {
    margin-left: 0.2rem;
    font-size: 0.7rem;
    background: rgba(0, 0, 0, 0.3);
    border-radius: 4px;
    padding: 0.05rem 0.4rem;
    color: var(--parchment-dim);
  }
  .games {
    margin-left: 0.3rem;
    font-size: 0.7rem;
    color: var(--muted);
  }
  .rows td.thin {
    color: var(--muted);
    opacity: 0.6;
  }
  .budget {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem 0.5rem;
    font-size: 0.78rem;
    margin-bottom: 0.4rem;
  }
  .blabel {
    color: var(--parchment-dim);
  }
  .have {
    color: var(--pass);
  }
  .addbtn {
    background: transparent;
    border: 1px solid var(--hairline-soft);
    color: var(--warn);
    border-radius: 4px;
    font-size: 0.7rem;
    padding: 0.05rem 0.35rem;
    white-space: nowrap;
  }
  .addbtn:hover {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .list {
    font-size: 0.8rem;
    border-bottom: 1px solid var(--hairline-soft);
    padding: 0.2rem 0;
  }
  .list summary {
    display: flex;
    gap: 0.45rem;
    align-items: baseline;
    cursor: pointer;
    color: var(--parchment-dim);
  }
  .list.fits summary {
    color: var(--parchment);
  }
  .list.fits .mark {
    color: var(--pass);
  }
  .lname {
    flex: 1;
  }
  .lstat {
    white-space: nowrap;
  }
  .need {
    display: flex;
    gap: 0.3rem;
    white-space: nowrap;
  }
  .list ul {
    columns: 2;
    margin: 0.3rem 0 0.3rem 1rem;
    padding: 0;
    list-style: none;
    font-size: 0.76rem;
    color: var(--parchment-dim);
  }
  .notice {
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid var(--hairline-soft);
    border-left: 3px solid var(--brass);
    border-radius: var(--radius);
    padding: 0.6rem 0.8rem;
    font-size: 0.84rem;
    margin-bottom: 0.6rem;
  }
  .notice.idle {
    border-left-color: var(--hairline);
    font-style: italic;
    color: var(--muted);
  }
  .notice.idle:empty {
    display: none;
  }
  .err {
    color: var(--fail);
    font-size: 0.8rem;
    margin-bottom: 0.5rem;
  }
  .dim {
    color: var(--muted);
  }
  .small {
    font-size: 0.78rem;
  }
</style>
