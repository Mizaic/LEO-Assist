"use client";

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
 *
 * Retired harness -- redirects to Validation Lab.
 * See docs/VALIDATION-LAB.md (UN-4DCE95C8).
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export default function ExtractionScenariosRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/validation-lab");
  }, [router]);

  return (
    <Box sx={{ p: 3 }} data-testid="extraction-scenarios-retired">
      <Typography variant="h5" component="h1" sx={{ mb: 1 }}>
        Moved to Validation Lab
      </Typography>
      <Alert severity="info">
        Extraction scenario validation now lives in Validation Lab. Redirecting…
      </Alert>
    </Box>
  );
}
