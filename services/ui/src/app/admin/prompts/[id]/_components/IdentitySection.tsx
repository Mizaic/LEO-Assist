"use client";

/**
 * Name + description + verification toggle for the AI Instructions editor.
 * Extracted from prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

interface IdentitySectionProps {
  name: string;
  description: string;
  verification: boolean;
  onNameChange: (next: string) => void;
  onDescriptionChange: (next: string) => void;
  onVerificationChange: (next: boolean) => void;
}

export function IdentitySection({
  name,
  description,
  verification,
  onNameChange,
  onDescriptionChange,
  onVerificationChange,
}: IdentitySectionProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 2, borderRadius: 2 }}>
      <Stack spacing={1.5}>
        <TextField
          fullWidth
          size="small"
          label="Name"
          placeholder="e.g. Standard clinical coder, Referral letter extractor"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
        />
        <TextField
          fullWidth
          size="small"
          label="What is this for?"
          multiline
          rows={2}
          placeholder="A plain English summary of what these instructions do -- shown on the cards page."
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
        />
        <FormControlLabel
          control={
            <Switch
              checked={verification}
              onChange={(e) => onVerificationChange(e.target.checked)}
              color="success"
              size="small"
            />
          }
          label={
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <Typography variant="body2">Double-check results</Typography>
              <Tooltip title="When on, a second AI check runs after the first to confirm accuracy before saving.">
                <InfoOutlinedIcon
                  sx={{ fontSize: 15, color: "text.disabled" }}
                />
              </Tooltip>
              {verification && (
                <Chip
                  size="small"
                  label="On"
                  color="success"
                  icon={
                    <CheckCircleOutlineIcon
                      sx={{ fontSize: "13px !important" }}
                    />
                  }
                />
              )}
            </Stack>
          }
        />
      </Stack>
    </Paper>
  );
}
