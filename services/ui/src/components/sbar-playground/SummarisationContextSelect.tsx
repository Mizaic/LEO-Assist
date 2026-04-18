"use client";

/**
 * SummarisationContextSelect -- grouped dropdown over the
 * SummarisationContext enum (libs/sbar/events.py).
 *
 * Design Controls: DI-LEO-AI-231.
 *
 * Renders the 20 NHS-aligned reasons a clinician asks LEO for an SBAR
 * summary, grouped into Primary care / Acute / Statutory / Quality
 * assurance for browsability. Below the selected option we render a
 * one-sentence friendly description so a non-clinical reviewer can
 * understand what they are asking the model to do.
 *
 * Backend value strings MUST match libs/sbar/events.SummarisationContext
 * exactly (one source of truth for both ends of the wire contract).
 */

import { useMemo } from "react";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import InputLabel from "@mui/material/InputLabel";
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import Select, { type SelectChangeEvent } from "@mui/material/Select";

// Backend enum values (must mirror libs/sbar/events.SummarisationContext).
export type SummarisationContextValue =
  | "clinic_appointment_prep"
  | "annual_ltc_review"
  | "structured_medication_review"
  | "mdt_discussion"
  | "ncda"
  | "two_week_wait"
  | "hospital_admission"
  | "discharge_summary"
  | "ooh_handover"
  | "care_home_review"
  | "advance_care_planning"
  | "safeguarding_case"
  | "significant_event_review"
  | "continuing_healthcare"
  | "death_summary"
  | "insurance_dvla_report"
  | "subject_access_request"
  | "peer_review_cbd"
  | "frailty_pcsp"
  | "learning_disability_ahc";

interface ContextOption {
  value: SummarisationContextValue;
  label: string;
  description: string;
}

interface ContextGroup {
  group: string;
  options: ContextOption[];
}

// Plain-English descriptions (reading age 9-11) for each context value.
export const SUMMARISATION_CONTEXT_GROUPS: ContextGroup[] = [
  {
    group: "Primary care",
    options: [
      {
        value: "clinic_appointment_prep",
        label: "Clinic appointment prep",
        description:
          "Get ready for a booked clinic or GP appointment. What should we ask or check today?",
      },
      {
        value: "annual_ltc_review",
        label: "Long-term condition annual review",
        description:
          "Yearly check for a long-term condition like asthma, COPD, diabetes, or high blood pressure.",
      },
      {
        value: "structured_medication_review",
        label: "Structured medication review (SMR)",
        description:
          "Review the patient's medicines: are they all needed, working, and safe?",
      },
      {
        value: "mdt_discussion",
        label: "MDT (multidisciplinary team) meeting",
        description:
          "Quick case for a team meeting. What is the team being asked to decide?",
      },
      {
        value: "ncda",
        label: "National Cancer Diagnosis Audit (NCDA)",
        description:
          "Review the route to a cancer diagnosis for the national audit.",
      },
      {
        value: "two_week_wait",
        label: "Suspected cancer (2WW / Faster Diagnosis)",
        description:
          "An urgent suspected cancer referral. What does the receiving team need to act on?",
      },
      {
        value: "frailty_pcsp",
        label: "Frailty / personalised care and support plan (PCSP)",
        description:
          "Plan support for a frail patient. What matters to them and who helps?",
      },
      {
        value: "learning_disability_ahc",
        label: "Learning disability annual health check",
        description:
          "Yearly health check tailored for someone with a learning disability.",
      },
    ],
  },
  {
    group: "Acute",
    options: [
      {
        value: "hospital_admission",
        label: "Hospital admission summary",
        description:
          "Ready for an admission. Why are they coming in and what must the ward know now?",
      },
      {
        value: "discharge_summary",
        label: "Hospital discharge summary",
        description:
          "Hand over to the GP after a hospital stay. Diagnosis, treatment, and follow-up needed.",
      },
      {
        value: "ooh_handover",
        label: "Out-of-hours handover",
        description:
          "Hand over to the next clinician at night or the weekend. What still needs doing?",
      },
    ],
  },
  {
    group: "Statutory and social",
    options: [
      {
        value: "care_home_review",
        label: "Care home / housebound review",
        description:
          "Visit or review for a patient in a care home or who cannot leave the house.",
      },
      {
        value: "advance_care_planning",
        label: "Advance care planning / ReSPECT / TEP",
        description:
          "Plan for serious illness. What matters to the patient if things get worse?",
      },
      {
        value: "safeguarding_case",
        label: "Safeguarding case conference",
        description:
          "A meeting about keeping a vulnerable patient safe. Who is at risk and what is in place?",
      },
      {
        value: "continuing_healthcare",
        label: "Continuing healthcare (CHC)",
        description:
          "Funding decision for ongoing health care. What are the patient's main health needs?",
      },
      {
        value: "death_summary",
        label: "Death summary / coroner request",
        description:
          "Summary of events leading to a patient's death.",
      },
      {
        value: "insurance_dvla_report",
        label: "Insurance / DVLA / occupational report",
        description:
          "Factual report for an insurer, the DVLA, or an employer. Stick to the facts.",
      },
      {
        value: "subject_access_request",
        label: "Subject access request (SAR)",
        description:
          "A patient asked for a copy of their record. Write it in plain English so they can read it.",
      },
    ],
  },
  {
    group: "Quality assurance",
    options: [
      {
        value: "significant_event_review",
        label: "Significant event review (SEA)",
        description:
          "Review a case that did not go to plan. What happened and what can we learn?",
      },
      {
        value: "peer_review_cbd",
        label: "Peer review / Case-based discussion (CBD)",
        description:
          "Share a case with a colleague for learning. What did you decide and why?",
      },
    ],
  },
];

const VALUE_TO_OPTION = new Map<SummarisationContextValue, ContextOption>(
  SUMMARISATION_CONTEXT_GROUPS.flatMap((g) =>
    g.options.map((o) => [o.value, o] as const),
  ),
);

export function getContextDescription(
  value: SummarisationContextValue | null,
): string | null {
  if (!value) return null;
  return VALUE_TO_OPTION.get(value)?.description ?? null;
}

export interface SummarisationContextSelectProps {
  value: SummarisationContextValue | null;
  onChange: (next: SummarisationContextValue | null) => void;
  required?: boolean;
  density?: "compact" | "comfortable";
}

export function SummarisationContextSelect({
  value,
  onChange,
  required = true,
  density = "compact",
}: SummarisationContextSelectProps) {
  const description = useMemo(() => getContextDescription(value), [value]);
  const handleChange = (event: SelectChangeEvent<string>) => {
    const v = String(event.target.value);
    if (!v) {
      onChange(null);
      return;
    }
    onChange(v as SummarisationContextValue);
  };
  return (
    <FormControl
      fullWidth
      size={density === "compact" ? "small" : "medium"}
      required={required}
      data-testid="summarisation-context-select"
    >
      <InputLabel id="summarisation-context-label">
        Why are we summarising?
      </InputLabel>
      <Select
        labelId="summarisation-context-label"
        label="Why are we summarising?"
        value={value ?? ""}
        onChange={handleChange}
        inputProps={{
          "data-testid": "summarisation-context-select-input",
        }}
      >
        <MenuItem value="">
          <em>Pick a reason</em>
        </MenuItem>
        {SUMMARISATION_CONTEXT_GROUPS.flatMap((g) => [
          <ListSubheader key={`group-${g.group}`}>{g.group}</ListSubheader>,
          ...g.options.map((o) => (
            <MenuItem
              key={o.value}
              value={o.value}
              data-testid={`summarisation-context-option-${o.value}`}
            >
              {o.label}
            </MenuItem>
          )),
        ])}
      </Select>
      <FormHelperText>
        {description ??
          "Tell LEO why this summary is being made. The wording of the summary changes to match."}
      </FormHelperText>
    </FormControl>
  );
}
