<script>
  import {
    deck,
    buildId,
    buildName,
    formatOptions,
    applySnapshot,
  } from "../lib/store.js";
  import { api } from "../lib/api.js";
  import BuildMenu from "./BuildMenu.svelte";
  import FinalizeButton from "./FinalizeButton.svelte";

  let editing = false;
  let draft = "";

  const MEDIUM_LABEL = { digital: "Arena", paper: "Paper" };

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

  // The pickers derive from the served format table: the medium toggle only where
  // the format has more than one medium, the size picker only where the current
  // medium may choose (paper Historic Brawl: 60 or 100).
  $: current = $formatOptions.find((f) => f.id === $deck.format);
  $: media = current?.media ?? [];
  $: showMedium = media.length > 1;
  $: sizeChoices = current?.size_choices?.[$deck.medium] ?? [];
  $: showSize = sizeChoices.length > 1;

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
      {#each $formatOptions as f (f.id)}
        <option value={f.id} selected={f.id === $deck.format}>{f.label}</option>
      {/each}
    </select>
    {#if showMedium}
      <select
        class="chip format"
        title="Paper or digital (Arena) — sets the collection & cost mode"
        on:change={changeMedium}
      >
        {#each media as m (m)}
          <option value={m} selected={m === $deck.medium}
            >{MEDIUM_LABEL[m] ?? m}</option
          >
        {/each}
      </select>
    {/if}
    {#if showSize}
      <select
        class="chip format"
        title="Paper Historic Brawl may be 60 or 100 cards"
        on:change={changeDeckSize}
      >
        {#each sizeChoices as n (n)}
          <option value={n} selected={n === $deck.deck_size}>{n}</option>
        {/each}
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
