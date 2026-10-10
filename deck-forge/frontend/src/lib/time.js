// Time display helpers shared across the SPA.

/** How long ago something happened, from its elapsed milliseconds: "just now"
 * under a minute, then "N min ago", "N h ago", "N days ago" ("" when unknown). */
export function timeAgo(ms) {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "";
  const min = Math.floor(Math.max(0, ms) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "1 day ago" : `${d} days ago`;
}
