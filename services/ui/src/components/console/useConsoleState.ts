"use client";

import { useCallback, useEffect, useState } from "react";
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

export function useConsoleState(): ConsoleState {
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [goldStats, setGoldStats] = useState<ConsoleState["goldStats"]>(null);
  const [goldenSetStats, setGoldenSetStats] = useState<{ total: number } | null>(null);
  const [candidateQueueTotal, setCandidateQueueTotal] = useState<number | null>(null);
  const [promotedVersion, setPromotedVersion] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [jobsRes, goldRes, goldenRes, queueRes, modelRes] = await Promise.allSettled([
        fetch("/api/training-worker/jobs"),
        fetch("/api/training/gold-labels/stats"),
        fetch("/api/training/gold-labels/golden-set/stats"),
        fetch("/api/training/candidates/active-learning-queue?page=1&page_size=1"),
        fetch("/api/model-registry/status"),
      ]);

      if (jobsRes.status === "fulfilled" && jobsRes.value.ok) {
        const data = await jobsRes.value.json();
        setJobs(data.jobs ?? data ?? []);
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
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 10000);
    return () => clearInterval(id);
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
