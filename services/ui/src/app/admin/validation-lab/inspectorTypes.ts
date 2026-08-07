/**
 * Validation Lab run inspector types and merge layer.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */

import type { StageProgress } from "./labApi";
import {
  summarizeStageErrors,
  summarizeStageMessages,
} from "./pipelineStageErrors";

export interface LabTraceSpan {
  step_id: string;
  event_type?: string;
  status: string;
  worker_id?: string;
  started_at?: string;
  completed_at?: string;
  attempt?: number;
  input_keys?: string[];
  output_keys?: string[];
  duration_ms?: number;
  subgraph_id?: string;
  errors?: string[];
  warnings?: string[];
  error_summary?: string;
  warning_summary?: string;
  source?: "neo4j" | "sse";
}

export interface LabTraceEvent {
  id: string;
  ts: string;
  type: string;
  payload: Record<string, unknown>;
}

export interface LabPlanStep {
  action_id: string;
  subgraph_id?: string;
  node_type?: string;
  sequence?: number;
  durable_loads?: string[];
  durable_persists?: string[];
}

export interface LabPlanEdge {
  source: string;
  target: string;
  relationship?: string;
}

export interface LabRunInspectorSnapshot {
  lab_run_id: string;
  pipeline_run_id: string;
  lab_status: string;
  pipeline_status: string;
  plan_id: string;
  plan_version_id?: string;
  plan_version_number?: number | null;
  execution_manifest?: Record<string, unknown>;
  plan_steps?: LabPlanStep[];
  plan_edges?: LabPlanEdge[];
  spans: LabTraceSpan[];
  sse_path: string;
}

export interface LabStageDetail {
  step_id: string;
  status: string;
  worker_id?: string;
  started_at?: string;
  completed_at?: string;
  attempt?: number;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  errors?: string[];
  warnings?: string[];
  error_summary?: string;
  warning_summary?: string;
  truncated?: boolean;
}

const DONE = new Set(["completed", "failed", "poisoned", "skipped_persist"]);

/** Rebuild a readable log from persisted Neo4j spans when SSE missed events. */
export function eventsFromSpans(spans: LabTraceSpan[]): LabTraceEvent[] {
  const events: LabTraceEvent[] = [];
  for (const span of spans) {
    if (span.started_at) {
      events.push(
        traceEventFromPayload({
          type: "durable_step_started",
          action_id: span.step_id,
          step_id: span.step_id,
          status: "running",
          worker_id: span.worker_id,
          ts: span.started_at,
        }),
      );
    }
    if (span.completed_at && DONE.has(span.status)) {
      const type =
        span.status === "failed" || span.status === "poisoned"
          ? "durable_step_failed"
          : "durable_step_completed";
      const errors = span.errors || [];
      const warnings = span.warnings || [];
      const errorSummary =
        span.error_summary || summarizeStageErrors(errors) || undefined;
      const warningSummary =
        span.warning_summary || summarizeStageMessages(warnings) || undefined;
      events.push(
        traceEventFromPayload({
          type,
          action_id: span.step_id,
          step_id: span.step_id,
          status: span.status,
          worker_id: span.worker_id,
          duration_ms: span.duration_ms,
          ts: span.completed_at,
          errors: errors.length ? errors : undefined,
          warnings: warnings.length ? warnings : undefined,
          error: errorSummary,
          warning: warningSummary,
        }),
      );
    }
  }
  return events.sort((a, b) => a.ts.localeCompare(b.ts));
}

function eventDedupeKey(ev: LabTraceEvent): string {
  const action = String(ev.payload.action_id || ev.payload.step_id || "");
  return `${ev.type}|${action}|${ev.ts}`;
}

function spanFromStage(row: StageProgress): LabTraceSpan {
  return {
    step_id: row.step_id,
    event_type: row.event_type,
    status: row.status,
    worker_id: row.worker_id,
    started_at: row.started_at,
    completed_at: row.completed_at,
    errors: row.errors,
    warnings: row.warnings,
    error_summary: row.error_summary,
    warning_summary: row.warning_summary,
    source: "neo4j",
  };
}

function spanFromSnapshot(row: LabTraceSpan): LabTraceSpan {
  return { ...row, source: row.source || "neo4j" };
}

function spanFromSse(payload: Record<string, unknown>): LabTraceSpan | null {
  const stepId = String(payload.action_id || payload.step_id || "").trim();
  if (!stepId) return null;
  const eventType = String(payload.type || "");
  let status = String(payload.status || "running");
  if (eventType.endsWith(".failed") || eventType === "durable_step_failed") {
    status = "failed";
  } else if (
    eventType.endsWith(".completed") ||
    eventType === "durable_step_completed"
  ) {
    status = "completed";
  } else if (eventType.endsWith(".started") || eventType.endsWith(".started")) {
    status = "running";
  }
  return {
    step_id: stepId,
    status,
    worker_id: String(payload.worker_id || ""),
    input_keys: Array.isArray(payload.input_keys)
      ? payload.input_keys.map(String)
      : undefined,
    output_keys: Array.isArray(payload.output_keys)
      ? payload.output_keys.map(String)
      : undefined,
    duration_ms:
      typeof payload.duration_ms === "number" ? payload.duration_ms : undefined,
    subgraph_id: String(payload.subgraph_id || ""),
    errors: Array.isArray(payload.errors)
      ? payload.errors.map(String)
      : undefined,
    warnings: Array.isArray(payload.warnings)
      ? payload.warnings.map(String)
      : undefined,
    error_summary:
      typeof payload.error === "string" && payload.error.trim()
        ? payload.error.trim()
        : summarizeStageErrors(
            Array.isArray(payload.errors) ? payload.errors.map(String) : [],
          ) || undefined,
    warning_summary:
      typeof payload.warning === "string" && payload.warning.trim()
        ? payload.warning.trim()
        : summarizeStageMessages(
            Array.isArray(payload.warnings) ? payload.warnings.map(String) : [],
          ) || undefined,
    source: "sse",
  };
}

function mergeSpan(existing: LabTraceSpan, incoming: LabTraceSpan): LabTraceSpan {
  const neo4jWins = existing.source === "neo4j" && DONE.has(existing.status);
  const status =
    neo4jWins && !DONE.has(incoming.status) ? existing.status : incoming.status;
  if (DONE.has(existing.status) && !DONE.has(incoming.status)) {
    return { ...existing, ...incoming, status: existing.status };
  }
  return {
    ...existing,
    ...incoming,
    status,
    started_at: existing.started_at || incoming.started_at,
    completed_at: incoming.completed_at || existing.completed_at,
    worker_id: incoming.worker_id || existing.worker_id,
    input_keys: incoming.input_keys?.length
      ? incoming.input_keys
      : existing.input_keys,
    output_keys: incoming.output_keys?.length
      ? incoming.output_keys
      : existing.output_keys,
    duration_ms: incoming.duration_ms ?? existing.duration_ms,
    subgraph_id: incoming.subgraph_id || existing.subgraph_id,
    errors: incoming.errors?.length ? incoming.errors : existing.errors,
    warnings: incoming.warnings?.length ? incoming.warnings : existing.warnings,
    error_summary: incoming.error_summary || existing.error_summary,
    warning_summary: incoming.warning_summary || existing.warning_summary,
    source: existing.source === "neo4j" ? "neo4j" : incoming.source,
  };
}

export function mergeInspectorState(
  snapshot: LabRunInspectorSnapshot | null,
  events: LabTraceEvent[],
  polledStages: StageProgress[] | undefined,
): { spans: LabTraceSpan[]; events: LabTraceEvent[] } {
  const spanMap = new Map<string, LabTraceSpan>();
  for (const row of snapshot?.spans || []) {
    spanMap.set(row.step_id, spanFromSnapshot(row));
  }
  for (const row of polledStages || []) {
    const current = spanMap.get(row.step_id);
    const next = spanFromStage(row);
    spanMap.set(
      row.step_id,
      current ? mergeSpan(current, next) : next,
    );
  }
  for (const ev of events) {
    const fromSse = spanFromSse(ev.payload);
    if (!fromSse) continue;
    const current = spanMap.get(fromSse.step_id);
    spanMap.set(
      fromSse.step_id,
      current ? mergeSpan(current, fromSse) : fromSse,
    );
  }
  const mergedEvents =
    events.length > 0 ? events : eventsFromSpans(Array.from(spanMap.values()));
  const dedupedEvents: LabTraceEvent[] = [];
  const seen = new Set<string>();
  for (const ev of mergedEvents) {
    const key = eventDedupeKey(ev);
    if (seen.has(key)) continue;
    seen.add(key);
    dedupedEvents.push(ev);
  }
  const spans = Array.from(spanMap.values()).sort((a, b) => {
    const ta = a.started_at || "";
    const tb = b.started_at || "";
    if (ta && tb) return ta.localeCompare(tb);
    return a.step_id.localeCompare(b.step_id);
  });
  return { spans, events: dedupedEvents };
}

export function traceEventFromPayload(payload: Record<string, unknown>): LabTraceEvent {
  const ts = String(payload.ts || new Date().toISOString());
  const type = String(payload.type || "message");
  const action = String(payload.action_id || payload.step_id || "");
  return {
    id: `${type}|${action}|${ts}`,
    ts,
    type,
    payload,
  };
}
