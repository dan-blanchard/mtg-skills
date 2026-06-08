<script>
  // Import a Collection into a slot (#2, ADR-0018). Distinct from the deck import: this
  // targets a global Collection slot (paper / arena), not a build. Ownership is then
  // DERIVED per snapshot from the active slot. Paste text or upload a CSV (Untapped /
  // Moxfield collection exports are the common case).
  import {
    collectionOpen,
    collection,
    deck,
    applySnapshot,
  } from "../lib/store.js";
  import { api } from "../lib/api.js";

  const SLOTS = [
    ["paper", "Paper", "Commander"],
    ["arena", "Arena", "Brawl / Historic Brawl"],
  ];

  let text = "";
  let slot = "paper";
  let busy = false;
  let error = "";
  let result = null;

  // Default the slot to whichever matches the live deck's format, on open.
  $: defaultSlot = $deck.format === "commander" ? "paper" : "arena";
  $: if ($collectionOpen && result === null && !busy) slot = defaultSlot;

  function close() {
    collectionOpen.set(false);
    text = "";
    error = "";
    result = null;
    busy = false;
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (file) text = await file.text();
  }

  async function submit() {
    if (!text.trim() || busy) return;
    busy = true;
    error = "";
    const r = await api.importCollection(text, slot);
    busy = false;
    if (!r.ok) {
      error = r.data.error || `import failed (${r.status})`;
      return;
    }
    applySnapshot(r.data);
    result = { slot: r.data.slot, size: r.data.size };
  }

  async function clearSlot(s) {
    if (busy) return;
    busy = true;
    const r = await api.clearCollection(s);
    busy = false;
    if (r.ok) applySnapshot(r.data);
  }

  $: slots = $collection?.slots || {};
</script>

{#if $collectionOpen}
  <div
    class="backdrop"
    on:click|self={close}
    on:keydown={(e) => (e.key === "Escape" ? close() : null)}
    role="presentation"
  >
    <div
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-label="Import a collection"
    >
      <header>
        <h2>📦 Import a collection</h2>
        <button class="x" title="Close" on:click={close}>×</button>
      </header>

      {#if result}
        <div class="done">
          <p class="ok">
            {result.slot === "paper" ? "Paper" : "Arena"} collection loaded —
            {result.size} cards.
          </p>
          <p class="dim">
            Owned cards now carry a badge in the deck, and the Commanders tab
            can rank what you can build from it.
          </p>
          <button class="btn btn-ember" on:click={close}>Done</button>
        </div>
      {:else}
        <p class="hint">
          Paste or upload an owned-cards export (Untapped / Moxfield CSV, or any
          list). It's stored globally per slot — a paper Commander deck reads
          the paper slot, a Brawl / Historic Brawl deck reads the Arena slot.
          Ownership is derived live; nothing is stored on a build.
        </p>
        <div class="slots">
          {#each SLOTS as [v, label, note] (v)}
            <label class="slotpick" class:on={slot === v}>
              <input type="radio" bind:group={slot} value={v} />
              <span class="snm">{label}</span>
              <span class="snote">{note}</span>
              {#if slots[v]}<span class="ssz">{slots[v]} loaded</span>{/if}
            </label>
          {/each}
        </div>
        <textarea
          bind:value={text}
          rows="9"
          placeholder="Paste or upload a CSV — e.g.  Quantity,Name · 4,Llanowar Elves · 1,Sol Ring …"
        ></textarea>
        <div class="row between">
          <div class="left">
            <label class="file">
              <input
                type="file"
                accept=".txt,.csv,text/plain,text/csv"
                on:change={onFile}
              />
              <span>📄 Upload CSV…</span>
            </label>
            {#if slots[slot]}
              <button class="link" on:click={() => clearSlot(slot)}
                >Clear {slot}</button
              >
            {/if}
          </div>
          <div class="actions">
            {#if error}<span class="err">{error}</span>{/if}
            <button class="btn ghost" on:click={close}>Cancel</button>
            <button
              class="btn btn-ember"
              disabled={busy || !text.trim()}
              on:click={submit}>{busy ? "Loading…" : "📦 Load"}</button
            >
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(0, 0, 0, 0.6);
    display: grid;
    place-items: center;
    padding: 1.5rem;
  }
  .modal {
    width: min(38rem, 100%);
    max-height: 90vh;
    overflow-y: auto;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 1.1rem 1.3rem;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.6rem;
  }
  h2 {
    font-family: var(--display);
    font-size: 1.05rem;
    color: var(--brass-bright);
  }
  .x {
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 1.4rem;
    line-height: 1;
  }
  .x:hover {
    color: var(--fail);
  }
  .hint {
    font-size: 0.82rem;
    color: var(--parchment-dim);
    margin-bottom: 0.7rem;
  }
  .slots {
    display: flex;
    gap: 0.6rem;
    margin-bottom: 0.7rem;
  }
  .slotpick {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    padding: 0.5rem 0.7rem;
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    cursor: pointer;
  }
  .slotpick.on {
    border-color: var(--brass);
    background: rgba(200, 150, 75, 0.08);
  }
  .slotpick input {
    display: none;
  }
  .snm {
    font-family: var(--display);
    color: var(--parchment);
    font-size: 0.9rem;
  }
  .snote {
    font-size: 0.7rem;
    color: var(--muted);
  }
  .ssz {
    font-size: 0.68rem;
    color: var(--pass);
  }
  textarea {
    width: 100%;
    resize: vertical;
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.6rem;
    font-family: var(--mono, monospace);
    font-size: 0.85rem;
    line-height: 1.4;
  }
  textarea:focus {
    outline: none;
    border-color: var(--brass);
  }
  .row {
    display: flex;
    gap: 0.7rem;
    margin-top: 0.7rem;
  }
  .row.between {
    justify-content: space-between;
    align-items: center;
  }
  .left {
    display: flex;
    align-items: center;
    gap: 0.7rem;
  }
  .file {
    position: relative;
    overflow: hidden;
    display: inline-flex;
    cursor: pointer;
    font-size: 0.78rem;
    color: var(--parchment-dim);
    border: 1px dashed var(--hairline);
    border-radius: var(--radius);
    padding: 0.4rem 0.7rem;
  }
  .file:hover {
    color: var(--brass-bright);
    border-color: var(--brass);
  }
  .file input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }
  .link {
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 0.76rem;
    text-decoration: underline;
    cursor: pointer;
  }
  .link:hover {
    color: var(--fail);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .btn {
    padding: 0.45rem 1rem;
    border-radius: var(--radius);
    border: 1px solid var(--hairline);
    color: var(--parchment);
    font-family: var(--display);
    font-size: 0.82rem;
    letter-spacing: 0.04em;
  }
  .btn.ghost:hover {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .btn:disabled {
    opacity: 0.5;
  }
  .err {
    color: var(--fail);
    font-size: 0.8rem;
  }
  .done .ok {
    color: var(--pass);
    font-family: var(--display);
  }
  .dim {
    color: var(--muted);
    font-size: 0.82rem;
    margin-top: 0.4rem;
  }
</style>
