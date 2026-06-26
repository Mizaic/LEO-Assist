/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E647765A")
 */
"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import MuiStep from "@mui/material/Step";
import MuiStepLabel from "@mui/material/StepLabel";
import MuiStepper from "@mui/material/Stepper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ConfirmDialog from "@/components/ConfirmDialog";
import {
  FilterBar,
  ProgressiveReveal,
  ProgressStrip,
  ReviewListCard,
  StatHero,
  ToolbarActions,
  type FilterChip,
  type ReviewListItem,
  type StatTile,
} from "@leo/design-system";

interface ReplaySummary {
  id: string;
  ruleset_version: string | null;
  scope_type: string;
  scope_id: string;
  guideline_id: string | null;
  regressions_count: number;
  passes_count: number;
  drift_count: number;
  total_count: number;
  completed_at: string;
}

interface BitmapStatus {
  active_version: string | null;
  rule_count: number;
  compile_timestamp: string | null;
  message?: string;
  scope_type?: string;
  scope_id?: string;
  policy_mode?: string;
  compile_stats?: Record<string, number>;
}

interface VersionEntry { version: string; active: boolean; scope_type?: string; scope_id?: string; }

type ScopeType = "global" | "guideline" | "domain" | "subdomain" | "custom";
type PolicyMode = "advisory" | "strict";

const SCOPE_OPTIONS: ReadonlyArray<{ value: ScopeType; label: string }> = [
  { value: "global", label: "Global" },
  { value: "guideline", label: "Guideline" },
  { value: "domain", label: "Domain" },
  { value: "subdomain", label: "Subdomain" },
  { value: "custom", label: "Custom" },
];

const POLICY_OPTIONS: ReadonlyArray<{ value: PolicyMode; label: string }> = [
  { value: "advisory", label: "Advisory" },
  { value: "strict", label: "Strict" },
];

// Step labels preserved for screen-reader / test context
const COMPILE_STEPS = ["Rules approved", "Compile rules", "Go live"];

function buildVersionItem(v: VersionEntry, activating: string | null, onActivate: (ver: string) => void): ReviewListItem {
  return {
    id: v.version,
    tone: v.active ? "positive" : "neutral",
    title: <span style={{ fontFamily: "monospace", fontSize: 13 }}>{v.version}</span>,
    chips: v.active ? <Chip label="Live" size="small" color="success" /> : null,
    actions: v.active ? undefined : (
      <Button size="small" variant="outlined" disabled={activating === v.version} onClick={() => onActivate(v.version)} aria-label={`Make version ${v.version} live`}>
        {activating === v.version ? <CircularProgress size={14} /> : "Make this live"}
      </Button>
    ),
  };
}

export default function BitmapLifecycleSection() {
  const [scopeType, setScopeType] = useState<ScopeType>("global");
  const [scopeId, setScopeId] = useState("default");
  const [policyMode, setPolicyMode] = useState<PolicyMode>("advisory");
  const [distanceChild, setDistanceChild] = useState("");
  const [distanceParent, setDistanceParent] = useState("");
  const [status, setStatus] = useState<BitmapStatus | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [latestReplay, setLatestReplay] = useState<ReplaySummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [activatingVersion, setActivatingVersion] = useState<string | null>(null);
  const [confirmVersion, setConfirmVersion] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (scopeType === "global" && scopeId !== "default") setScopeId("default");
  }, [scopeId, scopeType]);

  const fetchStatus = useCallback(async (): Promise<BitmapStatus | null> => {
    const qs = new URLSearchParams({ scope_type: scopeType, scope_id: scopeId || "default" }).toString();
    const replayQs = new URLSearchParams({ scope_type: scopeType, scope_id: scopeId || "default", limit: "1" }).toString();
    try {
      const [statusResp, versionsResp, replayResp] = await Promise.all([
        fetch(`/api/terminology/guidelines/bitmap/status?${qs}`),
        fetch(`/api/terminology/guidelines/bitmap/versions?${qs}`),
        fetch(`/api/guidance/test-patients/replay-reports?${replayQs}`),
      ]);
      if (!statusResp.ok || !versionsResp.ok) throw new Error("fetch failed");
      const statusData: BitmapStatus = await statusResp.json();
      setStatus(statusData);
      setVersions(await versionsResp.json());
      if (replayResp.ok) {
        const reports = (await replayResp.json()) as ReplaySummary[];
        setLatestReplay(reports[0] || null);
      } else {
        setLatestReplay(null);
      }
      setError(null);
      return statusData;
    } catch {
      setError("Could not load the current status. Please refresh the page.");
      return null;
    }
  }, [scopeId, scopeType]);

  useEffect(() => { fetchStatus(); }, [fetchStatus, refreshKey]);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const handleCompile = useCallback(async () => {
    setCompiling(true);
    setError(null);
    try {
      const resp = await fetch("/api/terminology/guidelines/bitmap/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope_type: scopeType, scope_id: scopeId || "default", policy_mode: policyMode, distance_child_override: distanceChild === "" ? null : Number(distanceChild), distance_parent_override: distanceParent === "" ? null : Number(distanceParent) }),
      });
      if (!resp.ok) throw new Error(await resp.text());

      const pollStart = Date.now();
      const MAX_POLL_MS = 300_000; // 5 min

      pollRef.current = setInterval(async () => {
        const s = await fetchStatus();
        const elapsed = Date.now() - pollStart;
        const isDone = s?.active_version != null || s?.compile_stats != null;
        if (isDone || elapsed > MAX_POLL_MS) {
          clearInterval(pollRef.current!);
          setCompiling(false);
          setRefreshKey((n) => n + 1);
        }
      }, 3000);
    } catch {
      setError("Could not start the compile. Please try again.");
      setCompiling(false);
    }
  }, [distanceChild, distanceParent, fetchStatus, policyMode, scopeId, scopeType]);

  const handleActivate = useCallback(async (version: string) => {
    setActivatingVersion(version);
    setError(null);
    try {
      const resp = await fetch(`/api/terminology/guidelines/bitmap/versions/${encodeURIComponent(version)}/activate`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope_type: scopeType, scope_id: scopeId || "default" }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setConfirmVersion(null);
      setRefreshKey((n) => n + 1);
    } catch {
      setError("Could not activate this version. Please try again.");
    } finally {
      setActivatingVersion(null);
    }
  }, [scopeId, scopeType]);

  const handleRollback = useCallback(async () => {
    setRollingBack(true);
    setError(null);
    try {
      const resp = await fetch("/api/terminology/guidelines/bitmap/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope_type: scopeType, scope_id: scopeId || "default" }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setRefreshKey((n) => n + 1);
    } catch {
      setError("Could not roll back this scope. Check there is at least one previous version.");
    } finally {
      setRollingBack(false);
    }
  }, [scopeId, scopeType]);

  const activeStep = status?.active_version ? 2 : versions.length > 0 ? 1 : 0;

  const scopeChips: FilterChip[] = SCOPE_OPTIONS.map((o) => ({
    id: o.value,
    label: o.label,
    active: scopeType === o.value,
    onToggle: () => setScopeType(o.value),
  }));

  const compileStats = status?.compile_stats;
  const statTiles: StatTile[] = compileStats ? [
    { id: "included", label: "Included", value: compileStats.rules_included ?? 0 },
    { id: "excluded", label: "Excluded", value: compileStats.rules_excluded ?? 0 },
    { id: "violations", label: "Policy violations", value: compileStats.policy_violations ?? 0 },
  ] : [];

  return (
    <Box>
      {/* -- Workflow progress -------------------------------------------- */}
      <MuiStepper activeStep={activeStep} sx={{ mb: 2 }}>
        {COMPILE_STEPS.map((label) => (
          <MuiStep key={label}>
            <MuiStepLabel>{label}</MuiStepLabel>
          </MuiStep>
        ))}
      </MuiStepper>

      <ProgressStrip
        label={`Step ${activeStep + 1} of ${COMPILE_STEPS.length}`}
        value={activeStep}
        total={COMPILE_STEPS.length - 1}
        subtitle={`${activeStep + 1} of ${COMPILE_STEPS.length} steps complete`}
        tone={activeStep === COMPILE_STEPS.length - 1 ? "positive" : "neutral"}
      />

      {error && <Alert severity="error" sx={{ mb: 2, mt: 2 }}>{error}</Alert>}

      {/* -- Scope filter ------------------------------------------------- */}
      <Box sx={{ mt: 2, mb: 1.5 }}>
        <FilterBar
          search={scopeType === "global" ? "" : scopeId}
          onSearchChange={(v) => { if (scopeType !== "global") setScopeId(v); }}
          searchPlaceholder={scopeType === "subdomain" ? "cancer_audit:symptoms" : "NG12 or cancer_audit"}
          aria-label="Scope filter"
          chips={scopeChips}
        />
      </Box>

      {/* -- Policy mode -------------------------------------------------- */}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary">Policy:</Typography>
        <ToolbarActions
          align="start"
          actions={POLICY_OPTIONS.map((o) => ({
            id: o.value,
            label: o.label,
            variant: policyMode === o.value ? "primary" : "secondary",
            onClick: () => setPolicyMode(o.value),
          }))}
        />
      </Stack>

      {/* -- Advanced options --------------------------------------------- */}
      <Box sx={{ mb: 2 }}>
        <ProgressiveReveal summary="Advanced options">
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 1 }}>
            <TextField size="small" label="Child depth override" value={distanceChild} onChange={(e) => setDistanceChild(e.target.value)} sx={{ width: 190 }} helperText="Optional. Leave empty to use rule default." />
            <TextField size="small" label="Parent depth override" value={distanceParent} onChange={(e) => setDistanceParent(e.target.value)} sx={{ width: 190 }} helperText="Optional. Leave empty to use rule default." />
          </Stack>
        </ProgressiveReveal>
      </Box>

      {/* -- Status summary ----------------------------------------------- */}
      {status && (
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="body2" color="text.secondary">Active version:</Typography>
          {status.active_version ? <Chip label={status.active_version} color="success" size="small" /> : <Chip label="No active version" size="small" />}
          {status.rule_count > 0 && <Typography variant="body2" color="text.secondary">{status.rule_count} rule{status.rule_count !== 1 ? "s" : ""} live</Typography>}
        </Stack>
      )}
      {status?.message && <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{status.message}</Typography>}

      {/* -- Compile stats StatHero --------------------------------------- */}
      {statTiles.length > 0 && <StatHero stats={statTiles} />}

      {/* -- Compile / rollback actions ----------------------------------- */}
      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <ToolbarActions
          actions={[
            { id: "compile", label: compiling ? "Compiling..." : "Compile rules", variant: "primary", onClick: handleCompile, disabled: compiling, loading: compiling },
            { id: "rollback", label: rollingBack ? "Rolling back..." : "Rollback scope", variant: "secondary", onClick: handleRollback, disabled: rollingBack || versions.length < 2, loading: rollingBack },
          ]}
        />
      </Stack>

      {compiling && (
        <Box sx={{ mb: 2 }}>
          <ProgressStrip label="Building the lookup index..." value={0} total={1} subtitle="This may take up to a few minutes." />
        </Box>
      )}

      {/* -- Latest replay ------------------------------------------------ */}
      {latestReplay && (
        <Box sx={{ mb: 2, p: 1.5, borderRadius: 1, bgcolor: latestReplay.regressions_count > 0 ? "error.50" : "success.50", border: "1px solid", borderColor: latestReplay.regressions_count > 0 ? "error.200" : "success.200" }}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="body2">Last test patient replay (ruleset {latestReplay.ruleset_version || "n/a"}):</Typography>
            <Chip size="small" color={latestReplay.regressions_count === 0 ? "success" : "error"} label={`${latestReplay.regressions_count} regression${latestReplay.regressions_count === 1 ? "" : "s"}`} />
            <Chip size="small" variant="outlined" label={`${latestReplay.passes_count} pass`} />
            <Chip size="small" variant="outlined" label={`${latestReplay.total_count} patients`} />
            <Box sx={{ flex: 1 }} />
            <Button component={Link} href="/admin/knowledge?tab=test-patients" size="small" variant="text">Open library</Button>
          </Stack>
          {latestReplay.regressions_count > 0 && <Typography variant="caption" color="error">The replay flagged regressions. Roll back to a known-good version above if needed.</Typography>}
        </Box>
      )}

      {/* -- Version list ------------------------------------------------- */}
      {versions.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>All compiled versions</Typography>
          <ReviewListCard
            items={versions.map((v) => buildVersionItem(v, activatingVersion, setConfirmVersion))}
          />
        </Box>
      )}

      {confirmVersion && (
        <ConfirmDialog
          title="Make this version live?"
          body={`This will update how the system matches patients to guidelines. Version ${confirmVersion} will become active straight away.`}
          confirmLabel="Yes, go live"
          cancelLabel="Cancel"
          variant="danger"
          onConfirm={() => handleActivate(confirmVersion)}
          onCancel={() => setConfirmVersion(null)}
        />
      )}
    </Box>
  );
}
