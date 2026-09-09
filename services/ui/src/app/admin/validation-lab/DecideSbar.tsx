/**
 * Draft assessment host for the Decide phase.
 *
 * Atlas: DI-49BA8E04 / DI-A898556B / VT-592D30E9
 *
 * Atlas trace:
 *   DO: DO-7B63A6BE
 *   DI: DI-49BA8E04
 *   Risks: R-823853D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7B63A6BE")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { LeoSbarHost, SbarFinalView } from "@/components/sbar-final";
import type { PhaseSpan } from "./clinicalPhases";
import { DecideOutcomes } from "./DecideOutcomes";
import { useDecideEvidence } from "./useDecideEvidence";

interface Props {
  caseId: string;
  runId: string;
  pipelineRunId?: string;
  spans: PhaseSpan[];
}

export function DecideSbar({
  caseId,
  runId,
  pipelineRunId = "",
  spans,
}: Props) {
  const view = useDecideEvidence(caseId, runId, pipelineRunId, spans);
  return (
    <Box
      sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 1.5 }}
      data-testid="validation-lab-decide-sbar"
    >
      <DecideOutcomes
        guideline={view.guideline}
        completeness={view.completeness}
      />
      {view.assessmentId ? (
        <LeoSbarHost assessmentId={view.assessmentId} />
      ) : null}
      {!view.assessmentId && view.markdown ? (
        <SbarFinalView markdown={view.markdown} testIdPrefix="validation-lab-sbar" />
      ) : null}
      {!view.assessmentId && !view.markdown ? (
        <Typography variant="body2" color="text.secondary">
          {view.loading ? "Loading the draft..." : view.error || "The draft is not ready yet."}
        </Typography>
      ) : null}
    </Box>
  );
}
