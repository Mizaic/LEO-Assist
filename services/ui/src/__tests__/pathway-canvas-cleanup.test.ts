// VT-LEO-AI-167 - Phase 6b-vi cleanup verification
// Static-source assertions that:
//   1. every PortEdge/* and probes/* module is at most 500 LOC;
//   2. the four legacy panel/*.tsx files are gone;
//   3. the ESLint guard for pathway/** @mui imports is registered;
//   4. PortEdge.tsx is a thin barrel re-exporting PortEdge/index;
//   5. probeStrategies.tsx imports from each per-domain probe module.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const PORT_EDGE_DIR = path.join(
  ROOT,
  "services/ui/src/components/pathway/edges/PortEdge",
);
const PROBES_DIR = path.join(
  ROOT,
  "services/ui/src/components/pathway/edges/probes",
);
const PORT_EDGE_BARREL = path.join(
  ROOT,
  "services/ui/src/components/pathway/edges/PortEdge.tsx",
);
const STRATEGIES_BARREL = path.join(
  ROOT,
  "services/ui/src/components/pathway/edges/probeStrategies.tsx",
);
const PANEL_DIR = path.join(
  ROOT,
  "services/ui/src/components/pathway/panel",
);
const ESLINT_CONFIG = path.join(ROOT, "services/ui/eslint.config.mjs");

const SIZE_LIMIT = 500;
const BARREL_LIMIT = 200;
const THIN_BARREL_LIMIT = 20;

function readSrc(p: string): string {
  return fs.readFileSync(p, "utf-8");
}

function lineCount(p: string): number {
  return readSrc(p).split(/\r?\n/).length;
}

function listModules(dir: string): string[] {
  return fs
    .readdirSync(dir)
    .filter((name) => /\.(ts|tsx)$/.test(name))
    .map((name) => path.join(dir, name));
}

describe("VT-LEO-AI-167 - Pathway probe surface decomposition", () => {
  it("VT-167-TC-001: every PortEdge/* and probes/* module is <=500 LOC", () => {
    const violations: Array<{ file: string; loc: number }> = [];
    for (const file of [...listModules(PORT_EDGE_DIR), ...listModules(PROBES_DIR)]) {
      const loc = lineCount(file);
      if (loc > SIZE_LIMIT) violations.push({ file: path.basename(file), loc });
    }
    expect(violations).toEqual([]);
  });

  it("VT-167-TC-002: legacy panel/* files are removed from the tree", () => {
    const dead = [
      "InputsTab.tsx",
      "OverviewTab.tsx",
      "ReviewTab.tsx",
      "TriggerContextPanel.tsx",
    ];
    const present = dead.filter((name) =>
      fs.existsSync(path.join(PANEL_DIR, name)),
    );
    expect(present).toEqual([]);
  });

  it("VT-167-TC-003: ESLint guard for pathway/** @mui imports is registered", () => {
    const src = readSrc(ESLINT_CONFIG);
    expect(src).toMatch(/no-restricted-imports/);
    expect(src).toMatch(/components\/pathway\/\*\*/);
    expect(src).toMatch(/@mui\/\*/);
  });

  it("VT-167-TC-004: PortEdge.tsx is a thin barrel re-exporting PortEdge/index", () => {
    const src = readSrc(PORT_EDGE_BARREL);
    expect(lineCount(PORT_EDGE_BARREL)).toBeLessThanOrEqual(THIN_BARREL_LIMIT);
    expect(src).toMatch(/export\s*\{\s*PortEdge\s*\}\s*from\s*["']\.\/PortEdge\/index["']/);
  });

  it("VT-167-TC-005: probeStrategies.tsx imports from each per-domain probe module", () => {
    const src = readSrc(STRATEGIES_BARREL);
    expect(lineCount(STRATEGIES_BARREL)).toBeLessThanOrEqual(BARREL_LIMIT);
    for (const mod of [
      "_shared",
      "extraction",
      "verification",
      "persist",
      "connectors",
      "guidance",
    ]) {
      expect(src).toMatch(new RegExp(`from\\s+["']\\./probes/${mod}["']`));
    }
  });

  it("VT-167-TC-006: per-domain probe modules expose the expected strategy symbols", () => {
    const expectations: Record<string, string[]> = {
      "_shared.tsx": ["ProbeStrategy"],
      "extraction.tsx": ["extraction", "postProcessing", "terminology", "tierClassify"],
      "verification.tsx": ["verification", "surfaceFormValidation", "compliance", "qualityCheck", "llmQualityCheck"],
      "persist.tsx": ["persist", "sbar", "anchorDetect", "episodeBuild", "safetyNet", "nextBestAction"],
      "connectors.tsx": ["restConnector", "queuePublish", "hitlQueue", "encounterLoader", "stagingEnrichment", "humanReviewGate", "encounterCodingAgent"],
      "guidance.tsx": ["guidanceRuleExtraction", "relationLinking"],
    };
    for (const [file, names] of Object.entries(expectations)) {
      const src = readSrc(path.join(PROBES_DIR, file));
      for (const name of names) {
        expect(src).toMatch(new RegExp(`export\\s+(?:const|type|interface)\\s+${name}\\b`));
      }
    }
  });
});
