<script>
  // The land-health detail surface — opened by clicking the footer's land pill.
  // It's a click-to-open MODAL (not a hover popover) because it carries ACTIONS
  // (Balance / Trim / Rebalance): a hover surface can't host buttons. See the
  // disclosure rule in CONTEXT — read-only → hover, actionable → click.
  import { mana, manaModalOpen, applySnapshot } from "../lib/store.js";
  import { landState } from "../lib/mana.js";
  import { api } from "../lib/api.js";

  let busy = false;
  $: ls = landState($mana);
  $: colorsOff = $mana ? $mana.color_balance_status !== "PASS" : false;

  // Tri-state remedy, by severity: too few → add, too many → trim, else off-color → swap.
  $: action = !ls
    ? null
    : ls.short > 0
      ? {
          label: `Balance lands (+${ls.short})`,
          run: api.balanceLands,
          kind: "add",
        }
      : ls.status === "FLOOD"
        ? {
            label: `Trim lands (−${ls.over})`,
            run: api.trimLands,
            kind: "trim",
          }
        : colorsOff
          ? { label: "Rebalance colors", run: api.balanceLands, kind: "swap" }
          : null;

  async function act() {
    if (busy || !action) return;
    busy = true;
    const r = await action.run();
    if (r.ok) applySnapshot(r.data);
    busy = false;
  }

  function close() {
    manaModalOpen.set(false);
  }
  function onKey(e) {
    if (e.key === "Escape") close();
  }
</script>

<svelte:window on:keydown={onKey} />

{#if $manaModalOpen && ls}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="scrim" on:click={close} role="presentation">
    <!-- Escape closes (window handler above); stopPropagation keeps inside-clicks open -->
    <div
      class="modal panel"
      on:click|stopPropagation
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <header>
        <h3 class="panel-title">Mana Gate</h3>
        <button class="x" on:click={close} aria-label="Close">×</button>
      </header>

      <div class="hero">
        <div class="lands status-{ls.status}">
          <span class="n">{ls.count}</span>
          <span class="u">lands</span>
        </div>
        <div class="meta">
          <span class="badge bg-{ls.status}">{ls.status}</span>
          <span class="tgt">target <b>{ls.recommended}</b></span>
        </div>
      </div>

      {#if action}
        <button
          class="btn act"
          class:ember={action.kind !== "trim"}
          class:trim={action.kind === "trim"}
          on:click={act}
          disabled={busy}
        >
          {busy ? "Working the bellows…" : action.label}
        </button>
      {/if}

      <div class="band" title="The healthy land window for this deck">
        <span class="edge">floor {ls.floor}</span>
        <span class="edge">flood {ls.ceiling}</span>
      </div>

      <div class="rows">
        {#if $mana.burgess_formula}
          <div class="row">
            <span>Burgess floor</span>
            <span class="hint"
              >{$mana.burgess_formula.colors}c · cmc {$mana.burgess_formula
                .commander_cmc}</span
            >
            <b>{$mana.burgess_formula.result}</b>
          </div>
          <div class="row">
            <span>Karsten</span>
            <span class="hint">ramp {$mana.karsten_adjustment.ramp_count}</span>
            <b>{$mana.karsten_adjustment.result}</b>
          </div>
        {:else if $mana.constructed_land_target}
          <div class="row">
            <span>Target</span><span class="hint"></span><b
              >{$mana.constructed_land_target.result}</b
            >
          </div>
        {/if}
        <div class="row">
          <span>Color balance</span>
          <span class="hint"></span>
          <b class="status-{$mana.color_balance_status}"
            >{$mana.color_balance_status}</b
          >
        </div>
      </div>

      {#if $mana.color_balance_flags?.length}
        <ul class="flags">
          {#each $mana.color_balance_flags as flag}<li>{flag}</li>{/each}
        </ul>
      {/if}

      {#if ls.status === "FLOOD"}
        <p class="note">
          Over the flood line (target + 2). Trim removes basics back to {ls.recommended}
          — but it's only a nudge: an all-lands combo deck is a fine reason to ignore
          it.
        </p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 90;
    display: grid;
    place-items: center;
    background:
      radial-gradient(
        120% 90% at 50% 100%,
        rgba(255, 106, 61, 0.1),
        transparent 60%
      ),
      rgba(10, 8, 6, 0.7);
    backdrop-filter: blur(3px);
    animation: fade 0.16s ease both;
  }
  .modal {
    width: min(420px, calc(100vw - 2rem));
    padding: 1.1rem 1.2rem 1.3rem;
    animation: rise 0.2s ease both;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  header .panel-title {
    margin: 0;
  }
  .x {
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 1.4rem;
    line-height: 1;
    padding: 0 0.2rem;
  }
  .x:hover {
    color: var(--fail);
  }
  .hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 0.9rem 0 0.8rem;
  }
  .lands {
    display: flex;
    align-items: baseline;
    gap: 0.45rem;
  }
  .lands .n {
    font-family: var(--display);
    font-size: 2.6rem;
    font-weight: 700;
    line-height: 1;
  }
  .lands .u {
    font-size: 0.8rem;
    color: var(--parchment-dim);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.4rem;
  }
  .badge {
    padding: 0.18rem 0.7rem;
    border-radius: 999px;
    font-family: var(--display);
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    color: #15110c;
  }
  .tgt {
    font-size: 0.82rem;
    color: var(--parchment-dim);
  }
  .act {
    width: 100%;
    text-align: center;
    font-family: var(--display);
    letter-spacing: 0.06em;
    margin-bottom: 0.9rem;
  }
  .act.ember {
    background: linear-gradient(180deg, var(--ember), var(--ember-deep));
    border-color: var(--ember-deep);
    color: #1a0f08;
    font-weight: 600;
  }
  .act.trim {
    border-color: var(--flood);
    color: var(--flood);
  }
  .act.trim:hover {
    background: rgba(74, 144, 217, 0.12);
    box-shadow: 0 0 14px rgba(74, 144, 217, 0.25);
  }
  .act:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .band {
    display: flex;
    justify-content: space-between;
    font-size: 0.68rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    border-top: 1px solid var(--hairline-soft);
    border-bottom: 1px solid var(--hairline-soft);
    padding: 0.4rem 0;
  }
  .rows {
    margin-top: 0.6rem;
  }
  .row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    align-items: baseline;
    gap: 0.6rem;
    font-size: 0.88rem;
    padding: 0.26rem 0;
    color: var(--parchment-dim);
  }
  .row .hint {
    font-size: 0.72rem;
    color: var(--muted);
    font-style: italic;
  }
  .row b {
    color: var(--parchment);
    font-family: var(--display);
    min-width: 1.6rem;
    text-align: right;
  }
  .flags {
    margin: 0.6rem 0 0;
    padding-left: 1rem;
    font-size: 0.8rem;
    color: var(--warn);
  }
  .note {
    margin: 0.8rem 0 0;
    font-size: 0.78rem;
    font-style: italic;
    color: var(--flood);
    line-height: 1.5;
  }
</style>
