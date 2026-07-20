"use client";

/**
 * Validation Lab -- Cases panel: create a new test patient via the
 * guided wizard, then browse existing patients + their real run history.
 *
 * Atlas: UN-4DCE95C8 / DI-724CD8A5 / DI-2289D095 / DI-9138BAC9 / DI-A898556B
 * DO: DO-158BE606
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import CreatePatientWizard from "./CreatePatientWizard";
import { getCase, listCases, promoteGold, scoreRun, type LabCase } from "./labApi";

export default function LabCasesPanel() {
  const [cases, setCases] = useState<LabCase[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<LabCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [score, setScore] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [showWizard, setShowWizard] = useState(true);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Promote failed");
    } finally {
      setBusy(false);
    }
  }

  const latestRun = detail?.runs?.[0];
  const assessmentId = latestRun?.outputs?.sbar_assessment_id;

  return (
    <Box data-testid="validation-lab-cases-panel">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        One flow: new test patient -&gt; build profile -&gt; add encounter(s)
        -&gt; create referral documentation -&gt; submit referral. Submitting
        runs the real pipeline end-to-end -- nothing shown here is
        fabricated.
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
          <CreatePatientWizard onCaseCreated={() => void reloadList()} />
        </Box>
      )}

      <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
        Test patients
      </Typography>
      <Stack spacing={1} sx={{ mb: 3 }} data-testid="validation-lab-case-list">
        {cases.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No test patients yet. Use &quot;New test patient&quot; above.
          </Typography>
        )}
        {cases.map((c) => (
          <Button
            key={c.id}
            variant={c.id === selectedId ? "contained" : "text"}
            onClick={() => void loadCase(c.id)}
            sx={{ justifyContent: "flex-start" }}
          >
            {c.title || c.id}
          </Button>
        ))}
      </Stack>

      {detail && (
        <Box sx={{ mb: 3 }} data-testid="validation-lab-case-detail">
          <Typography variant="subtitle1">
            Selected: {detail.title} -- patient {detail.patient_id}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Referral {detail.referral_id || "-"} | Chunks{" "}
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
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
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
    </Box>
  );
}
