<script>
  // One official MTG mana/color symbol, served as Scryfall's hosted SVG (same
  // no-local-hosting policy as card art). `sym` is a symbol code: a color
  // (W/U/B/R/G/C), generic ("2", "X"), or other ({T}, etc.) — pass it WITHOUT braces.
  export let sym;
  export let size = "1.1rem";
  $: code = String(sym).replace(/[{}]/g, "").toUpperCase();
</script>

<img
  class="ms"
  src="https://svgs.scryfall.io/card-symbols/{code}.svg"
  alt={code}
  title={code}
  style="width:{size}; height:{size}"
  loading="lazy"
/>

<style>
  .ms {
    display: inline-block;
    vertical-align: middle;
    border-radius: 50%;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
    flex: 0 0 auto;
  }
</style>
