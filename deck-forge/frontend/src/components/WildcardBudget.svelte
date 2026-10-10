<script>
  // The one wildcard-budget editor (ADR-0059): the four per-rarity inputs over the
  // shared wildcardBudget store and the label saying where its numbers came from.
  // Tune (layout "grid") and the Meta panel (layout "inline") both mount it, so an
  // edit in either is the other's budget.
  import {
    wildcardBudget,
    wildcardBudgetLabel,
    editWildcardBudget,
  } from "../lib/store.js";
  import { WC_TIERS } from "../lib/mana.js";

  export let layout = "grid";

  // A blank or half-typed entry waits; anything else goes to the store, which
  // cleans it (whole, ≥ 0). Leaving the field shows the value the store holds.
  function edit(tier, input) {
    if (input.value === "" || !Number.isFinite(Number(input.value))) return;
    editWildcardBudget(tier, input.value);
  }
  function settle(tier, input) {
    input.value = String($wildcardBudget[tier]);
  }
</script>

<div class="wcb {layout}">
  <div class="inputs">
    {#each WC_TIERS as [k, letter, cls] (k)}
      <label class="wc-in" title="{k} wildcards">
        <span class="wc-{cls}">{letter}</span>
        <input
          type="number"
          min="0"
          step="1"
          inputmode="numeric"
          aria-label="{k} wildcards"
          value={$wildcardBudget[k]}
          on:input={(e) => edit(k, e.currentTarget)}
          on:blur={(e) => settle(k, e.currentTarget)}
        />
      </label>
    {/each}
  </div>
  <span
    class="src"
    class:assumed={$wildcardBudgetLabel.assumed}
    title={$wildcardBudgetLabel.title}>{$wildcardBudgetLabel.text}</span
  >
</div>

<style>
  .wcb {
    display: flex;
    gap: 0.3rem 0.5rem;
  }
  .wcb.grid {
    flex-direction: column;
  }
  .wcb.inline {
    flex-wrap: wrap;
    align-items: center;
  }
  .grid .inputs {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.4rem;
  }
  .inline .inputs {
    display: flex;
    gap: 0.5rem;
  }
  .wc-in {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .wc-in span {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    width: 1ch;
    text-align: center;
  }
  input {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: 4px;
    color: var(--parchment);
  }
  .grid input {
    width: 100%;
    min-width: 0;
    padding: 0.35rem 0.45rem;
    font-size: 0.9rem;
  }
  .inline input {
    width: 3.2rem;
    padding: 0.1rem 0.3rem;
    font-size: 0.78rem;
  }
  .src {
    color: var(--muted);
    font-size: 0.72rem;
  }
  .src.assumed {
    color: var(--warn);
  }
</style>
