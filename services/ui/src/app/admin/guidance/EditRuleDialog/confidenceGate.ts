/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Anti-rubber-stamp gate for the highlight-to-build wizard's Step 3.
 *
 * A wizard that lets a reviewer "glance and click past" pre-filled rows
 * is efficient, but it is also exactly the condition under which a
 * subtly wrong AI draft gets confirmed fastest -- precisely because it
 * looks routine. This module is the concrete mechanism that stops that:
 * a pathway-level "looks right, continue" cannot silently pass a
 * medium/low-confidence or ``needs_human_review`` row. That row must
 * receive its own explicit tap (open the popover, see the candidates,
 * confirm or change) before the wizard allows moving on.
 *
 * Confidence lifecycle (the alert-fatigue trade): ``confidence`` is the
 * AI's score, immutable, set once. ``human_reviewed_at`` /
 * ``human_reviewed_by`` are a separate pair, modeled directly on
 * ``CodingReview.resolved_at`` / ``resolved_by``
 * (``libs/cypher/coding_review_queries.py``) -- once stamped, the row
 * never re-gates on reopen, even though ``confidence`` and
 * ``needs_human_review`` stay exactly as the AI set them (an auditable
 * record of what the AI thought, not a nag that keeps firing).
 */
import {
  getTerminologyConfidenceBand,
  type TerminologyConfidenceBand,
} from "@/lib/terminologyConfidence";
import type { EditableLogicNode, LogicCriterion } from "./types";

/** Confidence band actually shown to the reviewer for a criterion. */
export function criterionConfidenceBand(
  criterion: LogicCriterion | null | undefined,
): TerminologyConfidenceBand {
  return getTerminologyConfidenceBand(criterion?.confidence ?? null);
}

/**
 * True when this criterion has already been through an explicit human
 * decision (confirm or change) -- gating never re-fires after this,
 * regardless of the AI's original confidence/needs_human_review value.
 */
export function isHumanReviewed(
  criterion: LogicCriterion | null | undefined,
): boolean {
  return !!criterion?.human_reviewed_at;
}

/**
 * True when a CONCEPT leaf's criterion needs an explicit reviewer tap
 * before a pathway can be marked done: either the AI scored it below
 * "high" confidence, or the AI explicitly flagged
 * ``needs_human_review`` -- and neither has been superseded by an
 * actual human decision yet.
 */
export function criterionNeedsConfirmation(
  criterion: LogicCriterion | null | undefined,
): boolean {
  if (!criterion) return false;
  if (isHumanReviewed(criterion)) return false;
  if (criterion.needs_human_review) return true;
  const band = criterionConfidenceBand(criterion);
  return band === "medium" || band === "low";
}

/**
 * Stamp a human review decision onto a criterion. Called the moment a
 * reviewer's tap on a gated row fires its confirm/change action --
 * whether or not they actually changed the SNOMED code. ``confidence``
 * and ``needs_human_review`` are left untouched: this is "a human
 * looked at this," not "the AI got more sure."
 */
export function markCriterionReviewed(
  criterion: LogicCriterion,
  reviewedBy: string,
  reviewedAt: string = new Date().toISOString(),
): LogicCriterion {
  return {
    ...criterion,
    human_reviewed_at: reviewedAt,
    human_reviewed_by: reviewedBy,
  };
}

/**
 * Walk a pathway's subtree and collect the node_ids of every CONCEPT
 * leaf that still needs an explicit reviewer tap. An empty array means
 * the pathway is clear to mark done.
 */
export function findUnconfirmedLeafNodeIds(
  node: EditableLogicNode | null | undefined,
): string[] {
  if (!node) return [];
  const blockers: string[] = [];
  const walk = (n: EditableLogicNode): void => {
    if (n.kind === "CONCEPT" && criterionNeedsConfirmation(n.criterion)) {
      blockers.push(n.node_id);
    }
    for (const child of n.children ?? []) walk(child);
  };
  walk(node);
  return blockers;
}

/** True when every CONCEPT leaf under `node` has cleared the gate. */
export function pathwayIsClearToConfirm(
  node: EditableLogicNode | null | undefined,
): boolean {
  return findUnconfirmedLeafNodeIds(node).length === 0;
}

/**
 * Plain-English reason a "looks right, continue" action is blocked,
 * or null when nothing is blocking it. Reading age 9-11 per the
 * health-literacy rule.
 */
export function gateBlockedReason(
  node: EditableLogicNode | null | undefined,
): string | null {
  const count = findUnconfirmedLeafNodeIds(node).length;
  if (count === 0) return null;
  if (count === 1) {
    return "One row still needs your check before you can continue. Tap it to confirm or change the match.";
  }
  return `${count} rows still need your check before you can continue. Tap each one to confirm or change the match.`;
}
