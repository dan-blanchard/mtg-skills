<script>
  import { deck, buildId, buildName, applySnapshot } from "../lib/store.js";
  import { api } from "../lib/api.js";
  import BuildMenu from "./BuildMenu.svelte";
  import FinalizeButton from "./FinalizeButton.svelte";

  let editing = false;
  let draft = "";

  // The Commander-family formats deck-forge builds (paper Commander + Arena Brawl).
  const FORMATS = [
    ["commander", "Commander"],
    ["brawl", "Brawl"],
    ["historic_brawl", "Historic Brawl"],
  ];

  async function changeFormat(e) {
    const r = await api.setFormat(e.target.value);
    if (r.ok) applySnapshot(r.data);
  }

  async function changeMedium(e) {
    const r = await api.setMedium(e.target.value);
    if (r.ok) applySnapshot(r.data);
  }

  async function changeDeckSize(e) {
    const r = await api.setDeckSize(Number(e.target.value));
    if (r.ok) applySnapshot(r.data);
  }

  // Medium toggle only for the Arena-family formats (commander is paper-only); the
  // 60/100 size picker only for paper Historic Brawl (both legal for paper "Brawl").
  $: showMedium = $deck.format === "brawl" || $deck.format === "historic_brawl";
  $: showSize = $deck.format === "historic_brawl" && $deck.medium === "paper";

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
    <h1>deck&#8202;·&#8202;forge</h1>
    <span class="divider"></span>
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

  <div class="meta">
    <BuildMenu />
    <select class="chip format" title="Deck format" on:change={changeFormat}>
      {#each FORMATS as [val, label] (val)}
        <option value={val} selected={val === $deck.format}>{label}</option>
      {/each}
    </select>
    {#if showMedium}
      <select
        class="chip format"
        title="Paper or digital (Arena) — sets the collection & cost mode"
        on:change={changeMedium}
      >
        <option value="digital" selected={$deck.medium === "digital"}
          >Arena</option
        >
        <option value="paper" selected={$deck.medium === "paper"}>Paper</option>
      </select>
    {/if}
    {#if showSize}
      <select
        class="chip format"
        title="Paper Historic Brawl may be 60 or 100 cards"
        on:change={changeDeckSize}
      >
        <option value="100" selected={$deck.deck_size === 100}>100</option>
        <option value="60" selected={$deck.deck_size === 60}>60</option>
      </select>
    {/if}
    <FinalizeButton />
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
    gap: 1rem;
    padding: 0.5rem 1.4rem;
    background: linear-gradient(180deg, #241d16, #1b1612);
    border-bottom: 1px solid var(--hairline);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    min-width: 0;
  }
  .anvil {
    font-size: 1.45rem;
    color: var(--brass-bright);
    filter: drop-shadow(0 0 10px rgba(255, 106, 61, 0.4));
  }
  h1 {
    font-size: 1.15rem;
    color: var(--parchment);
    line-height: 1;
    white-space: nowrap;
  }
  .divider {
    width: 1px;
    height: 1.3rem;
    background: var(--hairline);
    flex-shrink: 0;
  }
  .namebtn {
    background: transparent;
    border: none;
    border-bottom: 1px dashed transparent;
    color: var(--parchment);
    font-family: var(--display);
    font-size: 1rem;
    letter-spacing: 0.02em;
    padding: 0;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
    cursor: text;
  }
  .namebtn:hover {
    color: var(--brass-bright);
    border-bottom-color: var(--hairline);
  }
  .pencil {
    font-size: 0.7rem;
    color: var(--muted);
    flex-shrink: 0;
  }
  .namein {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--brass);
    border-radius: var(--radius);
    color: var(--parchment);
    font-family: var(--display);
    font-size: 1rem;
    padding: 0.12rem 0.45rem;
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
  select.format {
    appearance: none;
    cursor: pointer;
    padding-right: 1.5rem;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='6'%3E%3Cpath d='M0 0l4 6 4-6z' fill='%23d9a441'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.55rem center;
    font-family: var(--body);
  }
  select.format:hover {
    border-color: var(--brass);
  }
  select.format option {
    background: var(--panel);
    color: var(--parchment);
  }
</style>
