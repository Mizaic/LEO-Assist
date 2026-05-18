/**
 * VT for EpisodeDetailPanel chrome.
 *
 * Atlas trace:
 *   DI: DI-CC0BD732 (per-episode SBAR with coherence)
 *   DI: DI-885930F8 (canonical episode-level code)
 *   DI: DI-E8FE404D (cross-encounter coding QA)
 *
 * Static-source verification (per VT-LEO-AI-142 pattern) for the
 * Phase 4 EpisodeDetailPanel:
 *   - Imports the canonical SbarFinalView (no fork).
 *   - Exposes the episode header, canonical code card, coherence
 *     flags, coding QA flags, and per-episode SBAR section with
 *     stable test ids.
 *   - Per-flag review labels are wired up so reviewers see the
 *     specific action they should take.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..");

const PANEL_FILE = path.join(
  ROOT,
  "components",
  "mission-control",
  "EpisodeDetailPanel.tsx",
);

function read(file: string): string {
  return fs.readFileSync(file, "utf8");
}

describe("EpisodeDetailPanel chrome", () => {
  test("TC-001: Atlas trace header references DI-CC0BD732 + DI-885930F8 + DI-E8FE404D", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/DI:\s*DI-CC0BD732/);
    expect(src).toMatch(/DI:\s*DI-885930F8/);
    expect(src).toMatch(/DI:\s*DI-E8FE404D/);
  });

  test("TC-002: imports SbarFinalView from the canonical module", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(
      /import\s*\{\s*SbarFinalView\s*\}\s*from\s*["']@\/components\/sbar-final\/SbarFinalView["']/,
    );
  });

  test("TC-003: header renders site, status, and encounter-count chips", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/data-testid="episode-detail-site-chip"/);
    expect(src).toMatch(/data-testid="episode-detail-status-chip"/);
    expect(src).toMatch(/data-testid="episode-detail-encounter-count"/);
  });

  test("TC-004: canonical code card has accept/override controls", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/data-testid="canonical-code-card"/);
    expect(src).toMatch(/data-testid="canonical-code-intent"/);
    expect(src).toMatch(/data-testid="canonical-code-confidence"/);
    expect(src).toMatch(/data-testid="canonical-code-accept"/);
    expect(src).toMatch(/data-testid="canonical-code-override"/);
  });

  test("TC-005: empty canonical code state surfaces the empty alert", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/data-testid="canonical-code-empty"/);
  });

  test("TC-006: coherence flag alerts are rendered with per-code resolve actions", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/data-testid="episode-detail-coherence-flags"/);
    expect(src).toMatch(/coherence-flag-\$\{flag\.code\}/);
    expect(src).toMatch(/coherence-flag-\$\{flag\.code\}-resolve/);
    expect(src).toMatch(/COHERENCE_REVIEW_LABEL/);
  });

  test("TC-007: coding QA flag alerts are rendered with encounter context", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/data-testid="episode-detail-coding-qa-flags"/);
    expect(src).toMatch(/coding-qa-flag-\$\{flag\.flagId\}/);
    expect(src).toMatch(/coding-qa-flag-\$\{flag\.flagId\}-resolve/);
    expect(src).toMatch(/Encounters:/);
    expect(src).toMatch(/CODING_QA_REVIEW_LABEL/);
  });

  test("TC-008: SBAR section carries an explicit episode scope chip", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/data-testid="episode-sbar-section"/);
    expect(src).toMatch(/data-testid="episode-sbar-scope-chip"/);
    expect(src).toMatch(/Scope: episode/);
  });

  test("TC-009: empty SBAR state offers a generate-SBAR action", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/data-testid="episode-sbar-empty"/);
    expect(src).toMatch(/data-testid="episode-sbar-generate"/);
  });

  test("TC-010: review label maps cover every coherence and QA flag code", () => {
    const src = read(PANEL_FILE);
    const coherenceCodes = ["narrative_contradiction", "code_narrative_drift"];
    for (const code of coherenceCodes) {
      expect(src).toMatch(new RegExp(`${code}:\\s*"`));
    }
    const codingCodes = [
      "trajectory_inversion",
      "code_contradiction",
      "site_mismatch",
    ];
    for (const code of codingCodes) {
      expect(src).toMatch(new RegExp(`${code}:\\s*"`));
    }
  });

  test("TC-011: severity-to-MUI-color map covers low/medium/high", () => {
    const src = read(PANEL_FILE);
    expect(src).toMatch(/SEVERITY_COLOR/);
    expect(src).toMatch(/low:\s*"info"/);
    expect(src).toMatch(/medium:\s*"warning"/);
    expect(src).toMatch(/high:\s*"error"/);
  });
});
