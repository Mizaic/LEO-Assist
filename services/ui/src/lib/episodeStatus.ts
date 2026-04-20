/**
 * Canonical EpisodeOfCare status vocabulary (DI-LEO-AI-529).
 *
 * MIRROR of libs/episodes/status.py -- keep in sync. The contract test
 * tests/contracts/test_episode_status_vocabulary.py parses this file and
 * fails the build if any value drifts from the Python source of truth.
 *
 * Every UI component that compares an episode status MUST import the
 * helpers / constants from this file, never inline a string literal like
 * "active" or "closed_benign".
 */

// -- Engine output ---------------------------------------------------------

export const STATUS_ACTIVE = "active";
export const STATUS_REVIEW = "review";
export const STATUS_COMPLETED = "completed";
export const STATUS_CLOSED_BENIGN = "closed_benign";

// -- Legacy-rule output ----------------------------------------------------

export const STATUS_MERGED = "merged";
export const STATUS_CLOSED_RELATED = "closed_related";
export const STATUS_CLOSED_PHANTOM = "closed_phantom";
export const STATUS_STALE_NO_DIAGNOSIS = "stale_no_diagnosis";
export const STATUS_STALE_POST_SPECIALIST = "stale_post_specialist";
export const STATUS_CLOSED = "closed";
export const STATUS_EXCLUDED = "excluded";

// -- Legacy-rule open ------------------------------------------------------

export const STATUS_IN_PROGRESS = "in_progress";


// -- Producer contract -----------------------------------------------------

export const ENGINE_OUTPUT_STATUSES: ReadonlySet<string> = new Set([
  STATUS_ACTIVE,
  STATUS_REVIEW,
  STATUS_COMPLETED,
  STATUS_CLOSED_BENIGN,
]);

// -- Consumer contracts ----------------------------------------------------

export const OPEN_STATUSES: ReadonlySet<string> = new Set([
  STATUS_ACTIVE,
  STATUS_REVIEW,
  STATUS_IN_PROGRESS,
]);

export const CLOSED_STATUSES: ReadonlySet<string> = new Set([
  STATUS_COMPLETED,
  STATUS_CLOSED,
  STATUS_CLOSED_BENIGN,
  STATUS_MERGED,
  STATUS_EXCLUDED,
  STATUS_CLOSED_RELATED,
  STATUS_CLOSED_PHANTOM,
  STATUS_STALE_NO_DIAGNOSIS,
  STATUS_STALE_POST_SPECIALIST,
]);

export const CLOSURE_REASON_STATUSES: readonly string[] = [
  STATUS_CLOSED_BENIGN,
  STATUS_STALE_NO_DIAGNOSIS,
  STATUS_STALE_POST_SPECIALIST,
  STATUS_CLOSED_RELATED,
];

export const ALWAYS_EXCLUDE_STATUSES: readonly string[] = [
  STATUS_MERGED,
  STATUS_CLOSED_PHANTOM,
];


// -- Migration: legacy aliases ---------------------------------------------

export const LEGACY_STATUS_REWRITES: Readonly<Record<string, string>> = {
  benign_closed: STATUS_CLOSED_BENIGN,
};


// -- Helpers ---------------------------------------------------------------

export function normaliseStatus(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  return LEGACY_STATUS_REWRITES[raw] ?? raw;
}

export function isOpen(raw: string | null | undefined): boolean {
  const v = normaliseStatus(raw);
  return v != null && OPEN_STATUSES.has(v);
}

export function isClosed(raw: string | null | undefined): boolean {
  const v = normaliseStatus(raw);
  return v != null && CLOSED_STATUSES.has(v);
}
