"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Link from "@mui/material/Link";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Drawer from "@mui/material/Drawer";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SearchIcon from "@mui/icons-material/Search";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import {
  fetchEncounter,
  fetchEncounterCodedLinks,
  fetchPatient,
  fetchPatientEncounters,
  fetchTasks,
  resetPatient,
  resetReviewQueue,
  searchPatientEncounters,
  syncGoldToPatient,
} from "@/lib/api";
import { rebuildPatientEpisodes } from "@/lib/analyticsApi";
import type { EncounterSearchResult } from "@/lib/api";
import type { CodedLink, EncounterSummary, ReviewTaskSummary } from "@/lib/types";
import { usePipeline } from "@/context/PipelineContext";
import ConfirmDialog from "./ConfirmDialog";

interface Props {
  patientId: string;
}

interface PatientInfo {
  patient_id: string;
  encounter_count: number;
  gender?: string;
  birth_date?: string;
}

// DR-1: Status colour system — amber/blue/green/red per brief
const STATUS_LABELS: Record<string, string> = {
  not_processed: "Needs review",
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  escalated: "Escalated",
};

const STATUS_CHIP_COLORS: Record<
  string,
  "default" | "warning" | "info" | "success" | "error" | "secondary"
> = {
  not_processed: "warning",
  pending: "info",
  approved: "success",
  rejected: "error",
  escalated: "secondary",
};

// DR-6: Fixed status order — always shown with zero counts
const ALL_STATUSES = [
  "not_processed",
  "pending",
  "approved",
  "rejected",
  "escalated",
] as const;

function getStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

// DR-3: Extract referral type from the flags field
function parseReferralType(flags?: string): string | null {
  if (!flags) return null;
  // Matches: "Referral: ... - Specialist for Condition (Primary Reason)"
  const match = flags.match(/Referral:.*? for ([^(\n,]+)/);
  const result = match?.[1]?.trim();
  return result && result.length > 0 ? result : null;
}

// DR-5: Calculate age from ISO birthDate string
function calculateAge(birthDate: string): number {
  const birth = new Date(birthDate);
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  if (
    now.getMonth() < birth.getMonth() ||
    (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())
  ) {
    age--;
  }
  return age;
}

function formatPatientContext(gender?: string, birthDate?: string): string | null {
  if (!gender && !birthDate) return null;
  const parts: string[] = [];
  if (gender) parts.push(gender.charAt(0).toUpperCase() + gender.slice(1));
  if (birthDate) {
    const year = birthDate.split("-")[0];
    parts.push(`Born ${year}`);
    parts.push(`Age ${calculateAge(birthDate)}`);
  }
  return parts.join(" · ");
}

// DR-5: Segmented progress bar
function ReviewProgressBar({
  total,
  counts,
}: {
  total: number;
  counts: Record<string, number>;
}) {
  if (total === 0) return null;
  const segments = [
    { key: "approved", color: "#16a34a" },
    { key: "pending", color: "#1F3A8A" },
    { key: "rejected", color: "#dc2626" },
    { key: "escalated", color: "#14B8A6" },
  ];
  return (
    <Tooltip
      title={`${counts.approved ?? 0} approved · ${counts.pending ?? 0} pending · ${counts.not_processed ?? 0} needs review`}
      arrow
    >
      <Box
        sx={{
          display: "flex",
          height: 6,
          borderRadius: 3,
          overflow: "hidden",
          bgcolor: "#E2E8F0",
          width: 160,
          flexShrink: 0,
        }}
      >
        {segments.map((s) => (
          <Box
            key={s.key}
            sx={{
              width: `${((counts[s.key] ?? 0) / total) * 100}%`,
              bgcolor: s.color,
              transition: "width 0.4s ease",
            }}
          />
        ))}
      </Box>
    </Tooltip>
  );
}

export default function EncounterList({ patientId }: Props) {
  const [patient, setPatient] = useState<PatientInfo | null>(null);
  const [tasks, setTasks] = useState<ReviewTaskSummary[]>([]);
  const [encounters, setEncounters] = useState<EncounterSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resettingQueue, setResettingQueue] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmResetQueue, setConfirmResetQueue] = useState(false);
  const [confirmSync, setConfirmSync] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [sortKey, setSortKey] = useState<"date-desc" | "date-asc" | "status" | "id">("date-desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"keyword" | "semantic">("keyword");
  const [semanticResults, setSemanticResults] = useState<EncounterSearchResult[] | null>(null);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const [statusFilter, setStatusFilter] = useState<string | null>(
    searchParams.get("status") || null,
  );
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Right-hand sidebar for encounter preview (click row to open, click another to switch)
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarEncounter, setSidebarEncounter] = useState<{
    encounterId: string;
    dateStr: string;
    taskId?: string;
  } | null>(null);
  const [sidebarData, setSidebarData] = useState<{
    encounter: { text: string };
    codedLinks: CodedLink[];
  } | null>(null);
  const [sidebarLoading, setSidebarLoading] = useState(false);
  const [sidebarError, setSidebarError] = useState<string | null>(null);
  const sidebarRequestIdRef = useRef(0);

  const loadSidebarEncounter = useCallback(
    async (encounterId: string) => {
      const requestId = ++sidebarRequestIdRef.current;
      setSidebarLoading(true);
      setSidebarError(null);
      try {
        const [encData, links] = await Promise.all([
          fetchEncounter(patientId, encounterId),
          fetchEncounterCodedLinks(patientId, encounterId),
        ]);
        if (requestId === sidebarRequestIdRef.current) {
          setSidebarData({ encounter: encData, codedLinks: links });
        }
      } catch (e) {
        if (requestId === sidebarRequestIdRef.current) {
          setSidebarError(e instanceof Error ? e.message : "Failed to load encounter");
        }
      } finally {
        if (requestId === sidebarRequestIdRef.current) {
          setSidebarLoading(false);
        }
      }
    },
    [patientId],
  );

  const handleEncounterClick = useCallback(
    (encounterId: string, dateStr: string, taskId?: string) => {
      setSidebarOpen(true);
      setSidebarEncounter({ encounterId, dateStr, taskId });
      setSidebarData(null);
      setSidebarError(null);
      setSidebarLoading(true);
      loadSidebarEncounter(encounterId);
    },
    [loadSidebarEncounter],
  );

  function updateStatusFilter(value: string | null) {
    setStatusFilter(value);
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set("status", value);
    } else {
      params.delete("status");
    }
    router.replace(`?${params.toString()}`, { scroll: false });
  }
  const pipeline = usePipeline();

  async function reload() {
    const [encounterRows, taskRows] = await Promise.all([
      fetchPatientEncounters(patientId),
      fetchTasks(undefined, patientId),
    ]);
    setEncounters(encounterRows);
    setTasks(taskRows);
  }

  const runSemanticSearch = useCallback(
    async (query: string) => {
      if (!query.trim() || searchMode !== "semantic") {
        setSemanticResults(null);
        return;
      }
      setSemanticLoading(true);
      try {
        const results = await searchPatientEncounters(patientId, query, "hybrid");
        setSemanticResults(results);
      } catch {
        setSemanticResults(null);
      } finally {
        setSemanticLoading(false);
      }
    },
    [patientId, searchMode],
  );

  useEffect(() => {
    if (searchMode !== "semantic") {
      setSemanticResults(null);
      return;
    }
    if (!searchQuery.trim()) {
      setSemanticResults(null);
      return;
    }
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => runSemanticSearch(searchQuery), 400);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [searchQuery, searchMode, runSemanticSearch]);

  async function doReset() {
    setResetting(true);
    setError(null);
    try {
      await resetPatient(patientId);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed. No changes were made.");
    } finally {
      setResetting(false);
      setConfirmReset(false);
    }
  }

  async function doResetReviewQueue() {
    setResettingQueue(true);
    setError(null);
    try {
      await resetReviewQueue(patientId);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset review list failed. Try again.");
    } finally {
      setResettingQueue(false);
      setConfirmResetQueue(false);
    }
  }

  async function doSyncGold() {
    setSyncing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const result = await syncGoldToPatient(patientId);
      const parts = [
        `Synced ${result.encounters_synced} encounters, ${result.links_created} links created`,
      ];
      if (result.surface_forms_written) {
        parts.push(`${result.surface_forms_written} surface forms written to terminology`);
      }
      setSuccessMsg(parts.join(" | "));
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Apply failed. Approved data was not written.");
    } finally {
      setSyncing(false);
      setConfirmSync(false);
    }
  }

  async function doRebuildPathways() {
    setRebuilding(true);
    setError(null);
    try {
      const result = await rebuildPatientEpisodes(patientId, true);
      setSuccessMsg(
        `Rebuilt pathways: ${result.episodes_created} created, ${result.encounters_linked} encounters linked`,
      );
      router.push(`/pathways?patient_id=${encodeURIComponent(patientId)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rebuild failed. Pathways were not updated.");
    } finally {
      setRebuilding(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchPatient(patientId),
      fetchPatientEncounters(patientId),
      fetchTasks(undefined, patientId),
    ])
      .then(([patientData, encounterRows, taskRows]) => {
        setPatient(patientData);
        setEncounters(encounterRows);
        setTasks(taskRows);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Could not load encounters. Check your connection and try again."),
      )
      .finally(() => setLoading(false));
  }, [patientId]);

  const latestTaskByEncounter = tasks.reduce((acc, task) => {
    const key = String(task.encounter_id).trim();
    const existing = acc.get(key);
    if (!existing) { acc.set(key, task); return acc; }
    if (existing.status !== "pending" && task.status === "pending") { acc.set(key, task); return acc; }
    if (new Date(task.updated_at).getTime() > new Date(existing.updated_at).getTime()) acc.set(key, task);
    return acc;
  }, new Map<string, ReviewTaskSummary>());

  const allMappedRows = encounters.map((encounter) => ({
    encounter,
    task: latestTaskByEncounter.get(String(encounter.encounter_id).trim()),
  }));

  const statusCounts = allMappedRows.reduce<Record<string, number>>((acc, { task }) => {
    const s = task?.status ?? "not_processed";
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});

  const semanticHitSet = semanticResults
    ? new Set(semanticResults.map((r) => String(r.encounter_id)))
    : null;

  const semanticMatchInfo = semanticResults
    ? new Map(semanticResults.map((r) => [String(r.encounter_id), r]))
    : null;

  const filteredAndSortedRows = allMappedRows
    .filter(({ encounter, task }) => {
      const rawStatus = task?.status ?? "not_processed";
      if (statusFilter !== null && rawStatus !== statusFilter) return false;
      if (!searchQuery.trim()) return true;

      if (searchMode === "semantic") {
        return semanticHitSet ? semanticHitSet.has(String(encounter.encounter_id)) : true;
      }

      const q = searchQuery.toLowerCase().trim();
      const referral = (parseReferralType(encounter.flags) ?? "").toLowerCase();
      const textContent = (encounter.text ?? "").toLowerCase();
      return (
        String(encounter.encounter_id).toLowerCase().includes(q) ||
        (encounter.date ?? "").includes(q) ||
        rawStatus.includes(q) ||
        getStatusLabel(rawStatus).toLowerCase().includes(q) ||
        referral.includes(q) ||
        textContent.includes(q)
      );
    })
    .sort((a, b) => {
      switch (sortKey) {
        case "date-asc": return new Date(a.encounter.date).getTime() - new Date(b.encounter.date).getTime();
        case "date-desc": return new Date(b.encounter.date).getTime() - new Date(a.encounter.date).getTime();
        case "status": return (a.task?.status ?? "not_processed").localeCompare(b.task?.status ?? "not_processed");
        case "id": return String(a.encounter.encounter_id).localeCompare(String(b.encounter.encounter_id));
        default: return 0;
      }
    });

  const rows = filteredAndSortedRows;
  const totalCount = encounters.length;
  const paginatedRows = rows.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  useEffect(() => {
    setPage(0);
  }, [searchQuery, searchMode, statusFilter]);
  const approvedCount = allMappedRows.filter((r) => r.task?.status === "approved").length;
  const withTask = allMappedRows.filter((r) => Boolean(r.task)).length;
  const unprocessedCount = totalCount - withTask;

  function handleProcessUnprocessed() {
    pipeline.start({
      patientIds: [patientId],
      unprocessedOnly: true,
      workers: 4,
    });
  }

  useEffect(() => {
    if (pipeline.result && !pipeline.running) {
      reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipeline.result, pipeline.running]);

  // DR-4 Option A: only show priority column when at least one task has been processed
  const hasPriority = withTask > 0;

  // DR-6: Always show all statuses with counts (including zeros)
  const statusFilterOptions = [
    { value: null, label: "All", count: totalCount },
    ...ALL_STATUSES.map((s) => ({ value: s, label: getStatusLabel(s), count: statusCounts[s] ?? 0 })),
  ];

  const patientContext = patient
    ? formatPatientContext(patient.gender, patient.birth_date)
    : null;

  return (
    <Box sx={{ maxWidth: 1100, mx: "auto", p: 3 }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        {searchParams.get("from") === "pathways"
          ? [
              <Link key="pathways" component="button" underline="hover" onClick={() => router.push("/pathways")} sx={{ fontSize: 14 }}>
                Referral Pathways
              </Link>,
              <Typography key="patient" sx={{ fontSize: 14 }} color="text.primary">Patient {patientId}</Typography>,
            ]
          : [
              <Link key="patients" component="button" underline="hover" onClick={() => router.push("/patients")} sx={{ fontSize: 14 }}>
                Patients
              </Link>,
              <Typography key="patient" sx={{ fontSize: 14 }} color="text.primary">Patient {patientId}</Typography>,
            ]}
      </Breadcrumbs>

      {/* DR-5: Patient header with context + progress + kebab */}
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.25 }}>
            Patient {patientId}
          </Typography>
          {patientContext && (
            <Typography variant="body2" sx={{ color: "text.secondary", mb: 0.5 }}>
              {patientContext}
            </Typography>
          )}
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mt: 0.5 }}>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              {totalCount} encounters · {withTask} processed · {approvedCount} reviewed
            </Typography>
            <ReviewProgressBar total={totalCount} counts={statusCounts} />
            {unprocessedCount > 0 && (
              <Button
                variant="contained"
                size="small"
                disabled={pipeline.running}
                onClick={handleProcessUnprocessed}
                sx={{
                  textTransform: "none",
                  fontWeight: 600,
                  fontSize: "0.75rem",
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 1.5,
                  bgcolor: "#4f46e5",
                  "&:hover": { bgcolor: "#4338ca" },
                }}
              >
                {pipeline.running ? "Processing…" : `Process ${unprocessedCount} unprocessed`}
              </Button>
            )}
            {(searchParams.get("from") === "episodes" || approvedCount > 0) && (
              <Button
                variant="outlined"
                size="small"
                disabled={rebuilding}
                onClick={doRebuildPathways}
                sx={{
                  textTransform: "none",
                  fontWeight: 600,
                  fontSize: "0.75rem",
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 1.5,
                }}
              >
                {rebuilding ? "Rebuilding…" : "Rebuild Pathways"}
              </Button>
            )}
          </Stack>
          {pipeline.running && pipeline.live && (
            <Stack spacing={0.5} sx={{ mt: 1 }}>
              <LinearProgress
                variant="determinate"
                value={pipeline.live.processed_encounters > 0 && unprocessedCount > 0
                  ? Math.min(100, (pipeline.live.processed_encounters / unprocessedCount) * 100)
                  : 0}
                sx={{ height: 4, borderRadius: 2, bgcolor: "#E2E8F0", "& .MuiLinearProgress-bar": { bgcolor: "#4f46e5" } }}
              />
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {pipeline.status} — {pipeline.live.processed_encounters} / {unprocessedCount} done
              </Typography>
            </Stack>
          )}
        </Box>

        {/* DR-5: Admin/destructive actions hidden behind kebab menu */}
        <Tooltip title="Patient actions">
          <IconButton
            size="small"
            onClick={(e) => setMenuAnchor(e.currentTarget)}
            disabled={loading}
            sx={{ mt: 0.5 }}
          >
            <MoreVertIcon />
          </IconButton>
        </Tooltip>
        <Menu
          anchorEl={menuAnchor}
          open={Boolean(menuAnchor)}
          onClose={() => setMenuAnchor(null)}
          transformOrigin={{ horizontal: "right", vertical: "top" }}
          anchorOrigin={{ horizontal: "right", vertical: "bottom" }}
        >
          <MenuItem
            onClick={() => { setMenuAnchor(null); setConfirmReset(true); }}
            disabled={resetting}
          >
            {resetting ? "Resetting…" : "Reset patient"}
          </MenuItem>
          <MenuItem
            onClick={() => { setMenuAnchor(null); if (withTask > 0) setConfirmResetQueue(true); }}
            disabled={resettingQueue || withTask === 0}
          >
            {resettingQueue ? "Clearing…" : "Reset review list"}
          </MenuItem>
          <Divider />
          <MenuItem
            onClick={() => { setMenuAnchor(null); if (approvedCount > 0) setConfirmSync(true); }}
            disabled={syncing || approvedCount === 0}
          >
            {syncing ? "Syncing…" : "Apply approved data"}
          </MenuItem>
          <Divider />
          <MenuItem
            onClick={() => { setMenuAnchor(null); doRebuildPathways(); }}
            disabled={rebuilding}
          >
            {rebuilding ? "Rebuilding…" : "Rebuild pathways"}
          </MenuItem>
        </Menu>
      </Stack>

      {/* Confirm dialogs */}
      {confirmReset && (
        <ConfirmDialog
          title="Reset patient?"
          body="This will remove all clinical codes for this patient. The encounter text will remain, but you will need to process and review again. This cannot be undone."
          confirmLabel="Reset"
          variant="danger"
          onConfirm={doReset}
          onCancel={() => setConfirmReset(false)}
        />
      )}
      {confirmResetQueue && (
        <ConfirmDialog
          title="Reset review list?"
          body="This will clear all pending tasks for this patient. Use this after a processing failure so you can re-process cleanly. Approved and rejected tasks will also be removed."
          confirmLabel="Clear list"
          variant="danger"
          onConfirm={doResetReviewQueue}
          onCancel={() => setConfirmResetQueue(false)}
        />
      )}
      {confirmSync && (
        <ConfirmDialog
          title="Apply approved data?"
          body="This will apply your approved encounters to the patient graph. Only encounters you have approved will be applied."
          confirmLabel="Apply"
          onConfirm={doSyncGold}
          onCancel={() => setConfirmSync(false)}
        />
      )}

      {error && (
        <Typography sx={{ color: "error.main", mb: 2, fontSize: 14 }}>{error}</Typography>
      )}
      {successMsg && (
        <Typography sx={{ color: "success.main", mb: 2, fontSize: 14 }}>{successMsg}</Typography>
      )}

      {/* Filter / sort bar */}
      {!loading && (
        <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1.5, alignItems: "center", mb: 1.5 }}>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={searchMode}
            onChange={(_, v) => {
              if (v) {
                setSearchMode(v);
                setSemanticResults(null);
              }
            }}
            sx={{
              "& .MuiToggleButton-root": {
                textTransform: "none",
                px: 1.5,
                py: 0.5,
                fontSize: "0.8rem",
                fontWeight: 600,
              },
            }}
          >
            <ToggleButton value="keyword">
              <SearchIcon sx={{ fontSize: 16, mr: 0.5 }} />
              Keyword
            </ToggleButton>
            <ToggleButton value="semantic">
              <TravelExploreIcon sx={{ fontSize: 16, mr: 0.5 }} />
              Semantic
            </ToggleButton>
          </ToggleButtonGroup>
          <TextField
            size="small"
            placeholder={
              searchMode === "keyword"
                ? "Search encounter text, date, status…"
                : "Search by clinical concept e.g. 'diabetes', 'chest pain'…"
            }
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search encounters"
            sx={{ flex: "1 1 220px", minWidth: 220 }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  {semanticLoading ? (
                    <CircularProgress size={16} />
                  ) : searchMode === "semantic" ? (
                    <TravelExploreIcon fontSize="small" sx={{ color: "text.disabled" }} />
                  ) : (
                    <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
                  )}
                </InputAdornment>
              ),
            }}
          />
          <TextField
            select
            size="small"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as typeof sortKey)}
            aria-label="Sort encounters"
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="date-desc">Date (newest first)</MenuItem>
            <MenuItem value="date-asc">Date (oldest first)</MenuItem>
            <MenuItem value="status">Status</MenuItem>
            <MenuItem value="id">Encounter ID</MenuItem>
          </TextField>
        </Stack>
      )}

      {/* DR-6: Status filter chips — always all statuses with counts */}
      {!loading && (
        <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75, mb: 2 }}>
          {statusFilterOptions.map((opt) => {
            const isActive = statusFilter === opt.value;
            const isEmpty = opt.count === 0;
            return (
              <Chip
                key={String(opt.value)}
                label={`${opt.label} ${opt.count}`}
                onClick={() => updateStatusFilter(opt.value)}
                variant={isActive ? "filled" : "outlined"}
                color={isActive ? "primary" : "default"}
                size="small"
                sx={{
                  opacity: isEmpty && !isActive ? 0.45 : 1,
                  fontVariantNumeric: "tabular-nums",
                }}
              />
            );
          })}
          {(searchQuery.trim() || statusFilter !== null) && (
            <Typography variant="caption" sx={{ color: "text.secondary", alignSelf: "center", ml: 0.5 }}>
              {rows.length} of {totalCount} shown
              {searchMode === "semantic" && searchQuery.trim() && semanticResults
                ? ` (${semanticResults.length} vector matches)`
                : ""}
            </Typography>
          )}
        </Stack>
      )}

      {/* Loading skeletons */}
      {loading && (
        <Table size="small">
          <TableBody>
            {Array.from({ length: 8 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell sx={{ width: 120 }}><Skeleton width={90} /></TableCell>
                <TableCell><Skeleton width="70%" /></TableCell>
                <TableCell sx={{ width: 120 }}><Skeleton width={80} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* DR-2: Dense table with alternating rows + pagination */}
      {!loading && rows.length > 0 && (
        <>
          <TableContainer sx={{ maxHeight: 520 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow sx={{ "& th": { py: 1 }, bgcolor: "background.paper" }}>
                  <TableCell sx={{ width: 120, fontWeight: 600 }}>Date</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Encounter</TableCell>
                  <TableCell sx={{ width: 130, fontWeight: 600 }}>Status</TableCell>
                  {hasPriority && <TableCell sx={{ width: 80, fontWeight: 600 }}>Priority</TableCell>}
                </TableRow>
              </TableHead>
              <TableBody>
                {paginatedRows.map(({ encounter, task }, idx) => {
                  const status = task?.status ?? "not_processed";
                  const referralType = parseReferralType(encounter.flags);
                  const dateStr = encounter.date
                    ? new Date(encounter.date).toLocaleDateString("en-GB", {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      })
                    : "\u2014";
                  const fullId = String(encounter.encounter_id);
                  const isEven = idx % 2 === 0;
                  const isSelected =
                    sidebarOpen && sidebarEncounter?.encounterId === fullId;

                  return (
                    <TableRow
                      key={encounter.encounter_id}
                      hover
                      selected={isSelected}
                      sx={{
                        cursor: "pointer",
                        bgcolor: isEven ? "background.paper" : "#FAFBFC",
                        "& td": { py: 0.75 },
                      }}
                      onClick={() =>
                        handleEncounterClick(fullId, dateStr, task?.task_id)
                      }
                    >
                      <TableCell>
                        <Typography sx={{ fontWeight: 600, fontSize: "0.875rem", whiteSpace: "nowrap" }}>
                          {dateStr}
                        </Typography>
                      </TableCell>

                      <TableCell sx={{ position: "relative" }}>
                        <Box sx={{ display: "block", width: "100%", minHeight: 24 }}>
                          {referralType ? (
                            <Box>
                              <Typography sx={{ fontSize: "0.875rem", fontWeight: 500, lineHeight: 1.3 }}>
                                {referralType}
                              </Typography>
                              <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.25 }}>
                                <Typography
                                  component="span"
                                  sx={{
                                    fontSize: "0.7rem",
                                    fontFamily: "monospace",
                                    color: "#9CA3AF",
                                    letterSpacing: "0.02em",
                                  }}
                                >
                                  {fullId.slice(0, 8)}
                                </Typography>
                                {task && task.warning_count > 0 && (
                                  <Chip size="small" color="warning" label={`${task.warning_count}w`} sx={{ height: 16, fontSize: "0.65rem" }} />
                                )}
                                {typeof encounter.coded_count === "number" && encounter.coded_count > 0 && (
                                  <Typography component="span" sx={{ fontSize: "0.7rem", color: "success.main" }}>
                                    {encounter.coded_count} coded
                                  </Typography>
                                )}
                              </Stack>
                            </Box>
                          ) : (
                            <Stack direction="row" spacing={1} alignItems="center">
                              <Typography
                                variant="subtitle2"
                                sx={{ fontFamily: "monospace", color: "text.secondary" }}
                              >
                                {fullId.slice(0, 8)}
                              </Typography>
                              {task && task.warning_count > 0 && (
                                <Chip size="small" color="warning" label={`${task.warning_count}w`} sx={{ height: 18 }} />
                              )}
                              {typeof encounter.coded_count === "number" && encounter.coded_count > 0 && (
                                <Typography variant="caption" sx={{ color: "success.main" }}>
                                  {encounter.coded_count} coded
                                </Typography>
                              )}
                            </Stack>
                          )}
                        </Box>
                        {searchMode === "semantic" && semanticMatchInfo?.has(fullId) && (() => {
                          const info = semanticMatchInfo.get(fullId)!;
                          const sim = info.similarity;
                          if (sim == null) return null;
                          const pct = Math.round(sim * 100);
                          const color = pct >= 90 ? "#16a34a" : pct >= 75 ? "#2563eb" : "#9333ea";
                          return (
                            <Chip
                              label={`${pct}% match`}
                              size="small"
                              sx={{
                                mt: 0.5,
                                height: 18,
                                fontSize: "0.65rem",
                                fontWeight: 600,
                                bgcolor: `${color}18`,
                                color,
                                border: `1px solid ${color}40`,
                                "& .MuiChip-label": { px: 0.75 },
                              }}
                            />
                          );
                        })()}
                      </TableCell>

                      <TableCell>
                        <Chip
                          label={getStatusLabel(status)}
                          color={STATUS_CHIP_COLORS[status] ?? "default"}
                          size="small"
                          sx={{ fontWeight: 500 }}
                        />
                      </TableCell>

                      {hasPriority && (
                        <TableCell>
                          <Typography variant="body2" sx={{ color: "text.secondary" }}>
                            {task ? `P${task.priority}` : "\u2014"}
                          </Typography>
                        </TableCell>
                      )}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            rowsPerPageOptions={[10, 25, 50, 100]}
            component="div"
            count={rows.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
          />
        </>
      )}

      {!loading && rows.length === 0 && !error && (
        <Typography sx={{ color: "text.secondary", textAlign: "center", py: 6, fontSize: "0.9rem" }}>
          {searchQuery.trim() || statusFilter !== null
            ? "No encounters match your search or filters."
            : "No encounters found for this patient."}
        </Typography>
      )}

      <Drawer
        anchor="right"
        open={sidebarOpen}
        hideBackdrop
        onClose={() => {
          setSidebarOpen(false);
          setSidebarEncounter(null);
          setSidebarData(null);
        }}
        slotProps={{
          root: {
            sx: { pointerEvents: "none" },
          },
          paper: {
            sx: {
              width: 480,
              maxWidth: "95vw",
              pointerEvents: "auto",
            },
          },
        }}
      >
        <Box sx={{ p: 2, height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
            {sidebarEncounter && (
              <Typography variant="subtitle1" fontWeight={600}>
                Encounter {sidebarEncounter.encounterId} ({sidebarEncounter.dateStr})
              </Typography>
            )}
            <Stack direction="row" spacing={0.5}>
              {sidebarEncounter && (
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<OpenInNewIcon />}
                  onClick={() => {
                    if (sidebarEncounter.taskId) {
                      router.push(`/patients/${patientId}/encounters/${sidebarEncounter.taskId}`);
                    } else {
                      router.push(`/patients/${patientId}/encounters/view/${sidebarEncounter.encounterId}`);
                    }
                  }}
                >
                  View full
                </Button>
              )}
              <IconButton size="small" onClick={() => setSidebarOpen(false)} aria-label="Close">
                <CloseIcon />
              </IconButton>
            </Stack>
          </Stack>
          <Box sx={{ flex: 1, overflow: "auto", minHeight: 0 }}>
            {sidebarLoading && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 4 }}>
                <CircularProgress size={24} />
                <Typography variant="body2" color="text.secondary">
                  Loading...
                </Typography>
              </Box>
            )}
            {sidebarError && (
              <Typography variant="body2" color="error" sx={{ py: 2 }}>
                {sidebarError}
              </Typography>
            )}
            {!sidebarLoading && !sidebarError && sidebarData && sidebarEncounter && (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <Typography
                  variant="body2"
                  component="pre"
                  sx={{
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    maxHeight: 280,
                    overflow: "auto",
                    fontSize: "0.85rem",
                    bgcolor: "grey.50",
                    p: 1.5,
                    borderRadius: 1,
                  }}
                >
                  {sidebarData.encounter.text || "(No text)"}
                </Typography>
                <Box>
                  <Typography variant="caption" fontWeight={600} color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    DOCUMENTS (coded links)
                  </Typography>
                  {sidebarData.codedLinks.length > 0 ? (
                    <Box component="ul" sx={{ m: 0, pl: 2, fontSize: "0.8rem", maxHeight: 220, overflow: "auto" }}>
                      {sidebarData.codedLinks.map((link, i) => (
                        <li key={link.concept_id + String(i)}>
                          <Typography component="span" variant="caption">
                            {link.term || link.concept_id}
                            {link.read_code && ` (${link.read_code})`}
                            {link.semantic_tag && ` [${link.semantic_tag}]`}
                          </Typography>
                          {(link.evidence || link.confidence != null || link.domain || link.coded_at || (link.context && Object.keys(link.context).length > 0) || (link.modifiers && Object.keys(link.modifiers).length > 0)) && (
                            <Typography
                              component="span"
                              variant="caption"
                              sx={{ display: "block", color: "text.secondary", fontSize: "0.75rem", mt: 0.25, pl: 1 }}
                            >
                              {[
                                link.evidence && `evidence: "${link.evidence}"`,
                                link.confidence != null && `confidence: ${Math.round(link.confidence * 100)}%`,
                                link.domain && `domain: ${link.domain}`,
                                link.coded_at && `coded_at: ${link.coded_at}`,
                                link.context && Object.keys(link.context).length > 0 && `context: ${JSON.stringify(link.context)}`,
                                link.modifiers && Object.keys(link.modifiers).length > 0 && `modifiers: ${JSON.stringify(link.modifiers)}`,
                              ]
                                .filter(Boolean)
                                .join(" · ")}
                            </Typography>
                          )}
                        </li>
                      ))}
                    </Box>
                  ) : (
                    <Typography variant="caption" color="text.secondary">
                      No coded links
                    </Typography>
                  )}
                </Box>
              </Box>
            )}
          </Box>
        </Box>
      </Drawer>
    </Box>
  );
}
