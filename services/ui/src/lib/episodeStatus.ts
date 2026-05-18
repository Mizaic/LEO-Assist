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
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
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
  in_review: STATUS_REVIEW,
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


// -- Review verdict --------------------------------------------------------
//
// Mirror of libs/episodes/lifecycle.py ReviewVerdict. The contract test
// tests/contracts/test_episode_status_vocabulary.py parses this list and
// asserts it is identical to the Python enum.
//
// Atlas trace:
//   DI: DI-E2498DF6
//   DO: DO-2A124BA0
//   VT: VT-2487F804

export const VERDICT_CONFIRMED_ACTIVE = "confirmed_active";
export const VERDICT_CONFIRMED_COMPLETED = "confirmed_completed";
export const VERDICT_CONFIRMED_BENIGN = "confirmed_benign";
export const VERDICT_CONFIRMED_MERGED = "confirmed_merged";
export const VERDICT_REJECTED = "rejected";

export const REVIEW_VERDICT_VALUES: readonly string[] = [
  VERDICT_CONFIRMED_ACTIVE,
  VERDICT_CONFIRMED_COMPLETED,
  VERDICT_CONFIRMED_BENIGN,
  VERDICT_CONFIRMED_MERGED,
  VERDICT_REJECTED,
];

// Projection verdict -> resulting EpisodeOfCare.status. Mirror of
// libs/episodes/lifecycle.py VERDICT_TO_STATUS. Consumers SHOULD use
// this map when they need to pre-render the status that a verdict
// would produce (e.g. for a confirmation dialog); the canonical
// writer is the /sign-off endpoint, never the client.
export const VERDICT_TO_STATUS: Readonly<Record<string, string>> = {
  [VERDICT_CONFIRMED_ACTIVE]: STATUS_ACTIVE,
  [VERDICT_CONFIRMED_COMPLETED]: STATUS_COMPLETED,
  [VERDICT_CONFIRMED_BENIGN]: STATUS_CLOSED_BENIGN,
  [VERDICT_CONFIRMED_MERGED]: STATUS_MERGED,
  [VERDICT_REJECTED]: STATUS_EXCLUDED,
};

// Plain-English labels for each verdict. Kept short (2-4 words) so
// the ReviewActionsPanel verdict selector is legible on narrow
// drawers. Plain English: "confirm active" not "confirm_active".
export const REVIEW_VERDICT_LABELS: Readonly<Record<string, string>> = {
  [VERDICT_CONFIRMED_ACTIVE]: "Confirm pathway is active",
  [VERDICT_CONFIRMED_COMPLETED]: "Confirm pathway is completed",
  [VERDICT_CONFIRMED_BENIGN]: "Confirm ruled out (benign)",
  [VERDICT_CONFIRMED_MERGED]: "Confirm duplicate of another pathway",
  [VERDICT_REJECTED]: "Reject (not a pathway)",
};

// One-sentence help text per verdict, shown under the selector.
export const REVIEW_VERDICT_HELP: Readonly<Record<string, string>> = {
  [VERDICT_CONFIRMED_ACTIVE]:
    "The patient is still being investigated or treated on this pathway.",
  [VERDICT_CONFIRMED_COMPLETED]:
    "Treatment is finished and no further action is expected.",
  [VERDICT_CONFIRMED_BENIGN]:
    "Cancer has been ruled out. Close this pathway as benign.",
  [VERDICT_CONFIRMED_MERGED]:
    "This pathway is a duplicate of another active pathway.",
  [VERDICT_REJECTED]:
    "The detector was wrong. This is not a real pathway.",
};

export function isValidVerdict(raw: string | null | undefined): boolean {
  return raw != null && REVIEW_VERDICT_VALUES.includes(raw);
}
