"use client";

import { SUBGRAPH_OPTIONS, SUBGRAPH_IO } from "../config/subgraphs";

export type PathSegment = string | number;

/* ── helpers ────────────────────────────────────────────────────────── */

function isRec(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function arr(v: unknown): unknown[] { return Array.isArray(v) ? v : []; }
function str(v: unknown, d = ""): string { return typeof v === "string" ? v : d; }
function num(v: unknown, d = 0): number { return typeof v === "number" ? v : d; }
function bool(v: unknown, d = false): boolean { return typeof v === "boolean" ? v : d; }
function trunc(s: string, n = 60): string { return s.length > n ? s.slice(0, n) + "…" : s; }
function pl(n: number, s: string, p = s + "s"): string { return `${n} ${n === 1 ? s : p}`; }
function pct(n: number): string { return `${Math.round(n * 100)}%`; }

function fmt(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return trunc(v.replace(/\s+/g, " "), 80);
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
  if (isRec(v)) return `${Object.keys(v).length} fields`;
  return trunc(String(v), 80);
}

/* ── shared palette ─────────────────────────────────────────────────── */

const C = {
  green: "#a6e3a1", red: "#f38ba8", orange: "#fab387",
  blue: "#89b4fa", purple: "#cba6f7", yellow: "#f9e2af",
  dim: "#6c7086", text: "#cdd6f4", bg: "#181825",
  border: "#313244", deep: "#11111b",
};

/* ── shared UI primitives ───────────────────────────────────────────── */

function Pill({ label, value, color = C.text }: { label: string; value: string | number; color?: string }) {
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

function MiniTable({ cols, rows, onRow, max = 6 }: {
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

function Verdict({ passed, label, detail, confidence }: {
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

function SectionCard({ title, text, color = C.blue }: { title: string; text: string; color?: string }) {
  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 8px", background: C.bg }}>
      <div style={{ color, fontSize: 10, fontWeight: 700, marginBottom: 3 }}>{title}</div>
      <div style={{ color: C.text, fontSize: 10, lineHeight: 1.45 }}>{trunc(text, 200)}</div>
    </div>
  );
}

function InspectButton({ label, onClick }: { label: string; onClick: () => void }) {
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

interface LayerTrace {
  layer_id: string; name: string; status: string;
  before_count: number; after_count: number;
  added_count: number; removed_count: number; updated_count: number;
  duration_ms: number; error?: string;
}

function asLayerTrace(v: unknown): LayerTrace[] {
  if (!Array.isArray(v)) return [];
  return v.filter((item): item is LayerTrace =>
    isRec(item) && typeof item.name === "string" && typeof item.status === "string"
    && typeof item.before_count === "number" && typeof item.after_count === "number"
  );
}

function layerChangeSummary(layer: LayerTrace): { text: string; color: string } {
  const delta = layer.after_count - layer.before_count;
  const hasChanges = layer.added_count > 0 || layer.removed_count > 0 || layer.updated_count > 0;
  if (!hasChanges && delta === 0) return { text: "no change", color: C.dim };
  const parts: string[] = [];
  if (layer.added_count > 0) parts.push(`+${layer.added_count} added`);
  if (layer.removed_count > 0) parts.push(`−${layer.removed_count} removed`);
  if (layer.updated_count > 0) parts.push(`${layer.updated_count} updated`);
  return { text: parts.join(", ") || (delta > 0 ? `+${delta}` : String(delta)), color: delta < 0 ? C.red : delta > 0 ? C.green : C.orange };
}

function LayerTraceTable({ layers }: { layers: LayerTrace[] }) {
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

function EntityDelta({ input, output }: { input: Record<string, unknown>; output: Record<string, unknown> }) {
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

/* ── strategies ─────────────────────────────────────────────────────── */

const extraction: ProbeStrategy = {
  icon: "🔍",
  headline: (out) => {
    const ents = arr(out.entities), sents = arr(out.sentences), errs = arr(out.errors);
    let h = `Found ${pl(ents.length, "clinical fact")}`;
    if (sents.length > 0) h += ` across ${pl(sents.length, "sentence")}`;
    if (errs.length > 0) h += ` · ${pl(errs.length, "error")}`;
    return h;
  },
  Detail: ({ output, openInspector }) => {
    const entities = arr(output.entities).filter(isRec) as Record<string, unknown>[];
    if (entities.length === 0) return <div style={{ color: C.dim, fontSize: 10 }}>No clinical facts found.</div>;
    const tags: Record<string, number> = {};
    for (const e of entities) { const t = str(e.semantic_tag, "other"); tags[t] = (tags[t] ?? 0) + 1; }
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {Object.entries(tags).sort(([, a], [, b]) => b - a).slice(0, 8).map(([t, c]) => (
            <Pill key={t} label={t} value={c} color={C.blue} />
          ))}
        </div>
        <MiniTable
          cols={["text", "semantic_tag", "assertion"]}
          rows={entities}
          onRow={(i) => openInspector(["entities", i])}
        />
      </div>
    );
  },
};

const postProcessing: ProbeStrategy = {
  icon: "🧹",
  headline: (out, inp) => {
    const before = arr(inp.entities).length, after = arr(out.entities).length;
    const diff = after - before;
    let h = `Cleaned ${before} → ${after} entities`;
    if (diff < 0) h += ` (removed ${Math.abs(diff)})`;
    else if (diff > 0) h += ` (added ${diff})`;
    return h;
  },
  Detail: ({ output, input }) => {
    const trace = asLayerTrace(output.post_processing_trace);
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <EntityDelta input={input} output={output} />
        {trace.length > 0 ? <LayerTraceTable layers={trace} /> : (
          <div style={{ color: C.dim, fontSize: 10 }}>Layer-by-layer trace not available for this run.</div>
        )}
      </div>
    );
  },
};

const terminology: ProbeStrategy = {
  icon: "🏷️",
  headline: (out) => {
    const entities = arr(out.entities).filter(isRec);
    const coded    = entities.filter(e => e.concept_id && !e.terminology_unresolved);
    const rejected = entities.filter(e => e.terminology_unresolved);
    let h = `Coded ${pl(coded.length, "entity", "entities")} to SNOMED CT`;
    if (rejected.length > 0) h += ` — ${pl(rejected.length, "entity", "entities")} below confidence threshold`;
    return h;
  },
  Detail: ({ output, input, openInspector }) => {
    const entities = arr(output.entities).filter(isRec) as Record<string, unknown>[];
    if (entities.length === 0) return null;
    const coded    = entities.filter(e => e.concept_id && !e.terminology_unresolved);
    const rejected = entities.filter(e => e.terminology_unresolved);
    return (
      <div style={{ display: "grid", gap: 10 }}>
        <EntityDelta input={input} output={output} />

        {coded.length > 0 && (
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.green, marginBottom: 4 }}>
              ✓ {pl(coded.length, "entity", "entities")} coded
            </div>
            <MiniTable
              cols={["text", "concept_id", "term", "score"]}
              rows={coded}
              onRow={(i) => openInspector(["entities", entities.indexOf(coded[i])])}
            />
          </div>
        )}

        {rejected.length > 0 && (
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.orange, marginBottom: 4 }}>
              ⚠ {pl(rejected.length, "entity", "entities")} below confidence threshold — no code assigned
            </div>
            <MiniTable
              cols={["text", "score", "semantic_tag"]}
              rows={rejected}
              onRow={(i) => openInspector(["entities", entities.indexOf(rejected[i])])}
            />
          </div>
        )}
      </div>
    );
  },
};

const tierClassify: ProbeStrategy = {
  icon: "🏅",
  headline: (out) => {
    const entities = arr(out.entities).filter(isRec);
    const tiers: Record<string, number> = {};
    for (const e of entities) { const t = str(e.tier, str(e.confidence_tier, "ungraded")); tiers[t] = (tiers[t] ?? 0) + 1; }
    const parts = Object.entries(tiers).map(([t, c]) => `${c} ${t}`);
    return `Graded ${pl(entities.length, "entity", "entities")}` + (parts.length > 0 ? ` — ${parts.join(", ")}` : "");
  },
  Detail: ({ output, openInspector }) => {
    const entities = arr(output.entities).filter(isRec) as Record<string, unknown>[];
    const decisions = arr(output.tier_decisions).filter(isRec) as Record<string, unknown>[];
    const tiers: Record<string, number> = {};
    for (const e of entities) {
      const t = str(e.tier, str(e.confidence_tier, "ungraded"));
      tiers[t] = (tiers[t] ?? 0) + 1;
    }
    const tierColors: Record<string, string> = { gold: "#f9e2af", silver: "#bac2de", bronze: "#fab387" };
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {Object.entries(tiers).map(([t, c]) => (
            <Pill key={t} label={t} value={c} color={tierColors[t] ?? C.text} />
          ))}
        </div>
        {decisions.length > 0
          ? <MiniTable cols={["entity_id", "tier", "confidence", "reason"]} rows={decisions} />
          : entities.length > 0
            ? <MiniTable cols={["text", "semantic_tag", "tier"]} rows={entities} onRow={(i) => openInspector(["entities", i])} />
            : null}
      </div>
    );
  },
};

const verification: ProbeStrategy = {
  icon: "🔬",
  headline: (out) => {
    const verified = bool(out.is_verified);
    const result = isRec(out.verification_result) ? out.verification_result : {};
    const status = str(result.status, verified ? "passed" : "not verified");
    return verified ? `Verification passed — ${status}` : `Verification ${status}`;
  },
  Detail: ({ output, openInspector }) => {
    const verified = bool(output.is_verified);
    const result = isRec(output.verification_result) ? output.verification_result : null;
    const confidence = result && typeof result.confidence === "number" ? result.confidence : undefined;
    const corrections = result ? arr(result.corrections ?? result.changes ?? result.issues) : [];
    const reasons = result ? arr(result.reasons ?? result.errors) : [];
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <Verdict
          passed={verified}
          label={verified ? "Verification passed" : "Verification failed"}
          detail={reasons.length > 0 ? reasons.slice(0, 3).map(r => fmt(r)).join("; ") : undefined}
          confidence={confidence}
        />
        {corrections.length > 0 && (
          <div>
            <div style={{ color: C.orange, fontSize: 10, fontWeight: 700, marginBottom: 4 }}>
              {pl(corrections.length, "correction")} suggested
            </div>
            {corrections.slice(0, 5).map((c, i) => (
              <div key={i} style={{ color: C.text, fontSize: 10, padding: "2px 0" }}>
                • {isRec(c) ? fmt((c as Record<string, unknown>).text ?? (c as Record<string, unknown>).description ?? c) : fmt(c)}
              </div>
            ))}
          </div>
        )}
        {result && <InspectButton label="View full verification result" onClick={() => openInspector(["verification_result"])} />}
      </div>
    );
  },
};

const surfaceFormValidation: ProbeStrategy = {
  icon: "✏️",
  headline: (out) => {
    const entities = arr(out.entities);
    const mismatches = arr(out.surface_form_mismatches);
    const tasks = arr(out.surface_form_tasks_created);
    let h = `Checked ${pl(entities.length, "surface form")}`;
    if (mismatches.length > 0) h += ` — ${pl(mismatches.length, "mismatch", "mismatches")}`;
    if (tasks.length > 0) h += `, ${pl(tasks.length, "review task")}`;
    if (mismatches.length === 0 && tasks.length === 0) h += " — all OK";
    return h;
  },
  Detail: ({ output, input }) => {
    const mismatches = arr(output.surface_form_mismatches).filter(isRec) as Record<string, unknown>[];
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <EntityDelta input={input} output={output} />
        {mismatches.length > 0
          ? <MiniTable cols={["text", "expected_code", "actual_code", "action"]} rows={mismatches} />
          : <div style={{ color: C.green, fontSize: 10 }}>✓ All surface forms matched correctly.</div>}
      </div>
    );
  },
};

const compliance: ProbeStrategy = {
  icon: "📋",
  headline: (out) => {
    const result = isRec(out.compliance_result) ? out.compliance_result : {};
    const compliant = bool(result.is_compliant);
    const passed = num(result.passed_count);
    const failed = num(result.failed_count);
    return compliant
      ? `Compliant — all ${passed} checks passed`
      : `Not compliant — ${failed} of ${passed + failed} checks failed`;
  },
  Detail: ({ output, openInspector }) => {
    const result = isRec(output.compliance_result) ? output.compliance_result : {};
    const compliant = bool(result.is_compliant);
    const items = arr(result.items).filter(isRec) as Record<string, unknown>[];
    const failed = items.filter(i => !bool(i.passed) && !bool(i.is_compliant));
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <Verdict
          passed={compliant}
          label={compliant ? "Compliant" : "Not compliant"}
          detail={`${num(result.passed_count)} passed, ${num(result.failed_count)} failed`}
        />
        {failed.length > 0 && (
          <div>
            <div style={{ color: C.red, fontSize: 10, fontWeight: 700, marginBottom: 4 }}>Failed checks</div>
            {failed.slice(0, 5).map((item, i) => (
              <div key={i} style={{ color: C.text, fontSize: 10, padding: "2px 0" }}>
                ✗ {fmt(item.description ?? item.title ?? item.name ?? item.rule)}
              </div>
            ))}
          </div>
        )}
        {items.length > 0 && (
          <InspectButton label={`View all ${items.length} checks`} onClick={() => openInspector(["compliance_result"])} />
        )}
      </div>
    );
  },
};

const qualityCheck: ProbeStrategy = {
  icon: "🔎",
  headline: (out) => {
    const issues = arr(out.quality_issues);
    return issues.length === 0 ? "Quality check passed — no issues found" : `${pl(issues.length, "quality issue")} found`;
  },
  Detail: ({ output, openInspector }) => {
    const issues = arr(output.quality_issues).filter(isRec) as Record<string, unknown>[];
    if (issues.length === 0) return <Verdict passed label="Quality check passed" detail="No issues found" />;
    const sevCounts: Record<string, number> = {};
    for (const i of issues) { const s = str(i.severity, "info"); sevCounts[s] = (sevCounts[s] ?? 0) + 1; }
    const sevColors: Record<string, string> = { error: C.red, critical: C.red, warning: C.orange, info: C.blue };
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {Object.entries(sevCounts).map(([s, c]) => <Pill key={s} label={s} value={c} color={sevColors[s] ?? C.text} />)}
        </div>
        <MiniTable cols={["description", "severity", "field"]} rows={issues} onRow={(i) => openInspector(["quality_issues", i])} />
      </div>
    );
  },
};

const persist: ProbeStrategy = {
  icon: "💾",
  headline: (out) => {
    const docs = num(out.documents_written), labels = num(out.training_labels_written);
    const isDry = bool(out.dry_run);
    if (isDry) return "Test run — nothing actually saved (dry run)";
    if (docs > 0 || labels > 0) {
      const parts: string[] = [];
      if (docs > 0)    parts.push(pl(docs, "document"));
      if (labels > 0)  parts.push(pl(labels, "training label"));
      return `Saved ${parts.join(" and ")}`;
    }
    return "Nothing saved";
  },
  Detail: ({ output, input }) => {
    const docs    = num(output.documents_written);
    const labels  = num(output.training_labels_written);
    const isDry   = bool(output.dry_run);
    const target  = str(output.output_target);

    // New errors = errors that appeared after this step ran
    const prevErrs = arr(input.errors).map((e) => str(e));
    const allErrs  = arr(output.errors).map((e) => str(e));
    const newErrs  = allErrs.filter((e) => !prevErrs.includes(e));
    const oldErrs  = allErrs.filter((e) =>  prevErrs.includes(e));

    return (
      <div style={{ display: "grid", gap: 8 }}>
        {/* Summary pills */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {target && <Pill label="Target" value={target === "gold_training" ? "Knowledge Base" : target === "patient_graph" ? "Patient Records" : "Both"} color={C.blue} />}
          <Pill label="Documents" value={isDry ? "—" : docs} color={docs > 0 ? C.green : C.dim} />
          <Pill label="Labels"    value={isDry ? "—" : labels} color={labels > 0 ? C.green : C.dim} />
        </div>

        {/* Dry-run note */}
        {isDry && (
          <div style={{ fontSize: 10, color: C.orange, background: C.deep, borderRadius: 6, padding: "4px 8px", border: `1px solid ${C.border}` }}>
            ⚠ This is a test run — nothing was actually written to the database.
          </div>
        )}

        {/* New errors from this step */}
        {newErrs.length > 0 && (
          <div style={{ display: "grid", gap: 4 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.red }}>❌ {pl(newErrs.length, "error")} from this step</div>
            {newErrs.map((e, i) => (
              <div key={i} style={{ fontSize: 10, color: C.red, background: C.deep, borderRadius: 4, padding: "3px 6px", border: `1px solid ${C.border}`, wordBreak: "break-word" }}>
                {e}
              </div>
            ))}
          </div>
        )}

        {/* Pre-existing errors (from earlier steps) */}
        {oldErrs.length > 0 && (
          <div style={{ display: "grid", gap: 4 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.dim }}>⚠ {pl(oldErrs.length, "earlier error")} carried from previous steps</div>
            {oldErrs.map((e, i) => (
              <div key={i} style={{ fontSize: 10, color: C.dim, background: C.deep, borderRadius: 4, padding: "3px 6px", border: `1px solid ${C.border}`, wordBreak: "break-word" }}>
                {e}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  },
};

const sbar: ProbeStrategy = {
  icon: "📝",
  headline: (out) => {
    const report = isRec(out.sbar_report) ? out.sbar_report : {};
    const filled = ["situation", "background", "assessment", "recommendation"].filter(s => str(report[s]).length > 0);
    return filled.length === 4 ? "SBAR summary complete" : `SBAR summary — ${filled.length} of 4 sections filled`;
  },
  Detail: ({ output, openInspector }) => {
    const report = isRec(output.sbar_report) ? output.sbar_report : {};
    const sections = [
      { key: "situation", label: "Situation", color: C.blue },
      { key: "background", label: "Background", color: C.green },
      { key: "assessment", label: "Assessment", color: C.orange },
      { key: "recommendation", label: "Recommendation", color: C.purple },
    ];
    return (
      <div style={{ display: "grid", gap: 6 }}>
        {sections.map(({ key, label, color }) => {
          const text = str(report[key]);
          return text
            ? <SectionCard key={key} title={label} text={text} color={color} />
            : <div key={key} style={{ color: C.dim, fontSize: 10, padding: "3px 0" }}>{label}: not generated</div>;
        })}
        <InspectButton label="View full report" onClick={() => openInspector(["sbar_report"])} />
      </div>
    );
  },
};

const anchorDetect: ProbeStrategy = {
  icon: "⚓",
  headline: (out) => {
    const anchors = arr(out.anchors);
    return anchors.length > 0 ? `Detected ${pl(anchors.length, "key finding")}` : "No key findings detected";
  },
  Detail: ({ output, openInspector }) => {
    const anchors = arr(output.anchors).filter(isRec) as Record<string, unknown>[];
    if (anchors.length === 0) return <div style={{ color: C.dim, fontSize: 10 }}>No anchors detected in this data.</div>;
    return <MiniTable cols={["text", "type", "significance"]} rows={anchors} onRow={(i) => openInspector(["anchors", i])} />;
  },
};

const episodeBuild: ProbeStrategy = {
  icon: "📅",
  headline: (out) => {
    const episodes = arr(out.episodes);
    return episodes.length > 0 ? `Built ${pl(episodes.length, "episode")}` : "No episodes built";
  },
  Detail: ({ output, openInspector }) => {
    const episodes = arr(output.episodes).filter(isRec) as Record<string, unknown>[];
    if (episodes.length === 0) return <div style={{ color: C.dim, fontSize: 10 }}>No episodes generated.</div>;
    return <MiniTable cols={["episode_id", "type", "event_count"]} rows={episodes} onRow={(i) => openInspector(["episodes", i])} />;
  },
};

const safetyNet: ProbeStrategy = {
  icon: "🛡️",
  headline: (out) => {
    const alerts = arr(out.safety_net_alerts);
    return alerts.length > 0 ? `${pl(alerts.length, "safety alert")} flagged` : "No safety concerns found";
  },
  Detail: ({ output, openInspector }) => {
    const alerts = arr(output.safety_net_alerts).filter(isRec) as Record<string, unknown>[];
    if (alerts.length === 0) return <Verdict passed label="All clear" detail="No overdue actions or missing follow-ups" />;
    const sevColors: Record<string, string> = { high: C.red, medium: C.orange, low: C.blue };
    return (
      <div style={{ display: "grid", gap: 6 }}>
        {alerts.slice(0, 6).map((a, i) => {
          const sev = str(a.severity, "medium");
          return (
            <button key={i} type="button" onClick={() => openInspector(["safety_net_alerts", i])} style={{
              display: "flex", gap: 8, alignItems: "center",
              background: C.deep, border: `1px solid ${C.border}`, borderRadius: 8,
              padding: "6px 8px", cursor: "pointer", textAlign: "left",
            }}>
              <span style={{ color: sevColors[sev] ?? C.orange, fontSize: 10, fontWeight: 700, textTransform: "uppercase", minWidth: 40 }}>{sev}</span>
              <span style={{ color: C.text, fontSize: 10, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {fmt(a.description ?? a.text ?? a.message)}
              </span>
            </button>
          );
        })}
        {alerts.length > 6 && <div style={{ color: C.dim, fontSize: 10 }}>…{alerts.length - 6} more alerts</div>}
      </div>
    );
  },
};

const nextBestAction: ProbeStrategy = {
  icon: "🎯",
  headline: (out) => {
    const recs = arr(out.recommendations);
    return recs.length > 0 ? `${pl(recs.length, "recommendation")} generated` : "No recommendations";
  },
  Detail: ({ output, openInspector }) => {
    const recs = arr(output.recommendations).filter(isRec) as Record<string, unknown>[];
    if (recs.length === 0) return <div style={{ color: C.dim, fontSize: 10 }}>No recommendations generated.</div>;
    return (
      <div style={{ display: "grid", gap: 6 }}>
        {recs.slice(0, 5).map((r, i) => (
          <button key={i} type="button" onClick={() => openInspector(["recommendations", i])} style={{
            display: "flex", gap: 8, alignItems: "center",
            background: C.deep, border: `1px solid ${C.border}`, borderRadius: 8,
            padding: "6px 8px", cursor: "pointer", textAlign: "left",
          }}>
            <span style={{ color: C.purple, fontSize: 10, fontWeight: 700, minWidth: 16 }}>{i + 1}.</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: C.text, fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {fmt(r.action ?? r.recommendation ?? r.title)}
              </div>
              {r.reason && (
                <div style={{ color: C.dim, fontSize: 9, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {fmt(r.reason)}
                </div>
              )}
            </div>
            {r.priority && <span style={{ color: C.orange, fontSize: 9, fontWeight: 700 }}>{str(r.priority)}</span>}
          </button>
        ))}
      </div>
    );
  },
};

const restConnector: ProbeStrategy = {
  icon: "🔗",
  headline: (out) => {
    const resp = isRec(out.connector_response) ? out.connector_response : {};
    const status = num(resp.status_code ?? resp.status, 0);
    const errs = arr(out.errors);
    if (errs.length > 0) return `API call failed — ${pl(errs.length, "error")}`;
    return status > 0 ? `API call completed (${status})` : "API call completed";
  },
  Detail: ({ output, openInspector }) => {
    const resp = isRec(output.connector_response) ? output.connector_response : null;
    const errs = arr(output.errors);
    if (!resp && errs.length === 0) return <div style={{ color: C.dim, fontSize: 10 }}>No response data.</div>;
    const status = resp ? num(resp.status_code ?? resp.status, 0) : 0;
    const ok = status >= 200 && status < 300;
    return (
      <div style={{ display: "grid", gap: 8 }}>
        {resp && <Verdict passed={ok} label={ok ? `HTTP ${status} OK` : `HTTP ${status}`} detail={resp.url ? str(resp.url) : undefined} />}
        {errs.length > 0 && errs.slice(0, 3).map((e, i) => (
          <div key={i} style={{ color: C.red, fontSize: 10 }}>✗ {fmt(e)}</div>
        ))}
        {resp && <InspectButton label="View full response" onClick={() => openInspector(["connector_response"])} />}
      </div>
    );
  },
};

const queuePublish: ProbeStrategy = {
  icon: "📤",
  headline: (out) => {
    const queued = out.queued;
    const errs = arr(out.errors);
    if (errs.length > 0) return `Queue publish failed — ${pl(errs.length, "error")}`;
    return queued ? "Message published to queue" : "Queue publish completed";
  },
  Detail: ({ output }) => {
    const queued = output.queued;
    const errs = arr(output.errors);
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <Pill label="Status" value={queued ? "published" : "pending"} color={queued ? C.green : C.dim} />
        {errs.length > 0 && <Pill label="Errors" value={errs.length} color={C.red} />}
      </div>
    );
  },
};

function countLogicLeaves(node: unknown): number {
  if (!isRec(node)) return 0;
  const kind = str(node.kind).toUpperCase();
  if (kind === "CONCEPT") return 1;
  return arr(node.children).reduce((n, child) => n + countLogicLeaves(child), 0);
}

const guidanceRuleExtraction: ProbeStrategy = {
  icon: "📖",
  headline: (out) => {
    const coded = isRec(out.coded_criteria) ? out.coded_criteria : {};
    const logicTree = isRec(coded.logic_tree) ? coded.logic_tree : null;
    const leaves = countLogicLeaves(logicTree);
    return logicTree ? `Extracted logic tree (${pl(leaves, "criterion")})` : "Guidance rule extraction completed";
  },
  Detail: ({ output, openInspector }) => {
    const coded = isRec(output.coded_criteria) ? output.coded_criteria : {};
    const logicTree = isRec(coded.logic_tree) ? coded.logic_tree : null;
    const schemaVersion = num(coded.schema_version, 0);
    const leaves = countLogicLeaves(logicTree);
    const action = isRec(coded.action) ? coded.action : null;
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {schemaVersion > 0 && <Pill label="Schema" value={`v${schemaVersion}`} color={C.blue} />}
          {logicTree && <Pill label="Criteria leaves" value={leaves} color={C.green} />}
        </div>
        {action && <SectionCard title="Action" text={fmt(action.term ?? action.preferred_term ?? action.snomed_concept_id ?? action)} color={C.purple} />}
        {(logicTree || action) && (
          <InspectButton label="View full coded criteria" onClick={() => openInspector(["coded_criteria"])} />
        )}
        {!logicTree && !action && <div style={{ color: C.dim, fontSize: 10 }}>No structured criteria extracted.</div>}
      </div>
    );
  },
};

/* ── registry ───────────────────────────────────────────────────────── */

export const PROBE_STRATEGIES: Record<string, ProbeStrategy> = {
  extraction,
  post_processing: postProcessing,
  terminology,
  tier_classify: tierClassify,
  verification,
  surface_form_validation: surfaceFormValidation,
  compliance,
  quality_check: qualityCheck,
  persist,
  sbar,
  anchor_detect: anchorDetect,
  episode_build: episodeBuild,
  safety_net: safetyNet,
  next_best_action: nextBestAction,
  rest_connector: restConnector,
  queue_publish: queuePublish,
  guidance_rule_extraction: guidanceRuleExtraction,
};

/* ── target hint ────────────────────────────────────────────────────── */

/**
 * Fields that the pipeline engine injects from the step's OWN action config
 * (via _build_step_state) rather than needing to arrive from an upstream step.
 * Exclude these from the "missing inputs" wiring check so the probe doesn't
 * raise a false alarm about fields the step self-supplies.
 */
const CONFIG_INJECTED_FIELDS: Record<string, string[]> = {
  persist:    [],  // output_target is now derived from wiring (no longer needs suppression)
  extraction: ["prompt_config_id", "model_tier"],
  verification: ["prompt_config_id", "model_tier", "max_retries", "confidence_threshold"],
  sbar:         ["prompt_config_id", "model_tier"],
  compliance:   ["prompt_config_id", "model_tier"],
  anchor_detect: ["prompt_config_id", "model_tier"],
  episode_build: ["prompt_config_id", "model_tier"],
  next_best_action: ["prompt_config_id", "model_tier"],
  quality_check:    ["prompt_config_id", "model_tier"],
  guidance_rule_extraction: ["prompt_config_id", "model_tier"],
};

export function TargetHint({ targetSubgraphId, producedKeys }: {
  targetSubgraphId: string;
  producedKeys: string[];
}) {
  const io = SUBGRAPH_IO[targetSubgraphId];
  const option = SUBGRAPH_OPTIONS.find(o => o.id === targetSubgraphId);
  if (!io || !option) return null;
  const selfSupplied = new Set(CONFIG_INJECTED_FIELDS[targetSubgraphId] ?? []);
  const needs = io.reads.filter(k => k !== "*" && !selfSupplied.has(k));
  if (needs.length === 0) return null;
  const met = needs.filter(k => producedKeys.includes(k));
  const missing = needs.filter(k => !producedKeys.includes(k));
  return (
    <div style={{
      border: `1px solid ${missing.length > 0 ? C.orange : C.border}`,
      borderRadius: 8, padding: "6px 9px", background: C.bg, fontSize: 10,
    }}>
      <span style={{ color: C.dim }}>→ Next: </span>
      <span style={{ color: C.blue, fontWeight: 700 }}>{option.label}</span>
      {" — "}
      {missing.length > 0
        ? <span style={{ color: C.orange }}>needs {missing.join(", ")} (not found here)</span>
        : <span style={{ color: C.green }}>all {met.length} inputs ready</span>}
    </div>
  );
}

/* ── helper to resolve friendly label ───────────────────────────────── */

export function getSubgraphLabel(id: string): string {
  return SUBGRAPH_OPTIONS.find(o => o.id === id)?.label ?? id;
}
