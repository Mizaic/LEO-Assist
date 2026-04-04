"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import StatusDot from "./StatusDot";
import ReviewSection from "./ReviewSection";
import RunSection from "./RunSection";
import TrainSection from "./TrainSection";
import DeploySection from "./DeploySection";
import QualitySection from "./QualitySection";

// -- Types -------------------------------------------------------------------

interface QuickStats {
  pendingReview: number;
  resolvedToday: number;
  modelVersion: string;
  modelHealth: "ok" | "warn" | "error" | "neutral";
  unacknowledgedAlerts: number;
}

type TabKey = "run" | "review" | "train" | "quality" | "deploy";

const TAB_ORDER: TabKey[] = ["run", "review", "train", "quality", "deploy"];

const TAB_LABELS: Record<TabKey, string> = {
  run: "Run pipeline",
  review: "Review",
  train: "Train",
  quality: "Quality",
  deploy: "Deploy",
};

// -- Fetch helpers -----------------------------------------------------------

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

async function loadQuickStats(): Promise<QuickStats> {
  const [metrics, model, alertCount] = await Promise.allSettled([
    fetchJson<{ metrics_by_stage: Record<string, Record<string, number>> }>(
      "/api/operations/metrics",
    ),
    fetchJson<{
      active_model: { model_version: string; status: string } | null;
    }>("/api/model-registry/status"),
    fetchJson<{ unacknowledged: number }>("/api/operations/quality/alerts/count"),
  ]);

  let pending = 0;
  let resolved = 0;
  if (metrics.status === "fulfilled") {
    for (const stage of Object.values(metrics.value.metrics_by_stage)) {
      pending += stage.pending ?? 0;
      resolved += (stage.resolved ?? 0) + (stage.dismissed ?? 0);
    }
  }

  let version = "--";
  let health: QuickStats["modelHealth"] = "neutral";
  if (model.status === "fulfilled" && model.value.active_model) {
    version = `v${model.value.active_model.model_version}`;
    const s = model.value.active_model.status;
    health = s === "active" ? "ok" : s === "canary" ? "warn" : "neutral";
  }

  const unacknowledgedAlerts =
    alertCount.status === "fulfilled" ? alertCount.value.unacknowledged : 0;

  return {
    pendingReview: pending,
    resolvedToday: resolved,
    modelVersion: version,
    modelHealth: health,
    unacknowledgedAlerts,
  };
}

// -- Component ---------------------------------------------------------------

interface Props {
  initialTab?: TabKey;
}

export default function OperationsWorkspace({ initialTab = "review" }: Props) {
  const [tab, setTab] = useState<TabKey>(initialTab);
  const [stats, setStats] = useState<QuickStats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const statsFailCount = useRef(0);

  const refresh = useCallback(() => {
    loadQuickStats()
      .then((s) => { setStats(s); setStatsError(false); statsFailCount.current = 0; })
      .catch(() => { statsFailCount.current += 1; if (statsFailCount.current >= 3) setStatsError(true); });
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (
        t instanceof HTMLInputElement ||
        t instanceof HTMLTextAreaElement ||
        t instanceof HTMLSelectElement ||
        t.isContentEditable ||
        t.closest('[role="combobox"]')
      )
        return;
      const idx = parseInt(e.key, 10) - 1;
      if (idx >= 0 && idx < TAB_ORDER.length) {
        setTab(TAB_ORDER[idx]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <Box sx={{ minHeight: "100%", bgcolor: "background.default" }}>
      {/* -- Header --------------------------------------------------------- */}
      <Box
        component="header"
        sx={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          bgcolor: "background.paper",
          borderBottom: 1,
          borderColor: "divider",
          px: { xs: 1.5, sm: 2.5 },
          py: 1,
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          flexWrap="wrap"
          gap={1}
        >
          <Typography component="h1" variant="h5" sx={{ fontWeight: 700 }}>
            Operations
          </Typography>

          {/* Quick-stat chips */}
          <Stack direction="row" gap={1} flexWrap="wrap" aria-label="Quick stats">
            {stats ? (
              <>
                <Chip
                  icon={<StatusDot variant={stats.pendingReview > 0 ? "warn" : "ok"} size={8} />}
                  label={`${stats.pendingReview} to review`}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  icon={<StatusDot variant="ok" size={8} />}
                  label={`${stats.resolvedToday} resolved`}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  icon={<StatusDot variant={stats.modelHealth} size={8} />}
                  label={`Model ${stats.modelVersion}`}
                  size="small"
                  variant="outlined"
                />
              </>
            ) : statsError ? (
              <Chip
                label="Stats unavailable"
                size="small"
                color="error"
                variant="outlined"
                onClick={refresh}
                clickable
              />
            ) : (
              <>
                <Skeleton width={100} height={24} />
                <Skeleton width={90} height={24} />
                <Skeleton width={80} height={24} />
              </>
            )}
          </Stack>
        </Stack>

        {/* -- Tabs --------------------------------------------------------- */}
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{ mt: 0.5 }}
          aria-label="Operations sections"
        >
          {TAB_ORDER.map((key, i) => (
            <Tab
              key={key}
              value={key}
              label={
                key === "review" && stats && stats.pendingReview > 0 ? (
                  <Badge
                    badgeContent={stats.pendingReview}
                    color="warning"
                    max={999}
                    sx={{ "& .MuiBadge-badge": { fontSize: 11 } }}
                  >
                    {TAB_LABELS[key]}
                  </Badge>
                ) : key === "quality" && stats && stats.unacknowledgedAlerts > 0 ? (
                  <Badge
                    badgeContent={stats.unacknowledgedAlerts}
                    color="error"
                    max={99}
                    sx={{ "& .MuiBadge-badge": { fontSize: 11 } }}
                  >
                    {TAB_LABELS[key]}
                  </Badge>
                ) : (
                  TAB_LABELS[key]
                )
              }
              id={`ops-tab-${key}`}
              aria-controls={`ops-panel-${key}`}
              sx={{
                textTransform: "none",
                fontWeight: 600,
                minHeight: 40,
                "&::after": {
                  content: `"${i + 1}"`,
                  ml: 0.75,
                  fontSize: 11,
                  color: "text.disabled",
                },
              }}
            />
          ))}
        </Tabs>
      </Box>

      {/* -- Content -------------------------------------------------------- */}
      <Box sx={{ px: { xs: 1.5, sm: 2.5 }, py: 1.5, maxWidth: 960, mx: "auto" }}>
        <Box
          role="tabpanel"
          id={`ops-panel-${tab}`}
          aria-labelledby={`ops-tab-${tab}`}
        >
          {tab === "run" && <RunSection />}
          {tab === "review" && <ReviewSection onStatsChange={refresh} />}
          {tab === "train" && <TrainSection />}
          {tab === "quality" && <QualitySection />}
          {tab === "deploy" && <DeploySection />}
        </Box>
      </Box>
    </Box>
  );
}
