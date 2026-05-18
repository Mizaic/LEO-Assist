/**
 * Canonical EpisodeOfCare lifecycle helpers for the UI.
 *
 * Mirrors the writer-side helpers in libs/episodes/lifecycle.py and
 * libs/episodes/status.py so the manual UI ALWAYS:
 *
 *   * renders the same status label the detector wrote (no stale
 *     "in_review" chips after the canonical lifecycle migration);
 *   * gates the action set (Mark reviewed / Close / Merge / Re-open)
 *     on the canonical status, not the legacy spelling; and
 *   * sends the canonical status string on every write call so the
 *     graph never re-acquires legacy spellings via the manual UI.
 *
 * Atlas trace:
 *   DI: DI-C4CEFA32 (canonical lifecycle + manual UI parity)
 *   DO: DO-C5B5E91E (lifecycle helpers)
 *   VT: VT-66DA36EC (round-trip parity)
 *
 * Single source of truth -- every UI component that compares,
 * renders, or writes EpisodeOfCare.status MUST go through this
 * module. The contract test
 * tests/contracts/test_episode_status_vocabulary.py asserts no
 * production writer drifts away from this vocabulary.
 */

import {
  CLOSED_STATUSES,
  ENGINE_OUTPUT_STATUSES,
  OPEN_STATUSES,
  STATUS_ACTIVE,
  STATUS_CLOSED,
  STATUS_CLOSED_BENIGN,
  STATUS_COMPLETED,
  STATUS_MERGED,
  STATUS_REVIEW,
  isClosed as legacyIsClosed,
  isOpen as legacyIsOpen,
  normaliseStatus,
} from "./episodeStatus";

// ---------------------------------------------------------------------------
// Display labels -- plain English, reading age 9-11.
// ---------------------------------------------------------------------------

/**
 * Map of canonical (and a few legacy) status values to the short
 * label rendered in the patient drawer chip rail and the audit
 * trail. Plain English so a non-clinical curator can read it.
 *
 * Anything not in the map falls through to the raw status string
 * so a brand-new value the canonical module has not yet caught up
 * with is still readable.
 */
export const EPISODE_STATUS_LABELS: Readonly<Record<string, string>> = {
  [STATUS_ACTIVE]: "In flight",
  [STATUS_REVIEW]: "In review",
  [STATUS_COMPLETED]: "Completed",
  [STATUS_CLOSED_BENIGN]: "Closed (not cancer)",
  [STATUS_CLOSED]: "Closed",
  [STATUS_MERGED]: "Merged",
  closed_related: "Closed (duplicate)",
  closed_phantom: "Closed (no evidence)",
  stale_no_diagnosis: "Closed (no diagnosis)",
  stale_post_specialist: "Closed (after specialist)",
  excluded: "Excluded",
  in_progress: "In progress",
};

/**
 * Render a status (legacy or canonical) as a plain-English label.
 * Falls back to the raw value when no label exists.
 */
export function episodeStatusLabel(raw: string | null | undefined): string {
  const canonical = normaliseStatus(raw) ?? raw ?? "";
  if (!canonical) return "Unknown";
  return EPISODE_STATUS_LABELS[canonical] ?? canonical;
}

// ---------------------------------------------------------------------------
// Verdict (curator sign-off) helpers.
// ---------------------------------------------------------------------------

/**
 * True when an episode has a curator sign-off recorded
 * (`reviewed_at` is non-empty). The recompute path on the server
 * will refuse to overwrite a reviewed status; the UI uses the same
 * predicate so it can render the verdict chip and gate actions
 * that should only run on un-reviewed episodes.
 */
export function isReviewed(
  episode: { reviewed_at?: string | null } | null | undefined,
): boolean {
  if (!episode) return false;
  const raw = episode.reviewed_at;
  if (raw == null) return false;
  return String(raw).trim() !== "";
}

/** Current open / closed / reviewed state, in plain English. */
export function lifecyclePhase(
  episode: { status?: string | null; reviewed_at?: string | null } | null,
): "open" | "review" | "closed" | "reviewed_open" | "reviewed_closed" | "unknown" {
  if (!episode) return "unknown";
  const canonical = normaliseStatus(episode.status) ?? episode.status ?? "";
  const reviewed = isReviewed(episode);
  if (legacyIsClosed(canonical)) {
    return reviewed ? "reviewed_closed" : "closed";
  }
  if (canonical === STATUS_REVIEW) return reviewed ? "reviewed_open" : "review";
  if (legacyIsOpen(canonical)) return reviewed ? "reviewed_open" : "open";
  return "unknown";
}

// ---------------------------------------------------------------------------
// Action set -- which buttons the manual UI offers for a given
// episode. Mirrors the canonical_close_props / canonical_review_props
// / canonical_merge_props helpers on the Python side.
// ---------------------------------------------------------------------------

/**
 * Curator action vocabulary. The manual UI exposes exactly these
 * actions; the server enforces the same set via the lifecycle
 * helpers.
 *
 *   - "review.mark"   -- mark the episode as reviewed (sets
 *                         reviewed_by/_at, clears the dual review
 *                         flags). Allowed when the episode is open
 *                         AND not yet reviewed.
 *   - "review.reopen" -- reopen for re-review (clears reviewed_*
 *                         and sets status back to "review"). Allowed
 *                         when the episode is reviewed but otherwise
 *                         still open OR completed.
 *   - "close.benign"  -- close as "not cancer". Allowed when the
 *                         episode is open OR completed and not yet
 *                         closed_benign.
 *   - "close.completed" -- mark treatment completed. Allowed when
 *                         the episode is open and not closed.
 *   - "close.no_diagnosis" -- close with the generic "closed"
 *                         status. Allowed when open and not closed.
 *   - "merge.into"    -- merge another episode into this one.
 *                         Allowed when this episode is open
 *                         (not closed, not merged).
 */
export type EpisodeAction =
  | "review.mark"
  | "review.reopen"
  | "close.benign"
  | "close.completed"
  | "close.no_diagnosis"
  | "merge.into";

const _CLOSE_ACTIONS: ReadonlySet<EpisodeAction> = new Set([
  "close.benign",
  "close.completed",
  "close.no_diagnosis",
]);

/**
 * Plain-English description of what each action does. Surfaced as
 * tooltip / button text so a curator who has never used the system
 * before can pick the right one.
 */
export const EPISODE_ACTION_LABELS: Readonly<Record<EpisodeAction, string>> = {
  "review.mark": "Mark reviewed",
  "review.reopen": "Re-open for review",
  "close.benign": "Close as not cancer",
  "close.completed": "Mark treatment completed",
  "close.no_diagnosis": "Close (no diagnosis)",
  "merge.into": "Merge another episode in",
};

/**
 * Return the actions the curator may take on this episode. The
 * order in the array is the order the actions should appear in the
 * UI -- positive verbs first, destructive last.
 */
export function availableActions(
  episode: { status?: string | null; reviewed_at?: string | null } | null,
): EpisodeAction[] {
  if (!episode) return [];
  const canonical = normaliseStatus(episode.status) ?? episode.status ?? "";
  const reviewed = isReviewed(episode);
  const closed = legacyIsClosed(canonical);
  const merged = canonical === STATUS_MERGED;
  if (merged) return [];

  const out: EpisodeAction[] = [];
  if (!closed && !reviewed) out.push("review.mark");
  if (reviewed) out.push("review.reopen");
  if (!closed) {
    out.push("close.completed", "close.benign", "close.no_diagnosis");
  } else if (canonical !== STATUS_CLOSED_BENIGN) {
    // A completed episode can still be revised down to "not cancer"
    // if the curator finds the diagnosis was wrong.
    out.push("close.benign");
  }
  if (!closed) out.push("merge.into");
  return out;
}

/**
 * The status string that an action writes. Used by the close /
 * merge dialog so the wire payload always carries the canonical
 * spelling, never a legacy alias.
 */
export function actionTargetStatus(action: EpisodeAction): string | null {
  switch (action) {
    case "close.benign":
      return STATUS_CLOSED_BENIGN;
    case "close.completed":
      return STATUS_COMPLETED;
    case "close.no_diagnosis":
      return STATUS_CLOSED;
    case "merge.into":
      return STATUS_MERGED;
    case "review.mark":
    case "review.reopen":
      // Review actions write reviewed_at/needs_review/needs_human_review
      // but do not change the status field directly.
      return null;
  }
}

/** True iff the action would close the episode. */
export function isCloseAction(action: EpisodeAction): boolean {
  return _CLOSE_ACTIONS.has(action);
}

// ---------------------------------------------------------------------------
// Re-exports so consumers can import everything from one module.
// ---------------------------------------------------------------------------

export {
  CLOSED_STATUSES,
  ENGINE_OUTPUT_STATUSES,
  OPEN_STATUSES,
  STATUS_ACTIVE,
  STATUS_CLOSED,
  STATUS_CLOSED_BENIGN,
  STATUS_COMPLETED,
  STATUS_MERGED,
  STATUS_REVIEW,
  legacyIsClosed as isClosed,
  legacyIsOpen as isOpen,
  normaliseStatus,
};
