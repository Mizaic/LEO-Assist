"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Small confidence indicator for a CONCEPT leaf, reused everywhere a
 * criterion is rendered: the sentence/tree canvas's ``ConceptPill``,
 * and the wizard's ``ListRecommendationView`` rows.
 *
 * Deliberately mirrors ``ReviewCard.tsx``'s ``TierBadge`` -- same
 * banding source (``getTerminologyConfidenceBand``), same Chip +
 * Tooltip shape -- so a reviewer who already recognises that pattern
 * from the coding-review queue does not have to learn a second visual
 * language here. High confidence renders as nothing at all (per the
 * plan: "high-confidence rows are the only ones that stay truly
 * glanceable") -- this component only ever appears when there is
 * something worth a second look, or once it has already been given one.
 */
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";

import { getTerminologyConfidenceExplanation } from "@/lib/terminologyConfidence";
import { criterionConfidenceBand, isHumanReviewed } from "./confidenceGate";
import type { LogicCriterion } from "./types";

interface Props {
  criterion: LogicCriterion | null | undefined;
}

export default function ConfidenceBadge({ criterion }: Props) {
  if (!criterion) return null;
  const band = criterionConfidenceBand(criterion);
  const reviewed = isHumanReviewed(criterion);

  if (band === "high" || band === "unknown") return null;

  if (reviewed) {
    const pct = Math.round((criterion.confidence ?? 0) * 100);
    const reviewedLabel = criterion.human_reviewed_by
      ? `Confirmed by ${criterion.human_reviewed_by}`
      : "Confirmed";
    return (
      <Tooltip title={`AI was ${pct}% sure. ${reviewedLabel}.`} arrow>
        <Chip
          label="Checked"
          size="small"
          color="success"
          variant="outlined"
          sx={{ height: 20, fontSize: "0.65rem", fontWeight: 600, borderRadius: 1 }}
        />
      </Tooltip>
    );
  }

  return (
    <Tooltip
      title={getTerminologyConfidenceExplanation(criterion.confidence)}
      arrow
    >
      <Chip
        label={band === "low" ? "Please check" : "Check this"}
        size="small"
        color={band === "low" ? "error" : "warning"}
        variant="outlined"
        sx={{ height: 20, fontSize: "0.65rem", fontWeight: 600, borderRadius: 1 }}
      />
    </Tooltip>
  );
}
