/**
 * Unit tests for the medium/low-confidence anti-rubber-stamp gate.
 *
 * A pathway cannot be marked done while any row is below the "high"
 * confidence band or flagged ``needs_human_review``, without that
 * row's own explicit confirm action (``human_reviewed_at``) having
 * fired. Once fired, the row never re-gates even though the AI's
 * original ``confidence`` / ``needs_human_review`` values are left
 * untouched.
 */
import { assignNodeIds } from "../treeOps";
import type { LogicCriterion } from "../types";
import {
  criterionConfidenceBand,
  criterionNeedsConfirmation,
  findUnconfirmedLeafNodeIds,
  gateBlockedReason,
  isHumanReviewed,
  markCriterionReviewed,
  pathwayIsClearToConfirm,
} from "../confidenceGate";

function criterion(overrides: Partial<LogicCriterion> = {}): LogicCriterion {
  return {
    snomed_concept_id: "43364001",
    preferred_term: "Upper abdominal pain",
    ...overrides,
  };
}

describe("criterionConfidenceBand", () => {
  it("bands a high-confidence criterion as high", () => {
    expect(criterionConfidenceBand(criterion({ confidence: 0.98 }))).toBe(
      "high",
    );
  });
  it("bands a medium-confidence criterion as medium", () => {
    expect(criterionConfidenceBand(criterion({ confidence: 0.8 }))).toBe(
      "medium",
    );
  });
  it("bands a low-confidence criterion as low", () => {
    expect(criterionConfidenceBand(criterion({ confidence: 0.3 }))).toBe(
      "low",
    );
  });
  it("bands a hand-authored criterion (no confidence) as unknown", () => {
    expect(criterionConfidenceBand(criterion())).toBe("unknown");
  });
});

describe("criterionNeedsConfirmation", () => {
  it("does not gate a high-confidence AI row", () => {
    expect(
      criterionNeedsConfirmation(criterion({ confidence: 0.99 })),
    ).toBe(false);
  });

  it("gates a medium-confidence AI row", () => {
    expect(
      criterionNeedsConfirmation(criterion({ confidence: 0.8 })),
    ).toBe(true);
  });

  it("gates a low-confidence AI row", () => {
    expect(
      criterionNeedsConfirmation(criterion({ confidence: 0.2 })),
    ).toBe(true);
  });

  it("gates a row explicitly flagged needs_human_review regardless of confidence", () => {
    expect(
      criterionNeedsConfirmation(
        criterion({ confidence: 0.99, needs_human_review: true }),
      ),
    ).toBe(true);
  });

  it("does not gate a hand-authored criterion with no AI signal at all", () => {
    expect(criterionNeedsConfirmation(criterion())).toBe(false);
  });

  it("stops gating once human_reviewed_at is stamped, even though confidence stays low", () => {
    const reviewed = markCriterionReviewed(
      criterion({ confidence: 0.2, needs_human_review: true }),
      "j.bloggs",
      "2026-06-12T10:00:00Z",
    );
    expect(criterionNeedsConfirmation(reviewed)).toBe(false);
    // The AI's own signal is untouched -- this is "a human looked at
    // this," not "the AI got more sure."
    expect(reviewed.confidence).toBe(0.2);
    expect(reviewed.needs_human_review).toBe(true);
    expect(isHumanReviewed(reviewed)).toBe(true);
  });
});

describe("markCriterionReviewed", () => {
  it("stamps human_reviewed_at and human_reviewed_by", () => {
    const reviewed = markCriterionReviewed(
      criterion({ confidence: 0.5 }),
      "j.bloggs",
      "2026-06-12T10:00:00Z",
    );
    expect(reviewed.human_reviewed_at).toBe("2026-06-12T10:00:00Z");
    expect(reviewed.human_reviewed_by).toBe("j.bloggs");
  });

  it("defaults reviewedAt to now when not supplied", () => {
    const before = Date.now();
    const reviewed = markCriterionReviewed(criterion(), "j.bloggs");
    const stampedMs = new Date(reviewed.human_reviewed_at!).getTime();
    expect(stampedMs).toBeGreaterThanOrEqual(before);
  });
});

describe("findUnconfirmedLeafNodeIds / pathwayIsClearToConfirm", () => {
  function makePathway() {
    return assignNodeIds({
      kind: "AND",
      children: [
        { kind: "CONCEPT", criterion: criterion({ confidence: 0.99 }) },
        {
          kind: "AT_LEAST",
          min: 1,
          children: [
            { kind: "CONCEPT", criterion: criterion({ confidence: 0.6 }) },
            { kind: "CONCEPT", criterion: criterion({ confidence: 0.97 }) },
          ],
        },
      ],
    });
  }

  it("finds the one gated leaf nested inside an AT_LEAST cluster", () => {
    const pathway = makePathway();
    const blockers = findUnconfirmedLeafNodeIds(pathway);
    expect(blockers).toHaveLength(1);
    expect(pathwayIsClearToConfirm(pathway)).toBe(false);
  });

  it("clears once the gated leaf is marked reviewed", () => {
    const pathway = makePathway();
    const atLeast = pathway.children![1];
    const gatedLeaf = atLeast.children![0];
    const fixed = {
      ...pathway,
      children: [
        pathway.children![0],
        {
          ...atLeast,
          children: [
            {
              ...gatedLeaf,
              criterion: markCriterionReviewed(gatedLeaf.criterion!, "reviewer"),
            },
            atLeast.children![1],
          ],
        },
      ],
    };
    expect(pathwayIsClearToConfirm(fixed)).toBe(true);
    expect(findUnconfirmedLeafNodeIds(fixed)).toHaveLength(0);
  });

  it("returns an empty array for a null/undefined node", () => {
    expect(findUnconfirmedLeafNodeIds(null)).toEqual([]);
    expect(findUnconfirmedLeafNodeIds(undefined)).toEqual([]);
  });
});

describe("gateBlockedReason", () => {
  it("returns null when nothing is blocking", () => {
    const pathway = assignNodeIds({
      kind: "AND",
      children: [{ kind: "CONCEPT", criterion: criterion({ confidence: 0.99 }) }],
    });
    expect(gateBlockedReason(pathway)).toBeNull();
  });

  it("uses singular phrasing for exactly one blocker", () => {
    const pathway = assignNodeIds({
      kind: "AND",
      children: [{ kind: "CONCEPT", criterion: criterion({ confidence: 0.4 }) }],
    });
    expect(gateBlockedReason(pathway)).toMatch(/^One row/);
  });

  it("uses plural phrasing with a count for multiple blockers", () => {
    const pathway = assignNodeIds({
      kind: "AND",
      children: [
        { kind: "CONCEPT", criterion: criterion({ confidence: 0.4 }) },
        { kind: "CONCEPT", criterion: criterion({ confidence: 0.5 }) },
      ],
    });
    expect(gateBlockedReason(pathway)).toBe(
      "2 rows still need your check before you can continue. Tap each one to confirm or change the match.",
    );
  });
});
