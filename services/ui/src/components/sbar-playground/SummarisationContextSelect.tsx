/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

/**
 * SummarisationContextSelect -- card-grid picker dialog over the
 * SummarisationContext enum (libs/sbar/events.py).
 *
 * Design Controls: DI-LEO-AI-231 (extended), DI-LEO-AI-507.
 *
 * Surfaces the 34 NHS-aligned reasons a clinician asks LEO for an SBAR
 * summary as a button that opens a Dialog. Inside the dialog a
 * search box filters across labels and descriptions, and the options
 * are laid out as a grid of selectable cards grouped under section
 * headers (Primary care / Secondary care / Statutory and social /
 * Quality assurance). Each card shows the friendly label and a one-
 * sentence description so a non-clinical reviewer can understand
 * what they are asking the model to do without scrolling through a
 * dropdown.
 *
 * Backend value strings MUST match libs/sbar/events.SummarisationContext
 * exactly (one source of truth for both ends of the wire contract).
 * The framing snippet that the orchestrator prepends to the Situation
 * prompt for each context is held in a :PromptConfig node named
 * `sbar_situation_context_<value>` so platform admins can tune the
 * wording in /admin/knowledge?tab=ai-instructions without an
 * engineering deploy (DI-LEO-AI-507).
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CheckCircleIcon from "@mui/icons-material/CheckCircleRounded";
import ClearIcon from "@mui/icons-material/CloseRounded";
import SearchIcon from "@mui/icons-material/SearchRounded";

// Backend enum values (must mirror libs/sbar/events.SummarisationContext).
export type SummarisationContextValue =
  // Primary care
  | "clinic_appointment_prep"
  | "annual_ltc_review"
  | "structured_medication_review"
  | "mdt_discussion"
  | "ncda"
  | "two_week_wait"
  | "referral_assessment"
  | "frailty_pcsp"
  | "learning_disability_ahc"
  // Secondary care
  | "hospital_admission"
  | "discharge_summary"
  | "ooh_handover"
  | "outpatient_new_clinic"
  | "outpatient_followup_clinic"
  | "mdt_specialty"
  | "pre_op_assessment"
  | "procedure_note"
  | "ward_round_progress"
  | "ed_handover"
  | "comprehensive_geriatric_assessment"
  | "tertiary_referral"
  | "specialty_letter_to_gp"
  | "chemotherapy_consent"
  | "palliative_care_mdt"
  // Statutory and social
  | "care_home_review"
  | "advance_care_planning"
  | "safeguarding_case"
  | "continuing_healthcare"
  | "death_summary"
  | "insurance_dvla_report"
  | "subject_access_request"
  | "best_interests_dols"
  | "mental_health_tribunal"
  // Quality assurance
  | "significant_event_review"
  | "peer_review_cbd";

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
        label: "MDT prep (primary care)",
        description:
          "Quick case for a primary-care team meeting. What is the team being asked to decide?",
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
        value: "referral_assessment",
        label: "Referral assessment triage",
        description:
          "Read a referral letter. Name urgency, specialty or test, and the main clinical trigger only if the letter says them. Do not assume two-week-wait.",
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
    group: "Secondary care",
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
      {
        value: "outpatient_new_clinic",
        label: "Outpatient new clinic letter",
        description:
          "First specialist clinic visit. What does the specialist need to know and decide today?",
      },
      {
        value: "outpatient_followup_clinic",
        label: "Outpatient follow-up clinic letter",
        description:
          "Follow-up clinic visit. How are things since last time and what is the next step?",
      },
      {
        value: "mdt_specialty",
        label: "Specialty MDT (cancer / surgical / neuro)",
        description:
          "Cancer, surgical, or neuro MDT. What does the team need to decide for this case?",
      },
      {
        value: "pre_op_assessment",
        label: "Pre-operative assessment",
        description:
          "Getting ready for an operation. Are they fit for surgery and what needs doing first?",
      },
      {
        value: "procedure_note",
        label: "Operation / procedure note summary",
        description:
          "Summary after an operation or procedure. What was done, what was found, and what next?",
      },
      {
        value: "ward_round_progress",
        label: "Ward round / inpatient progress note",
        description:
          "Daily ward round update. What is going on today and what is the plan?",
      },
      {
        value: "ed_handover",
        label: "Emergency Department triage / handover",
        description:
          "Handing over from A&E. What did A&E find and what does the next team need to do?",
      },
      {
        value: "comprehensive_geriatric_assessment",
        label: "Comprehensive Geriatric Assessment (CGA)",
        description:
          "Full review for an older patient. Health, ability to cope, social support, and mood.",
      },
      {
        value: "tertiary_referral",
        label: "Tertiary referral letter",
        description:
          "Sending to a more specialist hospital. Why we cannot manage locally and how urgent.",
      },
      {
        value: "specialty_letter_to_gp",
        label: "Specialty clinic letter back to GP",
        description:
          "Letter from the specialist back to the GP after clinic. Outcome and what the GP should do.",
      },
      {
        value: "chemotherapy_consent",
        label: "Chemotherapy / SACT consent",
        description:
          "Talking through cancer treatment. What is the plan, the risks, and what success looks like.",
      },
      {
        value: "palliative_care_mdt",
        label: "Palliative care MDT / hospice referral",
        description:
          "Palliative care meeting or hospice referral. Symptoms, plans, and support at end of life.",
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
      {
        value: "best_interests_dols",
        label: "Best Interests / DoLS meeting",
        description:
          "Meeting about a decision for someone who cannot decide for themselves. What is in their best interest?",
      },
      {
        value: "mental_health_tribunal",
        label: "Mental Health Act tribunal report",
        description:
          "Report for a Mental Health Act tribunal. The illness, risk, treatment, and reason for detention.",
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

const HELPER_DEFAULT =
  "Tell LEO why this summary is being made. The wording of the summary changes to match.";

function normalise(text: string): string {
  return text.toLowerCase().trim();
}

function filterGroups(query: string): ContextGroup[] {
  const q = normalise(query);
  if (!q) return SUMMARISATION_CONTEXT_GROUPS;
  return SUMMARISATION_CONTEXT_GROUPS.map((g) => ({
    group: g.group,
    options: g.options.filter((o) => {
      const haystack = `${o.label} ${o.description} ${o.value}`.toLowerCase();
      return haystack.includes(q);
    }),
  })).filter((g) => g.options.length > 0);
}

export function SummarisationContextSelect({
  value,
  onChange,
  required = true,
  density = "compact",
}: SummarisationContextSelectProps) {
  const selected = useMemo(
    () => (value ? VALUE_TO_OPTION.get(value) ?? null : null),
    [value],
  );
  const description = selected?.description ?? null;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const visibleGroups = useMemo(() => filterGroups(query), [query]);
  const totalVisible = visibleGroups.reduce(
    (sum, g) => sum + g.options.length,
    0,
  );

  const handleOpen = () => {
    setQuery("");
    setOpen(true);
  };
  const handleClose = () => setOpen(false);
  const handlePick = (next: SummarisationContextValue) => {
    onChange(next);
    setOpen(false);
  };
  const handleClear = () => onChange(null);

  const buttonSize = density === "compact" ? "small" : "medium";

  return (
    <Box data-testid="summarisation-context-select">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <Button
          variant={selected ? "outlined" : "contained"}
          color={selected ? "primary" : "primary"}
          size={buttonSize}
          onClick={handleOpen}
          data-testid="summarisation-context-open"
          aria-haspopup="dialog"
          aria-required={required}
          sx={{ textTransform: "none", justifyContent: "flex-start" }}
        >
          {selected ? selected.label : "Pick a reason"}
        </Button>
        {selected && (
          <IconButton
            size="small"
            onClick={handleClear}
            aria-label="Clear reason"
            data-testid="summarisation-context-clear"
          >
            <ClearIcon fontSize="small" />
          </IconButton>
        )}
      </Stack>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mt: 0.75 }}
        data-testid="summarisation-context-helper"
      >
        {description ?? HELPER_DEFAULT}
      </Typography>

      <Dialog
        open={open}
        onClose={handleClose}
        fullWidth
        maxWidth="lg"
        aria-labelledby="summarisation-context-dialog-title"
        data-testid="summarisation-context-dialog"
      >
        <DialogTitle id="summarisation-context-dialog-title">
          Why are we summarising?
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Pick the reason that matches the situation. The wording of
              the summary changes to match.
            </Typography>
            <TextField
              autoFocus
              fullWidth
              size="small"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search reasons (e.g. discharge, MDT, safeguarding)"
              aria-label="Search reasons"
              inputProps={{
                "data-testid": "summarisation-context-search",
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              }}
            />
            {totalVisible === 0 ? (
              <Box
                sx={{
                  p: 3,
                  textAlign: "center",
                  border: "1px dashed",
                  borderColor: "divider",
                  borderRadius: 1.5,
                }}
                data-testid="summarisation-context-no-match"
              >
                <Typography variant="body2" color="text.secondary">
                  No reasons match &quot;{query}&quot;. Try a shorter word or
                  clear the search.
                </Typography>
              </Box>
            ) : (
              <Stack spacing={3}>
                {visibleGroups.map((g) => (
                  <Box
                    key={g.group}
                    data-testid={`summarisation-context-group-${g.group
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, "-")}`}
                  >
                    <Typography
                      variant="overline"
                      color="text.secondary"
                      sx={{
                        display: "block",
                        mb: 1,
                        letterSpacing: 0.6,
                        fontWeight: 600,
                      }}
                    >
                      {g.group}
                    </Typography>
                    <Box
                      sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: {
                          xs: "1fr",
                          sm: "repeat(2, 1fr)",
                          md: "repeat(3, 1fr)",
                        },
                      }}
                    >
                      {g.options.map((o) => {
                        const isSelected = value === o.value;
                        return (
                          <ButtonBase
                            key={o.value}
                            onClick={() => handlePick(o.value)}
                            data-testid={`summarisation-context-option-${o.value}`}
                            aria-pressed={isSelected}
                            sx={{
                              display: "block",
                              textAlign: "left",
                              p: 1.75,
                              borderRadius: 1.5,
                              border: "1px solid",
                              borderColor: isSelected
                                ? "primary.main"
                                : "divider",
                              backgroundColor: isSelected
                                ? "primary.50"
                                : "background.paper",
                              transition:
                                "border-color 120ms ease, background-color 120ms ease, box-shadow 120ms ease",
                              minHeight: 96,
                              "&:hover": {
                                borderColor: "primary.main",
                                boxShadow:
                                  "0 1px 2px rgba(15,23,42,0.04), 0 4px 12px rgba(15,23,42,0.06)",
                              },
                              "&:focus-visible": {
                                outline: "2px solid",
                                outlineColor: "primary.main",
                                outlineOffset: 2,
                              },
                            }}
                          >
                            <Stack spacing={0.5}>
                              <Stack
                                direction="row"
                                spacing={1}
                                alignItems="flex-start"
                                justifyContent="space-between"
                              >
                                <Typography
                                  variant="subtitle2"
                                  sx={{ fontWeight: 600, lineHeight: 1.3 }}
                                >
                                  {o.label}
                                </Typography>
                                {isSelected && (
                                  <CheckCircleIcon
                                    color="primary"
                                    fontSize="small"
                                    aria-hidden="true"
                                  />
                                )}
                              </Stack>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ lineHeight: 1.4 }}
                              >
                                {o.description}
                              </Typography>
                            </Stack>
                          </ButtonBase>
                        );
                      })}
                    </Box>
                  </Box>
                ))}
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={handleClose}
            data-testid="summarisation-context-cancel"
          >
            Cancel
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
