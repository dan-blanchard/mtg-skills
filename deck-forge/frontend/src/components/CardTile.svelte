<script>
  // A candidate card, in one of two densities:
  //   • grid  (default) — art-forward tile (used by Find's grid view + Combos)
  //   • dense (dense=true) — compact row with a first line of oracle text (Find's
  //     list view)
  // CRITICAL: the two layouts share ONE DOM and switch via the `dense` class, so the
  // <img> elements (art + every mana symbol — all remote Scryfall SVGs) PERSIST across
  // a density toggle. Swapping between two separate components instead would destroy
  // and recreate ~5 images per card, which refetches them all when the browser cache
  // is off — the toggle would stutter and look like a network call. Keep all <img>s
  // outside the {#if dense} blocks; only cheap text (synergy/oracle lines) is
  // conditionally rendered.
  import { SYMBOL_ORDER, wildcardLabel } from "../lib/mana.js";
  import { displayName } from "../lib/cards.js";
  import { askForge } from "../lib/agent.js";
  import { hoverPreview } from "../lib/hover.js";
  import { isDigital } from "../lib/store.js";
  import Mana from "./Mana.svelte";
  import ManaCost from "./ManaCost.svelte";
  export let card;
  export let onadd;
  export let score = null;
  export let dense = false;

  $: price = card.prices?.usd;
  // Digital builds cost wildcards by rarity, not dollars (see lib/mana.wildcardLabel).
  $: wc = $isDigital ? wildcardLabel(card) : null;
  // Iterate SYMBOL_ORDER (not the card's identity order) so symbols read C, then WUBRG.
  $: colors = SYMBOL_ORDER.filter((c) =>
    (card.color_identity || []).includes(c),
  );
  $: noListing = price == null;
  // Only legendary creatures / other commander-eligible cards (for the deck's current
  // format) can be set as commander — the backend computes this per format.
  $: canCommand = card.can_be_commander === true;
  $: hasSynergy = score && score.synergy_fit > 0;
  $: served = score?.served ?? [];
  // First line of oracle text (dense only) — newlines flattened to a bullet so a
  // multi-paragraph card reads as one line; CSS ellipsis shows "as much as fits".
  $: oracle = (card.oracle_text || "").replace(/\s*\n+\s*/g, " • ").trim();
</script>

<div class="tile" class:dense use:hoverPreview={card}>
  <div class="art">
    {#if card.images?.art_crop}
      <img src={card.images.art_crop} alt={card.name} loading="lazy" />
    {:else if card.images?.small}
      <img src={card.images.small} alt={card.name} loading="lazy" />
    {:else}
      <div class="noart">{displayName(card.name)}</div>
    {/if}
  </div>
  <!-- color identity over the art (grid). Anchored to the .tile (stable width), NOT
       .art: Safari doesn't stretch an aspect-ratio flex item to full width, which
       pushed symbols off .art's right. Hidden in dense (shown inline by the name). -->
  <div class="ci ci-over">
    {#each colors as c (c)}<Mana sym={c} size="1.05rem" />{/each}
  </div>

  <div class="body">
    <div class="main">
      <div class="l1">
        <span class="name">{displayName(card.name)}</span>
        <span class="ci ci-in">
          {#each colors as c (c)}<Mana sym={c} size="0.92rem" />{/each}
        </span>
      </div>
      <div class="type">{card.type_line}</div>
      {#if dense}
        <!-- dense meta line: synergy spark + served lanes (Find's reason for the
             ranking — the deck list has no equivalent) with the type as a tail -->
        <div class="metaline" title={served.join(", ")}>
          {#if hasSynergy}
            <span class="spark">✦ {score.synergy_fit}</span>
            {#each served.slice(0, 3) as s, i (i)}<span class="served">{s}</span
              >{/each}
          {/if}
          <span class="typetail">{card.type_line}</span>
        </div>
        {#if oracle}<div class="oracle">{oracle}</div>{/if}
      {:else if hasSynergy}
        <div class="synergy" title={served.join(", ")}>
          <span class="spark">✦ {score.synergy_fit}</span>
          {#each served.slice(0, 2) as s, i (i)}<span class="served">{s}</span
            >{/each}
        </div>
      {/if}
    </div>

    <div class="side">
      <div class="foot">
        <ManaCost cost={card.mana_cost} size="0.95rem" />
        {#if wc}
          <span class="wcprice wc-{wc.cls}" title={wc.title}>{wc.text}</span>
        {:else}
          <span class="price" class:nolisting={noListing}>
            {noListing ? "no listing" : "$" + price}
          </span>
        {/if}
      </div>
      <div class="actions">
        <button
          class="btn btn-ember add"
          on:click={() => onadd(card.name, "cards")}>+ Add</button
        >
        <button
          class="btn star"
          title={canCommand
            ? "Set as commander"
            : "Not commander-eligible in this format"}
          disabled={!canCommand}
          on:click={() => onadd(card.name, "commanders")}>★</button
        >
        <button
          class="btn star"
          title="Ask the forge-friend to explain"
          on:click={() => askForge("explain", { card: card.name })}>?</button
        >
      </div>
    </div>
  </div>
</div>

<style>
  /* ---- grid (default) — the art-forward tile ------------------------------- */
  .tile {
    position: relative;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition:
      border-color 0.15s,
      transform 0.15s;
    animation: rise 0.25s ease both;
  }
  .tile:hover {
    border-color: var(--brass);
    transform: translateY(-2px);
  }
  .art {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #0d0a08;
  }
  .art img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .noart {
    width: 100%;
    height: 100%;
    display: grid;
    place-items: center;
    text-align: center;
    padding: 0.5rem;
    font-family: var(--display);
    color: var(--brass);
    font-size: 0.85rem;
  }
  .ci {
    display: flex;
    gap: 0.2rem;
  }
  .ci-over {
    position: absolute;
    top: 0.35rem;
    right: 0.4rem;
    left: 0.4rem;
    flex-wrap: wrap;
    justify-content: flex-end;
    pointer-events: none;
  }
  .ci-in {
    display: none;
  }
  .body {
    padding: 0.55rem 0.6rem 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }
  /* In grid mode .main/.side dissolve, so their children flow in .body's column
     exactly like the flat original tile; `order` restores the original sequence
     (name, type, mana/price, synergy, actions). */
  .main,
  .side {
    display: contents;
  }
  .l1 {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
    order: 0;
  }
  .name {
    font-size: 0.9rem;
    font-weight: 500;
    line-height: 1.15;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .type {
    font-size: 0.72rem;
    color: var(--muted);
    flex: 1;
    order: 1;
  }
  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
    min-height: 1.1rem;
    font-size: 0.76rem;
    color: var(--parchment-dim);
    order: 2;
  }
  .price {
    margin-left: auto;
  }
  .price.nolisting {
    color: var(--warn);
    font-style: italic;
  }
  /* Wildcard cost (digital builds) — layout only; the .wc-* global class tints it. */
  .wcprice {
    margin-left: auto;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .synergy {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.25rem;
    margin-top: 0.1rem;
    order: 3;
  }
  .spark {
    font-family: var(--display);
    font-size: 0.72rem;
    color: var(--brass-bright);
    flex-shrink: 0;
  }
  .served {
    font-size: 0.62rem;
    color: var(--parchment-dim);
    background: rgba(200, 150, 75, 0.12);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.05rem 0.4rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .metaline,
  .oracle {
    display: none;
  }
  .actions {
    display: flex;
    gap: 0.35rem;
    margin-top: 0.3rem;
    order: 4;
  }
  .add {
    flex: 1;
  }
  .star {
    width: 2rem;
    padding: 0.42rem 0;
  }
  .star:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  /* ---- dense — the compact row -------------------------------------------- */
  .tile.dense {
    flex-direction: row;
    align-items: stretch;
    gap: 0.65rem;
    padding: 0.45rem 0.55rem;
  }
  .tile.dense:hover {
    transform: translateX(2px);
  }
  /* a small landscape art window — keeps art presence at ~1/5 the tile height */
  .dense .art {
    width: 76px;
    height: 52px;
    flex-shrink: 0;
    aspect-ratio: auto;
    border-radius: 3px;
    border: 1px solid var(--hairline-soft);
    overflow: hidden;
  }
  .dense .noart {
    font-size: 1.1rem;
  }
  .dense .ci-over {
    display: none;
  }
  .dense .ci-in {
    display: inline-flex;
    gap: 0.12rem;
    flex-shrink: 0;
  }
  .dense .body {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    padding: 0;
    /* Without this, .body's automatic min-width (auto) lets the nowrap oracle in
       .main blow it past the tile, pushing .side (mana/price + buttons) off the
       clipped right edge. min-width:0 lets the row shrink to the tile so .main
       ellipsizes and .side stays visible. */
    min-width: 0;
  }
  .dense .main {
    display: flex;
    flex-direction: column;
    justify-content: center;
    flex: 1;
    min-width: 0;
    gap: 0.12rem;
  }
  .dense .side {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: center;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .dense .name {
    font-size: 0.92rem;
  }
  .dense .type {
    display: none; /* shown as a tail on the dense meta line instead */
  }
  .dense .metaline {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    min-width: 0;
    overflow: hidden;
  }
  .dense .metaline .served {
    flex-shrink: 0;
    max-width: 11rem;
  }
  .typetail {
    font-size: 0.66rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .dense .oracle {
    display: block;
    font-size: 0.74rem;
    line-height: 1.25;
    color: var(--parchment-dim);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dense .foot {
    justify-content: flex-end;
    min-height: 0;
    gap: 0.45rem;
    font-size: 0.78rem;
  }
  .dense .actions {
    margin-top: 0;
    gap: 0.3rem;
  }
  .dense .add {
    flex: 0 0 auto;
    padding: 0.3rem 0.7rem;
    font-size: 0.8rem;
    white-space: nowrap;
  }
  .dense .star {
    width: 1.7rem;
    height: 1.7rem;
    padding: 0;
  }
</style>
