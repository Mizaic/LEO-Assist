/**
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1
 */
"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import type { StatTile } from "@leo/design-system";

import type { LogLine } from "./LogPanel";
import type { PackageStatus } from "./PackageCard";

export interface Neo4jCounts {
  active_concepts?: number;
  terms?: number;
  is_a_rels?: number;
  icd10_maps?: number;
  read_maps?: number;
  icd10_codes?: number;
  opcs4_codes?: number;
  opcs4_maps?: number;
}

export interface StatusResponse {
  packages: Record<string, PackageStatus>;
  neo4j: Neo4jCounts;
}

export const PACKAGE_KEYS = ["snomed", "dmd", "icd10", "opcs4"] as const;
export type PkgKey = (typeof PACKAGE_KEYS)[number];

export function fmt(n: number | undefined): string {
  if (n == null) return "--";
  return n.toLocaleString("en-GB");
}

export function buildStatTiles(neo4j: Neo4jCounts): StatTile[] {
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

export function useTerminologyPage() {
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

  const fetchStatus = useLoadStatus(setStatus, setLoadingStatus, setStatusError);
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
    const es = new EventSource(
      `/api/admin/terminology/sync/stream?packages=${pkgs}&phases=auto`,
      { withCredentials: true },
    );
    esRef.current = es;
    bindSyncEvents(es, { appendLog, fetchStatus, setSyncing, setSyncDone, setSyncError, setLogLines });
  }, [syncing, selected, fetchStatus, appendLog]);

  const cancelSync = () => {
    esRef.current?.close();
    setSyncing(false);
    appendLog("Sync cancelled by user.", "warning");
  };

  const togglePackage = (key: PkgKey) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const stats = useMemo(
    () => (status ? buildStatTiles(status.neo4j) : []),
    [status],
  );

  return {
    status,
    loadingStatus,
    statusError,
    selected,
    syncing,
    logLines,
    syncDone,
    syncError,
    stats,
    fetchStatus,
    startSync,
    cancelSync,
    togglePackage,
    setLogLines,
  };
}

export type TerminologyPageState = ReturnType<typeof useTerminologyPage>;

function useLoadStatus(
  setStatus: (next: StatusResponse) => void,
  setLoadingStatus: (next: boolean) => void,
  setStatusError: (next: string | null) => void,
) {
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
  }, [setLoadingStatus, setStatus, setStatusError]);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  return fetchStatus;
}

type SyncBinders = {
  appendLog: (msg: string, level?: string) => void;
  fetchStatus: () => Promise<void>;
  setSyncing: (next: boolean) => void;
  setSyncDone: (next: boolean) => void;
  setSyncError: (next: string | null) => void;
  setLogLines: Dispatch<SetStateAction<LogLine[]>>;
};

function bindSyncEvents(es: EventSource, args: SyncBinders) {
  es.addEventListener("log", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    args.appendLog(d.msg, d.level);
  });
  es.addEventListener("download_start", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    args.appendLog(`Downloading ${d.label} (${d.size_mb} MB)...`);
  });
  es.addEventListener("download_progress", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    args.setLogLines((prev) => {
      const filtered = prev.filter((l) => l.pct == null);
      return [...filtered, { msg: "", pct: d.pct }];
    });
  });
  es.addEventListener("download_done", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    args.appendLog(`Download complete for ${d.package}.`);
  });
  es.addEventListener("phase_start", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    args.appendLog(`Running loader phases: ${d.phases.join(", ")}`);
  });
  bindSyncTerminalEvents(es, args);
}

function bindSyncTerminalEvents(es: EventSource, args: SyncBinders) {
  es.addEventListener("sync_done", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    args.appendLog(`Sync complete in ${d.duration_s}s.`);
    args.setSyncDone(true);
    args.setSyncing(false);
    es.close();
    void args.fetchStatus();
  });
  es.addEventListener("sync_error", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    args.setSyncError(d.msg);
    args.setSyncing(false);
    es.close();
  });
  es.onerror = () => {
    args.setSyncError("Connection lost. Check the server logs.");
    args.setSyncing(false);
    es.close();
  };
}
