import { hovered } from "./store.js";

// Svelte action: show the card preview ANCHORED to `node` (the hovered tile/row),
// not the cursor — so the preview sits beside the card and never covers its own
// cost / score / buttons. We report the node's live bounding rect; CardPreview
// places the popup to the card's right (flipping left if the viewport is tight).
// Usage: <div use:hoverPreview={card}>…</div>
export function hoverPreview(node, card) {
  let current = card;
  // Recompute the rect on enter and on move (cheap) so it stays correct if the
  // list scrolls while hovering; the popup position is stable because it's pinned
  // to the card, not the pointer.
  const show = () => hovered.set({ card: current, rect: node.getBoundingClientRect() });
  const leave = () => hovered.set(null);
  node.addEventListener("mouseenter", show);
  node.addEventListener("mousemove", show);
  node.addEventListener("mouseleave", leave);
  return {
    update(next) {
      current = next;
    },
    destroy() {
      node.removeEventListener("mouseenter", show);
      node.removeEventListener("mousemove", show);
      node.removeEventListener("mouseleave", leave);
      hovered.set(null);
    },
  };
}
