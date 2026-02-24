"use client";

import { useState } from "react";
import type { EncounterTerm, Correction } from "@/lib/types";

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
    <div style={{
      position: "fixed",
      bottom: 0,
      left: 0,
      right: 0,
      background: "#fff",
      borderTop: "2px solid #4f46e5",
      padding: "14px 24px",
      zIndex: 900,
      display: "flex",
      alignItems: "center",
      gap: 16,
      boxShadow: "0 -4px 20px rgba(0,0,0,0.08)",
    }}>
      <span style={{ fontWeight: 600, fontSize: 14 }}>Adjust span for &ldquo;{term.text}&rdquo;</span>
      <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13 }}>
        Start:
        <input type="number" value={start} onChange={(e) => setStart(+e.target.value)}
          style={{ width: 70, border: "1px solid #cbd5e1", borderRadius: 6, padding: "4px 8px", fontFamily: "var(--font-mono)", fontSize: 13 }}
        />
      </label>
      <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13 }}>
        End:
        <input type="number" value={end} onChange={(e) => setEnd(+e.target.value)}
          style={{ width: 70, border: "1px solid #cbd5e1", borderRadius: 6, padding: "4px 8px", fontFamily: "var(--font-mono)", fontSize: 13 }}
        />
      </label>
      <span style={{
        background: "#fef9c3",
        padding: "4px 10px",
        borderRadius: 6,
        fontSize: 13,
        fontFamily: "var(--font-mono)",
        maxWidth: 300,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}>
        &ldquo;{preview}&rdquo;
      </span>
      <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
        <button onClick={onCancel} style={{ padding: "6px 14px", border: "1px solid #e2e8f0", borderRadius: 8, background: "#fff", cursor: "pointer", fontSize: 13 }}>
          Cancel
        </button>
        <button
          onClick={save}
          disabled={!isValid}
          style={{
            padding: "6px 14px",
            border: "none",
            borderRadius: 8,
            background: isValid ? "#4f46e5" : "#94a3b8",
            color: "#fff",
            cursor: isValid ? "pointer" : "not-allowed",
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Save
        </button>
      </div>
    </div>
  );
}
