/**
 * Centre letter pane with highlight overlay.
 *
 * Atlas: DI-C953EF73 / DI-49BA8E04 / DO-4FD76836
 */
"use client";

import { useEffect, useRef, type MouseEvent } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { LetterMarkLegend } from "./LetterMarks";
import LetterMarkdownView from "./LetterMarkdownView";
import type { LetterMark } from "./letterHighlight";

export interface LetterMarkPick {
  term: string;
  assertion: string;
  semanticTag: string;
}

interface Props {
  referralText: string;
  openedBecause?: string;
  highlights?: LetterMark[];
  focusTerm?: string;
  onMarkClick?: (mark: LetterMarkPick) => void;
}

export default function LetterPane({
  referralText,
  openedBecause,
  highlights,
  focusTerm,
  onMarkClick,
}: Props) {
  const marks = highlights || [];
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!focusTerm || !scroller.current) return;
    const term = focusTerm.toLowerCase();
    const node = scroller.current.querySelector(
      `[data-letter-term="${cssAttr(term)}"]`,
    );
    if (node instanceof HTMLElement) {
      node.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focusTerm, marks]);

  return (
    <Box
      sx={{
        width: { xs: "100%", md: "50%" },
        minWidth: 280,
        borderRight: "1px solid",
        borderColor: "divider",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#FAFAFA",
        minHeight: 0,
      }}
      data-testid="validation-lab-letter-pane"
    >
      <Box
        ref={scroller}
        sx={{ flex: 1, overflow: "auto", p: 2 }}
        onClick={(event) => handleMarkClick(event, onMarkClick)}
      >
        {openedBecause ? (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1.5 }}
            data-testid="validation-lab-opened-because"
          >
            Why you opened this: {openedBecause}
          </Typography>
        ) : null}
        <LetterMarkLegend marks={marks} compact />
        <LetterMarkdownView
          text={referralText}
          marks={marks}
          testId="validation-lab-letter-highlight"
          emptyLabel="No letter is available for this run."
          focusTerm={focusTerm}
        />
      </Box>
    </Box>
  );
}

function handleMarkClick(
  event: MouseEvent,
  onMarkClick?: (mark: LetterMarkPick) => void,
): void {
  if (!onMarkClick) return;
  const node = (event.target as HTMLElement | null)?.closest?.(
    "mark[data-letter-term]",
  );
  if (!(node instanceof HTMLElement)) return;
  onMarkClick({
    term: node.getAttribute("data-letter-term") || node.textContent || "",
    assertion: node.getAttribute("data-assertion") || "present",
    semanticTag: node.getAttribute("data-semantic-tag") || "",
  });
}

function cssAttr(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}
