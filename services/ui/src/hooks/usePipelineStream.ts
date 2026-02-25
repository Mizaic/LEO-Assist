"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PipelineRunResponse } from "@/lib/types";

export interface PipelineStreamParams {
  patientIds: string[];
  maxEncountersPerPatient?: number;
  dryRun?: boolean;
  workers?: number;
  unprocessedOnly?: boolean;
}

export interface WorkerState {
  workerId: number;
  step: string;
  encounterId: string;
  statusText: string;
  completedCount: number;
}

export interface PipelineStreamState {
  running: boolean;
  status: string | null;
  live: PipelineRunResponse | null;
  result: PipelineRunResponse | null;
  error: string | null;
  workerStates: Record<number, WorkerState>;
}

export interface UsePipelineStreamReturn extends PipelineStreamState {
  start: (params: PipelineStreamParams) => void;
  cancel: () => void;
}

const API_BASE =
  typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE
    ? process.env.NEXT_PUBLIC_API_BASE
    : "http://localhost:8000";

const EMPTY_LIVE: PipelineRunResponse = {
  run_id: "starting",
  processed_encounters: 0,
  queued_for_review: 0,
  rejected_hard_fail: 0,
  warnings_only: 0,
};

type Setter<T> = React.Dispatch<React.SetStateAction<T>>;

function updateWorker(
  setWorkerStates: Setter<Record<number, WorkerState>>,
  d: Record<string, any>,
  stepKey: string,
  statusText: string,
) {
  const wid = d.worker_id ?? 0;
  setWorkerStates((prev) => {
    const prev_ws = prev[wid];
    const justFinished = stepKey === "done" && prev_ws?.step !== "done";
    return {
      ...prev,
      [wid]: {
        workerId: wid,
        step: stepKey,
        encounterId: d.encounter_id ?? prev_ws?.encounterId ?? "",
        statusText,
        completedCount: (prev_ws?.completedCount ?? 0) + (justFinished ? 1 : 0),
      },
    };
  });
}

function attachListeners(
  source: EventSource,
  setStatus: Setter<string | null>,
  setLive: Setter<PipelineRunResponse | null>,
  setResult: Setter<PipelineRunResponse | null>,
  setRunning: Setter<boolean>,
  setError: Setter<string | null>,
  setWorkerStates: Setter<Record<number, WorkerState>>,
  finished: React.MutableRefObject<boolean>,
  esRef: React.MutableRefObject<EventSource | null>,
) {
  const on = (name: string, fn: (d: any) => void) =>
    source.addEventListener(name, (e) => fn(JSON.parse((e as MessageEvent).data)));

  on("run_started", (d) => setStatus(`Run started (${d.run_id ?? "?"})`));

  on("patient_started", (d) =>
    setStatus(`Patient ${d.patient_id ?? "?"}: ${d.encounter_count ?? 0} encounters`),
  );

  on("encounter_started", (d) => {
    const wk = d.worker_id ? ` [W${d.worker_id}]` : "";
    setStatus(`${wk} Processing ${d.encounter_id ?? "encounter"}…`);
    updateWorker(setWorkerStates, d, "load", "Loading…");
  });

  on("encounter_loaded", (d) => {
    setStatus(`Loaded encounter ${d.encounter_id ?? "?"}`);
    updateWorker(setWorkerStates, d, "load", "Loaded");
  });

  on("deidentify_started", (d) => {
    setStatus("De-identifying…");
    updateWorker(setWorkerStates, d, "deid", "De-identifying…");
  });

  on("deidentify_completed", (d) => {
    setStatus(`De-id complete (${d.output_chars ?? 0} chars)`);
    updateWorker(setWorkerStates, d, "deid", "De-id done");
  });

  on("sentence_split_started", (d) => {
    setStatus("Splitting sentences…");
    updateWorker(setWorkerStates, d, "split", "Splitting…");
  });

  on("sentence_split_completed", (d) => {
    setStatus(`${d.sentence_count ?? 0} sentences`);
    updateWorker(setWorkerStates, d, "split", `${d.sentence_count ?? 0} sents`);
  });

  on("term_extraction_started", (d) => {
    setStatus("Extracting terms…");
    updateWorker(setWorkerStates, d, "extract", "Extracting…");
  });

  on("term_extraction_completed", (d) => {
    const tokens = d.llm_usage?.total_tokens ?? 0;
    const cost = d.llm_usage?.cost_usd;
    const costStr = cost != null ? ` ($${cost.toFixed(4)})` : "";
    setStatus(`Extracted ${d.term_count ?? 0} terms (${tokens} tokens${costStr})`);
    updateWorker(setWorkerStates, d, "extract", `${d.term_count ?? 0} terms`);
  });

  on("term_extraction_failed", (d) => {
    setStatus(`Extraction failed: ${d.error ?? "unknown"}`);
    updateWorker(setWorkerStates, d, "extract", "FAILED");
  });

  on("coding_resolve_completed", (d) => {
    setStatus(`Resolved ${d.resolution_count ?? 0} codings`);
    updateWorker(setWorkerStates, d, "code", `${d.resolution_count ?? 0} codes`);
  });

  on("validation_started", (d) => {
    setStatus("Validating…");
    updateWorker(setWorkerStates, d, "validate", "Validating…");
  });

  on("validation_completed", (d) => {
    setStatus(
      `Validation: ${d.hard_fail_count ?? 0} fails, ${d.warning_count ?? 0} warnings`,
    );
    updateWorker(setWorkerStates, d, "validate", "Validated");
  });

  on("persist_started", (d) => {
    setStatus("Persisting…");
    updateWorker(setWorkerStates, d, "persist", "Persisting…");
  });

  on("persist_completed", (d) => {
    setStatus(d.queued ? "Queued for review" : "Hard-fail — not queued");
    updateWorker(setWorkerStates, d, "persist", d.queued ? "Queued" : "Rejected");
  });

  on("persist_skipped", (d) => {
    setStatus("Dry-run: skipped persist");
    updateWorker(setWorkerStates, d, "persist", "Skipped");
  });

  on("encounter_processed", (d) => {
    setLive({
      run_id: d.run_id,
      processed_encounters: d.processed_encounters,
      queued_for_review: d.queued_for_review,
      rejected_hard_fail: d.rejected_hard_fail,
      warnings_only: d.warnings_only,
      llm_usage: d.llm_usage,
    });
    updateWorker(setWorkerStates, d, "done", "Done");
  });

  source.addEventListener("heartbeat", () =>
    setStatus((prev) => prev ?? "Pipeline running…"),
  );

  on("run_completed", (d) => {
    const res: PipelineRunResponse = {
      run_id: d.run_id,
      processed_encounters: d.processed_encounters,
      queued_for_review: d.queued_for_review,
      rejected_hard_fail: d.rejected_hard_fail,
      warnings_only: d.warnings_only,
      llm_usage: d.llm_usage,
    };
    setLive(res);
    setResult(res);
    setStatus("Run completed");
    setRunning(false);
    finished.current = true;
    source.close();
    esRef.current = null;
  });

  on("pipeline_error", (d) => {
    setError(d.message ?? "Pipeline error");
    setRunning(false);
    finished.current = true;
    source.close();
    esRef.current = null;
  });

  on("encounter_error", (d) => {
    setStatus(`Error on ${d.encounter_id}: ${d.error}`);
  });

  source.onerror = () => {
    if (finished.current) return;
    setError("Connection dropped");
    setRunning(false);
    source.close();
    esRef.current = null;
  };
}

export function usePipelineStream(): UsePipelineStreamReturn {
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [live, setLive] = useState<PipelineRunResponse | null>(null);
  const [result, setResult] = useState<PipelineRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workerStates, setWorkerStates] = useState<Record<number, WorkerState>>({});

  const esRef = useRef<EventSource | null>(null);
  const finishedRef = useRef(false);

  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  const cancel = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setRunning(false);
    setStatus("Cancelled");
  }, []);

  const start = useCallback((params: PipelineStreamParams) => {
    esRef.current?.close();
    setRunning(true);
    setError(null);
    setResult(null);
    setLive({ ...EMPTY_LIVE });
    setStatus("Connecting…");
    setWorkerStates({});
    finishedRef.current = false;

    const qs = new URLSearchParams({
      patient_ids: params.patientIds.join(","),
      dry_run: String(params.dryRun ?? false),
      workers: String(params.workers ?? 4),
    });
    if (params.maxEncountersPerPatient) {
      qs.set(
        "max_encounters_per_patient",
        String(params.maxEncountersPerPatient),
      );
    }

    const endpoint = params.unprocessedOnly ? "stream-unprocessed" : "stream";
    const source = new EventSource(`${API_BASE}/pipeline/${endpoint}?${qs}`);
    esRef.current = source;

    attachListeners(
      source,
      setStatus,
      setLive,
      setResult,
      setRunning,
      setError,
      setWorkerStates,
      finishedRef,
      esRef,
    );
  }, []);

  return { running, status, live, result, error, workerStates, start, cancel };
}
