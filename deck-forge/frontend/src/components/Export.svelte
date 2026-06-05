<script>
  import { api } from "../lib/api.js";

  let fmt = "moxfield";
  let text = "";
  let busy = false;

  const FORMATS = [
    ["moxfield", "Moxfield"],
    ["arena", "Arena"],
    ["json", "Deck JSON"],
  ];

  const HANDOFFS = [
    ["proxy-print --kind cards deck.json", "Print proxies"],
    ["lgs-search deck.json", "Source the cards"],
    ["deck-strat deck.json", "Strategy guide"],
    ["playtest-goldfish deck.json", "Goldfish it"],
  ];

  async function run(f) {
    fmt = f;
    busy = true;
    const r = await api.exportDeck(f);
    busy = false;
    if (!r.ok) {
      text = r.data.error || "export failed";
      return;
    }
    text = f === "json" ? JSON.stringify(r.data.deck, null, 2) : r.data.text;
  }

  function copy() {
    navigator.clipboard?.writeText(text);
  }
</script>

<div class="panel export">
  <h3 class="panel-title">Export & Handoff</h3>

  <div class="fmts">
    {#each FORMATS as [id, label]}
      <button class="btn" class:active={fmt === id} on:click={() => run(id)}>{label}</button>
    {/each}
    {#if text}<button class="btn copy" on:click={copy}>Copy</button>{/if}
  </div>

  <div class="body">
    {#if busy}
      <div class="notice">Exporting…</div>
    {:else if text}
      <textarea readonly>{text}</textarea>
    {:else}
      <div class="notice idle">
        Export the canonical deck JSON (the lingua franca of the whole repo), or
        Moxfield / Arena import text.
      </div>
    {/if}

    <div class="handoffs">
      <div class="hh">Hand off the exported JSON to:</div>
      {#each HANDOFFS as [cmd, label]}
        <div class="handoff"><span class="hl">{label}</span><code>{cmd}</code></div>
      {/each}
    </div>
  </div>
</div>

<style>
  .export {
    padding: 1rem;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .fmts {
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
  }
  .btn.active {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .copy {
    margin-left: auto;
  }
  .body {
    margin-top: 0.9rem;
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  textarea {
    flex: 1;
    min-height: 180px;
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
    padding: 0.6rem;
    resize: vertical;
  }
  .notice {
    color: var(--parchment-dim);
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid var(--hairline-soft);
    border-left: 3px solid var(--brass);
    border-radius: var(--radius);
    padding: 0.7rem 0.85rem;
    font-size: 0.85rem;
  }
  .notice.idle {
    border-left-color: var(--hairline);
    font-style: italic;
    color: var(--muted);
  }
  .handoffs {
    margin-top: 0.9rem;
    border-top: 1px solid var(--hairline-soft);
    padding-top: 0.7rem;
  }
  .hh {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin-bottom: 0.4rem;
  }
  .handoff {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
    font-size: 0.8rem;
  }
  .hl {
    color: var(--brass);
    min-width: 8rem;
  }
  code {
    color: var(--parchment-dim);
    font-size: 0.76rem;
  }
</style>
