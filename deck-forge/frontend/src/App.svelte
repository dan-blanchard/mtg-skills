<script>
  import { onMount, onDestroy } from "svelte";
  import { api, connectEvents } from "./lib/api.js";
  import { applySnapshot, connected } from "./lib/store.js";
  import Header from "./components/Header.svelte";
  import LeftTabs from "./components/LeftTabs.svelte";
  import Avenues from "./components/Avenues.svelte";
  import DeckList from "./components/DeckList.svelte";
  import ManaGate from "./components/ManaGate.svelte";
  import ForgeFriend from "./components/ForgeFriend.svelte";
  import Warnings from "./components/Warnings.svelte";
  import Budgets from "./components/Budgets.svelte";
  import Curve from "./components/Curve.svelte";
  import Counts from "./components/Counts.svelte";
  import ColorSources from "./components/ColorSources.svelte";
  import Finalize from "./components/Finalize.svelte";
  import CardPreview from "./components/CardPreview.svelte";

  let es;

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
  });

  onDestroy(() => es && es.close());
</script>

<Header />

<main class="bench">
  <section class="col"><LeftTabs /></section>
  <section class="col deck-col">
    <Avenues />
    <div class="deck-wrap"><DeckList /></div>
  </section>
  <aside class="rail">
    <ForgeFriend />
    <Warnings />
    <ManaGate />
    <Budgets />
    <Curve />
    <Counts />
    <ColorSources />
    <Finalize />
  </aside>
</main>

<CardPreview />

<style>
  .bench {
    position: relative;
    z-index: 2;
    display: grid;
    grid-template-columns: minmax(340px, 1.1fr) minmax(300px, 1fr) 340px;
    gap: 1rem;
    padding: 1rem 1.4rem 3rem;
    align-items: start;
    height: calc(100vh - 70px);
  }
  .col {
    height: 100%;
    min-height: 0;
  }
  .deck-col {
    display: flex;
    flex-direction: column;
  }
  .deck-wrap {
    flex: 1;
    min-height: 0;
  }
  .rail {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    height: 100%;
    overflow-y: auto;
  }
  :global(.widget) {
    padding: 0.9rem 1rem;
  }
  @media (max-width: 1100px) {
    .bench {
      grid-template-columns: 1fr;
      height: auto;
    }
    .col,
    .rail {
      height: auto;
    }
  }
</style>
