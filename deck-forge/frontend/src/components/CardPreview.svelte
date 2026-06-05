<script>
  import { hovered } from "../lib/store.js";

  const W = 244;
  const H = 340;

  function place(x, y) {
    let px = x + 22;
    let py = y + 22;
    if (typeof window !== "undefined") {
      if (px + W > window.innerWidth) px = x - W - 22;
      if (py + H > window.innerHeight) py = window.innerHeight - H - 8;
      if (py < 8) py = 8;
    }
    return { px, py };
  }

  $: pos = $hovered ? place($hovered.x, $hovered.y) : { px: 0, py: 0 };
  $: card = $hovered?.card;
</script>

{#if card}
  <div class="preview" style="left:{pos.px}px; top:{pos.py}px">
    {#if card.images?.normal}
      <img src={card.images.normal} alt={card.name} />
    {:else}
      <div class="fallback">
        <div class="nm">{card.name}</div>
        <div class="tl">{card.type_line}{card.mana_cost ? " · " + card.mana_cost : ""}</div>
        <div class="ot">{card.oracle_text || "—"}</div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .preview {
    position: fixed;
    z-index: 100;
    width: 244px;
    pointer-events: none;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 14px 44px rgba(0, 0, 0, 0.75);
    border: 1px solid var(--hairline);
    animation: fade 0.1s ease both;
  }
  .preview img {
    width: 100%;
    display: block;
  }
  .fallback {
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    padding: 0.9rem;
  }
  .nm {
    font-family: var(--display);
    color: var(--brass-bright);
    font-size: 1rem;
  }
  .tl {
    font-size: 0.78rem;
    color: var(--parchment-dim);
    margin: 0.25rem 0 0.5rem;
  }
  .ot {
    font-size: 0.82rem;
    line-height: 1.45;
    color: var(--parchment);
    white-space: pre-wrap;
  }
  @keyframes fade {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }
</style>
