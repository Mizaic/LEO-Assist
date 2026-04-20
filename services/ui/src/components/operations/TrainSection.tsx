/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2695BE52
 *   Also implements: DO-A2553F87
 *   DI: DI-3DFEE507, DI-425CA252
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2695BE52")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Link from "next/link";

interface StatCardProps {
  title: string;
  value: number | undefined;
  caption: string;
  loading?: boolean;
}

function StatCard({ title, value, caption, loading }: StatCardProps) {
  return (
    <Card variant="outlined" sx={{ flex: 1, minWidth: 180 }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          {title}
        </Typography>
        {loading ? (
          <Skeleton height={32} width={80} />
        ) : (
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            {value?.toLocaleString() ?? "--"}
          </Typography>
        )}
        <Typography variant="caption" color="text.secondary">
          {caption}
        </Typography>
      </CardContent>
    </Card>
  );
}

// -- Types -------------------------------------------------------------------

interface GoldStats {
  total: number;
  high_quality: number;
  avg_quality_score: number | null;
}

interface TrainingJob {
  job_id: string;
  status: string;
  phase: string;
  model_version: string;
  error: string;
  created_at: number;
  elapsed_s: number | null;
}

interface TrainingJobsResponse {
  jobs: TrainingJob[];
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || "Request failed");
  }
  return (await res.json()) as T;
}

// -- Component ---------------------------------------------------------------

export default function TrainSection() {
  const [goldStats, setGoldStats] = useState<GoldStats | null>(null);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  useEffect(() => {
    const refresh = async () => {
      try {
        const [stats, jobsRes] = await Promise.all([
          jsonFetch<GoldStats>("/api/training/gold-labels/stats"),
          jsonFetch<TrainingJobsResponse>("/api/training-worker/jobs"),
        ]);
        setGoldStats(stats);
        setJobs(
          [...(jobsRes.jobs ?? [])].sort((a, b) => b.created_at - a.created_at),
        );
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "Could not load training information. Please try again.",
        );
      }
    };
    void refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  const latestJob = useMemo(() => jobs[0] ?? null, [jobs]);

  const startTraining = async () => {
    setIsStarting(true);
    setError("");
    setInfo("");
    try {
      const data = await jsonFetch<{ job_id: string }>("/api/training-worker/jobs", {
        method: "POST",
        body: JSON.stringify({
          notes: "operations_gold_dataset_training",
          triggered_by: "operations_ui",
          base_model_version: "",
        }),
      });
      setInfo(`Training started. Job ID: ${data.job_id}`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not start the training run.",
      );
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <Stack gap={2}>
      {error && (
        <Alert severity="error" onClose={() => setError("")} sx={{ py: 0.25 }}>
          {error}
        </Alert>
      )}
      {info && (
        <Alert severity="success" onClose={() => setInfo("")} sx={{ py: 0.25 }}>
          {info}
        </Alert>
      )}

      <Stack
        direction="row"
        gap={1}
        role="tablist"
        aria-label="Training tabs"
      >
        <Button
          component={Link}
          href="/admin/knowledge?tab=training-data"
          variant="contained"
          size="small"
          role="tab"
        >
          Teach the AI
        </Button>
        <Button
          component={Link}
          href="/admin/knowledge?tab=label-verification"
          variant="outlined"
          size="small"
          role="tab"
        >
          Check the labels
        </Button>
      </Stack>

      <Stack direction="row" gap={1} flexWrap="wrap">
        <StatCard
          title="Teaching examples"
          value={goldStats?.total}
          caption="Examples that help the AI learn."
          loading={!goldStats}
        />
        <StatCard
          title="Checked records"
          value={goldStats?.high_quality}
          caption="Records a person has signed off."
          loading={!goldStats}
        />
        <StatCard
          title="Need attention"
          value={
            goldStats
              ? Math.max(0, goldStats.total - goldStats.high_quality)
              : undefined
          }
          caption="Records still waiting for a human check."
          loading={!goldStats}
        />
      </Stack>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Gold training data
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Manage label corrections and approvals in the gold dataset workspace.
            {goldStats?.avg_quality_score != null && (
              <>
                {" "}
                Average quality score:{" "}
                {goldStats.avg_quality_score.toFixed(3)}.
              </>
            )}
          </Typography>
          <Button
            component={Link}
            href="/admin/knowledge?tab=training-data"
            variant="outlined"
            size="small"
            sx={{ mt: 1.5 }}
          >
            Manage training data
          </Button>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Train model
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Start a training run from completed GoldLabel records.
          </Typography>
          <Button
            variant="contained"
            sx={{ mt: 1.5 }}
            onClick={startTraining}
            disabled={isStarting}
            startIcon={isStarting ? <CircularProgress size={16} /> : undefined}
          >
            {isStarting ? "Starting..." : "Run training"}
          </Button>
          <Divider sx={{ my: 1.5 }} />
          {latestJob ? (
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Latest job: {latestJob.job_id.slice(0, 12)}...
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Status: {latestJob.status}
                {latestJob.phase ? ` (${latestJob.phase})` : ""}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Model version: {latestJob.model_version || "--"}
              </Typography>
              {latestJob.error && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  {latestJob.error}
                </Alert>
              )}
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No training jobs yet.
            </Typography>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
