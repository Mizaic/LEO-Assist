"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Typography from "@mui/material/Typography";
import ConfirmDialog from "@/components/ConfirmDialog";

interface BitmapStatus {
  active_version: string | null;
  rule_count: number;
  compile_timestamp: string | null;
  message?: string;
}

interface VersionEntry {
  version: string;
  active: boolean;
}

const STEPS = ["Rules approved", "Compile rules", "Go live"];

export default function BitmapLifecycleSection() {
  const [status, setStatus] = useState<BitmapStatus | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [activatingVersion, setActivatingVersion] = useState<string | null>(null);
  const [confirmVersion, setConfirmVersion] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const fetchStatus = useCallback(async () => {
    try {
      const [statusResp, versionsResp] = await Promise.all([
        fetch("/api/terminology/guidelines/bitmap/status"),
        fetch("/api/terminology/guidelines/bitmap/versions"),
      ]);
      if (!statusResp.ok || !versionsResp.ok) throw new Error("fetch failed");
      setStatus(await statusResp.json());
      setVersions(await versionsResp.json());
      setError(null);
    } catch {
      setError("Could not load the current status. Please refresh the page.");
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus, refreshKey]);

  const handleCompile = useCallback(async () => {
    setCompiling(true);
    setError(null);
    try {
      const resp = await fetch("/api/terminology/guidelines/bitmap/compile", {
        method: "POST",
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
  }, [fetchStatus]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const handleActivate = useCallback(async (version: string) => {
    setActivatingVersion(version);
    setError(null);
    try {
      const resp = await fetch(
        `/api/terminology/guidelines/bitmap/versions/${encodeURIComponent(version)}/activate`,
        { method: "PUT" }
      );
      if (!resp.ok) throw new Error(await resp.text());
      setConfirmVersion(null);
      setRefreshKey((n) => n + 1);
    } catch {
      setError("Could not activate this version. Please try again.");
    } finally {
      setActivatingVersion(null);
    }
  }, []);

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
