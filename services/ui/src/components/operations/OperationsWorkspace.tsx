"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import BuildOutlinedIcon from "@mui/icons-material/BuildOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ModelTrainingOutlinedIcon from "@mui/icons-material/ModelTrainingOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import RocketLaunchOutlinedIcon from "@mui/icons-material/RocketLaunchOutlined";
import TrackChangesOutlinedIcon from "@mui/icons-material/TrackChangesOutlined";
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

type SectionKey = "fix" | "teach" | "quality" | "deploy" | "process";

type StatusVariant = "ok" | "warn" | "error" | "neutral";

interface SectionStatus {
  label: string;
  variant: StatusVariant;
}

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

// -- Context banner logic ----------------------------------------------------

interface ContextMessage {
  text: string;
  severity: "info" | "warning" | "success";
  action?: { label: string; section: SectionKey };
}

function resolveContextMessage(stats: QuickStats): ContextMessage {
  if (stats.pendingReview > 0) {
    const n = stats.pendingReview;
    return {
      text: `You have ${n} thing${n === 1 ? "" : "s"} to fix. Sort these out before teaching the AI.`,
      severity: "warning",
      action: { label: "Fix them now", section: "fix" },
    };
  }
  if (stats.modelHealth === "neutral") {
    return {
      text: "The AI is not live yet. Teach it some examples, then make it live.",
      severity: "info",
      action: { label: "Teach the AI", section: "teach" },
    };
  }
  if (stats.unacknowledgedAlerts > 0) {
    const n = stats.unacknowledgedAlerts;
    return {
      text: `There ${n === 1 ? "is" : "are"} ${n} quality alert${n === 1 ? "" : "s"} that need${n === 1 ? "s" : ""} your attention.`,
      severity: "warning",
      action: { label: "Check now", section: "quality" },
    };
  }
  return {
    text: `Everything looks good. The AI (${stats.modelVersion}) is live and up to date.`,
    severity: "success",
  };
}

// -- Auto-open logic ---------------------------------------------------------

function resolveDefaultSection(stats: QuickStats): SectionKey {
  if (stats.pendingReview > 0) return "fix";
  if (stats.modelHealth === "neutral") return "teach";
  if (stats.unacknowledgedAlerts > 0) return "quality";
  return "deploy";
}

// -- Tab-to-section map for backward compatibility ---------------------------

const TAB_TO_SECTION: Record<string, SectionKey> = {
  review: "fix",
  fix: "fix",
  train: "teach",
  teach: "teach",
  quality: "quality",
  deploy: "deploy",
  run: "process",
  process: "process",
};

// -- SectionRow component ----------------------------------------------------

interface SectionRowProps {
  sectionKey: SectionKey;
  icon: React.ReactElement;
  label: string;
  statusLabel: string;
  statusVariant: StatusVariant;
  open: boolean;
  onToggle: (key: SectionKey) => void;
  children: React.ReactNode;
}

function SectionRow({
  sectionKey,
  icon,
  label,
  statusLabel,
  statusVariant,
  open,
  onToggle,
  children,
}: SectionRowProps) {
  return (
    <Paper variant="outlined" sx={{ overflow: "hidden", borderRadius: 2 }}>
      <Box
        component="button"
        onClick={() => onToggle(sectionKey)}
        aria-expanded={open}
        aria-controls={`ops-section-${sectionKey}`}
        id={`ops-header-${sectionKey}`}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          width: "100%",
          px: { xs: 2, sm: 2.5 },
          py: 2,
          border: "none",
          bgcolor: open ? "action.selected" : "transparent",
          cursor: "pointer",
          textAlign: "left",
          transition: "background-color 0.15s",
          "&:hover": { bgcolor: open ? "action.selected" : "action.hover" },
        }}
      >
        <Box
          sx={{
            display: "flex",
            color: open ? "primary.main" : "text.secondary",
            flexShrink: 0,
          }}
        >
          {icon}
        </Box>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="subtitle1"
            component="span"
            sx={{
              fontWeight: 700,
              lineHeight: 1.2,
              color: open ? "primary.main" : "text.primary",
              display: "block",
            }}
          >
            {label}
          </Typography>
          <Stack
            direction="row"
            alignItems="center"
            gap={0.75}
            sx={{ mt: 0.25 }}
          >
            <StatusDot variant={statusVariant} size={7} />
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ lineHeight: 1 }}
            >
              {statusLabel}
            </Typography>
          </Stack>
        </Box>

        <ExpandMoreIcon
          sx={{
            color: "text.disabled",
            flexShrink: 0,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        />
      </Box>

      <Collapse in={open} timeout="auto" unmountOnExit>
        <Divider />
        <Box
          id={`ops-section-${sectionKey}`}
          role="region"
          aria-labelledby={`ops-header-${sectionKey}`}
          sx={{ px: { xs: 2, sm: 2.5 }, py: 2.5 }}
        >
          {children}
        </Box>
      </Collapse>
    </Paper>
  );
}

// -- Status helpers ----------------------------------------------------------

function fixStatus(stats: QuickStats | null): SectionStatus {
  if (!stats) return { label: "Loading...", variant: "neutral" };
  if (stats.pendingReview === 0) return { label: "All done", variant: "ok" };
  const n = stats.pendingReview;
  return {
    label: `${n} thing${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} fixing`,
    variant: "warn",
  };
}

function qualityStatus(stats: QuickStats | null): SectionStatus {
  if (!stats) return { label: "Loading...", variant: "neutral" };
  if (stats.unacknowledgedAlerts > 0) {
    const n = stats.unacknowledgedAlerts;
    return { label: `${n} alert${n === 1 ? "" : "s"} to check`, variant: "warn" };
  }
  return { label: "No alerts", variant: "ok" };
}

function deployStatus(stats: QuickStats | null): SectionStatus {
  if (!stats) return { label: "Loading...", variant: "neutral" };
  if (stats.modelHealth === "neutral") return { label: "No AI is live yet", variant: "warn" };
  if (stats.modelHealth === "ok") return { label: `${stats.modelVersion} is live`, variant: "ok" };
  if (stats.modelHealth === "warn") return { label: `${stats.modelVersion} in testing`, variant: "warn" };
  return { label: "Check status", variant: "error" };
}

// -- Main component ----------------------------------------------------------

interface Props {
  initialTab?: string;
}

export default function OperationsWorkspace({ initialTab }: Props) {
  const [statsState, setStatsState] = useState<QuickStats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const [openSection, setOpenSection] = useState<SectionKey | null>(null);
  const [reviewRefreshKey, setReviewRefreshKey] = useState(0);
  const statsFailCount = useRef(0);
  const hasAutoOpened = useRef(false);

  const refresh = useCallback(() => {
    loadQuickStats()
      .then((s) => {
        setStatsState(s);
        setStatsError(false);
        statsFailCount.current = 0;
        if (!hasAutoOpened.current) {
          hasAutoOpened.current = true;
          setOpenSection((prev) => {
            if (prev !== null) return prev;
            return resolveDefaultSection(s);
          });
        }
      })
      .catch(() => {
        statsFailCount.current += 1;
        if (statsFailCount.current >= 3) setStatsError(true);
      });
  }, []);

  useEffect(() => {
    const mapped = initialTab ? (TAB_TO_SECTION[initialTab] ?? null) : null;
    if (mapped) {
      setOpenSection(mapped);
      hasAutoOpened.current = true;
    }
    refresh();
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [refresh, initialTab]);

  const toggle = useCallback((key: SectionKey) => {
    setOpenSection((prev) => (prev === key ? null : key));
  }, []);

  const goToSection = useCallback((key: SectionKey) => {
    setOpenSection(key);
    setTimeout(() => {
      const el = document.getElementById(`ops-header-${key}`);
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 150);
  }, []);

  const ctx = statsState ? resolveContextMessage(statsState) : null;
  const fs = fixStatus(statsState);
  const qs = qualityStatus(statsState);
  const ds = deployStatus(statsState);

  return (
    <Box sx={{ minHeight: "100%", bgcolor: "background.default" }}>
      {/* -- Page header ----------------------------------------------------- */}
      <Box
        component="header"
        sx={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          bgcolor: "background.paper",
          borderBottom: 1,
          borderColor: "divider",
          px: { xs: 2, sm: 3 },
          py: 2,
        }}
      >
        <Typography component="h1" variant="h5" sx={{ fontWeight: 700 }}>
          Operations
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
          Manage, improve and monitor the AI
        </Typography>
      </Box>

      {/* -- Main content ---------------------------------------------------- */}
      <Box sx={{ px: { xs: 2, sm: 3 }, py: 3, maxWidth: 800, mx: "auto" }}>
        <Stack gap={2}>

          {/* Context banner */}
          {statsError ? (
            <Alert severity="warning">
              Could not load status. Some information may be out of date.
            </Alert>
          ) : ctx ? (
            <Alert
              severity={ctx.severity}
              action={
                ctx.action ? (
                  <Button
                    size="small"
                    color="inherit"
                    onClick={() => goToSection(ctx.action!.section)}
                    sx={{ whiteSpace: "nowrap" }}
                  >
                    {ctx.action.label}
                  </Button>
                ) : undefined
              }
            >
              {ctx.text}
            </Alert>
          ) : (
            <Skeleton variant="rounded" height={52} />
          )}

          {/* 1 -- Fix mistakes */}
          <SectionRow
            sectionKey="fix"
            icon={<BuildOutlinedIcon />}
            label="Fix mistakes"
            statusLabel={fs.label}
            statusVariant={fs.variant}
            open={openSection === "fix"}
            onToggle={toggle}
          >
            <ReviewSection
              onStatsChange={() => {
                refresh();
                setReviewRefreshKey((k) => k + 1);
              }}
              refreshKey={reviewRefreshKey}
            />
          </SectionRow>

          {/* 2 -- Teach the AI */}
          <SectionRow
            sectionKey="teach"
            icon={<ModelTrainingOutlinedIcon />}
            label="Teach the AI"
            statusLabel="Build training examples and run a training job"
            statusVariant="neutral"
            open={openSection === "teach"}
            onToggle={toggle}
          >
            <TrainSection />
          </SectionRow>

          {/* 3 -- How is it doing? */}
          <SectionRow
            sectionKey="quality"
            icon={<TrackChangesOutlinedIcon />}
            label="How is it doing?"
            statusLabel={qs.label}
            statusVariant={qs.variant}
            open={openSection === "quality"}
            onToggle={toggle}
          >
            <QualitySection />
          </SectionRow>

          {/* 4 -- Make it live */}
          <SectionRow
            sectionKey="deploy"
            icon={<RocketLaunchOutlinedIcon />}
            label="Make it live"
            statusLabel={ds.label}
            statusVariant={ds.variant}
            open={openSection === "deploy"}
            onToggle={toggle}
          >
            <DeploySection />
          </SectionRow>

          {/* 5 -- Process patients (utility action, not a workflow step) */}
          <SectionRow
            sectionKey="process"
            icon={<PlayArrowOutlinedIcon />}
            label="Process patients"
            statusLabel="Run the pipeline on a set of patient records"
            statusVariant="neutral"
            open={openSection === "process"}
            onToggle={toggle}
          >
            <RunSection />
          </SectionRow>

        </Stack>
      </Box>
    </Box>
  );
}
