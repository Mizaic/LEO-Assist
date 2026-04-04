"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import TrainingDataPanel from "./TrainingDataPanel";
import LabelVerificationPanel from "./LabelVerificationPanel";

// -- Types -------------------------------------------------------------------

interface LabelStats {
  total: number;
  included: number;
  excluded: number;
  by_source: Record<string, number>;
}

interface CodingStats {
  total: number;
  coded: number;
  uncoded: number;
  resolved: number;
  pending: number;
}

interface AllStats {
  labels: LabelStats;
  coding: CodingStats;
}

interface CorpusStats {
  gold_count: number;
  silver_count: number;
  holdout_count: number;
  negative_sentence_count: number;
  entity_type_breakdown: Record<string, number>;
  assertion_breakdown: Record<string, number>;
  imbalance_warnings: string[];
  safety_critical_blocked: boolean;
  training_ready: boolean;
  minimum_gold_met: boolean;
  last_updated: string | null;
}

const GOLD_MINIMUM = 5000;

// -- Fetch -------------------------------------------------------------------

async function loadStats(): Promise<AllStats> {
  const [labelsRes, codingRes] = await Promise.allSettled([
    fetch("/api/training/labels/stats").then((r) => r.json()),
    fetch("/api/training/coding-review/stats").then((r) => r.json()),
  ]);

  if (labelsRes.status === "rejected" && codingRes.status === "rejected") {
    throw new Error("Could not load training information. Please try again.");
  }

  return {
    labels:
      labelsRes.status === "fulfilled"
        ? labelsRes.value
        : { total: 0, included: 0, excluded: 0, by_source: {} },
    coding:
      codingRes.status === "fulfilled"
        ? codingRes.value
        : { total: 0, coded: 0, uncoded: 0, resolved: 0, pending: 0 },
  };
}

// -- Component ---------------------------------------------------------------

export default function TrainSection() {
  const [stats, setStats] = useState<AllStats | null>(null);
  const [corpus, setCorpus] = useState<CorpusStats | null>(null);
  const [tab, setTab] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    loadStats()
      .then(setStats)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load training information. Please try again."));

    fetch("/api/training/corpus/stats")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setCorpus)
      .catch(() => {
        // Non-blocking -- corpus stats are supplementary
      });
  }, []);

  return (
    <Stack gap={1.5}>
      {error && (
        <Alert severity="error" onClose={() => setError("")} sx={{ py: 0.25 }}>
          {error}
        </Alert>
      )}

      {/* Stats summary */}
      <Stack direction="row" gap={1.5} flexWrap="wrap">
        <StatCard
          title="Teaching examples"
          value={stats?.labels.total}
          sub={
            stats
              ? `${stats.labels.included} included, ${stats.labels.excluded} excluded`
              : undefined
          }
          hint="Records the AI learns from"
        />
        <StatCard
          title="Checked records"
          value={stats?.coding.total}
          sub={
            stats
              ? `${stats.coding.resolved} done, ${stats.coding.pending} waiting`
              : undefined
          }
          hint="Records reviewed by a person"
        />
        <StatCard
          title="Need attention"
          value={stats?.coding.uncoded}
          sub="Records without a clinical code"
          warn={stats != null && stats.coding.uncoded > 0}
        />
      </Stack>

      {/* Corpus card */}
      <CorpusCard corpus={corpus} />

      {/* Sub-tabs */}
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        aria-label="Training sub-sections"
        sx={{ minHeight: 36 }}
      >
        <Tab
          label="Teach the AI"
          id="train-tab-0"
          aria-controls="train-panel-0"
          sx={{ textTransform: "none", fontWeight: 600, minHeight: 36, py: 0.5 }}
        />
        <Tab
          label="Check the labels"
          id="train-tab-1"
          aria-controls="train-panel-1"
          sx={{ textTransform: "none", fontWeight: 600, minHeight: 36, py: 0.5 }}
        />
      </Tabs>

      <Box
        role="tabpanel"
        id={`train-panel-${tab}`}
        aria-labelledby={`train-tab-${tab}`}
      >
        {tab === 0 && <TrainingDataPanel />}
        {tab === 1 && <LabelVerificationPanel />}
      </Box>
    </Stack>
  );
}

// -- Corpus card -------------------------------------------------------------

function CorpusCard({ corpus }: { corpus: CorpusStats | null }) {
  if (!corpus) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Skeleton height={8} />
          <Skeleton variant="rectangular" height={100} sx={{ mt: 1 }} />
        </CardContent>
      </Card>
    );
  }

  const pct = Math.min(100, Math.round((corpus.gold_count / GOLD_MINIMUM) * 100));

  const chartData = Object.entries(corpus.entity_type_breakdown)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([tag, count]) => ({ tag: tag.slice(0, 20), count }));

  return (
    <Card
      variant="outlined"
      sx={{ borderColor: corpus.safety_critical_blocked ? "error.light" : "divider" }}
    >
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Training corpus
          </Typography>
          <Stack direction="row" gap={0.5} flexWrap="wrap">
            <Chip label={`${corpus.gold_count.toLocaleString()} confirmed`} size="small" color="primary" />
            <Chip label={`${corpus.silver_count.toLocaleString()} unconfirmed`} size="small" />
            <Chip label={`${corpus.holdout_count.toLocaleString()} held out`} size="small" variant="outlined" />
          </Stack>
        </Stack>

        {corpus.safety_critical_blocked && (
          <Alert severity="error" sx={{ mb: 1.5, py: 0.25 }}>
            Training blocked: not enough examples for safety-critical conditions (cancer, safeguarding, mental health crisis).
          </Alert>
        )}

        {corpus.imbalance_warnings.map((w) => (
          <Alert key={w} severity="warning" sx={{ mb: 0.5, py: 0.25 }}>
            {w}
          </Alert>
        ))}

        <Box sx={{ mb: 1.5 }}>
          <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              Progress to {GOLD_MINIMUM.toLocaleString()} confirmed examples
            </Typography>
            <Typography variant="caption" color={pct >= 100 ? "success.main" : "text.secondary"}>
              {corpus.gold_count.toLocaleString()} / {GOLD_MINIMUM.toLocaleString()}
            </Typography>
          </Stack>
          <LinearProgress
            variant="determinate"
            value={pct}
            color={pct >= 100 ? "success" : "primary"}
            aria-label="Progress to training minimum"
          />
        </Box>

        {chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e0e0e0" />
              <XAxis dataKey="tag" tick={{ fontSize: 9 }} interval={0} angle={-30} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 10 }} width={36} />
              <ChartTooltip formatter={(v: number) => [v.toLocaleString(), "Examples"]} />
              <Bar dataKey="count" name="Examples" fill="#1F3A8A" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}

        {corpus.last_updated && (
          <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 0.5 }}>
            Last updated: {corpus.last_updated.slice(0, 10)}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}


// -- Stat card ---------------------------------------------------------------

function StatCard({
  title,
  value,
  sub,
  hint,
  warn,
}: {
  title: string;
  value: number | undefined;
  sub?: string;
  hint?: string;
  warn?: boolean;
}) {
  return (
    <Card
      variant="outlined"
      sx={{
        flex: "1 1 160px",
        minWidth: 150,
        borderColor: warn ? "warning.light" : "divider",
      }}
    >
      <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, fontSize: 10.5 }}
        >
          {title}
        </Typography>
        {value != null ? (
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              lineHeight: 1.2,
              color: warn ? "warning.main" : "text.primary",
            }}
          >
            {value.toLocaleString()}
          </Typography>
        ) : (
          <Skeleton width={50} height={28} />
        )}
        {hint && (
          <Typography variant="caption" color="text.disabled" sx={{ display: "block", fontSize: 10.5, lineHeight: 1.3 }}>
            {hint}
          </Typography>
        )}
        {sub && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: 11, lineHeight: 1.3 }}>
            {sub}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
