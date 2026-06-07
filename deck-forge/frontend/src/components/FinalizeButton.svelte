<script>
  // Finalize moved into the header (#9). It has an ACTION (Override), so clicking opens
  // a popover that holds the gate evidence + the override, or the "finalized" note —
  // not a fire-and-forget button. Logic mirrors the old rail Finalize widget.
  import { api } from "../lib/api.js";

  let open = false;
  let result = null;
  let busy = false;

  async function run(override = false) {
    busy = true;
    const r = await api.finalize(override);
    busy = false;
    result = r.ok ? r.data : { error: r.data.error || "finalize failed" };
    open = true;
  }
  function close() {
    open = false;
  }
</script>

<svelte:window on:keydown={(e) => e.key === "Escape" && close()} />

<div class="fin" class:open>
  <button class="btn btn-ember go" on:click={() => run(false)} disabled={busy}>
    {busy ? "Checking…" : "✓ Finalize"}
  </button>

  {#if open && result}
    <div class="pop panel">
      <button class="x" on:click={close} aria-label="Close">×</button>
      {#if result.error}
        <p class="reason">{result.error}</p>
      {:else if result.gated}
        <p class="reason">
          Land gate: <b>{result.land_count}</b> lands, floor
          <b>{result.recommended_land_count}</b>
          —
          <span class="status-FAIL">FAIL</span>.
        </p>
        <p class="evidence" class:ok={result.evidence.defensible}>
          {#if result.evidence.defensible}
            Evidence supports running low: avg CMC {result.evidence.avg_cmc},
            {result.evidence.cheap_card_advantage} cheap card-advantage pieces.
          {:else}
            Nothing here justifies a low land count (avg CMC {result.evidence
              .avg_cmc}, only {result.evidence.cheap_card_advantage} cheap card-advantage
            pieces).
          {/if}
        </p>
        <button class="btn override" on:click={() => run(true)} disabled={busy}>
          Override &amp; finalize anyway
        </button>
      {:else}
        <p class="done">
          ✦ Deck finalized{result.overridden ? " (land gate overridden)" : ""}.
          {result.legality_status === "FAIL"
            ? "Resolve the ⚠ warnings before play."
            : "Legality clean."}
        </p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .fin {
    position: relative;
  }
  .go {
    font-family: var(--display);
    letter-spacing: 0.06em;
  }
  .pop {
    position: absolute;
    top: calc(100% + 0.6rem);
    right: 0;
    z-index: 30;
    width: 320px;
    padding: 0.9rem 1rem 1rem;
    animation: rise 0.18s ease both;
  }
  .pop::before {
    content: "";
    position: absolute;
    bottom: 100%;
    right: 1rem;
    border: 6px solid transparent;
    border-bottom-color: var(--hairline);
  }
  .x {
    position: absolute;
    top: 0.4rem;
    right: 0.5rem;
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 1.2rem;
    line-height: 1;
  }
  .x:hover {
    color: var(--fail);
  }
  .reason {
    font-size: 0.85rem;
    margin: 0 1rem 0.4rem 0;
  }
  .evidence {
    font-size: 0.8rem;
    color: var(--warn);
    margin: 0 0 0.6rem;
    line-height: 1.45;
  }
  .evidence.ok {
    color: var(--pass);
  }
  .override {
    width: 100%;
    border-color: var(--fail);
    color: var(--fail);
  }
  .override:hover {
    background: rgba(212, 69, 47, 0.12);
  }
  .done {
    margin: 0.2rem 0 0;
    font-size: 0.86rem;
    color: var(--pass);
    line-height: 1.5;
  }
</style>
