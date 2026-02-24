"use client";

import { useState } from "react";
import type { Correction } from "@/lib/types";

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
    <div style={{
      position: "fixed",
      bottom: 0,
      left: 0,
      right: 0,
      background: "#fff",
      borderTop: "2px solid #16a34a",
      padding: "14px 24px",
      zIndex: 900,
      display: "flex",
      alignItems: "center",
      gap: 16,
      boxShadow: "0 -4px 20px rgba(0,0,0,0.08)",
    }}>
      <span style={{ fontWeight: 600, fontSize: 14 }}>Add entity</span>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type text to match…"
        style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: "6px 12px", fontSize: 14, width: 240 }}
        autoFocus
      />
      {matchIdx >= 0 && (
        <span style={{ fontSize: 12, color: "#16a34a", fontFamily: "var(--font-mono)" }}>
          Found at [{matchIdx}:{matchIdx + text.length}]
        </span>
      )}
      {text.length >= 2 && matchIdx < 0 && (
        <span style={{ fontSize: 12, color: "#dc2626" }}>Not found in text</span>
      )}
      <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
        <button onClick={onCancel} style={{ padding: "6px 14px", border: "1px solid #e2e8f0", borderRadius: 8, background: "#fff", cursor: "pointer", fontSize: 13 }}>
          Cancel
        </button>
        <button onClick={handleAdd} disabled={matchIdx < 0} style={{
          padding: "6px 14px", border: "none", borderRadius: 8,
          background: matchIdx >= 0 ? "#16a34a" : "#94a3b8",
          color: "#fff", cursor: matchIdx >= 0 ? "pointer" : "not-allowed", fontSize: 13, fontWeight: 600,
        }}>
          Add
        </button>
      </div>
    </div>
  );
}
