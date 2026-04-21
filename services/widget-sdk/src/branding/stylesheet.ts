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
  line-height: 1.5;
  font-size: 14px;
  box-sizing: border-box;
}

* { box-sizing: border-box; }

.leo-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid ${BRAND.light.border};
  border-radius: 12px;
  background: ${BRAND.light.surface};
}

.leo-header {
  display: flex;
  align-items: center;
  gap: 10px;
  color: ${BRAND.light.primary};
}

.leo-mark {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  color: ${BRAND.light.primary};
}

.leo-product {
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 0.2px;
}

.leo-test-only {
  display: inline-block;
  background: ${BRAND.light.warningBg};
  color: ${BRAND.light.warningInk};
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.leo-stage {
  border: 1px solid ${BRAND.light.border};
  border-left-width: 4px;
  border-radius: 8px;
  overflow: hidden;
  background: ${BRAND.light.surface};
}

.leo-stage[data-stage="situation"] {
  border-left-color: ${STAGE_THEME.situation.accent};
}

.leo-stage[data-stage="background"] {
  border-left-color: ${STAGE_THEME.background.accent};
}

.leo-stage[data-stage="assessment"] {
  border-left-color: ${STAGE_THEME.assessment.accent};
}

.leo-stage[data-stage="recommendation"] {
  border-left-color: ${STAGE_THEME.recommendation.accent};
}

.leo-stage-header {
  padding: 8px 14px;
  font-weight: 700;
  font-size: 13px;
}

.leo-stage[data-stage="situation"] .leo-stage-header {
  background: ${STAGE_THEME.situation.tint};
  color: ${STAGE_THEME.situation.ink};
}

.leo-stage[data-stage="background"] .leo-stage-header {
  background: ${STAGE_THEME.background.tint};
  color: ${STAGE_THEME.background.ink};
}

.leo-stage[data-stage="assessment"] .leo-stage-header {
  background: ${STAGE_THEME.assessment.tint};
  color: ${STAGE_THEME.assessment.ink};
}

.leo-stage[data-stage="recommendation"] .leo-stage-header {
  background: ${STAGE_THEME.recommendation.tint};
  color: ${STAGE_THEME.recommendation.ink};
}

.leo-stage-body {
  padding: 10px 14px;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
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

.leo-empty {
  font-size: 12px;
  color: ${BRAND.light.textMuted};
}

.leo-error {
  border: 1px solid #b91c1c;
  background: #fef2f2;
  color: #7f1d1d;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
}

.leo-advisory {
  border: 1px solid ${BRAND.light.warningInk};
  background: ${BRAND.light.warningBg};
  color: ${BRAND.light.warningInk};
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
}

@media (prefers-color-scheme: dark) {
  :host {
    color: ${BRAND.dark.text};
    background: ${BRAND.dark.background};
  }

  .leo-root {
    border-color: ${BRAND.dark.border};
    background: ${BRAND.dark.surface};
  }

  .leo-header { color: ${BRAND.dark.primary}; }
  .leo-mark { color: ${BRAND.dark.primary}; }

  .leo-test-only {
    background: ${BRAND.dark.warningBg};
    color: ${BRAND.dark.warningInk};
  }

  .leo-stage {
    background: ${BRAND.dark.surface};
    border-color: ${BRAND.dark.border};
  }

  .leo-stage-body { color: ${BRAND.dark.text}; }

  .leo-source-chip {
    background: ${BRAND.dark.surfaceMuted};
    color: ${BRAND.dark.text};
    border-color: ${BRAND.dark.border};
  }

  .leo-disclosure-toggle { color: ${BRAND.dark.primary}; }

  .leo-empty, .leo-source-part-label { color: ${BRAND.dark.textMuted}; }
}
`.trim();
}
