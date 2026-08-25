/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import type { WorkTask } from "@leo/design-system";
import ExtractionQualityReviewDialog from "@/components/operations/ExtractionQualityReviewDialog";
import GoldWorkDialog from "./GoldWorkDialog";
import PhrasePublishDialog from "./PhrasePublishDialog";
import SafetyWorkDialog from "./SafetyWorkDialog";
import WorkReviewCardDialog from "./WorkReviewCardDialog";
import { workTaskSourceId } from "./workTaskSourceId";

interface Props {
  task: WorkTask | null;
  onClose: () => void;
  onResolved: () => void;
}

export default function WorkTaskDialog({ task, onClose, onResolved }: Props) {
  if (!task) return null;

  if (task.task_type === "extraction_quality_pause") {
    return (
      <ExtractionQualityReviewDialog
        taskId={workTaskSourceId(task.task_id)}
        open
        onClose={onClose}
        onUnlocked={onResolved}
      />
    );
  }

  if (task.task_type === "coding_review" || task.task_type === "surface_form_approval") {
    return (
      <WorkReviewCardDialog
        task={task}
        onClose={onClose}
        onResolved={onResolved}
      />
    );
  }

  if (task.task_type === "gold_label") {
    return (
      <GoldWorkDialog task={task} onClose={onClose} onResolved={onResolved} />
    );
  }

  if (task.task_type === "safety_net_alert") {
    return (
      <SafetyWorkDialog task={task} onClose={onClose} onResolved={onResolved} />
    );
  }

  if (task.task_type === "phrase_publish") {
    return (
      <PhrasePublishDialog task={task} onClose={onClose} onResolved={onResolved} />
    );
  }

  return null;
}
