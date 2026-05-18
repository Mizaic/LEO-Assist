/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

/**
 * Extraction-family probe strategies (Phase 6b-vi decomposition).
 *
 * Strategies covered:
 *   - extraction          (raw NER -> entities)
 *   - postProcessing      (post-processing layer trace)
 *   - terminology         (SNOMED CT coding)
 *   - tierClassify        (gold/silver/bronze grading)
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  C,
  EntityDelta,
  LayerTraceTable,
  MiniTable,
  Pill,
  arr,
  asLayerTrace,
  isRec,
  pl,
  str,
  type ProbeStrategy,
} from "./_shared";

export const extraction: ProbeStrategy = {
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

export const postProcessing: ProbeStrategy = {
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

export const terminology: ProbeStrategy = {
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

export const tierClassify: ProbeStrategy = {
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
