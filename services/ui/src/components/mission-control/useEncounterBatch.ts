/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

import { useCallback, useRef, useState } from "react";
import {
  batchResetAndRecodeEncounters,
  fetchEncounterList,
  type EncounterListItem,
  type EncounterListResponse,
} from "@/lib/missionControlApi";

type JobState = "queued" | "running" | "completed" | "failed";

const JOB_STATE_RANK: Record<JobState, number> = {
  queued: 1,
  running: 2,
  completed: 3,
  failed: 3,
};

// Browsers allow ~6 concurrent HTTP/1.1 connections per origin.
// SSE streams count against this limit for the lifetime of the batch run.
// Above this threshold we skip SSE entirely and use shared polling instead.
const SSE_CONNECTION_LIMIT = 6;

const SHARED_POLL_INTERVAL_MS = 2500;

interface BuildParams {
  (page: number, pageSize: number): Parameters<typeof fetchEncounterList>[0];
}

interface UseBatchOptions {
  triggerAnalysis: boolean;
  queryDiagnostics: EncounterListResponse["query_diagnostics"];
  buildSearchParams: BuildParams;
}

interface RunEntry {
  runId: string;
  encounterId: string;
}

// -- Shared-poll strategy (large batches) ---------------------------------

async function fetchBatchStatuses(
  runIds: string[]
): Promise<Array<{ run_id: string; state: string }>> {
  try {
    const res = await fetch(`${window.location.origin}/api/pipeline/progress-status/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_ids: runIds }),
    });
    if (!res.ok) return [];
    return (await res.json()) as Array<{ run_id: string; state: string }>;
  } catch {
    return [];
  }
}

function resolveJobState(raw: string): JobState | null {
  if (raw === "running") return "running";
  if (raw === "completed") return "completed";
  if (raw === "failed") return "failed";
  if (raw === "queued") return "queued";
  return null;
}

// -- Per-encounter SSE strategy (small batches) ---------------------------

function subscribeToRunViaSse(
  runId: string,
  encounterId: string,
  onState: (encounterId: string, state: JobState) => void
): () => void {
  const source = new EventSource(
    `${window.location.origin}/api/pipeline/progress/${encodeURIComponent(runId)}`
  );
  let terminal = false;

  const mark = (state: JobState) => onState(encounterId, state);

  const finish = (state: JobState) => {
    terminal = true;
    mark(state);
    source.close();
    window.clearInterval(pollTimer);
  };

  const pollLastStatus = async () => {
    if (terminal) return;
    try {
      const response = await fetch(
        `/api/pipeline/progress-status/${encodeURIComponent(runId)}`
      );
      if (!response.ok) return;
      const payload = (await response.json()) as { state?: string };
      const state = payload.state;
      if (state === "running") mark("running");
      else if (state === "completed") finish("completed");
      else if (state === "failed") finish("failed");
    } catch { /* Keep waiting. */ }
  };

  const pollTimer = window.setInterval(() => { void pollLastStatus(); }, 2500);

  const onEvent = (ev: MessageEvent) => {
    try {
      const payload = JSON.parse(ev.data) as { type?: string };
      const type = payload.type ?? "";
      if (
        ["run_started", "patient_started", "encounter_started", "step_completed", "step_done"]
          .includes(type)
      ) {
        mark("running");
      }
      if (
        ["run_completed", "encounter_completed", "pipeline_done", "extraction_done"]
          .includes(type)
      ) {
        finish("completed");
      }
      if (["pipeline_error", "run_error", "encounter_error"].includes(type)) {
        finish("failed");
      }
    } catch { /* Ignore malformed SSE events. */ }
  };

  [
    "run_started", "patient_started", "encounter_started", "step_completed", "step_done",
    "run_completed", "encounter_completed", "pipeline_done", "extraction_done",
    "pipeline_error", "run_error", "encounter_error",
  ].forEach((ev) => source.addEventListener(ev, onEvent as EventListener));

  source.onerror = () => { if (!terminal) void pollLastStatus(); };
  void pollLastStatus();

  return () => {
    terminal = true;
    source.close();
    window.clearInterval(pollTimer);
  };
}

// -- Hook -----------------------------------------------------------------

export function useEncounterBatch({
  triggerAnalysis,
  queryDiagnostics,
  buildSearchParams,
}: UseBatchOptions) {
  const [statuses, setStatuses] = useState<Record<string, JobState>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Shared-poll bookkeeping: map of runId -> encounterId for pending jobs.
  const pendingRunsRef = useRef<Map<string, string>>(new Map());
  // Browser timers are numeric IDs; avoid NodeJS.Timeout vs number mismatch under @types/node.
  const sharedPollTimerRef = useRef<number | null>(null);
  // Cleanup callbacks for SSE subscriptions (small-batch path).
  const sseCleanupRef = useRef<Array<() => void>>([]);

  const applyStateTransition = useCallback(
    (encounterId: string, next: JobState) => {
      setStatuses((prev) => {
        const current = prev[encounterId];
        if (current && JOB_STATE_RANK[current] > JOB_STATE_RANK[next]) return prev;
        if (
          current === next ||
          (current === "completed" && next === "failed") ||
          (current === "failed" && next === "completed")
        ) {
          return prev;
        }
        return { ...prev, [encounterId]: next };
      });
    },
    []
  );

  const stopSharedPoll = useCallback(() => {
    if (sharedPollTimerRef.current !== null) {
      window.clearInterval(sharedPollTimerRef.current);
      sharedPollTimerRef.current = null;
    }
    pendingRunsRef.current.clear();
  }, []);

  const stopSseSubscriptions = useCallback(() => {
    sseCleanupRef.current.forEach((cleanup) => cleanup());
    sseCleanupRef.current = [];
  }, []);

  const runSharedPollTick = useCallback(async () => {
    const pending = pendingRunsRef.current;
    if (pending.size === 0) {
      stopSharedPoll();
      return;
    }
    const runIds = Array.from(pending.keys());
    const results = await fetchBatchStatuses(runIds);
    for (const { run_id, state } of results) {
      const encounterId = pending.get(run_id);
      if (!encounterId) continue;
      const resolved = resolveJobState(state);
      if (!resolved) continue;
      applyStateTransition(encounterId, resolved);
      if (resolved === "completed" || resolved === "failed") {
        pending.delete(run_id);
      }
    }
    if (pending.size === 0) stopSharedPoll();
  }, [applyStateTransition, stopSharedPoll]);

  const startSharedPoll = useCallback(
    (runs: RunEntry[]) => {
      stopSharedPoll();
      for (const { runId, encounterId } of runs) {
        pendingRunsRef.current.set(runId, encounterId);
      }
      sharedPollTimerRef.current = window.setInterval(() => {
        void runSharedPollTick();
      }, SHARED_POLL_INTERVAL_MS);
      // Fire one tick immediately to pick up any already-completed jobs.
      void runSharedPollTick();
    },
    [stopSharedPoll, runSharedPollTick]
  );

  const runBatchForItems = useCallback(
    async (
      items: Array<Pick<EncounterListItem, "patient_id" | "encounter_id">>,
      label: "selected" | "all"
    ) => {
      if (!items.length) {
        setMessage(
          label === "all"
            ? "No encounters available for this search."
            : "Select at least one encounter first."
        );
        return;
      }
      setMessage(null);
      setStatuses({});
      stopSharedPoll();
      stopSseSubscriptions();

      const useSse = items.length <= SSE_CONNECTION_LIMIT;
      let queued = 0;
      let failed = 0;
      const pendingRuns: RunEntry[] = [];

      try {
        for (let i = 0; i < items.length; i += 500) {
          const chunk = items.slice(i, i + 500);
          const result = await batchResetAndRecodeEncounters(
            chunk.map(({ patient_id, encounter_id }) => ({ patient_id, encounter_id })),
            triggerAnalysis,
            queryDiagnostics
          );
          queued += result.queued_count;
          failed += result.failed_count;

          result.queued.forEach((job) => {
            setStatuses((prev) => {
              const current = prev[job.encounter_id];
              if (current === "running" || current === "completed") return prev;
              return { ...prev, [job.encounter_id]: "queued" };
            });
            pendingRuns.push({ runId: job.run_id, encounterId: job.encounter_id });
          });
          result.failed.forEach((job) => {
            setStatuses((prev) => ({ ...prev, [job.encounter_id]: "failed" }));
          });
        }

        if (useSse) {
          // Small batch: one SSE stream per encounter is within browser limits.
          for (const { runId, encounterId } of pendingRuns) {
            const cleanup = subscribeToRunViaSse(runId, encounterId, applyStateTransition);
            sseCleanupRef.current.push(cleanup);
          }
        } else {
          // Large batch: single shared poll to avoid exhausting browser connections.
          startSharedPoll(pendingRuns);
        }

        setMessage(`Batch queued (${label}): ${queued} queued, ${failed} failed.`);
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Batch reset and recode failed.");
      }
    },
    [
      triggerAnalysis,
      queryDiagnostics,
      applyStateTransition,
      startSharedPoll,
      stopSharedPoll,
      stopSseSubscriptions,
    ]
  );

  const fetchAllSearchRows = useCallback(async (): Promise<EncounterListItem[]> => {
    const pageSize = 100;
    let page = 1;
    let total = 0;
    const all: EncounterListItem[] = [];
    do {
      const response = await fetchEncounterList(buildSearchParams(page, pageSize));
      total = response.total;
      all.push(...response.items);
      if (!response.items.length || page > 100) break;
      page += 1;
    } while (all.length < total);
    return all;
  }, [buildSearchParams]);

  const runBatchAll = useCallback(
    async (totalResults: number) => {
      if (!totalResults) {
        setMessage("Search first to load encounter results.");
        return;
      }
      setLoading(true);
      try {
        const allRows = await fetchAllSearchRows();
        await runBatchForItems(
          allRows.map(({ patient_id, encounter_id }) => ({ patient_id, encounter_id })),
          "all"
        );
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Could not queue all results.");
      } finally {
        setLoading(false);
      }
    },
    [fetchAllSearchRows, runBatchForItems]
  );

  return { statuses, message, loading, runBatchForItems, runBatchAll };
}
