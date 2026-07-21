"use client";

/**
 * Validation Lab -- 5-step "new test patient" wizard.
 *
 * Supports generic referral / A&G plus SPoA-shaped scenarios
 * (EPC patient, GP consult, verbalised PMH in submission text).
 *
 * Atlas:
 *   UN: UN-4DCE95C8
 *   DI: DI-724CD8A5, DI-2289D095, DI-9138BAC9, DI-D6E5F94E
 *   DO: DO-158BE606, DO-E981C7B1
 */

import { useState } from "react";
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
import ScenarioBrainstormDrawer from "./ScenarioBrainstormDrawer";
import {
  useCreatePatientWizard,
  type WizardScenario,
} from "./useCreatePatientWizard";
import { EncountersStep, ProfilePmhStep } from "./WizardPmhEncounterSteps";
import { WizardAgThreadStep } from "./WizardAgThreadSteps";
import { WizardGpConsultStep } from "./WizardGpConsultStep";

const GENERIC_STEPS = [
  "New test patient",
  "Build profile",
  "Encounters",
  "Clinical text",
  "Submit",
];

const SPOA_STEPS = [
  "New test patient",
  "Build profile",
  "GP consultation",
  "Submission",
  "Submit",
];

interface CreatePatientWizardProps {
  onCaseCreated?: (caseId: string) => void;
}

export default function CreatePatientWizard({
  onCaseCreated,
}: CreatePatientWizardProps) {
  const [brainstormOpen, setBrainstormOpen] = useState(false);
  const wizard = useCreatePatientWizard(onCaseCreated);
  const {
    step,
    setStep,
    goNext,
    goBack,
    scenario,
    setScenario,
    caseType,
    spoa,
    title,
    setTitle,
    patientName,
    setPatientName,
    patientAge,
    setPatientAge,
    patientSex,
    setPatientSex,
    nhsNumber,
    setNhsNumber,
    gpPracticeName,
    setGpPracticeName,
    pmhRows,
    addPmhRow,
    updatePmhRow,
    removePmhRow,
    encounterRows,
    addEncounterRow,
    updateEncounterRow,
    removeEncounterRow,
    gpConsultLabel,
    setGpConsultLabel,
    gpConsultText,
    setGpConsultText,
    gpConsultDate,
    setGpConsultDate,
    reasonForSubmission,
    setReasonForSubmission,
    pmhPreview,
    refreshPmhPreview,
    referralText,
    setReferralText,
    planId,
    setPlanId,
    agTurnRows,
    addAgTurn,
    updateAgTurn,
    removeAgTurn,
    agResponseText,
    setAgResponseText,
    agRequestAttachments,
    addAgRequestAttachment,
    updateAgRequestAttachment,
    removeAgRequestAttachment,
    agUbrn,
    setAgUbrn,
    busy,
    polling,
    error,
    run,
    submit,
    reset,
  } = wizard;

  const steps = spoa ? SPOA_STEPS : GENERIC_STEPS;
  const canLeavePatientStep = title.trim().length > 0;
  const canLeaveGpStep = !spoa || gpConsultText.trim().length > 0;
  const canSubmit =
    caseType === "referral"
      ? spoa
        ? reasonForSubmission.trim().length > 0 || referralText.trim().length > 0
        : referralText.trim().length > 0
      : spoa
        ? reasonForSubmission.trim().length > 0 ||
          agTurnRows.some((row) => row.note.trim()) ||
          agResponseText.trim().length > 0
        : agTurnRows.some((row) => row.note.trim()) ||
          agResponseText.trim().length > 0;
  const assessmentId = run?.outputs?.sbar_assessment_id;
  const phaseOutputs = run?.outputs?.phase_outputs ?? [];
  const canGoNext =
    (step === 0 && canLeavePatientStep) ||
    (step === 2 && canLeaveGpStep) ||
    (step !== 0 && step !== 2);

  return (
    <Box data-testid="create-patient-wizard">
      <Stepper activeStep={step} sx={{ mb: 3 }}>
        {steps.map((label) => (
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
            required to move on. SPoA scenarios add a GP consultation and
            verbalise past medical history in the submission text.
          </Typography>
          <Button
            variant="outlined"
            onClick={() => setBrainstormOpen(true)}
            data-testid="open-brainstorm-drawer"
          >
            Brainstorm scenario
          </Button>
          <TextField
            select
            label="Scenario"
            value={scenario}
            onChange={(e) => setScenario(e.target.value as WizardScenario)}
            sx={{ maxWidth: 420 }}
            data-testid="wizard-scenario"
          >
            <MenuItem value="generic_referral">Generic referral</MenuItem>
            <MenuItem value="generic_ag">Generic A&amp;G</MenuItem>
            <MenuItem value="spo_ag">SPoA: A&amp;G request</MenuItem>
            <MenuItem value="ras_referral">RAS: Referral</MenuItem>
          </TextField>
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
          {spoa && (
            <Stack spacing={2} data-testid="wizard-spoa-demographics">
              <TextField
                label="NHS number (optional)"
                value={nhsNumber}
                onChange={(e) => setNhsNumber(e.target.value)}
                data-testid="wizard-nhs-number"
              />
              <TextField
                label="GP practice name (optional)"
                value={gpPracticeName}
                onChange={(e) => setGpPracticeName(e.target.value)}
                data-testid="wizard-gp-practice"
              />
            </Stack>
          )}
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

      {step === 2 && !spoa && (
        <EncountersStep
          rows={encounterRows}
          onAdd={addEncounterRow}
          onUpdate={updateEncounterRow}
          onRemove={removeEncounterRow}
        />
      )}

      {step === 2 && spoa && (
        <WizardGpConsultStep
          label={gpConsultLabel}
          text={gpConsultText}
          date={gpConsultDate}
          onLabelChange={setGpConsultLabel}
          onTextChange={setGpConsultText}
          onDateChange={setGpConsultDate}
        />
      )}

      {step === 3 && caseType === "referral" && (
        <Stack spacing={2} data-testid="wizard-step-referral">
          <Typography variant="body2" color="text.secondary">
            {spoa
              ? "Enter the reason for referral. Past medical history is verbalised into the referral letter text for the pipeline; the GP note stays on the graph only."
              : "Required. This is the only document the real pipeline reads -- it is submitted exactly as production referrals are, as document chunks, never as structured data."}
          </Typography>
          {spoa && (
            <TextField
              label="Reason for referral"
              value={reasonForSubmission}
              onChange={(e) => setReasonForSubmission(e.target.value)}
              multiline
              minRows={3}
              required
              data-testid="wizard-reason-for-submission"
            />
          )}
          <TextField
            label={spoa ? "Extra referral letter text (optional)" : "Referral letter text"}
            value={referralText}
            onChange={(e) => setReferralText(e.target.value)}
            multiline
            minRows={spoa ? 4 : 8}
            required={!spoa}
            data-testid="wizard-referral-text"
          />
          {spoa && (
            <Stack spacing={1} data-testid="wizard-pmh-preview">
              <Button
                variant="outlined"
                size="small"
                onClick={() => void refreshPmhPreview()}
                data-testid="wizard-preview-pmh"
              >
                Preview verbalised PMH
              </Button>
              {pmhPreview ? (
                <Alert severity="info" data-testid="wizard-pmh-preview-text">
                  <Typography
                    component="pre"
                    sx={{ whiteSpace: "pre-wrap", m: 0, fontFamily: "inherit" }}
                  >
                    {pmhPreview}
                  </Typography>
                </Alert>
              ) : null}
            </Stack>
          )}
          <TextField
            label="Plan definition id"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
            size="small"
            data-testid="wizard-plan-id"
          />
        </Stack>
      )}

      {step === 3 && caseType === "ag" && (
        <Stack spacing={2}>
          {spoa && (
            <>
              <TextField
                label="Reason for A&amp;G request"
                value={reasonForSubmission}
                onChange={(e) => setReasonForSubmission(e.target.value)}
                multiline
                minRows={3}
                required
                data-testid="wizard-reason-for-submission"
              />
              <Stack spacing={1} data-testid="wizard-pmh-preview">
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => void refreshPmhPreview()}
                  data-testid="wizard-preview-pmh"
                >
                  Preview verbalised PMH
                </Button>
                {pmhPreview ? (
                  <Alert severity="info" data-testid="wizard-pmh-preview-text">
                    <Typography
                      component="pre"
                      sx={{ whiteSpace: "pre-wrap", m: 0, fontFamily: "inherit" }}
                    >
                      {pmhPreview}
                    </Typography>
                  </Alert>
                ) : null}
              </Stack>
            </>
          )}
          <TextField
            label="UBRN (optional override)"
            value={agUbrn}
            onChange={(e) => setAgUbrn(e.target.value)}
            size="small"
            data-testid="wizard-ag-ubrn"
          />
          <TextField
            label="Plan definition id"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
            size="small"
            data-testid="wizard-plan-id"
          />
          <WizardAgThreadStep
            agTurnRows={agTurnRows}
            agResponseText={agResponseText}
            agRequestAttachments={agRequestAttachments}
            onAddTurn={addAgTurn}
            onUpdateTurn={updateAgTurn}
            onRemoveTurn={removeAgTurn}
            onAgResponseTextChange={setAgResponseText}
            onAddRequestAttachment={addAgRequestAttachment}
            onUpdateRequestAttachment={updateAgRequestAttachment}
            onRemoveRequestAttachment={removeAgRequestAttachment}
          />
        </Stack>
      )}

      {step === 4 && (
        <Stack spacing={2} data-testid="wizard-step-submit">
          <Typography variant="body2" color="text.secondary">
            Submitting enqueues the same event a real referral or A&amp;G
            thread would send. Nothing is fabricated -- the SBAR below is
            the genuine pipeline result.
          </Typography>
          {!run && (
            <Button
              variant="contained"
              onClick={() => void submit()}
              disabled={busy || !canSubmit}
              data-testid="wizard-submit"
            >
              {caseType === "ag" ? "Submit A&G case" : "Submit referral"}
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
            disabled={!canGoNext}
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

      <ScenarioBrainstormDrawer
        open={brainstormOpen}
        onClose={() => setBrainstormOpen(false)}
        onCreated={(ids) => {
          if (ids[0]) onCaseCreated?.(ids[0]);
          setBrainstormOpen(false);
        }}
      />
    </Box>
  );
}
