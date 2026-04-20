/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A2553F87
 *   DI: DI-425CA252
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A2553F87")
 */
"use client";

import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "100vh", p: 4, textAlign: "center" }}>
          <Typography variant="h4" component="h1" sx={{ mb: 2, fontWeight: 700 }}>
            Something went wrong
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ mb: 3, maxWidth: 480 }}>
            An unexpected error occurred. Your data has not been lost. Please try again or return to the dashboard.
          </Typography>
          <Box sx={{ display: "flex", gap: 2 }}>
            <Button variant="contained" onClick={reset}>
              Try again
            </Button>
            <Button variant="outlined" href="/care/dashboard">
              Go to Dashboard
            </Button>
          </Box>
        </Box>
      </body>
    </html>
  );
}
