<script>
  import {
    avenues,
    activeTab,
    exploreAvenue,
    applySnapshot,
  } from "../lib/store.js";
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

  // Pin a lane as "focused": the candidate ✦ score then counts only focused lanes (#2).
  async function toggleFocus(avenue) {
    const r = await api.focusAvenue(avenue.id);
    if (r.ok) applySnapshot(r.data);
  }

  $: anyFocused = $avenues.some((a) => a.focused);
</script>

{#if $avenues.length}
  <div class="panel avenues">
    <h3 class="panel-title">Avenues · what your deck cares about</h3>
    <div class="chips">
      {#each $avenues as a (a.id)}
        <button
          class="avenue"
          class:agent={a.source === "agent"}
          class:focused={a.focused}
          title={(a.description || a.label) + " — click to explore"}
          on:click={() => explore(a)}
        >
          <span
            class="pin"
            class:on={a.focused}
            role="button"
            tabindex="0"
            title={a.focused
              ? "Focused — the synergy score counts this lane. Click to unpin."
              : "Pin as a lane you're building toward (scopes the synergy score)"}
            on:click|stopPropagation={() => toggleFocus(a)}
            on:keydown|stopPropagation={(e) =>
              e.key === "Enter" ? toggleFocus(a) : null}>✦</span
          >
          <span class="label">{a.label}</span>
          {#if SCOPE_TAG[a.scope]}<span class="scope">{SCOPE_TAG[a.scope]}</span
            >{/if}
          {#if a.source === "agent"}
            <span
              class="rm"
              role="button"
              tabindex="0"
              title="Remove this avenue"
              on:click|stopPropagation={() => remove(a)}
              on:keydown|stopPropagation={(e) =>
                e.key === "Enter" ? remove(a) : null}>×</span
            >
          {/if}
          <span class="go">→</span>
        </button>
      {/each}
    </div>
    <p class="hint">
      {#if anyFocused}
        <b class="lit">✦ focused</b> — the synergy score counts only your pinned lanes.
        Click ✦ to pin / unpin.
      {:else}
        Click a lane for ranked candidates. Pin <span class="lit">✦</span> the lanes
        you're building toward to scope the synergy score.
      {/if}
    </p>
  </div>
{/if}

<style>
  .avenues {
    padding: 0.9rem 1rem;
    /* spacing between deck-col children is owned by the parent's `gap` now;
       a margin here doubled the Avenues→Curve gap vs Curve→Deck. */
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
  /* a pinned lane: full ember frame + glow, so the focused set reads at a glance */
  .avenue.focused {
    border-color: var(--ember);
    border-left-color: var(--ember);
    background: rgba(255, 106, 61, 0.12);
    box-shadow: 0 0 12px rgba(255, 106, 61, 0.18);
  }
  .pin {
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1;
    opacity: 0.55;
    transition: all 0.14s ease;
    cursor: pointer;
  }
  .pin:hover {
    color: var(--brass-bright);
    opacity: 1;
  }
  .pin.on {
    color: var(--ember);
    opacity: 1;
    text-shadow: 0 0 8px rgba(255, 106, 61, 0.6);
  }
  .lit {
    color: var(--ember);
    font-style: normal;
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
