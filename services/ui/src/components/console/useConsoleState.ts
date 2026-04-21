/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-0998FAF5
 *   Also implements: DO-E32DAC8D
 *   DI: DI-BE09736F
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StatTile } from "@leo/design-system";
import { HealthStatus } from "@/theme/tokens";

export interface TrainingJob {
  job_id: string;
  status: string;
  phase: string;
  f1?: number | null;
  precision?: number | null;
  recall?: number | null;
  per_label_f1?: Record<string, { precision: number; recall: number; f1: number }>;
  passed_gates?: boolean | null;
  golden_f1?: number | null;
  golden_passed?: boolean | null;
  model_version?: string;
  error?: string;
  created_at?: number;
  started_at?: number;
  finished_at?: number;
  elapsed_s?: number | null;
  log_lines?: string[];
  log_line_count?: number;
  export_total?: number | null;
  export_assertion_filtered?: number | null;
  export_span_misaligned?: number | null;
}

export interface ConsoleState {
  jobs: TrainingJob[];
  latestJob: TrainingJob | null;
  runningJob: TrainingJob | null;
  goldStats: { total: number; high_quality: number; avg_quality_score: number | null } | null;
  goldenSetStats: { total: number } | null;
  candidateQueueTotal: number | null;
  promotedVersion: string | null;
  loading: boolean;
  refresh: () => void;
}

const CONSOLE_FETCH_TIMEOUT_MS = 12000;

async function fetchWithTimeout(
  input: string,
  init?: RequestInit,
  timeoutMs = CONSOLE_FETCH_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }
}

// Adaptive polling cadence: when a training run is active we want
// near-realtime updates, but when the console is idle we should not
// hammer five backend endpoints every 10 seconds. The intervals scale
// roughly 6x between active and idle.
const ACTIVE_POLL_MS = 10_000;
const IDLE_POLL_MS = 60_000;

export function useConsoleState(): ConsoleState {
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [goldStats, setGoldStats] = useState<ConsoleState["goldStats"]>(null);
  const [goldenSetStats, setGoldenSetStats] = useState<{ total: number } | null>(null);
  const [candidateQueueTotal, setCandidateQueueTotal] = useState<number | null>(null);
  const [promotedVersion, setPromotedVersion] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const pollInFlightRef = useRef(false);
  const jobsRef = useRef<TrainingJob[]>([]);

  const fetchAll = useCallback(async () => {
    if (pollInFlightRef.current) {
      return;
    }
    pollInFlightRef.current = true;
    try {
      const [jobsRes, goldRes, goldenRes, queueRes, modelRes] = await Promise.allSettled([
        fetchWithTimeout("/api/training-worker/jobs"),
        fetchWithTimeout("/api/training/gold-labels/stats"),
        fetchWithTimeout("/api/training/gold-labels/golden-set/stats"),
        fetchWithTimeout("/api/training/candidates/active-learning-queue?page=1&page_size=1"),
        fetchWithTimeout("/api/model-registry/status"),
      ]);

      if (jobsRes.status === "fulfilled" && jobsRes.value.ok) {
        const data = await jobsRes.value.json();
        const next = (data.jobs ?? data ?? []) as TrainingJob[];
        jobsRef.current = next;
        setJobs(next);
      }
      if (goldRes.status === "fulfilled" && goldRes.value.ok) {
        setGoldStats(await goldRes.value.json());
      }
      if (goldenRes.status === "fulfilled" && goldenRes.value.ok) {
        setGoldenSetStats(await goldenRes.value.json());
      }
      if (queueRes.status === "fulfilled" && queueRes.value.ok) {
        const d = await queueRes.value.json();
        setCandidateQueueTotal(d.total ?? null);
      }
      if (modelRes.status === "fulfilled" && modelRes.value.ok) {
        const d = await modelRes.value.json();
        const active = d.active_model ?? d;
        setPromotedVersion(active.model_version ?? active.version ?? null);
      }
    } finally {
      setLoading(false);
      pollInFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const isActive = () =>
      jobsRef.current.some(
        (j) =>
          j.status === "running" ||
          j.status === "evaluating" ||
          j.status === "uploading",
      );

    const schedule = () => {
      if (cancelled) return;
      const visible =
        typeof document === "undefined" || !document.hidden;
      const interval = !visible
        ? IDLE_POLL_MS
        : isActive()
          ? ACTIVE_POLL_MS
          : IDLE_POLL_MS;
      timer = setTimeout(async () => {
        if (cancelled) return;
        if (typeof document === "undefined" || !document.hidden) {
          await fetchAll();
        }
        schedule();
      }, interval);
    };

    fetchAll().finally(() => schedule());

    const onVisibility = () => {
      if (typeof document !== "undefined" && !document.hidden) {
        if (timer) clearTimeout(timer);
        fetchAll().finally(() => schedule());
      }
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibility);
    }
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibility);
      }
    };
  }, [fetchAll]);

  const latestJob = jobs[0] ?? null;
  const runningJob =
    jobs.find(
      (j) =>
        j.status === "running" ||
        j.status === "evaluating" ||
        j.status === "uploading"
    ) ?? null;

  return {
    jobs,
    latestJob,
    runningJob,
    goldStats,
    goldenSetStats,
    candidateQueueTotal,
    promotedVersion,
    loading,
    refresh: fetchAll,
  };
}

// -- StatHero tile derivation ------------------------------------------------

// Pretty-print an F1 score (0..1) as a percentage with one decimal.
// Returns null when the value is missing so the caller can fall back.
function formatF1(value?: number | null): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  return (value * 100).toFixed(1) + "%";
}

function goldTile(state: ConsoleState): StatTile {
  const total = state.goldStats?.total ?? 0;
  return {
    id: "gold-labels",
    label: "Gold labels",
    value: total,
    hint: total === 0 ? "Nothing to train on yet" : "Verified training rows",
    tone: total >= 100 ? "positive" : total > 0 ? "neutral" : "warning",
  };
}

function queueTile(state: ConsoleState): StatTile {
  const total = state.candidateQueueTotal ?? 0;
  return {
    id: "candidate-queue",
    label: "Candidate queue",
    value: total,
    hint: total === 0 ? "All caught up" : "Awaiting reviewer",
    tone: total >= 20 ? "warning" : total > 0 ? "neutral" : "positive",
  };
}

function modelTile(state: ConsoleState): StatTile {
  const f1 = formatF1(state.latestJob?.f1);
  if (f1) {
    return {
      id: "latest-f1",
      label: "Latest F1",
      value: f1,
      hint: state.latestJob?.model_version ?? "Last training run",
      tone:
        state.latestJob?.passed_gates === false ? "danger" : "positive",
    };
  }
  return {
    id: "live-model",
    label: "Live model",
    value: state.promotedVersion ?? "None",
    hint: state.promotedVersion ? "Serving today" : "No model promoted",
    tone: state.promotedVersion ? "positive" : "neutral",
  };
}

// computeConsoleStats -- distil the console state into the small set of
// numbers operations users actually scan when they open the page. Used
// by /admin/console to feed StatHero. Returns >= 3 tiles so the
// design-system grid stays balanced. See DI-LEO-AI-164 acceptance
// criterion (>= 3 tiles) and VT-LEO-AI-162 TC-004.
export function computeConsoleStats(state: ConsoleState): StatTile[] {
  return [goldTile(state), queueTile(state), modelTile(state)];
}

// -- Smart nudge derivation --------------------------------------------------

export interface NudgeSuggestion {
  message: string;
  actionLabel: string;
  actionStage: string;
  severity: "info" | "warning" | "error";
}

export function deriveNudge(state: ConsoleState): NudgeSuggestion | null {
  const { latestJob, runningJob, goldStats, candidateQueueTotal, promotedVersion } = state;

  if (runningJob) {
    const phase = runningJob.phase ?? "running";
    return {
      message: `Training in progress — phase: ${phase}. Stay on this page to watch live results.`,
      actionLabel: "View progress",
      actionStage: "TRAIN",
      severity: "info",
    };
  }

  if (latestJob?.status === "failed") {
    return {
      message: `Last training job failed: ${latestJob.error ?? "unknown error"}. Check logs in the Train stage.`,
      actionLabel: "View details",
      actionStage: "TRAIN",
      severity: "error",
    };
  }

  if (
    latestJob?.status === "done" &&
    latestJob?.passed_gates === true &&
    !!latestJob?.model_version &&
    promotedVersion !== latestJob.model_version
  ) {
    return {
      message: "Model passed training checks. Run the safety test and decide whether to make it live.",
      actionLabel: "Open evaluation",
      actionStage: "EVALUATE",
      severity: "info",
    };
  }

  if (
    latestJob?.status === "done" &&
    latestJob?.golden_passed === false
  ) {
    return {
      message: `Golden set F1 dropped below threshold. The model regressed on the frozen benchmark.`,
      actionLabel: "View evaluation",
      actionStage: "EVALUATE",
      severity: "error",
    };
  }

  if (candidateQueueTotal != null && candidateQueueTotal >= 20) {
    return {
      message: `${candidateQueueTotal} candidates are waiting for review. Reviewing the top uncertain items could improve model recall.`,
      actionLabel: "Review candidates",
      actionStage: "CURATE",
      severity: "warning",
    };
  }

  if (goldStats && goldStats.total > 0 && !latestJob) {
    return {
      message: `You have ${goldStats.total} gold labels ready. Train the model to put them to use.`,
      actionLabel: "Train now",
      actionStage: "TRAIN",
      severity: "info",
    };
  }

  return null;
}

// -- Stage health computation ------------------------------------------------

export function deriveStageHealth(state: ConsoleState): Record<string, { status: HealthStatus; reason: string }> {
  const { latestJob, runningJob, goldStats, goldenSetStats, promotedVersion } = state;

  return {
    DISCOVER: { status: "healthy", reason: "Pipeline running" },
    CURATE: goldStats
      ? goldStats.total < 10
        ? { status: "warning", reason: "Fewer than 10 gold labels" }
        : { status: "healthy", reason: `${goldStats.total} gold labels` }
      : { status: "neutral", reason: "Loading" },
    TRAIN: runningJob
      ? { status: "info", reason: `Training — phase: ${runningJob.phase}` }
      : latestJob?.status === "failed"
      ? { status: "error", reason: latestJob.error ?? "Job failed" }
      : latestJob?.status === "done"
      ? { status: "healthy", reason: `Last job: ${latestJob.model_version ?? "done"}` }
      : { status: "neutral", reason: "No training history" },
    EVALUATE: latestJob?.status === "done" && latestJob?.passed_gates === false
      ? { status: "error", reason: "Learning gate failed" }
      : latestJob?.status === "done" && latestJob?.passed_gates === true && latestJob?.model_version
      ? promotedVersion === latestJob.model_version
        ? { status: "healthy", reason: "Latest model is live" }
        : { status: "warning", reason: "Safety test and release decision pending" }
      : { status: "neutral", reason: "No evaluation ready" },
    DEPLOY: promotedVersion
      ? { status: "healthy", reason: `Live: ${promotedVersion}` }
      : { status: "neutral", reason: "No live model" },
    MONITOR: { status: "healthy", reason: "Monitoring active" },
  };
}
