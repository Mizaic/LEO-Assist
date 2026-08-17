/**
 * Atlas trace:
 *   DO: DO-5D885390
 *   DI: DI-693FFEEA
 */
"use client";

import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { color, typography } from "@leo/design-system/tokens";

import { useEditorStripStyle } from "./EditorStrip";

export function WorkflowModeBar({
  workflowMode,
  onChange,
}: {
  workflowMode: string;
  onChange: (mode: "durable_pubsub" | "legacy_in_process") => void;
}) {
  const strip = useEditorStripStyle();
  const durable = workflowMode === "durable_pubsub";
  return (
    <div style={{ ...strip, padding: 12 }} data-testid="pathway-workflow-mode">
      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
        <FormControl size="small" sx={{ minWidth: 220 }}>
          <InputLabel id="workflow-mode-label">Workflow mode</InputLabel>
          <Select
            labelId="workflow-mode-label"
            label="Workflow mode"
            value={workflowMode}
            onChange={(event) => {
              onChange(
                event.target.value === "durable_pubsub"
                  ? "durable_pubsub"
                  : "legacy_in_process",
              );
            }}
          >
            <MenuItem value="legacy_in_process">Legacy in-process</MenuItem>
            <MenuItem value="durable_pubsub">Durable pub/sub</MenuItem>
          </Select>
        </FormControl>
        <Box sx={{ flex: 1, minWidth: 280 }}>
          <Typography variant="body2" fontWeight={700} sx={{ fontFamily: typography.fontFamily.body }}>
            {durable
              ? "Edges publish the next event after a persisted stage completes."
              : "Edges pass in-memory state from one subgraph to the next."}
          </Typography>
          <Typography variant="caption" sx={{ color: color.text.secondary }}>
            Durable mode shows graph loads, persisted artefacts, idempotency, and retry metadata for each step.
          </Typography>
        </Box>
        <span
          style={{
            height: 22,
            padding: "0 10px",
            borderRadius: 999,
            background: durable ? color.brand.primary : color.surface.alt,
            color: durable ? color.brand.onBrand : color.text.primary,
            border: "1px solid " + (durable ? color.brand.primary : color.text.secondary),
            fontSize: 11,
            fontWeight: 700,
            display: "inline-flex",
            alignItems: "center",
            fontFamily: typography.fontFamily.body,
          }}
        >
          {durable ? "Durable" : "Legacy"}
        </span>
      </Stack>
    </div>
  );
}
