"use client";

import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import type { ActionConfig } from "../config/types";
import { SUBGRAPH_IO } from "../config/subgraphs";

export function InputsTab({
  config,
  prevStepWrites,
  onChange,
}: {
  config: ActionConfig;
  prevStepWrites: string[] | null;
  onChange: (patch: Partial<ActionConfig>) => void;
}) {
  const io = SUBGRAPH_IO[config.subgraphId];
  const provided = new Set(prevStepWrites ?? []);
  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2">Inputs</Typography>
      <FormControl fullWidth size="small">
        <InputLabel>Input source</InputLabel>
        <Select value={config.inputSource} label="Input source" onChange={(e) => onChange({ inputSource: e.target.value })}>
          <MenuItem value="previous_step">Output of previous step</MenuItem>
          <MenuItem value="encounter_text">Raw encounter text</MenuItem>
          <MenuItem value="patient_graph">Patient graph</MenuItem>
          <MenuItem value="knowledge_graph">Knowledge graph</MenuItem>
        </Select>
      </FormControl>
      {io && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ display: "block", mb: 1 }}>
            REQUIRED INPUT KEYS
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {io.reads.map((k) => (
              <Chip key={k} size="small" label={k} color={provided.has(k) ? "success" : "default"} variant={provided.has(k) ? "filled" : "outlined"} sx={{ fontFamily: "monospace", fontSize: "0.68rem" }} />
            ))}
          </Stack>
        </Paper>
      )}
    </Stack>
  );
}

