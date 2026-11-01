<script>
  import { budgets } from "../lib/store.js";

  // The rows are the served family template, in its order, each carrying its own
  // label (Command Zone bands for a Commander deck; interaction / card draw / an
  // advisory creature count for 60-card). The fallback names are for a snapshot
  // from before rows carried labels.
  const LABELS = {
    lands: "Lands",
    ramp: "Ramp",
    card_draw: "Card draw",
    interaction: "Interaction",
    board_wipe: "Wraths",
  };
  $: rows = $budgets ? Object.entries($budgets) : [];
</script>

<div class="panel widget">
  <h3 class="panel-title">Slot Budgets</h3>
  {#if $budgets}
    <div class="rows">
      {#each rows as [role, row] (role)}
        {#if row}
          <div class="row" class:advisory={row.advisory}>
            <div class="head">
              <span class="lbl"
                >{row.label ?? LABELS[role] ?? role}{#if row.advisory}
                  <i title="A fact about the deck, not a slot to fill">·adv</i
                  >{/if}</span
              >
              <span class="num" class:met={row.remaining === 0}>
                {row.current}/{row.target}
              </span>
            </div>
            <div class="track">
              <div
                class="fill"
                class:met={row.remaining === 0}
                style="width: {Math.min(
                  100,
                  (row.current / Math.max(1, row.target)) * 100,
                )}%"
              ></div>
            </div>
          </div>
        {/if}
      {/each}
    </div>
    <p class="hint">
      Soft template for this format's family — nudges, not rules. The land gate
      is enforced above.
    </p>
  {:else}
    <p class="empty">No data yet.</p>
  {/if}
</div>

<style>
  .row {
    margin-bottom: 0.55rem;
  }
  .head {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    margin-bottom: 0.2rem;
  }
  .lbl {
    color: var(--parchment-dim);
  }
  .lbl i {
    font-size: 0.7rem;
    color: var(--muted);
    margin-left: 0.3rem;
  }
  .row.advisory .fill {
    opacity: 0.55;
  }
  .num {
    font-family: var(--display);
    color: var(--brass);
  }
  .num.met {
    color: var(--pass);
  }
  .track {
    height: 6px;
    background: rgba(0, 0, 0, 0.35);
    border-radius: 999px;
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: linear-gradient(90deg, var(--brass), var(--brass-bright));
    transition: width 0.35s ease;
  }
  .fill.met {
    background: linear-gradient(90deg, var(--g), var(--pass));
  }
  .hint {
    font-size: 0.7rem;
    color: var(--muted);
    font-style: italic;
    margin: 0.4rem 0 0;
  }
  .empty {
    color: var(--muted);
    font-style: italic;
  }
</style>
