/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import type { CSSProperties } from "react";

import type { UncodedPhrase } from "./phraseMappingsApi";
import { draftNeedsTermFix } from "./termNeedsFix";

export function PhraseQueueList({
  items,
  selectedKey,
  onSelect,
}: {
  items: UncodedPhrase[];
  selectedKey: string | null;
  onSelect: (row: UncodedPhrase) => void;
}) {
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
          background: "#fff",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        {items.map((row) => (
          <QueueRow
            key={row.phrase_key}
            row={row}
            selected={row.phrase_key === selectedKey}
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
  onSelect,
}: {
  row: UncodedPhrase;
  selected: boolean;
  onSelect: (row: UncodedPhrase) => void;
}) {
  const notes = row.note_count || 0;
  const mapped = draftLabel(row);
  return (
    <button
      type="button"
      onClick={() => onSelect(row)}
      aria-pressed={selected}
      style={queueRowStyle(selected)}
    >
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          style={{
            display: "block",
            fontSize: 15,
            fontWeight: 600,
            color: "#0F172A",
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
            color: "#6B7280",
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
    </button>
  );
}

function queueRowStyle(selected: boolean): CSSProperties {
  return {
    display: "flex",
    width: "100%",
    minWidth: 0,
    gap: 12,
    padding: "12px 14px",
    border: 0,
    borderBottom: "1px solid rgba(15, 23, 42, 0.08)",
    background: selected ? "rgba(29, 78, 216, 0.08)" : "transparent",
    textAlign: "left",
    cursor: "pointer",
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
  if (action === "exclude") return { background: "#FEE2E2", color: "#991B1B" };
  if (action === "fix term") return { background: "#FFEDD5", color: "#9A3412" };
  return { background: "#DBEAFE", color: "#1E40AF" };
}
