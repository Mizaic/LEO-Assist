"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import { HealthBar, NudgeBanner, StageCard, MetricChip } from "@/components/ui";
import { useConsoleState, deriveNudge, deriveStageHealth } from "@/components/console/useConsoleState";
import { DiscoverStage } from "@/components/console/DiscoverStage";
import { CurateStage } from "@/components/console/CurateStage";
import { TrainStage } from "@/components/console/TrainStage";
import { EvaluateStage } from "@/components/console/EvaluateStage";
import { DeployStage } from "@/components/console/DeployStage";
import { MonitorStage } from "@/components/console/MonitorStage";
import { STAGE_COLORS } from "@/theme/tokens";
import AreaIntro from "@/components/AreaIntro";

const STAGE_KEYS = ["DISCOVER", "CURATE", "TRAIN", "EVALUATE", "DEPLOY", "MONITOR"] as const;

export default function ConsolePage() {
  const state = useConsoleState();
  const [activeStage, setActiveStage] = useState<string | null>(null);
  const [training, setTraining] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const stageHealth = deriveStageHealth(state);
  const nudge = deriveNudge(state);

  const handleStageClick = (key: string) => {
    setActiveStage((prev) => (prev === key ? null : key));
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

  const stages = STAGE_KEYS.map((key) => ({
    key,
    label: key,
    ...(stageHealth[key] ?? { status: "neutral" as const, reason: "" }),
  }));

  if (state.loading) {
    return (
      <Box sx={{ p: 3, display: "flex", alignItems: "center", gap: 2 }}>
        <CircularProgress size={20} />
        <Typography>Loading console…</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <AreaIntro area="operations" />
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.5 }}>
        Intelligence Console
      </Typography>
      <Typography sx={{ color: "text.secondary", mb: 2.5, fontSize: "0.9rem" }}>
        The AI learning loop - from encounter to deployed model.
      </Typography>

      {/* Smart nudge */}
      {nudge && (
        <NudgeBanner
          message={nudge.message}
          actionLabel={nudge.actionLabel}
          severity={nudge.severity}
          onAction={() => handleStageClick(nudge.actionStage)}
        />
      )}

      {/* Health bar */}
      <HealthBar
        stages={stages}
        activeStage={activeStage ?? undefined}
        onStageClick={handleStageClick}
      />

      {/* Stage panels */}
      <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 1.5 }}>
        {activeStage === "DISCOVER" && (
          <StageCard
            title="Discover"
            status={stageHealth.DISCOVER?.status ?? "neutral"}
            statusReason={stageHealth.DISCOVER?.reason}
            defaultExpanded
            accentColor={STAGE_COLORS.DISCOVER}
          >
            <DiscoverStage />
          </StageCard>
        )}

        {activeStage === "CURATE" && (
          <StageCard
            title="Curate"
            status={stageHealth.CURATE?.status ?? "neutral"}
            statusReason={stageHealth.CURATE?.reason}
            metric={state.goldStats ? <MetricChip value={state.goldStats.total} label="labels" color={STAGE_COLORS.CURATE} /> : undefined}
            defaultExpanded
            accentColor={STAGE_COLORS.CURATE}
          >
            <CurateStage queueTotal={state.candidateQueueTotal} />
          </StageCard>
        )}

        {activeStage === "TRAIN" && (
          <StageCard
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
          </StageCard>
        )}

        {activeStage === "EVALUATE" && (
          <StageCard
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
          </StageCard>
        )}

        {activeStage === "DEPLOY" && (
          <StageCard
            title="Deploy"
            status={stageHealth.DEPLOY?.status ?? "neutral"}
            statusReason={stageHealth.DEPLOY?.reason}
            metric={
              state.promotedVersion ? (
                <MetricChip value={state.promotedVersion} label="live" color={STAGE_COLORS.DEPLOY} />
              ) : undefined
            }
            defaultExpanded
            accentColor={STAGE_COLORS.DEPLOY}
          >
            <DeployStage promotedVersion={state.promotedVersion} />
          </StageCard>
        )}

        {activeStage === "MONITOR" && (
          <StageCard
            title="Monitor"
            status={stageHealth.MONITOR?.status ?? "neutral"}
            statusReason={stageHealth.MONITOR?.reason}
            defaultExpanded
            accentColor={STAGE_COLORS.MONITOR}
          >
            <MonitorStage />
          </StageCard>
        )}

        {/* Overview when no stage selected */}
        {!activeStage && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {STAGE_KEYS.map((key) => {
              const h = stageHealth[key] ?? { status: "neutral" as const, reason: "" };
              return (
                <StageCard
                  key={key}
                  title={key}
                  status={h.status}
                  statusReason={h.reason}
                  actionLabel={_stageActionLabel(key)}
                  onAction={() => handleStageClick(key)}
                  accentColor={STAGE_COLORS[key]}
                />
              );
            })}
          </Box>
        )}
      </Box>
    </Box>
  );
}

function _stageActionLabel(stage: string): string {
  const map: Record<string, string> = {
    DISCOVER: "View encounters",
    CURATE: "Review candidates",
    TRAIN: "Train now",
    EVALUATE: "Run safety test",
    DEPLOY: "Manage models",
    MONITOR: "View alerts",
  };
  return map[stage] ?? "Open";
}
