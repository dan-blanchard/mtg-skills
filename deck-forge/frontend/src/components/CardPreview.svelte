<script>
  import { hovered } from "../lib/store.js";

  // Single-face popup dimensions, enlarged 50% over the old 244×340 so the rules
  // text in the card image is legible. (FH/FW == the MTG card aspect ratio.)
  const FW = 366;
  const FH = 510;
  const GAP = 10;

  $: card = $hovered?.card;
  // Double-faced cards expose every face's normal image — show them side-by-side.
  $: faces = card?.images?.faces;
  $: dfc = Array.isArray(faces) && faces.length >= 2;
  // Split / aftermath cards are printed with their halves turned 90°; rotate the
  // single image so the mini-cards read horizontally without tilting your head.
  $: split = !dfc && (card?.layout === "split" || card?.layout === "aftermath");

  // The popup's box. DFC: a row of faces. Split: the card turned on its side
  // (landscape, so W/H swap). Otherwise: one upright card.
  $: paneW = dfc ? FW * faces.length + GAP * (faces.length - 1) : split ? FH : FW;
  $: paneH = split ? FW : FH;

  function place(x, y, w, h) {
    let px = x + 22;
    let py = y + 22;
    if (typeof window !== "undefined") {
      if (px + w > window.innerWidth) px = x - w - 22;
      if (px < 8) px = 8;
      if (py + h > window.innerHeight) py = window.innerHeight - h - 8;
      if (py < 8) py = 8;
    }
    return { px, py };
  }

  $: pos = $hovered ? place($hovered.x, $hovered.y, paneW, paneH) : { px: 0, py: 0 };
</script>

{#if card}
  <div class="preview" style="left:{pos.px}px; top:{pos.py}px; width:{paneW}px; height:{paneH}px">
    {#if dfc}
      <div class="faces">
        {#each faces as fc (fc.normal)}
          <img src={fc.normal} alt={fc.name} style="width:{FW}px" />
        {/each}
      </div>
    {:else if split && card.images?.normal}
      <img class="rot" src={card.images.normal} alt={card.name} style="width:{FW}px" />
    {:else if card.images?.normal}
      <img class="single" src={card.images.normal} alt={card.name} />
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
    pointer-events: none;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 14px 44px rgba(0, 0, 0, 0.75);
    border: 1px solid var(--hairline);
    animation: fade 0.1s ease both;
  }
  .single {
    width: 100%;
    display: block;
  }
  /* Rotate the split card 90°; its natural FW×FH portrait fills the FH×FW box. */
  .rot {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(90deg);
    transform-origin: center;
    border-radius: 12px;
  }
  .faces {
    display: flex;
    flex-direction: row;
    gap: 10px;
  }
  .faces img {
    display: block;
    border-radius: 10px;
  }
  .fallback {
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    padding: 0.9rem;
  }
  .nm {
    font-family: var(--display);
    color: var(--brass-bright);
    font-size: 1.1rem;
  }
  .tl {
    font-size: 0.85rem;
    color: var(--parchment-dim);
    margin: 0.25rem 0 0.5rem;
  }
  .ot {
    font-size: 0.9rem;
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
