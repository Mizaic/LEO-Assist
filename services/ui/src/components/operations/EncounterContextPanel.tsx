"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { getTerminologyConfidenceLabel } from "@/lib/terminologyConfidence";
import { LABEL_COLORS, type SiblingEntity } from "./codingReviewUtils";

interface Props {
  siblings?: SiblingEntity[];
  currentReviewId: string;
}

export default function EncounterContextPanel({
  siblings,
  currentReviewId,
}: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!siblings || siblings.length === 0) return null;

  const others = siblings.filter((s) => s.review_id !== currentReviewId);
  if (others.length === 0) return null;

  return (
    <Box sx={{ mb: 1.5 }}>
      <Button
        size="small"
        variant="outlined"
        onClick={() => setExpanded((p) => !p)}
        endIcon={
          expanded ? (
            <ExpandLessIcon fontSize="small" />
          ) : (
            <ExpandMoreIcon fontSize="small" />
          )
        }
        sx={{
          textTransform: "none",
          fontWeight: 500,
          color: "text.primary",
          borderColor: "divider",
          px: 1,
          "&:hover": {
            borderColor: "text.secondary",
            bgcolor: "action.hover",
          },
        }}
      >
        {expanded
          ? "Hide other items from this note"
          : `Show ${others.length} other item${others.length === 1 ? "" : "s"} from this note`}
      </Button>
      {expanded && (
        <Box
          sx={{
            mt: 0.5,
            pl: 1,
            borderLeft: "2px solid",
            borderColor: "divider",
          }}
        >
          {others.map((s) => (
            <SiblingRow key={s.review_id} sibling={s} />
          ))}
        </Box>
      )}
    </Box>
  );
}

function SiblingRow({ sibling }: { sibling: SiblingEntity }) {
  const color = LABEL_COLORS[sibling.entity_label] || "#64748b";
  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      sx={{ py: 0.3 }}
    >
      <Chip
        label={sibling.entity_label.replace(/_/g, " ")}
        size="small"
        sx={{
          bgcolor: color,
          color: "#fff",
          fontSize: "0.65rem",
          height: 18,
          minWidth: 60,
        }}
      />
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {sibling.entity_text}
      </Typography>
      {sibling.resolved && sibling.resolved_term ? (
        <Chip
          label={sibling.resolved_term}
          size="small"
          color="success"
          variant="outlined"
          sx={{ fontSize: "0.7rem", height: 20 }}
        />
      ) : sibling.snomed_term ? (
        <Chip
          label={`${sibling.snomed_term} (${getTerminologyConfidenceLabel(sibling.score)} confidence)`}
          size="small"
          variant="outlined"
          sx={{ fontSize: "0.7rem", height: 20 }}
        />
      ) : (
        <Chip
          label="uncoded"
          size="small"
          variant="outlined"
          color="warning"
          sx={{ fontSize: "0.7rem", height: 20 }}
        />
      )}
      {sibling.assertion !== "present" && (
        <Chip
          label={sibling.assertion}
          size="small"
          sx={{ fontSize: "0.65rem", height: 18 }}
        />
      )}
    </Stack>
  );
}
