"use client";

/**
 * Intelligence Console -- Wave E Phase 8a redesign.
 *
 * The page hands its chrome to the @leo/design-system so it visually
 * matches the Knowledge tabs and the Pathways list:
 *
 *   - KnowledgePageLayout (width="wide", screenId="admin-console")
 *     supplies the shared gutter and 1600px column.
 *   - AreaIntro renders the role-aware IntroCard for the operations
 *     area (preserves the area-intro-wiring contract enforced by
 *     VT-LEO-AI-135 TC-004).
 *   - StatHero summarises the AI loop in three live tiles
 *     (gold labels / candidate queue / latest F1 or live model).
 *   - NudgeStrip surfaces the smart next-best-action banner.
 *   - PipelineRail is the accessible six-stage pipeline navigator.
 *   - ConsoleStagePanel renders each stage body inside a
 *     design-system-tokenised card.
 *
 * The internal stage modules (DiscoverStage, CurateStage, TrainStage,
 * EvaluateStage, DeployStage, MonitorStage) keep working unchanged
 * behind the new shell. Their bodies will be rebuilt on
 * ReviewListCard / DataGridCard primitives in Phase 8b.
 *
 * Design Controls: DI-LEO-AI-164, DO-LEO-AI-163, R-LEO-AI-165, VT-LEO-AI-162.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";

import {
  KnowledgePageLayout,
  NudgeStrip,
  PipelineRail,
  StatHero,
  type PipelineStage,
} from "@leo/design-system";

import AreaIntro from "@/components/AreaIntro";
import { MetricChip } from "@/components/ui";
import {
  computeConsoleStats,
  deriveNudge,
  deriveStageHealth,
  useConsoleState,
} from "@/components/console/useConsoleState";
import { ConsoleStagePanel } from "@/components/console/ConsoleStagePanel";
import { DiscoverStage } from "@/components/console/DiscoverStage";
import { CurateStage } from "@/components/console/CurateStage";
import { TrainStage } from "@/components/console/TrainStage";
import { EvaluateStage } from "@/components/console/EvaluateStage";
import { DeployStage } from "@/components/console/DeployStage";
import { MonitorStage } from "@/components/console/MonitorStage";
import { STAGE_COLORS } from "@/theme/tokens";

const STAGE_KEYS = [
  "DISCOVER",
  "CURATE",
  "TRAIN",
  "EVALUATE",
  "DEPLOY",
  "MONITOR",
] as const;

type StageKey = (typeof STAGE_KEYS)[number];

const STAGE_ACTION_LABELS: Record<StageKey, string> = {
  DISCOVER: "View encounters",
  CURATE: "Review candidates",
  TRAIN: "Train now",
  EVALUATE: "Run safety test",
  DEPLOY: "Manage models",
  MONITOR: "View alerts",
};

export default function ConsolePage() {
  const state = useConsoleState();
  const [activeStage, setActiveStage] = useState<StageKey | null>(null);
  const [training, setTraining] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const stageHealth = deriveStageHealth(state);
  const nudge = deriveNudge(state);
  const stats = useMemo(() => computeConsoleStats(state), [state]);

  const handleStageClick = (key: string) => {
    setActiveStage((prev) => (prev === key ? null : (key as StageKey)));
  };

  const handleTrain = async () => {
    setTraining(true);
    try {
      await fetch("/api/training-worker/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ triggered_by: "console" }),
      });
      state.refresh();
    } finally {
      setTraining(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    setCancelling(true);
    try {
      await fetch(`/api/training/jobs/${encodeURIComponent(jobId)}`, {
        method: "DELETE",
        credentials: "include",
      });
      state.refresh();
    } finally {
      setCancelling(false);
    }
  };

  const railStages: PipelineStage[] = STAGE_KEYS.map((key) => ({
    id: key,
    label: key,
    status: stageHealth[key]?.status ?? "neutral",
    reason: stageHealth[key]?.reason,
    accentColor: STAGE_COLORS[key],
  }));

  if (state.loading) {
    return (
      <KnowledgePageLayout screenId="admin-console" width="wide">
        <Box
          sx={{ p: 3, display: "flex", alignItems: "center", gap: 2 }}
          aria-live="polite"
        >
          <CircularProgress size={20} />
          <Typography>Loading console...</Typography>
        </Box>
      </KnowledgePageLayout>
    );
  }

  return (
    <KnowledgePageLayout screenId="admin-console" width="wide">
      <AreaIntro area="operations" />

      <StatHero stats={stats} />

      {nudge ? (
        <NudgeStrip
          message={nudge.message}
          actionLabel={nudge.actionLabel}
          severity={nudge.severity === "error" ? "danger" : nudge.severity}
          onAction={() => handleStageClick(nudge.actionStage)}
        />
      ) : null}

      <PipelineRail
        stages={railStages}
        activeStageId={activeStage}
        onStageSelect={handleStageClick}
        ariaLabel="AI learning loop stages"
      />

      <Stack spacing={1.5} sx={{ mt: 2 }}>
        {activeStage === "DISCOVER" && (
          <ConsoleStagePanel
            title="Discover"
            status={stageHealth.DISCOVER?.status ?? "neutral"}
            statusReason={stageHealth.DISCOVER?.reason}
            defaultExpanded
            accentColor={STAGE_COLORS.DISCOVER}
          >
            <DiscoverStage />
          </ConsoleStagePanel>
        )}

        {activeStage === "CURATE" && (
          <ConsoleStagePanel
            title="Curate"
            status={stageHealth.CURATE?.status ?? "neutral"}
            statusReason={stageHealth.CURATE?.reason}
            metric={
              state.goldStats ? (
                <MetricChip
                  value={state.goldStats.total}
                  label="labels"
                  color={STAGE_COLORS.CURATE}
                />
              ) : undefined
            }
            defaultExpanded
            accentColor={STAGE_COLORS.CURATE}
          >
            <CurateStage queueTotal={state.candidateQueueTotal} />
          </ConsoleStagePanel>
        )}

        {activeStage === "TRAIN" && (
          <ConsoleStagePanel
            title="Train"
            status={stageHealth.TRAIN?.status ?? "neutral"}
            statusReason={stageHealth.TRAIN?.reason}
            actionLabel="Train now"
            onAction={handleTrain}
            actionDisabled={training || !!state.runningJob}
            defaultExpanded
            accentColor={STAGE_COLORS.TRAIN}
          >
            <TrainStage
              jobs={state.jobs}
              runningJob={state.runningJob}
              latestJob={state.latestJob}
              onTrain={handleTrain}
              training={training}
              onCancelJob={handleCancelJob}
              cancelling={cancelling}
            />
          </ConsoleStagePanel>
        )}

        {activeStage === "EVALUATE" && (
          <ConsoleStagePanel
            title="Evaluate"
            status={stageHealth.EVALUATE?.status ?? "neutral"}
            statusReason={stageHealth.EVALUATE?.reason}
            metric={
              state.latestJob?.f1 != null ? (
                <MetricChip
                  value={`${(state.latestJob.f1 * 100).toFixed(1)}%`}
                  label="F1"
                  color={STAGE_COLORS.EVALUATE}
                />
              ) : undefined
            }
            defaultExpanded
            accentColor={STAGE_COLORS.EVALUATE}
          >
            <EvaluateStage
              jobs={state.jobs}
              latestJob={state.latestJob}
              promotedVersion={state.promotedVersion}
            />
          </ConsoleStagePanel>
        )}

        {activeStage === "DEPLOY" && (
          <ConsoleStagePanel
            title="Deploy"
            status={stageHealth.DEPLOY?.status ?? "neutral"}
            statusReason={stageHealth.DEPLOY?.reason}
            metric={
              state.promotedVersion ? (
                <MetricChip
                  value={state.promotedVersion}
                  label="live"
                  color={STAGE_COLORS.DEPLOY}
                />
              ) : undefined
            }
            defaultExpanded
            accentColor={STAGE_COLORS.DEPLOY}
          >
            <DeployStage promotedVersion={state.promotedVersion} />
          </ConsoleStagePanel>
        )}

        {activeStage === "MONITOR" && (
          <ConsoleStagePanel
            title="Monitor"
            status={stageHealth.MONITOR?.status ?? "neutral"}
            statusReason={stageHealth.MONITOR?.reason}
            defaultExpanded
            accentColor={STAGE_COLORS.MONITOR}
          >
            <MonitorStage />
          </ConsoleStagePanel>
        )}

        {!activeStage && (
          <Stack spacing={1}>
            {STAGE_KEYS.map((key) => {
              const h = stageHealth[key] ?? {
                status: "neutral" as const,
                reason: "",
              };
              return (
                <ConsoleStagePanel
                  key={key}
                  title={key}
                  status={h.status}
                  statusReason={h.reason}
                  actionLabel={STAGE_ACTION_LABELS[key]}
                  onAction={() => handleStageClick(key)}
                  accentColor={STAGE_COLORS[key]}
                />
              );
            })}
          </Stack>
        )}
      </Stack>
    </KnowledgePageLayout>
  );
}
