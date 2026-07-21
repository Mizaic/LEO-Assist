/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import LabResultsPanel from "./LabResultsPanel";

export default function LabResultsPage() {
  return (
    <Suspense
      fallback={
        <Stack alignItems="center" sx={{ pt: 6 }}>
          <CircularProgress size={28} />
        </Stack>
      }
    >
      <LabResultsPanel />
    </Suspense>
  );
}
