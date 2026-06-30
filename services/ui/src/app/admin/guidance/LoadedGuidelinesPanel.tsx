/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoFixHighOutlinedIcon from "@mui/icons-material/AutoFixHighOutlined";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import SystemUpdateAltOutlinedIcon from "@mui/icons-material/SystemUpdateAltOutlined";
import NewReleasesOutlinedIcon from "@mui/icons-material/NewReleasesOutlined";
import PageviewOutlinedIcon from "@mui/icons-material/PageviewOutlined";

import { EmptyState, ReviewListCard, ToolbarActions, type ReviewListItem } from "@leo/design-system";
import ConfirmDialog from "@/components/ConfirmDialog";
import GuidelineSubgraphDrawer from "./GuidelineSubgraphDrawer";
import GuidelineChangesDrawer from "./GuidelineChangesDrawer";

interface LoadedGuideline {
  code: string;
  title: string;
  guidance_type: string;
  publication_date: string;
  chapter_count: number;
  recommendation_count: number;
  rules_pending: number;
  rules_approved: number;
  rules_rejected: number;
}

interface UpdateStatus {
  checking: boolean;
  available: boolean | null;
  remoteDate: string;
  ingestDate: string;
  error: string | null;
}

type UpdateStatusMap = Record<string, UpdateStatus>;

interface Props {
  refreshKey?: number;
  onRulesGenerated?: () => void;
}

type StatusFilter = "all" | "no-rules" | "pending" | "active";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "no-rules", label: "No rules" },
  { value: "pending", label: "Pending" },
  { value: "active", label: "Active" },
];

function matchesStatusFilter(g: LoadedGuideline, f: StatusFilter): boolean {
  const total = g.rules_pending + g.rules_approved + g.rules_rejected;
  if (f === "no-rules") return total === 0;
  if (f === "pending") return g.rules_pending > 0;
  if (f === "active") return g.rules_approved > 0;
  return true;
}

function filterGuidelines(
  list: LoadedGuideline[],
  search: string,
  status: StatusFilter,
): LoadedGuideline[] {
  const q = search.trim().toLowerCase();
  return list.filter((g) => {
    const textMatch =
      !q || g.code.toLowerCase().includes(q) || (g.title || "").toLowerCase().includes(q);
    return textMatch && matchesStatusFilter(g, status);
  });
}

interface FilterBarProps {
  search: string;
  onSearch: (v: string) => void;
  status: StatusFilter;
  onStatus: (v: StatusFilter) => void;
  totalCount: number;
  visibleCount: number;
}

function GuidelineFilterBar({
  search, onSearch, status, onStatus, totalCount, visibleCount,
}: FilterBarProps) {
  return (
    <Stack spacing={1} sx={{ mb: 1.5 }}>
      <TextField
        size="small"
        placeholder="Search by code or title..."
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" sx={{ color: "text.secondary" }} />
            </InputAdornment>
          ),
        }}
        sx={{ maxWidth: 420 }}
        aria-label="Search guidelines"
      />
      <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
        {STATUS_FILTERS.map((f) => (
          <Chip
            key={f.value}
            label={f.label}
            size="small"
            variant={status === f.value ? "filled" : "outlined"}
            color={status === f.value ? "primary" : "default"}
            onClick={() => onStatus(f.value)}
            sx={{ cursor: "pointer" }}
          />
        ))}
        {(search || status !== "all") && (
          <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
            {visibleCount} of {totalCount}
          </Typography>
        )}
      </Stack>
    </Stack>
  );
}

function ruleStatusPill(g: LoadedGuideline): ReactNode {
  const total = g.rules_pending + g.rules_approved + g.rules_rejected;
  if (total === 0) return <Chip label="No rules yet" size="small" variant="outlined" />;
  const parts: string[] = [];
  if (g.rules_pending > 0) parts.push(`Pending (${g.rules_pending})`);
  if (g.rules_approved > 0) parts.push(`Approved (${g.rules_approved})`);
  if (parts.length === 0) return <Chip label="None approved" size="small" variant="outlined" />;
  return <Chip label={parts.join(" / ")} size="small" variant="outlined" />;
}

function formatUpdateDate(iso: string): string {
  const day = iso.split("T")[0];
  if (!day) return iso;
  const [y, m, d] = day.split("-");
  return `${d}/${m}/${y}`;
}

function buildGuidelineItem(
  g: LoadedGuideline,
  generating: string | null,
  reingesting: string | null,
  updateStatus: UpdateStatus | undefined,
  onGenerate: (code: string, hasRules: boolean) => void,
  onInspect: (code: string) => void,
  onReviewChanges: (code: string) => void,
): ReviewListItem {
  const hasRules = g.rules_pending + g.rules_approved + g.rules_rejected > 0;
  const isGenerating = generating === g.code;
  const isReingesting = reingesting === g.code;

  const updateChip = (() => {
    if (!updateStatus) return null;
    if (updateStatus.checking) {
      return (
        <Chip
          icon={<CircularProgress size={10} color="inherit" />}
          label="Checking..."
          size="small"
          variant="outlined"
          sx={{ color: "text.secondary", borderColor: "divider" }}
        />
      );
    }
    if (updateStatus.available) {
      const label = updateStatus.remoteDate
        ? `Update available - ${formatUpdateDate(updateStatus.remoteDate)}`
        : "Update available";
      const tip = updateStatus.ingestDate
        ? `NICE updated this guideline after it was last ingested (${formatUpdateDate(updateStatus.ingestDate)}). Re-ingest to get the latest recommendations.`
        : "NICE has published changes to this guideline. Re-ingest to get the latest recommendations.";
      return (
        <Tooltip title={tip}>
          <Chip
            icon={<NewReleasesOutlinedIcon fontSize="small" />}
            label={label}
            size="small"
            sx={{ bgcolor: "#FEF3C7", color: "#92400E", border: "1px solid #FDE68A", fontWeight: 600, cursor: "default" }}
          />
        </Tooltip>
      );
    }
    if (updateStatus.available === false) {
      return (
        <Chip label="Up to date" size="small" sx={{ bgcolor: "#ECFDF5", color: "#065F46", border: "1px solid #A7F3D0" }} />
      );
    }
    if (updateStatus.error) {
      return <Chip label="Check failed" size="small" color="error" variant="outlined" />;
    }
    return null;
  })();

  return {
    id: g.code,
    tone: g.recommendation_count === 0 ? "danger" : "neutral",
    title: (
      <Stack direction="row" spacing={1} alignItems="center">
        <Chip label={g.code} size="small" sx={{ bgcolor: "#DBEAFE", color: "#1D4ED8", border: "1px solid #BFDBFE", fontWeight: 700 }} />
        <Typography variant="body2" sx={{ fontWeight: 500 }}>{g.title || g.code}</Typography>
      </Stack>
    ),
    meta: (
      <Stack direction="row" spacing={2}>
        <span>{g.chapter_count} chapters</span>
        <span>{g.recommendation_count} recommendations</span>
        {g.guidance_type && <span>{g.guidance_type}</span>}
      </Stack>
    ),
    chips: (
      <Stack direction="row" spacing={0.5} flexWrap="wrap">
        {ruleStatusPill(g)}
        {updateChip}
      </Stack>
    ),
    actions: (
      <Stack direction="row" spacing={0.5} alignItems="center">
        {updateStatus?.available && (
          <Tooltip title="See exactly what has changed and decide whether to update">
            <span>
              <Button
                size="small"
                variant="contained"
                color="warning"
                disabled={isReingesting}
                startIcon={isReingesting ? <CircularProgress size={14} color="inherit" /> : <PageviewOutlinedIcon fontSize="small" />}
                onClick={() => onReviewChanges(g.code)}
                aria-label={`Review changes for ${g.code} before re-ingesting`}
              >
                {isReingesting ? "Updating..." : "Review changes"}
              </Button>
            </span>
          </Tooltip>
        )}
        <Tooltip title={hasRules ? "Re-generate rules (replaces drafts)" : "Ask the AI to write rules for each recommendation"}>
          <span>
            <Button
              size="small"
              variant={hasRules ? "outlined" : "contained"}
              color={hasRules ? "warning" : "primary"}
              disabled={isGenerating || isReingesting || g.recommendation_count === 0}
              startIcon={isGenerating ? <CircularProgress size={14} color="inherit" /> : <AutoFixHighOutlinedIcon fontSize="small" />}
              onClick={() => onGenerate(g.code, hasRules)}
              aria-label={`Generate rules for ${g.code}`}
            >
              {isGenerating ? "Generating..." : hasRules ? "Re-generate" : "Generate rules"}
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Inspect what is stored in Neo4j for this guideline">
          <span>
            <Button size="small" variant="outlined" onClick={() => onInspect(g.code)} aria-label={`Inspect Neo4j subgraph for ${g.code}`}>
              <AccountTreeIcon fontSize="small" />
            </Button>
          </span>
        </Tooltip>
      </Stack>
    ),
  };
}

export default function LoadedGuidelinesPanel({ refreshKey, onRulesGenerated }: Props) {
  const [guidelines, setGuidelines] = useState<LoadedGuideline[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState<string | null>(null);
  const [inspectCode, setInspectCode] = useState<string | null>(null);
  const [updateStatuses, setUpdateStatuses] = useState<UpdateStatusMap>({});
  const [reingesting, setReingesting] = useState<string | null>(null);
  const [changesDrawerCode, setChangesDrawerCode] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  const fetchLoaded = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/nice/loaded");
      if (!r.ok) throw new Error(r.statusText);
      setGuidelines(await r.json());
    } catch {
      setError("Could not load the list of guidelines. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchLoaded(); }, [fetchLoaded, refreshKey]);

  const handleGenerate = useCallback(async (code: string) => {
    setConfirmCode(null);
    setGenerating(code);
    setGenerateError(null);
    if (pollRef.current) clearTimeout(pollRef.current);

    let jobId: string;
    try {
      const r = await fetch("/api/guidance/rules/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guideline_id: code, only_without_rules: true }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(body.detail || r.statusText);
      }
      jobId = (await r.json()).job_id;
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : "Could not start rule generation. Please try again.");
      setGenerating(null);
      return;
    }

    async function poll() {
      try {
        const r = await fetch(`/api/guidance/rules/generate/${jobId}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const job = await r.json();
        if (job.status === "done") { await fetchLoaded(); onRulesGenerated?.(); setGenerating(null); return; }
        if (job.status === "error") { setGenerateError(job.error || "Rule generation failed."); await fetchLoaded(); setGenerating(null); return; }
        pollRef.current = setTimeout(poll, 5000);
      } catch {
        setGenerateError("Lost contact with the server. Check the review queue to see if rules were created.");
        await fetchLoaded();
        onRulesGenerated?.();
        setGenerating(null);
      }
    }

    pollRef.current = setTimeout(poll, 3000);
  }, [fetchLoaded, onRulesGenerated]);

  const checkUpdates = useCallback(async () => {
    if (guidelines.length === 0) return;
    setUpdateStatuses(
      Object.fromEntries(guidelines.map((g) => [g.code, { checking: true, available: null, remoteDate: "", ingestDate: "", error: null }]))
    );
    await Promise.all(
      guidelines.map(async (g) => {
        try {
          const r = await fetch(`/api/nice/${g.code}/check-update`);
          if (!r.ok) throw new Error(r.statusText);
          const data = await r.json();
          setUpdateStatuses((prev) => ({
            ...prev,
            [g.code]: { checking: false, available: data.update_available as boolean, remoteDate: data.remote_date as string, ingestDate: data.ingest_date as string, error: null },
          }));
        } catch {
          setUpdateStatuses((prev) => ({
            ...prev,
            [g.code]: { checking: false, available: null, remoteDate: "", ingestDate: "", error: "Check failed" },
          }));
        }
      })
    );
  }, [guidelines]);

  const handleReingest = useCallback(async (code: string, diffJobId?: string) => {
    setReingesting(code);
    let jobId: string;
    try {
      const r = await fetch("/api/nice/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, diff_job_id: diffJobId ?? null }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error((body as { detail?: string }).detail || r.statusText);
      }
      jobId = (await r.json() as { job_id: string }).job_id;
    } catch {
      setReingesting(null);
      return;
    }

    async function pollReingest() {
      try {
        const r = await fetch(`/api/nice/jobs/${jobId}/status`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const job = await r.json() as { status: string };
        if (job.status === "done") {
          await fetchLoaded();
          setUpdateStatuses((prev) => ({ ...prev, [code]: { checking: false, available: false, remoteDate: "", ingestDate: "", error: null } }));
          onRulesGenerated?.();
          setReingesting(null);
          return;
        }
        if (job.status === "error") { setReingesting(null); return; }
        pollRef.current = setTimeout(pollReingest, 3000);
      } catch {
        setReingesting(null);
      }
    }

    pollRef.current = setTimeout(pollReingest, 3000);
  }, [fetchLoaded, onRulesGenerated]);

  if (loading) {
    return <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}><CircularProgress size={24} aria-label="Loading loaded guidelines" /></Box>;
  }

  if (error) return <Alert severity="error">{error}</Alert>;

  const visible = filterGuidelines(guidelines, search, statusFilter);

  return (
    <Box>
      {generateError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setGenerateError(null)}>{generateError}</Alert>}

      {/* -- Toolbar -------------------------------------------------------- */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary">
          {guidelines.length} guideline{guidelines.length !== 1 ? "s" : ""} in the knowledge graph
        </Typography>
        <ToolbarActions
          actions={[
            {
              id: "check-updates",
              label: Object.values(updateStatuses).some((s) => s.checking) ? "Checking..." : "Check for updates",
              variant: "secondary",
              icon: <SystemUpdateAltOutlinedIcon fontSize="small" />,
              onClick: checkUpdates,
              loading: Object.values(updateStatuses).some((s) => s.checking),
              disabled: guidelines.length === 0,
            },
            { id: "refresh", label: "Refresh", variant: "ghost", onClick: fetchLoaded, icon: <RefreshIcon fontSize="small" />, loading },
          ]}
        />
      </Stack>

      {/* -- Filter bar ----------------------------------------------------- */}
      {guidelines.length > 0 && (
        <GuidelineFilterBar
          search={search}
          onSearch={setSearch}
          status={statusFilter}
          onStatus={setStatusFilter}
          totalCount={guidelines.length}
          visibleCount={visible.length}
        />
      )}

      {/* -- List ----------------------------------------------------------- */}
      {guidelines.length === 0 ? (
        <EmptyState
          icon={<MenuBookOutlinedIcon fontSize="large" />}
          title="No guidelines loaded yet"
          body="Load a NICE guideline above to get started."
          data-testid="guidelines-empty"
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={<SearchIcon fontSize="large" />}
          title="No guidelines match"
          body="Try a different search or filter."
          data-testid="guidelines-no-match"
        />
      ) : (
        <ReviewListCard
          items={visible.map((g) =>
            buildGuidelineItem(
              g,
              generating,
              reingesting,
              updateStatuses[g.code],
              (code, hasRules) => (hasRules ? setConfirmCode(code) : handleGenerate(code)),
              setInspectCode,
              setChangesDrawerCode,
            )
          )}
        />
      )}

      {confirmCode && (
        <ConfirmDialog
          title="Replace existing rules?"
          body={`This will delete all draft rules for ${confirmCode} and ask the AI to write new ones. Rules you have already approved will also be deleted. Are you sure?`}
          confirmLabel="Yes, re-generate"
          cancelLabel="Cancel"
          variant="danger"
          onConfirm={() => handleGenerate(confirmCode)}
          onCancel={() => setConfirmCode(null)}
        />
      )}

      <GuidelineChangesDrawer
        code={changesDrawerCode}
        onClose={() => setChangesDrawerCode(null)}
        onConfirmIngest={(code, diffJobId) => {
          setChangesDrawerCode(null);
          handleReingest(code, diffJobId);
        }}
      />

      <GuidelineSubgraphDrawer code={inspectCode} onClose={() => setInspectCode(null)} />
    </Box>
  );
}
