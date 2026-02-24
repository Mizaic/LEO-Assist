"use client";

import { useState } from "react";
import { CTX_FLAGS } from "@/lib/types";
import type { EncounterTerm, TermContext, Correction } from "@/lib/types";

interface Props {
  term: EncounterTerm;
  position: { top: number; left: number };
  onClose: () => void;
  onContextChange: (termId: string, ctx: Partial<TermContext>) => void;
  onReassign: (termId: string) => void;
  onAdjustSpan: (termId: string) => void;
  onRemove: (termId: string) => void;
  onCorrection: (c: Correction) => void;
}

function deriveFlags(ctx: TermContext) {
  return {
    negated: ctx.negated,
    uncertain: ctx.uncertain,
    historical: ctx.historical,
    family: ctx.subject === "family",
    hypothetical: ctx.temporality === "hypothetical",
    resolved: false,
  };
}

export default function EntityCard({
  term,
  position,
  onClose,
  onContextChange,
  onReassign,
  onAdjustSpan,
  onRemove,
  onCorrection,
}: Props) {
  const [flags, setFlags] = useState(deriveFlags(term.context));

  function toggle(key: string) {
    const next = { ...flags, [key]: !flags[key as keyof typeof flags] };
    setFlags(next);
    const partial: Partial<TermContext> = {
      negated: next.negated,
      uncertain: next.uncertain,
      historical: next.historical,
      subject: next.family ? "family" : "patient",
      temporality: next.hypothetical ? "hypothetical" : "present",
    };
    onContextChange(term.term_id, partial);
    onCorrection({
      type: "context",
      text: term.text,
      detail: `Toggled ${key} → ${!flags[key as keyof typeof flags]}`,
      time: new Date().toISOString(),
    });
  }

  const score = Math.round((term.extraction_confidence ?? 0) * 100);
  const scoreColor = score >= 80 ? "#16a34a" : score >= 50 ? "#f59e0b" : "#dc2626";

  return (
    <div
      style={{
        position: "fixed",
        top: position.top,
        left: position.left,
        zIndex: 1000,
        background: "#fff",
        borderRadius: 12,
        boxShadow: "0 8px 30px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)",
        padding: 20,
        width: 360,
        animation: "cardIn 0.2s ease",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 12 }}>
        <div>
          <h4 style={{ fontSize: 16, fontWeight: 600, color: "#0f172a", marginBottom: 2 }}>
            {term.text}
          </h4>
          <span style={{ fontSize: 12, color: "#64748b" }}>{term.extraction_method}</span>
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#94a3b8" }}>
          ✕
        </button>
      </div>

      <div style={{
        background: "#f8fafc",
        borderRadius: 8,
        padding: 10,
        marginBottom: 12,
        fontSize: 13,
        fontFamily: "var(--font-mono)",
      }}>
        {term.coding.snomed_concept_id && (
          <div>SNOMED: <strong>{term.coding.snomed_concept_id}</strong></div>
        )}
        {term.coding.snomed_term && <div>{term.coding.snomed_term}</div>}
        {term.coding.read_code && <div>Read: {term.coding.read_code}</div>}
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
          <span>Confidence:</span>
          <div style={{ flex: 1, height: 4, background: "#e2e8f0", borderRadius: 2 }}>
            <div style={{ width: `${score}%`, height: 4, background: scoreColor, borderRadius: 2 }} />
          </div>
          <span style={{ color: scoreColor, fontWeight: 600 }}>{score}%</span>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
        {CTX_FLAGS.map((f) => {
          const active = flags[f.key as keyof typeof flags];
          return (
            <button
              key={f.key}
              title={f.label}
              onClick={() => toggle(f.key)}
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                border: `1.5px solid ${active ? f.color : "#e2e8f0"}`,
                background: active ? f.color + "18" : "#fff",
                color: active ? f.color : "#94a3b8",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              {f.short}
            </button>
          );
        })}
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => onReassign(term.term_id)}
          style={{ flex: 1, padding: "7px 0", borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", color: "#4f46e5" }}
        >
          Reassign
        </button>
        <button
          onClick={() => onAdjustSpan(term.term_id)}
          style={{ flex: 1, padding: "7px 0", borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", color: "#475569" }}
        >
          Adjust span
        </button>
        <button
          onClick={() => {
            onRemove(term.term_id);
            onCorrection({ type: "remove", text: term.text, detail: "Entity removed", time: new Date().toISOString() });
          }}
          style={{ flex: 1, padding: "7px 0", borderRadius: 8, border: "1px solid #fecaca", background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", color: "#dc2626" }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}
