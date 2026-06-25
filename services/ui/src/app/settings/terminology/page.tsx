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
 *   - SkeletonGrid: shown while stats are loading (8 columns x 1 row).
 *   - StatHero: active concepts / terms / IS_A relationships /
 *     ICD-10 codes + maps / OPCS-4 codes + maps / Read code maps.
 *   - ToolbarActions: Refresh status.
 *   - PackageCards: click-to-select for sync, framer-motion hover lift,
 *     hover-reveal "Sync this package" ghost action.
 *   - LogPanel: streaming sync output with copy + clear.
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145
 *                  + DI-LEO-AI-228 / DO-LEO-AI-301 / VT-LEO-AI-301 (ICD-10)
 *                  + DI-LEO-AI-226 / DO-LEO-AI-223 / VT-LEO-AI-302 (OPCS-4).
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DownloadingIcon from "@mui/icons-material/Downloading";
import RefreshIcon from "@mui/icons-material/Refresh";

import {
  SkeletonGrid,
  StatHero,
  ToolbarActions,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import { PackageCard, type PackageStatus } from "./PackageCard";
import { LogPanel, type LogLine } from "./LogPanel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n: number | undefined): string {
  if (n == null) return "--";
  return n.toLocaleString("en-GB");
}

const PACKAGE_KEYS = ["snomed", "dmd", "icd10", "opcs4"] as const;
type PkgKey = (typeof PACKAGE_KEYS)[number];

function buildStatTiles(neo4j: Neo4jCounts): StatTile[] {
  return [
    { id: "active-concepts", label: "Active concepts", value: fmt(neo4j.active_concepts), hint: "SNOMED concepts in the graph" },
    { id: "terms", label: "Terms", value: fmt(neo4j.terms), hint: "Synonyms and descriptions" },
    { id: "is-a-rels", label: "IS_A links", value: fmt(neo4j.is_a_rels), hint: "Hierarchy edges" },
    { id: "icd10-codes", label: "ICD-10 codes", value: fmt(neo4j.icd10_codes), hint: "Titled ICD-10 nodes" },
    { id: "icd10-maps", label: "ICD-10 maps", value: fmt(neo4j.icd10_maps), hint: "SNOMED -> ICD-10 cross-maps" },
    { id: "opcs4-codes", label: "OPCS-4 codes", value: fmt(neo4j.opcs4_codes), hint: "Titled OPCS-4 nodes" },
    { id: "opcs4-maps", label: "OPCS-4 maps", value: fmt(neo4j.opcs4_maps), hint: "SNOMED -> OPCS-4 cross-maps" },
    { id: "read-maps", label: "Read maps", value: fmt(neo4j.read_maps), hint: "Read code mappings" },
  ];
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

// LONG FUNCTION: page orchestrates status fetch, package selection,
// SSE sync streaming, and log management.
export default function TerminologyPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Wave E: PackageCards are click-to-select; no separate checkboxes.
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

  const appendLog = useCallback((msg: string, level?: string, pct?: number) => {
    setLogLines((prev) => [...prev, { msg, level, pct }]);
  }, []);

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
      void fetchStatus();
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
  }, [syncing, selected, fetchStatus, appendLog]);

  const cancelSync = () => {
    esRef.current?.close();
    setSyncing(false);
    appendLog("Sync cancelled by user.", "warning");
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
      {/* Stats loading: SkeletonGrid while counts are fetched */}
      {loadingStatus ? (
        <SkeletonGrid columns={8} rows={1} itemHeight={88} />
      ) : stats.length > 0 ? (
        <StatHero stats={stats} />
      ) : null}

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
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Package status
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Click a card to select or deselect it for sync.
          </Typography>
        </Box>
        <ToolbarActions actions={toolbarActions} />
      </Stack>

      {/* Package cards -- 2x2 grid; click to toggle selection */}
      {loadingStatus ? null : status ? (
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
              <PackageCard
                key={key}
                pkg={status.packages[key]}
                selected={selected.has(key)}
                onToggle={() => togglePackage(key)}
                disabled={syncing}
              />
            ) : null,
          )}
        </Box>
      ) : null}

      {/* Sync controls -- start / cancel buttons only (selection via cards above) */}
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
          {selected.size === 0
            ? "Select at least one package above to enable sync."
            : `${selected.size} package${selected.size === 1 ? "" : "s"} selected. The knowledge graph will update automatically after download.`}
        </Typography>
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

      <LogPanel
        lines={logLines}
        onClear={() => setLogLines([])}
      />
    </Box>
  );
}
