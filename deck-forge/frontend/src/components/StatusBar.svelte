<script>
  // The forge's hot base: a sticky footer of glanceable read-outs (Moxfield-style),
  // freeing the right rail for the Forge-Friend alone. Three zones:
  //   summary  — read-only deck numbers (cards · curve · counts · colors · price · bracket)
  //   health   — land pill (CLICK → Mana Gate modal), budgets + warnings (HOVER → popover)
  //   link     — the two genuinely-distinct status dots: ● Hub (SSE) and ● Session (agent)
  import {
    stats,
    mana,
    budgets,
    warnings,
    bracket,
    deck,
    collection,
    wildcards,
    connected,
    agentAttached,
    manaModalOpen,
  } from "../lib/store.js";
  import {
    landState,
    priceOf,
    FORMAT_TARGET,
    SYMBOL_ORDER,
    COLOR_LABEL,
    WC_TIERS,
  } from "../lib/mana.js";
  import Mana from "./Mana.svelte";
  import Budgets from "./Budgets.svelte";
  import Warnings from "./Warnings.svelte";

  $: ls = landState($mana);
  // Effective deck-size target (60 or 100 for paper Historic Brawl), else format default.
  $: target = $deck.deck_size ?? FORMAT_TARGET[$deck.format] ?? 100;
  // Arena wildcard tiers (mythic→common), shown for digital builds in place of USD.
  $: wcTotal = $wildcards
    ? Object.values($wildcards).reduce((a, b) => a + b, 0)
    : 0;
  $: colorPips = SYMBOL_ORDER.filter((c) => ($stats?.color_sources || {})[c]);
  $: deckTotal = [...$deck.commanders, ...$deck.cards].reduce(
    (sum, c) => sum + (priceOf(c) ?? 0) * (c.quantity || 1),
    0,
  );
  // How much of the estimate is cards you DON'T already own (the spend to acquire the
  // deck). Only meaningful when a Collection is loaded for the active slot; basics are
  // excluded (assumed owned, matching the owned readout). Owned-ness is the derived flag.
  $: collectionLoaded =
    $collection && ($collection.slots?.[$collection.active_slot] || 0) > 0;
  const isBasic = (c) => /\bBasic Land\b/.test(c.type_line || "");
  $: unownedTotal = [...$deck.commanders, ...$deck.cards].reduce(
    (sum, c) =>
      c.owned || isBasic(c) ? sum : sum + (priceOf(c) ?? 0) * (c.quantity || 1),
    0,
  );
  // Slot budgets met / tracked, for the compact chip (full bars live in the popover).
  $: budgetRoles = $budgets ? Object.values($budgets) : [];
  $: budgetsMet = budgetRoles.filter((b) => b && b.remaining === 0).length;
  $: warnCount = $warnings.length;
  $: bracketFactors = $bracket
    ? [
        $bracket.game_changers?.length
          ? `${$bracket.game_changers.length} game changers`
          : null,
        $bracket.mass_land_denial?.length ? "mass land denial" : null,
        $bracket.fast_curve ? "fast curve" : null,
      ].filter(Boolean)
    : [];
</script>

<footer class="bar">
  <!-- ── summary ─────────────────────────────────────────────── -->
  <div class="zone summary">
    <div class="stat">
      <b>{$stats?.total_cards ?? 0}</b><span class="o">/{target}</span><em
        >cards</em
      >
    </div>
    <div class="stat"><b>{$stats?.avg_cmc ?? 0}</b><em>avg</em></div>
    <div class="stat">
      <b>{$stats?.creature_count ?? 0}</b><em>creatures</em>
    </div>
    <div class="stat"><b>{$stats?.ramp_count ?? 0}</b><em>ramp</em></div>
    {#if colorPips.length}
      <div class="stat colors">
        {#each colorPips as c (c)}
          <span class="src" title={COLOR_LABEL[c]}
            ><Mana sym={c} size="0.95rem" /><i>{$stats.color_sources[c]}</i
            ></span
          >
        {/each}
      </div>
    {/if}
    {#if $deck.medium === "digital"}
      <div
        class="stat wc"
        title="Arena wildcards needed for cards you don't own (basics are free)"
      >
        {#if $wildcards && wcTotal}
          {#each WC_TIERS as [k, label, cls] (k)}
            {#if $wildcards[k]}
              <span class="wc-{cls}">{$wildcards[k]}{label}</span>
            {/if}
          {/each}
        {:else if $wildcards}
          <b class="owned-all">✓</b>
        {:else}
          <b>—</b>
        {/if}
        <em>wildcards</em>
      </div>
    {:else}
      <div class="stat">
        <b>${deckTotal.toFixed(0)}</b><em>est.</em>
        {#if collectionLoaded}
          <span
            class="unowned"
            title="Estimated cost of cards not in your {$collection.active_slot} collection (basics excluded)"
            >(${unownedTotal.toFixed(0)} unowned)</span
          >
        {/if}
      </div>
    {/if}
    {#if $bracket}
      <div
        class="stat bracket"
        title={bracketFactors.join(" · ") || "Mechanical estimate"}
      >
        <b>B{$bracket.bracket}</b><em>{$bracket.name}</em>
      </div>
    {/if}
  </div>

  <!-- ── health (disclosure) ─────────────────────────────────── -->
  <div class="zone health">
    {#if ls}
      <button
        class="pill status-{ls.status}"
        on:click={() => manaModalOpen.set(true)}
        title="Land health — click for the Mana Gate"
      >
        <span class="dot bg-{ls.status}"></span>
        <b>{ls.count}</b> lands · {ls.status}
      </button>
    {/if}

    {#if $budgets}
      <div class="hc">
        <span class="chip">⛓ {budgetsMet}/{budgetRoles.length} slots</span>
        <div class="pop"><Budgets /></div>
      </div>
    {/if}

    <div class="hc">
      <span
        class="chip"
        class:bad={warnCount}
        title="Format legality — hover for any violations"
      >
        {#if warnCount}⚠ {warnCount}{:else}✓ Legal{/if}
      </span>
      {#if warnCount}<div class="pop"><Warnings /></div>{/if}
    </div>
  </div>

  <!-- ── link ────────────────────────────────────────────────── -->
  <div class="zone link">
    <span
      class="conn"
      class:on={$connected}
      title={$connected ? "Browser ↔ hub: live" : "Browser ↔ hub: offline"}
    >
      <span class="d"></span>Hub
    </span>
    <span
      class="conn"
      class:on={$agentAttached}
      title={$agentAttached
        ? "Claude session attached"
        : "No Claude session — run /deck-forge"}
    >
      <span class="d"></span>Session
    </span>
  </div>
</footer>

<style>
  .bar {
    position: relative;
    z-index: 6;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 1.1rem;
    height: 40px;
    padding: 0 1.2rem;
    background: linear-gradient(180deg, #211c18, #17120e);
    border-top: 1px solid var(--hairline);
    box-shadow:
      0 -8px 24px rgba(0, 0, 0, 0.45),
      0 -1px 0 rgba(255, 220, 160, 0.04) inset;
    font-size: 0.78rem;
  }
  /* ember licks up from the base — echoes the body's bottom glow */
  .bar::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: radial-gradient(
      60% 200% at 50% 100%,
      rgba(255, 106, 61, 0.07),
      transparent 70%
    );
  }
  .zone {
    display: flex;
    align-items: center;
    gap: 1rem;
    position: relative;
  }
  .zone.health {
    gap: 0.5rem;
    padding-left: 1.1rem;
    border-left: 1px solid var(--hairline-soft);
  }
  .zone.link {
    margin-left: auto;
    gap: 0.9rem;
    padding-left: 1.1rem;
    border-left: 1px solid var(--hairline-soft);
  }
  .summary {
    overflow: hidden;
    flex-wrap: wrap;
    max-height: 40px;
  }
  /* numbers in Spectral, labels in muted Cinzel small-caps */
  .stat {
    display: inline-flex;
    align-items: baseline;
    gap: 0.3rem;
    white-space: nowrap;
  }
  .stat b {
    color: var(--parchment);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .stat .o {
    color: var(--muted);
    margin-left: -0.22rem;
  }
  .stat em {
    font-style: normal;
    font-family: var(--display);
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .colors {
    gap: 0.5rem;
  }
  .src {
    display: inline-flex;
    align-items: center;
    gap: 0.18rem;
  }
  .src i {
    font-style: normal;
    color: var(--parchment-dim);
    font-variant-numeric: tabular-nums;
  }
  .unowned {
    color: var(--warn);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    margin-left: -0.05rem;
  }
  /* Arena wildcard tiers — tinted by rarity via the global .wc-* classes (app.css). */
  .wc {
    gap: 0.4rem;
  }
  .wc span {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    font-size: 0.82rem;
  }
  .wc .owned-all {
    color: var(--pass);
  }
  .bracket b {
    color: var(--brass-bright);
    font-family: var(--display);
  }
  .bracket em {
    color: var(--parchment-dim);
    text-transform: none;
    letter-spacing: 0.02em;
    font-size: 0.72rem;
  }
  /* health pill — clickable */
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.2rem 0.65rem;
    font-size: 0.76rem;
    color: var(--parchment-dim);
    transition:
      border-color 0.14s,
      box-shadow 0.14s;
  }
  .pill b {
    color: var(--parchment);
    font-variant-numeric: tabular-nums;
  }
  .pill:hover {
    border-color: var(--brass);
    box-shadow: 0 0 12px rgba(232, 181, 99, 0.16);
  }
  .pill .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
  }
  /* hover-disclosure chips */
  .hc {
    position: relative;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid var(--hairline-soft);
    border-radius: 999px;
    padding: 0.2rem 0.65rem;
    font-size: 0.76rem;
    color: var(--parchment-dim);
    cursor: default;
  }
  .chip.bad {
    color: var(--fail);
    border-color: rgba(212, 69, 47, 0.4);
  }
  .hc:hover .chip {
    border-color: var(--brass);
    color: var(--brass-bright);
  }
  /* hidden until the chip (or the popover itself, a descendant) is hovered */
  .pop {
    position: absolute;
    bottom: calc(100% + 0.5rem);
    left: 50%;
    transform: translateX(-50%) translateY(4px);
    width: 248px;
    z-index: 20;
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    transition:
      opacity 0.14s ease,
      transform 0.14s ease,
      visibility 0.14s;
  }
  .hc:hover .pop {
    opacity: 1;
    visibility: visible;
    pointer-events: auto;
    transform: translateX(-50%) translateY(0);
  }
  /* the reused widgets already render a .panel; tighten for the popover */
  .pop :global(.widget) {
    padding: 0.8rem 0.9rem;
    box-shadow: var(--shadow);
  }
  .pop::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 6px solid transparent;
    border-top-color: var(--hairline);
  }
  /* connection dots */
  .conn {
    display: inline-flex;
    align-items: center;
    gap: 0.32rem;
    font-family: var(--display);
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .conn .d {
    width: 0.52rem;
    height: 0.52rem;
    border-radius: 50%;
    background: #4a3c28;
    transition: all 0.3s;
  }
  .conn.on {
    color: var(--parchment-dim);
  }
  .conn.on .d {
    background: var(--pass);
    box-shadow: 0 0 6px rgba(74, 158, 99, 0.7);
  }
  @media (max-width: 1100px) {
    .bar {
      height: auto;
      flex-wrap: wrap;
      gap: 0.7rem;
      padding: 0.6rem 1.2rem;
    }
    .zone.link {
      margin-left: 0;
    }
  }
</style>
