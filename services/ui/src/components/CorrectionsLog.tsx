"use client";

import type { Correction } from "@/lib/types";

interface Props {
  corrections: Correction[];
}

const TYPE_ICONS: Record<string, string> = {
  context: "🏷",
  reassign: "🔄",
  span: "📏",
  add: "➕",
  remove: "🗑",
};

export default function CorrectionsLog({ corrections }: Props) {
  if (corrections.length === 0) {
    return (
      <div style={{ padding: 16, color: "#94a3b8", fontSize: 13 }}>
        No corrections yet
      </div>
    );
  }

  return (
    <div style={{ maxHeight: 280, overflowY: "auto" }}>
      {corrections.map((c, i) => (
        <div
          key={i}
          style={{
            padding: "10px 16px",
            borderBottom: "1px solid #f1f5f9",
            fontSize: 13,
            animation: "slideIn 0.2s ease",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            <span>{TYPE_ICONS[c.type] || "•"}</span>
            <strong>{c.text}</strong>
          </div>
          <div style={{ color: "#64748b", fontSize: 12 }}>{c.detail}</div>
        </div>
      ))}
    </div>
  );
}
