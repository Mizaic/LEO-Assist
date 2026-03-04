"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
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
  const [tab, setTab] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    loadStats()
      .then(setStats)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load training information. Please try again."));
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
