"use client";

import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import type { ActionConfig } from "../config/types";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1 }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="caption" fontWeight={600} sx={{ textAlign: "right" }}>{value}</Typography>
    </Box>
  );
}

export function ReviewTab({ config }: { config: ActionConfig }) {
  const mappingCount = Array.isArray(config.params.field_mappings) ? (config.params.field_mappings as unknown[]).length : 0;
  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2">Review</Typography>
      <Paper variant="outlined" sx={{ p: 1.5 }}>
        <Stack spacing={0.75}>
          <Row label="Node type" value={config.nodeType || "action"} />
          <Row label="Subgraph" value={config.subgraphId || "—"} />
          <Row label="Input source" value={config.inputSource} />
          <Row label="Output target" value={config.outputTarget} />
          <Row label="Prompt" value={config.promptConfigId || "—"} />
          <Row label="Model preset" value={config.modelPresetId || "—"} />
          <Row label="Temperature" value={config.temperature.toFixed(1)} />
          <Row label="Field mappings" value={String(mappingCount)} />
        </Stack>
      </Paper>
    </Stack>
  );
}

