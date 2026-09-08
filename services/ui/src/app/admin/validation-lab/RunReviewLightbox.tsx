/**
 * Clinical Validation Lab run review. Letter in the centre. Rewind four phases.
 *
 * Atlas: DI-49BA8E04 / DI-C953EF73 / DO-4FD76836 / VT-592D30E9
 */
"use client";

import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import {
  useLabRunInspector,
  useLabRunStagePoll,
} from "@/hooks/useLabRunInspector";
import { DecideSbar } from "./DecideSbar";
import { FactTree } from "./FactTree";
import type { LabWorkPreview } from "./inspectorTypes";
import LetterPane from "./LetterPane";
import { PhaseRail } from "./PhaseRail";
import { useClinicalReview } from "./useClinicalReview";

export interface RunReviewTarget {
  title: string;
  caseId?: string;
  labRunId?: string;
  pipelineRunId?: string;
  referralText?: string;
  whyOpened?: string;
  gpNote?: string;
  pmhText?: string;
  status: string;
  terminal: boolean;
  readOnly?: boolean;
  previousPreviews?: Record<string, LabWorkPreview>;
  assessmentCaseId?: string;
}

interface Props {
  target: RunReviewTarget | null;
  onClose: () => void;
  onRetest?: (previews: Record<string, LabWorkPreview>) => void;
  onSavedGold?: () => void;
  onBuildTwin?: (phrases: string[]) => void;
}

export default function RunReviewLightbox({ target, onClose }: Props) {
  if (!target) return null;
  return <ReviewBody target={target} onClose={onClose} />;
}

function ReviewBody({
  target,
  onClose,
}: {
  target: RunReviewTarget;
  onClose: () => void;
}) {
  const caseId = target.caseId || "";
  const labRunId = target.labRunId || "";
  const inspector = useRunInspector(target);
  const review = useClinicalReview(inspector);

  return (
    <Dialog
      open
      onClose={onClose}
      fullWidth
      maxWidth={false}
      data-testid="validation-lab-run-review"
      PaperProps={{
        sx: {
          width: "min(1600px, 100%)",
          height: "min(920px, calc(100vh - 32px))",
          maxWidth: "none",
          m: 2,
        },
      }}
    >
      <Stack sx={{ height: "100%", minHeight: 0 }}>
        <ReviewHeader title={target.title} status={target.status} onClose={onClose} />
        <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
          <PhaseRail selected={review.selectedPhase} onSelect={review.onSelectPhase} />
          <LetterPane
            referralText={
              target.referralText || inspector.snapshot?.source_text || ""
            }
            openedBecause={target.whyOpened}
            highlights={review.highlights}
            focusTerm={review.focusTerm}
            onMarkClick={review.onMarkClick}
          />
          <ReviewSide caseId={caseId} runId={labRunId} review={review} />
        </Box>
      </Stack>
    </Dialog>
  );
}

function useRunInspector(target: RunReviewTarget) {
  const caseId = target.caseId || "";
  const labRunId = target.labRunId || "";
  const pipelineRunId = target.pipelineRunId || "";
  const polledStages = useLabRunStagePoll(
    caseId,
    labRunId,
    Boolean(labRunId && caseId),
    target.terminal,
  );
  return useLabRunInspector({
    caseId,
    runId: labRunId,
    pipelineRunId,
    enabled: Boolean(labRunId || pipelineRunId),
    pollStages: polledStages,
    terminal: target.terminal,
  });
}

function ReviewSide({
  caseId,
  runId,
  review,
}: {
  caseId: string;
  runId: string;
  review: ReturnType<typeof useClinicalReview>;
}) {
  return (
    <Box
      sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}
    >
      {review.selectedPhase === "decide" ? (
        <DecideSbar caseId={caseId} runId={runId} />
      ) : (
        <FactTree
          groups={review.tree}
          openAssertion={review.openAssertion}
          openTag={review.openTag}
          selectedText={review.focusTerm}
          onToggleAssertion={review.onToggleAssertion}
          onToggleTag={review.onToggleTag}
          onSelectLeaf={review.onSelectLeaf}
        />
      )}
    </Box>
  );
}

function ReviewHeader({
  title,
  status,
  onClose,
}: {
  title: string;
  status: string;
  onClose: () => void;
}) {
  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={1}
      sx={{ px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}
    >
      <Box sx={{ flex: 1 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          {title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {status}
        </Typography>
      </Box>
      <IconButton onClick={onClose} aria-label="Close review">
        <CloseIcon />
      </IconButton>
    </Stack>
  );
}
