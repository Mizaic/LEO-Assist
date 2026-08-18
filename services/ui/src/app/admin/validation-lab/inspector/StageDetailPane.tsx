/**
 * Selected-stage story, Yes/No, and collapsed extra detail.
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

import { parseSbarStageError } from "../pipelineStageErrors";
import { plainStageCopy } from "../plainStageCopy";
import type { LabStageDetail, LabTraceSpan, LabWorkItem, LabWorkPreview } from "../inspectorTypes";
import { diffWorkItems } from "../letterHighlight";
import { isCodingStep, isFirstFactStep } from "../reviewWalk";
import { StageStoryPanel } from "./StageStoryPanel";
import { StageExtraDetail } from "./StageExtraDetail";
import { stageStory } from "./stageEvidence";
import { inputWorkItems, workPreviewFromStage } from "./stageWorkItems";
import { formatMs, StageIcon, stageColor } from "./pipelineWizardChrome";

interface Props {
  span: LabTraceSpan;
  detailReady: boolean;
  stageDetail: LabStageDetail | null;
  stageLoading: boolean;
  onFixInGuards: (span: LabTraceSpan) => void;
  onMarkWrong?: (text: string) => void;
  previousPreview?: LabWorkPreview;
  onNext?: () => void;
  reviewed?: boolean;
  isLastStep?: boolean;
  walkFinished?: boolean;
}

export function StageDetailPane(props: Props) {
  return <StagePaneBody model={buildPaneModel(props)} />;
}

type PaneModel = {
  span: LabTraceSpan;
  copyName: string;
  copyPlain: string;
  copyQuestion: string;
  walkFinished: boolean;
  onNext?: () => void;
  onMarkWrong?: (text: string) => void;
  markTarget: string;
  onAdvance?: () => void;
  retestNote: string;
  story: ReturnType<typeof stageStory>;
  items?: LabWorkItem[];
  loading: boolean;
  detailReady: boolean;
  stageDetail: LabStageDetail | null;
  errorText: string;
  errorCode: string;
  onFixInGuards: (span: LabTraceSpan) => void;
};

function buildPaneModel(props: Props): PaneModel {
  const {
    span,
    detailReady,
    stageDetail,
    stageLoading,
    onFixInGuards,
    onMarkWrong,
    previousPreview,
    onNext,
    reviewed,
    isLastStep,
    walkFinished,
  } = props;
  const copy = plainStageCopy(span.step_id, span.name);
  const output = detailReady ? stageDetail?.output || {} : null;
  const input = detailReady ? stageDetail?.input || {} : null;
  const story = stageStory(span.step_id, output, input);
  const preview = workPreviewFromStage(output, input, span.work_preview);
  const diffedPreview = buildDiffedPreview(
    preview,
    previousPreview,
    detailReady ? inputWorkItems(stageDetail?.input) : [],
    span.step_id,
  );
  const chipKinds = story.kind === "facts" || story.kind === "codes";
  const retestNote =
    previousPreview?.headline && previousPreview.headline !== preview.headline
      ? `Before retest: ${previousPreview.headline}`
      : "";
  return {
    span,
    copyName: copy.name,
    copyPlain: copy.plain,
    copyQuestion: copy.question,
    walkFinished: Boolean(walkFinished),
    onNext,
    onMarkWrong,
    markTarget: preview.items?.[0]?.text || preview.headline || span.step_id,
    onAdvance: reviewed && !isLastStep ? onNext : undefined,
    retestNote,
    story,
    items: chipKinds ? diffedPreview.items : story.items,
    loading: stageLoading && !span.work_preview?.items?.length,
    detailReady,
    stageDetail,
    errorText: stageErrorText(span, detailReady ? stageDetail : null),
    errorCode: stageErrorCode(span, detailReady ? stageDetail : null),
    onFixInGuards,
  };
}

function StagePaneBody({ model }: { model: PaneModel }) {
  return (
    <Box sx={{ flex: 1, overflowY: "auto", p: 2, minWidth: 0 }}>
      <StageHeading span={model.span} name={model.copyName} />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {model.copyPlain}
      </Typography>
      <FinishedBanner show={model.walkFinished} />
      <StageQuestionCard
        status={model.span.status}
        question={model.copyQuestion}
        onYes={model.onNext}
        onNo={model.onMarkWrong ? () => model.onMarkWrong?.(model.markTarget) : undefined}
        onAdvance={model.onAdvance}
      />
      {model.retestNote ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          {model.retestNote}
        </Typography>
      ) : null}
      <StageStoryPanel
        story={model.story}
        items={model.items}
        loading={model.loading}
        onMarkWrong={model.onMarkWrong}
      />
      <StageExtraDetail
        span={model.span}
        detailReady={model.detailReady}
        stageDetail={model.stageDetail}
      />
      <StageErrorAlert
        span={model.span}
        errorText={model.errorText}
        errorCode={model.errorCode}
        onFixInGuards={model.onFixInGuards}
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

function FinishedBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <Alert
      severity="success"
      data-testid="validation-lab-review-finished"
      sx={{ mb: 1.5, fontSize: "0.85rem" }}
    >
      Review finished. You can save this as gold.
    </Alert>
  );
}

function StageQuestionCard({
  status,
  question,
  onYes,
  onNo,
  onAdvance,
}: {
  status: string;
  question: string;
  onYes?: () => void;
  onNo?: () => void;
  onAdvance?: () => void;
}) {
  if (status !== "completed") return null;
  return (
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
        {question}
      </Typography>
      <StageYesNo onYes={onYes} onNo={onNo} onAdvance={onAdvance} />
    </Box>
  );
}

function StageYesNo({
  onYes,
  onNo,
  onAdvance,
}: {
  onYes?: () => void;
  onNo?: () => void;
  onAdvance?: () => void;
}) {
  if (!onYes && !onNo && !onAdvance) return null;
  return (
    <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
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
      {onAdvance ? (
        <Button
          size="small"
          variant="text"
          data-testid="validation-lab-after-finding-next"
          aria-label="Next step"
          onClick={onAdvance}
        >
          Next step
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
