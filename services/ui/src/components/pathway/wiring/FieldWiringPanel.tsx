"use client";

import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import RemoveIcon from "@mui/icons-material/Remove";
import type { FieldMappingRow } from "../config/types";
import { PIPELINE_GENERATED_SENTINEL } from "../config/types";
import { WiringPill } from "./WiringPill";

interface FieldWiringPanelProps {
  titleLeft?: string;
  titleRight?: string;
  rows: FieldMappingRow[];
  onRowsChange: (rows: FieldMappingRow[]) => void;
}

export function FieldWiringPanel({
  titleLeft = "AI RETURNS",
  titleRight = "PIPELINE STATE",
  rows,
  onRowsChange,
}: FieldWiringPanelProps) {
  const aiRows = rows.filter((r) => r.llmField !== PIPELINE_GENERATED_SENTINEL);
  const updateRow = (id: string, patch: Partial<FieldMappingRow>) =>
    onRowsChange(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const addRow = () =>
    onRowsChange([
      ...rows,
      {
        id: `custom_${Date.now()}`,
        llmField: "result.field",
        type: "string",
        description: "",
        required: false,
        statePath: "",
        custom: true,
      },
    ]);
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <Paper variant="outlined" sx={{ flex: 1, p: 1.5 }}>
        <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ mb: 1, display: "block" }}>{titleLeft}</Typography>
        <Stack spacing={0.5}>
          {aiRows.map((row) => (
            <WiringPill key={row.id} label={row.llmField} type={row.type} required={row.required} connected={Boolean(row.statePath.trim())} />
          ))}
        </Stack>
      </Paper>
      <Box sx={{ width: 28, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <Stack spacing={0.5}>
          {aiRows.map((row) => (
            <Box key={row.id} sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 28 }}>
              {row.statePath.trim() ? <ArrowForwardIcon color="success" sx={{ fontSize: 16 }} /> : <RemoveIcon color="error" sx={{ fontSize: 16 }} />}
            </Box>
          ))}
        </Stack>
      </Box>
      <Paper variant="outlined" sx={{ flex: 1, p: 1.5 }}>
        <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ mb: 1, display: "block" }}>{titleRight}</Typography>
        <Stack spacing={0.5}>
          {aiRows.map((row) => (
            <WiringPill
              key={row.id}
              label={row.statePath}
              required={row.required}
              connected={Boolean(row.statePath.trim())}
              editable
              onLabelChange={(value) => updateRow(row.id, { statePath: value })}
            />
          ))}
        </Stack>
        <Button size="small" onClick={addRow} sx={{ mt: 1, fontSize: "0.72rem", textTransform: "none" }}>+ Add field</Button>
      </Paper>
    </Box>
  );
}

