/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import type { WorkTask } from "@leo/design-system";
import type { TermSearchResult } from "@/lib/types";
import ReviewCard, {
  buildExplanation,
  buildQuestion,
  type ReviewItem,
} from "@/components/operations/ReviewCard";
import WorkFixPanel from "./WorkFixPanel";
import { workJson } from "./workJson";
import { workTaskSourceId } from "./workTaskSourceId";

interface CodingGroup {
  entity_text: string;
  entity_label: string;
  review_count: number;
  best_score: number | null;
  sample_review_id: string;
  any_uncoded: boolean;
  suggested_semantic_tag: string | null;
  sample_encounter_text: string | null;
  decision_tier: number | null;
  tier_reason: string | null;
  tier_decision: string | null;
  suggested_label: string | null;
  tag_mismatch_delta: number | null;
}

interface SurfaceFormTask {
  task_id: string;
  entity_text: string;
  current_concept: string;
  current_term: string;
  suggested_concept: string;
  suggested_term: string;
  confidence: number;
  source?: string;
}

interface Props {
  task: WorkTask;
  onClose: () => void;
  onResolved: () => void;
}

function codingGroupToItem(group: CodingGroup): ReviewItem {
  const item: ReviewItem = {
    id: "coding:" + group.entity_text,
    kind: "coding",
    entityText: group.entity_text,
    entityLabel: group.entity_label,
    count: group.review_count,
    confidence: group.best_score,
    uncoded: group.any_uncoded,
    question: "",
    explanation: "",
    suggestedSemanticTag: group.suggested_semantic_tag ?? undefined,
    sampleEncounterText: group.sample_encounter_text ?? undefined,
    decisionTier: (group.decision_tier as 1 | 2 | 3 | null) ?? null,
    tierReason: group.tier_reason ?? null,
    tierDecision: group.tier_decision ?? null,
    suggestedLabel: group.suggested_label ?? undefined,
    tagMismatchDelta: group.tag_mismatch_delta ?? undefined,
  };
  item.question = buildQuestion(item);
  item.explanation = buildExplanation(item);
  return item;
}

function surfaceTaskToItem(row: SurfaceFormTask): ReviewItem {
  const item: ReviewItem = {
    id: "surface_form:" + row.task_id,
    kind: "coding",
    entityText: row.entity_text,
    entityLabel: "surface_form",
    count: 1,
    confidence: row.confidence ?? null,
    uncoded: false,
    question: 'Check this code mapping for "' + row.entity_text + '"',
    explanation:
      "Current: " +
      (row.current_term || row.current_concept || "none") +
      "\nSuggested: " +
      (row.suggested_term || row.suggested_concept || "none"),
    suggestedConceptId: row.suggested_concept || undefined,
    suggestedConceptTerm: row.suggested_term || undefined,
  };
  return item;
}

async function loadReviewItem(task: WorkTask): Promise<ReviewItem> {
  const sourceId = workTaskSourceId(task.task_id);
  if (task.task_type === "surface_form_approval") {
    const payload = await workJson<{ items: SurfaceFormTask[] }>(
      "/api/training/surface-form-tasks?page=1&page_size=50&status=pending",
    );
    const row = payload.items.find((item) => item.task_id === sourceId);
    if (!row) throw new Error("missing");
    return surfaceTaskToItem(row);
  }
  const payload = await workJson<{ groups: CodingGroup[] }>(
    "/api/training/coding-review/grouped?page=1&page_size=200",
  );
  const group = payload.groups.find((row) => row.sample_review_id === sourceId);
  if (!group) throw new Error("missing");
  return codingGroupToItem(group);
}

export default function WorkReviewCardDialog({
  task,
  onClose,
  onResolved,
}: Props) {
  const [item, setItem] = useState<ReviewItem | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setItem(null);
    loadReviewItem(task)
      .then((next) => {
        if (!cancelled) setItem(next);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this task. Try again.");
      });
    return () => {
      cancelled = true;
    };
  }, [task]);

  const resolveCoding = useCallback(
    async (current: ReviewItem, result: TermSearchResult) => {
      setBusy(true);
      try {
        if (current.id.startsWith("surface_form:")) {
          const taskId = current.id.replace("surface_form:", "");
          await workJson("/api/training/surface-form-tasks/" + taskId + "/resolve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              status: "approved",
              resolved_concept: result.snomed_concept_id,
              resolved_by: "work_ui",
            }),
          });
          onResolved();
          return;
        }
        await workJson("/api/training/coding-review/batch-resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            entity_text: current.entityText,
            entity_label: current.entityLabel,
            resolved_concept_id: result.snomed_concept_id,
            resolved_term: result.term,
            reviewer: "work_ui",
            resolved_assertion: current.assertion ?? "present",
          }),
        });
        onResolved();
      } catch {
        setError("Could not save. Please try again.");
      } finally {
        setBusy(false);
      }
    },
    [onResolved],
  );

  return (
    <Dialog
      open
      onClose={onClose}
      fullWidth
      maxWidth="md"
      data-testid="work-task-dialog"
    >
      <DialogTitle sx={{ pr: 6 }}>
        {task.summary}
        <IconButton
          aria-label="Close"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        ) : null}
        {!item && !error ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress size={28} aria-label="Loading" />
          </Box>
        ) : null}
        {item ? (
          <>
            <ReviewCard
              item={item}
              onResolveCoding={resolveCoding}
              onResolveHitl={() => undefined}
              onSkip={onClose}
              onAllCasesResolved={onResolved}
              busy={busy}
              onAcceptSuggestion={
                item.suggestedConceptId
                  ? (current) =>
                      void resolveCoding(current, {
                        snomed_concept_id: current.suggestedConceptId ?? "",
                        term: current.suggestedConceptTerm ?? "",
                      })
                  : undefined
              }
            />
            <WorkFixPanel
              entityText={item.entityText}
              entityLabel={item.entityLabel}
              reviewId={
                task.task_type === "coding_review"
                  ? workTaskSourceId(task.task_id)
                  : null
              }
              encounterText={item.sampleEncounterText}
            />
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
