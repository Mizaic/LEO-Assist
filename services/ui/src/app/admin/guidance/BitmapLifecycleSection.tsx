"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ConfirmDialog from "@/components/ConfirmDialog";

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

interface VersionEntry {
  version: string;
  active: boolean;
  scope_type?: string;
  scope_id?: string;
}

const STEPS = ["Rules approved", "Compile rules", "Go live"];

export default function BitmapLifecycleSection() {
  const [scopeType, setScopeType] = useState<"global" | "guideline" | "domain" | "subdomain" | "custom">("global");
  const [scopeId, setScopeId] = useState("default");
  const [policyMode, setPolicyMode] = useState<"advisory" | "strict">("advisory");
  const [distanceChild, setDistanceChild] = useState("");
  const [distanceParent, setDistanceParent] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [status, setStatus] = useState<BitmapStatus | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [activatingVersion, setActivatingVersion] = useState<string | null>(null);
  const [confirmVersion, setConfirmVersion] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (scopeType === "global" && scopeId !== "default") {
      setScopeId("default");
    }
  }, [scopeId, scopeType]);

  const fetchStatus = useCallback(async () => {
    const qs = new URLSearchParams({
      scope_type: scopeType,
      scope_id: scopeId || "default",
    }).toString();
    try {
      const [statusResp, versionsResp] = await Promise.all([
        fetch(`/api/terminology/guidelines/bitmap/status?${qs}`),
        fetch(`/api/terminology/guidelines/bitmap/versions?${qs}`),
      ]);
      if (!statusResp.ok || !versionsResp.ok) throw new Error("fetch failed");
      setStatus(await statusResp.json());
      setVersions(await versionsResp.json());
      setError(null);
    } catch {
      setError("Could not load the current status. Please refresh the page.");
    }
  }, [scopeId, scopeType]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus, refreshKey]);

  const handleCompile = useCallback(async () => {
    setCompiling(true);
    setError(null);
    try {
      const resp = await fetch("/api/terminology/guidelines/bitmap/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope_type: scopeType,
          scope_id: scopeId || "default",
          policy_mode: policyMode,
          distance_child_override: distanceChild === "" ? null : Number(distanceChild),
          distance_parent_override: distanceParent === "" ? null : Number(distanceParent),
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());

      pollRef.current = setInterval(async () => {
        await fetchStatus();
      }, 3000);

      setTimeout(() => {
        if (pollRef.current) clearInterval(pollRef.current);
        setCompiling(false);
        setRefreshKey((n) => n + 1);
      }, 30000);
    } catch {
      setError("Could not start the compile. Please try again.");
      setCompiling(false);
    }
  }, [distanceChild, distanceParent, fetchStatus, policyMode, scopeId, scopeType]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const handleActivate = useCallback(async (version: string) => {
    setActivatingVersion(version);
    setError(null);
    try {
      const resp = await fetch(
        `/api/terminology/guidelines/bitmap/versions/${encodeURIComponent(version)}/activate`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scope_type: scopeType,
            scope_id: scopeId || "default",
          }),
        }
      );
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
        body: JSON.stringify({
          scope_type: scopeType,
          scope_id: scopeId || "default",
        }),
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

  return (
    <Box>
      <Stepper activeStep={activeStep} sx={{ mb: 3 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label="Scope type"
          value={scopeType}
          onChange={(e) => setScopeType(e.target.value as "global" | "guideline" | "domain" | "subdomain" | "custom")}
          sx={{ minWidth: 170 }}
        >
          <MenuItem value="global">Global</MenuItem>
          <MenuItem value="guideline">Guideline</MenuItem>
          <MenuItem value="domain">Domain</MenuItem>
          <MenuItem value="subdomain">Subdomain</MenuItem>
          <MenuItem value="custom">Custom</MenuItem>
        </TextField>
        <TextField
          size="small"
          label="Scope id"
          value={scopeId}
          onChange={(e) => setScopeId(e.target.value)}
          placeholder={scopeType === "subdomain" ? "cancer_audit:symptoms" : "NG12 or cancer_audit"}
          sx={{ minWidth: 220 }}
          disabled={scopeType === "global"}
        />
        <TextField
          select
          size="small"
          label="Policy"
          value={policyMode}
          onChange={(e) => setPolicyMode(e.target.value as "advisory" | "strict")}
          sx={{ minWidth: 140 }}
        >
          <MenuItem value="advisory">Advisory</MenuItem>
          <MenuItem value="strict">Strict</MenuItem>
        </TextField>
      </Stack>
      <Button
        variant="text"
        size="small"
        sx={{ mb: 1 }}
        onClick={() => setShowAdvanced((v) => !v)}
      >
        {showAdvanced ? "Hide advanced options" : "Show advanced options"}
      </Button>
      <Collapse in={showAdvanced} timeout="auto" unmountOnExit>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mb: 2 }}>
          <TextField
            size="small"
            label="Child depth override"
            value={distanceChild}
            onChange={(e) => setDistanceChild(e.target.value)}
            sx={{ width: 190 }}
            helperText="Optional. Leave empty to use rule default."
          />
          <TextField
            size="small"
            label="Parent depth override"
            value={distanceParent}
            onChange={(e) => setDistanceParent(e.target.value)}
            sx={{ width: 190 }}
            helperText="Optional. Leave empty to use rule default."
          />
        </Stack>
      </Collapse>

      {status && (
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Active version:
          </Typography>
          {status.active_version ? (
            <Chip label={status.active_version} color="success" size="small" />
          ) : (
            <Chip label="No active version" size="small" />
          )}
          {status.rule_count > 0 && (
            <Typography variant="body2" color="text.secondary">
              {status.rule_count} rule{status.rule_count !== 1 ? "s" : ""} live
            </Typography>
          )}
          <Chip label={`${status.scope_type || scopeType}:${status.scope_id || scopeId}`} size="small" />
          {status.policy_mode && <Chip label={`Policy: ${status.policy_mode}`} size="small" />}
        </Stack>
      )}

      {status?.message && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {status.message}
        </Typography>
      )}

      <Button
        variant="contained"
        disabled={compiling}
        onClick={handleCompile}
        startIcon={compiling ? <CircularProgress size={16} /> : undefined}
        aria-label="Compile rules into the lookup index"
        sx={{ mb: 2 }}
      >
        {compiling ? "Compiling..." : "Compile rules"}
      </Button>
      <Button
        variant="outlined"
        sx={{ ml: 1, mb: 2 }}
        disabled={rollingBack || versions.length < 2}
        onClick={handleRollback}
      >
        {rollingBack ? "Rolling back..." : "Rollback scope"}
      </Button>

      {status?.compile_stats && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
          Included: {status.compile_stats.rules_included ?? 0} | Excluded: {status.compile_stats.rules_excluded ?? 0} |
          Policy issues: {status.compile_stats.policy_violations ?? 0}
        </Typography>
      )}

      {compiling && (
        <Box sx={{ mb: 2 }}>
          <LinearProgress />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            Building the lookup index. This takes up to 30 seconds.
          </Typography>
        </Box>
      )}

      {versions.length > 0 && (
        <Box>
          <Divider sx={{ my: 2 }} />
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
            All compiled versions
          </Typography>
          <Stack spacing={1}>
            {versions.map((v) => (
              <Stack
                key={v.version}
                direction="row"
                spacing={2}
                alignItems="center"
                sx={{
                  p: 1.5,
                  borderRadius: 1,
                  bgcolor: v.active ? "success.50" : "grey.50",
                  border: "1px solid",
                  borderColor: v.active ? "success.200" : "grey.200",
                }}
              >
                <Typography variant="body2" sx={{ flex: 1, fontFamily: "monospace" }}>
                  {v.version}
                </Typography>
                {v.active ? (
                  <Chip label="Live" color="success" size="small" />
                ) : (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={activatingVersion === v.version}
                    onClick={() => setConfirmVersion(v.version)}
                    aria-label={`Make version ${v.version} live`}
                  >
                    Make this live
                  </Button>
                )}
              </Stack>
            ))}
          </Stack>
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
