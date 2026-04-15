"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  DetailLevel,
  MissionCatalogueResponse,
  MissionDescription,
  MissionRun,
  PersonaLens,
  RunResult,
  fetchMissions,
  pollMissionRun,
  startMissionRun,
} from "@/lib/researchApi";

export interface ScopingParams {
  area: string;
  period: string;
  detail: DetailLevel;
  patient_id?: string;
  context_filter: "current" | "all";
  confidence_min: number;
}

export interface ResearchState {
  // Catalogue
  catalogue: MissionCatalogueResponse | null;
  catalogueLoading: boolean;
  catalogueError: string | null;

  // Active mission selection
  activeMission: MissionDescription | null;
  lens: PersonaLens;

  // Scoping
  scopingOpen: boolean;
  scoping: ScopingParams;

  // Run lifecycle
  activeRun: MissionRun | null;
  runLoading: boolean;
  result: RunResult | null;

  // Actions
  selectMission: (mission: MissionDescription) => void;
  closeMission: () => void;
  setLens: (lens: PersonaLens) => void;
  openScoping: () => void;
  closeScoping: () => void;
  updateScoping: (params: Partial<ScopingParams>) => void;
  submitRun: (overrides?: Partial<ScopingParams>) => Promise<void>;
  refreshCatalogue: () => void;
  navigateToMission: (missionId: string) => void;
}

const DEFAULT_SCOPING: ScopingParams = {
  area: "all",
  period: "6m",
  detail: "summary",
  context_filter: "current",
  confidence_min: 0.5,
};

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 60; // 2 mins

export function useResearchState(): ResearchState {
  const [catalogue, setCatalogue] =
    useState<MissionCatalogueResponse | null>(null);
  const [catalogueLoading, setCatalogueLoading] = useState(true);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);

  const [activeMission, setActiveMission] =
    useState<MissionDescription | null>(null);
  const [lens, setLens] = useState<PersonaLens>("patients");

  const [scopingOpen, setScopingOpen] = useState(false);
  const [scoping, setScoping] = useState<ScopingParams>(DEFAULT_SCOPING);

  const [activeRun, setActiveRun] = useState<MissionRun | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollCountRef.current = 0;
  }, []);

  const loadCatalogue = useCallback(async () => {
    setCatalogueLoading(true);
    setCatalogueError(null);
    try {
      const data = await fetchMissions();
      setCatalogue(data);
    } catch (err) {
      setCatalogueError(
        err instanceof Error ? err.message : "Failed to load missions"
      );
    } finally {
      setCatalogueLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCatalogue();
    return () => stopPolling();
  }, [loadCatalogue, stopPolling]);

  const startPolling = useCallback(
    (run: MissionRun) => {
      stopPolling();
      pollCountRef.current = 0;
      pollRef.current = setInterval(async () => {
        pollCountRef.current += 1;
        if (pollCountRef.current > MAX_POLL_ATTEMPTS) {
          stopPolling();
          setRunLoading(false);
          return;
        }
        try {
          const updated = await pollMissionRun(run.mission_id, run.run_id);
          setActiveRun(updated);
          if (updated.status === "done" || updated.status === "failed") {
            stopPolling();
            setRunLoading(false);
            if (updated.result) setResult(updated.result);
          }
        } catch {
          stopPolling();
          setRunLoading(false);
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling]
  );

  const submitRun = useCallback(
    async (overrides?: Partial<ScopingParams>) => {
      if (!activeMission) return;
      const params = { ...scoping, ...overrides };
      setRunLoading(true);
      setResult(null);
      setActiveRun(null);
      stopPolling();

      try {
        const run = await startMissionRun(activeMission.id, {
          area: params.area,
          period: params.period,
          detail: params.detail,
          patient_id: params.patient_id,
          confidence_min: params.confidence_min,
          context_filter: params.context_filter,
        });
        setActiveRun(run);
        setScopingOpen(false);

        if (run.status === "done") {
          setRunLoading(false);
          if (run.result) setResult(run.result);
        } else {
          startPolling(run);
        }
      } catch (err) {
        setRunLoading(false);
        const msg = err instanceof Error ? err.message : "Run failed";
        setActiveRun({
          run_id: "",
          mission_id: activeMission.id,
          status: "failed",
          created_at: new Date().toISOString(),
          result: {
            mission_id: activeMission.id,
            headline: msg,
            items: [],
            total_count: 0,
            coverage: {
              patient_count: 0,
              practice_count: 0,
              confidence: "low",
              confidence_note: "",
            },
            method_plain: "",
            method_technical: "",
            next_steps: [],
            detail_level: params.detail,
            data_available: false,
            error: msg,
          },
        });
      }
    },
    [activeMission, scoping, startPolling, stopPolling]
  );

  const selectMission = useCallback(
    (mission: MissionDescription) => {
      if (!mission.data_available) return;
      setActiveMission(mission);
      setResult(null);
      setActiveRun(null);
      stopPolling();
      setScopingOpen(true);
    },
    [stopPolling]
  );

  const closeMission = useCallback(() => {
    setActiveMission(null);
    setResult(null);
    setActiveRun(null);
    setScopingOpen(false);
    stopPolling();
  }, [stopPolling]);

  const navigateToMission = useCallback(
    (missionId: string) => {
      const mission = catalogue?.missions.find((m) => m.id === missionId);
      if (mission) selectMission(mission);
    },
    [catalogue, selectMission]
  );

  return {
    catalogue,
    catalogueLoading,
    catalogueError,
    activeMission,
    lens,
    scopingOpen,
    scoping,
    activeRun,
    runLoading,
    result,
    selectMission,
    closeMission,
    setLens,
    openScoping: () => setScopingOpen(true),
    closeScoping: () => setScopingOpen(false),
    updateScoping: (p) => setScoping((prev) => ({ ...prev, ...p })),
    submitRun,
    refreshCatalogue: loadCatalogue,
    navigateToMission,
  };
}
