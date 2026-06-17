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
  import { facetOk, nameOk } from "../lib/filter.js";
  import ManaCost from "./ManaCost.svelte";
  import FilterWidget from "./FilterWidget.svelte";

  // Live filtering of the current deck (A4) — the SAME widget Find uses, applied
  // client-side over the loaded deck cards.
  let fName = "";
  let fType = "";
  let fCmc = "";
  let fPrice = "";
  let fRarity = "";
  let fOwned = false;

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

  // Printing picker (C): one open dropdown at a time, keyed by zone:name. Opening fetches
  // the card's printings; choosing one (or "Default") pins it via the backend, which
  // returns a fresh snapshot (image/price/export then follow the choice).
  let pickerKey = null;
  let pickerPrints = [];
  let pickerLoading = false;
  const keyOf = (c, zone) => `${zone}:${c.name}`;
  async function togglePicker(c, zone) {
    const k = keyOf(c, zone);
    if (pickerKey === k) {
      pickerKey = null;
      return;
    }
    pickerKey = k;
    pickerPrints = [];
    pickerLoading = true;
    const r = await api.printings(c.name);
    pickerLoading = false;
    if (pickerKey === k) pickerPrints = r.ok ? r.data.printings : [];
  }
  async function choosePrinting(c, zone, id) {
    const r = await api.setPrinting(c.name, id, zone);
    if (r.ok) applySnapshot(r.data);
    pickerKey = null;
  }
  const printPrice = (p) => (p.prices?.usd != null ? `$${p.prices.usd}` : "—");

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
  // Whether any filter is set (so we only show "N of M" and the clear hint when filtering).
  $: filtering = !!(fName || fType || fCmc || fPrice || fRarity || fOwned);
  // Filter each group client-side with the shared predicate. The facet values are read
  // into the inline object HERE so Svelte tracks them as dependencies of this reactive.
  $: filteredGroups = groups.map((g) => ({
    ...g,
    total: g.cards.length,
    cards: g.cards.filter(
      (c) =>
        nameOk(c, fName) &&
        facetOk(
          c,
          {
            type: fType,
            cmc: fCmc,
            price: fPrice,
            rarity: fRarity,
            owned: fOwned,
          },
          $isDigital,
        ),
    ),
  }));
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
    <div class="deck-filter">
      <FilterWidget
        showName
        bind:name={fName}
        bind:facetType={fType}
        bind:facetCmc={fCmc}
        bind:facetPrice={fPrice}
        bind:facetRarity={fRarity}
        bind:facetOwned={fOwned}
        digital={$isDigital}
      />
    </div>
    {#each filteredGroups as g (g.key)}
      {#if g.cards.length}
        <div class="group">
          <div class="group-head">
            {g.label}
            <span
              >· {filtering ? `${g.cards.length} of ${g.total}` : g.total}</span
            >
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
                {#if !c.unknown}
                  <button
                    class="rm setbtn"
                    class:pinned={c.printing_id}
                    title={c.set
                      ? `Printing: ${c.set.toUpperCase()} #${c.collector_number} — change`
                      : "Choose printing"}
                    on:click={() => togglePicker(c, g.key)}
                    >{c.set ? c.set.toUpperCase() : "◆"}</button
                  >
                {/if}
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
            {#if pickerKey === keyOf(c, g.key)}
              <div class="printings">
                {#if pickerLoading}
                  <div class="pload">Loading printings…</div>
                {:else}
                  <button
                    class="prow"
                    class:on={!c.printing_id}
                    on:click={() => choosePrinting(c, g.key, null)}
                    use:hoverPreview={{
                      name: c.name,
                      images: c.images,
                      layout: c.layout,
                    }}
                  >
                    <span class="pset">Default (cheapest)</span>
                  </button>
                  {#each pickerPrints as p (p.id)}
                    <button
                      class="prow"
                      class:on={c.printing_id === p.id}
                      on:click={() => choosePrinting(c, g.key, p.id)}
                      use:hoverPreview={{
                        name: c.name,
                        images: p.images,
                        layout: c.layout,
                      }}
                    >
                      <span class="pset"
                        >{p.set?.toUpperCase()} · #{p.collector_number}</span
                      >
                      <span class="pmeta">{p.set_name}</span>
                      <span class="pprice">{printPrice(p)}</span>
                    </button>
                  {/each}
                  {#if !pickerPrints.length}
                    <div class="pload">No printings found.</div>
                  {/if}
                {/if}
              </div>
            {/if}
          {/each}
        </div>
      {/if}
    {/each}
    {#if filtering && filteredGroups.every((g) => !g.cards.length)}
      <div class="nomatch">No cards in the deck match this filter.</div>
    {/if}
  {/if}
</div>

<style>
  .deck-filter {
    margin: 0.25rem 0 0.7rem;
  }
  .nomatch {
    color: var(--muted);
    font-style: italic;
    font-size: 0.85rem;
    padding: 0.6rem 0.2rem;
  }
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
  /* printing picker (C): the set-code chip + its dropdown of printings */
  .rm.setbtn {
    width: auto;
    min-width: 1.5rem;
    padding: 0 0.3rem;
    font-size: 0.6rem;
    font-family: var(--display);
    letter-spacing: 0.04em;
  }
  .rm.setbtn.pinned {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .rm.setbtn:hover {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  .printings {
    margin: 0.15rem 0 0.5rem 2.6rem;
    max-height: 14rem;
    overflow-y: auto;
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    background: rgba(0, 0, 0, 0.25);
  }
  .pload {
    padding: 0.5rem 0.6rem;
    font-size: 0.78rem;
    color: var(--muted);
    font-style: italic;
  }
  .prow {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    border-bottom: 1px solid var(--hairline-soft);
    color: var(--parchment-dim);
    padding: 0.32rem 0.6rem;
    cursor: pointer;
    font-size: 0.78rem;
  }
  .prow:hover {
    background: rgba(255, 220, 160, 0.06);
    color: var(--parchment);
  }
  .prow.on {
    color: var(--brass-bright);
  }
  .prow .pset {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .prow .pmeta {
    flex: 1;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .prow .pprice {
    color: var(--pass);
    font-variant-numeric: tabular-nums;
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
