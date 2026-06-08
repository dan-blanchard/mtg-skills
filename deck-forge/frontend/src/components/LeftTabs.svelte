<script>
  import { activeTab } from "../lib/store.js";
  import Find from "./Find.svelte";
  import Commanders from "./Commanders.svelte";
  import Combos from "./Combos.svelte";
  import Export from "./Export.svelte";

  const TABS = [
    ["find", "Find"],
    ["commanders", "Commanders"],
    ["combos", "Combos"],
    ["export", "Export"],
  ];
</script>

<div class="left">
  <div class="tabbar">
    {#each TABS as [id, label] (id)}
      <button
        class="tab"
        class:active={$activeTab === id}
        on:click={() => activeTab.set(id)}
      >
        {label}
      </button>
    {/each}
  </div>
  <div class="tabbody">
    {#if $activeTab === "commanders"}
      <Commanders />
    {:else if $activeTab === "combos"}
      <Combos />
    {:else if $activeTab === "export"}
      <Export />
    {:else}
      <Find />
    {/if}
  </div>
</div>

<style>
  .left {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .tabbar {
    display: flex;
    gap: 0.3rem;
    margin-bottom: 0.7rem;
    flex-shrink: 0;
  }
  .tab {
    flex: 1;
    background: linear-gradient(180deg, #241d16, #1b1612);
    border: 1px solid var(--hairline-soft);
    border-bottom: 2px solid transparent;
    color: var(--parchment-dim);
    border-radius: var(--radius) var(--radius) 0 0;
    padding: 0.45rem 0.5rem;
    font-family: var(--display);
    font-size: 0.78rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    transition: all 0.14s ease;
  }
  .tab:hover {
    color: var(--parchment);
  }
  .tab.active {
    color: var(--brass-bright);
    border-bottom-color: var(--ember);
    box-shadow: 0 -2px 14px rgba(255, 106, 61, 0.12);
  }
  .tabbody {
    flex: 1;
    min-height: 0;
  }
</style>
