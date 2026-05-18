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
 * Guidance + relation-linking probe strategies (Phase 6b-vi decomposition).
 *
 * Strategies covered:
 *   - guidanceRuleExtraction (clinical guidance -> coded criteria)
 *   - relationLinking        (entity relation graph build)
 *
 * Helpers:
 *   - countLogicLeaves       (recursive logic-tree leaf counter)
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  C,
  EntityDelta,
  InspectButton,
  MiniTable,
  Pill,
  SectionCard,
  arr,
  fmt,
  isRec,
  num,
  pl,
  str,
  type ProbeStrategy,
} from "./_shared";

export function countLogicLeaves(node: unknown): number {
  if (!isRec(node)) return 0;
  const kind = str(node.kind).toUpperCase();
  if (kind === "CONCEPT") return 1;
  return arr(node.children).reduce<number>((n, child) => n + countLogicLeaves(child), 0);
}

export const guidanceRuleExtraction: ProbeStrategy = {
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

export const relationLinking: ProbeStrategy = {
  icon: "🔗",
  headline: (out, inp) => {
    const before = arr(inp.entities).length;
    const after = arr(out.entities).length;
    const changes = arr(out.relation_changes).length;
    const errs = arr(out.errors).length;
    let h = `Linked relations on ${pl(before, "entity", "entities")}`;
    if (changes > 0) h += ` — ${pl(changes, "relation")} added`;
    if (before !== after) h += ` · ${before} → ${after} entities`;
    if (errs > 0) h += ` · ${pl(errs, "error")}`;
    return h;
  },
  Detail: ({ output, input, openInspector }) => {
    const entities = arr(output.entities).filter(isRec) as Record<string, unknown>[];
    const changes = arr(output.relation_changes).filter(isRec) as Record<string, unknown>[];
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <EntityDelta input={input} output={output} />
        {changes.length > 0 && (
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.purple, marginBottom: 4 }}>
              {pl(changes.length, "relation")} linked
            </div>
            <MiniTable
              cols={["source", "relation_type", "target"]}
              rows={changes}
            />
          </div>
        )}
        {entities.length > 0 && (
          <MiniTable
            cols={["text", "semantic_tag", "relations"]}
            rows={entities}
            onRow={(i) => openInspector(["entities", i])}
          />
        )}
      </div>
    );
  },
};
