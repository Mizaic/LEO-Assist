"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Grid from "@mui/material/Grid";
import Chip from "@mui/material/Chip";
import { fetchSafetyNetAlerts, actionSafetyNetAlert } from "@/lib/analyticsApi";
import type { SafetyNetAlert } from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import AlertFilters from "@/components/safety-netting/AlertFilters";
import type { AlertFilterState, ViewMode } from "@/components/safety-netting/AlertFilters";
import AlertWorklist from "@/components/safety-netting/AlertWorklist";
import AlertDetailPanel from "@/components/safety-netting/AlertDetailPanel";

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

const INITIAL_FILTERS: AlertFilterState = {
  search: "",
  severity: null,
  type: null,
  actionedFilter: "outstanding",
};

export default function SafetyNetAlertsPage() {
  const orgId = useOrgId();
  const [alerts, setAlerts] = useState<SafetyNetAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<AlertFilterState>(INITIAL_FILTERS);
  const [selected, setSelected] = useState<SafetyNetAlert | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("grouped");

  useEffect(() => {
    setLoading(true);
    fetchSafetyNetAlerts(orgId)
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }, [orgId]);

  const filtered = useMemo(() => {
    const q = filters.search.toLowerCase();
    return alerts
      .filter((a) => {
        if (filters.actionedFilter === "outstanding" && a.actioned) return false;
        if (filters.actionedFilter === "actioned" && !a.actioned) return false;
        if (filters.severity && a.severity !== filters.severity) return false;
        if (filters.type && a.type !== filters.type) return false;
        if (q) {
          const haystack = [
            a.type, a.description, a.patient_id, a.condition_type, a.episode_id,
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          if (!haystack.includes(q)) return false;
        }
        return true;
      })
      .sort(
        (a, b) =>
          (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99),
      );
  }, [alerts, filters]);

  const handleAction = useCallback(
    async (alertId: string, actioned: boolean) => {
      setActionLoading(true);
      try {
        await actionSafetyNetAlert(alertId, actioned);
        setAlerts((prev) =>
          prev.map((a) => (a.id === alertId ? { ...a, actioned } : a)),
        );
        setSelected((prev) =>
          prev?.id === alertId ? { ...prev, actioned } : prev,
        );
      } catch {
        // Silently fail -- alert stays in previous state
      } finally {
        setActionLoading(false);
      }
    },
    [],
  );

  const outstanding = alerts.filter((a) => !a.actioned).length;
  const criticalHigh = alerts.filter(
    (a) => !a.actioned && (a.severity === "critical" || a.severity === "high"),
  ).length;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <Box sx={{ p: 3, pb: 0 }}>
        <Typography variant="h5" sx={{ mb: 0.5 }}>
          Safety Netting
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          Clinical safety signals aligned with NG12 -- review, triage and action
        </Typography>

        {loading ? (
          <Grid container spacing={2} sx={{ mb: 2.5 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <Grid key={i} size={{ xs: 6, sm: 3 }}>
                <Card>
                  <CardContent sx={{ py: 2 }}>
                    <Skeleton width={80} height={20} />
                    <Skeleton width={50} height={36} />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        ) : (
          <Grid container spacing={2} sx={{ mb: 2.5 }}>
            <Grid size={{ xs: 6, sm: 3 }}>
              <SummaryCard label="Total alerts" value={alerts.length} />
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <SummaryCard
                label="Outstanding"
                value={outstanding}
                color="warning.main"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <SummaryCard
                label="Critical / High"
                value={criticalHigh}
                color="error.main"
                badge={criticalHigh > 0 ? "action needed" : undefined}
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <SummaryCard
                label="Actioned"
                value={alerts.length - outstanding}
                color="success.main"
              />
            </Grid>
          </Grid>
        )}

        {!loading && (
          <AlertFilters
            filters={filters}
            onChange={setFilters}
            alerts={alerts}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
          />
        )}

        {!loading && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 1.5, mb: 0.5 }}
          >
            {viewMode === "grouped"
              ? `${new Set(filtered.map((a) => a.patient_id ?? "Unknown")).size} patients, ${filtered.length} alerts`
              : `Showing ${filtered.length} of ${alerts.length} alerts`}
          </Typography>
        )}
      </Box>

      <Box sx={{ flex: 1, display: "flex", minHeight: 0 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {loading ? (
            <Box sx={{ px: 3, pt: 1 }}>
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} variant="rounded" height={44} sx={{ mb: 0.5 }} />
              ))}
            </Box>
          ) : (
            <AlertWorklist
              alerts={filtered}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
              viewMode={viewMode}
            />
          )}
        </Box>

        {selected && (
          <AlertDetailPanel
            alert={selected}
            onClose={() => setSelected(null)}
            onAction={handleAction}
            actionLoading={actionLoading}
          />
        )}
      </Box>
    </Box>
  );
}

function SummaryCard({
  label,
  value,
  color,
  badge,
}: {
  label: string;
  value: number;
  color?: string;
  badge?: string;
}) {
  return (
    <Card>
      <CardContent sx={{ py: 2 }}>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 0.5, fontSize: "0.8rem" }}
        >
          {label}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="h4" sx={{ fontSize: "1.8rem", color }}>
            {value}
          </Typography>
          {badge && <Chip label={badge} size="small" color="error" />}
        </Box>
      </CardContent>
    </Card>
  );
}
