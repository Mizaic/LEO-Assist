"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import CodingValidationPanel from "./CodingValidationPanel";

export default function CodingValidationPage() {
  return (
    <Suspense
      fallback={
        <Stack alignItems="center" sx={{ pt: 6 }}>
          <CircularProgress size={28} />
        </Stack>
      }
    >
      <CodingValidationPanel />
    </Suspense>
  );
}
