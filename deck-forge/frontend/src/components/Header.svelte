<script>
  import { deck, stats, mana, connected, buildId, buildName, applySnapshot } from "../lib/store.js";
  import { api } from "../lib/api.js";
  import BuildMenu from "./BuildMenu.svelte";

  let editing = false;
  let draft = "";

  function startEdit() {
    draft = $buildName;
    editing = true;
  }
  async function commit() {
    editing = false;
    const name = draft.trim() || "Untitled";
    if (name !== $buildName) {
      const r = await api.renameBuild($buildId, name);
      if (r.ok) applySnapshot(r.data);
    }
  }
  function focusEl(node) {
    node.focus();
    node.select?.();
  }
</script>

<header class="banner">
  <div class="brand">
    <span class="anvil">⚒</span>
    <div class="brand-text">
      <h1>deck&#8202;·&#8202;forge</h1>
      {#if editing}
        <input
          class="namein"
          bind:value={draft}
          use:focusEl
          on:blur={commit}
          on:keydown={(e) => (e.key === "Enter" ? commit() : null)}
        />
      {:else}
        <button class="namebtn" title="Rename this deck" on:click={startEdit}>
          {$buildName}<span class="pencil">✎</span>
        </button>
      {/if}
    </div>
  </div>

  <div class="meta">
    <BuildMenu />
    <span class="chip format">{$deck.format.replace("_", " ")}</span>
    <span class="chip">{$stats?.total_cards ?? 0} cards</span>
    {#if $mana}
      <span class="chip gate status-{$mana.overall_status}">
        <span class="dot bg-{$mana.overall_status}"></span>{$mana.overall_status}
      </span>
    {/if}
    <span class="live" class:on={$connected} title={$connected ? "live" : "offline"}>●</span>
  </div>
</header>

<style>
  .banner {
    position: sticky;
    top: 0;
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.8rem 1.4rem;
    background: linear-gradient(180deg, #241d16, #1b1612);
    border-bottom: 1px solid var(--hairline);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.85rem;
  }
  .anvil {
    font-size: 1.8rem;
    color: var(--brass-bright);
    filter: drop-shadow(0 0 10px rgba(255, 106, 61, 0.4));
  }
  h1 {
    font-size: 1.45rem;
    color: var(--parchment);
    line-height: 1;
  }
  .namebtn {
    margin: 0.2rem 0 0;
    background: transparent;
    border: none;
    border-bottom: 1px dashed transparent;
    color: var(--parchment-dim);
    font-family: var(--body);
    font-size: 0.84rem;
    padding: 0;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    cursor: text;
  }
  .namebtn:hover {
    color: var(--brass-bright);
    border-bottom-color: var(--hairline);
  }
  .pencil {
    font-size: 0.7rem;
    color: var(--muted);
  }
  .namein {
    margin: 0.2rem 0 0;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--brass);
    border-radius: var(--radius);
    color: var(--parchment);
    font-family: var(--body);
    font-size: 0.84rem;
    padding: 0.1rem 0.4rem;
    width: 16rem;
  }
  .meta {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .chip {
    font-size: 0.78rem;
    padding: 0.28rem 0.6rem;
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.2);
    text-transform: capitalize;
  }
  .format {
    color: var(--brass-bright);
    border-color: var(--hairline);
  }
  .gate {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--display);
    letter-spacing: 0.1em;
    font-size: 0.72rem;
  }
  .dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    display: inline-block;
  }
  .live {
    color: #4a3c28;
    font-size: 0.7rem;
    transition: color 0.3s;
  }
  .live.on {
    color: var(--pass);
    filter: drop-shadow(0 0 5px rgba(74, 158, 99, 0.7));
  }
</style>
