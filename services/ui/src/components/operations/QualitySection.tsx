/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-720CD183
 *   DI: DI-1126FFD1
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-720CD183")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import ConfirmDialog from "@/components/ConfirmDialog";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DriftPoint {
  week_start: string;
  pct_clean: number | null;
  critical_count: number | null;
  overcoded_count: number | null;
  pct_clean_by_domain: string | null;
  model_version_changed: boolean | null;
  auditor_model_version: string | null;
}

interface AuditRun {
  run_id: string;
  status: string;
  since_date: string;
  until_date: string;
  encounter_count: number | null;
  pct_clean: number | null;
  cost_usd: number | null;
  triggered_by: string | null;
  started_at: string | null;
  completed_at: string | null;
}

interface QualityAlert {
  alert_id: string;
  alert_type: string;
  description: string;
  severity: string;
  escalation_level: number | null;
  acknowledged_at: string | null;
}

interface LoopConfig {
  loop_id: string;
  description: string;
  enabled: boolean;
  updated_by: string | null;
  updated_at: string | null;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, "success" | "warning" | "error" | "default"> = {
  complete: "success",
  running: "warning",
  failed: "error",
};

const SEVERITY_COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "warning",
  medium: "info",
};

const LOOP_LABELS: Record<string, string> = {
  loop1_audit: "Weekly quality check",
  loop2_surface_form: "Dictionary learning",
  loop3_evidence: "Training data collection",
};

const LOOP_HINTS: Record<string, string> = {
  loop1_audit: "Runs every Monday to check how well the AI is coding encounters.",
  loop2_surface_form: "Learns new word-to-code mappings from reviewed encounters.",
  loop3_evidence: "Collects labelled examples to train the next AI model.",
};

function RunStatusChip({ status }: { status: string }) {
  return (
    <Chip
      label={status}
      size="small"
      color={STATUS_COLORS[status] ?? "default"}
    />
  );
}

function SeverityChip({ severity }: { severity: string }) {
  return (
    <Chip
      label={severity}
      size="small"
      color={SEVERITY_COLORS[severity] ?? "default"}
    />
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function QualitySection() {
  const [drift, setDrift] = useState<DriftPoint[]>([]);
  const [runs, setRuns] = useState<AuditRun[]>([]);
  const [alerts, setAlerts] = useState<QualityAlert[]>([]);
  const [configs, setConfigs] = useState<LoopConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [triggerBusy, setTriggerBusy] = useState(false);
  const [ackBusy, setAckBusy] = useState<string | null>(null);
  const [configBusy, setConfigBusy] = useState<string | null>(null);
  const [confirmTrigger, setConfirmTrigger] = useState(false);
  const [totalCost, setTotalCost] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [driftRes, runsRes, alertsRes, configRes] = await Promise.allSettled([
        apiFetch<{ series: DriftPoint[] }>("/api/operations/quality/drift?weeks=12"),
        apiFetch<{ items: AuditRun[] }>("/api/operations/quality/runs?page=1&page_size=5"),
        apiFetch<{ items: QualityAlert[] }>("/api/operations/quality/alerts?unacknowledged_only=true"),
        apiFetch<{ configs: LoopConfig[] }>("/api/operations/quality/config"),
      ]);

      if (driftRes.status === "fulfilled") setDrift(driftRes.value.series);
      if (runsRes.status === "fulfilled") {
        const items = runsRes.value.items;
        setRuns(items.slice(0, 5));
        const cost = items
          .slice(0, 4)
          .reduce((sum, r) => sum + (r.cost_usd ?? 0), 0);
        setTotalCost(cost);
      }
      if (alertsRes.status === "fulfilled") setAlerts(alertsRes.value.items);
      if (configRes.status === "fulfilled") setConfigs(configRes.value.configs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load quality data. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleTrigger() {
    setTriggerBusy(true);
    try {
      await apiFetch("/api/operations/quality/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ since_days: 7, triggered_by: "manual" }),
      });
      await load();
    } catch {
      setError("Could not start the quality check. Please try again.");
    } finally {
      setTriggerBusy(false);
      setConfirmTrigger(false);
    }
  }

  async function handleAcknowledge(alertId: string) {
    setAckBusy(alertId);
    try {
      await apiFetch(`/api/operations/quality/alerts/${alertId}/acknowledge`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ acknowledged_by: "operations_ui" }),
      });
      setAlerts((prev) => prev.filter((a) => a.alert_id !== alertId));
    } catch {
      setError("Could not acknowledge alert. Please try again.");
    } finally {
      setAckBusy(null);
    }
  }

  async function handleToggleLoop(loopId: string, enabled: boolean) {
    setConfigBusy(loopId);
    try {
      await apiFetch(`/api/operations/quality/config/${loopId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      setConfigs((prev) =>
        prev.map((c) => (c.loop_id === loopId ? { ...c, enabled } : c)),
      );
    } catch {
      setError("Could not update loop setting. Please try again.");
    } finally {
      setConfigBusy(null);
    }
  }

  if (loading) {
    return (
      <Stack gap={2}>
        <Skeleton height={8} />
        <Skeleton variant="rounded" height={240} />
        <Skeleton variant="rounded" height={120} />
      </Stack>
    );
  }

  const chartData = drift.map((d) => ({
    week: d.week_start ? d.week_start.slice(0, 10) : "",
    accuracy: d.pct_clean ?? undefined,
    urgent: d.critical_count ?? undefined,
    overcoded: d.overcoded_count ?? undefined,
    model_changed: d.model_version_changed ?? false,
  }));

  const versionChangeWeeks = chartData
    .filter((d) => d.model_changed)
    .map((d) => d.week);

  return (
    <Stack gap={2.5}>
      {error && (
        <Alert severity="error" onClose={() => setError("")}>
          {error}
        </Alert>
      )}

      {/* -- Trend chart ----------------------------------------------------- */}
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Coding accuracy over time
            </Typography>
            <Button
              variant="outlined"
              size="small"
              disabled={triggerBusy}
              onClick={() => setConfirmTrigger(true)}
              startIcon={triggerBusy ? <CircularProgress size={14} aria-label="Loading" /> : null}
            >
              Run quality check now
            </Button>
          </Stack>

          {chartData.length === 0 ? (
            <Alert severity="info" sx={{ mt: 1 }}>
              No data yet. Run a quality check to see results here.
            </Alert>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="pct" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <YAxis yAxisId="count" orientation="right" tick={{ fontSize: 11 }} />
                <ChartTooltip
                  formatter={(value, name) => {
                    const n = value ?? 0;
                    const label = name ?? "";
                    if (label === "Coding accuracy (%)") return [`${n}%`, label];
                    return [n, label];
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {versionChangeWeeks.map((w) => (
                  <ReferenceLine
                    key={w}
                    yAxisId="pct"
                    x={w}
                    stroke="#9e9e9e"
                    strokeDasharray="4 4"
                    label={{ value: "Checker updated", position: "top", fontSize: 10 }}
                  />
                ))}
                <Line
                  yAxisId="pct"
                  type="monotone"
                  dataKey="accuracy"
                  name="Coding accuracy (%)"
                  stroke="#1F3A8A"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="count"
                  type="monotone"
                  dataKey="urgent"
                  name="Urgent items"
                  stroke="#d32f2f"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  yAxisId="count"
                  type="monotone"
                  dataKey="overcoded"
                  name="Overcoded items"
                  stroke="#ed6c02"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* -- Run history + cost tracker -------------------------------------- */}
      <Stack direction={{ xs: "column", sm: "row" }} gap={2}>
        <Card variant="outlined" sx={{ flex: 2 }}>
          <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
              Recent checks
            </Typography>
            {runs.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No checks run yet.
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontSize: 11 }}>Started</TableCell>
                    <TableCell sx={{ fontSize: 11 }}>Encounters</TableCell>
                    <TableCell sx={{ fontSize: 11 }}>Accuracy</TableCell>
                    <TableCell sx={{ fontSize: 11 }}>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {runs.map((r) => (
                    <TableRow key={r.run_id} hover>
                      <TableCell sx={{ fontSize: 11 }}>
                        {r.started_at ? r.started_at.slice(0, 10) : "--"}
                      </TableCell>
                      <TableCell sx={{ fontSize: 11 }}>
                        {r.encounter_count ?? "--"}
                      </TableCell>
                      <TableCell sx={{ fontSize: 11 }}>
                        {r.pct_clean != null ? `${r.pct_clean}%` : "--"}
                      </TableCell>
                      <TableCell>
                        <RunStatusChip status={r.status} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
              Cost (last 4 checks)
            </Typography>
            {totalCost != null ? (
              <Typography variant="h5" sx={{ fontWeight: 700, color: "text.primary" }}>
                ${totalCost.toFixed(2)}
              </Typography>
            ) : (
              <Skeleton width={80} height={36} />
            )}
            <Typography variant="caption" color="text.secondary">
              Estimated AI model cost
            </Typography>
          </CardContent>
        </Card>
      </Stack>

      {/* -- Alerts ---------------------------------------------------------- */}
      {alerts.length > 0 && (
        <Card variant="outlined">
          <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
              Alerts needing attention
            </Typography>
            <Stack gap={1}>
              {alerts.map((a) => (
                <Box
                  key={a.alert_id}
                  sx={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 1,
                    p: 1,
                    borderRadius: 1,
                    border: "1px solid",
                    borderColor: "divider",
                  }}
                >
                  <SeverityChip severity={a.severity ?? "medium"} />
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {a.alert_type.replace(/_/g, " ")}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {a.description}
                    </Typography>
                    {(a.escalation_level ?? 0) > 0 && (
                      <Chip
                        label={`Escalation level ${a.escalation_level}`}
                        size="small"
                        color="error"
                        sx={{ ml: 1, height: 18, fontSize: 10 }}
                      />
                    )}
                  </Box>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={ackBusy === a.alert_id}
                    onClick={() => handleAcknowledge(a.alert_id)}
                    startIcon={
                      ackBusy === a.alert_id ? (
                        <CircularProgress size={12} aria-label="Loading" />
                      ) : null
                    }
                  >
                    Acknowledge
                  </Button>
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* -- Loop toggles ---------------------------------------------------- */}
      <Card variant="outlined">
        <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>
            Learning loops
          </Typography>
          <Stack gap={1.5} divider={<Divider flexItem />}>
            {configs.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No loop settings loaded.
              </Typography>
            ) : (
              configs.map((c) => (
                <Box key={c.loop_id}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={c.enabled}
                        disabled={configBusy === c.loop_id}
                        onChange={(_, v) => handleToggleLoop(c.loop_id, v)}
                        aria-label={`Toggle ${LOOP_LABELS[c.loop_id] ?? c.loop_id}`}
                        size="small"
                      />
                    }
                    label={
                      <Box>
                        <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                          {LOOP_LABELS[c.loop_id] ?? c.loop_id}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {LOOP_HINTS[c.loop_id] ?? ""}
                        </Typography>
                      </Box>
                    }
                  />
                </Box>
              ))
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* -- Confirm trigger ------------------------------------------------- */}
      {confirmTrigger && (
        <ConfirmDialog
          title="Run quality check now?"
          body="This will start a new AI quality check on recent encounters. It may take several minutes and will use AI credits."
          confirmLabel="Start check"
          onConfirm={handleTrigger}
          onCancel={() => setConfirmTrigger(false)}
        />
      )}
    </Stack>
  );
}
