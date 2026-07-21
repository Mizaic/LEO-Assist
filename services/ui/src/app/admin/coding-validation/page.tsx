"use client";

/**
 * Retired harness -- redirects to Validation Lab.
 * See docs/VALIDATION-LAB.md (UN-4DCE95C8).
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export default function CodingValidationRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/validation-lab");
  }, [router]);

  return (
    <Box sx={{ p: 3 }} data-testid="coding-validation-retired">
      <Typography variant="h5" component="h1" sx={{ mb: 1 }}>
        Moved to Validation Lab
      </Typography>
      <Alert severity="info">
        Coding validation gold editing now lives in Validation Lab. Redirecting…
      </Alert>
    </Box>
  );
}
