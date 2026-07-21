/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import TablePagination from "@mui/material/TablePagination";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import RefreshIcon from "@mui/icons-material/Refresh";
import VisibilityIcon from "@mui/icons-material/Visibility";

import type { ExtractionScenarioRow } from "@/app/admin/extraction-scenarios/types";
import {
  SbarFinalView,
  type SbarBackgroundPart,
  type CompletenessFinding,
} from "@/components/sbar-final";
import {
  fetchDomain,
  fetchDomains,
  type DomainSummary,
  type SubdomainSummary,
} from "@/lib/analyticsApi";
import {
  getScenarioRun,
  listScenarioOptions,
  listScenarioRuns,
  startScenarioRun,
  type ReferralAssessmentCompletedEvent,
  type ScenarioRunChild,
  type ScenarioRunChildStage,
  type ScenarioRunSummary,
} from "./scenarioRunsApi";

// Register the <leo-sbar> custom element from the workspace widget SDK.
// This import has side effects (defines the custom element) and is safe
// to call multiple times -- the browser's customElements registry ignores
// duplicate define calls for the same tag name.
import "@mizaic/leo-widget";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace React {
    namespace JSX {
      interface IntrinsicElements {
        "leo-sbar": React.DetailedHTMLProps<
          React.HTMLAttributes<HTMLElement>,
          HTMLElement
        > & {
          "assessment-id"?: string;
          "widget-token"?: string;
          "proxy-origin"?: string;
          advisory?: string;
        };
      }
    }
  }
}

const DEFAULT_GUIDELINE = "NG12";
const DEFAULT_DOMAIN = "cancer_referrals";

const ACTIVE_STATUSES = new Set(["running", "queued"]);

const PULSE_SX = {
  "@keyframes sbar-pulse": {
    "0%, 100%": { opacity: 1, transform: "scale(1)" },
    "50%": { opacity: 0.55, transform: "scale(0.88)" },
  },
  animation: "sbar-pulse 1.3s ease-in-out infinite",
} as const;

function useAutoRefresh(isActive: boolean, onRefresh: () => void, ms = 4000) {
  const cbRef = useRef(onRefresh);
  useEffect(() => {
    cbRef.current = onRefresh;
  }, [onRefresh]);
  useEffect(() => {
    if (!isActive) return;
    const id = setInterval(() => cbRef.current(), ms);
    return () => clearInterval(id);
  }, [isActive, ms]);
}

interface LoadedGuideline {
  code: string;
  title: string;
}

function titleCaseFromId(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function labelWithId(label: string, id: string): string {
  const friendly = label.trim() || titleCaseFromId(id);
  if (!id || friendly === id) return friendly;
  return `${friendly} (${id})`;
}

function guidelineLabel(option: LoadedGuideline | string): string {
  if (typeof option === "string") return option;
  return labelWithId(option.title, option.code);
}

function domainLabel(option: DomainSummary | string): string {
  if (typeof option === "string") return titleCaseFromId(option);
  return labelWithId(option.name || option.description || "", option.id);
}

function subdomainLabel(option: SubdomainSummary | string): string {
  if (typeof option === "string") return titleCaseFromId(option);
  return labelWithId(option.description || option.name, option.name);
}

function composeSbarMarkdown(assessment: NonNullable<ScenarioRunChild["assessment"]>) {
  if (assessment.content) return assessment.content;
  return [
    "# SBAR",
    "",
    "## Situation",
    "",
    assessment.situation || "_Not generated._",
    "",
    "## Background",
    "",
    assessment.background || "_Not generated._",
    "",
    "## Assessment",
    "",
    assessment.assessment || "_Not generated._",
    "",
    "## Recommendation",
    "",
    assessment.recommendation || "_Not generated._",
  ].join("\n");
}

function normaliseCompletenessFinding(
  rawJson?: string | null,
): CompletenessFinding | null {
  if (!rawJson) return null;
  try {
    const result = JSON.parse(rawJson) as Record<string, unknown>;
    if (!result || !result.configured) return null;
    const matched = (result.matched_groups as Array<Record<string, unknown>>) || [];
    const missing = (result.missing_groups as Array<Record<string, unknown>>) || [];
    return {
      requiredFields: [...matched, ...missing]
        .filter((g) => g.required)
        .map((g) => String(g.name)),
      presentFields: matched.map((g) => String(g.name)),
      missingFields: missing.filter((g) => g.required).map((g) => String(g.name)),
      unclearFields: missing.filter((g) => !g.required).map((g) => String(g.name)),
    };
  } catch {
    return null;
  }
}

function _coerceSourceIds(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  for (const item of raw) {
    if (typeof item === "string" && item) {
      out.push(item);
      continue;
    }
    if (typeof item === "number" && Number.isFinite(item)) {
      out.push(String(item));
    }
  }
  return out;
}

function normaliseBackgroundParts(
  parts?: Array<Record<string, unknown>>,
): SbarBackgroundPart[] {
  return (parts || []).map((part, index) => ({
    index: Number(part.index ?? index + 1),
    total: Number(part.total ?? parts?.length ?? 1),
    recordCount: Number(part.recordCount ?? part.record_count ?? 0),
    recordRange: (part.recordRange ?? part.record_range ?? [0, 0]) as [
      number,
      number,
    ],
    sourceIds: _coerceSourceIds(part.sourceIds ?? part.source_ids),
    status: part.status === "failed" ? "failed" : "completed",
    errorCode: (part.errorCode ?? part.error_code ?? null) as string | null,
    errorMessage: (part.errorMessage ?? part.error_message ?? null) as
      | string
      | null,
  }));
}

function inferSubdomain(cases: ExtractionScenarioRow[], selected: Set<string>): string {
  const first = cases.find((row) => selected.has(row.case_id));
  const site = (first?.site || "").toLowerCase();
  if (site.includes("upper")) return "upper_gi";
  return "lower_gi";
}

function statusColor(status: string): "success" | "info" | "error" | "default" {
  if (status === "completed") return "success";
  if (status === "failed") return "error";
  if (status === "running" || status === "queued") return "info";
  return "default";
}

/** Prefer subgraph/event label; fall back to action id (strip act-ref- prefix). */
function stageDisplayName(stage: ScenarioRunChildStage): string {
  const eventType = (stage.event_type || "").trim();
  if (eventType && eventType !== "durable_step") {
    return eventType;
  }
  const stepId = (stage.step_id || "").trim();
  if (!stepId) return eventType || "step";
  return stepId.replace(/^act-ref-/, "").replace(/^act-/, "");
}

function formatDate(value?: string | null): string {
  if (!value) return "Not recorded";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

async function loadLoadedGuidelines(): Promise<LoadedGuideline[]> {
  const response = await fetch("/api/nice/loaded", {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!response.ok) throw new Error("Could not load guidelines.");
  const data = (await response.json()) as Array<
    LoadedGuideline & Record<string, unknown>
  >;
  return data.map((row) => ({ code: row.code, title: row.title || "" }));
}

export default function ScenarioRunPanel() {
  const [scenarios, setScenarios] = useState<ExtractionScenarioRow[]>([]);
  const [runs, setRuns] = useState<ScenarioRunSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [scenarioPage, setScenarioPage] = useState(0);
  const [scenariosPerPage, setScenariosPerPage] = useState(25);
  const [guidelineId, setGuidelineId] = useState(DEFAULT_GUIDELINE);
  const [domain, setDomain] = useState(DEFAULT_DOMAIN);
  const [subdomain, setSubdomain] = useState("lower_gi");
  const [guidelines, setGuidelines] = useState<LoadedGuideline[]>([]);
  const [domains, setDomains] = useState<DomainSummary[]>([]);
  const [subdomains, setSubdomains] = useState<SubdomainSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [scopeLoading, setScopeLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ScenarioRunSummary | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const selectedCount = selected.size;
  const canRun = selectedCount > 0 && !starting;

  const loadScenarios = useCallback(() => {
    setLoading(true);
    setError(null);
    setScenarioPage(0);
    listScenarioOptions({ search: search || undefined })
      .then((data) => setScenarios(data.cases))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load scenarios."),
      )
      .finally(() => setLoading(false));
  }, [search]);

  const loadRuns = useCallback(() => {
    listScenarioRuns()
      .then((data) => setRuns(data.runs))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load runs."),
      );
  }, []);

  useEffect(() => {
    loadScenarios();
    loadRuns();
  }, [loadScenarios, loadRuns]);

  useEffect(() => {
    let cancelled = false;
    setScopeLoading(true);
    Promise.all([loadLoadedGuidelines(), fetchDomains()])
      .then(([loadedGuidelines, loadedDomains]) => {
        if (cancelled) return;
        setGuidelines(loadedGuidelines);
        setDomains(loadedDomains);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load scope options."),
      )
      .finally(() => {
        if (!cancelled) setScopeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const matchedDomain = domains.find((row) => row.id === domain);
    if (!matchedDomain) {
      setSubdomains([]);
      return;
    }
    setScopeLoading(true);
    fetchDomain(matchedDomain.id)
      .then((detail) => {
        if (cancelled) return;
        setSubdomains(detail.subdomains || []);
        if (detail.subdomains.length > 0) {
          setSubdomain((current) => current || detail.subdomains[0].name);
        }
      })
      .catch(() => {
        if (!cancelled) setSubdomains([]);
      })
      .finally(() => {
        if (!cancelled) setScopeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [domain, domains]);

  useEffect(() => {
    if (selected.size === 0) return;
    setSubdomain(inferSubdomain(scenarios, selected));
  }, [scenarios, selected]);

  const selectedLabels = useMemo(
    () => scenarios.filter((row) => selected.has(row.case_id)),
    [scenarios, selected],
  );
  const selectedGuideline =
    guidelines.find((row) => row.code === guidelineId) ||
    ({ code: guidelineId, title: "" } as LoadedGuideline);
  const selectedDomain =
    domains.find((row) => row.id === domain) ||
    ({
      id: domain,
      name: domain,
      description: "",
      source: "platform",
      subdomain_count: 0,
    } as DomainSummary);
  const selectedSubdomain =
    subdomains.find((row) => row.name === subdomain) ||
    ({
      name: subdomain,
      description: "",
      semantic_tags: [],
      concept_count: 0,
    } as SubdomainSummary);

  const toggle = (caseId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(caseId)) next.delete(caseId);
      else next.add(caseId);
      return next;
    });
  };

  const runSelected = async () => {
    if (!canRun) return;
    setStarting(true);
    setError(null);
    try {
      const res = await startScenarioRun({
        case_ids: Array.from(selected),
        guideline_id: guidelineId,
        completeness_domain: domain,
        completeness_subdomain: subdomain,
      });
      setSelected(new Set());
      await loadRuns();
      await openDetail(res.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start run.");
    } finally {
      setStarting(false);
    }
  };

  const openDetail = async (runId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      setDetail(await getScenarioRun(runId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load run detail.");
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <Stack spacing={2}>
      <Alert severity="info">
        Run approved or draft extraction scenarios through the durable referral
        workflow and review the generated SBAR output. These runs use synthetic
        test patients only.
      </Alert>

      {error ? (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="h6" sx={{ flex: 1, minWidth: 240 }}>
              Select scenarios
            </Typography>
            <TextField
              size="small"
              label="Search scenarios"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Button onClick={loadScenarios} startIcon={<RefreshIcon />}>
              Refresh
            </Button>
          </Stack>

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <ScopeAutocomplete
              label="Guideline"
              loading={scopeLoading}
              options={guidelines}
              value={selectedGuideline}
              getLabel={guidelineLabel}
              onChange={(option) =>
                setGuidelineId(typeof option === "string" ? option : option?.code || "")
              }
            />
            <ScopeAutocomplete
              label="Completeness domain"
              loading={scopeLoading}
              options={domains}
              value={selectedDomain}
              getLabel={domainLabel}
              onChange={(option) =>
                setDomain(typeof option === "string" ? option : option?.id || "")
              }
            />
            <ScopeAutocomplete
              label="Completeness subdomain"
              loading={scopeLoading}
              options={subdomains}
              value={selectedSubdomain}
              getLabel={subdomainLabel}
              onChange={(option) =>
                setSubdomain(typeof option === "string" ? option : option?.name || "")
              }
              disabled={!domain}
            />
            <Button
              variant="contained"
              disabled={!canRun}
              onClick={runSelected}
              startIcon={
                starting ? <CircularProgress size={16} /> : <PlayCircleOutlineIcon />
              }
            >
              Run {selectedCount || ""} scenario{selectedCount === 1 ? "" : "s"}
            </Button>
          </Stack>

          <SelectedScenarioChips rows={selectedLabels} />
          <ScenarioList
            rows={scenarios}
            selected={selected}
            loading={loading}
            page={scenarioPage}
            rowsPerPage={scenariosPerPage}
            onPageChange={setScenarioPage}
            onRowsPerPageChange={(value) => {
              setScenariosPerPage(value);
              setScenarioPage(0);
            }}
            onToggle={toggle}
          />
        </Stack>
      </Paper>

      <RunHistory runs={runs} onRefresh={loadRuns} onOpen={openDetail} />
      <RunDetailDialog
        run={detail}
        loading={detailLoading}
        onClose={() => setDetail(null)}
        onRefresh={() => detail && openDetail(detail.run_id)}
      />
    </Stack>
  );
}

function ScopeAutocomplete<T>({
  label,
  loading,
  options,
  value,
  getLabel,
  onChange,
  disabled = false,
}: {
  label: string;
  loading: boolean;
  options: T[];
  value: T | string;
  getLabel: (option: T | string) => string;
  onChange: (option: T | string | null) => void;
  disabled?: boolean;
}) {
  return (
    <Autocomplete<T, false, false, true>
      freeSolo
      size="small"
      options={options}
      loading={loading}
      value={value}
      disabled={disabled}
      onChange={(_event, option) => onChange(option)}
      onInputChange={(_event, next, reason) => {
        if (reason === "input") onChange(next);
      }}
      getOptionLabel={getLabel}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          sx={{ minWidth: 220 }}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {loading ? <CircularProgress size={16} sx={{ mr: 1 }} /> : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
        />
      )}
    />
  );
}

function SelectedScenarioChips({ rows }: { rows: ExtractionScenarioRow[] }) {
  if (rows.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary">
        No scenarios selected.
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {rows.map((row) => (
        <Chip key={row.case_id} size="small" label={row.case_id} />
      ))}
    </Stack>
  );
}

function ScenarioList({
  rows,
  selected,
  loading,
  page,
  rowsPerPage,
  onPageChange,
  onRowsPerPageChange,
  onToggle,
}: {
  rows: ExtractionScenarioRow[];
  selected: Set<string>;
  loading: boolean;
  page: number;
  rowsPerPage: number;
  onPageChange: (page: number) => void;
  onRowsPerPageChange: (rowsPerPage: number) => void;
  onToggle: (caseId: string) => void;
}) {
  if (loading) {
    return (
      <Stack alignItems="center" sx={{ py: 3 }}>
        <CircularProgress size={24} />
      </Stack>
    );
  }
  if (rows.length === 0) {
    return <Typography color="text.secondary">No scenarios found.</Typography>;
  }
  const visibleRows = rows.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  return (
    <Stack spacing={1}>
      {visibleRows.map((row) => (
        <Paper key={row.case_id} variant="outlined" sx={{ p: 1.25 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Checkbox
              checked={selected.has(row.case_id)}
              onChange={() => onToggle(row.case_id)}
            />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" fontWeight={700}>
                {row.case_id}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {row.site || "Unknown site"} - {row.format || "Unknown format"}
              </Typography>
            </Box>
            <Chip size="small" variant="outlined" label={row.review_status} />
          </Stack>
        </Paper>
      ))}
      <TablePagination
        component="div"
        count={rows.length}
        page={page}
        rowsPerPage={rowsPerPage}
        rowsPerPageOptions={[10, 25, 50, 100]}
        onPageChange={(_event, nextPage) => onPageChange(nextPage)}
        onRowsPerPageChange={(event) =>
          onRowsPerPageChange(Number(event.target.value))
        }
      />
    </Stack>
  );
}

function LiveDot() {
  return (
    <Box
      sx={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        bgcolor: "info.main",
        "@keyframes sbar-live-dot": {
          "0%, 100%": { opacity: 1, transform: "scale(1)" },
          "50%": { opacity: 0.35, transform: "scale(0.65)" },
        },
        animation: "sbar-live-dot 1.1s ease-in-out infinite",
      }}
    />
  );
}

function RunHistory({
  runs,
  onRefresh,
  onOpen,
}: {
  runs: ScenarioRunSummary[];
  onRefresh: () => void;
  onOpen: (runId: string) => void;
}) {
  const hasActive = runs.some((r) => ACTIVE_STATUSES.has(r.status));
  useAutoRefresh(hasActive, onRefresh, 5000);

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          Previous scenario runs
        </Typography>
        {hasActive && <LiveDot />}
        {hasActive && (
          <Typography variant="caption" color="info.main">
            Live
          </Typography>
        )}
        <Button onClick={onRefresh} startIcon={<RefreshIcon />}>
          Refresh
        </Button>
      </Stack>
      <Stack spacing={1}>
        {runs.length === 0 ? (
          <Typography color="text.secondary">No scenario runs yet.</Typography>
        ) : (
          runs.map((run) => (
            <RunHistoryRow key={run.run_id} run={run} onOpen={onOpen} />
          ))
        )}
      </Stack>
    </Paper>
  );
}

function RunHistoryRow({
  run,
  onOpen,
}: {
  run: ScenarioRunSummary;
  onOpen: (runId: string) => void;
}) {
  const isActive = ACTIVE_STATUSES.has(run.status);
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.25,
        transition: "border-color 0.3s",
        ...(isActive ? { borderColor: "info.light" } : {}),
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" fontWeight={700}>
            {run.case_count} scenario{run.case_count === 1 ? "" : "s"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {formatDate(run.triggered_at)} - {run.guideline_id} -{" "}
            {run.completeness_subdomain}
          </Typography>
        </Box>
        <Chip
          size="small"
          color={statusColor(run.status)}
          label={run.status}
          sx={isActive ? PULSE_SX : undefined}
        />
        <Typography variant="caption" color="text.secondary">
          {run.completed_count}/{run.case_count} complete
        </Typography>
        <IconButton size="small" onClick={() => onOpen(run.run_id)}>
          <VisibilityIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Paper>
  );
}

function RunDetailDialog({
  run,
  loading,
  onClose,
  onRefresh,
}: {
  run: ScenarioRunSummary | null;
  loading: boolean;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const isActive = Boolean(run && ACTIVE_STATUSES.has(run.status));
  const [tab, setTab] = useState(0);
  useAutoRefresh(isActive, onRefresh, 3000);

  return (
    <Dialog open={Boolean(run)} onClose={onClose} maxWidth="lg" fullWidth>
      {isActive && (
        <LinearProgress
          sx={{ position: "absolute", top: 0, left: 0, right: 0, zIndex: 1 }}
        />
      )}
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography variant="h6" sx={{ flex: 1 }}>
            Scenario run detail
          </Typography>
          {isActive && (
            <Typography variant="caption" color="info.main" sx={{ pr: 0.5 }}>
              Auto-refreshing...
            </Typography>
          )}
          <Button onClick={onRefresh} disabled={loading}>
            Refresh
          </Button>
          <IconButton onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </Stack>
        <Tabs value={tab} onChange={(_e, v) => setTab(v as number)} sx={{ mt: 1 }}>
          <Tab
            icon={<AccountTreeIcon fontSize="small" />}
            iconPosition="start"
            label="Workflow validation"
          />
          <Tab
            icon={<OpenInNewIcon fontSize="small" />}
            iconPosition="start"
            label="Consumer validation"
          />
        </Tabs>
      </DialogTitle>
      <DialogContent dividers>
        {loading && !run ? (
          <Stack alignItems="center" sx={{ py: 4 }}>
            <CircularProgress size={28} />
          </Stack>
        ) : run ? (
          <>
            {tab === 0 && (
              <Stack spacing={2}>
                <RunDetailHeader run={run} />
                {(run.children || []).map((child) => (
                  <ChildRunCard key={child.run_id} child={child} />
                ))}
              </Stack>
            )}
            {tab === 1 && (
              <Stack spacing={3}>
                <RunDetailHeader run={run} />
                {(run.children || []).map((child) => (
                  <ConsumerValidationPanel key={child.run_id} child={child} />
                ))}
              </Stack>
            )}
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function RunDetailHeader({ run }: { run: ScenarioRunSummary }) {
  const isActive = ACTIVE_STATUSES.has(run.status);
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
        Run {run.run_id} - started {formatDate(run.triggered_at)}
      </Typography>
      <Chip
        size="small"
        color={statusColor(run.status)}
        label={run.status}
        sx={isActive ? PULSE_SX : undefined}
      />
    </Stack>
  );
}

function ChildRunCard({ child }: { child: ScenarioRunChild }) {
  const assessment = child.assessment;
  const isActive = ACTIVE_STATUSES.has(child.status);
  const sbarMarkdown = assessment ? composeSbarMarkdown(assessment) : "";
  const backgroundParts = assessment
    ? normaliseBackgroundParts(assessment.background_parts)
    : [];
  const completenessFinding = assessment
    ? normaliseCompletenessFinding(assessment.completeness_result_json)
    : null;
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.5,
        transition: "border-color 0.4s, box-shadow 0.4s",
        ...(isActive
          ? {
              borderColor: "info.light",
              boxShadow: (theme) => `0 0 0 1px ${theme.palette.info.light}`,
            }
          : {}),
      }}
    >
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="subtitle2" sx={{ flex: 1 }}>
            {child.case_id}
          </Typography>
          <Chip
            size="small"
            color={statusColor(child.status)}
            label={child.status}
            sx={isActive ? PULSE_SX : undefined}
          />
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Assessment {child.assessment_id || "not created yet"}
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {(child.stages || []).map((stage) => {
            const stageActive = ACTIVE_STATUSES.has(stage.status);
            return (
              <Chip
                key={`${child.run_id}-${stage.step_id}`}
                size="small"
                variant="outlined"
                color={statusColor(stage.status)}
                label={`${stageDisplayName(stage)}: ${stage.status}`}
                title={stage.step_id}
                sx={stageActive ? PULSE_SX : undefined}
              />
            );
          })}
        </Stack>
        {isActive && !assessment ? (
          <Stack spacing={0.75} sx={{ mt: 1 }}>
            <Skeleton variant="text" width="60%" height={20} />
            <Skeleton variant="rectangular" height={56} />
            <Skeleton variant="text" width="80%" height={20} />
            <Skeleton variant="rectangular" height={80} />
          </Stack>
        ) : null}
        {assessment ? (
          <Box sx={{ mt: 1 }}>
            <SbarFinalView
              markdown={sbarMarkdown}
              backgroundParts={backgroundParts}
              completenessFinding={completenessFinding}
              dense
              testOnly
              testIdPrefix={`scenario-sbar-${child.case_id}`}
            />
          </Box>
        ) : null}
        {child.completion_event ? (
          <CompletionEventPanel event={child.completion_event} />
        ) : null}
      </Stack>
    </Paper>
  );
}

function CompletionEventPanel({ event }: { event: ReferralAssessmentCompletedEvent }) {
  const [open, setOpen] = useState(false);
  return (
    <Box>
      <Divider sx={{ my: 0.5 }} />
      <Button
        size="small"
        variant="text"
        color="secondary"
        startIcon={
          <ExpandMoreIcon
            fontSize="small"
            sx={{
              transform: open ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 0.2s",
            }}
          />
        }
        onClick={() => setOpen((v) => !v)}
        data-testid="completion-event-toggle"
      >
        Completion event published to{" "}
        <Typography
          component="span"
          variant="caption"
          sx={{ fontFamily: "monospace", ml: 0.5 }}
        >
          referral-assessments-output
        </Typography>
      </Button>
      <Collapse in={open}>
        <Box
          component="pre"
          data-testid="completion-event-json"
          sx={{
            bgcolor: "grey.50",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1.5,
            fontSize: "0.72rem",
            fontFamily: "monospace",
            overflowX: "auto",
            maxHeight: 320,
            mt: 0.5,
          }}
        >
          {JSON.stringify(event, null, 2)}
        </Box>
      </Collapse>
    </Box>
  );
}

function ConsumerValidationPanel({ child }: { child: ScenarioRunChild }) {
  const [widgetToken, setWidgetToken] = useState<string | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(false);
  const [widgetEvents, setWidgetEvents] = useState<string[]>([]);
  const widgetRef = useRef<HTMLElement | null>(null);
  const event = child.completion_event;
  const assessmentId = event?.assessment_id || child.assessment_id;

  const loadWidget = async () => {
    if (!assessmentId) return;
    setTokenLoading(true);
    setTokenError(null);
    try {
      const res = await fetch("/api/sdk/widget-token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assessment_id: assessmentId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Token exchange failed");
      setWidgetToken(data.widget_token as string);
    } catch (err) {
      setTokenError(err instanceof Error ? err.message : "Failed to get token");
    } finally {
      setTokenLoading(false);
    }
  };

  useEffect(() => {
    if (!widgetToken || !widgetRef.current) return;
    const el = widgetRef.current;
    const LEO_EVENTS = ["leo:loaded", "leo:completeness-incomplete", "leo:completeness-unavailable"];
    const handlers = LEO_EVENTS.map((name) => {
      const handler = () =>
        setWidgetEvents((prev) => [
          ...prev,
          `${new Date().toLocaleTimeString()} - ${name}`,
        ]);
      el.addEventListener(name, handler);
      return { name, handler };
    });
    return () => {
      handlers.forEach(({ name, handler }) => el.removeEventListener(name, handler));
    };
  }, [widgetToken]);

  if (!event && !assessmentId) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {child.case_id}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Workflow not yet complete for this case. Run the scenario first.
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="subtitle2" sx={{ flex: 1 }}>
            {child.case_id}
          </Typography>
          <Chip size="small" color={statusColor(child.status)} label={child.status} />
        </Stack>

        <Box>
          <Typography variant="overline" color="text.secondary">
            Step 1 - Completion event received
          </Typography>
          <Box
            component="pre"
            data-testid="consumer-completion-event"
            sx={{
              bgcolor: "grey.50",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              p: 1.5,
              fontSize: "0.72rem",
              fontFamily: "monospace",
              overflowX: "auto",
              maxHeight: 220,
              mt: 0.5,
            }}
          >
            {event
              ? JSON.stringify(event, null, 2)
              : `{ "assessment_id": "${assessmentId || "pending"}" }`}
          </Box>
        </Box>

        <Box>
          <Typography variant="overline" color="text.secondary">
            Step 2 - Exchange host secret for widget token
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
            <Button
              variant="outlined"
              size="small"
              onClick={loadWidget}
              disabled={!assessmentId || tokenLoading || Boolean(widgetToken)}
              startIcon={tokenLoading ? <CircularProgress size={14} /> : undefined}
              data-testid="load-widget-button"
            >
              {widgetToken ? "Token active" : "Load widget"}
            </Button>
            {widgetToken && (
              <Typography variant="caption" color="success.main">
                Token obtained - widget loading
              </Typography>
            )}
            {tokenError && (
              <Typography variant="caption" color="error.main">
                {tokenError}
              </Typography>
            )}
          </Stack>
        </Box>

        {widgetToken && assessmentId && (
          <Box>
            <Typography variant="overline" color="text.secondary">
              Step 3 - Widget render (CDN component, no internal auth)
            </Typography>
            <Box
              sx={{
                border: "1px dashed",
                borderColor: "divider",
                borderRadius: 1,
                p: 1,
                mt: 0.5,
                minHeight: 120,
              }}
              data-testid="widget-host"
            >
              <leo-sbar
                ref={widgetRef}
                data-testid="leo-sbar-widget"
                assessment-id={assessmentId}
                widget-token={widgetToken}
                proxy-origin={typeof window !== "undefined" ? window.location.origin : ""}
              />
            </Box>
            {widgetEvents.length > 0 && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="overline" color="text.secondary">
                  Widget events
                </Typography>
                <Stack spacing={0.25} sx={{ mt: 0.25 }}>
                  {widgetEvents.map((msg, i) => (
                    <Typography
                      key={i}
                      variant="caption"
                      sx={{ fontFamily: "monospace" }}
                      data-testid="widget-event-log"
                    >
                      {msg}
                    </Typography>
                  ))}
                </Stack>
              </Box>
            )}
          </Box>
        )}
      </Stack>
    </Paper>
  );
}
