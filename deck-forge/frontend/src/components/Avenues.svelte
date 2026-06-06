<script>
  import { avenues, activeTab, exploreAvenue, applySnapshot } from "../lib/store.js";
  import { api } from "../lib/api.js";

  // Scope is only shown when it's contrastive — "yours" is the unremarkable default,
  // so we surface only the cases that change how you build (opponents' / each player).
  const SCOPE_TAG = { opponents: "opponents'", each: "each player" };

  function explore(avenue) {
    exploreAvenue.set(avenue);
    activeTab.set("synergies");
  }

  async function remove(avenue) {
    const r = await api.removeAvenue(avenue.id);
    if (r.ok) applySnapshot(r.data);
  }
</script>

{#if $avenues.length}
  <div class="panel avenues">
    <h3 class="panel-title">Avenues · what your deck cares about</h3>
    <div class="chips">
      {#each $avenues as a (a.id)}
        <button
          class="avenue"
          class:agent={a.source === "agent"}
          title={(a.description || a.label) + " — click to explore"}
          on:click={() => explore(a)}
        >
          <span class="label">{a.label}</span>
          {#if SCOPE_TAG[a.scope]}<span class="scope">{SCOPE_TAG[a.scope]}</span>{/if}
          {#if a.source === "agent"}
            <span
              class="rm"
              role="button"
              tabindex="0"
              title="Remove this avenue"
              on:click|stopPropagation={() => remove(a)}
              on:keydown|stopPropagation={(e) => (e.key === "Enter" ? remove(a) : null)}
            >×</span>
          {/if}
          <span class="go">→</span>
        </button>
      {/each}
    </div>
    <p class="hint">Click an avenue to surface ranked, real-card candidates that feed it.</p>
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
    padding: 0.32rem 0.6rem;
    border: 1px solid var(--hairline);
    border-left: 3px solid var(--brass);
    border-radius: var(--radius);
    background: rgba(200, 150, 75, 0.07);
    color: var(--parchment);
    font-family: var(--body);
    font-size: 0.82rem;
    transition: all 0.14s ease;
  }
  .avenue:hover {
    border-color: var(--brass-bright);
    background: rgba(255, 106, 61, 0.12);
    transform: translateY(-1px);
  }
  /* agent-discovered avenues get the ember accent to distinguish from engine ones */
  .avenue.agent {
    border-left-color: var(--ember);
  }
  .scope {
    font-size: 0.66rem;
    color: var(--warn);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .go {
    color: var(--brass);
    font-weight: 700;
  }
  .rm {
    color: var(--muted);
    font-size: 0.9rem;
    line-height: 1;
    padding: 0 0.1rem;
    border-radius: 3px;
  }
  .rm:hover {
    color: var(--fail);
  }
  .hint {
    margin: 0.6rem 0 0;
    font-size: 0.72rem;
    font-style: italic;
    color: var(--muted);
  }
</style>
