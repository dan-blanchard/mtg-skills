<script>
  import { deck, applySnapshot } from "../lib/store.js";
  import { api } from "../lib/api.js";
  import { hoverPreview } from "../lib/hover.js";
  import ManaCost from "./ManaCost.svelte";

  async function remove(name, zone) {
    const r = await api.remove(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }

  async function addOne(name, zone) {
    const r = await api.add(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }

  // Singleton: only basics and "any number of cards named X" cards (Relentless Rats,
  // Shadowborn Apostle, Dragon's Approach…) may have more than one copy.
  function canHaveMultiple(c) {
    if (/\bBasic Land\b/.test(c.type_line || "")) return true;
    return /a deck can have any number of cards named/i.test(
      c.oracle_text || "",
    );
  }

  // Cheapest USD listing for a card, or null (no-listing ≠ free — never shown as $0).
  function priceOf(c) {
    const p = c.prices?.usd ?? c.prices?.usd_foil ?? c.prices?.usd_etched;
    const n = p == null ? null : Number(p);
    return n == null || Number.isNaN(n) ? null : n;
  }
  const money = (n) => `$${n.toFixed(2)}`;

  function groupTotal(cards) {
    return cards.reduce(
      (sum, c) => sum + (priceOf(c) ?? 0) * (c.quantity || 1),
      0,
    );
  }

  $: groups = [
    { key: "commanders", label: "Command Zone", cards: $deck.commanders },
    { key: "cards", label: "Deck", cards: $deck.cards },
  ];
  $: empty = !$deck.commanders.length && !$deck.cards.length;
</script>

<div class="panel deck">
  <h3 class="panel-title">The Deck</h3>

  {#if empty}
    <div class="cold">
      <span class="glyph">🜂</span>
      <p>The forge is cold. Search for a commander and add it to begin.</p>
    </div>
  {:else}
    {#each groups as g (g.key)}
      {#if g.cards.length}
        <div class="group">
          <div class="group-head">
            {g.label} <span>· {g.cards.length}</span>
            <span class="subtotal">{money(groupTotal(g.cards))}</span>
          </div>
          {#each g.cards as c (c.name)}
            <div class="row" use:hoverPreview={c}>
              <div class="thumb">
                {#if c.images?.small}
                  <img src={c.images.small} alt={c.name} loading="lazy" />
                {:else}
                  <span class="noart">{c.name[0]}</span>
                {/if}
              </div>
              <div class="info">
                <div class="name">{c.name}</div>
                <div class="type">
                  {c.type_line || (c.unknown ? "unknown card" : "")}
                </div>
              </div>
              <div class="right">
                {#if c.quantity > 1}<span class="qty">×{c.quantity}</span>{/if}
                {#if priceOf(c) != null}
                  <span class="price">{money(priceOf(c))}</span>
                {:else}
                  <span
                    class="price none"
                    title="No listing — likely scarce/expensive, not free"
                    >—</span
                  >
                {/if}
                <span class="cost"
                  ><ManaCost cost={c.mana_cost} size="0.82rem" /></span
                >
                {#if g.key === "cards" && canHaveMultiple(c)}
                  <button
                    class="rm add"
                    title="Add another"
                    on:click={() => addOne(c.name, g.key)}>+</button
                  >
                {/if}
                <button
                  class="rm"
                  title="Remove one"
                  on:click={() => remove(c.name, g.key)}>−</button
                >
              </div>
            </div>
          {/each}
        </div>
      {/if}
    {/each}
  {/if}
</div>

<style>
  .deck {
    padding: 1rem;
    height: 100%;
    overflow-y: auto;
  }
  .cold {
    text-align: center;
    color: var(--muted);
    padding: 3rem 1rem;
  }
  .cold .glyph {
    font-size: 2.6rem;
    display: block;
    margin-bottom: 0.7rem;
    opacity: 0.6;
  }
  .group-head {
    font-family: var(--display);
    font-size: 0.74rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--parchment-dim);
    margin: 0.8rem 0 0.4rem;
  }
  .group-head span {
    color: var(--muted);
  }
  .group-head .subtotal {
    float: right;
    color: var(--brass);
    letter-spacing: 0.04em;
  }
  .price {
    font-size: 0.78rem;
    color: var(--pass);
    font-variant-numeric: tabular-nums;
  }
  .price.none {
    color: var(--muted);
    font-style: italic;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.32rem 0.3rem;
    border-radius: var(--radius);
    animation: rise 0.25s ease both;
  }
  .row:hover {
    background: rgba(255, 220, 160, 0.04);
  }
  .thumb {
    width: 34px;
    height: 34px;
    border-radius: 4px;
    overflow: hidden;
    flex-shrink: 0;
    background: #0d0a08;
    border: 1px solid var(--hairline-soft);
    display: grid;
    place-items: center;
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 18%;
  }
  .noart {
    font-family: var(--display);
    color: var(--brass);
  }
  .info {
    flex: 1;
    min-width: 0;
  }
  .name {
    font-size: 0.92rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .type {
    font-size: 0.72rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .qty {
    font-size: 0.78rem;
    color: var(--parchment-dim);
  }
  .cost {
    display: flex;
    justify-content: flex-end;
    min-width: 2.2rem;
  }
  .rm {
    background: transparent;
    border: 1px solid var(--hairline-soft);
    color: var(--parchment-dim);
    border-radius: 4px;
    width: 1.5rem;
    height: 1.5rem;
    line-height: 1;
    font-size: 1.1rem;
  }
  .rm:hover {
    border-color: var(--fail);
    color: var(--fail);
  }
  .rm.add:hover {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
</style>
