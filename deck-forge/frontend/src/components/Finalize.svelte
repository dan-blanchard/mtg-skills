<script>
  import { api } from "../lib/api.js";

  let result = null;
  let busy = false;

  async function finalize(override = false) {
    busy = true;
    const r = await api.finalize(override);
    busy = false;
    result = r.ok ? r.data : { error: r.data.error || "finalize failed" };
  }
</script>

<div class="panel widget finalize">
  <h3 class="panel-title">Finalize</h3>
  <button class="btn btn-ember go" on:click={() => finalize(false)} disabled={busy}>
    {busy ? "Checking…" : "✓ Finalize deck"}
  </button>

  {#if result && !result.error}
    {#if result.gated}
      <div class="gate">
        <p class="reason">
          Land gate: <b>{result.land_count}</b> lands, floor <b>{result.recommended_land_count}</b> — <span class="status-FAIL">FAIL</span>.
        </p>
        <p class="evidence" class:ok={result.evidence.defensible}>
          {#if result.evidence.defensible}
            Evidence supports running low: avg CMC {result.evidence.avg_cmc},
            {result.evidence.cheap_card_advantage} cheap card-advantage pieces.
          {:else}
            Nothing here justifies a low land count (avg CMC {result.evidence.avg_cmc},
            only {result.evidence.cheap_card_advantage} cheap card-advantage pieces).
          {/if}
        </p>
        <button class="btn override" on:click={() => finalize(true)}>
          Override & finalize anyway
        </button>
      </div>
    {:else}
      <p class="done">
        ✦ Deck finalized{result.overridden ? " (land gate overridden)" : ""}.
        {result.legality_status === "FAIL" ? "Resolve the warnings above before play." : "Legality clean."}
      </p>
    {/if}
  {:else if result?.error}
    <p class="reason">{result.error}</p>
  {/if}
</div>

<style>
  .go {
    width: 100%;
    font-family: var(--display);
    letter-spacing: 0.08em;
  }
  .gate {
    margin-top: 0.7rem;
    border-left: 3px solid var(--fail);
    padding-left: 0.6rem;
  }
  .reason {
    font-size: 0.85rem;
    margin: 0 0 0.4rem;
  }
  .evidence {
    font-size: 0.8rem;
    color: var(--warn);
    margin: 0 0 0.5rem;
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
    margin-top: 0.7rem;
    font-size: 0.86rem;
    color: var(--pass);
  }
</style>
