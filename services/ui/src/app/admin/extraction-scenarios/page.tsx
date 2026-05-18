/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-1B3B5375, DI-B492CAFD
 *   DO: DO-416BA91D
 *   Risk: R-80E8BD96
 *   VT: VT-24D7A846
 *   VAL-87173594  phrase-level F1 validation
 *   VT-29880CC8   extraction scenario verification
 */
"use client";

import { Suspense } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import ExtractionScenarioPanel from "./ExtractionScenarioPanel";

export default function ExtractionScenariosPage() {
  return (
    <Suspense
      fallback={
        <Stack alignItems="center" sx={{ pt: 6 }}>
          <CircularProgress size={28} />
        </Stack>
      }
    >
      <ExtractionScenarioPanel />
    </Suspense>
  );
}
