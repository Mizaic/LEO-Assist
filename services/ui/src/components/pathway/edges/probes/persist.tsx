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
 * Persist + downstream probe strategies (Phase 6b-vi decomposition).
 *
 * Strategies covered:
 *   - persist          (write documents / training labels)
 *   - sbar             (Situation/Background/Assessment/Recommendation)
 *   - anchorDetect     (key clinical findings)
 *   - episodeBuild     (episode-of-care fusion)
 *   - safetyNet        (overdue / missing follow-up alerts)
 *   - nextBestAction   (recommendation engine)
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  C,
  InspectButton,
  MiniTable,
  Pill,
  SectionCard,
  Verdict,
  arr,
  bool,
  fmt,
  isRec,
  num,
  pl,
  str,
  type ProbeStrategy,
} from "./_shared";

export const persist: ProbeStrategy = {
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

    const prevErrs = arr(input.errors).map((e) => str(e));
    const allErrs  = arr(output.errors).map((e) => str(e));
    const newErrs  = allErrs.filter((e) => !prevErrs.includes(e));
    const oldErrs  = allErrs.filter((e) =>  prevErrs.includes(e));

    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {target && <Pill label="Target" value={target === "gold_training" ? "Knowledge Base" : target === "patient_graph" ? "Patient Records" : "Both"} color={C.blue} />}
          <Pill label="Documents" value={isDry ? "—" : docs} color={docs > 0 ? C.green : C.dim} />
          <Pill label="Labels"    value={isDry ? "—" : labels} color={labels > 0 ? C.green : C.dim} />
        </div>

        {isDry && (
          <div style={{ fontSize: 10, color: C.orange, background: C.deep, borderRadius: 6, padding: "4px 8px", border: `1px solid ${C.border}` }}>
            ⚠ This is a test run — nothing was actually written to the database.
          </div>
        )}

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

export const sbar: ProbeStrategy = {
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

export const anchorDetect: ProbeStrategy = {
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

export const episodeBuild: ProbeStrategy = {
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

export const episodeEngine: ProbeStrategy = {
  icon: "🤖",
  headline: (out) => {
    const episodes = arr(out.written_episodes);
    return episodes.length > 0
      ? `AI found ${pl(episodes.length, "episode")}`
      : "No episodes detected by the AI";
  },
  Detail: ({ output, openInspector }) => {
    const episodes = arr(output.written_episodes).filter(isRec) as Record<string, unknown>[];
    if (episodes.length === 0) {
      return (
        <div style={{ color: C.dim, fontSize: 10 }}>
          The AI agent chain found no episodes for this patient.
        </div>
      );
    }
    return (
      <MiniTable
        cols={["episode_id", "episode_type", "suspected_site", "confidence"]}
        rows={episodes}
        onRow={(i) => openInspector(["written_episodes", i])}
      />
    );
  },
};

export const safetyNet: ProbeStrategy = {
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

export const nextBestAction: ProbeStrategy = {
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
              {Boolean(r.reason) && (
                <div style={{ color: C.dim, fontSize: 9, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {fmt(r.reason)}
                </div>
              )}
            </div>
            {Boolean(r.priority) && <span style={{ color: C.orange, fontSize: 9, fontWeight: 700 }}>{str(r.priority)}</span>}
          </button>
        ))}
      </div>
    );
  },
};
