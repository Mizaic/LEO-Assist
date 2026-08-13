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
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import AssertionChip from "@/components/AssertionChip";
import type {
  ConceptMention,
  ConceptMentionDetail,
  ConceptMentionSourceType,
} from "@/lib/patientEprApi";

const SOURCE_LABEL: Record<ConceptMentionSourceType, string> = {
  encounter: "Encounter",
  document: "Document",
  communication: "Message",
};

function formatDate(raw: string | null): string {
  if (!raw) return "No date recorded";
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
  onToggle: (sourceType: ConceptMentionSourceType, sourceId: string) => void;
}

export function MentionRow({
  mention,
  expanded,
  detail,
  detailLoading,
  detailError,
  onToggle,
}: MentionRowProps) {
  const hasDate = Boolean(mention.source_date);
  return (
    <Box component="li" sx={{ listStyle: "none" }}>
      <Box
        component="button"
        type="button"
        onClick={() => onToggle(mention.source_type, mention.source_id)}
        aria-expanded={expanded}
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1,
          width: "100%",
          background: expanded ? "#F8FAFC" : "none",
          border: "1px solid",
          borderColor: expanded ? "#CBD5E1" : "#E2E8F0",
          borderRadius: "6px",
          px: 1,
          py: 0.625,
          cursor: "pointer",
          font: "inherit",
          textAlign: "left",
          transition: "background-color 120ms ease, border-color 120ms ease",
          "&:hover": { bgcolor: "#F8FAFC", borderColor: "#CBD5E1" },
        }}
      >
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
          <Typography
            variant="caption"
            fontWeight={hasDate ? 700 : 500}
            color={hasDate ? "text.primary" : "text.secondary"}
            fontStyle={hasDate ? "normal" : "italic"}
            sx={{ whiteSpace: "nowrap" }}
          >
            {formatDate(mention.source_date)}
          </Typography>
          <Chip
            label={SOURCE_LABEL[mention.source_type] ?? mention.source_type}
            size="small"
            sx={{
              height: 16,
              fontSize: "0.625rem",
              fontWeight: 600,
              bgcolor: "#EEF2F6",
              color: "#64748B",
              "& .MuiChip-label": { px: 0.6 },
            }}
          />
        </Stack>
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexShrink: 0 }}>
          <AssertionChip assertion={mention.assertion} size="small" />
          {expanded ? (
            <ExpandLessIcon sx={{ fontSize: 16, color: "text.secondary" }} />
          ) : (
            <ExpandMoreIcon sx={{ fontSize: 16, color: "text.secondary" }} />
          )}
        </Stack>
      </Box>
      {expanded && (
        <Box sx={{ px: 1, py: 0.75 }}>
          {detailLoading && (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={12} aria-label="Loading" role="status" />
              <Typography variant="caption" color="text.secondary">
                Loading evidence...
              </Typography>
            </Stack>
          )}
          {detailError && !detail && !detailLoading && (
            <Alert severity="error" sx={{ fontSize: 11, py: 0.25 }}>
              {detailError}
            </Alert>
          )}
          {detail && <MentionEvidence detail={detail} />}
        </Box>
      )}
    </Box>
  );
}

function MentionEvidence({ detail }: { detail: ConceptMentionDetail }) {
  const span = (detail.evidence || "").trim();
  const sentence = (detail.evidence_sentence || "").trim();
  if (!span && !sentence) {
    return (
      <Typography variant="caption" color="text.secondary" fontStyle="italic">
        No evidence recorded.
      </Typography>
    );
  }
  return (
    <Box sx={{ borderLeft: "3px solid #CBD5E1", pl: 1, py: 0.25 }}>
      {span ? (
        <Typography variant="caption" sx={{ display: "block", lineHeight: 1.5 }}>
          evidence: {span}
        </Typography>
      ) : null}
      {sentence ? (
        <Typography
          variant="caption"
          sx={{
            display: "block",
            fontStyle: "italic",
            color: "text.secondary",
            lineHeight: 1.5,
          }}
        >
          evidence_sentence: &quot;{sentence}&quot;
        </Typography>
      ) : null}
    </Box>
  );
}
