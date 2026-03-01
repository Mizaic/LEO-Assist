"use client";

import { useState } from "react";
import type { EncounterTerm, Correction } from "@/lib/types";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";

interface Props {
  term: EncounterTerm;
  fullText: string;
  onSave: (termId: string, start: number, end: number, newText: string) => void;
  onCancel: () => void;
  onCorrection: (c: Correction) => void;
}

export default function SpanAdjustBanner({ term, fullText, onSave, onCancel, onCorrection }: Props) {
  const [start, setStart] = useState(term.span_start);
  const [end, setEnd] = useState(term.span_end);
  const preview = fullText.slice(Math.max(0, start), Math.min(end, fullText.length));
  const isValid = start < end && start >= 0 && end <= fullText.length;

  function save() {
    if (!isValid) return;
    onSave(term.term_id, start, end, preview);
    onCorrection({
      type: "span",
      text: term.text,
      detail: `Span adjusted: "${term.text}" → "${preview}" [${start}:${end}]`,
      time: new Date().toISOString(),
    });
  }

  return (
    <Paper
      elevation={8}
      sx={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        borderTop: "2px solid",
        borderColor: "primary.main",
        p: "14px 24px",
        zIndex: 900,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={2}>
        <Typography sx={{ fontWeight: 600, fontSize: 14 }}>
          Adjust span for &ldquo;{term.text}&rdquo;
        </Typography>
        <TextField
          size="small"
          type="number"
          label="Start"
          value={start}
          onChange={(e) => setStart(+e.target.value)}
          sx={{
            width: 90,
            "& .MuiInputBase-input": {
              fontFamily: "var(--font-mono)",
              fontSize: 13,
            },
          }}
        />
        <TextField
          size="small"
          type="number"
          label="End"
          value={end}
          onChange={(e) => setEnd(+e.target.value)}
          sx={{
            width: 90,
            "& .MuiInputBase-input": {
              fontFamily: "var(--font-mono)",
              fontSize: 13,
            },
          }}
        />
        <Typography
          variant="body2"
          sx={{
            bgcolor: "#fef9c3",
            px: 1.25,
            py: 0.5,
            borderRadius: 1.5,
            fontFamily: "var(--font-mono)",
            maxWidth: 300,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          &ldquo;{preview}&rdquo;
        </Typography>
        <Stack direction="row" spacing={1} sx={{ ml: "auto" }}>
          <Button variant="text" onClick={onCancel} sx={{ fontSize: 13, textTransform: "none" }}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={save}
            disabled={!isValid}
            sx={{ fontSize: 13, fontWeight: 600, textTransform: "none" }}
          >
            Save
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
