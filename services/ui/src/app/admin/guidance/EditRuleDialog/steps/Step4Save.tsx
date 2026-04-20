/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Step 4 -- "Save your change".
 *
 * The reviewer enters a short reason and then commits. The Live
 * Preview pane on the right of the dialog shows a "Before / After"
 * pair so the reviewer can see exactly what they are saving without
 * walking back through the earlier steps.
 *
 * The reason field is the same one that used to live in the dialog
 * footer; we surface it in the canvas so it has the visual weight it
 * deserves (it is a hard requirement -- the API rejects empty
 * reasons).
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510.
 */

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { STEP_HELPERS, STEP_TITLES } from "../copy";

interface Props {
  reason: string;
  onReasonChange: (next: string) => void;
  saving?: boolean;
  reasonError?: string;
}

export default function Step4Save({
  reason,
  onReasonChange,
  saving,
  reasonError,
}: Props) {
  const reasonTooShort = reason.trim().length > 0 && reason.trim().length < 3;
  const helperText =
    reasonError ??
    (reasonTooShort
      ? "Please write a few more characters so others can see why."
      : "At least 3 characters. Saved with the change so others can see why.");

  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <Box>
        <Typography
          variant="h6"
          component="h3"
          sx={{ fontWeight: 700, fontSize: "1.05rem" }}
        >
          {STEP_TITLES.save}
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ lineHeight: 1.5, mt: 0.5 }}
        >
          {STEP_HELPERS.save}
        </Typography>
      </Box>

      <TextField
        size="small"
        label="Why are you changing this rule?"
        placeholder="For example: NICE updated the age threshold."
        helperText={helperText}
        value={reason}
        onChange={(e) => onReasonChange(e.target.value)}
        inputProps={{
          "aria-label": "Why are you changing this rule",
          minLength: 3,
        }}
        required
        multiline
        minRows={3}
        disabled={saving}
        error={Boolean(reasonError) || reasonTooShort}
      />

      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ lineHeight: 1.5 }}
      >
        Use the <strong>Save changes</strong> button at the bottom of this
        dialog when you are ready. You can still go back to any step using
        the list on the left.
      </Typography>
    </Stack>
  );
}
