/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import type { ReactNode } from "react";

import type { WorkTask, WorkTaskType } from "./TaskQueueTypes";

const SOURCE_LABELS: Record<WorkTaskType, string> = {
  coding_review: "Code checks",
  safety_net_alert: "Safety alerts",
  gold_label: "Label reviews",
  extraction_quality_pause: "Paused extractions",
  surface_form_approval: "Phrase approvals",
  phrase_publish: "Changes to publish",
};

function severityLabel(severity: number): string {
  if (severity >= 5) return "Urgent";
  if (severity >= 4) return "High";
  if (severity >= 3) return "Medium";
  return "Normal";
}

function severityColour(severity: number): string {
  if (severity >= 5) return "#b91c1c";
  if (severity >= 4) return "#c2410c";
  if (severity >= 3) return "#b45309";
  return "#475569";
}

function ageLabel(age_days: number): string {
  if (age_days <= 0) return "Today";
  if (age_days === 1) return "1 day old";
  return age_days + " days old";
}

export function formatWorkTaskWhen(
  created_at?: string | null,
  age_days = 0,
): string {
  const parsed = Date.parse(created_at || "");
  if (Number.isNaN(parsed)) return ageLabel(age_days);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(parsed));
}

export function canCancelWorkTask(
  task: WorkTask,
  onCancelTask?: (task: WorkTask) => void,
  canCancelTask?: (task: WorkTask) => boolean,
): boolean {
  if (!onCancelTask) return false;
  return canCancelTask ? canCancelTask(task) : true;
}

interface TaskRowProps {
  task: WorkTask;
  transition?: string;
  onSelectTask?: (task: WorkTask) => void;
  onCancelTask?: (task: WorkTask) => void;
  canCancelTask?: (task: WorkTask) => boolean;
  renderExtra?: (task: WorkTask) => ReactNode;
}

function TaskRowLink({
  task,
  transition,
  onSelectTask,
  renderExtra,
}: Omit<TaskRowProps, "onCancelTask" | "canCancelTask">) {
  return (
    <a
      href={task.resolve_url}
      data-testid={"task-queue-row-" + task.task_id}
      data-task-type={task.task_type}
      onClick={(event) => {
        if (!onSelectTask) return;
        event.preventDefault();
        onSelectTask(task);
      }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        flex: 1,
        minWidth: 0,
        padding: "12px 16px",
        textDecoration: "none",
        color: "inherit",
        transition,
      }}
    >
      <span
        aria-label={severityLabel(task.severity)}
        style={{
          display: "inline-block",
          width: 4,
          alignSelf: "stretch",
          borderRadius: 4,
          background: severityColour(task.severity),
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 500,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {task.summary}
        </div>
        <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
          {SOURCE_LABELS[task.task_type]}
          {" - "}
          {formatWorkTaskWhen(task.created_at, task.age_days)}
          {task.patient_id ? " - patient " + task.patient_id : ""}
        </div>
      </div>
      {renderExtra ? (
        <div data-testid="task-queue-row-extra">{renderExtra(task)}</div>
      ) : null}
      <span aria-hidden="true" style={{ fontSize: 14, color: "#64748b" }}>
        &rarr;
      </span>
    </a>
  );
}

export function TaskRow({
  task,
  transition,
  onSelectTask,
  onCancelTask,
  canCancelTask,
  renderExtra,
}: TaskRowProps) {
  const showCancel = canCancelWorkTask(task, onCancelTask, canCancelTask);
  return (
    <li role="listitem">
      <div
        style={{
          display: "flex",
          alignItems: "stretch",
          border: "1px solid rgba(15, 23, 42, 0.10)",
          borderRadius: 10,
          background: "#ffffff",
        }}
      >
        <TaskRowLink
          task={task}
          transition={transition}
          onSelectTask={onSelectTask}
          renderExtra={renderExtra}
        />
        {showCancel ? (
          <button
            type="button"
            data-testid={"task-queue-cancel-" + task.task_id}
            aria-label={"Remove " + task.summary}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onCancelTask?.(task);
            }}
            style={{
              border: "none",
              background: "transparent",
              color: "inherit",
              fontSize: 13,
              fontWeight: 600,
              padding: "0 16px",
              cursor: "pointer",
            }}
          >
            Remove
          </button>
        ) : null}
      </div>
    </li>
  );
}
