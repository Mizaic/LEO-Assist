/**
 * Selected-stage facts, keys, and error reason.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-257D6883, DI-FE423B8D
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import BuildOutlinedIcon from "@mui/icons-material/BuildOutlined";

import { formatStageLabel } from "../labRunFormat";
import { parseSbarStageError } from "../pipelineStageErrors";
import { plainStageCopy } from "../plainStageCopy";
import type { LabStageDetail, LabTraceSpan, LabWorkItem, LabWorkPreview } from "../inspectorTypes";
import { diffWorkItems } from "../letterHighlight";
import { isCodingStep, isFirstFactStep } from "../reviewWalk";
import { StateKeyChips } from "./StateKeyChips";
import { StageWorkPreview } from "./StageWorkPreview";
import { inputWorkItems, workPreviewFromStage } from "./stageWorkItems";
import { formatMs, StageIcon, stageColor } from "./pipelineWizardChrome";

interface Props {
  span: LabTraceSpan;
  detailReady: boolean;
  stageDetail: LabStageDetail | null;
  stageLoading: boolean;
  onFixInGuards: (span: LabTraceSpan) => void;
  onMarkWrong?: (text: string) => void;
  /** Full work preview from the previous run (retest mode). */
  previousPreview?: LabWorkPreview;
  onNext?: () => void;
}

export function StageDetailPane({
  span,
  detailReady,
  stageDetail,
  stageLoading,
  onFixInGuards,
  onMarkWrong,
  previousPreview,
  onNext,
}: Props) {
  const copy = plainStageCopy(span.step_id, span.name);
  const preview = workPreviewFromStage(
    detailReady ? stageDetail?.output || {} : null,
    detailReady ? stageDetail?.input || {} : null,
    span.work_preview,
  );
  const diffedPreview = buildDiffedPreview(
    preview,
    previousPreview,
    detailReady ? inputWorkItems(stageDetail?.input) : [],
    span.step_id,
  );
  const errorText = stageErrorText(span, detailReady ? stageDetail : null);
  const errorCode = stageErrorCode(span, detailReady ? stageDetail : null);
  const hasPreview = Boolean(
    span.work_preview?.headline || span.work_preview?.items?.length,
  );
  return (
    <Box sx={{ flex: 1, overflowY: "auto", p: 2, minWidth: 0 }}>
      <StageHeading span={span} name={copy.name} />
      <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 0.5 }}>
        {formatStageLabel(span.step_id)}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {copy.plain}
      </Typography>
      {span.status === "completed" && (
        <Box
          sx={{
            p: 1.25,
            mb: 1.5,
            bgcolor: "#EFF6FF",
            borderLeft: "3px solid",
            borderColor: "primary.main",
            borderRadius: "0 8px 8px 0",
          }}
        >
          <Typography variant="body2" fontWeight={600} color="primary.dark">
            {copy.question}
          </Typography>
          <StageYesNo
            onYes={onNext}
            onNo={
              onMarkWrong
                ? () =>
                    onMarkWrong(
                      preview.items?.[0]?.text || preview.headline || span.step_id,
                    )
                : undefined
            }
          />
        </Box>
      )}
      {previousPreview?.headline && previousPreview.headline !== preview.headline ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          Before retest: {previousPreview.headline}
        </Typography>
      ) : null}
      <StageWorkPreview
        preview={diffedPreview}
        loading={stageLoading && !hasPreview}
        onMarkWrong={onMarkWrong}
      />
      <StageTelemetry
        span={span}
        modelLabel={modelLabelFromOutput(
          detailReady ? stageDetail?.output ?? null : null,
        )}
      />
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
      <StageErrorAlert
        span={span}
        errorText={errorText}
        errorCode={errorCode}
        onFixInGuards={onFixInGuards}
      />
    </Box>
  );
}

function buildDiffedPreview(
  preview: LabWorkPreview,
  previousPreview: LabWorkPreview | undefined,
  stageInputItems: LabWorkItem[],
  stepId: string,
): LabWorkPreview {
  const coding = isCodingStep(stepId);
  const inRetestMode = Boolean(previousPreview);
  const baseItems: LabWorkItem[] = inRetestMode
    ? (previousPreview?.items || [])
    : isFirstFactStep(stepId)
      ? []
      : stageInputItems;
  if (!baseItems.length && !inRetestMode) return preview;
  return { ...preview, items: diffWorkItems(baseItems, preview.items || [], coding) };
}

function StageYesNo({
  onYes,
  onNo,
}: {
  onYes?: () => void;
  onNo?: () => void;
}) {
  if (!onYes && !onNo) return null;
  return (
    <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
      {onYes ? (
        <Button
          size="small"
          variant="contained"
          data-testid="validation-lab-next-step"
          aria-label="Yes, this step looks right"
          onClick={onYes}
        >
          Yes
        </Button>
      ) : null}
      {onNo ? (
        <Button
          size="small"
          variant="outlined"
          data-testid="validation-lab-mark-wrong"
          aria-label="No, mark something wrong"
          onClick={onNo}
        >
          No
        </Button>
      ) : null}
    </Stack>
  );
}

function StageHeading({ span, name }: { span: LabTraceSpan; name: string }) {
  return (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
      <StageIcon status={span.status} />
      <Typography variant="subtitle2" fontWeight={700}>
        {name}
      </Typography>
      <Chip
        size="small"
        label={span.status}
        color={stageColor(span.status)}
        sx={{ height: 20, fontSize: "0.68rem" }}
      />
      {span.duration_ms !== undefined ? (
        <Typography variant="caption" color="text.disabled">
          {formatMs(span.duration_ms)}
        </Typography>
      ) : null}
    </Stack>
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

function StageErrorAlert({
  span,
  errorText,
  errorCode,
  onFixInGuards,
}: {
  span: LabTraceSpan;
  errorText: string;
  errorCode: string;
  onFixInGuards: (span: LabTraceSpan) => void;
}) {
  if (!errorText) {
    if (!span.warning_summary) return null;
    return (
      <Alert severity="warning" sx={{ fontSize: "0.8rem" }}>
        {span.warning_summary}
      </Alert>
    );
  }
  return (
    <Alert severity="error" sx={{ mb: 1.5, fontSize: "0.8rem" }}>
      {errorText}
      {errorCode ? (
        <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
          Reason code: {errorCode}
        </Typography>
      ) : null}
      {(span.rule_id || span.source_sentence) && (
        <Button
          size="small"
          variant="outlined"
          color="error"
          startIcon={<BuildOutlinedIcon />}
          sx={{ mt: 1, display: "block" }}
          onClick={() => onFixInGuards(span)}
        >
          Fix in Pipeline Guards
        </Button>
      )}
    </Alert>
  );
}

function stageErrorText(span: LabTraceSpan, detail: LabStageDetail | null): string {
  return (
    (detail?.error_summary || span.error_summary || "").trim() ||
    (detail?.errors?.[0] || span.errors?.[0] || "")
  );
}

function stageErrorCode(span: LabTraceSpan, detail: LabStageDetail | null): string {
  const raw = detail?.errors?.[0] || span.errors?.[0] || "";
  return parseSbarStageError(raw)?.code || "";
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
