"use client";

/**
 * Read-only ER card for Service, Organisation, and derived Scheduler.
 */

import type { ReactElement } from "react";
import { Handle, Position } from "@xyflow/react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { attributeRowKey } from "../../contextAttributes";
import type { ContextAttribute, ContextKind, WorkflowNodeData } from "../../types";

interface ContextEntityCardProps {
  data: WorkflowNodeData;
  selected: boolean;
  kind: ContextKind;
}

const KIND_LABEL: Record<ContextKind, string> = {
  service: "Service",
  organisation: "Organisation",
  scheduler: "Scheduler",
};

function accentToken(kind: ContextKind): string {
  if (kind === "organisation") return "primary.dark";
  if (kind === "scheduler") return "warning.main";
  return "info.main";
}

export function ContextEntityCard({
  data,
  selected,
  kind,
}: ContextEntityCardProps): ReactElement {
  const accent = accentToken(kind);
  return (
    <Box
      sx={{
        width: 260,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: selected ? accent : "divider",
        borderRadius: 1,
        boxShadow: selected ? 4 : 1,
        overflow: "hidden",
        cursor: "pointer",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ width: 8, height: 8 }} />
      <ContextHeader data={data} kind={kind} accent={accent} />
      <AttributeRows rows={data.attributes ?? []} />
      <Handle type="source" position={Position.Bottom} style={{ width: 8, height: 8 }} />
    </Box>
  );
}

function ContextHeader({
  data,
  kind,
  accent,
}: {
  data: WorkflowNodeData;
  kind: ContextKind;
  accent: string;
}): ReactElement {
  return (
    <Box sx={{ px: 1, py: 0.7, bgcolor: accent, color: "primary.contrastText" }}>
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
          {KIND_LABEL[kind]}
          {data.derived ? " (derived)" : ""}
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
      </Stack>
    </Box>
  );
}

function AttributeRows({ rows }: { rows: ContextAttribute[] }): ReactElement {
  return (
    <Stack>
      {rows.map((row, index) => (
        <Stack
          key={attributeRowKey(row, index)}
          direction="row"
          justifyContent="space-between"
          spacing={1}
          sx={{ px: 1, py: 0.2, borderTop: "1px solid", borderColor: "divider" }}
        >
          <Typography
            sx={{
              fontSize: "0.62rem",
              fontFamily: "monospace",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {row.name}
          </Typography>
          <Typography
            sx={{
              fontSize: "0.58rem",
              fontFamily: "monospace",
              color: "text.secondary",
              flexShrink: 0,
              maxWidth: "58%",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {row.value}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}
