import { hovered } from "./store.js";

// Svelte action: show the cursor-following card preview while hovering `node`.
// Usage: <div use:hoverPreview={card}>…</div>
export function hoverPreview(node, card) {
  let current = card;
  const move = (e) => hovered.set({ card: current, x: e.clientX, y: e.clientY });
  const leave = () => hovered.set(null);
  node.addEventListener("mousemove", move);
  node.addEventListener("mouseleave", leave);
  return {
    update(next) {
      current = next;
    },
    destroy() {
      node.removeEventListener("mousemove", move);
      node.removeEventListener("mouseleave", leave);
      hovered.set(null);
    },
  };
}
