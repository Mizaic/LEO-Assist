"use client";

import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Typography from "@mui/material/Typography";
import { SUBGRAPH_OPTIONS } from "../config/subgraphs";
import type { ActionConfig } from "../config/types";

export function OverviewTab({
  config,
  onChange,
}: {
  config: ActionConfig;
  onChange: (patch: Partial<ActionConfig>) => void;
}) {
  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2">Node Overview</Typography>
      <FormControl fullWidth size="small">
        <InputLabel>Step type</InputLabel>
        <Select
          value={config.subgraphId}
          label="Step type"
          onChange={(e) => {
            const selected = SUBGRAPH_OPTIONS.find((s) => s.id === e.target.value);
            onChange({
              subgraphId: e.target.value,
              label: config.label || selected?.label || "",
              description: config.description || selected?.description || "",
            });
          }}
        >
          {SUBGRAPH_OPTIONS.map((s) => (
            <MenuItem key={s.id} value={s.id}>{s.label}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <TextField label="Display name" size="small" fullWidth value={config.label} onChange={(e) => onChange({ label: e.target.value })} />
      <TextField label="Description" size="small" fullWidth multiline minRows={2} value={config.description} onChange={(e) => onChange({ description: e.target.value })} />
    </Stack>
  );
}

