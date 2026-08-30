"use client";

/**
 * Full I/O contract for the selected workflow step.
 */

import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  getAgentIo,
  kindLabel,
  strictnessLabel,
  type IoField,
} from "../agentIo";

interface AgentIoPanelProps {
  agentType: string;
}

export function AgentIoPanel({ agentType }: AgentIoPanelProps): ReactElement {
  const io = getAgentIo(agentType);

  return (
    <Stack spacing={1.2} aria-label="Agent inputs and outputs">
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          fontSize: "0.68rem",
          color: "text.secondary",
          textTransform: "uppercase",
          letterSpacing: 0.6,
        }}
      >
        Data contract
      </Typography>
      <Typography sx={{ fontSize: "0.72rem", color: "text.secondary" }}>
        {io.summary}
      </Typography>
      <Typography
        sx={{ fontSize: "0.66rem", fontFamily: "monospace", color: "text.secondary" }}
      >
        {io.stateName}
      </Typography>
      <Typography sx={{ fontSize: "0.66rem", color: "text.secondary" }}>
        {strictnessLabel(io.strictness)}
      </Typography>
      <FieldGroup title="Inputs" fields={io.inputs} color="primary.main" />
      <FieldGroup title="Outputs" fields={io.outputs} color="secondary.main" />
    </Stack>
  );
}

function FieldGroup({
  title,
  fields,
  color,
}: {
  title: string;
  fields: IoField[];
  color: "primary.main" | "secondary.main";
}): ReactElement {
  return (
    <Stack spacing={0.5}>
      <Typography
        sx={{
          fontSize: "0.66rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.4,
          color,
        }}
      >
        {title}
      </Typography>
      {fields.length === 0 && (
        <Typography sx={{ fontSize: "0.72rem", color: "text.secondary" }}>
          None listed.
        </Typography>
      )}
      {fields.map((field) => (
        <Box
          key={field.name}
          sx={{
            px: 0.8,
            py: 0.5,
            borderRadius: "6px",
            border: "1px solid",
            borderColor: "divider",
            bgcolor: "background.paper",
          }}
        >
          <Stack direction="row" justifyContent="space-between" spacing={1}>
            <Typography
              sx={{ fontSize: "0.72rem", fontFamily: "monospace", fontWeight: 600 }}
            >
              {field.name}
              {field.required ? " *" : ""}
            </Typography>
            <Typography sx={{ fontSize: "0.66rem", color: "text.secondary" }}>
              {kindLabel(field.kind)}
            </Typography>
          </Stack>
          {field.note && (
            <Typography sx={{ fontSize: "0.66rem", color: "text.secondary", mt: 0.2 }}>
              {field.note}
            </Typography>
          )}
        </Box>
      ))}
    </Stack>
  );
}
