"use client";

// -- PathwayLoadError ---------------------------------------------------------
// Surfaces a failed `GET /fhir/PlanDefinition/{id}` so the user sees an
// actionable error instead of an empty canvas. The original orchestrator
// silently swallowed load failures with `.catch(() => {})`, which left
// users staring at a blank editor with no feedback.
//
// Stateless / prop-driven: the parent owns the error, the parent owns the
// retry callback. The component is purely presentational so it can be unit
// tested with no fetch / API mocks.

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import RefreshIcon from "@mui/icons-material/Refresh";

export interface PathwayLoadErrorProps {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}

export function PathwayLoadError({
  message,
  onRetry,
  onDismiss,
}: PathwayLoadErrorProps) {
  return (
    <Box
      role="alert"
      data-testid="pathway-load-error"
      sx={{
        mx: 2,
        mt: 1,
        p: 2,
        borderRadius: 2,
        border: "1px solid",
        borderColor: "error.light",
        bgcolor: "error.50",
        display: "flex",
        gap: 1.5,
        alignItems: "flex-start",
      }}
    >
      <ErrorOutlineIcon sx={{ color: "error.main", mt: 0.25 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="subtitle2" fontWeight={700} color="error.main">
          We could not load this pathway
        </Typography>
        <Typography variant="caption" color="text.secondary" component="p">
          {message}
        </Typography>
      </Box>
      <Stack direction="row" spacing={1}>
        {onRetry ? (
          <Button
            size="small"
            variant="outlined"
            color="error"
            startIcon={<RefreshIcon />}
            onClick={onRetry}
            sx={{ textTransform: "none" }}
          >
            Try again
          </Button>
        ) : null}
        {onDismiss ? (
          <Button
            size="small"
            variant="text"
            color="inherit"
            onClick={onDismiss}
            sx={{ textTransform: "none" }}
          >
            Dismiss
          </Button>
        ) : null}
      </Stack>
    </Box>
  );
}
