<script>
  // Render a run of rules text with its {…} symbols (mana, {T}, {Q}, {E}, hybrids,
  // loyalty…) drawn as Scryfall symbol icons instead of literal "{5}{U}" braces.
  // Tokenize into text spans + symbol tokens; Mana resolves each token to its SVG.
  import Mana from "./Mana.svelte";
  export let text = "";
  export let size = "0.85rem";

  $: tokens = tokenize(text);
  function tokenize(s) {
    const out = [];
    const re = /\{([^}]+)\}/g;
    let last = 0;
    let m;
    while ((m = re.exec(s)) !== null) {
      if (m.index > last) out.push({ sym: false, v: s.slice(last, m.index) });
      out.push({ sym: true, v: m[1] });
      last = m.index + m[0].length;
    }
    if (last < s.length) out.push({ sym: false, v: s.slice(last) });
    return out;
  }
</script>

{#each tokens as tok, i (i)}{#if tok.sym}<Mana
      sym={tok.v}
      {size}
    />{:else}{tok.v}{/if}{/each}
