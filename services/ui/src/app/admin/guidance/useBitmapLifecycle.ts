/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-15565AF5, DO-599B9828
 *   DI: DI-3DDA3519, DI-8DD23CE2
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-15565AF5")
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  BitmapStatus,
  CandidateTestSummary,
  CompileMode,
  PolicyMode,
  VersionEntry,
} from "./bitmapLifecycleHelpers";

export interface ActiveRule {
  rule_id: string;
  name: string;
  guideline_id: string;
  guideline_title: string;
  strength: string;
}

interface UseBitmapLifecycleArgs {
  onVersionActivated?: () => void;
}

export function useBitmapLifecycle({ onVersionActivated }: UseBitmapLifecycleArgs) {
  const [compileMode, setCompileMode] = useState<CompileMode>("global");
  const [scopeId, setScopeId] = useState("default");
  const [pickScopeId, setPickScopeId] = useState("");
  const [pickGuidelineId, setPickGuidelineId] = useState("");
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set());
  const [activeRules, setActiveRules] = useState<ActiveRule[]>([]);
  const [rulesLoadError, setRulesLoadError] = useState<string | null>(null);
  const [policyMode, setPolicyMode] = useState<PolicyMode>("advisory");
  const [distanceChild, setDistanceChild] = useState("");
  const [distanceParent, setDistanceParent] = useState("");
  const [status, setStatus] = useState<BitmapStatus | null>(null);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [compileElapsedSec, setCompileElapsedSec] = useState(0);
  const [rollingBack, setRollingBack] = useState(false);
  const [activatingVersion, setActivatingVersion] = useState<string | null>(null);
  const [confirmVersion, setConfirmVersion] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [justActivatedVersion, setJustActivatedVersion] = useState<string | null>(null);
  const [justCompiled, setJustCompiled] = useState(false);
  const [candidateVersion, setCandidateVersion] = useState<string | null>(null);
  const [labTestOpen, setLabTestOpen] = useState(false);
  const [candidateTestSummary, setCandidateTestSummary] =
    useState<CandidateTestSummary | null>(null);
  const [shadowing, setShadowing] = useState(false);
  const [shadowSummary, setShadowSummary] = useState<string | null>(null);

  // Reset scopeId when switching away from guideline mode.
  useEffect(() => {
    if (compileMode !== "guideline" && scopeId !== "default") setScopeId("default");
  }, [compileMode, scopeId]);

  // Load active rules when entering pick mode.
  useEffect(() => {
    if (compileMode !== "pick") return;
    let cancelled = false;
    setRulesLoadError(null);
    fetch("/api/terminology/guidelines/rules/active")
      .then(async (r) => {
        if (!r.ok) throw new Error("Could not load approved rules.");
        return r.json();
      })
      .then((rows: ActiveRule[]) => {
        if (!cancelled) setActiveRules(Array.isArray(rows) ? rows : []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setActiveRules([]);
        setRulesLoadError(
          err instanceof Error ? err.message : "Could not load approved rules.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [compileMode]);

  const visibleRules = activeRules.filter((rule) =>
    pickGuidelineId ? rule.guideline_id === pickGuidelineId : false,
  );

  const selectPickGuideline = useCallback((guidelineId: string) => {
    setPickGuidelineId(guidelineId);
    setSelectedRuleIds(new Set());
  }, []);

  const canCompile =
    !compiling &&
    (compileMode === "global" ||
      (compileMode === "guideline" && Boolean(scopeId) && scopeId !== "default") ||
      (compileMode === "pick" &&
        Boolean(pickScopeId.trim()) &&
        selectedRuleIds.size > 0));

  const toggleRuleId = useCallback((ruleId: string) => {
    setSelectedRuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) next.delete(ruleId);
      else next.add(ruleId);
      return next;
    });
  }, []);

  const clearRuleIds = useCallback(() => setSelectedRuleIds(new Set()), []);

  const _resolvedScope = useCallback((): {
    scope_type: string;
    scope_id: string;
  } => {
    if (compileMode === "guideline") {
      return { scope_type: "guideline", scope_id: scopeId || "default" };
    }
    if (compileMode === "pick") {
      return { scope_type: "custom", scope_id: pickScopeId || "pick-default" };
    }
    return { scope_type: "global", scope_id: "default" };
  }, [compileMode, scopeId, pickScopeId]);

  const fetchStatus = useCallback(async (): Promise<BitmapStatus | null> => {
    const { scope_type, scope_id } = _resolvedScope();
    const qs = new URLSearchParams({ scope_type, scope_id }).toString();
    try {
      const [statusResp, compiledResp] = await Promise.all([
        fetch(`/api/terminology/guidelines/bitmap/status?${qs}`),
        fetch(`/api/terminology/guidelines/compiled?${qs}`),
      ]);
      if (!statusResp.ok || !compiledResp.ok) throw new Error("fetch failed");
      const statusData: BitmapStatus = await statusResp.json();
      const compiled = (await compiledResp.json()) as {
        versions?: VersionEntry[];
      };
      setStatus(statusData);
      setVersions(Array.isArray(compiled.versions) ? compiled.versions : []);
      setError(null);
      return statusData;
    } catch {
      setError("Could not load the current status. Please refresh the page.");
      return null;
    }
  }, [_resolvedScope]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus, refreshKey]);
  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    if (!compiling) {
      setCompileElapsedSec(0);
      return;
    }
    const started = Date.now();
    setCompileElapsedSec(0);
    const tick = setInterval(() => {
      setCompileElapsedSec(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => clearInterval(tick);
  }, [compiling]);

  const handleCompile = useCallback(async () => {
    setCompiling(true);
    setError(null);
    setShadowSummary(null);
    try {
      const { scope_type, scope_id } = _resolvedScope();
      const compileBody: Record<string, unknown> = {
        scope_type,
        scope_id,
        policy_mode: policyMode,
        activate: false,
        distance_child_override: distanceChild === "" ? null : Number(distanceChild),
        distance_parent_override: distanceParent === "" ? null : Number(distanceParent),
      };
      if (compileMode === "pick") {
        compileBody.include_rule_ids = [...selectedRuleIds];
      }
      const resp = await fetch("/api/terminology/guidelines/bitmap/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(compileBody),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const started = (await resp.json()) as { job_id: string; version: string };
      setCandidateVersion(started.version);
      const pollStart = Date.now();
      const finishCompile = (ok: boolean) => {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setCompiling(false);
        setRefreshKey((n) => n + 1);
        if (ok) {
          setJustCompiled(true);
          setTimeout(() => setJustCompiled(false), 2200);
        }
      };
      pollRef.current = setInterval(async () => {
        const elapsed = Date.now() - pollStart;
        const jobResp = await fetch(
          `/api/terminology/guidelines/bitmap/jobs/${started.job_id}`,
        );
        if (jobResp.ok) {
          const job = (await jobResp.json()) as { status?: string };
          if (job.status === "error") {
            setError("Compile failed. Check the API logs and try again.");
            finishCompile(false);
            return;
          }
          if (job.status === "done") {
            finishCompile(true);
            return;
          }
        }
        // Job state is in-memory -- lost on API reload. If the candidate
        // version is already listed, compile succeeded even when the job
        // endpoint 404s or never flips to done.
        const { scope_type: pst, scope_id: psi } = _resolvedScope();
        const versionsResp = await fetch(
          `/api/terminology/guidelines/compiled?scope_type=${encodeURIComponent(
            pst,
          )}&scope_id=${encodeURIComponent(psi)}`,
        );
        if (versionsResp.ok) {
          const listed = (await versionsResp.json()) as {
            versions?: Array<{ version?: string }>;
          };
          if ((listed.versions ?? []).some((v) => v.version === started.version)) {
            finishCompile(true);
            return;
          }
        }
        if (elapsed > 300_000) {
          setError(
            "Compile is taking too long. Refresh the page -- the candidate may already be ready.",
          );
          finishCompile(false);
        }
      }, 3000);
    } catch {
      setError("Could not start the compile. Please try again.");
      setCompiling(false);
    }
  }, [_resolvedScope, compileMode, distanceChild, distanceParent, policyMode, selectedRuleIds]);

  const handleTestOnLabPatients = useCallback(() => {
    if (!versions.length) return;
    setError(null);
    setCandidateTestSummary(null);
    setLabTestOpen(true);
  }, [versions.length]);

  const handleLabTestComplete = useCallback((summary: CandidateTestSummary) => {
    setCandidateTestSummary(summary);
  }, []);

  const handleLabTestClose = useCallback(() => {
    setLabTestOpen(false);
  }, []);

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
      const { scope_type: hst, scope_id: hsi } = _resolvedScope();
      const resp = await fetch("/api/guidance/shadow/diff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_version: candidateVersion,
          scope_type: hst,
          scope_id: hsi,
          guideline_id: compileMode === "guideline" ? scopeId : null,
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
  }, [candidateVersion, compileMode, scopeId, _resolvedScope]);

  const handleActivate = useCallback(
    async (version: string) => {
      setActivatingVersion(version);
      setError(null);
      try {
        const { scope_type: ast, scope_id: asi } = _resolvedScope();
        const resp = await fetch(
          `/api/terminology/guidelines/bitmap/versions/${encodeURIComponent(version)}/activate`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scope_type: ast, scope_id: asi }),
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
    [onVersionActivated, _resolvedScope],
  );

  const handleRollback = useCallback(async () => {
    setRollingBack(true);
    setError(null);
    try {
      const { scope_type: rst, scope_id: rsi } = _resolvedScope();
      const resp = await fetch("/api/terminology/guidelines/bitmap/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope_type: rst, scope_id: rsi }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setRefreshKey((n) => n + 1);
    } catch {
      setError("Could not roll back this scope. Check there is at least one previous version.");
    } finally {
      setRollingBack(false);
    }
  }, [_resolvedScope]);

  return {
    compileMode,
    setCompileMode,
    scopeId,
    setScopeId,
    pickScopeId,
    setPickScopeId,
    pickGuidelineId,
    selectPickGuideline,
    selectedRuleIds,
    toggleRuleId,
    clearRuleIds,
    activeRules,
    visibleRules,
    rulesLoadError,
    canCompile,
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
    compileElapsedSec,
    rollingBack,
    activatingVersion,
    confirmVersion,
    setConfirmVersion,
    justActivatedVersion,
    justCompiled,
    candidateVersion,
    labTestOpen,
    candidateTestSummary,
    shadowing,
    shadowSummary,
    handleCompile,
    handleTestOnLabPatients,
    handleLabTestComplete,
    handleLabTestClose,
    handleHistoricShadow,
    handleActivate,
    handleRollback,
  };
}
