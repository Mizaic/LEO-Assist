/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-3AD4D385
 *   DI: DI-9DCBC4BA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3AD4D385")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import type { CoverageInfo, RunResult } from "@/lib/researchApi";

interface Props {
  result: RunResult | null;
  loading: boolean;
  error?: string | null;
}

export default function HeadlineResult({ result, loading, error }: Props) {
  if (loading) {
    return (
      <Box
        sx={{
          p: 3,
          borderRadius: 2,
          bgcolor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        <LinearProgress sx={{ mb: 2 }} />
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Running investigation...
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Box
        sx={{
          p: 3,
          borderRadius: 2,
          bgcolor: "error.light",
          border: "1px solid",
          borderColor: "error.main",
        }}
      >
        <Typography variant="body2" sx={{ color: "error.contrastText" }}>
          {error}
        </Typography>
      </Box>
    );
  }

  if (!result) return null;

  if (!result.data_available) {
    return (
      <Box
        sx={{
          p: 3,
          borderRadius: 2,
          bgcolor: "info.light",
          border: "1px solid",
          borderColor: "info.main",
        }}
      >
        <Typography variant="body2" sx={{ color: "info.contrastText" }}>
          {result.unavailable_reason ||
            "This investigation is not available yet."}
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        p: 3,
        borderRadius: 2,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Typography
        variant="body1"
        sx={{ fontWeight: 600, lineHeight: 1.5, mb: 2 }}
      >
        {result.headline}
      </Typography>
      <CoverageBadge coverage={result.coverage} />
    </Box>
  );
}

function CoverageBadge({ coverage }: { coverage: CoverageInfo }) {
  const confidenceColor =
    coverage.confidence === "high"
      ? "success"
      : coverage.confidence === "moderate"
      ? "warning"
      : "default";

  const patLabel =
    coverage.patient_count > 0
      ? `${coverage.patient_count.toLocaleString()} patient${coverage.patient_count !== 1 ? "s" : ""}`
      : null;

  const pracLabel =
    coverage.practice_count > 0
      ? `${coverage.practice_count} practice${coverage.practice_count !== 1 ? "s" : ""}`
      : null;

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 1,
      }}
    >
      <Chip
        label={coverage.confidence_note || "Coverage unknown"}
        size="small"
        color={confidenceColor as "success" | "warning" | "default"}
        variant="outlined"
        sx={{ fontSize: "0.7rem", height: 22 }}
      />
      {patLabel && (
        <Chip
          label={patLabel}
          size="small"
          variant="outlined"
          sx={{ fontSize: "0.7rem", height: 22 }}
        />
      )}
      {pracLabel && (
        <Chip
          label={pracLabel}
          size="small"
          variant="outlined"
          sx={{ fontSize: "0.7rem", height: 22 }}
        />
      )}
    </Box>
  );
}
