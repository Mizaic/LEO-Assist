/**
 * AlertsPanel -- list of safety alerts with severity, source, and actions.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { ProgressiveReveal, color } from "@leo/design-system";
import type { AlertRow } from "@/lib/patientEprApi";
import { fetchEprAlerts, patchAlert } from "@/lib/patientEprApi";
import { RecordShowMore } from "./RecordShowMore";
import { RECORD_PAGE_SIZE, remainingCount, visibleSlice } from "./recordPage";

const SEVERITY_CONFIG: Record<
  string,
  { label: string; color: string; bg: string; icon: React.ReactElement }
> = {
  high: {
    label: "HIGH",
    color: "#B91C1C",
    bg: "#FEE2E2",
    icon: <ErrorOutlineIcon fontSize="small" />,
  },
  critical: {
    label: "CRITICAL",
    color: "#7F1D1D",
    bg: "#FCA5A5",
    icon: <ErrorOutlineIcon fontSize="small" />,
  },
  medium: {
    label: "MEDIUM",
    color: "#B45309",
    bg: "#FEF3C7",
    icon: <WarningAmberOutlinedIcon fontSize="small" />,
  },
  low: {
    label: "LOW",
    color: "#047857",
    bg: "#D1FAE5",
    icon: <InfoOutlinedIcon fontSize="small" />,
  },
};

function severityConfig(s: string) {
  return SEVERITY_CONFIG[s.toLowerCase()] ?? SEVERITY_CONFIG.medium;
}

function fmt(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function AlertCard({
  alert,
  patientId,
  onUpdated,
}: {
  alert: AlertRow;
  patientId: string;
  onUpdated: (alertId: string, action: string) => void;
}) {
  const cfg = severityConfig(alert.severity);
  const resolved = Boolean(alert.resolved_at);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function handleAction(action: "resolve" | "escalate" | "review") {
    setBusy(true);
    setActionError(null);
    try {
      await patchAlert(patientId, alert.alert_id, action);
      onUpdated(alert.alert_id, action);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      sx={{
        border: `1px solid ${cfg.color}40`,
        borderRadius: "10px",
        overflow: "hidden",
        mb: 2,
        opacity: resolved ? 0.6 : 1,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2,
          py: 1.25,
          bgcolor: cfg.bg,
          borderBottom: `1px solid ${cfg.color}30`,
        }}
      >
        <Box sx={{ color: cfg.color }}>{cfg.icon}</Box>
        <Chip
          label={cfg.label}
          size="small"
          sx={{ bgcolor: cfg.color, color: "#fff", fontWeight: 700, fontSize: 11, height: 20 }}
        />
        <Typography variant="body2" fontWeight={700} sx={{ flex: 1 }}>
          {alert.alert_type}
        </Typography>
        {resolved && (
          <Stack direction="row" spacing={0.5} alignItems="center">
            <CheckCircleOutlineIcon sx={{ fontSize: 14, color: "#047857" }} />
            <Typography variant="caption" color="#047857">
              Resolved {fmt(alert.resolved_at)}
            </Typography>
          </Stack>
        )}
      </Box>

      <Box sx={{ px: 2, py: 1.5 }}>
        {alert.message && (
          <Typography variant="body2" sx={{ mb: 1 }}>
            {alert.message}
          </Typography>
        )}

        <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ mb: 1 }}>
          {alert.created_at && (
            <Typography variant="caption" sx={{ color: color.text.caption }}>
              Raised: {fmt(alert.created_at)}
            </Typography>
          )}
          {alert.guideline_ref && (
            <Typography variant="caption" sx={{ color: color.text.caption }}>
              Source: {alert.guideline_ref}
            </Typography>
          )}
          {alert.condition_context && (
            <Typography variant="caption" sx={{ color: color.text.caption }}>
              Context: {alert.condition_context}
            </Typography>
          )}
        </Stack>

        {actionError && (
          <Typography variant="caption" color="error" sx={{ display: "block", mb: 1 }}>
            {actionError}
          </Typography>
        )}

        {!resolved && (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="outlined"
              disabled={busy}
              onClick={() => handleAction("review")}
              sx={{ fontSize: 12 }}
            >
              Mark reviewed
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={busy}
              onClick={() => handleAction("resolve")}
              sx={{ fontSize: 12, borderColor: "#047857", color: "#047857" }}
            >
              Resolve
            </Button>
            {(alert.severity === "high" || alert.severity === "critical") && (
              <Button
                size="small"
                variant="contained"
                color="warning"
                disabled={busy}
                onClick={() => handleAction("escalate")}
                sx={{ fontSize: 12 }}
              >
                Escalate
              </Button>
            )}
          </Stack>
        )}
      </Box>
    </Box>
  );
}

interface Props {
  patientId: string;
}

export function AlertsPanel({ patientId }: Props) {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState(RECORD_PAGE_SIZE);

  useEffect(() => {
    setLoading(true);
    fetchEprAlerts(patientId)
      .then(setAlerts)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load alerts."))
      .finally(() => setLoading(false));
  }, [patientId]);

  function handleAlertUpdated(alertId: string, action: string) {
    setAlerts((prev) =>
      prev.map((a) => {
        if (a.alert_id !== alertId) return a;
        const now = new Date().toISOString();
        return {
          ...a,
          resolved_at: action === "resolve" ? now : a.resolved_at,
        };
      })
    );
  }

  if (loading) {
    return (
      <Stack spacing={1.5}>
        {[1, 2].map((i) => <Skeleton key={i} variant="rounded" height={120} />)}
      </Stack>
    );
  }

  if (error) return <Alert severity="error">{error}</Alert>;

  const active = alerts.filter((a) => !a.resolved_at);
  const resolved = alerts.filter((a) => Boolean(a.resolved_at));
  const visibleActive = visibleSlice(active, shown);

  if (alerts.length === 0) {
    return <Alert severity="success">No safety alerts on record for this patient.</Alert>;
  }

  return (
    <Box>
      {active.length > 0 && (
        <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
          Active ({active.length})
        </Typography>
      )}
      {visibleActive.map((a) => (
        <AlertCard key={a.alert_id} alert={a} patientId={patientId} onUpdated={handleAlertUpdated} />
      ))}
      <RecordShowMore
        remaining={remainingCount(active.length, shown)}
        onShowMore={() => setShown((n) => n + RECORD_PAGE_SIZE)}
      />

      {resolved.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <ProgressiveReveal summary={`Resolved (${resolved.length})`}>
            {resolved.map((a) => (
              <AlertCard
                key={a.alert_id}
                alert={a}
                patientId={patientId}
                onUpdated={handleAlertUpdated}
              />
            ))}
          </ProgressiveReveal>
        </Box>
      )}
    </Box>
  );
}
