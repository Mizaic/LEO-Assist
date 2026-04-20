/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B1116B14
 *   DI: DI-35494904
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B1116B14")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Skeleton from "@mui/material/Skeleton";
import Typography from "@mui/material/Typography";
import { actionSafetyNetAlert, fetchSafetyNetWorklist } from "@/lib/analyticsApi";
import type { SafetyNetWorklistItem } from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import WorklistSummaryCards from "@/components/safety-netting/WorklistSummaryCards";
import WorklistFilters from "@/components/safety-netting/WorklistFilters";
import type { WorklistFilterState } from "@/components/safety-netting/WorklistFilters";
import PatientPathwayWorklist from "@/components/safety-netting/PatientPathwayWorklist";
import type { SafetyNetWorklistRow } from "@/components/safety-netting/PatientPathwayWorklist";
import PathwayDetailPanel from "@/components/safety-netting/PathwayDetailPanel";
import { assessPathwayRisk, normalizeMilestones } from "@/lib/pathwayRisk";

const INITIAL_FILTERS: WorklistFilterState = {
  search: "",
  cancerSite: "all",
  stage: "all",
  rag: "all",
  actioned: "all",
};

function stageLabel(row: SafetyNetWorklistRow): string {
  switch (row.risk.nextExpectedMilestone) {
    case "presentation":
    case "referral":
      return "Referred";
    case "first_clinic":
      return "Booked / First Seen";
    case "diagnosis":
      return "Diagnostics";
    default:
      return "Outcome";
  }
}

export default function SafetyNettingPage() {
  const orgId = useOrgId();
  const [items, setItems] = useState<SafetyNetWorklistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<WorklistFilterState>(INITIAL_FILTERS);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchSafetyNetWorklist(orgId)
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [orgId]);

  const rows = useMemo<SafetyNetWorklistRow[]>(() => {
    return items
      .map((item) => {
        const normalizedMilestones = normalizeMilestones(item.milestones);
        const risk = assessPathwayRisk(
          {
            episode_id: item.episode_id,
            patient_id: item.patient_id,
            condition_type: item.condition_type ?? "Unknown",
            status: item.status ?? "unknown",
            referral_date: item.referral_date,
            milestones: normalizedMilestones,
          },
        );
        return { ...item, normalizedMilestones, risk };
      })
      .sort((a, b) => a.risk.sortKey - b.risk.sortKey);
  }, [items]);

  const cancerSites = useMemo(
    () =>
      Array.from(new Set(rows.map((r) => r.condition_type).filter(Boolean) as string[])).sort(),
    [rows],
  );

  const stages = useMemo(
    () => Array.from(new Set(rows.map((r) => stageLabel(r)))).sort(),
    [rows],
  );

  const filteredRows = useMemo(() => {
    const q = filters.search.trim().toLowerCase();
    return rows.filter((row) => {
      if (filters.cancerSite !== "all" && row.condition_type !== filters.cancerSite) return false;
      if (filters.stage !== "all" && stageLabel(row) !== filters.stage) return false;
      if (filters.rag !== "all" && row.risk.level !== filters.rag) return false;

      const outstanding = row.alerts.some((a) => !a.actioned);
      const actionedOnly = row.alerts.length > 0 && row.alerts.every((a) => a.actioned);
      if (filters.actioned === "outstanding" && !outstanding) return false;
      if (filters.actioned === "actioned" && !actionedOnly) return false;

      if (q) {
        const haystack = [
          row.patient_id,
          row.condition_type,
          row.episode_id,
          ...row.alerts.map((a) => a.description),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [rows, filters]);

  const selected = useMemo(
    () => rows.find((r) => r.episode_id === selectedEpisodeId) ?? null,
    [rows, selectedEpisodeId],
  );

  const handleAction = useCallback(
    async (alertId: string, actioned: boolean) => {
      setActionLoading(true);
      try {
        await actionSafetyNetAlert(alertId, actioned);
        setItems((prev) =>
          prev.map((item) => ({
            ...item,
            alerts: item.alerts.map((a) => (a.id === alertId ? { ...a, actioned } : a)),
          })),
        );
      } catch {
        // Keep previous local state if API call fails.
      } finally {
        setActionLoading(false);
      }
    },
    [],
  );

  const summary = useMemo(() => {
    const totalActive = rows.length;
    const overdueBreached = rows.filter((r) => r.risk.level === "breached").length;
    const atRisk = rows.filter((r) => r.risk.level === "at-risk").length;
    const onTrack = rows.filter((r) => r.risk.level === "on-track").length;
    const actionRequired = rows.filter((r) => r.alerts.some((a) => !a.actioned)).length;
    return { totalActive, overdueBreached, atRisk, onTrack, actionRequired };
  }, [rows]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <Box sx={{ px: { xs: 2, md: 3.5 }, pt: 3, pb: 1.5 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
          Safety Netting
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          Clinical safety signals aligned with NG12 &ndash; review, triage and
          action
        </Typography>

        {loading ? (
          <Skeleton variant="rounded" height={84} sx={{ mb: 2 }} />
        ) : (
          <WorklistSummaryCards summary={summary} />
        )}

        {!loading && (
          <WorklistFilters
            filters={filters}
            onChange={setFilters}
            cancerSites={cancerSites}
            stages={stages}
          />
        )}

        {!loading && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 1.5, mb: 0 }}
          >
            {`${filteredRows.length} pathways shown (${rows.length} total active)`}
          </Typography>
        )}
      </Box>

      <Box
        sx={{
          flex: 1,
          display: "flex",
          minHeight: 0,
          borderTop: "1px solid",
          borderColor: "divider",
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
          {loading ? (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
              }}
            >
              <CircularProgress aria-label="Loading" size={22} />
            </Box>
          ) : (
            <PatientPathwayWorklist
              rows={filteredRows}
              selectedEpisodeId={selectedEpisodeId}
              onSelect={(row) => setSelectedEpisodeId(row.episode_id)}
            />
          )}
        </Box>

        {selected && (
          <PathwayDetailPanel
            row={selected}
            onClose={() => setSelectedEpisodeId(null)}
            onActionAlert={handleAction}
            actionLoading={actionLoading}
          />
        )}
      </Box>
    </Box>
  );
}
