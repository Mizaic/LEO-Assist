/**
 * Pipeline tab: stage rail plus live facts/codes for the selected step.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-257D6883, DI-FE423B8D
 *   VT: VT-825F42CC
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { formatStageLabel } from "../labRunFormat";
import { plainStageCopy } from "../plainStageCopy";
import type { LabStageDetail, LabTraceSpan, LabWorkPreview } from "../inspectorTypes";
import { StageDetailPane } from "./StageDetailPane";
import {
  canOpenStep,
  firstStepId,
  nextStepId,
  unlockedIndex,
  walkComplete,
} from "../reviewWalk";
import { StageIcon } from "./pipelineWizardChrome";

interface Props {
  spans: LabTraceSpan[];
  onFixInGuards: (span: LabTraceSpan) => void;
  onMarkWrong?: (text: string) => void;
  /** Previous run's work preview per step_id (retest mode). */
  previousPreviews?: Record<string, LabWorkPreview>;
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
  stageLoading: boolean;
  /** Increments when the reviewer saves a finding for the open step. */
  findingSavedAt?: number;
}

export function PipelineWizard({
  spans,
  onFixInGuards,
  onMarkWrong,
  previousPreviews,
  selectedStepId,
  onSelectStep,
  stageDetail,
  stageLoading,
  findingSavedAt,
}: Props) {
  const [reviewed, setReviewed] = useState<string[]>([]);
  useEffect(() => {
    setReviewed([]);
  }, [spans[0]?.step_id]);
  useEffect(() => {
    const first = firstStepId(spans);
    if (!first) return;
    if (!selectedStepId || !spans.some((s) => s.step_id === selectedStepId)) {
      onSelectStep(first);
    }
  }, [spans, selectedStepId, onSelectStep]);

  const selected =
    selectedStepId && spans.some((s) => s.step_id === selectedStepId)
      ? selectedStepId
      : firstStepId(spans);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  useEffect(() => {
    if (!findingSavedAt) return;
    const id = selectedRef.current;
    if (!id) return;
    setReviewed((prev) => (prev.includes(id) ? prev : [...prev, id]));
  }, [findingSavedAt]);
  const openIndex = unlockedIndex(spans, reviewed);
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
        reviewed={reviewed}
        openIndex={openIndex}
        onPick={(id) => {
          if (canOpenStep(spans, id, reviewed)) onSelectStep(id);
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
          previousPreview={previousPreviews?.[span.step_id]}
          reviewed={reviewed.includes(span.step_id)}
          isLastStep={!nextStepId(spans, span.step_id)}
          walkFinished={walkComplete(spans, reviewed)}
          onNext={() => {
            if (!reviewed.includes(span.step_id)) {
              setReviewed([...reviewed, span.step_id]);
            }
            const next = nextStepId(spans, span.step_id);
            if (next) onSelectStep(next);
          }}
        />
      ) : null}
    </Box>
  );
}

function StageRail({
  spans,
  selected,
  reviewed,
  openIndex,
  onPick,
}: {
  spans: LabTraceSpan[];
  selected: string;
  reviewed: string[];
  openIndex: number;
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
      {spans.map((s, index) => (
        <StageRailRow
          key={s.step_id}
          span={s}
          active={s.step_id === selected}
          locked={index > openIndex}
          seen={reviewed.includes(s.step_id)}
          onPick={onPick}
        />
      ))}
    </Box>
  );
}

function StageRailRow({
  span,
  active,
  locked,
  seen,
  onPick,
}: {
  span: LabTraceSpan;
  active: boolean;
  locked: boolean;
  seen: boolean;
  onPick: (id: string) => void;
}) {
  const copy = plainStageCopy(span.step_id, span.name);
  return (
    <Box
      onClick={() => {
        if (!locked) onPick(span.step_id);
      }}
      aria-disabled={locked}
      data-locked={locked ? "true" : "false"}
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 1,
        px: 1.5,
        py: 1,
        cursor: locked ? "not-allowed" : "pointer",
        opacity: locked ? 0.42 : 1,
        borderLeft: "3px solid",
        borderLeftColor: active ? "primary.main" : "transparent",
        bgcolor: active ? "primary.50" : "transparent",
        "&:hover": {
          bgcolor: locked ? "transparent" : active ? "primary.50" : "action.hover",
        },
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
          {locked
            ? "Review earlier steps first"
            : seen
              ? "Checked"
              : span.work_preview?.headline || formatStageLabel(span.step_id)}
        </Typography>
      </Box>
    </Box>
  );
}
