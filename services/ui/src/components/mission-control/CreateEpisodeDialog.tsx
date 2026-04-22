/**
 * CreateEpisodeDialog -- "+ New episode" form launched from the
 * Mission Control patient drawer. Calls POST /analytics/episodes with
 * an optional initial encounter attachment (which the server uses to
 * re-derive the episode dates).
 *
 * Atlas trace:
 *   DO: DO-0792E2CB, DI: DI-3A19BE12
 *   Risks: R-E951555E, R-A737EE12, R-DD23FB44
 *   VT: VT-26729755 (create + audit)
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Close from "@mui/icons-material/Close";
import { createEpisode } from "@/lib/missionControlApi";
import type { EpisodeCreateBody } from "@/lib/missionControlApi";
import {
  STATUS_ACTIVE,
  STATUS_COMPLETED,
  STATUS_REVIEW,
  EPISODE_STATUS_LABELS,
} from "@/lib/episodeLifecycle";
import { MILESTONE_OPTIONS } from "./milestoneOptions";

// Restricted starting-status set for manual create. The full
// vocabulary in libs/episodes/status.py is wider, but on the manual
// create path we expose only the four engine-output values that are
// meaningful for a brand-new pathway. Closed / merged / stale_*
// statuses are written by their dedicated actions on the Edit
// dialog (Close, Merge, etc.), never by Create.
const CREATE_STATUS_OPTIONS: ReadonlyArray<{
  value: string;
  label: string;
}> = [
  { value: STATUS_REVIEW, label: `${EPISODE_STATUS_LABELS[STATUS_REVIEW]} (default)` },
  { value: STATUS_ACTIVE, label: EPISODE_STATUS_LABELS[STATUS_ACTIVE] },
  { value: STATUS_COMPLETED, label: EPISODE_STATUS_LABELS[STATUS_COMPLETED] },
];

const CURATOR_ROLES = new Set(["clinician", "qa_ra_lead", "platform_admin"]);

interface Props {
  open: boolean;
  patientId: string;
  reviewerRole: string;
  onClose: () => void;
  /** Notify the parent so it can refresh the patient's episode list. */
  onCreated: (episodeId: string) => void;
}

interface FormState {
  cancer_type: string;
  cancer_stage: string;
  condition_type: string;
  referral_date: string;
  end_date: string;
  status: string;
  audit_notes: string;
  attachInitialEncounter: boolean;
  initialEncounterId: string;
  initialMilestoneType: string;
}

const INITIAL_FORM: FormState = {
  cancer_type: "",
  cancer_stage: "",
  condition_type: "",
  referral_date: "",
  end_date: "",
  status: STATUS_REVIEW,
  audit_notes: "",
  attachInitialEncounter: false,
  initialEncounterId: "",
  initialMilestoneType: "first_presentation",
};

function buildBody(patientId: string, form: FormState): EpisodeCreateBody {
  const body: EpisodeCreateBody = {
    patient_id: patientId,
    cancer_type: form.cancer_type || null,
    cancer_stage: form.cancer_stage || null,
    condition_type: form.condition_type || null,
    referral_date: form.referral_date || null,
    end_date: form.end_date || null,
    status: form.status || STATUS_REVIEW,
    audit_notes: form.audit_notes || null,
  };
  if (form.attachInitialEncounter && form.initialEncounterId.trim()) {
    body.initial_encounter_links = [
      {
        encounter_id: form.initialEncounterId.trim(),
        milestone_type: form.initialMilestoneType,
      },
    ];
  }
  return body;
}

export default function CreateEpisodeDialog({
  open,
  patientId,
  reviewerRole,
  onClose,
  onCreated,
}: Props) {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isCurator = CURATOR_ROLES.has(reviewerRole);
  const update = (field: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const value =
        e.target instanceof HTMLInputElement && e.target.type === "checkbox"
          ? e.target.checked
          : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const handleCreate = async () => {
    if (!isCurator || saving) return;
    setSaving(true);
    setError(null);
    try {
      const body = buildBody(patientId, form);
      const res = await createEpisode(body);
      setForm(INITIAL_FORM);
      onCreated(res.episode_id);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the episode.");
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void handleCreate();
  };

  const handleClose = () => {
    if (saving) return;
    setForm(INITIAL_FORM);
    setError(null);
    onClose();
  };

  // Block backdrop and Escape dismissals -- they were being mistaken
  // for a successful create. The user must use Cancel, the X icon,
  // or a successful submit to close the dialog.
  const handleDialogClose = (
    _event: object,
    reason: "backdropClick" | "escapeKeyDown",
  ) => {
    if (reason === "backdropClick" || reason === "escapeKeyDown") return;
    handleClose();
  };

  return (
    <Dialog
      open={open}
      onClose={handleDialogClose}
      fullWidth
      maxWidth="sm"
      aria-labelledby="create-episode-dialog-title"
    >
      <DialogTitle id="create-episode-dialog-title" sx={{ pr: 6 }}>
        Create new episode
        <IconButton
          aria-label="Close create episode dialog"
          onClick={handleClose}
          disabled={saving}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <Close />
        </IconButton>
      </DialogTitle>
      <Box component="form" onSubmit={handleSubmit} noValidate>
      <DialogContent dividers>
        {!isCurator && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Your current role can only view episodes. Switch to clinician
            or QA / RA lead to create one.
          </Alert>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Creating a new episode for patient <strong>{patientId}</strong>.
          You can attach an encounter at the same time -- the episode dates
          will be re-derived from the attached encounter.
        </Typography>
        <Stack spacing={2}>
          <TextField
            label="Cancer type"
            value={form.cancer_type}
            onChange={update("cancer_type")}
            disabled={!isCurator || saving}
            inputProps={{ "aria-label": "Cancer type" }}
            helperText="Plain English. Example: breast, lung, prostate."
          />
          <TextField
            label="Cancer stage"
            value={form.cancer_stage}
            onChange={update("cancer_stage")}
            disabled={!isCurator || saving}
            inputProps={{ "aria-label": "Cancer stage" }}
          />
          <TextField
            label="Condition type"
            value={form.condition_type}
            onChange={update("condition_type")}
            disabled={!isCurator || saving}
            inputProps={{ "aria-label": "Condition type" }}
            helperText="Defaults to cancer type when blank."
          />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="Referral date"
              type="date"
              value={form.referral_date}
              onChange={update("referral_date")}
              disabled={!isCurator || saving}
              InputLabelProps={{ shrink: true }}
              inputProps={{ "aria-label": "Referral date" }}
              sx={{ flex: 1 }}
            />
            <TextField
              label="End date"
              type="date"
              value={form.end_date}
              onChange={update("end_date")}
              disabled={!isCurator || saving}
              InputLabelProps={{ shrink: true }}
              inputProps={{ "aria-label": "End date" }}
              sx={{ flex: 1 }}
            />
          </Stack>
          <TextField
            select
            label="Initial status"
            value={form.status}
            onChange={update("status")}
            disabled={!isCurator || saving}
            inputProps={{ "aria-label": "Initial status" }}
          >
            {CREATE_STATUS_OPTIONS.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>
                {opt.label}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Audit notes"
            value={form.audit_notes}
            onChange={update("audit_notes")}
            disabled={!isCurator || saving}
            multiline
            minRows={2}
            inputProps={{ "aria-label": "Audit notes" }}
            helperText="Plain English. Saved on the audit trail."
          />
          <Box sx={{ borderTop: 1, borderColor: "divider", pt: 2 }}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.attachInitialEncounter}
                  onChange={update("attachInitialEncounter")}
                  inputProps={{ "aria-label": "Attach an initial encounter" }}
                  disabled={!isCurator || saving}
                />
              }
              label="Attach an initial encounter"
            />
            {form.attachInitialEncounter && (
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mt: 1 }}>
                <TextField
                  label="Encounter ID"
                  value={form.initialEncounterId}
                  onChange={update("initialEncounterId")}
                  disabled={!isCurator || saving}
                  inputProps={{ "aria-label": "Initial encounter ID" }}
                  sx={{ flex: 2 }}
                />
                <TextField
                  select
                  label="Milestone slot"
                  value={form.initialMilestoneType}
                  onChange={update("initialMilestoneType")}
                  disabled={!isCurator || saving}
                  inputProps={{ "aria-label": "Initial milestone slot" }}
                  sx={{ flex: 1 }}
                >
                  {MILESTONE_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
            )}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={saving} type="button">
          Cancel
        </Button>
        <Button
          type="submit"
          variant="contained"
          disabled={!isCurator || saving}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : null}
          data-testid="create-episode-confirm"
        >
          {saving ? "Creating..." : "Create episode"}
        </Button>
      </DialogActions>
      </Box>
    </Dialog>
  );
}
