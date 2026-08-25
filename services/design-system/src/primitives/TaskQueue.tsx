/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useMemo } from "react";

import { useMotion } from "../motion";
import { TaskRow } from "./TaskQueueRow";
import type {
  CountsBySource,
  TaskQueueProps,
  WorkTask,
  WorkTaskType,
} from "./TaskQueueTypes";

export type {
  CountsBySource,
  TaskQueueProps,
  WorkTask,
  WorkTaskType,
} from "./TaskQueueTypes";

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

function sortTasks(tasks: ReadonlyArray<WorkTask>): WorkTask[] {
  return [...tasks].sort((a, b) => {
    if (b.severity !== a.severity) return b.severity - a.severity;
    if (b.age_days !== a.age_days) return b.age_days - a.age_days;
    return a.task_id.localeCompare(b.task_id);
  });
}

function SourceCounts({
  countsBySource,
  activeSources,
  onToggleSource,
  transition,
}: {
  countsBySource: CountsBySource;
  activeSources?: ReadonlyArray<WorkTaskType>;
  onToggleSource?: (source: WorkTaskType) => void;
  transition?: string;
}) {
  return (
    <div
      role="region"
      aria-label="Open work by source"
      data-testid="task-queue-counts"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
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
              background: active ? "rgba(15, 23, 42, 0.04)" : "transparent",
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
  );
}

export function TaskQueue({
  tasks,
  countsBySource,
  activeSources,
  onToggleSource,
  onSelectTask,
  onCancelTask,
  canCancelTask,
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
      <SourceCounts
        countsBySource={countsBySource}
        activeSources={activeSources}
        onToggleSource={onToggleSource}
        transition={transition}
      />
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
            <TaskRow
              key={task.task_id}
              task={task}
              transition={transition}
              onSelectTask={onSelectTask}
              onCancelTask={onCancelTask}
              canCancelTask={canCancelTask}
              renderExtra={renderExtra}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
