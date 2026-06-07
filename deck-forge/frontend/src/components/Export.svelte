<script>
  import { api } from "../lib/api.js";
  import { agentAttached } from "../lib/store.js";

  let fmt = "moxfield";
  let text = "";
  let busy = false;

  const FORMATS = [
    ["moxfield", "Moxfield"],
    ["arena", "Arena"],
    ["json", "Deck JSON"],
  ];

  // Session-tier handoffs (ADR-0016): need reasoning or a headed browser, so they route
  // to the attached Claude session over the agent bridge (kind "handoff"), which invokes
  // the named skill on the current deck. [tool id, button label].
  const SESSION_HANDOFFS = [
    ["deck-strat", "Strategy guide"],
    ["lgs-search", "Source the cards"],
  ];

  let gfBusy = false;
  let gfReport = "";
  let gfErr = "";
  let proxyBusy = false;
  let proxyErr = "";
  let sessBusy = {};
  let sessMsg = {};

  // Route a handoff to the attached session; it runs the skill and posts a one-liner
  // back. agentAsk handles the long-poll + offline/slow detection.
  async function sessionHandoff(tool, label) {
    sessBusy = { ...sessBusy, [tool]: true };
    sessMsg = { ...sessMsg, [tool]: "" };
    const res = await api.agentAsk("handoff", { tool });
    sessBusy = { ...sessBusy, [tool]: false };
    let msg;
    if (res.offline) msg = "No session attached — run /deck-forge.";
    else if (res.slow) msg = "Session is working — check your terminal.";
    else if (res.error) msg = res.error;
    else msg = res.result?.text || `${label} started in your session.`;
    sessMsg = { ...sessMsg, [tool]: msg };
  }

  // Proxies come back as a binary PDF, so bypass the JSON api helper and stream the blob
  // straight into a browser download.
  async function proxies() {
    proxyBusy = true;
    proxyErr = "";
    try {
      const resp = await fetch("/api/handoff/proxies", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{}",
      });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        proxyErr = d.error || `proxies failed (${resp.status})`;
        return;
      }
      const url = URL.createObjectURL(await resp.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "proxies.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      proxyBusy = false;
    }
  }

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

  async function goldfish() {
    gfBusy = true;
    gfErr = "";
    gfReport = "";
    const r = await api.handoffGoldfish();
    gfBusy = false;
    if (!r.ok) {
      gfErr = r.data.error || "goldfish failed";
      return;
    }
    gfReport = r.data.markdown;
  }

  function copy() {
    navigator.clipboard?.writeText(text);
  }
</script>

<div class="panel export">
  <h3 class="panel-title">Export & Handoff</h3>

  <div class="fmts">
    {#each FORMATS as [id, label] (id)}
      <button class="btn" class:active={fmt === id} on:click={() => run(id)}
        >{label}</button
      >
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
      <div class="hh">Run here</div>
      <div class="runhere">
        <button class="btn btn-ember gf" on:click={goldfish} disabled={gfBusy}>
          {gfBusy ? "Goldfishing…" : "✦ Goldfish it"}
        </button>
        <button class="btn gf" on:click={proxies} disabled={proxyBusy}>
          {proxyBusy ? "Rendering…" : "⎙ Print proxies"}
        </button>
      </div>
      {#if gfErr}<div class="notice">{gfErr}</div>{/if}
      {#if proxyErr}<div class="notice">{proxyErr}</div>{/if}
      {#if gfReport}
        <div class="gfhead">
          <span>Goldfish report</span>
          <button class="clear" on:click={() => (gfReport = "")}>× clear</button
          >
        </div>
        <pre class="gfreport">{gfReport}</pre>
      {/if}

      <div class="hh">Run in your session</div>
      {#if !$agentAttached}
        <div class="notice idle">
          Attach a Claude session (run <code>/deck-forge</code>) to use these.
        </div>
      {/if}
      {#each SESSION_HANDOFFS as [tool, label] (tool)}
        <div class="srow">
          <button
            class="btn shbtn"
            disabled={!$agentAttached || sessBusy[tool]}
            on:click={() => sessionHandoff(tool, label)}
          >
            {sessBusy[tool] ? "Sending…" : label}
          </button>
          {#if sessMsg[tool]}<span class="smsg">{sessMsg[tool]}</span>{/if}
        </div>
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
  .hh:not(:first-child) {
    margin-top: 0.9rem;
    padding-top: 0.7rem;
    border-top: 1px solid var(--hairline-soft);
  }
  .runhere {
    display: flex;
    gap: 0.4rem;
  }
  .gf {
    flex: 1;
    font-family: var(--display);
    letter-spacing: 0.06em;
    white-space: nowrap;
  }
  .gfhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 0.7rem 0 0.3rem;
    font-size: 0.74rem;
    color: var(--brass);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .clear {
    background: transparent;
    border: 1px solid var(--hairline-soft);
    color: var(--parchment-dim);
    border-radius: 999px;
    padding: 0.1rem 0.55rem;
    font-size: 0.72rem;
  }
  .clear:hover {
    border-color: var(--fail);
    color: var(--fail);
  }
  .gfreport {
    max-height: 280px;
    overflow: auto;
    margin: 0;
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment-dim);
    font-family: ui-monospace, monospace;
    font-size: 0.74rem;
    line-height: 1.5;
    padding: 0.7rem 0.8rem;
    white-space: pre-wrap;
  }
  .srow {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.4rem;
  }
  .shbtn {
    flex-shrink: 0;
    min-width: 9rem;
    text-align: left;
  }
  .shbtn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .smsg {
    font-size: 0.78rem;
    color: var(--parchment-dim);
    font-style: italic;
  }
  code {
    color: var(--brass);
    font-size: 0.78rem;
  }
</style>
