/**
 * Display formatting helpers. Locale-explicit ("en-US") so server- and
 * client-rendered output cannot diverge. All inputs are untrusted strings
 * from API responses; unknown values render as "—", never fabricated.
 */

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
});

/** "Jun 12, 2025, 3:04 PM" or "—" for missing/invalid input. */
export function formatDateTime(iso?: string | null): string {
  return formatWith(dateTimeFormatter, iso);
}

/** "Jun 12, 2025" or "—" for missing/invalid input. */
export function formatDate(iso?: string | null): string {
  return formatWith(dateFormatter, iso);
}

function formatWith(formatter: Intl.DateTimeFormat, iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return formatter.format(date);
}

/**
 * Short human form of a content hash or commit SHA for display; the full
 * value stays available to assistive tech via `title`.
 */
export function formatShortHash(hash?: string | null, length = 12): string {
  if (!hash) return "—";
  return hash.length <= length ? hash : `${hash.slice(0, length)}…`;
}
