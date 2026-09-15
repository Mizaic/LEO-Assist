/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

/**
 * Validation Lab -- Cases panel: create a new test patient via the
 * guided wizard, then browse existing patients in a rolodex with
 * search / filter / rename / delete / Test (real pipeline run).
 *
 * Atlas: UN-4DCE95C8 / DI-724CD8A5 / DI-2289D095 / DI-9138BAC9 /
 * DI-A898556B / DI-12D40786 / DI-43E908C6 / DI-020F98AE /
 * DI-FE423B8D / DI-62175179
 * DO: DO-158BE606
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { PatientShell } from "@/components/patients/PatientShell";
import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import CreatePatientWizard from "./CreatePatientWizard";
import {
  initialMultiSheet,
  runBatchWithLiveProgress,
} from "./labBatchRunner";
import LabRunSheetHost from "./LabRunSheetHost";
import type { RunSheetState } from "./RunSheetDialog";
import TestPatientRolodex from "./TestPatientRolodex";
import {
  deleteCase,
  getCase,
  listCases,
  promoteGold,
  scoreRun,
  updateCase,
  type LabCase,
  type LabRun,
} from "./labApi";
import { formatUsd } from "./labRunFormat";
import { pollCasePipeline, queueCasePipeline } from "./labRun";

function carePatientHref(patientId: string): string {
  return `/care/patients/${encodeURIComponent(patientId)}`;
}

export default function LabCasesPanel({
  initialMode,
  onBack,
}: {
  initialMode?: "rule" | "case";
  onBack?: () => void;
}) {
  const [cases, setCases] = useState<LabCase[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<LabCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [score, setScore] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [testingCaseId, setTestingCaseId] = useState("");
  // "rule" mode starts with the create wizard open; "case" mode goes straight to the list
  const [showWizard, setShowWizard] = useState(initialMode !== "case");
  const [viewPatientId, setViewPatientId] = useState<string>("");
  const [runSheet, setRunSheet] = useState<RunSheetState | null>(null);
  const sheetOpenRef = useRef(true);

  const reloadList = useCallback(async () => {
    setCases(await listCases());
  }, []);

  useEffect(() => {
    void reloadList().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : "Unable to load cases"),
    );
  }, [reloadList]);

  const loadCase = useCallback(async (id: string) => {
    setScore(null);
    const c = await getCase(id);
    setDetail(c);
    setSelectedId(id);
    setShowWizard(false);
  }, []);

  function closeRunSheet() {
    sheetOpenRef.current = false;
    setRunSheet(null);
    setBusy(false);
  }

  function applySingleTick(caseId: string, title: string, run: LabRun) {
    if (!sheetOpenRef.current) return;
    const terminal =
      run.status === "completed" || run.status === "failed";
    setRunSheet({
      mode: "single",
      caseId,
      title,
      runId: run.id,
      status: run.status,
      phases: run.outputs?.phase_outputs || [],
      stages: run.stage_progress || [],
      llmUsage: run.outputs?.llm_usage,
      rulesetVersion: run.ruleset_version,
      error: run.error_message || undefined,
      terminal,
    });
  }

  async function onTest(caseId: string) {
    setBusy(true);
    setTestingCaseId(caseId);
    setError(null);
    setNotice(null);
    sheetOpenRef.current = true;
    try {
      const labCase = await getCase(caseId);
      const title = labCase.title || caseId;
      setRunSheet({
        mode: "single",
        caseId,
        title,
        status: "starting",
        phases: [],
        terminal: false,
      });
      await loadCase(caseId);
      const started = await queueCasePipeline(caseId, labCase.plan_id);
      applySingleTick(caseId, title, started);
      const finalRun = await pollCasePipeline(caseId, started.id, (run) =>
        applySingleTick(caseId, title, run),
      );
      applySingleTick(caseId, title, finalRun);
      if (finalRun.status === "completed") {
        setNotice(`Pipeline run ${finalRun.id}: completed`);
      } else if (finalRun.status === "failed") {
        setError(
          finalRun.error_message ||
            "Pipeline test failed. Check Service Bus and the pipeline worker.",
        );
      } else {
        setError(
          finalRun.error_message ||
            `Pipeline run stopped updating while status was "${finalRun.status}". Refresh the case or re-test.`,
        );
      }
      await loadCase(caseId);
      await reloadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline test failed");
      if (sheetOpenRef.current) {
        setRunSheet((prev) =>
          prev && prev.mode === "single"
            ? {
                ...prev,
                status: "failed",
                error: err instanceof Error ? err.message : "Pipeline test failed",
                terminal: true,
              }
            : prev,
        );
      }
    } finally {
      setTestingCaseId("");
      setBusy(false);
    }
  }

  async function onTestMany(caseIds: string[]) {
    if (!caseIds.length) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    sheetOpenRef.current = true;
    setRunSheet(initialMultiSheet(caseIds, cases));
    try {
      const feedback = await runBatchWithLiveProgress({
        caseIds,
        cases,
        isOpen: () => sheetOpenRef.current,
        onSheet: (updater) => {
          setRunSheet((prev) =>
            prev && prev.mode === "multi" ? updater(prev) : prev,
          );
        },
      });
      setNotice(feedback.notice);
      if (feedback.error) setError(feedback.error);
      await reloadList();
      if (selectedId && caseIds.includes(selectedId)) {
        await loadCase(selectedId);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to queue pipeline runs",
      );
      await reloadList();
    } finally {
      setBusy(false);
    }
  }

  async function onPromote() {
    const latestRun = detail?.runs?.[0];
    if (!selectedId || !latestRun) return;
    setBusy(true);
    setError(null);
    try {
      await promoteGold(selectedId, latestRun.id);
      setNotice("Saved run as gold.");
      setScore(await scoreRun(selectedId, latestRun.id));
      await loadCase(selectedId);
      await reloadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Promote failed");
    } finally {
      setBusy(false);
    }
  }

  async function onRename(caseId: string, title: string) {
    setBusy(true);
    setError(null);
    try {
      await updateCase(caseId, { title });
      setNotice("Renamed test patient.");
      await reloadList();
      if (selectedId === caseId) await loadCase(caseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(caseId: string) {
    await onDeleteMany([caseId]);
  }

  async function onDeleteMany(caseIds: string[]) {
    if (!caseIds.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const caseId of caseIds) {
        await deleteCase(caseId);
      }
      setNotice(
        caseIds.length === 1
          ? "Deleted test patient."
          : `Deleted ${caseIds.length} test patients.`,
      );
      if (caseIds.includes(selectedId)) {
        setSelectedId("");
        setDetail(null);
        setScore(null);
      }
      await reloadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      await reloadList();
    } finally {
      setBusy(false);
    }
  }

  const latestRun = detail?.runs?.[0];
  const assessmentId = latestRun?.outputs?.sbar_assessment_id;
  const latestCost =
    latestRun?.outputs?.llm_usage?.cost_usd ?? latestRun?.llm_cost_usd;

  const makingNew = showWizard;
  const modeLabel = initialMode === "case" ? "Open a saved test" : "Make a new test";
  const modeHint = makingNew
    ? "Follow the steps. When you submit, LEO will read the letter."
    : "Pick a test. Press Test to see what LEO found.";

  return (
    <Box data-testid="validation-lab-cases-panel">
      {onBack ? (
        <Button size="small" onClick={onBack} sx={{ mb: 1 }}>
          Back to start
        </Button>
      ) : null}
      <Typography variant="h6" fontWeight={700} sx={{ mb: 0.5 }}>
        {modeLabel}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {modeHint}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="validation-lab-error">
          {error}
        </Alert>
      )}
      {notice && (
        <Alert severity="success" sx={{ mb: 2 }} data-testid="validation-lab-notice">
          {notice}
        </Alert>
      )}

      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Button
          variant={makingNew ? "contained" : "outlined"}
          onClick={() => {
            setShowWizard(true);
            setDetail(null);
            setSelectedId("");
          }}
          data-testid="validation-lab-new-patient"
        >
          Make a new test
        </Button>
        <Button
          variant={!makingNew ? "contained" : "outlined"}
          onClick={() => setShowWizard(false)}
          data-testid="validation-lab-browse"
        >
          Open a saved test
        </Button>
      </Stack>

      {makingNew && (
        <Box sx={{ mb: 3 }}>
          <CreatePatientWizard
            onCaseCreated={() => {
              void reloadList();
            }}
          />
        </Box>
      )}

      {!makingNew && (
      <Box sx={{ mb: 3 }}>
        <TestPatientRolodex
          cases={cases}
          selectedId={selectedId}
          busy={busy}
          testingCaseId={testingCaseId}
          onSelect={(id) => void loadCase(id)}
          onViewPatient={setViewPatientId}
          onTest={onTest}
          onTestMany={onTestMany}
          onRename={onRename}
          onDelete={onDelete}
          onDeleteMany={onDeleteMany}
        />
      </Box>
      )}

      {detail && !makingNew && (
        <Box sx={{ mb: 3 }} data-testid="validation-lab-case-detail">
          <Typography variant="subtitle1">
            Selected: {detail.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Patient {detail.patient_id || "-"} | Referral{" "}
            {detail.referral_id || "-"} | Chunks{" "}
            {(detail.chunk_ids || []).length} | Background encounters{" "}
            {(detail.background_encounter_ids || []).length}
          </Typography>
          {latestRun && (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid="validation-lab-latest-run"
            >
              Latest run: {latestRun.id} ({latestRun.status}) ·{" "}
              {formatUsd(latestCost)}
              {latestRun.ruleset_version
                ? ` · bitmap ${latestRun.ruleset_version}`
                : ""}
            </Typography>
          )}
          {latestRun?.ruleset_version ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", fontFamily: "monospace" }}
              data-testid="validation-lab-latest-bitmap"
            >
              Bitmap version: {latestRun.ruleset_version}
            </Typography>
          ) : null}
          {score && (
            <Alert
              severity={score.pass ? "success" : "warning"}
              sx={{ mt: 1 }}
              data-testid="validation-lab-score"
            >
              Gold score: {score.pass ? "pass" : "fail"}
            </Alert>
          )}
          <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap">
            <Button
              variant="contained"
              disabled={busy || testingCaseId === detail.id}
              onClick={() => void onTest(detail.id)}
              data-testid="validation-lab-test-pipeline"
            >
              {testingCaseId === detail.id ? "Testing..." : "Test pipeline"}
            </Button>
            <Button
              variant="outlined"
              disabled={!detail.patient_id}
              onClick={() => {
                if (detail.patient_id) setViewPatientId(detail.patient_id);
              }}
              data-testid="validation-lab-view-patient"
            >
              View patient
            </Button>
            {detail.patient_id ? (
              <Button
                variant="outlined"
                href={carePatientHref(detail.patient_id)}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="validation-lab-open-care"
              >
                Open in Care
              </Button>
            ) : (
              <Button
                variant="outlined"
                disabled
                data-testid="validation-lab-open-care"
              >
                Open in Care
              </Button>
            )}
            <Button
              variant="outlined"
              onClick={() => void onPromote()}
              disabled={
                busy || !latestRun || latestRun.persist_mode !== "production"
              }
              data-testid="validation-lab-promote"
            >
              Save latest run as gold
            </Button>
          </Stack>
        </Box>
      )}

      {assessmentId && !makingNew && (
        <Box sx={{ mt: 2 }} data-testid="validation-lab-sbar">
          <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
            LEO's draft summary
          </Typography>
          <LeoSbarHost assessmentId={assessmentId} />
        </Box>
      )}

      <LabRunSheetHost
        sheet={runSheet}
        detail={detail}
        onClose={closeRunSheet}
        onRetest={(caseId) => void onTest(caseId)}
        onSavedGold={() => void onPromote()}
      />

      <Dialog
        fullScreen
        open={Boolean(viewPatientId)}
        onClose={() => setViewPatientId("")}
        data-testid="validation-lab-patient-dialog"
      >
        {viewPatientId ? (
          <div style={{ height: "100%", minHeight: 0 }}>
            <PatientShell
              patientId={viewPatientId}
              backLabel="Back to Validation Lab"
              onBack={() => setViewPatientId("")}
            />
          </div>
        ) : null}
      </Dialog>
    </Box>
  );
}
