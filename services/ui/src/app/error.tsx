/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A2553F87
 *   DI: DI-425CA252
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A2553F87")
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <Box sx={{ p: 5, maxWidth: 600, mx: "auto" }}>
      <Typography variant="h5" component="h1" sx={{ mb: 2, fontWeight: 700 }}>
        Something went wrong
      </Typography>
      <Alert severity="error" sx={{ mb: 3 }}>
        {error.message || "An unexpected error occurred."}
      </Alert>
      <Box sx={{ display: "flex", gap: 2 }}>
        <Button variant="contained" onClick={reset}>
          Try again
        </Button>
        <Button variant="outlined" href="/care/dashboard">
          Go to Dashboard
        </Button>
      </Box>
    </Box>
  );
}
