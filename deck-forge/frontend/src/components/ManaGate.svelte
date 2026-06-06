<script>
  import { mana, applySnapshot } from "../lib/store.js";
  import { api } from "../lib/api.js";

  let busy = false;

  // Below the FAIL floor → needs lands; otherwise off-color → needs a swap.
  $: belowFloor = $mana ? $mana.land_count < $mana.land_count_floor : false;
  $: colorsOff = $mana ? $mana.color_balance_status !== "PASS" : false;
  $: needsBalance = belowFloor || colorsOff;
  $: balanceLabel = belowFloor
    ? `Balance lands (+${$mana.land_count_floor - $mana.land_count})`
    : "Rebalance colors";

  async function balance() {
    if (busy) return;
    busy = true;
    const r = await api.balanceLands();
    if (r.ok) applySnapshot(r.data);
    busy = false;
  }
</script>

<div class="panel widget">
  <h3 class="panel-title">Mana Gate</h3>
  {#if $mana}
    <div class="gauge">
      <div class="big status-{$mana.land_count_status}">{$mana.land_count}</div>
      <div class="sub">
        lands · target <b>{$mana.recommended_land_count}</b>
      </div>
      <div class="badge bg-{$mana.land_count_status}">{$mana.land_count_status}</div>
    </div>

    {#if needsBalance}
      <button class="btn balance" on:click={balance} disabled={busy}>
        {busy ? "Balancing…" : balanceLabel}
      </button>
    {/if}

    <div class="rows">
      {#if $mana.burgess_formula}
        <div class="row"><span>Burgess floor</span><b>{$mana.burgess_formula.result}</b></div>
        <div class="row"><span>Karsten</span><b>{$mana.karsten_adjustment.result}</b></div>
      {:else if $mana.constructed_land_target}
        <div class="row"><span>Target</span><b>{$mana.constructed_land_target.result}</b></div>
      {/if}
      <div class="row">
        <span>Color balance</span>
        <b class="status-{$mana.color_balance_status}">{$mana.color_balance_status}</b>
      </div>
    </div>

    {#if $mana.color_balance_flags?.length}
      <ul class="flags">
        {#each $mana.color_balance_flags as flag}
          <li>{flag}</li>
        {/each}
      </ul>
    {/if}
  {:else}
    <p class="empty">The forge is cold.</p>
  {/if}
</div>

<style>
  .gauge {
    text-align: center;
    padding: 0.4rem 0 0.8rem;
  }
  .big {
    font-family: var(--display);
    font-size: 3.2rem;
    font-weight: 700;
    line-height: 1;
  }
  .sub {
    color: var(--parchment-dim);
    font-size: 0.82rem;
    margin-top: 0.2rem;
  }
  .badge {
    display: inline-block;
    margin-top: 0.6rem;
    padding: 0.18rem 0.7rem;
    border-radius: 999px;
    font-family: var(--display);
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    color: #15110c;
  }
  .balance {
    display: block;
    width: 100%;
    margin: 0 0 0.7rem;
    text-align: center;
    font-family: var(--display);
    letter-spacing: 0.04em;
  }
  .balance:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .rows {
    border-top: 1px solid var(--hairline-soft);
    padding-top: 0.6rem;
  }
  .row {
    display: flex;
    justify-content: space-between;
    font-size: 0.86rem;
    padding: 0.22rem 0;
    color: var(--parchment-dim);
  }
  .row b {
    color: var(--parchment);
  }
  .flags {
    margin: 0.6rem 0 0;
    padding-left: 1rem;
    font-size: 0.78rem;
    color: var(--warn);
  }
  .empty {
    color: var(--muted);
    font-style: italic;
  }
</style>
