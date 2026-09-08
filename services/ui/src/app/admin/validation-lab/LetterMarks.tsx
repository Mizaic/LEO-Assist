/**
 * Per-step letter marks: fill is kind, bar is context.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
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

const MentionClock = createContext<{ next(term: string): number } | null>(null);

export function MentionClockProvider({
  resetKey,
  children,
}: {
  resetKey: string;
  children: ReactNode;
}) {
  const clock = useMemo(() => {
    const counts: Record<string, number> = {};
    return {
      next(term: string): number {
        const key = term.toLowerCase();
        counts[key] = (counts[key] || 0) + 1;
        return counts[key];
      },
    };
  }, [resetKey]);
  return <MentionClock.Provider value={clock}>{children}</MentionClock.Provider>;
}

export function LetterMarks({
  text,
  marks,
  testId = "validation-lab-letter-highlight",
  numberMentions = false,
}: {
  text: string;
  marks: LetterMark[];
  testId?: string;
  numberMentions?: boolean;
}): ReactNode {
  if (!text) return text;
  if (!marks.length) return text;
  const byKey = new Map(marks.map((mark) => [mark.term.toLowerCase(), mark]));
  const pattern = markPattern(marks, numberMentions);
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
            numberMentions={numberMentions}
          />
        );
      })}
    </Box>
  );
}

function markPattern(marks: LetterMark[], tightWords: boolean): RegExp {
  const parts = marks.map((mark) => {
    const escaped = escapeRegex(mark.term);
    if (tightWords && /^\w+$/.test(mark.term)) return `\\b${escaped}\\b`;
    return escaped;
  });
  return new RegExp(`(${parts.join("|")})`, "gi");
}

function LetterMarkSpan({
  part,
  mark,
  testId,
  numberMentions,
}: {
  part: string;
  mark?: LetterMark;
  testId: string;
  numberMentions: boolean;
}) {
  const clock = useContext(MentionClock);
  const mentionIndex = numberMentions ? clock?.next(part) ?? 0 : 0;
  const kind = semanticTagLabel(mark?.semanticTag);
  const change = mark?.change || "stable";
  const title = [
    mentionIndex ? `Mention ${mentionIndex}` : "",
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
        data-letter-term={part.toLowerCase()}
        data-mention-index={mentionIndex || undefined}
        data-review-focus={mentionIndex === 1 ? "true" : undefined}
        sx={{
          bgcolor: markBackground(mark?.assertion, mark?.semanticTag),
          color: markForeground(mark?.assertion, mark?.semanticTag),
          borderLeft: `${CONTEXT_BAR_PX}px solid ${markContextBar(mark?.assertion)}`,
          outline: mentionIndex === 1 ? "2px solid" : undefined,
          outlineColor: mentionIndex === 1 ? "primary.main" : undefined,
          outlineOffset: mentionIndex === 1 ? "1px" : undefined,
          cursor: "pointer",
          pl: 0.7,
          borderRadius: "2px",
          fontWeight: 600,
          ...changeSx(change),
        }}
      >
        {mentionIndex ? <MentionBadge index={mentionIndex} /> : null}
        {part}
      </Box>
    </Tooltip>
  );
}

function MentionBadge({ index }: { index: number }) {
  return (
    <Box
      component="span"
      aria-label={`Mention ${index}`}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 14,
        height: 14,
        mr: 0.4,
        px: 0.3,
        borderRadius: "7px",
        bgcolor: "primary.main",
        color: "primary.contrastText",
        fontSize: "0.65rem",
        fontWeight: 800,
        lineHeight: 1,
        verticalAlign: "middle",
      }}
    >
      {index}
    </Box>
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

