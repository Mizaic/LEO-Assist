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
