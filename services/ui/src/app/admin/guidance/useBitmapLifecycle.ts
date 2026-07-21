/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listCases, pollRunUntilTerminal, scoreRun, startRun } from "../validation-lab/labApi";
import type {
  BitmapStatus,
  CandidateTestSummary,
  PolicyMode,
  ScopeType,
  VersionEntry,
} from "./bitmapLifecycleHelpers";

const DEFAULT_PLAN_ID = "pd-referral-assessment";
const MAX_LAB_PATIENTS_TESTED = 5;

interface UseBitmapLifecycleArgs {
  onVersionActivated?: () => void;
}

export function useBitmapLifecycle({ onVersionActivated }: UseBitmapLifecycleArgs) {
  const [scopeType, setScopeType] = useState<ScopeType>("global");
  const [scopeId, setScopeId] = useState("default");
  const [policyMode, setPolicyMode] = useState<PolicyMode>("advisory");
  const [distanceChild, setDistanceChild] = useState("");
  const [distanceParent, setDistanceParent] = useState("");
  const [status, setStatus] = useState<BitmapStatus | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [activatingVersion, setActivatingVersion] = useState<string | null>(null);
  const [confirmVersion, setConfirmVersion] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [justActivatedVersion, setJustActivatedVersion] = useState<string | null>(null);
  const [justCompiled, setJustCompiled] = useState(false);
  const [candidateVersion, setCandidateVersion] = useState<string | null>(null);
  const [testingLabPatients, setTestingLabPatients] = useState(false);
  const [candidateTestSummary, setCandidateTestSummary] =
    useState<CandidateTestSummary | null>(null);
  const [shadowing, setShadowing] = useState(false);
  const [shadowSummary, setShadowSummary] = useState<string | null>(null);

  useEffect(() => {
    if (scopeType === "global" && scopeId !== "default") setScopeId("default");
  }, [scopeId, scopeType]);

  const fetchStatus = useCallback(async (): Promise<BitmapStatus | null> => {
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
      const statusData: BitmapStatus = await statusResp.json();
      setStatus(statusData);
      setVersions(await versionsResp.json());
      setError(null);
      return statusData;
    } catch {
      setError("Could not load the current status. Please refresh the page.");
      return null;
    }
  }, [scopeId, scopeType]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus, refreshKey]);
  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const handleCompile = useCallback(async () => {
    setCompiling(true);
    setError(null);
    setShadowSummary(null);
    try {
      const resp = await fetch("/api/terminology/guidelines/bitmap/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope_type: scopeType,
          scope_id: scopeId || "default",
          policy_mode: policyMode,
          activate: false,
          distance_child_override: distanceChild === "" ? null : Number(distanceChild),
          distance_parent_override: distanceParent === "" ? null : Number(distanceParent),
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const started = (await resp.json()) as { job_id: string; version: string };
      setCandidateVersion(started.version);
      const pollStart = Date.now();
      pollRef.current = setInterval(async () => {
        const jobResp = await fetch(
          `/api/terminology/guidelines/bitmap/jobs/${started.job_id}`,
        );
        const elapsed = Date.now() - pollStart;
        let jobDone = false;
        if (jobResp.ok) {
          const job = (await jobResp.json()) as { status?: string };
          jobDone = job.status === "done" || job.status === "error";
          if (job.status === "error") {
            setError("Compile failed. Check the API logs and try again.");
          }
        }
        if (jobDone || elapsed > 300_000) {
          clearInterval(pollRef.current!);
          setCompiling(false);
          setRefreshKey((n) => n + 1);
          if (jobDone) {
            setJustCompiled(true);
            setTimeout(() => setJustCompiled(false), 2200);
          }
        }
      }, 3000);
    } catch {
      setError("Could not start the compile. Please try again.");
      setCompiling(false);
    }
  }, [distanceChild, distanceParent, policyMode, scopeId, scopeType]);

  const handleTestOnLabPatients = useCallback(async () => {
    if (!candidateVersion) return;
    setTestingLabPatients(true);
    setError(null);
    setCandidateTestSummary(null);
    try {
      const cases = await listCases();
      const sample = cases.slice(0, MAX_LAB_PATIENTS_TESTED);
      let passed = 0;
      let failed = 0;
      let errored = 0;
      for (const labCase of sample) {
        try {
          const started = await startRun(labCase.id, {
            plan_id: labCase.plan_id || DEFAULT_PLAN_ID,
            phase_ids: [],
            persist_mode: "production",
            ruleset_version: candidateVersion,
          });
          const finalRun = await pollRunUntilTerminal(labCase.id, started.run.id);
          if (finalRun.status !== "completed") {
            errored += 1;
            continue;
          }
          const score = (await scoreRun(labCase.id, finalRun.id)) as { pass?: boolean };
          if (score.pass) passed += 1;
          else failed += 1;
        } catch {
          errored += 1;
        }
      }
      setCandidateTestSummary({ tested: sample.length, passed, failed, errored });
    } catch {
      setError("Could not test the candidate against Validation Lab patients.");
    } finally {
      setTestingLabPatients(false);
    }
  }, [candidateVersion]);

  const handleHistoricShadow = useCallback(async () => {
    if (!candidateVersion) return;
    setShadowing(true);
    setError(null);
    setShadowSummary(null);
    try {
      const srcResp = await fetch("/api/guidance/shadow/source-patients?limit=10");
      const sources = srcResp.ok ? ((await srcResp.json()) as Array<{ id?: string }>) : [];
      const sourceIds = sources.map((s) => s.id).filter((id): id is string => Boolean(id));
      if (!sourceIds.length) {
        setShadowSummary("No real patients available yet for a historic comparison.");
        return;
      }
      const resp = await fetch("/api/guidance/shadow/diff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_version: candidateVersion,
          scope_type: scopeType,
          scope_id: scopeId || "default",
          guideline_id: scopeType === "guideline" ? scopeId : null,
          source_patient_ids: sourceIds,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const report = (await resp.json()) as {
        changed_count: number;
        patient_count: number;
        live_pointer_unchanged: boolean;
      };
      setShadowSummary(
        `Shadow: ${report.changed_count} of ${report.patient_count} patients differ` +
          (report.live_pointer_unchanged ? " (live unchanged)." : "."),
      );
    } catch {
      setError("Could not run the historic shadow comparison.");
    } finally {
      setShadowing(false);
    }
  }, [candidateVersion, scopeId, scopeType]);

  const handleActivate = useCallback(
    async (version: string) => {
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
          },
        );
        if (!resp.ok) throw new Error(await resp.text());
        setConfirmVersion(null);
        setRefreshKey((n) => n + 1);
        setJustActivatedVersion(version);
        setTimeout(() => setJustActivatedVersion(null), 2200);
        onVersionActivated?.();
      } catch {
        setError("Could not activate this version. Please try again.");
      } finally {
        setActivatingVersion(null);
      }
    },
    [onVersionActivated, scopeId, scopeType],
  );

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

  return {
    scopeType,
    setScopeType,
    scopeId,
    setScopeId,
    policyMode,
    setPolicyMode,
    distanceChild,
    setDistanceChild,
    distanceParent,
    setDistanceParent,
    status,
    versions,
    error,
    compiling,
    rollingBack,
    activatingVersion,
    confirmVersion,
    setConfirmVersion,
    justActivatedVersion,
    justCompiled,
    candidateVersion,
    testingLabPatients,
    candidateTestSummary,
    shadowing,
    shadowSummary,
    handleCompile,
    handleTestOnLabPatients,
    handleHistoricShadow,
    handleActivate,
    handleRollback,
  };
}
