import js from "@eslint/js";
import svelte from "eslint-plugin-svelte";
import globals from "globals";

export default [
  js.configs.recommended,
  ...svelte.configs["flat/recommended"],
  {
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "module",
      globals: { ...globals.browser },
    },
  },
  {
    rules: {
      // Runes-mode rule: it recommends SvelteSet/SvelteMap over plain Set/Map.
      // This frontend is legacy mode (export let / $:), where a plain Set plus
      // reassignment (`colors = new Set(colors)`) is the correct reactivity
      // idiom — the flagged sites already do that. Not applicable here.
      "svelte/prefer-svelte-reactivity": "off",
      // Diverges from the Svelte compiler's a11y analysis: the plugin doesn't
      // flag the modal scrim's click-without-keyboard, so it reports the
      // (genuinely required) `svelte-ignore` as unused. svelte-check is the
      // source of truth for a11y suppressions here.
      "svelte/no-unused-svelte-ignore": "off",
    },
  },
  {
    ignores: ["dist/", "node_modules/"],
  },
];
