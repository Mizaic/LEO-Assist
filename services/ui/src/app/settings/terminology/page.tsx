"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import LinearProgress from "@mui/material/LinearProgress";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DownloadingIcon from "@mui/icons-material/Downloading";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PackageStatus {
  label: string;
  local_version: string | null;
  trud_version: string | null;
  trud_date: string | null;
  trud_size_mb: number | null;
  up_to_date: boolean;
}

interface Neo4jCounts {
  active_concepts?: number;
  terms?: number;
  is_a_rels?: number;
  icd10_maps?: number;
  read_maps?: number;
}

interface StatusResponse {
  packages: Record<string, PackageStatus>;
  neo4j: Neo4jCounts;
}

interface LogLine {
  msg: string;
  level?: string;
  pct?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n: number | undefined): string {
  if (n == null) return "--";
  return n.toLocaleString("en-GB");
}

function VersionChip({ pkg }: { pkg: PackageStatus }) {
  if (pkg.up_to_date) {
    return (
      <Chip
        icon={<CheckCircleOutlineIcon />}
        label="Up to date"
        color="success"
        size="small"
        sx={{ flexShrink: 0 }}
      />
    );
  }
  if (!pkg.local_version) {
    return (
      <Chip
        label="Not on disk"
        color="default"
        size="small"
        sx={{ flexShrink: 0 }}
      />
    );
  }
  return (
    <Chip
      label="Update available"
      color="warning"
      size="small"
      icon={<WarningAmberIcon />}
      sx={{ flexShrink: 0 }}
    />
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "baseline" }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 100 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {value}
      </Typography>
    </Box>
  );
}

function PackageCard({ pkg }: { pkg: PackageStatus }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, flex: 1, minWidth: 0 }}>
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" mb={1.5} gap={1}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
          {pkg.label}
        </Typography>
        <VersionChip pkg={pkg} />
      </Stack>
      <Stack spacing={0.75}>
        <Row label="On disk" value={pkg.local_version ?? <em style={{ opacity: 0.5 }}>not downloaded</em>} />
        <Row
          label="TRUD latest"
          value={
            pkg.trud_version
              ? `${pkg.trud_version}${pkg.trud_date ? ` — ${pkg.trud_date}` : ""}`
              : "--"
          }
        />
        {pkg.trud_size_mb != null && (
          <Row label="Download" value={`${pkg.trud_size_mb} MB`} />
        )}
      </Stack>
    </Paper>
  );
}

function Neo4jCounts({ counts }: { counts: Neo4jCounts }) {
  const items = [
    { label: "Active concepts", value: counts.active_concepts },
    { label: "Terms (descriptions)", value: counts.terms },
    { label: "IS_A relationships", value: counts.is_a_rels },
    { label: "ICD-10 mappings", value: counts.icd10_maps },
    { label: "Read code mappings", value: counts.read_maps },
  ];
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
        <HubOutlinedIcon sx={{ color: "primary.main" }} />
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Knowledge graph — current counts
        </Typography>
      </Stack>
      <Stack direction="row" flexWrap="wrap" gap={1.5}>
        {items.map((item) => (
          <Box key={item.label} sx={{ minWidth: 160 }}>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              {fmt(item.value)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {item.label}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// Log panel
// ---------------------------------------------------------------------------

function LogPanel({ lines }: { lines: LogLine[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  if (lines.length === 0) return null;

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.5,
        maxHeight: 360,
        overflowY: "auto",
        bgcolor: "grey.950",
        fontFamily: "JetBrains Mono, monospace",
        fontSize: "0.72rem",
      }}
    >
      {lines.map((line, i) => (
        <Box
          key={i}
          sx={{
            color:
              line.level === "error" || line.level === "critical"
                ? "error.light"
                : line.level === "warning"
                  ? "warning.light"
                  : "grey.300",
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          {line.pct != null ? (
            <Stack direction="row" alignItems="center" spacing={1}>
              <Box sx={{ flex: 1 }}>
                <LinearProgress variant="determinate" value={line.pct} sx={{ height: 6, borderRadius: 1 }} />
              </Box>
              <Typography variant="caption" sx={{ color: "grey.400", minWidth: 36 }}>
                {line.pct}%
              </Typography>
            </Stack>
          ) : (
            line.msg
          )}
        </Box>
      ))}
      <div ref={bottomRef} />
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const PACKAGE_KEYS = ["snomed", "dmd"] as const;
type PkgKey = (typeof PACKAGE_KEYS)[number];

export default function TerminologyPage() {
  const router = useRouter();
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Set<PkgKey>>(new Set(["snomed", "dmd"]));
  const [syncing, setSyncing] = useState(false);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [syncDone, setSyncDone] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const fetchStatus = useCallback(async () => {
    setLoadingStatus(true);
    setStatusError(null);
    try {
      const resp = await fetch("/api/admin/terminology/status", {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!resp.ok) throw new Error(`Server returned ${resp.status}`);
      setStatus(await resp.json());
    } catch (e: unknown) {
      setStatusError(e instanceof Error ? e.message : "Could not load status.");
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const togglePackage = (key: PkgKey) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const startSync = useCallback(() => {
    if (syncing || selected.size === 0) return;
    setSyncing(true);
    setSyncDone(false);
    setSyncError(null);
    setLogLines([]);

    const pkgs = [...selected].join(",");
    const url = `/api/admin/terminology/sync/stream?packages=${pkgs}&phases=auto`;
    const es = new EventSource(url, { withCredentials: true });
    esRef.current = es;

    const appendLog = (msg: string, level?: string, pct?: number) =>
      setLogLines((prev) => [...prev, { msg, level, pct }]);

    es.addEventListener("log", (e) => {
      const d = JSON.parse(e.data);
      appendLog(d.msg, d.level);
    });
    es.addEventListener("download_start", (e) => {
      const d = JSON.parse(e.data);
      appendLog(`Downloading ${d.label} (${d.size_mb} MB)...`);
    });
    es.addEventListener("download_progress", (e) => {
      const d = JSON.parse(e.data);
      setLogLines((prev) => {
        const filtered = prev.filter((l) => l.pct == null);
        return [...filtered, { msg: "", pct: d.pct }];
      });
    });
    es.addEventListener("download_done", (e) => {
      const d = JSON.parse(e.data);
      appendLog(`Download complete for ${d.package}.`);
    });
    es.addEventListener("phase_start", (e) => {
      const d = JSON.parse(e.data);
      appendLog(`Running loader phases: ${d.phases.join(", ")}`);
    });
    es.addEventListener("sync_done", (e) => {
      const d = JSON.parse(e.data);
      appendLog(`Sync complete in ${d.duration_s}s.`);
      setSyncDone(true);
      setSyncing(false);
      es.close();
      fetchStatus();
    });
    es.addEventListener("sync_error", (e) => {
      const d = JSON.parse(e.data);
      setSyncError(d.msg);
      setSyncing(false);
      es.close();
    });
    es.onerror = () => {
      setSyncError("Connection lost. Check the server logs.");
      setSyncing(false);
      es.close();
    };
  }, [syncing, selected, fetchStatus]);

  const cancelSync = () => {
    esRef.current?.close();
    setSyncing(false);
    setLogLines((prev) => [...prev, { msg: "Sync cancelled by user.", level: "warning" }]);
  };

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      {/* Breadcrumb */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link
          underline="hover"
          color="inherit"
          sx={{ cursor: "pointer" }}
          onClick={() => router.push("/settings")}
        >
          Settings
        </Link>
        <Typography color="text.primary">Terminology data</Typography>
      </Breadcrumbs>

      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Terminology data
        </Typography>
        <Button
          variant="outlined"
          size="small"
          onClick={fetchStatus}
          disabled={loadingStatus}
        >
          Refresh
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Check for new SNOMED CT and dm+d releases from NHS TRUD. Download and load them into the
        knowledge graph without leaving this page.
      </Typography>

      {/* Status section */}
      {loadingStatus ? (
        <Stack spacing={1.5} mb={3}>
          <Skeleton variant="rounded" height={100} />
          <Skeleton variant="rounded" height={100} />
          <Skeleton variant="rounded" height={80} />
        </Stack>
      ) : statusError ? (
        <Alert severity="error" sx={{ mb: 3 }}>
          {statusError}
        </Alert>
      ) : status ? (
        <Stack spacing={2} mb={3}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            {PACKAGE_KEYS.map((key) =>
              status.packages[key] ? (
                <PackageCard key={key} pkg={status.packages[key]} />
              ) : null
            )}
          </Stack>
          <Neo4jCounts counts={status.neo4j} />
        </Stack>
      ) : null}

      <Divider sx={{ mb: 3 }} />

      {/* Sync controls */}
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
        Sync from TRUD
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Choose which packages to download. The knowledge graph will update automatically after
        download.
      </Typography>

      <FormGroup row sx={{ mb: 2 }}>
        {PACKAGE_KEYS.map((key) => (
          <FormControlLabel
            key={key}
            control={
              <Checkbox
                checked={selected.has(key)}
                onChange={() => togglePackage(key)}
                disabled={syncing}
              />
            }
            label={status?.packages[key]?.label ?? key}
          />
        ))}
      </FormGroup>

      <Stack direction="row" spacing={1.5} mb={3}>
        <Button
          variant="contained"
          startIcon={syncing ? <CircularProgress size={16} color="inherit" /> : <DownloadingIcon />}
          onClick={startSync}
          disabled={syncing || selected.size === 0}
        >
          {syncing ? "Syncing..." : "Start sync"}
        </Button>
        {syncing && (
          <Button variant="outlined" color="error" onClick={cancelSync}>
            Cancel
          </Button>
        )}
      </Stack>

      {syncDone && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Sync finished. The knowledge graph is now up to date.
        </Alert>
      )}
      {syncError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {syncError}
        </Alert>
      )}

      <LogPanel lines={logLines} />
    </Box>
  );
}
