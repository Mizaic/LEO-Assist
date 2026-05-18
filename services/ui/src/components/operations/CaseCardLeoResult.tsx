/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { AskLeoSmartResult } from "@/lib/types";

type LeoStep = "idle" | "loading" | "done" | "error";

interface Props {
  step: LeoStep;
  result: AskLeoSmartResult | null;
  error: string;
}

export default function CaseCardLeoResult({ step, result, error }: Props) {
  if (step === "loading") {
    return (
      <Stack
        direction="row"
        alignItems="center"
        gap={1}
        sx={{ mb: 1.5 }}
      >
        <CircularProgress aria-label="Loading" size={14} />
        <Typography variant="body2" color="text.secondary">
          LEO is reading the encounter context...
        </Typography>
      </Stack>
    );
  }

  if (step === "error") {
    return (
      <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>
        {error}
      </Alert>
    );
  }

  if (step !== "done" || !result) return null;

  const leoMatch = result.matched_candidate ?? null;

  return (
    <Box
      sx={{
        mb: 1.5,
        p: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        bgcolor: "background.paper",
      }}
    >
      {result.alternative_query_used && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mb: 0.5 }}
        >
          Also searched: &quot;{result.alternative_query_used}&quot;
        </Typography>
      )}
      {result.is_ambiguous || !leoMatch ? (
        <Alert severity="info" sx={{ py: 0.25, mb: 1 }}>
          <Typography variant="caption">
            {result.reason ||
              "LEO could not determine the correct code from this context. Please search manually."}
          </Typography>
        </Alert>
      ) : (
        <LeoMatchDisplay
          term={leoMatch.term}
          conceptId={leoMatch.snomed_concept_id}
          assertion={result.assertion ?? null}
          reason={result.reason ?? ""}
        />
      )}
    </Box>
  );
}

interface LeoMatchDisplayProps {
  term: string;
  conceptId: string;
  assertion: string | null;
  reason: string;
}

function LeoMatchDisplay({
  term,
  conceptId,
  assertion,
  reason,
}: LeoMatchDisplayProps) {
  const showAssertionChip = Boolean(assertion) && assertion !== "present";
  return (
    <>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 0.75 }}
      >
        {reason}
      </Typography>
      <Box
        sx={{
          p: 1,
          bgcolor: "action.hover",
          borderRadius: 1,
          mb: 0.75,
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          gap={1}
          flexWrap="wrap"
          sx={{ mb: 0.5 }}
        >
          <Typography variant="body2" fontWeight={600}>
            {term}
          </Typography>
          {showAssertionChip && (
            <Tooltip
              title={`LEO: code the procedure with assertion '${assertion}' -- it will show as ${assertion} in the patient timeline`}
            >
              <Chip
                label={assertion}
                size="small"
                color={assertion === "declined" ? "warning" : "default"}
                variant="filled"
                sx={{ fontWeight: 600, fontSize: "0.7rem" }}
              />
            </Tooltip>
          )}
        </Stack>
        <Stack
          direction="row"
          alignItems="center"
          gap={1}
          sx={{ mt: 0.25 }}
        >
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ fontFamily: "monospace", flexGrow: 1 }}
          >
            SNOMED: {conceptId}
          </Typography>
          <Tooltip title="LEO confidence">
            <Box sx={{ width: 40, flexShrink: 0 }}>
              <LinearProgress
                variant="determinate"
                value={90}
                color="success"
                sx={{ height: 4, borderRadius: 2 }}
              />
            </Box>
          </Tooltip>
          <Typography variant="caption" color="text.secondary">
            90%
          </Typography>
        </Stack>
      </Box>
    </>
  );
}
