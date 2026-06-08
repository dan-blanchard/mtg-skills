<script>
  // An inline card reference inside a forge-friend reply: a tiny art thumb + the
  // card name. Hovering shows the same full-card preview used everywhere else
  // (via the shared `hovered` store); clicking adds the card to the deck. While
  // the card object is still resolving (or unresolvable), it degrades to a plain
  // name pill — never a broken image.
  import { hoverPreview } from "../lib/hover.js";
  import { applySnapshot } from "../lib/store.js";
  import { api } from "../lib/api.js";

  export let name;
  export let card = null; // hydrated card object (images/oracle/…) once resolved
  // Hover-only mode (clickable=false): identify + preview a card that is already in the
  // deck, without the click-to-add action that only makes sense for new candidates.
  export let clickable = true;

  $: art = card?.images?.art_crop || card?.images?.small || null;

  let adding = false;
  async function add() {
    if (adding) return;
    adding = true;
    const r = await api.add(name, "cards", 1);
    if (r.ok) applySnapshot(r.data);
    adding = false;
  }
</script>

{#if card && clickable}
  <button
    class="cardchip"
    use:hoverPreview={card}
    on:click={add}
    title={`Add ${name}`}
  >
    {#if art}<img class="thumb" src={art} alt="" loading="lazy" />{/if}
    <span class="nm">{name}</span>
  </button>
{:else if card}
  <span class="cardchip static" use:hoverPreview={card}>
    {#if art}<img class="thumb" src={art} alt="" loading="lazy" />{/if}
    <span class="nm">{name}</span>
  </span>
{:else}
  <span class="cardchip pending">{name}</span>
{/if}

<style>
  .cardchip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    vertical-align: baseline;
    padding: 0.05rem 0.4rem 0.05rem 0.15rem;
    margin: 0 0.05rem;
    background: linear-gradient(180deg, #3a2f22, #2a221a);
    border: 1px solid var(--hairline);
    color: var(--parchment);
    border-radius: 999px;
    font-size: 0.82rem;
    line-height: 1.3;
    cursor: pointer;
  }
  .cardchip:hover {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .cardchip.static {
    cursor: help;
  }
  .cardchip.pending {
    cursor: default;
    padding-left: 0.4rem;
    opacity: 0.85;
  }
  .thumb {
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    object-fit: cover;
    flex: 0 0 auto;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  }
  .nm {
    white-space: nowrap;
  }
</style>
