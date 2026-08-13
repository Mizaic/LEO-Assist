/**
 * Pipeline tab: stage rail plus live facts/codes for the selected step.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-257D6883, DI-FE423B8D
 *   VT: VT-825F42CC
 */
"use client";

import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { formatStageLabel } from "../labRunFormat";
import { plainStageCopy } from "../plainStageCopy";
import type { LabStageDetail, LabTraceSpan } from "../inspectorTypes";
import { StageDetailPane } from "./StageDetailPane";
import { StageIcon, watchStepId } from "./pipelineWizardChrome";

interface Props {
  spans: LabTraceSpan[];
  onFixInGuards: (span: LabTraceSpan) => void;
  onMarkWrong?: (text: string) => void;
  previousHeadlines?: Record<string, string>;
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
  stageLoading: boolean;
}

export function PipelineWizard({
  spans,
  onFixInGuards,
  onMarkWrong,
  previousHeadlines,
  selectedStepId,
  onSelectStep,
  stageDetail,
  stageLoading,
}: Props) {
  const userPicked = useRef(false);
  useEffect(() => {
    if (userPicked.current || !spans.length) return;
    const next = watchStepId(spans);
    if (next && next !== selectedStepId) onSelectStep(next);
  }, [spans, selectedStepId, onSelectStep]);

  const selected =
    selectedStepId && spans.some((s) => s.step_id === selectedStepId)
      ? selectedStepId
      : watchStepId(spans);
  const span = spans.find((s) => s.step_id === selected) ?? spans[0];
  const detailReady =
    Boolean(stageDetail) &&
    stageDetail?.step_id === span?.step_id &&
    !stageLoading;

  if (!spans.length) {
    return (
      <Typography variant="body2" color="text.disabled" sx={{ p: 2 }}>
        Each step will show here as LEO works. Wait a moment.
      </Typography>
    );
  }

  return (
    <Box
      sx={{
        display: "flex",
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "10px",
      }}
    >
      <StageRail
        spans={spans}
        selected={selected}
        onPick={(id) => {
          userPicked.current = true;
          onSelectStep(id);
        }}
      />
      {span ? (
        <StageDetailPane
          span={span}
          detailReady={detailReady}
          stageDetail={stageDetail}
          stageLoading={stageLoading}
          onFixInGuards={onFixInGuards}
          onMarkWrong={onMarkWrong}
          previousHeadline={previousHeadlines?.[span.step_id]}
        />
      ) : null}
    </Box>
  );
}

function StageRail({
  spans,
  selected,
  onPick,
}: {
  spans: LabTraceSpan[];
  selected: string;
  onPick: (id: string) => void;
}) {
  return (
    <Box
      sx={{
        width: 220,
        flexShrink: 0,
        borderRight: "1px solid",
        borderColor: "divider",
        overflowY: "auto",
        bgcolor: "#FAFAFA",
      }}
    >
      <Typography
        variant="caption"
        sx={{
          display: "block",
          px: 1.5,
          py: 1,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "text.disabled",
        }}
      >
        Stages
      </Typography>
      {spans.map((s) => (
        <StageRailRow
          key={s.step_id}
          span={s}
          active={s.step_id === selected}
          onPick={onPick}
        />
      ))}
    </Box>
  );
}

function StageRailRow({
  span,
  active,
  onPick,
}: {
  span: LabTraceSpan;
  active: boolean;
  onPick: (id: string) => void;
}) {
  const copy = plainStageCopy(span.step_id, span.name);
  return (
    <Box
      onClick={() => onPick(span.step_id)}
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 1,
        px: 1.5,
        py: 1,
        cursor: "pointer",
        borderLeft: "3px solid",
        borderLeftColor: active ? "primary.main" : "transparent",
        bgcolor: active ? "primary.50" : "transparent",
        "&:hover": { bgcolor: active ? "primary.50" : "action.hover" },
      }}
    >
      <Box sx={{ mt: 0.25, flexShrink: 0 }}>
        <StageIcon status={span.status} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography
          variant="caption"
          fontWeight={active ? 700 : 500}
          noWrap
          sx={{ display: "block" }}
        >
          {copy.name}
        </Typography>
        <Typography
          variant="caption"
          sx={{ fontSize: "0.65rem", color: "text.disabled", display: "block" }}
          noWrap
        >
          {span.work_preview?.headline || formatStageLabel(span.step_id)}
        </Typography>
      </Box>
    </Box>
  );
}
