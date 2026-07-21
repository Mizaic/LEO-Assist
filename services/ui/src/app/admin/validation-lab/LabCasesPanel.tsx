"use client";

/**
 * Validation Lab -- Cases panel: create a new test patient via the
 * guided wizard, then browse existing patients in a rolodex with
 * search / filter / rename / delete / Test (real pipeline run).
 *
 * Atlas: UN-4DCE95C8 / DI-724CD8A5 / DI-2289D095 / DI-9138BAC9 /
 * DI-A898556B / DI-12D40786 / DI-43E908C6
 * DO: DO-158BE606
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { PatientShell } from "@/components/patients/PatientShell";
import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import CreatePatientWizard from "./CreatePatientWizard";
import TestPatientRolodex from "./TestPatientRolodex";
import {
  deleteCase,
  getCase,
  listCases,
  promoteGold,
  scoreRun,
  updateCase,
  type LabCase,
} from "./labApi";
import { runCasePipeline } from "./labRun";

function carePatientHref(patientId: string): string {
  return `/care/patients/${encodeURIComponent(patientId)}`;
}

export default function LabCasesPanel() {
  const [cases, setCases] = useState<LabCase[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<LabCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [score, setScore] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [testingCaseId, setTestingCaseId] = useState("");
  const [showWizard, setShowWizard] = useState(true);
  const [viewPatientId, setViewPatientId] = useState<string>("");

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

  async function onTest(caseId: string) {
    setBusy(true);
    setTestingCaseId(caseId);
    setError(null);
    setNotice(null);
    try {
      const labCase = await getCase(caseId);
      setNotice("Pipeline run started...");
      await loadCase(caseId);
      const finalRun = await runCasePipeline(caseId, labCase.plan_id);
      setNotice(`Pipeline run ${finalRun.id}: ${finalRun.status}`);
      if (finalRun.status === "failed") {
        setError(
          finalRun.error_message ||
            "Pipeline test failed to start. Check Service Bus and the pipeline worker.",
        );
      }
      await loadCase(caseId);
      await reloadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline test failed");
    } finally {
      setTestingCaseId("");
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

  return (
    <Box data-testid="validation-lab-cases-panel">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Create synthetic test patients, browse them like a rolodex, then run
        the real pipeline. Nothing shown here is fabricated.
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
          variant={showWizard ? "contained" : "outlined"}
          onClick={() => {
            setShowWizard(true);
            setDetail(null);
            setSelectedId("");
          }}
          data-testid="validation-lab-new-patient"
        >
          New test patient
        </Button>
      </Stack>

      {showWizard && (
        <Box sx={{ mb: 3 }}>
          <CreatePatientWizard
            onCaseCreated={() => {
              void reloadList();
            }}
          />
        </Box>
      )}

      <Box sx={{ mb: 3 }}>
        <TestPatientRolodex
          cases={cases}
          selectedId={selectedId}
          busy={busy}
          testingCaseId={testingCaseId}
          onSelect={(id) => void loadCase(id)}
          onViewPatient={setViewPatientId}
          onTest={onTest}
          onRename={onRename}
          onDelete={onDelete}
          onDeleteMany={onDeleteMany}
        />
      </Box>

      {detail && (
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
            <Typography variant="body2" color="text.secondary">
              Latest run: {latestRun.id} ({latestRun.status})
            </Typography>
          )}
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
            <Button
              variant="outlined"
              disabled={!detail.patient_id}
              href={
                detail.patient_id
                  ? carePatientHref(detail.patient_id)
                  : undefined
              }
              target="_blank"
              rel="noopener noreferrer"
              data-testid="validation-lab-open-care"
            >
              Open in Care
            </Button>
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

      {assessmentId && (
        <Box sx={{ mt: 2 }} data-testid="validation-lab-sbar">
          <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
            SBAR (CDN widget)
          </Typography>
          <LeoSbarHost assessmentId={assessmentId} />
        </Box>
      )}

      <Dialog
        fullScreen
        open={Boolean(viewPatientId)}
        onClose={() => setViewPatientId("")}
        data-testid="validation-lab-patient-dialog"
      >
        {viewPatientId ? (
          <PatientShell
            patientId={viewPatientId}
            backLabel="Back to Validation Lab"
            onBack={() => setViewPatientId("")}
          />
        ) : null}
      </Dialog>
    </Box>
  );
}
