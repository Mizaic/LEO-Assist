"use client";

/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 *
 * Retired harness -- redirects to Validation Lab.
 * See docs/VALIDATION-LAB.md (UN-4DCE95C8).
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export default function AiSummarisationRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/validation-lab");
  }, [router]);

  return (
    <Box sx={{ p: 3 }} data-testid="ai-summarisation-retired">
      <Typography variant="h5" component="h1" sx={{ mb: 1 }}>
        Moved to Validation Lab
      </Typography>
      <Alert severity="info">
        Manual SBAR playground and scenario runs now live in Validation Lab.
        Redirecting…
      </Alert>
    </Box>
  );
}
