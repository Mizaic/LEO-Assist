/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
import type { ReactNode } from "react";

export type WorkTaskType =
  | "coding_review"
  | "safety_net_alert"
  | "gold_label"
  | "extraction_quality_pause"
  | "surface_form_approval"
  | "phrase_publish";

export interface WorkTask {
  task_id: string;
  task_type: WorkTaskType;
  severity: number;
  summary: string;
  age_days: number;
  created_at?: string | null;
  resolve_url: string;
  patient_id?: string | null;
  episode_id?: string | null;
  failure_kind?: string;
  draft_author?: string;
  draft_action?: string;
}

export interface CountsBySource {
  coding_review: number;
  safety_net_alert: number;
  gold_label: number;
  extraction_quality_pause: number;
  surface_form_approval: number;
  phrase_publish: number;
}

export interface TaskQueueProps {
  tasks: ReadonlyArray<WorkTask>;
  countsBySource: CountsBySource;
  activeSources?: ReadonlyArray<WorkTaskType>;
  onToggleSource?: (source: WorkTaskType) => void;
  onSelectTask?: (task: WorkTask) => void;
  onCancelTask?: (task: WorkTask) => void;
  canCancelTask?: (task: WorkTask) => boolean;
  emptyMessage?: string;
  renderExtra?: (task: WorkTask) => ReactNode;
}
