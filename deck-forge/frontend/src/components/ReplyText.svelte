<script>
  // Render a forge-friend reply as rich content: prose stays prose, {W}-style
  // tokens become official mana-symbol SVGs, and [[Card Name]] references become
  // inline card chips (tiny art + hover preview + click-to-add). The reasoning
  // is preserved verbatim — only card names and mana symbols get upgraded.
  import { tokenizeReply } from "../lib/mana.js";
  import { api } from "../lib/api.js";
  import Mana from "./Mana.svelte";
  import CardChip from "./CardChip.svelte";

  export let text = "";
  export let cards = [];

  $: tokens = tokenizeReply(text || "");

  let resolved = {}; // name -> card object | null (null = resolved-but-missing)
  const inflight = new Set();
  async function resolve(name) {
    if (!name || name in resolved || inflight.has(name)) return;
    inflight.add(name);
    const r = await api.card(name);
    resolved = { ...resolved, [name]: r.ok && r.data ? r.data.card : null };
    inflight.delete(name);
  }

  $: refNames = tokens.filter((t) => t.t === "card").map((t) => t.v);
  $: allNames = Array.from(new Set([...refNames, ...(cards || [])]));
  $: allNames.forEach(resolve);

  // Endorsed cards the agent didn't weave into the prose: surface them as an add
  // row so the affordance is never lost (also a graceful fallback for replies
  // written before the [[…]] convention).
  $: extraCards = (cards || []).filter((n) => !refNames.includes(n));
</script>

<div class="reply-rich">
  <!-- prettier-ignore -->
  <p class="prose">{#each tokens as tok, i (i)}{#if tok.t === "text"}{tok.v}{:else if tok.t === "mana"}<Mana sym={tok.v} size="0.95rem" />{:else}<CardChip name={tok.v} card={resolved[tok.v] ?? null} />{/if}{/each}</p>
  {#if extraCards.length}
    <div class="extra">
      {#each extraCards as n (n)}<CardChip
          name={n}
          card={resolved[n] ?? null}
        />{/each}
    </div>
  {/if}
</div>

<style>
  .prose {
    margin: 0;
    font-size: 0.86rem;
    line-height: 1.7;
    white-space: pre-wrap;
  }
  .extra {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin-top: 0.55rem;
  }
</style>
