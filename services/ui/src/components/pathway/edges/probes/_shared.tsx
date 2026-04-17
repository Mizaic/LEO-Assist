"use client";

/**
 * Shared probe primitives and helpers (Phase 6b-vi decomposition).
 *
 * Extracted verbatim from the legacy services/ui/src/components/pathway/
 * edges/probeStrategies.tsx (1198 LOC) into a focused <500 LOC module.
 *
 * Public surface (re-exported from probeStrategies.tsx barrel):
 *   types  : PathSegment, ProbeDetailProps, ProbeStrategy, LayerTrace
 *   palette: C
 *   helpers: isRec, arr, str, num, bool, trunc, pl, pct, fmt, safeJSON,
 *            asLayerTrace, layerChangeSummary
 *   UI     : Pill, MiniTable, Verdict, SectionCard, InspectButton,
 *            LayerTraceTable, EntityDelta
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

export type PathSegment = string | number;

/* ── helpers ────────────────────────────────────────────────────────── */

export function isRec(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
export function arr(v: unknown): unknown[] { return Array.isArray(v) ? v : []; }
export function str(v: unknown, d = ""): string { return typeof v === "string" ? v : d; }
export function num(v: unknown, d = 0): number { return typeof v === "number" ? v : d; }
export function bool(v: unknown, d = false): boolean { return typeof v === "boolean" ? v : d; }
export function trunc(s: string, n = 60): string { return s.length > n ? s.slice(0, n) + "…" : s; }
export function pl(n: number, s: string, p = s + "s"): string { return `${n} ${n === 1 ? s : p}`; }
export function pct(n: number): string { return `${Math.round(n * 100)}%`; }

export function fmt(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return trunc(v.replace(/\s+/g, " "), 80);
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
  if (isRec(v)) return `${Object.keys(v).length} fields`;
  return trunc(String(v), 80);
}

export function safeJSON(value: unknown): string {
  try { return JSON.stringify(value); } catch { return "[unserializable]"; }
}

/* ── shared palette ─────────────────────────────────────────────────── */

export const C = {
  green: "#a6e3a1", red: "#f38ba8", orange: "#fab387",
  blue: "#89b4fa", purple: "#cba6f7", yellow: "#f9e2af",
  dim: "#6c7086", text: "#cdd6f4", bg: "#181825",
  border: "#313244", deep: "#11111b",
};

/* ── shared UI primitives ───────────────────────────────────────────── */

export function Pill({ label, value, color = C.text }: { label: string; value: string | number; color?: string }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      background: C.deep, border: `1px solid ${C.border}`,
      borderRadius: 999, padding: "3px 8px", fontSize: 10, fontWeight: 700, color,
    }}>
      {label}: {value}
    </span>
  );
}

export function MiniTable({ cols, rows, onRow, max = 6 }: {
  cols: string[];
  rows: Record<string, unknown>[];
  onRow?: (i: number) => void;
  max?: number;
}) {
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${C.border}` }}>
            {cols.map(c => (
              <th key={c} style={{ textAlign: "left", padding: "4px 6px", color: C.dim, fontWeight: 600 }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, max).map((r, i) => (
            <tr key={i} onClick={() => onRow?.(i)} style={{ borderBottom: `1px solid ${C.border}40`, cursor: onRow ? "pointer" : "default" }}>
              {cols.map(c => (
                <td key={c} style={{ padding: "3px 6px", color: C.text, maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {fmt(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > max && (
        <div style={{ padding: "3px 6px", color: C.dim, fontSize: 10 }}>…{rows.length - max} more</div>
      )}
    </div>
  );
}

export function Verdict({ passed, label, detail, confidence }: {
  passed: boolean; label: string; detail?: string; confidence?: number;
}) {
  return (
    <div style={{
      border: `1px solid ${passed ? C.green : C.red}`, borderRadius: 8,
      padding: "8px 10px", background: C.bg,
      display: "flex", alignItems: "center", gap: 10,
    }}>
      <span style={{ fontSize: 18 }}>{passed ? "✓" : "✗"}</span>
      <div style={{ flex: 1 }}>
        <div style={{ color: passed ? C.green : C.red, fontSize: 12, fontWeight: 700 }}>{label}</div>
        {detail && <div style={{ color: C.text, fontSize: 10, marginTop: 2 }}>{detail}</div>}
      </div>
      {confidence != null && (
        <span style={{ color: C.purple, fontSize: 10, fontWeight: 700 }}>{pct(confidence)}</span>
      )}
    </div>
  );
}

export function SectionCard({ title, text, color = C.blue }: { title: string; text: string; color?: string }) {
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 8px", background: C.bg }}>
      <div style={{ color, fontSize: 10, fontWeight: 700, marginBottom: 3 }}>{title}</div>
      <div style={{ color: C.text, fontSize: 10, lineHeight: 1.45 }}>{trunc(text, 200)}</div>
    </div>
  );
}

export function InspectButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} style={{
      background: C.deep, border: `1px solid ${C.border}`, borderRadius: 8,
      padding: "6px 8px", color: C.blue, cursor: "pointer", fontSize: 10, textAlign: "left",
    }}>
      {label} →
    </button>
  );
}

/* ── layer trace (post_processing) ──────────────────────────────────── */

export interface LayerTrace {
  layer_id: string; name: string; status: string;
  before_count: number; after_count: number;
  added_count: number; removed_count: number; updated_count: number;
  duration_ms: number; error?: string;
}

export function asLayerTrace(v: unknown): LayerTrace[] {
  if (!Array.isArray(v)) return [];
  return v.filter((item): item is LayerTrace =>
    isRec(item) && typeof item.name === "string" && typeof item.status === "string"
    && typeof item.before_count === "number" && typeof item.after_count === "number"
  );
}

export function layerChangeSummary(layer: LayerTrace): { text: string; color: string } {
  const delta = layer.after_count - layer.before_count;
  const hasChanges = layer.added_count > 0 || layer.removed_count > 0 || layer.updated_count > 0;
  if (!hasChanges && delta === 0) return { text: "no change", color: C.dim };
  const parts: string[] = [];
  if (layer.added_count > 0) parts.push(`+${layer.added_count} added`);
  if (layer.removed_count > 0) parts.push(`−${layer.removed_count} removed`);
  if (layer.updated_count > 0) parts.push(`${layer.updated_count} updated`);
  return { text: parts.join(", ") || (delta > 0 ? `+${delta}` : String(delta)), color: delta < 0 ? C.red : delta > 0 ? C.green : C.orange };
}

export function LayerTraceTable({ layers }: { layers: LayerTrace[] }) {
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", background: C.bg }}>
      <div style={{
        color: C.blue, fontSize: 10, fontWeight: 700, padding: "7px 9px",
        letterSpacing: "0.04em", textTransform: "uppercase",
        borderBottom: `1px solid ${C.border}`,
      }}>
        Did each clean-up step run?
      </div>
      {layers.map((layer, i) => {
        const isSkipped = layer.status === "skipped";
        const isError = layer.status === "error";
        const statusColor = isError ? C.red : isSkipped ? C.dim : C.green;
        const statusIcon = isError ? "✗" : isSkipped ? "○" : "✓";
        const statusLabel = isError ? "Error" : isSkipped ? "Skipped" : "Ran OK";
        const change = layerChangeSummary(layer);
        return (
          <div
            key={layer.layer_id}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto",
              alignItems: "center",
              gap: 10,
              padding: "5px 9px",
              borderBottom: i < layers.length - 1 ? `1px solid ${C.border}40` : "none",
              opacity: isSkipped ? 0.6 : 1,
            }}
          >
            <span style={{ color: C.text, fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {layer.name}
            </span>
            <span style={{ color: change.color, fontSize: 10, whiteSpace: "nowrap" }}>
              {isSkipped ? "—" : change.text}
            </span>
            <span style={{ color: statusColor, fontSize: 10, fontWeight: 700, whiteSpace: "nowrap", minWidth: 60, textAlign: "right" }}>
              {statusIcon} {statusLabel}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ── entity in/out delta (shared by many strategies) ────────────────── */

export function EntityDelta({ input, output }: { input: Record<string, unknown>; output: Record<string, unknown> }) {
  const before = arr(input.entities).length;
  const after = arr(output.entities).length;
  if (before === 0 && after === 0) return null;
  const diff = after - before;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", fontSize: 10 }}>
      <Pill label="In" value={before} />
      <span style={{ color: C.dim }}>→</span>
      <Pill label="Out" value={after} color={diff < 0 ? C.red : diff > 0 ? C.green : C.text} />
      {diff !== 0 && (
        <span style={{ color: diff < 0 ? C.red : C.green, fontWeight: 700 }}>
          ({diff > 0 ? "+" : ""}{diff})
        </span>
      )}
    </div>
  );
}

/* ── strategy interface ─────────────────────────────────────────────── */

export interface ProbeDetailProps {
  output: Record<string, unknown>;
  input: Record<string, unknown>;
  openInspector: (path: PathSegment[]) => void;
}

export interface ProbeStrategy {
  icon: string;
  headline: (output: Record<string, unknown>, input: Record<string, unknown>) => string;
  Detail: (props: ProbeDetailProps) => JSX.Element | null;
}
