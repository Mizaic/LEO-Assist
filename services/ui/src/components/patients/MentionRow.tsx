/**
 * A single dated mention row inside the coded-entity evidence popover.
 * Term, assertion, and reading stay visible. Letter text is behind See more.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-7DE8E8ED
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import { assertionDisplayLabel } from "@/components/AssertionChip";
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

function formatDate(raw: string | null | undefined): string {
  if (!raw) return "No date recorded";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function mentionDate(mention: ConceptMention): string | null {
  return mention.observed_at || mention.source_date;
}

function readingLabel(mention: ConceptMention): string | null {
  const value = (mention.value || "").trim();
  if (!value) return null;
  const unit = (mention.unit || "").trim();
  return unit ? `${value} ${unit}` : value;
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
  const displayDate = mentionDate(mention);
  const reading = readingLabel(mention);
  return (
    <Box
      component="li"
      sx={{
        listStyle: "none",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        px: 1,
        py: 0.75,
      }}
    >
      <Stack spacing={0.25}>
        <Stack direction="row" spacing={1} alignItems="baseline" sx={{ minWidth: 0 }}>
          <Typography variant="caption" fontWeight={700}>
            {assertionDisplayLabel(mention.assertion)}
          </Typography>
          {reading ? (
            <Typography variant="body2" fontWeight={700}>
              {reading}
            </Typography>
          ) : null}
        </Stack>
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Typography
            variant="caption"
            color={displayDate ? "text.primary" : "text.secondary"}
            fontStyle={displayDate ? "normal" : "italic"}
          >
            {formatDate(displayDate)}
          </Typography>
          <Chip
            label={SOURCE_LABEL[mention.source_type] ?? mention.source_type}
            size="small"
            sx={{
              height: 16,
              fontSize: "0.625rem",
              fontWeight: 600,
              "& .MuiChip-label": { px: 0.6 },
            }}
          />
        </Stack>
        <Button
          type="button"
          size="small"
          variant="text"
          onClick={() => onToggle(mention.source_type, mention.source_id)}
          aria-expanded={expanded}
          sx={{ alignSelf: "flex-start", minHeight: 24, px: 0 }}
        >
          {expanded ? "See less" : "See more"}
        </Button>
      </Stack>
      {expanded ? (
        <MentionEvidenceBody
          detail={detail}
          detailLoading={detailLoading}
          detailError={detailError}
        />
      ) : null}
    </Box>
  );
}

function MentionEvidenceBody({
  detail,
  detailLoading,
  detailError,
}: {
  detail?: ConceptMentionDetail;
  detailLoading: boolean;
  detailError: string | null;
}) {
  if (detailLoading) {
    return (
      <Stack direction="row" spacing={1} alignItems="center" sx={{ pt: 0.5 }}>
        <CircularProgress size={12} aria-label="Loading" role="status" />
        <Typography variant="caption" color="text.secondary">
          Loading letter text...
        </Typography>
      </Stack>
    );
  }
  if (detailError && !detail) {
    return (
      <Alert severity="error" sx={{ fontSize: 11, py: 0.25, mt: 0.5 }}>
        {detailError}
      </Alert>
    );
  }
  if (!detail) return null;
  return <MentionEvidence detail={detail} />;
}

function MentionEvidence({ detail }: { detail: ConceptMentionDetail }) {
  const span = (detail.evidence || "").trim();
  const sentence = (detail.evidence_sentence || "").trim();
  if (!span && !sentence) {
    return (
      <Typography variant="caption" color="text.secondary" fontStyle="italic">
        No letter text recorded.
      </Typography>
    );
  }
  return (
    <Box sx={{ borderLeft: "3px solid", borderColor: "divider", pl: 1, py: 0.25 }}>
      {span ? (
        <Typography variant="caption" sx={{ display: "block", lineHeight: 1.5 }}>
          {span}
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
          &quot;{sentence}&quot;
        </Typography>
      ) : null}
    </Box>
  );
}
