/**
 * Static analysis tests for VT-LEO-AI-110.
 *
 * These tests read Pathway Explorer source files and assert structural
 * properties: plain-English compliance, accessibility attributes, file
 * existence, data-gated UX patterns, and coverage badge presence.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");
const RESEARCH_DIR = path.join(UI_SRC, "components/research");

function readResearch(filename: string): string {
  return fs.readFileSync(path.join(RESEARCH_DIR, filename), "utf-8");
}

function readUISrc(relativePath: string): string {
  return fs.readFileSync(path.join(UI_SRC, relativePath), "utf-8");
}

// -- VT-110-TC-001: All research component files exist ------------------------

describe("VT-110-TC-001: Research component files exist", () => {
  const required = [
    "MissionCard.tsx",
    "MissionCardGrid.tsx",
    "ScopingWizard.tsx",
    "HeadlineResult.tsx",
    "ResultsTable.tsx",
    "MethodExplainer.tsx",
    "GuidedNextSteps.tsx",
    "ResultsPanel.tsx",
    "PersonaLensToggle.tsx",
    "PathwayExplorerWorkspace.tsx",
    "useResearchState.ts",
  ];

  for (const file of required) {
    it(`${file} exists`, () => {
      expect(fs.existsSync(path.join(RESEARCH_DIR, file))).toBe(true);
    });
  }

  it("pathway-explorer page.tsx exists", () => {
    const p = path.join(UI_SRC, "app/admin/pathway-explorer/page.tsx");
    expect(fs.existsSync(p)).toBe(true);
  });

  it("researchApi.ts exists", () => {
    const p = path.join(UI_SRC, "lib/researchApi.ts");
    expect(fs.existsSync(p)).toBe(true);
  });
});

// -- VT-110-TC-002: No algorithm jargon in user-facing text -------------------

describe("VT-110-TC-002: No algorithm jargon in user-facing components", () => {
  const JARGON_TERMS = [
    "betweenness",
    "centrality",
    " leiden",
    "pagerank",
    " jaccard",
    " cosine",
    " knn",
    " wcc",
    " scc",
    "fastrp",
    "graphsage",
    "node2vec",
  ];

  const USER_FACING_FILES = [
    "MissionCard.tsx",
    "MissionCardGrid.tsx",
    "ScopingWizard.tsx",
    "HeadlineResult.tsx",
    "ResultsTable.tsx",
    "GuidedNextSteps.tsx",
    "PersonaLensToggle.tsx",
    "PathwayExplorerWorkspace.tsx",
  ];

  for (const file of USER_FACING_FILES) {
    it(`${file} contains no algorithm jargon in JSX strings`, () => {
      const content = readResearch(file).toLowerCase();
      // Only check inside JSX string literals and template literals,
      // not inside comments or method explainer (collapsed) sections.
      const jsxStringPattern = /(?:>|=\s*")[^"<>{}]*?(term)[^"<>{}]*?(?:<|")/;
      for (const term of JARGON_TERMS) {
        // Strip comments before checking
        const noComments = content
          .replace(/\/\*[\s\S]*?\*\//g, "")
          .replace(/\/\/[^\n]*/g, "");
        // Allow terms inside MethodExplainer which is deliberately technical
        const noMethod = noComments.replace(
          /methodexplainer[\s\S]{0,2000}methodexplainer/gi,
          ""
        );
        // Check for jargon in JSX text nodes (between > and <)
        const jsxTextMatches = noMethod.match(/>([^<{]*)</g) || [];
        for (const textNode of jsxTextMatches) {
          const normalized = textNode.toLowerCase();
          if (normalized.includes(term)) {
            throw new Error(
              `Found jargon term "${term}" in JSX text in ${file}: ${textNode.trim()}`
            );
          }
        }
      }
    });
  }
});

// -- VT-110-TC-003: MissionCard accessibility attributes ---------------------

describe("VT-110-TC-003: MissionCard accessibility", () => {
  const card = readResearch("MissionCard.tsx");

  it("uses aria-label on the card button/element", () => {
    expect(card).toMatch(/aria-label/);
  });

  it("supports keyboard interaction (onKeyDown or onKeyPress)", () => {
    expect(card).toMatch(/onKey(Down|Press|Up)/);
  });

  it("handles Enter and Space keys", () => {
    expect(card).toMatch(/Enter/);
    expect(card).toMatch(/Space|" "/);
  });

  it("applies aria-disabled for data-gated missions", () => {
    expect(card).toMatch(/aria-disabled/);
  });
});

// -- VT-110-TC-004: HeadlineResult ARIA live region --------------------------

describe("VT-110-TC-004: HeadlineResult ARIA live region", () => {
  const headline = readResearch("HeadlineResult.tsx");

  it('has role="status" for screen reader announcements', () => {
    expect(headline).toContain('role="status"');
  });

  it('has aria-live="polite"', () => {
    expect(headline).toContain('aria-live="polite"');
  });

  it("renders loading state", () => {
    expect(headline).toMatch(/loading|CircularProgress|skeleton/i);
  });

  it("renders error state", () => {
    expect(headline).toMatch(/error/i);
  });

  it("renders data unavailable state", () => {
    expect(headline).toMatch(/data_available|not enough|unavailable/i);
  });
});

// -- VT-110-TC-005: Data-gated missions show Coming soon ---------------------

describe("VT-110-TC-005: Data-gated mission UX", () => {
  const card = readResearch("MissionCard.tsx");

  it("shows Coming soon text for data-gated missions", () => {
    expect(card).toMatch(/Coming soon|coming soon/i);
  });

  it("prevents click action on data-gated missions", () => {
    // MissionCard uses isLocked derived from !mission.data_available
    expect(card).toMatch(/isLocked|data_available/);
    expect(card).toMatch(/return|disabled/);
  });
});

// -- VT-110-TC-006: ScopingWizard three-question structure -------------------

describe("VT-110-TC-006: ScopingWizard structure", () => {
  const scoping = readResearch("ScopingWizard.tsx");

  it("contains area/pathway question", () => {
    expect(scoping).toMatch(/area|pathway|which area/i);
  });

  it("contains time period question", () => {
    expect(scoping).toMatch(/period|time|months/i);
  });

  it("contains detail level question", () => {
    expect(scoping).toMatch(/detail|summary|level/i);
  });

  it("uses MUI Dialog component", () => {
    expect(scoping).toMatch(/Dialog/);
  });

  it("uses MUI ToggleButtonGroup for selections", () => {
    expect(scoping).toMatch(/ToggleButtonGroup|ToggleButton/);
  });
});

// -- VT-110-TC-007: ResultsTable plain-English column headers ----------------

describe("VT-110-TC-007: ResultsTable plain-English column headers", () => {
  const table = readResearch("ResultsTable.tsx");

  it("has a column header mapping or humanisation function", () => {
    expect(table).toMatch(/humanise|humanize|columnLabel|COLUMN_LABELS|toUpperCase\(\)|replace.*_/i);
  });

  it("provides an export button", () => {
    expect(table).toMatch(/export|Export|download|Download/i);
  });

  it("implements sorting", () => {
    expect(table).toMatch(/sort|Sort/);
  });
});

// -- VT-110-TC-008: AppShell includes Pathway Explorer navigation -------------

describe("VT-110-TC-008: AppShell Pathway Explorer nav item", () => {
  const appShell = readUISrc("components/AppShell.tsx");

  it("includes pathway-explorer route", () => {
    expect(appShell).toContain("pathway-explorer");
  });

  it("includes Pathway Explorer label", () => {
    expect(appShell).toMatch(/Pathway Explorer/);
  });
});

// -- VT-110-TC-009: PersonaLensToggle three lenses ---------------------------

describe("VT-110-TC-009: PersonaLensToggle three lenses", () => {
  const toggle = readResearch("PersonaLensToggle.tsx");

  it("includes Patients lens", () => {
    expect(toggle).toMatch(/patient|Patient/);
  });

  it("includes Pathways lens", () => {
    expect(toggle).toMatch(/pathway|Pathway/);
  });

  it("includes Capacity lens", () => {
    expect(toggle).toMatch(/capacity|Capacity/);
  });

  it("uses ToggleButtonGroup", () => {
    expect(toggle).toMatch(/ToggleButtonGroup/);
  });
});

// -- VT-110-TC-010: MethodExplainer collapsible pattern ----------------------

describe("VT-110-TC-010: MethodExplainer collapsible pattern", () => {
  const explainer = readResearch("MethodExplainer.tsx");

  it("has a toggle/expand button", () => {
    expect(explainer).toMatch(/onClick|onToggle|open|collapsed/i);
  });

  it("contains plain text explanation", () => {
    expect(explainer).toMatch(/plain|how|method|explain/i);
  });

  it("contains technical note section", () => {
    expect(explainer).toMatch(/technical|Technical/);
  });
});
