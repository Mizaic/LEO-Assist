"use client";

import type { EncounterTerm } from "@/lib/types";

interface Props {
  terms: EncounterTerm[];
  selectedId: string | null;
  onSelect: (termId: string) => void;
}

export default function EntitySidebar({ terms, selectedId, onSelect }: Props) {
  return (
    <div>
      <h3 style={{ fontSize: 14, fontWeight: 600, color: "#334155", padding: "12px 16px", borderBottom: "1px solid #e2e8f0" }}>
        Entities ({terms.length})
      </h3>
      <div style={{ overflowY: "auto", maxHeight: "calc(100vh - 320px)" }}>
        {terms.map((t) => {
          const score = Math.round(t.extraction_confidence * 100);
          const scoreColor = score >= 80 ? "#16a34a" : score >= 50 ? "#f59e0b" : "#dc2626";
          const isSelected = t.term_id === selectedId;

          return (
            <button
              key={t.term_id}
              onClick={() => onSelect(t.term_id)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "10px 16px",
                borderBottom: "1px solid #f1f5f9",
                background: isSelected ? "#eef2ff" : "transparent",
                border: "none",
                cursor: "pointer",
                transition: "background 0.1s",
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 500, color: "#0f172a", marginBottom: 2 }}>
                {t.text}
              </div>
              <div style={{ fontSize: 12, color: "#64748b", fontFamily: "var(--font-mono)" }}>
                {t.coding.snomed_concept_id || t.coding.read_code || "unlinked"}
                <span style={{ float: "right", color: scoreColor, fontWeight: 600 }}>{score}%</span>
              </div>
              {(t.context.negated || t.context.uncertain || t.context.historical) && (
                <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                  {t.context.negated && <span style={{ fontSize: 10, background: "#fef2f2", color: "#b91c1c", padding: "1px 5px", borderRadius: 3 }}>NEG</span>}
                  {t.context.uncertain && <span style={{ fontSize: 10, background: "#fffbeb", color: "#b45309", padding: "1px 5px", borderRadius: 3 }}>UNC</span>}
                  {t.context.historical && <span style={{ fontSize: 10, background: "#f5f3ff", color: "#6d28d9", padding: "1px 5px", borderRadius: 3 }}>Hx</span>}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
