"use client";

import { useState } from "react";
import type { Correction } from "@/lib/types";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";

interface Props {
  fullText: string;
  onAdd: (text: string, start: number, end: number) => void;
  onCancel: () => void;
  onCorrection: (c: Correction) => void;
}

export default function ManualEntityBanner({ fullText, onAdd, onCancel, onCorrection }: Props) {
  const [text, setText] = useState("");
  const matchIdx = text.length >= 2 ? fullText.toLowerCase().indexOf(text.toLowerCase()) : -1;

  function handleAdd() {
    if (matchIdx < 0 || text.length < 2) return;
    onAdd(text, matchIdx, matchIdx + text.length);
    onCorrection({
      type: "add",
      text,
      detail: `Manual entity added at [${matchIdx}:${matchIdx + text.length}]`,
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
        borderColor: "success.main",
        p: "14px 24px",
        zIndex: 900,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={2}>
        <Typography sx={{ fontWeight: 600, fontSize: 14 }}>Add entity</Typography>
        <TextField
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type text to match…"
          size="small"
          autoFocus
          sx={{
            width: 240,
            "& .MuiInputBase-input": { fontSize: 14 },
          }}
        />
        {matchIdx >= 0 && (
          <Typography
            variant="caption"
            sx={{ color: "success.main", fontFamily: "var(--font-mono)" }}
          >
            Found at [{matchIdx}:{matchIdx + text.length}]
          </Typography>
        )}
        {text.length >= 2 && matchIdx < 0 && (
          <Typography variant="caption" sx={{ color: "error.main" }}>
            Not found in text
          </Typography>
        )}
        <Stack direction="row" spacing={1} sx={{ ml: "auto" }}>
          <Button variant="text" onClick={onCancel} sx={{ fontSize: 13, textTransform: "none" }}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="success"
            onClick={handleAdd}
            disabled={matchIdx < 0}
            sx={{ fontSize: 13, fontWeight: 600, textTransform: "none" }}
          >
            Add
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
