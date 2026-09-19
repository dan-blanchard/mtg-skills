<script>
  // The one theme-preset picker: a filterable multiselect over the hub's presets
  // (name + description, so a blurb like "sacrifice" surfaces edict / exploit by
  // what they do, not only by name). Find and Commanders both mount it, so the two
  // panels offer the same presets the same way. `selected` is a Set of names, bound.
  export let presets = [];
  export let selected = new Set();
  export let placeholder = "Choose theme presets";

  let open = false;
  let filter = ""; // narrows the list inside the dropdown (client-side)

  function toggle(n) {
    selected.has(n) ? selected.delete(n) : selected.add(n);
    selected = new Set(selected);
  }
  // Matches name OR description, so "sacrifice" surfaces edict/exploit presets by
  // their blurb too.
  $: filtered = filter.trim()
    ? presets.filter((p) => {
        const q = filter.toLowerCase();
        return (
          p.name.toLowerCase().includes(q) ||
          (p.description || "").toLowerCase().includes(q)
        );
      })
    : presets;
</script>

{#if selected.size}
  <div class="selchips">
    {#each [...selected] as n (n)}
      <button
        type="button"
        class="selchip"
        title="Remove {n}"
        on:click={() => toggle(n)}>{n} <em>✕</em></button
      >
    {/each}
    <button
      type="button"
      class="clearpresets"
      on:click={() => (selected = new Set())}>clear all</button
    >
  </div>
{/if}
<div class="presets">
  <button class="dropbtn" type="button" on:click={() => (open = !open)}>
    {selected.size ? `${selected.size} selected — add more` : placeholder} ▾
  </button>
  {#if open}
    <div class="dropdown">
      <input
        class="presearch"
        type="search"
        placeholder="Filter {presets.length} presets…"
        bind:value={filter}
      />
      <div class="optlist">
        {#each filtered as p (p.name)}
          <label class="opt" class:sel={selected.has(p.name)}>
            <input
              type="checkbox"
              checked={selected.has(p.name)}
              on:change={() => toggle(p.name)}
            />
            <span class="opt-text">
              <span class="opt-name">{p.name}</span>
              <span class="opt-desc">{p.description}</span>
            </span>
          </label>
        {/each}
        {#if !filtered.length}
          <div class="opt-empty">
            No preset matches “{filter}”.
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .selchips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    text-transform: none;
    letter-spacing: 0;
  }
  .selchip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.74rem;
    color: var(--brass-bright);
    background: rgba(200, 150, 75, 0.16);
    border: 1px solid var(--brass);
    border-radius: 999px;
    padding: 0.12rem 0.55rem;
    cursor: pointer;
  }
  .selchip em {
    font-style: normal;
    color: var(--parchment-dim);
  }
  .selchip:hover {
    background: rgba(212, 69, 47, 0.25);
    border-color: rgba(212, 69, 47, 0.6);
    color: var(--parchment);
  }
  .clearpresets {
    font-size: 0.72rem;
    color: var(--muted);
    background: none;
    border: none;
    text-decoration: underline;
    cursor: pointer;
    padding: 0.12rem 0.3rem;
  }
  .clearpresets:hover {
    color: var(--parchment-dim);
  }
  .presets {
    position: relative;
  }
  .dropbtn {
    width: 100%;
    text-align: left;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    font-size: 0.82rem;
    text-transform: none;
    letter-spacing: 0;
  }
  .dropdown {
    position: absolute;
    z-index: 30;
    top: 110%;
    left: 0;
    right: 0;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--hairline);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 0.35rem;
  }
  /* search pinned above the scrolling list so every preset is findable, not scrolled */
  .presearch {
    width: 100%;
    box-sizing: border-box;
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius);
    color: var(--parchment);
    padding: 0.4rem 0.5rem;
    font-size: 0.82rem;
    margin-bottom: 0.35rem;
  }
  .presearch:focus {
    outline: none;
    border-color: var(--brass);
  }
  .optlist {
    max-height: 260px;
    overflow-y: auto;
  }
  .opt {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    gap: 0.45rem;
    padding: 0.3rem 0.35rem;
    border-radius: var(--radius);
    text-transform: none;
    letter-spacing: 0;
    color: var(--parchment);
  }
  .opt:hover {
    background: rgba(255, 220, 160, 0.06);
  }
  .opt.sel {
    background: rgba(200, 150, 75, 0.12);
  }
  .opt input {
    width: auto;
    margin-top: 0.18rem;
  }
  .opt-text {
    display: flex;
    flex-direction: column;
    gap: 0.05rem;
    min-width: 0;
  }
  .opt-name {
    font-size: 0.82rem;
    color: var(--parchment);
  }
  .opt-desc {
    font-size: 0.7rem;
    line-height: 1.25;
    color: var(--muted);
  }
  .opt-empty {
    padding: 0.5rem 0.4rem;
    font-size: 0.78rem;
    color: var(--muted);
    text-transform: none;
    letter-spacing: 0;
  }
</style>
