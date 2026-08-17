/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import type { CSSProperties } from "react";
import { motion as fm } from "framer-motion";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, elevation, radius, typography } from "@leo/design-system/tokens";

import type { UncodedPhrase } from "./phraseMappingsApi";
import { draftNeedsTermFix } from "./termNeedsFix";

const BRAND = color.brand.primary;
const WELL = "rgba(15, 23, 42, 0.06)";

export function PhraseQueueList({
  items,
  selectedKey,
  onSelect,
}: {
  items: UncodedPhrase[];
  selectedKey: string | null;
  onSelect: (row: UncodedPhrase) => void;
}) {
  const { reducedMotion } = useMotion();
  return (
    <div
      data-testid="phrase-queue"
      style={{
        minWidth: 0,
        minHeight: 0,
        maxWidth: "100%",
        overflow: "auto",
        padding: "4px 16px 32px 0",
      }}
    >
      <div
        style={{
          background: color.surface.raised,
          borderRadius: radius.md,
          boxShadow: elevation.card,
          overflow: "hidden",
        }}
      >
        {items.map((row) => (
          <QueueRow
            key={row.phrase_key}
            row={row}
            selected={row.phrase_key === selectedKey}
            reducedMotion={reducedMotion}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

function draftLabel(row: UncodedPhrase): string {
  if (row.draft_action === "exclude") return "Do not code";
  if (draftNeedsTermFix(row)) return "Needs preferred term";
  if (row.draft_concept_term) return row.draft_concept_term;
  if (row.draft_concept_id) return row.draft_concept_id;
  return "";
}

function QueueRow({
  row,
  selected,
  reducedMotion,
  onSelect,
}: {
  row: UncodedPhrase;
  selected: boolean;
  reducedMotion: boolean;
  onSelect: (row: UncodedPhrase) => void;
}) {
  const notes = row.note_count || 0;
  const mapped = draftLabel(row);
  return (
    <fm.button
      type="button"
      onClick={() => onSelect(row)}
      aria-pressed={selected}
      whileTap={tapScale(reducedMotion)}
      whileHover={reducedMotion || selected ? undefined : { backgroundColor: WELL }}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={queueRowStyle(selected)}
    >
      {selected ? (
        <fm.span
          layoutId={reducedMotion ? undefined : "phrase-queue-rail"}
          aria-hidden="true"
          transition={springOrInstant(reducedMotion, springs.ui)}
          style={{
            position: "absolute",
            left: 0,
            top: 8,
            bottom: 8,
            width: 3,
            borderRadius: 999,
            background: BRAND,
          }}
        />
      ) : null}
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          style={{
            display: "block",
            fontFamily: typography.fontFamily.body,
            fontSize: 15,
            fontWeight: 600,
            color: color.text.primary,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {row.normalized || row.phrase_key}
        </span>
        <span
          style={{
            display: "block",
            marginTop: 2,
            fontSize: 12,
            color: color.text.caption,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {notes} {notes === 1 ? "note" : "notes"}
          {row.extracted_tag ? ` · ${row.extracted_tag}` : ""}
          {mapped ? ` · ${mapped}` : ""}
        </span>
      </span>
      <DraftChip
        action={draftNeedsTermFix(row) ? "fix term" : row.draft_action}
      />
    </fm.button>
  );
}

function queueRowStyle(selected: boolean): CSSProperties {
  return {
    display: "flex",
    position: "relative",
    width: "100%",
    minWidth: 0,
    gap: 12,
    padding: "12px 14px 12px 16px",
    border: 0,
    borderBottom: "1px solid " + color.surface.divider,
    background: selected ? color.surface.raised : "transparent",
    boxShadow: selected ? elevation.card : "none",
    color: selected ? BRAND : color.text.primary,
    textAlign: "left",
    cursor: "pointer",
    fontFamily: typography.fontFamily.body,
  };
}

function DraftChip({ action }: { action?: string }) {
  if (!action) return null;
  const tone = chipTone(action);
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        borderRadius: 999,
        padding: "2px 8px",
        height: "fit-content",
        flexShrink: 0,
        background: tone.background,
        color: tone.color,
      }}
    >
      {action}
    </span>
  );
}

function chipTone(action: string): { background: string; color: string } {
  if (action === "exclude") {
    return { background: "rgba(185, 28, 28, 0.12)", color: color.status.danger };
  }
  if (action === "fix term") {
    return { background: "rgba(180, 83, 9, 0.12)", color: color.status.warning };
  }
  return { background: "rgba(13, 70, 214, 0.12)", color: color.brand.primaryHover };
}
