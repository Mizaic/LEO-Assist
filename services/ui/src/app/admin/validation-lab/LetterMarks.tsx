/**
 * Per-step letter marks: fill is kind, bar is context.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 */
"use client";

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";

import { changeLabel, type LetterChange, type LetterMark } from "./letterHighlight";
import {
  assertionLabel,
  CONTEXT_BAR_PX,
  markBackground,
  markContextBar,
  markForeground,
  semanticTagLabel,
} from "./letterMarkStyle";
import { escapeRegex } from "@/components/mission-control/HighlightedText";

export { LetterMarkLegend } from "./LetterMarkLegend";

export function LetterMarks({
  text,
  marks,
  testId = "validation-lab-letter-highlight",
}: {
  text: string;
  marks: LetterMark[];
  testId?: string;
}): ReactNode {
  if (!text) return text;
  if (!marks.length) return text;
  const byKey = new Map(marks.map((mark) => [mark.term.toLowerCase(), mark]));
  const pattern = new RegExp(
    `(${marks.map((mark) => escapeRegex(mark.term)).join("|")})`,
    "gi",
  );
  const parts = text.split(pattern);
  return (
    <Box component="span" sx={MARK_MOTION}>
      {parts.map((part, idx) => {
        if (!part) return null;
        if (idx % 2 !== 1) {
          return <span key={`lt-${idx}`}>{part}</span>;
        }
        return (
          <LetterMarkSpan
            key={`hl-${idx}`}
            part={part}
            mark={byKey.get(part.toLowerCase())}
            testId={testId}
          />
        );
      })}
    </Box>
  );
}

function LetterMarkSpan({
  part,
  mark,
  testId,
}: {
  part: string;
  mark?: LetterMark;
  testId: string;
}) {
  const kind = semanticTagLabel(mark?.semanticTag);
  const change = mark?.change || "stable";
  const title = [
    assertionLabel(mark?.assertion),
    kind,
    mark?.code ? `Code ${mark.code}` : "",
    changeLabel(change),
  ]
    .filter(Boolean)
    .join(" -- ");
  return (
    <Tooltip title={title} enterDelay={200} placement="top">
      <Box
        component="mark"
        data-testid={testId}
        data-assertion={String(mark?.assertion || "present").toLowerCase()}
        data-semantic-tag={mark?.semanticTag || ""}
        data-change={change}
        sx={{
          bgcolor: markBackground(mark?.assertion, mark?.semanticTag),
          color: markForeground(mark?.assertion, mark?.semanticTag),
          borderLeft: `${CONTEXT_BAR_PX}px solid ${markContextBar(mark?.assertion)}`,
          pl: 0.7,
          borderRadius: "2px",
          fontWeight: 600,
          ...changeSx(change),
        }}
      >
        {part}
      </Box>
    </Tooltip>
  );
}

const MARK_MOTION = {
  "@keyframes leoUncoded": {
    "0%, 100%": { boxShadow: "0 0 0 0 rgba(220, 38, 38, 0.65)" },
    "50%": { boxShadow: "0 0 12px 6px rgba(220, 38, 38, 0.2)" },
  },
  "@keyframes leoContext": {
    "0%, 100%": { boxShadow: "0 0 0 0 rgba(245, 158, 11, 0.55)" },
    "50%": { boxShadow: "0 0 10px 4px rgba(245, 158, 11, 0.35)" },
  },
  "@keyframes leoNew": {
    from: { opacity: 0, transform: "scale(0.96)" },
    to: { opacity: 1, transform: "scale(1)" },
  },
} as const;

function changeSx(change: LetterChange): Record<string, unknown> {
  if (change === "uncoded") {
    return { animation: "leoUncoded 1.1s ease-in-out infinite" };
  }
  if (change === "context") {
    return { animation: "leoContext 1.4s ease-in-out infinite" };
  }
  if (change === "new") {
    return { animation: "leoNew 0.35s ease-out" };
  }
  if (change === "dropped") {
    return { textDecoration: "line-through", opacity: 0.55 };
  }
  return {};
}

