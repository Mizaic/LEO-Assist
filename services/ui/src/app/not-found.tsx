/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A2553F87
 *   DI: DI-425CA252
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A2553F87")
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

export default function NotFound() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", p: 4, textAlign: "center" }}>
      <Typography variant="h4" component="h1" sx={{ mb: 1, fontWeight: 700 }}>
        Page not found
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        The page you are looking for does not exist or has been moved.
      </Typography>
      <Button variant="contained" href="/care/dashboard">
        Go to Dashboard
      </Button>
    </Box>
  );
}
