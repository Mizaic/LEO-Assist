/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E981C7B1
 *   DI: DI-D6E5F94E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E981C7B1")
 */
"use client";

/**
 * GP consultation step for SPoA Validation Lab scenarios.
 *
 * Atlas: DI-D6E5F94E
 */

import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

interface WizardGpConsultStepProps {
  label: string;
  text: string;
  date: string;
  onLabelChange: (value: string) => void;
  onTextChange: (value: string) => void;
  onDateChange: (value: string) => void;
}

export function WizardGpConsultStep({
  label,
  text,
  date,
  onLabelChange,
  onTextChange,
  onDateChange,
}: WizardGpConsultStepProps) {
  return (
    <Stack spacing={2} data-testid="wizard-step-gp-consult">
      <Typography variant="body2" color="text.secondary">
        Record the primary-care GP consultation. This stays on the patient
        graph as context and is not submitted to the pipeline. The A&amp;G
        request or referral submission is entered in the next step.
      </Typography>
      <TextField
        label="Consultation label"
        value={label}
        onChange={(e) => onLabelChange(e.target.value)}
        data-testid="wizard-gp-consult-label"
      />
      <TextField
        label="Consultation date (YYYY-MM-DD)"
        value={date}
        onChange={(e) => onDateChange(e.target.value)}
        data-testid="wizard-gp-consult-date"
      />
      <TextField
        label="GP consultation note"
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        multiline
        minRows={6}
        required
        data-testid="wizard-gp-consult-text"
      />
    </Stack>
  );
}
