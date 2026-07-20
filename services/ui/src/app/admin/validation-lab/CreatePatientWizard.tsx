"use client";

/**
 * Validation Lab -- 5-step "new test patient" wizard.
 *
 * new test patient -> build profile (PMH) -> add encounter(s) ->
 * create referral documentation -> submit referral (real pipeline run).
 *
 * Atlas:
 *   UN: UN-4DCE95C8
 *   DI: DI-724CD8A5, DI-2289D095, DI-9138BAC9
 *   DO: DO-158BE606
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import { EncountersStep, ProfilePmhStep } from "./WizardPmhEncounterSteps";
import { useCreatePatientWizard } from "./useCreatePatientWizard";

const STEPS = [
  "New test patient",
  "Build profile",
  "Encounters",
  "Referral",
  "Submit",
];

interface CreatePatientWizardProps {
  onCaseCreated?: (caseId: string) => void;
}

export default function CreatePatientWizard({
  onCaseCreated,
}: CreatePatientWizardProps) {
  const wizard = useCreatePatientWizard(onCaseCreated);
  const {
    step,
    setStep,
    goNext,
    goBack,
    title,
    setTitle,
    patientName,
    setPatientName,
    patientAge,
    setPatientAge,
    patientSex,
    setPatientSex,
    pmhRows,
    addPmhRow,
    updatePmhRow,
    removePmhRow,
    encounterRows,
    addEncounterRow,
    updateEncounterRow,
    removeEncounterRow,
    referralText,
    setReferralText,
    planId,
    setPlanId,
    busy,
    polling,
    error,
    run,
    submit,
    reset,
  } = wizard;

  const canLeavePatientStep = title.trim().length > 0;
  const canSubmit = referralText.trim().length > 0;
  const assessmentId = run?.outputs?.sbar_assessment_id;
  const phaseOutputs = run?.outputs?.phase_outputs ?? [];

  return (
    <Box data-testid="create-patient-wizard">
      <Stepper activeStep={step} sx={{ mb: 3 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="wizard-error">
          {error}
        </Alert>
      )}

      {step === 0 && (
        <Stack spacing={2} data-testid="wizard-step-patient">
          <Typography variant="body2" color="text.secondary">
            Start a new production-faithful test patient. Only the title is
            required to move on.
          </Typography>
          <TextField
            label="Test patient / case title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            data-testid="wizard-title"
          />
          <TextField
            label="Patient name (optional)"
            value={patientName}
            onChange={(e) => setPatientName(e.target.value)}
            data-testid="wizard-patient-name"
          />
          <Stack direction="row" spacing={2}>
            <TextField
              label="Age"
              type="number"
              value={patientAge}
              onChange={(e) => setPatientAge(e.target.value)}
              data-testid="wizard-patient-age"
            />
            <TextField
              select
              label="Sex"
              value={patientSex}
              onChange={(e) => setPatientSex(e.target.value)}
              sx={{ minWidth: 160 }}
              data-testid="wizard-patient-sex"
            >
              <MenuItem value="">Not specified</MenuItem>
              <MenuItem value="male">Male</MenuItem>
              <MenuItem value="female">Female</MenuItem>
              <MenuItem value="other">Other</MenuItem>
            </TextField>
          </Stack>
        </Stack>
      )}

      {step === 1 && (
        <ProfilePmhStep
          rows={pmhRows}
          onAdd={addPmhRow}
          onUpdate={updatePmhRow}
          onRemove={removePmhRow}
        />
      )}

      {step === 2 && (
        <EncountersStep
          rows={encounterRows}
          onAdd={addEncounterRow}
          onUpdate={updateEncounterRow}
          onRemove={removeEncounterRow}
        />
      )}

      {step === 3 && (
        <Stack spacing={2} data-testid="wizard-step-referral">
          <Typography variant="body2" color="text.secondary">
            Required. This is the only document the real pipeline reads --
            it is submitted exactly as production referrals are, as document
            chunks, never as structured data.
          </Typography>
          <TextField
            label="Referral letter text"
            value={referralText}
            onChange={(e) => setReferralText(e.target.value)}
            multiline
            minRows={8}
            required
            data-testid="wizard-referral-text"
          />
          <TextField
            label="Plan definition id"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
            size="small"
            data-testid="wizard-plan-id"
          />
        </Stack>
      )}

      {step === 4 && (
        <Stack spacing={2} data-testid="wizard-step-submit">
          <Typography variant="body2" color="text.secondary">
            Submitting enqueues the same referral-received event a real
            referral would send. Nothing is fabricated -- the SBAR below is
            the genuine pipeline result.
          </Typography>
          {!run && (
            <Button
              variant="contained"
              onClick={() => void submit()}
              disabled={busy || !canSubmit}
              data-testid="wizard-submit"
            >
              Submit referral
            </Button>
          )}
          {run && (
            <Alert
              severity={run.status === "failed" ? "error" : "info"}
              data-testid="wizard-run-status"
            >
              Run {run.id}: {run.status}
              {polling ? " (waiting for the real pipeline...)" : ""}
            </Alert>
          )}
          {polling && <CircularProgress size={20} />}
          {phaseOutputs.length > 0 && (
            <Stack spacing={1} data-testid="wizard-phase-outputs">
              {phaseOutputs.map((p) => (
                <Alert
                  key={p.phase_id}
                  severity={p.pipeline_error ? "error" : "info"}
                  data-testid={`wizard-phase-${p.phase_id}`}
                >
                  {p.headline || p.phase_id}: {p.status}
                </Alert>
              ))}
            </Stack>
          )}
          {assessmentId && (
            <Box data-testid="wizard-sbar">
              <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
                SBAR (real pipeline output)
              </Typography>
              <LeoSbarHost assessmentId={assessmentId} />
            </Box>
          )}
          {run && run.status !== "queued" && (
            <Button variant="outlined" onClick={reset} data-testid="wizard-start-another">
              Start another test patient
            </Button>
          )}
        </Stack>
      )}

      {step < 4 && (
        <Stack direction="row" spacing={1} sx={{ mt: 3 }}>
          <Button disabled={step === 0} onClick={goBack} data-testid="wizard-back">
            Back
          </Button>
          <Button
            variant="contained"
            onClick={goNext}
            disabled={step === 0 && !canLeavePatientStep}
            data-testid="wizard-next"
          >
            {step === 3 ? "Review" : "Next"}
          </Button>
          {step > 0 && (
            <Button onClick={() => setStep(4)} data-testid="wizard-skip-to-submit">
              Skip to submit
            </Button>
          )}
        </Stack>
      )}
    </Box>
  );
}
