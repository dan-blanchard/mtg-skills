<script>
  // The Pool panel for a sealed / draft build (ADR-0055): every colour pair the
  // opened pool supports, enumerated on equal footing BEFORE any opinion (playables,
  // creatures, removal, evasion, big bodies, rares — the deterministic core's
  // readout, never a guess), a one-click seed of a first 40 in a pair, and a scan
  // of what the SET holds (the threats and answers opponents draw from).
  import { api } from "../lib/api.js";
  import { pool, applySnapshot, importOpen } from "../lib/store.js";
  import Mana from "./Mana.svelte";

  const COLUMNS = [
    ["playables", "play", "Nonland cards the pair can run"],
    ["creatures", "crea", "Creatures"],
    ["removal", "rmvl", "Removal, incl. sweepers"],
    ["evasion", "evas", "Evasive creatures"],
    ["power_4_plus", "4+", "Creatures with power 4 or more"],
    ["rares", "rare", "Rares and mythics"],
    ["avg_cmc", "avg", "Average mana value of the playables"],
  ];
  let sortKey = "playables";
  let sortDesc = true;
  function sortBy(key) {
    if (sortKey === key) sortDesc = !sortDesc;
    else {
      sortKey = key;
      sortDesc = key !== "avg_cmc";
    }
  }
  $: rows = ($pool?.color_pairs ?? [])
    .slice()
    .sort((a, b) =>
      sortDesc ? b[sortKey] - a[sortKey] : a[sortKey] - b[sortKey],
    );

  let seeding = "";
  let seedError = "";
  async function seed(pair) {
    seeding = pair;
    seedError = "";
    const r = await api.seedBuild(pair);
    seeding = "";
    if (r.ok) applySnapshot(r.data);
    else seedError = r.data.error || "couldn't seed a deck";
  }

  let setCode = "";
  let scan = null;
  let scanBusy = false;
  let scanError = "";
  async function runScan() {
    const code = setCode.trim();
    if (!code) return;
    scanBusy = true;
    scanError = "";
    const r = await api.setScan(code);
    scanBusy = false;
    if (r.ok) scan = r.data;
    else {
      scan = null;
      scanError = r.data.error || `scan failed (${r.status})`;
    }
  }
  const counts = (d) =>
    Object.entries(d || {})
      .filter(([, v]) => v)
      .map(([k, v]) => `${k} ${v}`)
      .join(", ");
</script>

<div class="panel poolpanel">
  {#if !$pool || !$pool.size}
    <div class="notice empty">
      No pool yet. Import your sealed or draft export — its Deck and Sideboard
      become the pool.
      <button class="loadbtn" on:click={() => importOpen.set(true)}
        >⬇ Import a pool</button
      >
    </div>
  {:else}
    <p class="lead">
      <b>{$pool.size}</b> cards opened, <b>{$pool.unused}</b> unused. Every colour
      pair on equal footing — pick one, then seed a first 40 and tune it.
    </p>
    <table class="pairs">
      <thead>
        <tr>
          <th>pair</th>
          {#each COLUMNS as [key, label, title] (key)}
            <th class:on={sortKey === key} {title} on:click={() => sortBy(key)}
              >{label}{sortKey === key ? (sortDesc ? " ▾" : " ▴") : ""}</th
            >
          {/each}
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each rows as r (r.pair)}
          <tr>
            <td class="pair"
              >{#each [...r.pair] as c (c)}<Mana
                  sym={c}
                  size="0.95rem"
                />{/each}</td
            >
            {#each COLUMNS as [key] (key)}
              <td>{r[key]}</td>
            {/each}
            <td>
              <button
                class="seedbtn"
                title="Replace the deck with a first 40 in these colours, from the pool"
                disabled={!!seeding}
                on:click={() => seed(r.pair)}
                >{seeding === r.pair ? "…" : "seed"}</button
              >
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    {#if seedError}<div class="err">{seedError}</div>{/if}
  {/if}

  <div class="scan">
    <h4>What the set holds</h4>
    <form class="scanrow" on:submit|preventDefault={runScan}>
      <input
        bind:value={setCode}
        placeholder="set code, e.g. HOB"
        aria-label="Set code"
      />
      <button class="btn btn-ember" type="submit" disabled={scanBusy}
        >{scanBusy ? "…" : "Scan"}</button
      >
    </form>
    {#if scanError}<div class="err">{scanError}</div>{/if}
    {#if scan}
      <ul class="scanout">
        <li>
          <b>{scan.size}</b> cards ({counts(scan.by_rarity)})
        </li>
        <li>
          Removal <b>{scan.removal.total}</b> ({counts(
            scan.removal.by_rarity,
          )}); sweepers: {scan.sweepers.length
            ? scan.sweepers.join(", ")
            : "none"}
        </li>
        <li>
          Creatures <b>{scan.creatures}</b>, evasive <b>{scan.evasion.total}</b>
          ({counts(scan.evasion.by_keyword)}); toughness 6+:
          <b>{scan.toughness_6_plus}</b>
        </li>
        <li>
          Biggest: {scan.biggest_bodies.by_toughness
            .slice(0, 5)
            .map((b) => `${b.name} ${b.power}/${b.toughness}`)
            .join(", ")}
        </li>
      </ul>
    {/if}
  </div>
</div>

<style>
  .poolpanel {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    height: 100%;
    overflow-y: auto;
  }
  .notice {
    color: var(--muted);
    font-style: italic;
    font-size: 0.86rem;
    line-height: 1.5;
  }
  .loadbtn {
    display: block;
    margin-top: 0.6rem;
    background: transparent;
    border: 1px solid var(--brass);
    color: var(--brass-bright);
    border-radius: var(--radius);
    padding: 0.3rem 0.7rem;
  }
  .lead {
    font-size: 0.84rem;
    color: var(--parchment-dim);
    margin: 0;
  }
  .pairs {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }
  .pairs th,
  .pairs td {
    padding: 0.2rem 0.35rem;
    text-align: right;
    border-bottom: 1px solid var(--hairline-soft);
  }
  .pairs th {
    color: var(--muted);
    font-weight: normal;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  .pairs th.on {
    color: var(--brass-bright);
  }
  .pairs td.pair,
  .pairs th:first-child {
    text-align: left;
    white-space: nowrap;
  }
  .seedbtn {
    background: transparent;
    border: 1px solid var(--hairline-soft);
    color: var(--parchment-dim);
    border-radius: 4px;
    font-size: 0.72rem;
    padding: 0.1rem 0.4rem;
  }
  .seedbtn:hover:not(:disabled) {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .scan h4 {
    font-family: var(--display);
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--brass);
    margin: 0 0 0.4rem;
  }
  .scanrow {
    display: flex;
    gap: 0.4rem;
  }
  .scanrow input {
    flex: 1;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.25rem 0.5rem;
  }
  .scanout {
    margin: 0.5rem 0 0;
    padding-left: 1rem;
    font-size: 0.8rem;
    color: var(--parchment-dim);
    line-height: 1.5;
  }
  .err {
    color: var(--fail);
    font-size: 0.8rem;
  }
</style>
