const u = {
  loaded: "leo:loaded",
  error: "leo:error",
  disclosureOpened: "leo:disclosure-opened",
  disclosureClosed: "leo:disclosure-closed",
  sourceClicked: "leo:source-clicked",
  /**
   * Fires before the widget renders when completeness findings show
   * missing or unclear fields. The host SHOULD show a confirmation dialog.
   */
  completenessIncomplete: "leo:completeness-incomplete",
  /**
   * Fires when no completeness findings are in the payload -- either
   * because the pipeline has not run the check yet, or no schema is
   * configured for this healthcare service.
   */
  completenessUnavailable: "leo:completeness-unavailable"
};
function A(e) {
  const s = (e.guideline_matches ?? []).map(
    (o) => ({
      ruleId: o.rule_id,
      name: o.name,
      strength: o.strength,
      guidelineId: o.guideline_id,
      recommendationVerbatim: o.recommendation_verbatim ?? null
    })
  ), t = e.completeness_findings;
  return {
    assessmentId: e.assessment_id,
    tenantId: e.tenant_id,
    generatedAt: e.generated_at,
    markdown: e.markdown,
    backgroundParts: e.background_parts ?? [],
    patientReferenceLabel: e.patient_reference_label,
    guidelineMatches: s,
    completenessFinding: t ?? null
  };
}
let I = null;
function re(e) {
  I = e;
}
function E(e) {
  try {
    return new URL(e).origin;
  } catch {
    throw new Error(
      `leo-widget: invalid proxy origin '${e}' (not a parseable URL)`
    );
  }
}
function C(e) {
  const s = E(e.proxyOrigin);
  if (!(e.allowedProxyOrigins ?? [e.proxyOrigin]).map(
    E
  ).includes(s))
    throw new Error("leo-widget: refusing to fetch from non-proxy origin");
  return s;
}
async function S(e) {
  const t = `${C(e)}/sdk/sbar/${encodeURIComponent(e.assessmentId)}`, o = await fetch(t, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${e.widgetToken}`,
      Accept: "application/json"
    },
    credentials: "omit",
    mode: "cors"
  });
  if (!o.ok)
    throw new Error(`leo-widget: assessment fetch failed (${o.status})`);
  const n = await o.json();
  return A(n);
}
async function O(e) {
  return (I ?? S)(e);
}
const p = Object.freeze({
  situation: Object.freeze({ accent: "#2563eb", tint: "#eff6ff", ink: "#1e3a8a" }),
  background: Object.freeze({ accent: "#7c3aed", tint: "#f5f3ff", ink: "#5b21b6" }),
  assessment: Object.freeze({ accent: "#d97706", tint: "#fffbeb", ink: "#92400e" }),
  recommendation: Object.freeze({ accent: "#0d9488", tint: "#f0fdfa", ink: "#115e59" })
}), r = Object.freeze({
  productName: "LEO by Mizaic",
  fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
  light: Object.freeze({
    background: "#ffffff",
    surface: "#ffffff",
    surfaceMuted: "#f8fafc",
    border: "#e2e8f0",
    text: "#0f172a",
    textMuted: "#475569",
    primary: "#1e3a8a",
    primaryInk: "#ffffff",
    warningBg: "#fef3c7",
    warningInk: "#92400e"
  }),
  dark: Object.freeze({
    background: "#0f172a",
    surface: "#111827",
    surfaceMuted: "#1f2937",
    border: "#374151",
    text: "#f8fafc",
    textMuted: "#cbd5f5",
    primary: "#60a5fa",
    primaryInk: "#0b1120",
    warningBg: "#78350f",
    warningInk: "#fde68a"
  })
}), R = '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="LEO by Mizaic"><rect width="64" height="64" rx="14" fill="currentColor"/><text x="32" y="40" text-anchor="middle" font-family="Inter, system-ui, sans-serif" font-weight="700" font-size="22" fill="#ffffff">LEO</text></svg>';
function z() {
  return `
:host {
  all: initial;
  display: block;
  font-family: ${r.fontFamily};
  color: ${r.light.text};
  background: ${r.light.background};
  line-height: 1.6;
  font-size: 14px;
  box-sizing: border-box;
}

*, *::before, *::after { box-sizing: border-box; }

/* Explicitly preserve browser text-formatting defaults inside the
   shadow root. Some environments with aggressive UA resets do not
   apply the UA bold/italic rules to shadow-DOM children. */
strong, b { font-weight: 700; }
em, i { font-style: italic; }

/* ------ Root card ------ */

.leo-root {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border: 1px solid ${r.light.border};
  border-radius: 12px;
  background: ${r.light.surface};
  box-shadow: 0 1px 3px 0 rgba(0,0,0,0.07), 0 1px 2px -1px rgba(0,0,0,0.05);
}

/* ------ Header ------ */

.leo-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid ${r.light.border};
  color: ${r.light.primary};
}

.leo-mark {
  width: 26px;
  height: 26px;
  flex: 0 0 auto;
  color: ${r.light.primary};
}

.leo-product {
  font-weight: 700;
  font-size: 13.5px;
  letter-spacing: 0.1px;
  flex: 1;
}

.leo-test-only {
  display: inline-block;
  background: ${r.light.warningBg};
  color: ${r.light.warningInk};
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1px;
  white-space: nowrap;
}

/* ------ Advisory banner ------ */

.leo-advisory {
  border: 1px solid ${r.light.warningInk};
  background: ${r.light.warningBg};
  color: ${r.light.warningInk};
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

/* ------ SBAR stage cards ------ */

.leo-stage {
  border: 1px solid ${r.light.border};
  border-left-width: 4px;
  border-radius: 8px;
  overflow: hidden;
  background: ${r.light.surface};
}

.leo-stage[data-stage="situation"]      { border-left-color: ${p.situation.accent}; }
.leo-stage[data-stage="background"]     { border-left-color: ${p.background.accent}; }
.leo-stage[data-stage="assessment"]     { border-left-color: ${p.assessment.accent}; }
.leo-stage[data-stage="recommendation"] { border-left-color: ${p.recommendation.accent}; }

.leo-stage-header {
  padding: 7px 14px;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.leo-stage[data-stage="situation"]      .leo-stage-header { background: ${p.situation.tint};      color: ${p.situation.ink}; }
.leo-stage[data-stage="background"]     .leo-stage-header { background: ${p.background.tint};     color: ${p.background.ink}; }
.leo-stage[data-stage="assessment"]     .leo-stage-header { background: ${p.assessment.tint};     color: ${p.assessment.ink}; }
.leo-stage[data-stage="recommendation"] .leo-stage-header { background: ${p.recommendation.tint}; color: ${p.recommendation.ink}; }

/* ------ Stage body (plain text) ------ */

.leo-stage-body {
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

/* ------ Stage body (markdown-rendered) ------ */

.leo-stage-body--md {
  padding: 6px 14px 12px;
}

.leo-stage-body--md .leo-md-p {
  margin: 7px 0;
  font-size: 13px;
  line-height: 1.6;
}

.leo-stage-body--md .leo-md-p:first-child { margin-top: 4px; }
.leo-stage-body--md .leo-md-p:last-child  { margin-bottom: 2px; }

/* Sub-section headings inside a stage body, e.g. ### Routine.
   Styled in each stage's ink colour so they read as in-context
   dividers rather than generic section labels. */
.leo-stage-body--md .leo-md-h {
  margin: 14px 0 5px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: ${r.light.textMuted};
}

.leo-stage-body--md .leo-md-h:first-child { margin-top: 6px; }

.leo-stage[data-stage="situation"]      .leo-stage-body--md .leo-md-h { color: ${p.situation.ink}; }
.leo-stage[data-stage="background"]     .leo-stage-body--md .leo-md-h { color: ${p.background.ink}; }
.leo-stage[data-stage="assessment"]     .leo-stage-body--md .leo-md-h { color: ${p.assessment.ink}; }
.leo-stage[data-stage="recommendation"] .leo-stage-body--md .leo-md-h { color: ${p.recommendation.ink}; }

/* Top-level list (rule bullets, background bullets) */
.leo-stage-body--md .leo-md-list {
  margin: 6px 0;
  padding-left: 20px;
  list-style: disc;
}

/* Nested list (Recommendation / Matched on / Action / Guideline) */
.leo-stage-body--md .leo-md-list .leo-md-list {
  margin: 3px 0;
  padding-left: 14px;
  list-style: circle;
}

/* Third level (rare) */
.leo-stage-body--md .leo-md-list .leo-md-list .leo-md-list {
  list-style: square;
}

/* Top-level items: body size, with room between rules */
.leo-stage-body--md .leo-md-list > .leo-md-item {
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.55;
}

/* Nested items: smaller, muted -- contextual detail */
.leo-stage-body--md .leo-md-list .leo-md-list > .leo-md-item {
  margin: 3px 0;
  font-size: 12px;
  color: ${r.light.textMuted};
  line-height: 1.5;
}

/*
 * SAFETY-CRITICAL: the source-record disclosure mitigates R-4965BCD2.
 * It MUST be visible whenever the host renders the widget. The
 * !important rules below are defence-in-depth on top of the closed
 * shadow root (web component) and the cross-origin frame (iframe).
 */
.leo-disclosure[data-leo-disclosure="source-records"] {
  display: block !important;
  visibility: visible !important;
  opacity: 1 !important;
  transform: none !important;
  pointer-events: auto !important;
  padding: 6px 14px 10px 14px;
}

.leo-disclosure-toggle {
  appearance: none;
  background: none;
  border: 0;
  padding: 0;
  font: inherit;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
  text-decoration: underline;
  color: ${r.light.primary};
}

.leo-disclosure-toggle:focus-visible {
  outline: 2px solid ${r.light.primary};
  outline-offset: 2px;
  border-radius: 2px;
}

.leo-disclosure-panel {
  margin-top: 8px;
  display: none;
  flex-direction: column;
  gap: 8px;
}

.leo-disclosure[data-open="true"] .leo-disclosure-panel {
  display: flex;
}

.leo-source-part-label {
  font-size: 11px;
  color: ${r.light.textMuted};
  margin-bottom: 4px;
  display: block;
}

.leo-source-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.leo-source-chip {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  border: 1px solid ${r.light.border};
  border-radius: 999px;
  padding: 2px 8px;
  background: ${r.light.surfaceMuted};
  color: ${r.light.text};
  cursor: pointer;
}

.leo-source-chip:focus-visible {
  outline: 2px solid ${r.light.primary};
  outline-offset: 2px;
}


/* ------ Completeness panel ------ */

.leo-completeness {
  border: 1px solid ${r.light.border};
  border-left: 4px solid #6366f1;
  border-radius: 8px;
  overflow: hidden;
  background: ${r.light.surface};
}

.leo-field-list {
  list-style: none;
  margin: 0;
  padding: 8px 14px 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.leo-field {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 500;
}

.leo-field--present { background: #f0fdf4; color: #14532d; border: 1px solid #bbf7d0; }
.leo-field--missing { background: #fef2f2; color: #7f1d1d; border: 1px solid #fecaca; }
.leo-field--unclear { background: #fffbeb; color: #78350f; border: 1px solid #fed7aa; }

/* ------ Empty / error states ------ */

.leo-empty {
  font-size: 12.5px;
  color: ${r.light.textMuted};
  padding: 4px 0;
}

.leo-error {
  border: 1px solid #b91c1c;
  background: #fef2f2;
  color: #7f1d1d;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
}

/* ------ Dark mode ------ */

@media (prefers-color-scheme: dark) {
  :host {
    color: ${r.dark.text};
    background: ${r.dark.background};
  }

  .leo-root {
    border-color: ${r.dark.border};
    background: ${r.dark.surface};
    box-shadow: none;
  }

  .leo-header {
    color: ${r.dark.primary};
    border-bottom-color: ${r.dark.border};
  }

  .leo-mark { color: ${r.dark.primary}; }

  .leo-test-only {
    background: ${r.dark.warningBg};
    color: ${r.dark.warningInk};
  }

  .leo-stage {
    background: ${r.dark.surface};
    border-color: ${r.dark.border};
  }

  .leo-stage-body { color: ${r.dark.text}; }

  .leo-stage-body--md .leo-md-h { color: ${r.dark.textMuted}; }

  .leo-stage[data-stage="situation"]      .leo-stage-body--md .leo-md-h { color: ${p.situation.tint}; }
  .leo-stage[data-stage="background"]     .leo-stage-body--md .leo-md-h { color: ${p.background.tint}; }
  .leo-stage[data-stage="assessment"]     .leo-stage-body--md .leo-md-h { color: ${p.assessment.tint}; }
  .leo-stage[data-stage="recommendation"] .leo-stage-body--md .leo-md-h { color: ${p.recommendation.tint}; }

  .leo-stage-body--md .leo-md-list .leo-md-list > .leo-md-item { color: ${r.dark.textMuted}; }

  .leo-source-chip {
    background: ${r.dark.surfaceMuted};
    color: ${r.dark.text};
    border-color: ${r.dark.border};
  }

  .leo-disclosure-toggle { color: ${r.dark.primary}; }

  .leo-empty, .leo-source-part-label { color: ${r.dark.textMuted}; }

  .leo-completeness {
    border-color: ${r.dark.border};
    background: ${r.dark.surface};
  }
}
`.trim();
}
const M = [
  "situation",
  "background",
  "assessment",
  "recommendation"
], T = new Set(M), L = /^##\s+(.+?)\s*$/, N = /^[ \t]*<!--\s*sources:\s*[^>]*?-->[ \t]*\r?\n?/gm, F = /<!--\s*sources:\s*[^>]*?-->/g;
function j(e) {
  return e && e.replace(N, "").replace(F, "");
}
function B(e) {
  const s = (e ?? "").split(/\r?\n/), t = /* @__PURE__ */ new Map();
  let o = null;
  for (const n of s) {
    const i = L.exec(n);
    if (i && i[1]) {
      const a = i[1].trim().toLowerCase();
      if (T.has(a)) {
        o = a, t.has(o) || t.set(o, []);
        continue;
      }
      o = null;
      continue;
    }
    o && t.get(o).push(n);
  }
  return M.filter((n) => t.has(n)).map((n) => ({
    stage: n,
    body: (t.get(n) ?? []).join(`
`).trim()
  }));
}
function H(e, s) {
  return e <= 0 || s <= 0 ? "no records" : e === s ? `record ${e}` : `records ${e}-${s}`;
}
function U(e) {
  const s = H(
    e.recordRange?.[0] ?? 0,
    e.recordRange?.[1] ?? 0
  );
  return `Part ${e.index} of ${e.total} -- ${s}`;
}
function h(e) {
  return e.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function D({ stage: e, parts: s }) {
  const t = s.reduce((n, i) => n + i.sourceIds.length, 0);
  if (t === 0) return "";
  const o = s.filter((n) => n.sourceIds.length > 0).map((n, i) => {
    const a = n.sourceIds.map(
      (c) => `<button type="button" class="leo-source-chip" data-source-id="${h(c)}" data-stage="${e}" aria-label="Open source record ${h(c)}">${h(c)}</button>`
    ).join(""), l = n.status === "failed" ? " -- this part did not finish" : "";
    return `<div class="leo-source-part" data-testid="leo-disclosure-${e}-part-${i}"><span class="leo-source-part-label">${h(U(n))}${h(l)}</span><div class="leo-source-chips">${a}</div></div>`;
  }).join("");
  return `<div class="leo-disclosure" data-leo-disclosure="source-records" data-stage="${e}" data-open="false" data-testid="leo-disclosure-${e}"><button type="button" class="leo-disclosure-toggle" data-leo-toggle="${e}" aria-expanded="false" data-testid="leo-disclosure-${e}-toggle">Show source records (${t})</button><div class="leo-disclosure-panel">${o}</div></div>`;
}
function q(e, s) {
  function t(n) {
    const i = n.target;
    if (!(i instanceof HTMLElement)) return;
    const a = i.closest("[data-leo-toggle]");
    if (a) {
      const c = a.getAttribute("data-leo-toggle"), g = a.closest(".leo-disclosure");
      if (!g) return;
      const d = !(g.getAttribute("data-open") === "true");
      g.setAttribute("data-open", d ? "true" : "false"), a.setAttribute("aria-expanded", d ? "true" : "false");
      const f = d ? a.textContent?.replace(/^Show /, "Hide ") : a.textContent?.replace(/^Hide /, "Show ");
      f && (a.textContent = f), d ? s.onOpen({ stage: c }) : s.onClose({ stage: c });
      return;
    }
    const l = i.closest(".leo-source-chip");
    if (l) {
      const c = l.getAttribute("data-stage"), g = l.getAttribute("data-source-id") ?? "";
      s.onSourceClicked({ stage: c, sourceId: g });
    }
  }
  const o = e;
  return o.addEventListener("click", t), () => o.removeEventListener("click", t);
}
const G = /\[RULE:\s*[^\]]+\]/g, P = /^(#{2,4})\s+(.+)$/, V = /^(\s*)[-*]\s+(.+)$/;
function W(e) {
  return e.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function k(e) {
  return W(e).replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/_([^_\s][^_]*[^_\s]|[^_\s])_/g, "<em>$1</em>").replace(/\*([^*\s][^*]*[^*\s]|[^*\s])\*/g, "<em>$1</em>");
}
function K(e) {
  const t = e.replace(G, "").trim().split(/\r?\n/), o = [];
  let n = [], i = [];
  function a() {
    const c = n.map((g) => g.trim()).filter(Boolean).join(" ");
    c && o.push({ type: "paragraph", text: c }), n = [];
  }
  function l() {
    i.length > 0 && (o.push({ type: "list", items: i }), i = []);
  }
  for (const c of t) {
    const g = c.trim();
    if (!g) {
      a(), l();
      continue;
    }
    const m = P.exec(g);
    if (m) {
      a(), l(), o.push({
        type: "heading",
        level: (m[1] ?? "##").length,
        text: m[2] ?? ""
      });
      continue;
    }
    const d = V.exec(c);
    if (d) {
      a();
      const f = (d[1] ?? "").length;
      i.push({ indent: f, text: d[2] ?? "" });
      continue;
    }
    l(), n.push(g);
  }
  return a(), l(), o;
}
function $(e, s, t) {
  let o = '<ul class="leo-md-list">';
  for (; t.current < e.length; ) {
    const n = e[t.current];
    if (n.indent < s) break;
    if (n.indent > s) {
      o += $(e, n.indent, t);
      continue;
    }
    t.current++;
    let i = `<li class="leo-md-item">${k(n.text)}`;
    const a = e[t.current];
    a !== void 0 && a.indent > s && (i += $(e, a.indent, t)), i += "</li>", o += i;
  }
  return o += "</ul>", o;
}
function Y(e) {
  if (!e) return "";
  const s = K(e), t = [];
  for (const o of s)
    if (o.type === "heading") {
      const n = `h${Math.min(o.level ?? 3, 6)}`;
      t.push(
        `<${n} class="leo-md-h">${k(o.text ?? "")}</${n}>`
      );
    } else if (o.type === "list" && o.items && o.items.length > 0) {
      const n = o.items[0].indent, i = { current: 0 };
      t.push($(o.items, n, i));
    } else o.type === "paragraph" && t.push(`<p class="leo-md-p">${k(o.text ?? "")}</p>`);
  return t.join(`
`);
}
const Z = {
  situation: "Situation",
  background: "Background",
  assessment: "Assessment",
  recommendation: "Recommendation"
};
function x(e) {
  return e.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function J(e, s) {
  const t = Y(j(e.body)), o = D({
    stage: e.stage,
    parts: s[e.stage] ?? []
  });
  return `<section class="leo-stage" data-stage="${e.stage}" data-testid="leo-stage-${e.stage}"><header class="leo-stage-header">${Z[e.stage]}</header><div class="leo-stage-body leo-stage-body--md">${t}</div>` + o + "</section>";
}
function Q(e) {
  return `<header class="leo-header" data-testid="leo-header"><span class="leo-mark">${R}</span><span class="leo-product">LEO by Mizaic</span><span class="leo-test-only" data-testid="leo-test-only-banner">Test only -- not for clinical use</span></header>`;
}
function X(e) {
  return e ? `<div class="leo-advisory" role="alert" data-testid="leo-advisory">${x(e)}</div>` : "";
}
function ee(e) {
  if (!e) return "";
  const s = [
    ...e.presentFields.map(
      (t) => `<li class="leo-field leo-field--present" data-testid="leo-field-present">${x(t)}</li>`
    ),
    ...e.missingFields.map(
      (t) => `<li class="leo-field leo-field--missing" data-testid="leo-field-missing">${x(t)}</li>`
    ),
    ...e.unclearFields.map(
      (t) => `<li class="leo-field leo-field--unclear" data-testid="leo-field-unclear">${x(t)}</li>`
    )
  ];
  return s.length === 0 ? "" : `<section class="leo-completeness" data-testid="leo-completeness"><header class="leo-stage-header">Referral completeness</header><ul class="leo-field-list">${s.join("")}</ul></section>`;
}
function te(e, s) {
  const t = e.completenessFinding;
  if (t == null) {
    s({
      type: u.completenessUnavailable,
      detail: { assessmentId: e.assessmentId }
    });
    return;
  }
  const o = t.missingFields.length > 0, n = t.unclearFields.length > 0;
  (o || n) && s({
    type: u.completenessIncomplete,
    detail: {
      assessmentId: e.assessmentId,
      missingFields: t.missingFields,
      unclearFields: t.unclearFields
    }
  });
}
function oe(e, s) {
  const { payload: t, emit: o, advisory: n } = s;
  te(t, o);
  const i = B(t.markdown ?? ""), a = {
    situation: [],
    background: t.backgroundParts ?? [],
    assessment: [],
    recommendation: []
  };
  let l = "";
  l += Q(), l += X(n ?? null), l += ee(t.completenessFinding), i.length === 0 ? l += '<div class="leo-empty" data-testid="leo-empty">No SBAR content yet.</div>' : l += i.map((d) => J(d, a)).join("");
  const c = e.querySelector?.(".leo-root") ?? null;
  let g;
  if (c)
    g = c;
  else {
    const d = (e.ownerDocument ?? document).createElement("div");
    d.className = "leo-root", d.setAttribute("data-testid", "leo-root"), d.setAttribute("data-assessment-id", t.assessmentId), e.appendChild(d), g = d;
  }
  g.innerHTML = l;
  const m = q(g, {
    onOpen: ({ stage: d }) => o({
      type: u.disclosureOpened,
      detail: { assessmentId: t.assessmentId, stage: d }
    }),
    onClose: ({ stage: d }) => o({
      type: u.disclosureClosed,
      detail: { assessmentId: t.assessmentId, stage: d }
    }),
    onSourceClicked: ({ stage: d, sourceId: f }) => o({
      type: u.sourceClicked,
      detail: { assessmentId: t.assessmentId, stage: d, sourceId: f }
    })
  });
  return o({
    type: u.loaded,
    detail: { assessmentId: t.assessmentId }
  }), m;
}
const _ = "leo-sbar", y = /* @__PURE__ */ new WeakMap(), b = /* @__PURE__ */ new WeakMap(), v = class v extends HTMLElement {
  constructor() {
    super();
    const s = this.attachShadow({ mode: "closed" });
    y.set(this, s);
    const t = document.createElement("style");
    t.textContent = z(), s.appendChild(t);
  }
  connectedCallback() {
    this._refresh();
  }
  disconnectedCallback() {
    const s = b.get(this);
    s && s(), b.delete(this);
  }
  attributeChangedCallback() {
    this.isConnected && this._refresh();
  }
  _emit(s) {
    this.dispatchEvent(
      new CustomEvent(s.type, {
        detail: s.detail,
        bubbles: !0,
        composed: !0
      })
    );
  }
  async _refresh() {
    const s = y.get(this);
    if (!s) return;
    const t = this.getAttribute("assessment-id") ?? "", o = this.getAttribute("widget-token") ?? "", n = this.getAttribute("proxy-origin") ?? window.location.origin, i = this.getAttribute("advisory");
    if (!t || !o) {
      this._renderError(
        "Missing required attributes: assessment-id, widget-token."
      );
      return;
    }
    try {
      const a = await O({
        assessmentId: t,
        widgetToken: o,
        proxyOrigin: n
      }), l = oe(s, {
        payload: a,
        advisory: i,
        emit: (g) => this._emit({ type: g.type, detail: g.detail })
      }), c = b.get(this);
      c && c(), b.set(this, l), this.setAttribute("data-leo-state", "loaded");
    } catch (a) {
      const l = a instanceof Error ? a.message : String(a);
      this._renderError(l), this._emit({
        type: u.error,
        detail: { assessmentId: t, errorMessage: l }
      });
    }
  }
  _renderError(s) {
    const t = y.get(this);
    if (!t) return;
    let o = t.querySelector(".leo-root");
    o || (o = document.createElement("div"), o.className = "leo-root", t.appendChild(o)), o.innerHTML = '<div class="leo-error" role="alert" data-testid="leo-error">' + s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") + "</div>";
  }
};
v.observedAttributes = [
  "assessment-id",
  "widget-token",
  "proxy-origin",
  "advisory"
];
let w = v;
function se() {
  typeof customElements > "u" || customElements.get(_) || customElements.define(_, w);
}
se();
export {
  u as LEO_EVENT_NAMES,
  w as LeoSbarElement,
  re as configureFetcher,
  O as fetchAssessment,
  se as registerLeoSbarElement
};
//# sourceMappingURL=leo-widget.js.map
