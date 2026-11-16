/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Companion sub-sections for StepPathwayConditions: weighted companion
 * checklist banner and inline editors for resolved DEMOGRAPHIC /
 * OBSERVATION rows. Split out so StepPathwayConditions stays below the
 * 500-LOC file limit.
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import DemographicRow from "../LogicTreeEditor/DemographicRow";
import ObservationRow from "../LogicTreeEditor/ObservationRow";
import type { EditableLogicNode, NodeUpdate } from "../types";
import { STEP_PATHWAY_CONDITIONS } from "./copy";

export interface WeightedChecklistView {
  title: string;
  threshold: number;
  expanded: boolean;
  scorePhrase: string | null;
  majors: string[];
  minors: string[];
}

export function WeightedChecklistSection({
  weightedChecklist,
  onExpandWeightedChecklist,
}: {
  weightedChecklist: WeightedChecklistView | null;
  onExpandWeightedChecklist?: () => void;
}) {
  if (!weightedChecklist) return null;
  if (!weightedChecklist.expanded && onExpandWeightedChecklist) {
    const expandLabel = STEP_PATHWAY_CONDITIONS.weightedChecklistExpand(
      weightedChecklist.threshold,
    );
    return (
      <Box
        sx={{
          p: 1.5,
          borderRadius: 1.5,
          border: "1px dashed",
          borderColor: "primary.main",
        }}
        data-testid="weighted-checklist-expand"
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
          {weightedChecklist.title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {STEP_PATHWAY_CONDITIONS.weightedChecklistExpandHint}
        </Typography>
        <Tooltip title={STEP_PATHWAY_CONDITIONS.weightedChecklistExpandHint}>
          <Button
            variant="contained"
            size="small"
            onClick={onExpandWeightedChecklist}
            aria-label={expandLabel}
          >
            {expandLabel}
          </Button>
        </Tooltip>
      </Box>
    );
  }
  if (!weightedChecklist.expanded) return null;
  return (
    <Typography variant="body2" color="text.secondary">
      Major features ({weightedChecklist.majors.length}) and minor features (
      {weightedChecklist.minors.length}). Score at least {weightedChecklist.threshold}{" "}
      means any two majors, or one major plus one minor, or three minors.
    </Typography>
  );
}

export function ExpandedConditionEditors({
  expandedDemographicNode,
  expandedObservationNode,
  onUpdatePathway,
  onSelectObservation,
}: {
  expandedDemographicNode: EditableLogicNode | null;
  expandedObservationNode: EditableLogicNode | null;
  onUpdatePathway?: (update: NodeUpdate) => void;
  onSelectObservation?: (nodeId: string, anchor?: HTMLElement | null) => void;
}) {
  return (
    <>
      {expandedDemographicNode && onUpdatePathway && (
        <Box sx={{ p: 1.5, borderRadius: 1.5, border: "1px solid", borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
            {STEP_PATHWAY_CONDITIONS.editingDemographicHeading}
          </Typography>
          <DemographicRow node={expandedDemographicNode} onUpdate={onUpdatePathway} />
        </Box>
      )}
      {expandedObservationNode && onUpdatePathway && onSelectObservation && (
        <Box sx={{ p: 1.5, borderRadius: 1.5, border: "1px solid", borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
            {STEP_PATHWAY_CONDITIONS.editingObservationHeading}
          </Typography>
          <ObservationRow
            node={expandedObservationNode}
            onUpdate={onUpdatePathway}
            onSelect={onSelectObservation}
          />
        </Box>
      )}
    </>
  );
}
