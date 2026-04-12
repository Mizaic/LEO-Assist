"use client";

import { useCallback, useState } from "react";
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

interface BuildParams {
  (page: number, pageSize: number): Parameters<typeof fetchEncounterList>[0];
}

interface UseBatchOptions {
  triggerAnalysis: boolean;
  queryDiagnostics: EncounterListResponse["query_diagnostics"];
  buildSearchParams: BuildParams;
}

export function useEncounterBatch({
  triggerAnalysis,
  queryDiagnostics,
  buildSearchParams,
}: UseBatchOptions) {
  const [statuses, setStatuses] = useState<Record<string, JobState>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const subscribeToRun = useCallback((runId: string, encounterId: string) => {
    const source = new EventSource(
      `${window.location.origin}/api/pipeline/progress/${encodeURIComponent(runId)}`
    );
    let terminal = false;
    const mark = (state: JobState) =>
      setStatuses((prev) => {
        const current = prev[encounterId];
        if (current && JOB_STATE_RANK[current] > JOB_STATE_RANK[state]) {
          return prev;
        }
        if (current && JOB_STATE_RANK[current] === JOB_STATE_RANK[state]) {
          if (current === "completed" && state === "failed") {
            return prev;
          }
          if (current === "failed" && state === "completed") {
            return prev;
          }
        }
        return { ...prev, [encounterId]: state };
      });
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
        if (state === "running") {
          mark("running");
        } else if (state === "completed") {
          finish("completed");
        } else if (state === "failed") {
          finish("failed");
        }
      } catch {
        // Keep waiting for next poll/SSE event.
      }
    };
    const pollTimer = window.setInterval(() => {
      void pollLastStatus();
    }, 2500);
    const onEvent = (ev: MessageEvent) => {
      try {
        const payload = JSON.parse(ev.data) as { type?: string };
        const type = payload.type ?? "";
        if (
          [
            "run_started",
            "patient_started",
            "encounter_started",
            "step_completed",
            "step_done",
          ].includes(type)
        ) {
          mark("running");
        }
        if (
          [
            "run_completed",
            "encounter_completed",
            "pipeline_done",
            "extraction_done",
          ].includes(type)
        ) {
          finish("completed");
        }
        if (["pipeline_error", "run_error", "encounter_error"].includes(type)) {
          finish("failed");
        }
      } catch { /* Ignore malformed SSE events. */ }
    };
    [
      "run_started",
      "patient_started",
      "encounter_started",
      "step_completed",
      "step_done",
      "run_completed",
      "encounter_completed",
      "pipeline_done",
      "extraction_done",
      "pipeline_error",
      "run_error",
      "encounter_error",
    ]
      .forEach((ev) => source.addEventListener(ev, onEvent as EventListener));
    source.onerror = () => {
      if (!terminal) {
        void pollLastStatus();
      }
    };
    void pollLastStatus();
  }, []);

  const runBatchForItems = useCallback(async (
    items: Array<Pick<EncounterListItem, "patient_id" | "encounter_id">>,
    label: "selected" | "all"
  ) => {
    if (!items.length) {
      setMessage(label === "all" ? "No encounters available for this search." : "Select at least one encounter first.");
      return;
    }
    setMessage(null);
    setStatuses({});
    let queued = 0;
    let failed = 0;
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
            if (current === "running" || current === "completed") {
              return prev;
            }
            return { ...prev, [job.encounter_id]: "queued" };
          });
          subscribeToRun(job.run_id, job.encounter_id);
        });
        result.failed.forEach((job) => {
          setStatuses((prev) => ({ ...prev, [job.encounter_id]: "failed" }));
        });
      }
      setMessage(`Batch queued (${label}): ${queued} queued, ${failed} failed.`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Batch reset and recode failed.");
    }
  }, [triggerAnalysis, queryDiagnostics, subscribeToRun]);

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

  const runBatchAll = useCallback(async (totalResults: number) => {
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
  }, [fetchAllSearchRows, runBatchForItems]);

  return { statuses, message, loading, runBatchForItems, runBatchAll };
}
