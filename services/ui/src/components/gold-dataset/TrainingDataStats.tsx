/**
 * TrainingDataStats -- StatHero + ProgressStrip for the gold dataset page.
 *
 * Extracted from GoldDatasetPanel as part of Wave E file-size refactoring.
 * Design Controls: DI-21946271, DO-1E9BCC70.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";

import {
  ProgressStrip,
  StatHero,
  type StatTile as DsStatTile,
} from "@leo/design-system";

import type { CandidateStats, GoldStats, SyntheticStats } from "./goldDatasetTypes";

export interface TrainingDataStatsProps {
  candidateStats: CandidateStats | null;
  goldStats: GoldStats | null;
  syntheticStats: SyntheticStats | null;
  statsLoading: boolean;
  statsError: string | null;
  onDismissError: () => void;
  currentTab: "candidates" | "gold" | "synthetic";
}

function buildStats(
  candidateStats: CandidateStats | null,
  goldStats: GoldStats | null,
  syntheticStats: SyntheticStats | null,
): DsStatTile[] {
  return [
    { id: "received", label: "Received", value: candidateStats?.total ?? 0 },
    {
      id: "ready",
      label: "Ready for training",
      value: goldStats?.total ?? 0,
      tone: "positive",
    },
    {
      id: "failed",
      label: "Failed",
      value: candidateStats?.failed ?? 0,
      tone: (candidateStats?.failed ?? 0) > 0 ? "danger" : "neutral",
    },
    {
      id: "verified",
      label: "Verified gold",
      value: goldStats?.total ?? 0,
    },
    {
      id: "synthetic",
      label: "Synthetic gold",
      value: syntheticStats?.synthetic_gold_labels ?? 0,
    },
    {
      id: "quality",
      label: "Avg quality",
      value:
        goldStats?.avg_quality_score != null
          ? `${Math.round((goldStats.avg_quality_score ?? 0) * 100)}%`
          : "-",
      hint:
        goldStats && goldStats.total > 0
          ? `${goldStats.high_quality} high quality`
          : undefined,
      tone:
        goldStats?.avg_quality_score != null
          ? goldStats.avg_quality_score >= 0.8
            ? "positive"
            : goldStats.avg_quality_score >= 0.5
              ? "warning"
              : "danger"
          : "neutral",
    },
  ];
}

export function TrainingDataStats({
  candidateStats,
  goldStats,
  syntheticStats,
  statsLoading,
  statsError,
  onDismissError,
  currentTab,
}: TrainingDataStatsProps) {
  const showProgress =
    !statsLoading &&
    currentTab === "candidates" &&
    candidateStats != null &&
    candidateStats.total > candidateStats.completed;

  return (
    <>
      {statsError ? (
        <Alert severity="error" sx={{ mb: 1.5 }} onClose={onDismissError}>
          {statsError}
        </Alert>
      ) : null}

      {statsLoading ? (
        <Stack direction="row" spacing={1.25} sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} variant="rounded" width={160} height={96} />
          ))}
        </Stack>
      ) : (
        <StatHero
          stats={buildStats(candidateStats, goldStats, syntheticStats)}
          maxTiles={6}
        />
      )}

      {showProgress && candidateStats ? (
        <ProgressStrip
          label={`${candidateStats.total - candidateStats.completed} item${
            candidateStats.total - candidateStats.completed !== 1 ? "s" : ""
          } left to review`}
          value={candidateStats.completed}
          total={candidateStats.total}
          tone="positive"
        />
      ) : null}
    </>
  );
}
