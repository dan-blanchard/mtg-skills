<script>
  import { api } from "../lib/api.js";
  import { applySnapshot } from "../lib/store.js";

  let open = false;
  let builds = [];
  let current = null;
  let loading = false;

  async function refresh() {
    loading = true;
    const r = await api.builds();
    loading = false;
    if (r.ok) {
      builds = r.data.builds;
      current = r.data.current;
    }
  }

  async function toggle() {
    open = !open;
    if (open) await refresh();
  }

  async function newBuild() {
    const r = await api.buildsNew("commander", "Untitled");
    if (r.ok) {
      applySnapshot(r.data);
      open = false;
    }
  }

  async function load(id) {
    const r = await api.buildsLoad(id);
    if (r.ok) {
      applySnapshot(r.data);
      open = false;
    }
  }

  async function remove(id) {
    const r = await api.deleteBuild(id);
    if (r.ok) {
      builds = r.data.builds;
      current = r.data.current;
    }
  }
</script>

<div class="bm">
  <button class="chip" on:click={newBuild}>＋ New</button>
  <button class="chip" on:click={toggle}>Library ▾</button>
  {#if open}
    <div class="menu">
      {#if loading}
        <div class="empty">Loading…</div>
      {:else if builds.length}
        {#each builds as b (b.id)}
          <div class="row" class:current={b.id === current}>
            <button class="item" on:click={() => load(b.id)}>
              <span class="nm">{b.name}{b.id === current ? " ·current" : ""}</span>
              <span class="meta">{b.format.replace("_", " ")} · {b.card_count}</span>
            </button>
            <button class="del" title="Delete this build" on:click={() => remove(b.id)}>×</button>
          </div>
        {/each}
      {:else}
        <div class="empty">No saved builds yet.</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .bm {
    position: relative;
    display: flex;
    gap: 0.4rem;
  }
  .chip {
    font-size: 0.76rem;
    padding: 0.28rem 0.6rem;
    border: 1px solid var(--hairline);
    border-radius: 999px;
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.25);
  }
  .chip:hover {
    color: var(--brass-bright);
    border-color: var(--brass);
  }
  .menu {
    position: absolute;
    top: 120%;
    right: 0;
    z-index: 20;
    min-width: 16rem;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 0.35rem;
  }
  .row {
    display: flex;
    align-items: center;
    border-radius: var(--radius);
  }
  .row:hover {
    background: rgba(255, 220, 160, 0.06);
  }
  .row.current {
    border-left: 2px solid var(--brass);
  }
  .item {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex: 1;
    background: transparent;
    border: none;
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    border-radius: var(--radius);
    text-align: left;
  }
  .del {
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 1rem;
    line-height: 1;
    padding: 0 0.5rem;
    border-radius: var(--radius);
  }
  .del:hover {
    color: var(--fail);
  }
  .meta {
    font-size: 0.7rem;
    color: var(--muted);
  }
  .empty {
    padding: 0.5rem;
    font-size: 0.8rem;
    color: var(--muted);
    font-style: italic;
  }
</style>
