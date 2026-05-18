/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import HelpPopover from "@/components/ui/HelpPopover";
import { SUPPRESS_HELP } from "./codingReviewCopy";

interface Props {
  entityText: string;
  warning: string | null | undefined;
  warningIsSafety: boolean;
  contextPhrase: string;
  onContextPhraseChange: (value: string) => void;
  phraseSource: "leo" | "user" | "none";
  requirePhrase: boolean;
  suppressing: boolean;
  suppressError: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function CaseCardSuppressForm({
  entityText,
  warning,
  warningIsSafety,
  contextPhrase,
  onContextPhraseChange,
  phraseSource,
  requirePhrase,
  suppressing,
  suppressError,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <Box
      sx={{
        mt: 1,
        mb: 1.5,
        p: 1.5,
        border: "1px solid",
        borderColor: warningIsSafety ? "error.main" : "warning.main",
        borderRadius: 1,
        ...(warningIsSafety && { bgcolor: "rgba(220, 38, 38, 0.04)" }),
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 1 }}
      >
        <SuppressBanner
          entityText={entityText}
          warning={warning}
          warningIsSafety={warningIsSafety}
        />
        <HelpPopover
          title={SUPPRESS_HELP.title}
          body={SUPPRESS_HELP.body}
          triggerLabel="What does suppress do?"
        />
      </Stack>
      <Stack
        direction="row"
        spacing={1}
        alignItems="flex-start"
        flexWrap="wrap"
      >
        <TextField
          size="small"
          placeholder="Type a phrase from the encounter text"
          label="Context phrase"
          value={contextPhrase}
          onChange={(e) => onContextPhraseChange(e.target.value)}
          helperText={
            phraseSource === "leo"
              ? "LEO suggested this -- edit to narrow the rule further if needed"
              : undefined
          }
          FormHelperTextProps={{ sx: { color: "info.main" } }}
          required={requirePhrase}
          sx={{ flex: 1, minWidth: 200 }}
        />
        <Button
          size="small"
          variant="contained"
          color="warning"
          onClick={onConfirm}
          disabled={
            suppressing || (requirePhrase && contextPhrase.trim() === "")
          }
          startIcon={
            suppressing ? (
              <CircularProgress
                aria-label="Loading"
                size={14}
                color="inherit"
              />
            ) : undefined
          }
        >
          {suppressing ? "Suppressing..." : "Confirm suppress"}
        </Button>
        <Button size="small" variant="text" onClick={onCancel}>
          Cancel
        </Button>
      </Stack>
      {suppressError && (
        <Typography
          variant="caption"
          color="error"
          sx={{ display: "block", mt: 0.5 }}
        >
          {suppressError}
        </Typography>
      )}
    </Box>
  );
}

interface BannerProps {
  entityText: string;
  warning: string | null | undefined;
  warningIsSafety: boolean;
}

function SuppressBanner({ entityText, warning, warningIsSafety }: BannerProps) {
  if (warning && warningIsSafety) {
    return (
      <Typography
        variant="caption"
        color="error.main"
        sx={{ display: "block" }}
      >
        This entity was incorrectly extracted as a diagnosis from a lab
        value. Suppressing will prevent this false positive in future
        pipeline runs. <strong>A context phrase is required</strong> so only
        this specific context is suppressed, not every mention of &apos;
        {entityText}&apos;. LEO has suggested a phrase below -- edit it if
        needed.
      </Typography>
    );
  }
  if (warning) {
    return (
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block" }}
      >
        This will suppress &apos;{entityText}&apos; in future pipeline runs.{" "}
        <strong>A context phrase is required</strong> so only this specific
        context is suppressed, not every mention of &apos;{entityText}&apos;.
        LEO has suggested a phrase below -- edit it if needed.
      </Typography>
    );
  }
  return (
    <Typography
      variant="caption"
      color="text.secondary"
      sx={{ display: "block" }}
    >
      This will suppress &apos;{entityText}&apos; in future pipeline runs. Add
      a context phrase to make the rule narrower (recommended for short
      terms).
    </Typography>
  );
}
