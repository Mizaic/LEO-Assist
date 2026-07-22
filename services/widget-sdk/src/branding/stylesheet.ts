/**
 * Compiled stylesheet for the LEO widget trust boundary.
 *
 * Atlas trace:
 *   DI: DI-85944331 (locked branding plus reactive light/dark)
 *   DI: DI-85C95E53 (closed shadow root prevents host-CSS bleed)
 *
 * Returned as a string and adopted via CSSStyleSheet inside the
 * shadow root. Identical CSS is inlined into the iframe variant.
 *
 * The disclosure rule below uses ``!important`` plus an attribute
 * selector that the host cannot reach. Even if the host could reach
 * it, the closed shadow root and the cross-origin iframe make a host
 * stylesheet invisible to these selectors. The ``!important``
 * provides defence-in-depth for the iframe-without-CSP edge case.
 */

import { BRAND, STAGE_THEME } from "./tokens";

export function buildShadowStylesheet(): string {
  return `
:host {
  all: initial;
  display: block;
  font-family: ${BRAND.fontFamily};
  color: ${BRAND.light.text};
  background: ${BRAND.light.background};
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
  border: 1px solid ${BRAND.light.border};
  border-radius: 12px;
  background: ${BRAND.light.surface};
  box-shadow: 0 1px 3px 0 rgba(0,0,0,0.07), 0 1px 2px -1px rgba(0,0,0,0.05);
}

/* ------ Header ------ */

.leo-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid ${BRAND.light.border};
  color: ${BRAND.light.primary};
}

.leo-mark {
  width: 26px;
  height: 26px;
  flex: 0 0 auto;
  color: ${BRAND.light.primary};
}

.leo-product {
  font-weight: 700;
  font-size: 13.5px;
  letter-spacing: 0.1px;
  flex: 1;
}

/* ------ AI-generated advisory disclaimer (persistent, non-dismissible) ------ */

.leo-ai-disclaimer {
  border: 1px solid #3b82f6;
  background: #eff6ff;
  color: #1e3a8a;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
}

/* ------ Advisory banner (CSO safety advisory, escalated notices) ------ */

.leo-advisory {
  border: 1px solid ${BRAND.light.warningInk};
  background: ${BRAND.light.warningBg};
  color: ${BRAND.light.warningInk};
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

/* ------ SBAR stage cards ------ */

.leo-stage {
  border: 1px solid ${BRAND.light.border};
  border-left-width: 4px;
  border-radius: 8px;
  overflow: hidden;
  background: ${BRAND.light.surface};
}

.leo-stage[data-stage="situation"]      { border-left-color: ${STAGE_THEME.situation.accent}; }
.leo-stage[data-stage="background"]     { border-left-color: ${STAGE_THEME.background.accent}; }
.leo-stage[data-stage="assessment"]     { border-left-color: ${STAGE_THEME.assessment.accent}; }
.leo-stage[data-stage="recommendation"] { border-left-color: ${STAGE_THEME.recommendation.accent}; }

.leo-stage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 14px;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.leo-stage-label {
  flex: 1;
}

/* ------ Completeness chip (inline in Background header) ------ */

.leo-completeness-chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1px;
  cursor: default;
  text-transform: none;
}

.leo-completeness-chip--green {
  background: #f0fdf4;
  color: #14532d;
  border: 1px solid #bbf7d0;
}

.leo-completeness-chip--amber {
  background: #fffbeb;
  color: #78350f;
  border: 1px solid #fed7aa;
}

.leo-completeness-chip--red {
  background: #fef2f2;
  color: #7f1d1d;
  border: 1px solid #fecaca;
}

.leo-stage[data-stage="situation"]      .leo-stage-header { background: ${STAGE_THEME.situation.tint};      color: ${STAGE_THEME.situation.ink}; }
.leo-stage[data-stage="background"]     .leo-stage-header { background: ${STAGE_THEME.background.tint};     color: ${STAGE_THEME.background.ink}; }
.leo-stage[data-stage="assessment"]     .leo-stage-header { background: ${STAGE_THEME.assessment.tint};     color: ${STAGE_THEME.assessment.ink}; }
.leo-stage[data-stage="recommendation"] .leo-stage-header { background: ${STAGE_THEME.recommendation.tint}; color: ${STAGE_THEME.recommendation.ink}; }

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
  color: ${BRAND.light.textMuted};
}

.leo-stage-body--md .leo-md-h:first-child { margin-top: 6px; }

.leo-stage[data-stage="situation"]      .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.situation.ink}; }
.leo-stage[data-stage="background"]     .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.background.ink}; }
.leo-stage[data-stage="assessment"]     .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.assessment.ink}; }
.leo-stage[data-stage="recommendation"] .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.recommendation.ink}; }

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
  color: ${BRAND.light.textMuted};
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
  color: ${BRAND.light.primary};
}

.leo-disclosure-toggle:focus-visible {
  outline: 2px solid ${BRAND.light.primary};
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
  color: ${BRAND.light.textMuted};
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
  border: 1px solid ${BRAND.light.border};
  border-radius: 999px;
  padding: 2px 8px;
  background: ${BRAND.light.surfaceMuted};
  color: ${BRAND.light.text};
  cursor: pointer;
}

.leo-source-chip:focus-visible {
  outline: 2px solid ${BRAND.light.primary};
  outline-offset: 2px;
}

.leo-source-dialog {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 40;
  padding: 16px;
}

.leo-source-dialog-card {
  background: ${BRAND.light.surface};
  color: ${BRAND.light.text};
  border-radius: 12px;
  max-width: 560px;
  width: 100%;
  max-height: 80vh;
  overflow: auto;
  padding: 16px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.2);
}

.leo-source-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.leo-source-dialog-close {
  border: 1px solid ${BRAND.light.border};
  background: ${BRAND.light.surfaceMuted};
  border-radius: 8px;
  padding: 4px 10px;
  cursor: pointer;
}

.leo-source-dialog-meta {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: ${BRAND.light.textMuted};
  margin: 0 0 8px;
}

.leo-source-dialog-note {
  font-size: 12px;
  font-style: italic;
  color: ${BRAND.light.textMuted};
  margin: 0 0 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid ${BRAND.light.border};
}

.leo-source-dialog-body {
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.55;
  margin: 0;
}


/* ------ Completeness panel ------ */

.leo-completeness {
  border: 1px solid ${BRAND.light.border};
  border-left: 4px solid #6366f1;
  border-radius: 8px;
  overflow: hidden;
  background: ${BRAND.light.surface};
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
  color: ${BRAND.light.textMuted};
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
    color: ${BRAND.dark.text};
    background: ${BRAND.dark.background};
  }

  .leo-root {
    border-color: ${BRAND.dark.border};
    background: ${BRAND.dark.surface};
    box-shadow: none;
  }

  .leo-header {
    color: ${BRAND.dark.primary};
    border-bottom-color: ${BRAND.dark.border};
  }

  .leo-mark { color: ${BRAND.dark.primary}; }

  .leo-ai-disclaimer {
    border-color: #1d4ed8;
    background: #1e3a8a;
    color: #bfdbfe;
  }

  .leo-stage {
    background: ${BRAND.dark.surface};
    border-color: ${BRAND.dark.border};
  }

  .leo-stage-body { color: ${BRAND.dark.text}; }

  .leo-stage-body--md .leo-md-h { color: ${BRAND.dark.textMuted}; }

  .leo-stage[data-stage="situation"]      .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.situation.tint}; }
  .leo-stage[data-stage="background"]     .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.background.tint}; }
  .leo-stage[data-stage="assessment"]     .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.assessment.tint}; }
  .leo-stage[data-stage="recommendation"] .leo-stage-body--md .leo-md-h { color: ${STAGE_THEME.recommendation.tint}; }

  .leo-stage-body--md .leo-md-list .leo-md-list > .leo-md-item { color: ${BRAND.dark.textMuted}; }

  .leo-source-chip {
    background: ${BRAND.dark.surfaceMuted};
    color: ${BRAND.dark.text};
    border-color: ${BRAND.dark.border};
  }

  .leo-disclosure-toggle { color: ${BRAND.dark.primary}; }

  .leo-empty, .leo-source-part-label { color: ${BRAND.dark.textMuted}; }

  .leo-completeness {
    border-color: ${BRAND.dark.border};
    background: ${BRAND.dark.surface};
  }
}
`.trim();
}
