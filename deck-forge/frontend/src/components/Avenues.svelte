<script>
  import { signals } from "../lib/store.js";

  const SCOPE_TAG = { you: "yours", opponents: "opponents'", each: "each player", any: "" };
</script>

{#if $signals.length}
  <div class="panel avenues">
    <h3 class="panel-title">Avenues · what your deck cares about</h3>
    <div class="chips">
      {#each $signals as s}
        <div class="avenue" class:dim={!s.actionable} title={s.avenue || s.key}>
          <span class="label">{s.label}</span>
          {#if SCOPE_TAG[s.scope]}<span class="scope">{SCOPE_TAG[s.scope]}</span>{/if}
        </div>
      {/each}
    </div>
    <p class="hint">Discover synergy packages that feed these from the Synergies tab.</p>
  </div>
{/if}

<style>
  .avenues {
    padding: 0.9rem 1rem;
    margin-bottom: 1rem;
    flex-shrink: 0;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }
  .avenue {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.6rem;
    border: 1px solid var(--hairline);
    border-left: 3px solid var(--brass);
    border-radius: var(--radius);
    background: rgba(200, 150, 75, 0.07);
    font-size: 0.82rem;
  }
  .avenue.dim {
    border-left-color: var(--hairline-soft);
    opacity: 0.6;
  }
  .scope {
    font-size: 0.66rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .hint {
    margin: 0.6rem 0 0;
    font-size: 0.72rem;
    font-style: italic;
    color: var(--muted);
  }
</style>
