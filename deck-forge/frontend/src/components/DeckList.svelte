<script>
  import {
    deck,
    applySnapshot,
    importOpen,
    collection,
    activeTab,
    isDigital,
  } from "../lib/store.js";
  import { api } from "../lib/api.js";
  import { hoverPreview } from "../lib/hover.js";
  import { displayName } from "../lib/cards.js";
  import { wildcardLabel, wildcardTotals, WC_TIERS } from "../lib/mana.js";
  import ManaCost from "./ManaCost.svelte";

  async function remove(name, zone) {
    const r = await api.remove(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }

  async function addOne(name, zone) {
    const r = await api.add(name, zone, 1);
    if (r.ok) applySnapshot(r.data);
  }

  // Promote a card already in the deck from the mainboard into the command zone
  // (#1, ADR-0017) — the inverse of adding-as-commander. An imported list with no
  // marked commander lands as a pile; ★ here moves a legendary into the command zone.
  // Move = remove one from cards, then add one to commanders (no single move endpoint).
  async function promote(name) {
    const r1 = await api.remove(name, "cards", 1);
    if (!r1.ok) return;
    const r2 = await api.add(name, "commanders", 1);
    applySnapshot((r2.ok ? r2 : r1).data);
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

  // Non-zero wildcard tiers for a group's subtotal in a digital build, e.g. [["rare",
  // "R","rare"], …] paired with counts → "2R 5U". Empty when nothing needs crafting.
  function wcSubtotal(cards) {
    const totals = wildcardTotals(cards);
    return WC_TIERS.filter(([k]) => totals[k]).map(([k, label, cls]) => ({
      label,
      cls,
      n: totals[k],
    }));
  }

  $: groups = [
    { key: "commanders", label: "Command Zone", cards: $deck.commanders },
    { key: "cards", label: "Deck", cards: $deck.cards },
  ];
  $: empty = !$deck.commanders.length && !$deck.cards.length;
  // The owned readout shows only when a Collection is loaded for the ACTIVE slot
  // (strictly single-slot, ADR-0018) — otherwise there's nothing to compare against.
  $: ownedReadout =
    $collection && ($collection.slots?.[$collection.active_slot] || 0) > 0
      ? $collection
      : null;
</script>

<div class="panel deck">
  <h3 class="panel-title">The Deck</h3>
  {#if ownedReadout}
    <div
      class="owned-readout"
      title="Owned in your {ownedReadout.active_slot} collection"
    >
      <span class="own-tick">✓</span>
      {ownedReadout.owned} of {ownedReadout.deck_total} owned
      <span class="own-slot">· {ownedReadout.active_slot}</span>
    </div>
  {/if}

  {#if empty}
    <div class="cold">
      <span class="glyph">🜂</span>
      <p>The forge is cold. Search for a commander and add it to begin,</p>
      <p class="or">or bring a list you already have:</p>
      <div class="cold-actions">
        <button class="import-btn" on:click={() => importOpen.set(true)}
          >⬇ Import a deck</button
        >
        <button
          class="import-btn ghost"
          on:click={() => activeTab.set("commanders")}
          >✦ Discover from your collection</button
        >
      </div>
    </div>
  {:else}
    {#each groups as g (g.key)}
      {#if g.cards.length}
        <div class="group">
          <div class="group-head">
            {g.label} <span>· {g.cards.length}</span>
            {#if $isDigital}
              <span
                class="subtotal wc-sub"
                title="Wildcards to craft this group"
              >
                {#each wcSubtotal(g.cards) as t (t.cls)}
                  <span class="wc-{t.cls}">{t.n}{t.label}</span>
                {:else}
                  <span class="wc-owned">✓</span>
                {/each}
              </span>
            {:else}
              <span class="subtotal">{money(groupTotal(g.cards))}</span>
            {/if}
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
                <div class="name">
                  {displayName(c.name)}{#if c.owned}<span
                      class="owned-tick"
                      title="Owned ×{c.owned_qty}">✓</span
                    >{/if}
                </div>
                <div class="type">
                  {c.type_line || (c.unknown ? "unknown card" : "")}
                </div>
              </div>
              <div class="right">
                {#if c.quantity > 1}<span class="qty">×{c.quantity}</span>{/if}
                {#if $isDigital}
                  {@const wc = wildcardLabel(c)}
                  <span class="wcprice wc-{wc.cls}" title={wc.title}
                    >{wc.text}</span
                  >
                {:else if priceOf(c) != null}
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
                {#if g.key === "cards" && c.can_be_commander}
                  <button
                    class="rm star"
                    title="Promote to commander"
                    on:click={() => promote(c.name)}>★</button
                  >
                {/if}
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
  /* Wildcard cost (digital) — layout only; the .wc-* global classes supply the tint. */
  .wcprice {
    font-size: 0.78rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .wc-sub {
    display: inline-flex;
    gap: 0.32rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
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
  .rm.star {
    font-size: 0.95rem;
  }
  .rm.star:hover {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .cold .or {
    margin-top: 0.4rem;
    font-size: 0.85rem;
  }
  .import-btn {
    margin-top: 0.8rem;
    padding: 0.5rem 1.2rem;
    background: rgba(200, 150, 75, 0.08);
    border: 1px solid var(--brass);
    border-radius: 999px;
    color: var(--brass-bright);
    font-family: var(--display);
    font-size: 0.82rem;
    letter-spacing: 0.04em;
    cursor: pointer;
  }
  .import-btn:hover {
    background: rgba(255, 106, 61, 0.12);
    border-color: var(--brass-bright);
  }
  .cold-actions {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
  }
  .import-btn.ghost {
    background: transparent;
    border-color: var(--hairline);
    color: var(--parchment-dim);
  }
  .import-btn.ghost:hover {
    color: var(--brass-bright);
    border-color: var(--brass);
  }
  .owned-readout {
    font-size: 0.74rem;
    color: var(--pass);
    margin: 0.15rem 0 0.3rem;
    letter-spacing: 0.02em;
  }
  .owned-readout .own-tick {
    margin-right: 0.2rem;
  }
  .owned-readout .own-slot {
    color: var(--muted);
    text-transform: capitalize;
  }
  .owned-tick {
    color: var(--pass);
    font-size: 0.72rem;
    margin-left: 0.35rem;
    vertical-align: middle;
  }
</style>
