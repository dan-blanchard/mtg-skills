<script>
  import { budgets } from "../lib/store.js";

  const LABELS = {
    lands: "Lands",
    ramp: "Ramp",
    card_draw: "Card draw",
    removal: "Removal",
    board_wipe: "Wraths",
  };
  const ORDER = ["lands", "ramp", "card_draw", "removal", "board_wipe"];
</script>

<div class="panel widget">
  <h3 class="panel-title">Slot Budgets</h3>
  {#if $budgets}
    <div class="rows">
      {#each ORDER as role (role)}
        {#if $budgets[role]}
          <div class="row">
            <div class="head">
              <span class="lbl">{LABELS[role]}</span>
              <span class="num" class:met={$budgets[role].remaining === 0}>
                {$budgets[role].current}/{$budgets[role].target}
              </span>
            </div>
            <div class="track">
              <div
                class="fill"
                class:met={$budgets[role].remaining === 0}
                style="width: {Math.min(
                  100,
                  ($budgets[role].current /
                    Math.max(1, $budgets[role].target)) *
                    100,
                )}%"
              ></div>
            </div>
          </div>
        {/if}
      {/each}
    </div>
    <p class="hint">
      Soft template — nudges, not rules. The land gate is enforced above.
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
