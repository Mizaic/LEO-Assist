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
 * Verification-family probe strategies (Phase 6b-vi decomposition).
 *
 * Strategies covered:
 *   - verification         (LLM verifier with auto-correct loop)
 *   - surfaceFormValidation (surface form audit)
 *   - compliance           (rule-based compliance gate)
 *   - qualityCheck         (heuristic QA scan)
 *   - llmQualityCheck      (LLM-driven QA gate)
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  C,
  EntityDelta,
  InspectButton,
  MiniTable,
  Pill,
  Verdict,
  arr,
  bool,
  fmt,
  isRec,
  num,
  pct,
  pl,
  str,
  type ProbeStrategy,
} from "./_shared";

export const verification: ProbeStrategy = {
  icon: "🔬",
  headline: (out) => {
    const verified = bool(out.is_verified);
    const result = isRec(out.verification_result) ? out.verification_result : {};
    const attempts = arr(out.extraction_attempts);
    const passReason = str(result.pass_reason ?? "");
    if (verified) {
      if (passReason === "confidence_override") return `Verification passed (confidence override after ${attempts.length} attempt${attempts.length === 1 ? "" : "s"})`;
      if (attempts.length > 1) return `Verification passed (after ${attempts.length - 1} auto-correction${attempts.length - 1 === 1 ? "" : "s"})`;
      return "Verification passed";
    }
    if (attempts.length > 1) return `Verification not verified (${attempts.length} attempts)`;
    return "Verification not verified";
  },
  Detail: ({ output, openInspector }) => {
    const verified = bool(output.is_verified);
    const result = isRec(output.verification_result) ? output.verification_result : null;
    const promptMeta = isRec(output.verification_prompt) ? output.verification_prompt : null;
    const toolTrace = arr(output.verification_tool_trace);
    const confidence = result && typeof result.confidence === "number" ? result.confidence : undefined;
    const issues = result ? arr(result.issues) : [];
    const structuredCorrections = result ? arr(result.corrections) : [];
    const attempts = arr(output.extraction_attempts);
    const passReason = result ? str(result.pass_reason ?? "") : "";
    const correctionCount = Math.max(0, attempts.length - 1);
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <Verdict
          passed={verified}
          label={verified ? "Verification passed" : "Verification failed"}
          detail={issues.length > 0 ? issues.slice(0, 2).map(r => fmt(r)).join("; ") : undefined}
          confidence={confidence}
        />

        {promptMeta && (
          <div style={{ fontSize: 10, color: C.dim, background: C.deep, borderRadius: 6, padding: "4px 8px", border: `1px solid ${C.border}` }}>
            Prompt: {str(promptMeta.prompt_name, "unknown")}
            {promptMeta.prompt_version != null ? ` v${str(promptMeta.prompt_version)}` : ""}
            {" · "}
            {str(promptMeta.prompt_source, "unknown")}
          </div>
        )}

        {toolTrace.length > 0 && (
          <div style={{ fontSize: 10, color: C.dim, background: C.deep, borderRadius: 6, padding: "4px 8px", border: `1px solid ${C.border}` }}>
            SNOMED lookups used: {toolTrace.length}
          </div>
        )}

        {/* Auto-correction history */}
        {correctionCount > 0 && verified && passReason !== "confidence_override" && (
          <div style={{ fontSize: 10, color: C.green, background: C.deep, borderRadius: 6, padding: "4px 8px", border: `1px solid ${C.border}` }}>
            ✨ Auto-corrected {correctionCount} time{correctionCount === 1 ? "" : "s"} before passing.
          </div>
        )}
        {passReason === "confidence_override" && (
          <div style={{ fontSize: 10, color: C.orange, background: C.deep, borderRadius: 6, padding: "4px 8px", border: `1px solid ${C.border}` }}>
            ⚠ Passed via confidence override after {correctionCount} correction{correctionCount === 1 ? "" : "s"} — confidence {confidence != null ? pct(confidence) : "?"} ≥ threshold. Minor issues remain in the log.
          </div>
        )}
        {correctionCount > 0 && !verified && (
          <div style={{ fontSize: 10, color: C.red, background: C.deep, borderRadius: 6, padding: "4px 8px", border: `1px solid ${C.border}` }}>
            🔁 Retried {correctionCount} time{correctionCount === 1 ? "" : "s"} — still not verified.
          </div>
        )}

        {/* Structured corrections the verifier suggested */}
        {structuredCorrections.length > 0 && (
          <div>
            <div style={{ color: C.orange, fontSize: 10, fontWeight: 700, marginBottom: 4 }}>
              {pl(structuredCorrections.length, "correction")} applied to entities
            </div>
            {(structuredCorrections as Record<string, unknown>[]).slice(0, 8).map((c, i) => {
              if (c.drop) {
                return (
                  <div key={i} style={{ color: C.dim, fontSize: 10, padding: "2px 0" }}>
                    🗑 Entity {str(c.entity_index as unknown as string)}: <span style={{ fontStyle: "italic" }}>dropped — not SNOMED-representable</span>
                  </div>
                );
              }
              const parts: string[] = [];
              if (c.corrected_label) parts.push(`label → ${c.corrected_label}`);
              if (c.corrected_lookup_term) parts.push(`lookup → "${c.corrected_lookup_term}"`);
              if (c.corrected_assertion) parts.push(`assertion → ${c.corrected_assertion}`);
              return (
                <div key={i} style={{ color: C.text, fontSize: 10, padding: "2px 0" }}>
                  ✏ Entity {str(c.entity_index as unknown as string)}: {parts.join(", ") || "corrected"}
                </div>
              );
            })}
          </div>
        )}

        {/* Remaining issues */}
        {issues.length > 0 && (
          <div>
            <div style={{ color: C.dim, fontSize: 10, fontWeight: 700, marginBottom: 4 }}>Remaining issues</div>
            {issues.slice(0, 3).map((iss, i) => (
              <div key={i} style={{ color: C.dim, fontSize: 10, padding: "2px 0" }}>• {fmt(iss)}</div>
            ))}
          </div>
        )}

        {promptMeta && <InspectButton label="View prompt metadata" onClick={() => openInspector(["verification_prompt"])} />}
        {toolTrace.length > 0 && <InspectButton label="View SNOMED lookup trace" onClick={() => openInspector(["verification_tool_trace"])} />}
        {result && <InspectButton label="View full verification result" onClick={() => openInspector(["verification_result"])} />}
      </div>
    );
  },
};

export const surfaceFormValidation: ProbeStrategy = {
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

export const compliance: ProbeStrategy = {
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

export const qualityCheck: ProbeStrategy = {
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

export const llmQualityCheck: ProbeStrategy = {
  icon: "QA",
  headline: (out) => {
    const changes = arr(out.llm_check_changes);
    const result = isRec(out.llm_check_result) ? out.llm_check_result : {};
    const accepted = bool(result.accepted, true);
    if (changes.length === 0) {
      return accepted ? "Quality check passed -- no corrections needed" : "Quality check flagged issues";
    }
    return `Quality check applied ${pl(changes.length, "correction")}`;
  },
  Detail: ({ output, input, openInspector }) => {
    const changes = arr(output.llm_check_changes).filter(isRec) as Record<string, unknown>[];
    const result = isRec(output.llm_check_result) ? output.llm_check_result : null;
    const accepted = result ? bool(result.accepted, true) : true;
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <EntityDelta input={input} output={output} />
        <Verdict
          passed={accepted}
          label={accepted ? "Quality gate passed" : "Quality gate flagged issues"}
          detail={result ? str(result.summary, "") || undefined : undefined}
        />
        {changes.length > 0 ? (
          <MiniTable
            cols={["path", "before", "after", "reason"]}
            rows={changes}
            onRow={(i) => openInspector(["llm_check_changes", i])}
          />
        ) : (
          <div style={{ color: C.dim, fontSize: 10 }}>No structured corrections recorded for this run.</div>
        )}
        {result && (
          <InspectButton label="View full quality check result" onClick={() => openInspector(["llm_check_result"])} />
        )}
      </div>
    );
  },
};
