/**
 * Collapsed engineer fields for a Validation Lab stage.
 *
 * Atlas: DI-257D6883 / DO-158BE606 / VT-825F42CC
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

import { formatStageLabel } from "../labRunFormat";
import type { LabStageDetail, LabTraceSpan } from "../inspectorTypes";
import { StateKeyChips } from "./StateKeyChips";

export function StageExtraDetail({
  span,
  detailReady,
  stageDetail,
}: {
  span: LabTraceSpan;
  detailReady: boolean;
  stageDetail: LabStageDetail | null;
}) {
  const [open, setOpen] = useState(false);
  const modelLabel = modelLabelFromOutput(
    detailReady ? stageDetail?.output ?? null : null,
  );
  return (
    <Box sx={{ mb: 1.5 }}>
      <Button
        size="small"
        variant="text"
        data-testid="validation-lab-extra-detail"
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "Hide extra detail" : "Show extra detail"}
      </Button>
      {open ? (
        <Box sx={{ mt: 1 }}>
          <Typography
            variant="caption"
            color="text.disabled"
            sx={{ display: "block", mb: 1 }}
          >
            {formatStageLabel(span.step_id)}
          </Typography>
          <StageTelemetry span={span} modelLabel={modelLabel} />
          <StageKeyBlock
            title="Input keys"
            keys={span.input_keys}
            values={detailReady ? stageDetail?.input ?? {} : null}
            ready={detailReady}
            tone="input"
          />
          <StageKeyBlock
            title="Output keys"
            keys={span.output_keys}
            values={detailReady ? stageDetail?.output ?? {} : null}
            ready={detailReady}
            tone="output"
          />
        </Box>
      ) : null}
    </Box>
  );
}

function StageTelemetry({
  span,
  modelLabel,
}: {
  span: LabTraceSpan;
  modelLabel: string;
}) {
  if (!span.started_at && !span.worker_id && !modelLabel) return null;
  return (
    <Box
      sx={{
        display: "flex",
        flexWrap: "wrap",
        gap: 2,
        p: 1.25,
        mb: 1.5,
        bgcolor: "#F8FAFC",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "8px",
        fontSize: "0.72rem",
      }}
    >
      {span.worker_id ? (
        <Box>
          <Box component="span" sx={{ color: "text.disabled" }}>Worker </Box>
          <strong>{span.worker_id}</strong>
        </Box>
      ) : null}
      {span.started_at ? (
        <Box>
          <Box component="span" sx={{ color: "text.disabled" }}>Started </Box>
          <strong>{new Date(span.started_at).toLocaleTimeString()}</strong>
        </Box>
      ) : null}
      {modelLabel ? (
        <Box>
          <Box component="span" sx={{ color: "text.disabled" }}>Model </Box>
          <strong>{modelLabel}</strong>
        </Box>
      ) : null}
      {span.attempt !== undefined && span.attempt > 1 ? (
        <Box>
          <Box component="span" sx={{ color: "text.disabled" }}>Attempt </Box>
          <strong>{span.attempt}</strong>
        </Box>
      ) : null}
    </Box>
  );
}

function StageKeyBlock({
  title,
  keys,
  values,
  ready,
  tone,
}: {
  title: string;
  keys?: string[];
  values: Record<string, unknown> | null;
  ready: boolean;
  tone: "input" | "output";
}) {
  if (!keys?.length) return null;
  const output = tone === "output";
  return (
    <Box
      sx={{
        mb: 1.5,
        p: 1.25,
        bgcolor: output ? "#F0FDF4" : "#F8FAFC",
        border: "1px solid",
        borderColor: output ? "#BBF7D0" : "divider",
        borderRadius: "8px",
      }}
    >
      <Typography
        variant="caption"
        sx={{
          display: "block",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: output ? "#166534" : "text.disabled",
          mb: 0.75,
        }}
      >
        {title}
      </Typography>
      <StateKeyChips keys={keys} values={values} valuesReady={ready} />
    </Box>
  );
}

function modelLabelFromOutput(
  output: Record<string, unknown> | null,
): string {
  if (!output) return "";
  const name = String(output.extraction_model_name || "").trim();
  const version = String(output.extraction_model_version || "").trim();
  const route = String(output.extraction_route || "").trim();
  return [name, version, route].filter(Boolean).join(" -- ");
}
