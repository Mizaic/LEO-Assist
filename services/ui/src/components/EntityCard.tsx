"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import { CTX_FLAGS } from "@/lib/types";
import type { EncounterTerm, TermContext, Correction } from "@/lib/types";

interface Props {
  term: EncounterTerm;
  group?: EncounterTerm[];
  position: { top: number; left: number };
  onClose: () => void;
  onContextChange: (termId: string, ctx: Partial<TermContext>) => void;
  onReassign: (termId: string) => void;
  onAdjustSpan: (termId: string) => void;
  onRemove: (termId: string) => void;
  onCorrection: (c: Correction) => void;
  onSelectGroupTerm?: (termId: string) => void;
}

function deriveFlags(ctx: TermContext) {
  return {
    negated: ctx.negated,
    uncertain: ctx.uncertain,
    historical: ctx.historical,
    family: ctx.subject === "family",
    hypothetical: ctx.temporality === "hypothetical",
    resolved: false,
  };
}

export default function EntityCard({
  term,
  group = [],
  position,
  onClose,
  onContextChange,
  onReassign,
  onAdjustSpan,
  onRemove,
  onCorrection,
  onSelectGroupTerm,
}: Props) {
  const [flags, setFlags] = useState(deriveFlags(term.context));
  const groupIndex = group.length > 1 ? group.findIndex((t) => t.term_id === term.term_id) : -1;
  const hasGroup = group.length > 1;

  function toggle(key: string) {
    const next = { ...flags, [key]: !flags[key as keyof typeof flags] };
    setFlags(next);
    const partial: Partial<TermContext> = {
      negated: next.negated,
      uncertain: next.uncertain,
      historical: next.historical,
      subject: next.family ? "family" : "patient",
      temporality: next.hypothetical ? "hypothetical" : "present",
    };
    onContextChange(term.term_id, partial);
    onCorrection({
      type: "context",
      text: term.text,
      detail: `Toggled ${key} → ${!flags[key as keyof typeof flags]}`,
      time: new Date().toISOString(),
    });
  }

  const score = Math.round((term.extraction_confidence ?? 0) * 100);
  const scoreColor =
    score >= 80 ? "success" : score >= 50 ? "warning" : "error";
  const scoreHex =
    score >= 80 ? "#16a34a" : score >= 50 ? "#f59e0b" : "#dc2626";

  return (
    <Paper
      elevation={8}
      onClick={(e) => e.stopPropagation()}
      sx={{
        position: "fixed",
        top: position.top,
        left: position.left,
        zIndex: 1000,
        borderRadius: 3,
        p: 2.5,
        width: 360,
        animation: "cardIn 0.2s ease",
      }}
    >
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "start",
          mb: 1.5,
        }}
      >
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, color: "text.primary", lineHeight: 1.3 }}>
            {term.text}
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {term.extraction_method}
          </Typography>
        </Box>
        <IconButton size="small" onClick={onClose} sx={{ color: "text.disabled" }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {hasGroup && (
        <Stack
          direction="row"
          sx={{ alignItems: "center", mb: 1, gap: 0.5 }}
        >
          <IconButton
            size="small"
            disabled={groupIndex <= 0}
            onClick={() => onSelectGroupTerm?.(group[groupIndex - 1].term_id)}
          >
            <ChevronLeftIcon fontSize="small" />
          </IconButton>
          <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600 }}>
            Concept {groupIndex + 1} of {group.length}
          </Typography>
          <IconButton
            size="small"
            disabled={groupIndex >= group.length - 1}
            onClick={() => onSelectGroupTerm?.(group[groupIndex + 1].term_id)}
          >
            <ChevronRightIcon fontSize="small" />
          </IconButton>
        </Stack>
      )}

      <Box
        sx={{
          bgcolor: "grey.50",
          borderRadius: 2,
          p: 1.25,
          mb: 1.5,
          fontFamily: "var(--font-mono)",
        }}
      >
        {term.coding.snomed_concept_id && (
          <Typography variant="body2">
            SNOMED: <strong>{term.coding.snomed_concept_id}</strong>
          </Typography>
        )}
        {term.coding.snomed_term && (
          <Typography variant="body2">{term.coding.snomed_term}</Typography>
        )}
        {term.coding.read_code && (
          <Typography variant="body2">Read: {term.coding.read_code}</Typography>
        )}
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mt: 0.5 }}>
          <Typography variant="body2">Confidence:</Typography>
          <LinearProgress
            variant="determinate"
            value={score}
            color={scoreColor}
            sx={{ flex: 1, height: 4, borderRadius: 1 }}
          />
          <Typography variant="body2" sx={{ color: scoreHex, fontWeight: 600 }}>
            {score}%
          </Typography>
        </Stack>
      </Box>

      <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75, mb: 1.75 }}>
        {CTX_FLAGS.map((f) => {
          const active = flags[f.key as keyof typeof flags];
          return (
            <Chip
              key={f.key}
              label={f.short}
              title={f.label}
              size="small"
              onClick={() => toggle(f.key)}
              sx={{
                borderWidth: 1.5,
                borderStyle: "solid",
                borderColor: active ? f.color : "grey.300",
                bgcolor: active ? f.color + "18" : "background.paper",
                color: active ? f.color : "text.disabled",
                fontWeight: 600,
                fontSize: 12,
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            />
          );
        })}
      </Stack>

      <Divider sx={{ mb: 1.5 }} />

      <Stack direction="row" spacing={1}>
        <Button
          variant="outlined"
          size="small"
          onClick={() => onReassign(term.term_id)}
          sx={{ flex: 1, fontWeight: 600, textTransform: "none" }}
        >
          Reassign code
        </Button>
        <Button
          variant="outlined"
          size="small"
          color="inherit"
          onClick={() => onAdjustSpan(term.term_id)}
          sx={{ flex: 1, fontWeight: 600, textTransform: "none" }}
        >
          Adjust span
        </Button>
        <Button
          variant="outlined"
          size="small"
          color="error"
          onClick={() => {
            onRemove(term.term_id);
            onCorrection({
              type: "remove",
              text: term.text,
              detail: "Entity removed",
              time: new Date().toISOString(),
            });
          }}
          sx={{ flex: 1, fontWeight: 600, textTransform: "none" }}
        >
          Remove entity
        </Button>
      </Stack>
    </Paper>
  );
}
