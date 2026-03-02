"use client";

import { useEffect, useState } from "react";
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

  useEffect(() => {
    loadStats().then(setStats).catch(() => {});
  }, []);

  return (
    <Stack gap={2.5}>
      {/* Stats summary */}
      <Stack direction="row" gap={2} flexWrap="wrap">
        <StatCard
          title="Training labels"
          value={stats?.labels.total}
          sub={
            stats
              ? `${stats.labels.included} included, ${stats.labels.excluded} excluded`
              : undefined
          }
        />
        <StatCard
          title="Coding reviews"
          value={stats?.coding.total}
          sub={
            stats
              ? `${stats.coding.resolved} resolved, ${stats.coding.pending} pending`
              : undefined
          }
        />
        <StatCard
          title="Uncoded items"
          value={stats?.coding.uncoded}
          sub="Need a clinical code"
          warn={stats != null && stats.coding.uncoded > 0}
        />
      </Stack>

      {/* Sub-tabs */}
      <Box>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          aria-label="Training sub-sections"
        >
          <Tab
            label="Training data"
            id="train-tab-0"
            aria-controls="train-panel-0"
            sx={{ textTransform: "none", fontWeight: 600 }}
          />
          <Tab
            label="Label checks"
            id="train-tab-1"
            aria-controls="train-panel-1"
            sx={{ textTransform: "none", fontWeight: 600 }}
          />
        </Tabs>
      </Box>

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
  warn,
}: {
  title: string;
  value: number | undefined;
  sub?: string;
  warn?: boolean;
}) {
  return (
    <Card sx={{ flex: "1 1 200px", minWidth: 180 }}>
      <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}
        >
          {title}
        </Typography>
        {value != null ? (
          <Typography
            variant="h5"
            sx={{
              fontWeight: 700,
              mt: 0.5,
              color: warn ? "warning.main" : "text.primary",
            }}
          >
            {value.toLocaleString()}
          </Typography>
        ) : (
          <Skeleton width={60} height={32} sx={{ mt: 0.5 }} />
        )}
        {sub && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
            {sub}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
