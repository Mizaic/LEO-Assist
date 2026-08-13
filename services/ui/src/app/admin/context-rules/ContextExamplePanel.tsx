/**
 * With / without worked example for a Context Rule category.
 */
"use client";

import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { ContextWorkedExample } from "./types";

function ExampleCard({
  title,
  body,
  tone,
}: {
  title: string;
  body: string;
  tone: "warn" | "ok";
}) {
  const border = tone === "ok" ? "#A7F3D0" : "#FECACA";
  const bg = tone === "ok" ? "#F0FDF4" : "#FEF2F2";
  return (
    <Paper
      variant="outlined"
      sx={{ p: 1.5, borderRadius: "10px", borderColor: border, bgcolor: bg, flex: 1, minWidth: 0 }}
    >
      <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>
        {title}
      </Typography>
      <Typography variant="body2">{body}</Typography>
    </Paper>
  );
}

export default function ContextExamplePanel({ example }: { example: ContextWorkedExample }) {
  return (
    <Stack spacing={1.5} sx={{ height: "100%" }}>
      <Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          Worked example
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Same category story. The sample note follows the phrase you pick.
        </Typography>
      </Box>
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: "10px", bgcolor: "#FFFFFF" }}>
        <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>
          What this does to the data
        </Typography>
        <Typography variant="body2">{example.dataChange}</Typography>
      </Paper>
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: "10px", bgcolor: "#FFFFFF" }}>
        <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>
          Sample note
        </Typography>
        <Typography variant="body2" sx={{ fontStyle: "italic" }}>
          {example.note}
        </Typography>
      </Paper>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ flex: 1 }}>
        <ExampleCard title="Without this rule" body={example.withoutGuard} tone="warn" />
        <ExampleCard title="With this rule" body={example.withGuard} tone="ok" />
      </Stack>
    </Stack>
  );
}
