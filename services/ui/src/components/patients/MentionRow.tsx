/**
 * A single dated mention row inside the coded-entity evidence popover.
 * Collapsed by default; expands in place to show the evidence sentence.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-7DE8E8ED
 */
"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import type { ConceptMention, ConceptMentionDetail } from "@/lib/patientEprApi";

const ASSERTION_LABEL: Record<string, string> = {
  present: "Present",
  historical: "Historical",
  absent: "Absent",
  refuted: "Refuted",
  possible: "Possible",
  planned: "Planned",
  hypothetical: "Hypothetical",
  family: "Family history",
  declined: "Declined",
  cancelled: "Cancelled",
};

function formatDate(raw: string | null): string {
  if (!raw) return "Date not recorded";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

interface MentionRowProps {
  mention: ConceptMention;
  expanded: boolean;
  detail?: ConceptMentionDetail;
  detailLoading: boolean;
  detailError: string | null;
  onToggle: (encounterId: string) => void;
}

export function MentionRow({
  mention,
  expanded,
  detail,
  detailLoading,
  detailError,
  onToggle,
}: MentionRowProps) {
  return (
    <Box component="li" sx={{ listStyle: "none" }}>
      <Box
        component="button"
        type="button"
        onClick={() => onToggle(mention.encounter_id)}
        aria-expanded={expanded}
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "100%",
          background: "none",
          border: "1px solid #E2E8F0",
          borderRadius: "6px",
          px: 1,
          py: 0.5,
          cursor: "pointer",
          font: "inherit",
          textAlign: "left",
        }}
      >
        <Typography variant="caption" fontWeight={600}>
          {formatDate(mention.encounter_date)}
        </Typography>
        <Stack direction="row" spacing={0.5} alignItems="center">
          {mention.assertion && (
            <Typography variant="caption" color="text.secondary">
              {ASSERTION_LABEL[mention.assertion] ?? mention.assertion}
            </Typography>
          )}
          {expanded ? (
            <ExpandLessIcon sx={{ fontSize: 16 }} />
          ) : (
            <ExpandMoreIcon sx={{ fontSize: 16 }} />
          )}
        </Stack>
      </Box>
      {expanded && (
        <Box sx={{ px: 1, py: 0.75 }}>
          {detailLoading && (
            <Typography variant="caption" color="text.secondary">
              Loading evidence...
            </Typography>
          )}
          {detailError && !detail && !detailLoading && (
            <Alert severity="error" sx={{ fontSize: 11, py: 0.25 }}>
              {detailError}
            </Alert>
          )}
          {detail && (
            <Typography
              variant="caption"
              sx={{ display: "block", fontStyle: "italic" }}
            >
              &quot;
              {detail.evidence_sentence ||
                detail.evidence ||
                "No evidence sentence recorded."}
              &quot;
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}
