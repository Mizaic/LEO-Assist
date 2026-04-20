/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CommandBar from "./CommandBar";
import KPIStrip from "./KPIStrip";
import PatientCaseTable from "./PatientCaseTable";
import PatientDetailDrawer from "./PatientDetailDrawer";
import type { MissionEpisode, MissionKPIs, MissionPatient } from "@/lib/missionControlApi";
import {
  fetchMissionKPIs,
  fetchMissionPatients,
  fetchPatientRebuildStatus,
} from "@/lib/missionControlApi";
import { useOrgId } from "@/context/OrgContext";
import { useAnalyticsDateFilter } from "@/context/AnalyticsDateFilterContext";
import {
  DEFAULT_FILTERS,
  deserialiseFilters,
  type MissionControlFilters,
} from "@/lib/missionControlFilters";

const USER_EMAIL_PLACEHOLDER = "auditor@nhs.net";
const ACTIVE_REBUILD_STATUSES = new Set(["queued", "running"]);

type DrawerTab = "overview" | "coded" | "encounters" | "audit";

function parseDrawerTab(tab: string | null): DrawerTab {
  if (tab === "coded") return "coded";
  if (tab === "encounters" || tab === "encounter-text" || tab === "text") return "encounters";
  if (tab === "audit") return "audit";
  return "overview";
}

export default function MissionControl() {
  const searchParams = useSearchParams();
  const orgId = useOrgId();
  const {
    dateFrom: sharedDateFrom,
    dateTo: sharedDateTo,
    appliedFrom,
    appliedTo,
    setDateFrom: setSharedDateFrom,
    setDateTo: setSharedDateTo,
    apply: applySharedDate,
    clear: clearSharedDate,
  } = useAnalyticsDateFilter();

  // Initialise draft filters from URL params (enables audit page deep-links)
  const initFilters = useCallback((): MissionControlFilters => {
    const fromUrl = searchParams
      ? deserialiseFilters(new URLSearchParams(searchParams.toString()))
      : DEFAULT_FILTERS;
    return {
      ...fromUrl,
      // Respect shared org/date filters unless explicitly provided via URL.
      orgId: fromUrl.orgId || orgId || "",
      dateFrom: fromUrl.dateFrom || appliedFrom || "",
      dateTo: fromUrl.dateTo || appliedTo || "",
    };
  }, [searchParams, orgId, appliedFrom, appliedTo]);

  const [draft, setDraft] = useState<MissionControlFilters>(initFilters);
  const [applied, setApplied] = useState<MissionControlFilters>(initFilters);

  const [patients, setPatients] = useState<MissionPatient[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sortBy, setSortBy] = useState("referral_date");
  const [sortDir, setSortDir] = useState<"ASC" | "DESC">("DESC");

  const [kpis, setKpis] = useState<MissionKPIs | null>(null);
  const [kpisLoading, setKpisLoading] = useState(false);
  const [tableLoading, setTableLoading] = useState(false);
  const [tableError, setTableError] = useState<string | null>(null);

  const [selectedPatient, setSelectedPatient] = useState<MissionPatient | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("overview");

  const requestedDrawer = useMemo(() => {
    const patientId =
      searchParams?.get("patient") ?? searchParams?.get("patient_id") ?? "";
    const tab = parseDrawerTab(searchParams?.get("tab"));
    return { patientId, tab };
  }, [searchParams]);
  const [drawerRequestConsumed, setDrawerRequestConsumed] = useState(
    !requestedDrawer.patientId
  );

  useEffect(() => {
    setDrawerRequestConsumed(!requestedDrawer.patientId);
  }, [requestedDrawer.patientId, requestedDrawer.tab]);

  const withSharedScope = useCallback(
    (filters: MissionControlFilters): MissionControlFilters => ({
      ...filters,
      orgId: orgId || "",
      dateFrom: appliedFrom || filters.dateFrom,
      dateTo: appliedTo || filters.dateTo,
    }),
    [orgId, appliedFrom, appliedTo]
  );

  // Abort controller reference to cancel stale requests
  const abortRef = useRef<AbortController | null>(null);

  const loadData = useCallback(
    async (filters: MissionControlFilters, p: number, ps: number, sb: string, sd: string) => {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();

      setTableLoading(true);
      setTableError(null);
      setKpisLoading(true);

      try {
        const scopedFilters = withSharedScope(filters);
        const [kpiResult, patientResult] = await Promise.all([
          fetchMissionKPIs(scopedFilters),
          fetchMissionPatients(scopedFilters, p, ps),
        ]);
        const awaiting = patientResult.patients.filter(
          (pt) => (pt.episodes?.length ?? 0) === 0
        );
        let rebuildMap: Record<string, Awaited<ReturnType<typeof fetchPatientRebuildStatus>> | null> = {};
        if (awaiting.length > 0) {
          const statuses = await Promise.all(
            awaiting.map(async (pt) => {
              try {
                const status = await fetchPatientRebuildStatus(pt.patient_id, {
                  orgId: scopedFilters.orgId || undefined,
                });
                return [pt.patient_id, status] as const;
              } catch {
                return [pt.patient_id, null] as const;
              }
            })
          );
          rebuildMap = Object.fromEntries(statuses);
        }
        const enrichedPatients = patientResult.patients.map((pt) => ({
          ...pt,
          rebuild_status: rebuildMap[pt.patient_id] ?? null,
        }));
        setKpis(kpiResult);
        setPatients(enrichedPatients);
        setTotal(patientResult.total);
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setTableError(e instanceof Error ? e.message : "Could not load patient data.");
        }
      } finally {
        setTableLoading(false);
        setKpisLoading(false);
      }
    },
    [withSharedScope]
  );

  // Load on mount (applies URL param filters) and when applied/pagination changes
  useEffect(() => {
    loadData(applied, page, pageSize, sortBy, sortDir);
  }, [applied, page, pageSize, sortBy, sortDir, loadData]);

  // Refresh rebuild statuses for rows that are still awaiting rebuild.
  useEffect(() => {
    const awaiting = patients.filter(
      (pt) =>
        (pt.episodes?.length ?? 0) === 0 &&
        ACTIVE_REBUILD_STATUSES.has(pt.rebuild_status?.status ?? "")
    );
    if (awaiting.length === 0) return;

    let polling = false;
    const interval = window.setInterval(async () => {
      if (polling) return;
      polling = true;
      const updates = await Promise.all(
        awaiting.map(async (pt) => {
          try {
            const status = await fetchPatientRebuildStatus(pt.patient_id, {
              orgId: applied.orgId || undefined,
            });
            return [pt.patient_id, status] as const;
          } catch {
            return [pt.patient_id, null] as const;
          }
        })
      );
      const map = Object.fromEntries(updates);
      const hasCompleted = Object.values(map).some(
        (status) => status?.status === "completed"
      );
      setPatients((prev) =>
        prev.map((pt) =>
          (pt.episodes?.length ?? 0) === 0
            ? { ...pt, rebuild_status: map[pt.patient_id] ?? pt.rebuild_status ?? null }
            : pt
        )
      );
      if (hasCompleted) {
        await loadData(applied, page, pageSize, sortBy, sortDir);
      }
      polling = false;
    }, 8000);
    return () => window.clearInterval(interval);
  }, [patients, applied.orgId, loadData, applied, page, pageSize, sortBy, sortDir]);

  // Keep Mission Control in sync with shared org/date filters from the app shell/audit flow.
  useEffect(() => {
    const nextOrg = orgId || "";
    const nextFrom = appliedFrom || "";
    const nextTo = appliedTo || "";
    setDraft((prev) => ({ ...prev, orgId: nextOrg, dateFrom: nextFrom, dateTo: nextTo }));
    setApplied((prev) => ({ ...prev, orgId: nextOrg, dateFrom: nextFrom, dateTo: nextTo }));
    setPage(1);
  }, [orgId, appliedFrom, appliedTo]);

  // Keep Mission Control draft date fields visually aligned with shared date inputs.
  useEffect(() => {
    setDraft((prev) => ({
      ...prev,
      dateFrom: sharedDateFrom || prev.dateFrom,
      dateTo: sharedDateTo || prev.dateTo,
    }));
  }, [sharedDateFrom, sharedDateTo]);

  const handleApply = () => {
    setSharedDateFrom(draft.dateFrom || "");
    setSharedDateTo(draft.dateTo || "");
    applySharedDate();
    setApplied({ ...draft });
    setPage(1);
  };

  const handleClear = () => {
    clearSharedDate();
    setDraft(DEFAULT_FILTERS);
    setApplied(DEFAULT_FILTERS);
    setPage(1);
  };

  const handleSortChange = (col: string) => {
    if (col === sortBy) {
      setSortDir((d) => (d === "DESC" ? "ASC" : "DESC"));
    } else {
      setSortBy(col);
      setSortDir("DESC");
    }
    setPage(1);
  };

  const handleEpisodeUpdated = (
    patientId: string,
    episodeId: string,
    patch: Partial<MissionEpisode>
  ) => {
    setPatients((prev) =>
      prev.map((p) => {
        if (p.patient_id !== patientId) return p;
        return {
          ...p,
          episodes: p.episodes.map((ep) =>
            ep.episode_id === episodeId ? { ...ep, ...patch } : ep
          ),
        };
      })
    );
    if (selectedPatient?.patient_id === patientId) {
      setSelectedPatient((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          episodes: prev.episodes.map((ep) =>
            ep.episode_id === episodeId ? { ...ep, ...patch } : ep
          ),
        };
      });
    }
  };

  const handlePatientRebuilt = async (_patientId: string) => {
    await loadData(applied, page, pageSize, sortBy, sortDir);
    // Episode graph can shift after a rebuild; closing avoids stale drawer context.
    setSelectedPatient(null);
  };

  const handleOpenPatient = useCallback(
    (patient: MissionPatient, tab: DrawerTab = "overview") => {
      setDrawerTab(tab);
      setSelectedPatient(patient);
    },
    []
  );

  useEffect(() => {
    if (drawerRequestConsumed || !requestedDrawer.patientId) {
      return;
    }
    const match = patients.find((p) => p.patient_id === requestedDrawer.patientId);
    if (!match) {
      return;
    }
    handleOpenPatient(match, requestedDrawer.tab);
    setDrawerRequestConsumed(true);
  }, [
    drawerRequestConsumed,
    requestedDrawer.patientId,
    requestedDrawer.tab,
    patients,
    handleOpenPatient,
  ]);

  return (
    <Box sx={{ maxWidth: 1400, mx: "auto", p: 3, display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Page heading */}
      <Box>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
          Mission Control
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Find, review, and validate cancer pathway episodes before decisions are made on
          this data.
        </Typography>
      </Box>

      {/* Filters */}
      <CommandBar
        draft={draft}
        onChange={(patch, applyNow = false) => {
          setDraft((prev) => {
            const next = { ...prev, ...patch };
            if (applyNow) {
              setApplied(next);
            }
            return next;
          });
          if (applyNow) {
            setPage(1);
          }
        }}
        onApply={handleApply}
        onClear={handleClear}
      />

      {/* KPI strip */}
      <KPIStrip kpis={kpis} loading={kpisLoading} />

      {/* Patient case table */}
      <PatientCaseTable
        patients={patients}
        total={total}
        page={page}
        pageSize={pageSize}
        sortBy={sortBy}
        sortDir={sortDir}
        loading={tableLoading}
        error={tableError}
        onSortChange={handleSortChange}
        onPageChange={setPage}
        onPageSizeChange={(ps) => {
          setPageSize(ps);
          setPage(1);
        }}
        onOpenPatient={(patient) => handleOpenPatient(patient)}
        filters={applied}
      />

      {/* Patient detail drawer */}
      {selectedPatient && (
        <PatientDetailDrawer
          patient={selectedPatient}
          userEmail={USER_EMAIL_PLACEHOLDER}
          orgId={applied.orgId || undefined}
          initialTab={drawerTab}
          onClose={() => setSelectedPatient(null)}
          onEpisodeUpdated={(episodeId, patch) =>
            handleEpisodeUpdated(selectedPatient.patient_id, episodeId, patch)
          }
          onPatientRebuilt={handlePatientRebuilt}
        />
      )}
    </Box>
  );
}
