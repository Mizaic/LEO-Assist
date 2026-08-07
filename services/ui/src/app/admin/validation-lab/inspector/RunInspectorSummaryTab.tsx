/**
 * Stage summary tab using pathway probe strategies.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { PROBE_STRATEGIES } from "@/components/pathway/edges/probeStrategies";
import type { PathSegment } from "@/lib/pipelineStateDiff";
import { formatStageLabel } from "../labRunFormat";
import type { LabPlanStep, LabStageDetail, LabTraceSpan } from "../inspectorTypes";
import { resolveSubgraphId } from "./inspectorSubgraph";
import { TraceWaterfallChart } from "./TraceWaterfallChart";

interface Props {
  spans: LabTraceSpan[];
  planSteps: LabPlanStep[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
  loading: boolean;
}

function StageSummaryBody({
  subgraphId,
  input,
  output,
}: {
  subgraphId: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
}) {
  const [inspectPath, setInspectPath] = useState<PathSegment[] | null>(null);
  const strategy = PROBE_STRATEGIES[subgraphId];

  const stageSummary = output.stage_summary;
  const guidelineDiagnostics = output.guideline_diagnostics;

  if (!strategy && !stageSummary) {
    return (
      <Typography variant="body2" color="text.secondary">
        No summary probe registered for subgraph &quot;{subgraphId}&quot;.
      </Typography>
    );
  }

  const headline = strategy
    ? strategy.headline(output, input)
    : String((stageSummary as Record<string, unknown>).headline || "Stage summary");

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} alignItems="center">
        {strategy ? (
          <Typography component="span" aria-hidden="true">
            {strategy.icon}
          </Typography>
        ) : null}
        <Typography variant="body2" fontWeight={600}>
          {headline}
        </Typography>
      </Stack>

      {stageSummary && typeof stageSummary === "object" ? (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
            fontFamily: "monospace",
            fontSize: 11,
          }}
        >
          <Typography variant="caption" color="text.secondary" display="block">
            Stage summary
          </Typography>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {JSON.stringify(stageSummary, null, 2)}
          </pre>
        </Box>
      ) : null}

      {strategy ? (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
          }}
        >
          <strategy.Detail
            input={input}
            output={output}
            openInspector={(path) => setInspectPath(path)}
          />
        </Box>
      ) : null}

      {guidelineDiagnostics && typeof guidelineDiagnostics === "object" ? (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
            fontFamily: "monospace",
            fontSize: 11,
          }}
        >
          <Typography variant="caption" color="text.secondary" display="block">
            Guideline diagnostics (Validation Lab)
          </Typography>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {JSON.stringify(guidelineDiagnostics, null, 2)}
          </pre>
        </Box>
      ) : null}

      {inspectPath ? (
        <Box
          sx={{
            bgcolor: "grey.900",
            color: "grey.100",
            borderRadius: 1,
            p: 1,
            fontFamily: "monospace",
            fontSize: 11,
            maxHeight: 180,
            overflow: "auto",
          }}
        >
          <Typography variant="caption" color="grey.400" display="block" sx={{ mb: 0.5 }}>
            {inspectPath.join(".")}
          </Typography>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(
              inspectPath.reduce<unknown>((current, segment) => {
                if (current == null || typeof current !== "object") return undefined;
                return (current as Record<string, unknown>)[String(segment)];
              }, output),
              null,
              2,
            )}
          </pre>
        </Box>
      ) : null}
    </Stack>
  );
}

export function RunInspectorSummaryTab({
  spans,
  planSteps,
  selectedStepId,
  onSelectStep,
  stageDetail,
  loading,
}: Props) {
  const selectedSpan = useMemo(
    () => spans.find((span) => span.step_id === selectedStepId) || null,
    [spans, selectedStepId],
  );

  const subgraphId = selectedStepId
    ? resolveSubgraphId(selectedStepId, planSteps, selectedSpan)
    : "";

  const input = (stageDetail?.input || {}) as Record<string, unknown>;
  const output = (stageDetail?.output || {}) as Record<string, unknown>;

  return (
    <Stack spacing={1.5} data-testid="validation-lab-inspector-summary">
      <TraceWaterfallChart
        spans={spans}
        selectedStepId={selectedStepId}
        onSelectStep={onSelectStep}
        compact
      />
      {!selectedStepId ? (
        <Typography variant="body2" color="text.secondary">
          Select a span above to view a readable summary for that stage.
        </Typography>
      ) : null}
      {loading ? (
        <Typography variant="body2" color="text.secondary">
          Loading stage detail...
        </Typography>
      ) : null}
      {selectedStepId && !loading && stageDetail ? (
        <StageSummaryBody subgraphId={subgraphId} input={input} output={output} />
      ) : null}
      {selectedStepId && !loading && !stageDetail ? (
        <Typography variant="body2" color="text.secondary">
          No detail loaded for {formatStageLabel(selectedStepId)} yet.
        </Typography>
      ) : null}
    </Stack>
  );
}
