"use client";

import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import type { ActionConfig, FieldMappingRow } from "../config/types";
import { SUBGRAPH_IO } from "../config/subgraphs";
import { FieldWiringPanel } from "../wiring/FieldWiringPanel";
import { useFieldMappings } from "../wiring/useFieldMappings";

export function OutputsTab({
  config,
  onRowsChange,
}: {
  config: ActionConfig;
  onRowsChange: (rows: FieldMappingRow[]) => void;
}) {
  const rows = ((config.params.field_mappings as FieldMappingRow[]) ?? []);
  const { loading } = useFieldMappings(config.promptConfigId, rows.length > 0, onRowsChange);
  const io = SUBGRAPH_IO[config.subgraphId];
  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2">Outputs</Typography>
      {io && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ display: "block", mb: 1 }}>
            PRODUCED KEYS
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {io.writes.map((k) => (
              <Chip key={k} size="small" label={k} color="primary" variant="outlined" sx={{ fontFamily: "monospace", fontSize: "0.68rem" }} />
            ))}
          </Stack>
        </Paper>
      )}
      {config.promptConfigId ? (
        loading ? (
          <Alert severity="info">Loading prompt output schema…</Alert>
        ) : (
          <FieldWiringPanel rows={rows} onRowsChange={onRowsChange} />
        )
      ) : (
        <Alert severity="info">Select a prompt in Settings to configure field-level output wiring.</Alert>
      )}
    </Stack>
  );
}

