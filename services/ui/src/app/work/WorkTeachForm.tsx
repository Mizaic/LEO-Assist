/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-4A012A59
 *   DO: DO-E7824FED
 */
"use client";

import { useEffect, useState } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { saveTeachExample, type WorkFixKind } from "./workFixApi";

export function sentenceForSpan(letter: string, span: string): string {
  const needle = span.trim();
  const text = letter || "";
  if (!needle) return "";
  const hit = text
    .split(/(?<=[.!?])\s+/)
    .find((part) => part.toLowerCase().includes(needle.toLowerCase()));
  if (hit) return hit.trim();
  const idx = text.toLowerCase().indexOf(needle.toLowerCase());
  if (idx < 0) return needle;
  return text
    .slice(Math.max(0, idx - 80), Math.min(text.length, idx + needle.length + 80))
    .trim();
}

export function TeachMode(props: {
  phrase: string;
  entityText: string;
  entityLabel?: string;
  encounterText?: string;
  busy: boolean;
  onIdle: () => void;
  onRunFix: (kind: WorkFixKind, action: () => Promise<void>) => Promise<void>;
}) {
  const [span, setSpan] = useState(props.phrase || props.entityText);
  useEffect(() => {
    setSpan(props.phrase || props.entityText);
  }, [props.phrase, props.entityText]);
  const sentence = sentenceForSpan(props.encounterText || "", span);
  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        This teaching example goes live now. We save the missed word and its
        sentence. Names and NHS numbers are removed first.
      </Typography>
      {sentence ? (
        <Typography variant="body2">{sentence}</Typography>
      ) : (
        <Typography variant="caption" color="text.secondary">
          Type the missed word in Phrase, or highlight it in the letter.
        </Typography>
      )}
      <Button
        size="small"
        onClick={() => {
          const picked = window.getSelection()?.toString().trim() ?? "";
          if (picked) setSpan(picked);
        }}
      >
        Use highlighted text
      </Button>
      <Stack direction="row" spacing={1}>
        <Button
          size="small"
          variant="contained"
          disabled={props.busy || !span.trim()}
          onClick={() =>
            void props.onRunFix("teach", () =>
              saveTeachExample({
                span,
                letter: props.encounterText || "",
                semantic_tag: props.entityLabel || "finding",
                assertion: "present",
              }),
            )
          }
        >
          {props.busy ? "Saving..." : "Save teaching example"}
        </Button>
        <Button size="small" onClick={props.onIdle} disabled={props.busy}>
          Cancel
        </Button>
      </Stack>
    </Stack>
  );
}
