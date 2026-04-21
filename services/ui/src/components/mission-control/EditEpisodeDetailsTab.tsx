/**
 * EditEpisodeDetailsTab -- form for the EpisodeOfCare property fields.
 * PATCHes the manual update endpoint with only the fields the user
 * actually changed.
 *
 * Atlas trace:
 *   DO: DO-BDBEDA43, DI: DI-F4C06C92, VT: VT-79845292
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { updateEpisode } from "@/lib/missionControlApi";
import type { EpisodeUpdateBody, MissionEpisode } from "@/lib/missionControlApi";

interface Props {
  episode: MissionEpisode;
  disabled: boolean;
  onSaved: (info?: string) => void;
  onError: (message: string) => void;
}

interface FormState {
  cancer_type: string;
  cancer_stage: string;
  condition_type: string;
  referral_date: string;
  end_date: string;
  audit_notes: string;
  audit_flag: string;
}

function fromEpisode(episode: MissionEpisode): FormState {
  return {
    cancer_type: episode.cancer_type ?? "",
    cancer_stage: episode.cancer_stage ?? "",
    condition_type: episode.condition_type ?? "",
    referral_date: episode.referral_date ?? "",
    end_date: episode.end_date ?? "",
    audit_notes: episode.audit_notes ?? "",
    audit_flag: episode.audit_flag ? "true" : "",
  };
}

function buildPatch(initial: FormState, current: FormState): EpisodeUpdateBody {
  const patch: EpisodeUpdateBody = {};
  if (initial.cancer_type !== current.cancer_type) {
    patch.cancer_type = current.cancer_type || null;
  }
  if (initial.cancer_stage !== current.cancer_stage) {
    patch.cancer_stage = current.cancer_stage || null;
  }
  if (initial.condition_type !== current.condition_type) {
    patch.condition_type = current.condition_type || null;
  }
  if (initial.referral_date !== current.referral_date) {
    patch.referral_date = current.referral_date || null;
  }
  if (initial.end_date !== current.end_date) {
    patch.end_date = current.end_date || null;
  }
  if (initial.audit_notes !== current.audit_notes) {
    patch.audit_notes = current.audit_notes;
  }
  if (initial.audit_flag !== current.audit_flag) {
    patch.audit_flag = current.audit_flag || null;
  }
  return patch;
}

export default function EditEpisodeDetailsTab({
  episode,
  disabled,
  onSaved,
  onError,
}: Props) {
  const [initial] = useState<FormState>(() => fromEpisode(episode));
  const [form, setForm] = useState<FormState>(() => fromEpisode(episode));
  const [saving, setSaving] = useState(false);

  const patch = buildPatch(initial, form);
  const dirtyFieldCount = Object.keys(patch).length;
  const dirty = dirtyFieldCount > 0;

  const update = (field: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
    };

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      await updateEpisode(episode.episode_id, patch);
      onSaved(`Saved ${dirtyFieldCount} change${dirtyFieldCount === 1 ? "" : "s"}.`);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not save changes.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box component="form" noValidate onSubmit={(e) => e.preventDefault()}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Episode <strong>{episode.episode_id}</strong>. Only changed fields
        are saved. Dates re-derive automatically from attached encounters
        when you leave them blank.
      </Typography>
      <Stack spacing={2}>
        <TextField
          label="Cancer type"
          value={form.cancer_type}
          onChange={update("cancer_type")}
          disabled={disabled || saving}
          inputProps={{ "aria-label": "Cancer type" }}
          helperText="Plain English. Example: breast, lung, prostate."
        />
        <TextField
          label="Cancer stage"
          value={form.cancer_stage}
          onChange={update("cancer_stage")}
          disabled={disabled || saving}
          inputProps={{ "aria-label": "Cancer stage" }}
        />
        <TextField
          label="Condition type"
          value={form.condition_type}
          onChange={update("condition_type")}
          disabled={disabled || saving}
          inputProps={{ "aria-label": "Condition type" }}
          helperText="Defaults to cancer type when blank on the create form."
        />
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField
            label="Referral date"
            type="date"
            value={form.referral_date}
            onChange={update("referral_date")}
            disabled={disabled || saving}
            InputLabelProps={{ shrink: true }}
            inputProps={{ "aria-label": "Referral date" }}
            sx={{ flex: 1 }}
          />
          <TextField
            label="End date"
            type="date"
            value={form.end_date}
            onChange={update("end_date")}
            disabled={disabled || saving}
            InputLabelProps={{ shrink: true }}
            inputProps={{ "aria-label": "End date" }}
            sx={{ flex: 1 }}
          />
        </Stack>
        <TextField
          label="Audit notes"
          value={form.audit_notes}
          onChange={update("audit_notes")}
          disabled={disabled || saving}
          multiline
          minRows={2}
          inputProps={{ "aria-label": "Audit notes" }}
          helperText="Saved on the audit trail. Plain English, short."
        />
        <TextField
          label="Audit flag"
          value={form.audit_flag}
          onChange={update("audit_flag")}
          disabled={disabled || saving}
          inputProps={{ "aria-label": "Audit flag" }}
          helperText="Optional short tag (e.g. 'review-needed')."
        />
        <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
          <Button
            type="button"
            variant="contained"
            onClick={handleSave}
            disabled={!dirty || disabled || saving}
            data-testid="edit-episode-details-save"
            startIcon={
              saving ? <CircularProgress size={16} color="inherit" /> : null
            }
          >
            {dirty ? `Save ${dirtyFieldCount} change${dirtyFieldCount === 1 ? "" : "s"}` : "No changes"}
          </Button>
        </Box>
      </Stack>
    </Box>
  );
}
