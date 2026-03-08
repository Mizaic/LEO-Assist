"use client";

import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import type { ActionConfig } from "../config/types";

export function SettingsTab({
  config,
  onChange,
}: {
  config: ActionConfig;
  onChange: (patch: Partial<ActionConfig>) => void;
}) {
  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2">Settings</Typography>
      <FormControl fullWidth size="small">
        <InputLabel>Max retries</InputLabel>
        <Select value={String(config.maxRetries)} label="Max retries" onChange={(e) => onChange({ maxRetries: Number(e.target.value) })}>
          {[0, 1, 2, 3, 5].map((n) => <MenuItem key={n} value={String(n)}>{n}</MenuItem>)}
        </Select>
      </FormControl>
      <TextField label="Temperature" size="small" type="number" inputProps={{ min: 0, max: 1, step: 0.1 }} value={config.temperature} onChange={(e) => onChange({ temperature: Number(e.target.value) })} />
      <TextField label="Prompt config ID" size="small" value={config.promptConfigId} onChange={(e) => onChange({ promptConfigId: e.target.value })} />
      <TextField label="Model preset ID" size="small" value={config.modelPresetId} onChange={(e) => onChange({ modelPresetId: e.target.value })} />
    </Stack>
  );
}

