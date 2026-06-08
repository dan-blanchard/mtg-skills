<script>
  // Import an existing deck list (#1, ADR-0017). Paste text or upload a file (Moxfield /
  // Arena / MTGO / CSV / plain — auto-detected by the backend); pick the game format;
  // the hub parses it in-process and seeds a NEW build (never overwrites the live one).
  import { importOpen, deck, applySnapshot } from "../lib/store.js";
  import { api } from "../lib/api.js";

  const FORMATS = [
    ["commander", "Commander"],
    ["brawl", "Brawl"],
    ["historic_brawl", "Historic Brawl"],
  ];

  let text = "";
  let name = "";
  let format = "commander";
  let busy = false;
  let error = "";
  let result = null;
  let fileEl;

  // Default the format to whatever the live deck is on, each time the dialog opens.
  $: if ($importOpen && !busy && result === null && format === "commander")
    format = $deck.format || "commander";

  function close() {
    importOpen.set(false);
    text = "";
    name = "";
    error = "";
    result = null;
    busy = false;
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    text = await file.text();
    if (!name) name = file.name.replace(/\.[^.]+$/, "");
  }

  async function submit() {
    if (!text.trim() || busy) return;
    busy = true;
    error = "";
    const r = await api.importDeck(text, format, name.trim() || null);
    busy = false;
    if (!r.ok) {
      error = r.data.error || `import failed (${r.status})`;
      return;
    }
    applySnapshot(r.data);
    result = r.data.imported || { commanders: 0, cards: 0, unknown: [] };
  }
</script>

{#if $importOpen}
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
      aria-label="Import a deck"
    >
      <header>
        <h2>⬇ Import a deck</h2>
        <button class="x" title="Close" on:click={close}>×</button>
      </header>

      {#if result}
        <div class="done">
          <p class="ok">Imported into a new build.</p>
          <ul>
            <li>{result.cards} card{result.cards === 1 ? "" : "s"}</li>
            <li>
              {result.commanders} commander{result.commanders === 1 ? "" : "s"}
              {#if result.commanders === 0}
                <span class="dim"
                  >— no commander was marked; promote one with ★ in the deck
                  list</span
                >
              {/if}
            </li>
            {#if result.unknown?.length}
              <li class="warn">
                {result.unknown.length} name{result.unknown.length === 1
                  ? ""
                  : "s"} not found in card data (shown as “unknown”):
                <span class="dim"
                  >{result.unknown.slice(0, 8).join(", ")}{result.unknown
                    .length > 8
                    ? "…"
                    : ""}</span
                >
              </li>
            {/if}
          </ul>
          <button class="btn btn-ember" on:click={close}>Done</button>
        </div>
      {:else}
        <p class="hint">
          Paste a list (Moxfield / Arena / MTGO / CSV / plain) or upload a file.
          A marked commander is detected automatically; an unmarked list lands
          as a pile you promote from. Imports into a <b>new</b> build — your current
          deck is untouched.
        </p>
        <textarea
          bind:value={text}
          rows="10"
          placeholder="Paste your list here — e.g.  1 Sol Ring · 1 Arcane Signet · 1 Cultivate …"
        ></textarea>
        <div class="row">
          <label class="fld">
            <span>Format</span>
            <select bind:value={format}>
              {#each FORMATS as [v, l] (v)}<option value={v}>{l}</option>{/each}
            </select>
          </label>
          <label class="fld grow">
            <span>Name (optional)</span>
            <input bind:value={name} placeholder="Imported deck" />
          </label>
        </div>
        <div class="row between">
          <label class="file">
            <input
              type="file"
              accept=".txt,.csv,.dec,text/plain,text/csv"
              bind:this={fileEl}
              on:change={onFile}
            />
            <span>📄 Upload a file…</span>
          </label>
          <div class="actions">
            {#if error}<span class="err">{error}</span>{/if}
            <button class="btn ghost" on:click={close}>Cancel</button>
            <button
              class="btn btn-ember"
              disabled={busy || !text.trim()}
              on:click={submit}>{busy ? "Importing…" : "⚒ Import"}</button
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
    width: min(40rem, 100%);
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
    align-items: flex-end;
  }
  .row.between {
    justify-content: space-between;
    align-items: center;
  }
  .fld {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }
  .fld.grow {
    flex: 1;
  }
  .fld select,
  .fld input {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    font-size: 0.88rem;
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
  .done ul {
    margin: 0.6rem 0 1rem;
    padding-left: 1.1rem;
    font-size: 0.86rem;
    color: var(--parchment);
  }
  .done .warn {
    color: var(--warn);
  }
  .dim {
    color: var(--muted);
    font-style: italic;
  }
</style>
