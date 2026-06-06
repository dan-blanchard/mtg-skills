<script>
  import { hovered } from "../lib/store.js";

  const W = 244;

  $: card = $hovered?.card;
  // Double-faced cards expose every face's normal image — show both sides.
  $: faces = card?.images?.faces;
  $: dfc = Array.isArray(faces) && faces.length >= 2;
  $: H = dfc ? 340 * faces.length + 8 * (faces.length - 1) : 340;

  function place(x, y, h) {
    let px = x + 22;
    let py = y + 22;
    if (typeof window !== "undefined") {
      if (px + W > window.innerWidth) px = x - W - 22;
      if (py + h > window.innerHeight) py = window.innerHeight - h - 8;
      if (py < 8) py = 8;
    }
    return { px, py };
  }

  $: pos = $hovered ? place($hovered.x, $hovered.y, H) : { px: 0, py: 0 };
</script>

{#if card}
  <div class="preview" style="left:{pos.px}px; top:{pos.py}px">
    {#if dfc}
      <div class="faces">
        {#each faces as fc (fc.normal)}
          <img src={fc.normal} alt={fc.name} />
        {/each}
      </div>
    {:else if card.images?.normal}
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
  .faces {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .faces img {
    border-radius: 10px;
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
