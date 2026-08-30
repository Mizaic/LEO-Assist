"use client";

/**
 * Workflow canvas route: /admin/workflows/[id]
 *
 * Renders full-height (no page padding) so React Flow can fill the viewport.
 * The WorkflowCanvas component owns the 3-panel layout internally.
 */

import { use } from "react";
import Box from "@mui/material/Box";
import { WorkflowCanvas } from "./WorkflowCanvas";

interface Props {
  params: Promise<{ id: string }>;
}

export default function WorkflowEditorPage({ params }: Props) {
  const { id } = use(params);

  return (
    <Box
      sx={{
        position: "fixed",
        inset: 0,
        /* Push content past the app shell sidebar width */
        left: "var(--shell-sidebar-width, 240px)",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#f0f4f8",
        zIndex: 10,
      }}
    >
      <WorkflowCanvas workflowId={id} />
    </Box>
  );
}
