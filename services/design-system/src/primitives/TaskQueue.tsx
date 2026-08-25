/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useMemo, type ReactNode } from "react";

import { useMotion } from "../motion";

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
  emptyMessage?: string;
  renderExtra?: (task: WorkTask) => ReactNode;
}

const SOURCE_LABELS: Record<WorkTaskType, string> = {
  coding_review: "Code checks",
  safety_net_alert: "Safety alerts",
  gold_label: "Label reviews",
  extraction_quality_pause: "Paused extractions",
  surface_form_approval: "Phrase approvals",
  phrase_publish: "Changes to publish",
};

const SOURCE_ORDER: ReadonlyArray<WorkTaskType> = [
  "safety_net_alert",
  "phrase_publish",
  "extraction_quality_pause",
  "coding_review",
  "surface_form_approval",
  "gold_label",
];

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

function sortTasks(tasks: ReadonlyArray<WorkTask>): WorkTask[] {
  return [...tasks].sort((a, b) => {
    if (b.severity !== a.severity) return b.severity - a.severity;
    if (b.age_days !== a.age_days) return b.age_days - a.age_days;
    return a.task_id.localeCompare(b.task_id);
  });
}

export function TaskQueue({
  tasks,
  countsBySource,
  activeSources,
  onToggleSource,
  onSelectTask,
  emptyMessage = "No open tasks. Great work.",
  renderExtra,
}: TaskQueueProps) {
  const { reducedMotion } = useMotion();
  const sortedTasks = useMemo(() => sortTasks(tasks), [tasks]);
  const transition = reducedMotion
    ? undefined
    : "background-color 140ms ease-out, transform 140ms ease-out";

  return (
    <div data-testid="task-queue" style={{ width: "100%" }}>
      <div
        role="region"
        aria-label="Open work by source"
        data-testid="task-queue-counts"
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 12,
          marginBottom: 16,
        }}
      >
        {SOURCE_ORDER.map((source) => {
          const active =
            !activeSources ||
            activeSources.length === 0 ||
            activeSources.includes(source);
          return (
            <button
              key={source}
              type="button"
              onClick={() => onToggleSource?.(source)}
              aria-pressed={active}
              data-testid={"task-queue-count-" + source}
              style={{
                textAlign: "left",
                padding: "12px 14px",
                border: "1px solid rgba(15, 23, 42, 0.12)",
                borderRadius: 10,
                background: active
                  ? "rgba(15, 23, 42, 0.04)"
                  : "transparent",
                cursor: onToggleSource ? "pointer" : "default",
                transition,
              }}
            >
              <div style={{ fontSize: 12, color: "#64748b" }}>
                {SOURCE_LABELS[source]}
              </div>
              <div style={{ fontSize: 24, fontWeight: 600 }}>
                {countsBySource[source] ?? 0}
              </div>
            </button>
          );
        })}
      </div>

      {sortedTasks.length === 0 ? (
        <p
          data-testid="task-queue-empty"
          style={{
            margin: 0,
            padding: 16,
            background: "rgba(15, 23, 42, 0.03)",
            borderRadius: 10,
            color: "#475569",
            fontSize: 14,
          }}
        >
          {emptyMessage}
        </p>
      ) : (
        <ol
          role="list"
          data-testid="task-queue-list"
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {sortedTasks.map((task) => (
            <li key={task.task_id} role="listitem">
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
                  padding: "12px 16px",
                  border: "1px solid rgba(15, 23, 42, 0.10)",
                  borderRadius: 10,
                  textDecoration: "none",
                  color: "inherit",
                  background: "#ffffff",
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
                  <div
                    style={{
                      fontSize: 12,
                      color: "#64748b",
                      marginTop: 2,
                    }}
                  >
                    {SOURCE_LABELS[task.task_type]}
                    {" - "}
                    {ageLabel(task.age_days)}
                    {task.patient_id ? " - patient " + task.patient_id : ""}
                  </div>
                </div>
                {renderExtra ? (
                  <div data-testid="task-queue-row-extra">
                    {renderExtra(task)}
                  </div>
                ) : null}
                <span
                  aria-hidden="true"
                  style={{ fontSize: 14, color: "#64748b" }}
                >
                  &rarr;
                </span>
              </a>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
