/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   Also implements: DO-DA9FD5E8
 *   DI: DI-340279C1, DI-6424B6FC
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CFA1ED55")
 */
"use client";

/**
 * Terminology -- Wave E Phase 3d redesign
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: active concepts / terms / IS_A relationships /
 *     ICD-10 codes + maps / OPCS-4 codes + maps / Read code maps
 *     (driven from Neo4j counts).
 *   - ToolbarActions: Refresh status.
 *   - Package status cards: tone-accented (success / warning / muted)
 *     with version + size + a single primary "Sync" action when
 *     updates are available. Cards render in a 2x2 grid for the
 *     four supported packages (SNOMED, dm+d, NHS ICD-10, OPCS-4).
 *   - Streaming sync log panel (preserved, restyled).
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145
 *                  + DI-LEO-AI-228 / DO-LEO-AI-301 / VT-LEO-AI-301 (ICD-10)
 *                  + DI-LEO-AI-226 / DO-LEO-AI-223 / VT-LEO-AI-302 (OPCS-4).
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DownloadingIcon from "@mui/icons-material/Downloading";
import RefreshIcon from "@mui/icons-material/Refresh";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import {
  StatHero,
  ToolbarActions,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

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
  icd10_codes?: number;
  opcs4_codes?: number;
  opcs4_maps?: number;
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

function packageTone(pkg: PackageStatus): "positive" | "warning" | "neutral" {
  if (pkg.up_to_date) return "positive";
  if (!pkg.local_version) return "neutral";
  return "warning";
}

function packageStatusLabel(pkg: PackageStatus): string {
  if (pkg.up_to_date) return "Up to date";
  if (!pkg.local_version) return "Not on disk";
  return "Update available";
}

// ---------------------------------------------------------------------------
// PackageCard -- one tone-accented status card per package
// ---------------------------------------------------------------------------

function PackageCard({ pkg }: { pkg: PackageStatus }) {
  const tone = packageTone(pkg);
  const accent =
    tone === "positive" ? "#16A34A" : tone === "warning" ? "#D97706" : "#94A3B8";
  const Icon =
    tone === "positive"
      ? CheckCircleOutlineIcon
      : tone === "warning"
        ? WarningAmberIcon
        : DownloadingIcon;
  return (
    <Box
      data-testid={`terminology-package-${pkg.label.toLowerCase().replace(/\s+/g, "-")}`}
      sx={{
        position: "relative",
        background: "#FFFFFF",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "12px",
        p: "18px",
        flex: 1,
        minWidth: 0,
        minHeight: 168,
        display: "flex",
        flexDirection: "column",
        gap: 1.25,
      }}
    >
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 1,
          bgcolor: accent,
        }}
      />
      <Stack
        direction="row"
        alignItems="flex-start"
        justifyContent="space-between"
        spacing={1}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          <Icon sx={{ color: accent, fontSize: 22 }} />
          <Typography
            sx={{
              fontWeight: 600,
              fontSize: "1rem",
              lineHeight: 1.25,
            }}
          >
            {pkg.label}
          </Typography>
        </Stack>
        <Chip
          label={packageStatusLabel(pkg)}
          size="small"
          sx={{
            height: 22,
            fontSize: "0.7rem",
            bgcolor:
              tone === "positive"
                ? "#ECFDF5"
                : tone === "warning"
                  ? "#FEF3C7"
                  : "#F1F5F9",
            color:
              tone === "positive"
                ? "#047857"
                : tone === "warning"
                  ? "#92400E"
                  : "#475569",
            border: "1px solid",
            borderColor:
              tone === "positive"
                ? "#A7F3D0"
                : tone === "warning"
                  ? "#FDE68A"
                  : "#E2E8F0",
            flexShrink: 0,
          }}
        />
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: "auto 1fr", rowGap: 0.5, columnGap: 1 }}>
        <Typography variant="caption" color="text.secondary">
          On disk
        </Typography>
        <Typography variant="caption" sx={{ fontWeight: 500 }}>
          {pkg.local_version ?? (
            <em style={{ opacity: 0.5 }}>not downloaded</em>
          )}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          TRUD latest
        </Typography>
        <Typography variant="caption" sx={{ fontWeight: 500 }}>
          {pkg.trud_version
            ? `${pkg.trud_version}${pkg.trud_date ? ` - ${pkg.trud_date}` : ""}`
            : "--"}
        </Typography>
        {pkg.trud_size_mb != null ? (
          <>
            <Typography variant="caption" color="text.secondary">
              Download
            </Typography>
            <Typography variant="caption" sx={{ fontWeight: 500 }}>
              {pkg.trud_size_mb} MB
            </Typography>
          </>
        ) : null}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// LogPanel -- streaming sync output
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
        bgcolor: "#0F172A",
        fontFamily: "JetBrains Mono, monospace",
        fontSize: "0.72rem",
        borderRadius: 2,
      }}
      data-testid="terminology-log-panel"
    >
      {lines.map((line, i) => (
        <Box
          key={i}
          sx={{
            color:
              line.level === "error" || line.level === "critical"
                ? "#FCA5A5"
                : line.level === "warning"
                  ? "#FDE68A"
                  : "#CBD5E1",
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          {line.pct != null ? (
            <Stack direction="row" alignItems="center" spacing={1}>
              <Box sx={{ flex: 1 }}>
                <LinearProgress
                  variant="determinate"
                  value={line.pct}
                  sx={{ height: 6, borderRadius: 1 }}
                />
              </Box>
              <Typography variant="caption" sx={{ color: "#94A3B8", minWidth: 36 }}>
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

const PACKAGE_KEYS = ["snomed", "dmd", "icd10", "opcs4"] as const;
type PkgKey = (typeof PACKAGE_KEYS)[number];

function buildStatTiles(neo4j: Neo4jCounts): StatTile[] {
  return [
    {
      id: "active-concepts",
      label: "Active concepts",
      value: fmt(neo4j.active_concepts),
      hint: "SNOMED concepts in the graph",
    },
    {
      id: "terms",
      label: "Terms",
      value: fmt(neo4j.terms),
      hint: "Synonyms and descriptions",
    },
    {
      id: "is-a-rels",
      label: "IS_A links",
      value: fmt(neo4j.is_a_rels),
      hint: "Hierarchy edges",
    },
    {
      id: "icd10-codes",
      label: "ICD-10 codes",
      value: fmt(neo4j.icd10_codes),
      hint: "Titled ICD-10 nodes",
    },
    {
      id: "icd10-maps",
      label: "ICD-10 maps",
      value: fmt(neo4j.icd10_maps),
      hint: "SNOMED -> ICD-10 cross-maps",
    },
    {
      id: "opcs4-codes",
      label: "OPCS-4 codes",
      value: fmt(neo4j.opcs4_codes),
      hint: "Titled OPCS-4 nodes",
    },
    {
      id: "opcs4-maps",
      label: "OPCS-4 maps",
      value: fmt(neo4j.opcs4_maps),
      hint: "SNOMED -> OPCS-4 cross-maps",
    },
    {
      id: "read-maps",
      label: "Read maps",
      value: fmt(neo4j.read_maps),
      hint: "Read code mappings",
    },
  ];
}

export default function TerminologyPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Set<PkgKey>>(
    new Set(["snomed", "dmd", "icd10", "opcs4"]),
  );
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
    setLogLines((prev) => [
      ...prev,
      { msg: "Sync cancelled by user.", level: "warning" },
    ]);
  };

  const stats = useMemo(
    () => (status ? buildStatTiles(status.neo4j) : []),
    [status],
  );

  const toolbarActions: ToolbarAction[] = [
    {
      id: "refresh-status",
      label: loadingStatus ? "Refreshing" : "Refresh",
      icon: <RefreshIcon fontSize="small" />,
      variant: "secondary",
      onClick: fetchStatus,
      disabled: loadingStatus || syncing,
      loading: loadingStatus,
    },
  ];

  return (
    <Box>
      {stats.length > 0 ? <StatHero stats={stats} /> : null}

      {statusError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {statusError}
        </Alert>
      ) : null}

      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 1.5, flexWrap: "wrap", gap: 1 }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Package status
        </Typography>
        <ToolbarActions actions={toolbarActions} />
      </Stack>

      {loadingStatus ? (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
            gap: 2,
            mb: 3,
          }}
        >
          <Skeleton variant="rounded" height={168} />
          <Skeleton variant="rounded" height={168} />
          <Skeleton variant="rounded" height={168} />
          <Skeleton variant="rounded" height={168} />
        </Box>
      ) : status ? (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
            gap: 2,
            mb: 3,
          }}
        >
          {PACKAGE_KEYS.map((key) =>
            status.packages[key] ? (
              <PackageCard key={key} pkg={status.packages[key]} />
            ) : null,
          )}
        </Box>
      ) : null}

      <Box
        sx={{
          mt: 1,
          mb: 3,
          p: 2.25,
          borderRadius: 2,
          border: "1px solid",
          borderColor: "divider",
          bgcolor: "#F8FAFC",
        }}
        data-testid="terminology-sync-controls"
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.5 }}>
          Sync from TRUD
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 1.5, fontSize: "0.85rem" }}
        >
          Choose which packages to download. The knowledge graph will update
          automatically after download.
        </Typography>
        <FormGroup row sx={{ mb: 1.5 }}>
          {PACKAGE_KEYS.map((key) => (
            <FormControlLabel
              key={key}
              control={
                <Checkbox
                  checked={selected.has(key)}
                  onChange={() => togglePackage(key)}
                  disabled={syncing}
                  size="small"
                />
              }
              label={
                <Typography variant="body2">
                  {status?.packages[key]?.label ?? key}
                </Typography>
              }
            />
          ))}
        </FormGroup>
        <Stack direction="row" spacing={1.5}>
          <Button
            variant="contained"
            startIcon={
              syncing ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <DownloadingIcon />
              )
            }
            onClick={startSync}
            disabled={syncing || selected.size === 0}
            sx={{ textTransform: "none" }}
          >
            {syncing ? "Syncing..." : "Start sync"}
          </Button>
          {syncing ? (
            <Button
              variant="outlined"
              color="error"
              onClick={cancelSync}
              sx={{ textTransform: "none" }}
            >
              Cancel
            </Button>
          ) : null}
        </Stack>
      </Box>

      {syncDone ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          Sync finished. The knowledge graph is now up to date.
        </Alert>
      ) : null}
      {syncError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {syncError}
        </Alert>
      ) : null}

      <LogPanel lines={logLines} />
    </Box>
  );
}
