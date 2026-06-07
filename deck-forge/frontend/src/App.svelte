<script>
  import { onMount, onDestroy } from "svelte";
  import { api, connectEvents } from "./lib/api.js";
  import { applySnapshot, connected, agentAttached } from "./lib/store.js";
  import Header from "./components/Header.svelte";
  import LeftTabs from "./components/LeftTabs.svelte";
  import Avenues from "./components/Avenues.svelte";
  import DeckList from "./components/DeckList.svelte";
  import Curve from "./components/Curve.svelte";
  import ForgeFriend from "./components/ForgeFriend.svelte";
  import StatusBar from "./components/StatusBar.svelte";
  import CardPreview from "./components/CardPreview.svelte";
  import ManaGateModal from "./components/ManaGateModal.svelte";

  let es;
  let statusTimer;

  // The right rail now holds only the Forge-Friend, so it auto-collapses when no session
  // is attached (a tall empty column otherwise) — but a manual toggle persists until the
  // next attach/detach transition, so the user stays in control between transitions.
  let railCollapsed = false;
  let prevAttached = null;
  $: {
    const a = $agentAttached;
    if (prevAttached !== null && a !== prevAttached) railCollapsed = !a;
    // Persisted across reactive re-runs to detect attach/detach transitions
    // (read at the top of this block on the next run, not within it).
    // eslint-disable-next-line no-useless-assignment
    prevAttached = a;
  }

  async function refreshAgent() {
    const r = await api.agentStatus();
    agentAttached.set(r.ok && !!r.data.attached);
  }

  onMount(async () => {
    try {
      applySnapshot(await api.snapshot());
    } catch (err) {
      console.error("snapshot failed", err);
    }
    es = connectEvents({
      onSnapshot: applySnapshot,
      onOpen: () => connected.set(true),
      onError: () => connected.set(false),
    });
    refreshAgent();
    statusTimer = setInterval(refreshAgent, 4000);
  });

  onDestroy(() => {
    es && es.close();
    clearInterval(statusTimer);
  });
</script>

<div class="shell">
  <Header />

  <main class="bench" class:rail-collapsed={railCollapsed}>
    <section class="col find-col"><LeftTabs /></section>

    <section class="col deck-col">
      <Avenues />
      <Curve />
      <div class="deck-wrap"><DeckList /></div>
    </section>

    <aside class="rail" class:collapsed={railCollapsed}>
      <button
        class="rail-toggle"
        title={railCollapsed ? "Show Forge-Friend" : "Hide Forge-Friend"}
        on:click={() => (railCollapsed = !railCollapsed)}
      >
        {railCollapsed ? "‹" : "›"}
      </button>
      {#if railCollapsed}
        <span class="rail-spine">Forge-Friend</span>
      {:else}
        <ForgeFriend />
      {/if}
    </aside>
  </main>

  <StatusBar />
</div>

<CardPreview />
<ManaGateModal />

<style>
  .shell {
    position: relative;
    z-index: 2;
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  .bench {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(340px, 1.1fr) minmax(300px, 1fr) 320px;
    /* Bound the single row to the bench height (minmax(0,1fr)), NOT to content —
       otherwise a tall deck list grows the column past 100vh and paints over the
       footer instead of scrolling internally. overflow:hidden is the backstop. */
    grid-template-rows: minmax(0, 1fr);
    gap: 1rem;
    padding: 1rem 1.4rem;
    overflow: hidden;
  }
  .bench.rail-collapsed {
    grid-template-columns: minmax(340px, 1.1fr) minmax(300px, 1fr) 34px;
  }
  .col {
    height: 100%;
    min-height: 0;
  }
  .deck-col {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  .deck-wrap {
    flex: 1;
    min-height: 0;
  }
  .rail {
    position: relative;
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
  }
  .rail.collapsed {
    overflow: hidden;
    border-left: 1px solid var(--hairline-soft);
  }
  .rail-toggle {
    position: absolute;
    top: 0;
    right: 0;
    z-index: 3;
    width: 1.6rem;
    height: 1.6rem;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    color: var(--parchment-dim);
    font-size: 0.9rem;
    line-height: 1;
  }
  .rail-toggle:hover {
    color: var(--brass-bright);
    border-color: var(--brass);
  }
  .rail.collapsed .rail-toggle {
    left: 0;
    right: auto;
  }
  .rail-spine {
    position: absolute;
    top: 3rem;
    left: 50%;
    transform: translateX(-50%) rotate(180deg);
    writing-mode: vertical-rl;
    font-family: var(--display);
    font-size: 0.7rem;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--muted);
    white-space: nowrap;
  }
  :global(.widget) {
    padding: 0.9rem 1rem;
  }
  @media (max-width: 1100px) {
    .shell {
      height: auto;
      min-height: 100vh;
    }
    .bench,
    .bench.rail-collapsed {
      grid-template-columns: 1fr;
      height: auto;
    }
    .col,
    .rail {
      height: auto;
    }
    .rail.collapsed {
      display: none;
    }
  }
</style>
