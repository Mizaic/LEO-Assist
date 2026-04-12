"use client";

import { useCallback, useState } from "react";
import {
  batchResetAndRecodeEncounters,
  fetchEncounterList,
  type EncounterListItem,
  type EncounterListResponse,
} from "@/lib/missionControlApi";

type JobState = "queued" | "running" | "completed" | "failed";

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
    const mark = (state: JobState) =>
      setStatuses((prev) => ({ ...prev, [encounterId]: state }));
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
          mark("completed");
          source.close();
        }
        if (["pipeline_error", "run_error", "encounter_error"].includes(type)) {
          mark("failed");
          source.close();
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
    source.onerror = () => { mark("failed"); source.close(); };
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
    const initial: Record<string, JobState> = {};
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
          initial[job.encounter_id] = "queued";
          subscribeToRun(job.run_id, job.encounter_id);
        });
        result.failed.forEach((job) => { initial[job.encounter_id] = "failed"; });
      }
      setStatuses(initial);
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
