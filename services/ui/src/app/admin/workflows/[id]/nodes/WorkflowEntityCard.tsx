"use client";

/**
 * Shared ER-style entity card for agent and human workflow steps.
 */

import type { ReactElement } from "react";
import { Handle, Position } from "@xyflow/react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { WorkflowNodeData, StepKind } from "../../types";
import { getAgentIo } from "../../agentIo";
import { EntityIoTable } from "../../EntityIoTable";

interface WorkflowEntityCardProps {
  data: WorkflowNodeData;
  selected: boolean;
  kind: StepKind;
}

export function WorkflowEntityCard({
  data,
  selected,
  kind,
}: WorkflowEntityCardProps): ReactElement {
  const io = getAgentIo(data.agentType);
  const accent =
    kind === "human"
      ? "secondary.main"
      : kind === "ambient"
        ? "info.main"
        : "primary.main";

  return (
    <Box
      sx={{
        width: 260,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: selected ? accent : "divider",
        borderRadius: "4px",
        boxShadow: selected ? 4 : 1,
        overflow: "hidden",
        cursor: "pointer",
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: 8, height: 8 }}
      />
      <Box
        sx={{
          px: 1,
          py: 0.7,
          bgcolor: accent,
          color: "primary.contrastText",
        }}
      >
        <Stack spacing={0.15}>
          <Typography
            sx={{
              fontSize: "0.58rem",
              fontWeight: 700,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              opacity: 0.85,
            }}
          >
            {kind === "human" ? "Human" : kind === "ambient" ? "Scheduled" : "Agent"}
          </Typography>
          <Typography
            sx={{
              fontSize: "0.76rem",
              fontWeight: 700,
              lineHeight: 1.25,
              wordBreak: "break-word",
            }}
          >
            {data.label}
          </Typography>
          <Typography sx={{ fontSize: "0.6rem", opacity: 0.85 }}>
            {data.agentType}
          </Typography>
        </Stack>
      </Box>
      <EntityIoTable inputs={io.inputs} outputs={io.outputs} />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 8, height: 8 }}
      />
    </Box>
  );
}
