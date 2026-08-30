"use client";

/**
 * ER-style attribute table for a workflow step's typed I/O.
 */

import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  CANVAS_IO_PREVIEW,
  kindLabel,
  previewFields,
  type IoField,
} from "./agentIo";

interface EntityIoTableProps {
  inputs: IoField[];
  outputs: IoField[];
}

export function EntityIoTable({
  inputs,
  outputs,
}: EntityIoTableProps): ReactElement {
  return (
    <Stack>
      <AttributeSection title="In" fields={inputs} />
      <AttributeSection title="Out" fields={outputs} />
    </Stack>
  );
}

function AttributeSection({
  title,
  fields,
}: {
  title: string;
  fields: IoField[];
}): ReactElement | null {
  if (fields.length === 0) return null;
  const shown = previewFields(fields, CANVAS_IO_PREVIEW);
  const extra = fields.length - shown.length;
  return (
    <Box sx={{ borderTop: "1px solid", borderColor: "divider" }}>
      <Typography
        sx={{
          px: 1,
          py: 0.35,
          fontSize: "0.58rem",
          fontWeight: 700,
          letterSpacing: 0.5,
          textTransform: "uppercase",
          color: "text.secondary",
          bgcolor: "action.hover",
        }}
      >
        {title}
      </Typography>
      {shown.map((field) => (
        <Stack
          key={field.name}
          direction="row"
          justifyContent="space-between"
          spacing={1}
          sx={{
            px: 1,
            py: 0.2,
            borderTop: "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography
            sx={{
              fontSize: "0.62rem",
              fontFamily: "monospace",
              fontWeight: field.required ? 700 : 500,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {field.name}
          </Typography>
          <Typography
            sx={{
              fontSize: "0.58rem",
              fontFamily: "monospace",
              color: "text.secondary",
              flexShrink: 0,
            }}
          >
            {kindLabel(field.kind)}
          </Typography>
        </Stack>
      ))}
      {extra > 0 && (
        <Typography
          sx={{
            px: 1,
            py: 0.2,
            fontSize: "0.58rem",
            color: "text.secondary",
            borderTop: "1px solid",
            borderColor: "divider",
          }}
        >
          +{extra} more
        </Typography>
      )}
    </Box>
  );
}
