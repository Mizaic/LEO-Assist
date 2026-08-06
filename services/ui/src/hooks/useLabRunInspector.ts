/**
 * Validation Lab run inspector hook (SSE + snapshot + poll merge).
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getRun,
  getRunInspector,
  getRunInspectorStage,
  type StageProgress,
} from "@/app/admin/validation-lab/labApi";
import {
  mergeInspectorState,
  traceEventFromPayload,
  type LabRunInspectorSnapshot,
  type LabStageDetail,
  type LabTraceEvent,
  type LabTraceSpan,
} from "@/app/admin/validation-lab/inspectorTypes";

export interface UseLabRunInspectorOptions {
  caseId: string;
  runId: string;
  enabled: boolean;
  pollStages?: StageProgress[];
}

export interface UseLabRunInspectorReturn {
  snapshot: LabRunInspectorSnapshot | null;
  spans: LabTraceSpan[];
  events: LabTraceEvent[];
  connected: boolean;
  error: string | null;
  selectedStepId: string | null;
  setSelectedStepId: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
  stageLoading: boolean;
  refreshSnapshot: () => Promise<void>;
}

export function useLabRunInspector(
  opts: UseLabRunInspectorOptions,
): UseLabRunInspectorReturn {
  const { caseId, runId, enabled, pollStages } = opts;
  const [snapshot, setSnapshot] = useState<LabRunInspectorSnapshot | null>(null);
  const [events, setEvents] = useState<LabTraceEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [stageDetail, setStageDetail] = useState<LabStageDetail | null>(null);
  const [stageLoading, setStageLoading] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const refreshSnapshot = useCallback(async () => {
    if (!caseId || !runId) return;
    try {
      const data = await getRunInspector(caseId, runId);
      setSnapshot(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inspector load failed");
    }
  }, [caseId, runId]);

  useEffect(() => {
    if (!enabled || !caseId || !runId) return;
    void refreshSnapshot();
  }, [enabled, caseId, runId, refreshSnapshot]);

  useEffect(() => {
    if (!enabled || !runId) return;
    const origin = window.location.origin;
    const source = new EventSource(
      `${origin}/api/pipeline/progress/${encodeURIComponent(runId)}`,
    );
    esRef.current = source;
    setConnected(true);

    const onPayload = (payload: Record<string, unknown>) => {
      setEvents((prev) => [...prev, traceEventFromPayload(payload)]);
    };

    const attach = (name: string) => {
      source.addEventListener(name, (e) => {
        try {
          onPayload(JSON.parse((e as MessageEvent).data));
        } catch {
          /* ignore malformed */
        }
      });
    };

    [
      "lab.bootstrap.started",
      "lab.bootstrap.completed",
      "lab.bootstrap.failed",
      "durable_step_started",
      "durable_step_completed",
      "durable_step_failed",
      "durable_step_poisoned",
      "durable_step_already_completed",
      "heartbeat",
      "pipeline_error",
      "message",
    ].forEach(attach);

    source.onmessage = (e) => {
      try {
        onPayload(JSON.parse(e.data));
      } catch {
        /* ignore */
      }
    };

    source.onerror = () => {
      setConnected(false);
    };

    return () => {
      source.close();
      esRef.current = null;
      setConnected(false);
    };
  }, [enabled, runId]);

  useEffect(() => {
    if (!selectedStepId || !caseId || !runId) {
      setStageDetail(null);
      return;
    }
    let cancelled = false;
    setStageLoading(true);
    getRunInspectorStage(caseId, runId, selectedStepId)
      .then((detail) => {
        if (!cancelled) setStageDetail(detail);
      })
      .catch(() => {
        if (!cancelled) setStageDetail(null);
      })
      .finally(() => {
        if (!cancelled) setStageLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, runId, selectedStepId]);

  const merged = useMemo(
    () => mergeInspectorState(snapshot, events, pollStages),
    [snapshot, events, pollStages],
  );

  return {
    snapshot,
    spans: merged.spans,
    events: merged.events,
    connected,
    error,
    selectedStepId,
    setSelectedStepId,
    stageDetail,
    stageLoading,
    refreshSnapshot,
  };
}

/** Poll lab run for stage_progress while inspector is open. */
export function useLabRunStagePoll(
  caseId: string,
  runId: string,
  enabled: boolean,
  terminal: boolean,
): StageProgress[] {
  const [stages, setStages] = useState<StageProgress[]>([]);
  useEffect(() => {
    if (!enabled || !caseId || !runId || terminal) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const packed = await getRun(caseId, runId);
        if (!cancelled) setStages(packed.run.stage_progress || []);
      } catch {
        /* ignore poll errors */
      }
    };
    void tick();
    const id = window.setInterval(tick, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [caseId, runId, enabled, terminal]);
  return stages;
}
