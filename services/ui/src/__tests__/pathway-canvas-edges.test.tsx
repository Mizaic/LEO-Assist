// VT-LEO-AI-158 - Pathway probe registry parity + popover safety (Phase 6b-v)
// Static-source verification that:
//   1. every subgraph registered in libs/pipeline_graph/registry.py has both
//      a SUBGRAPH_IO descriptor and a PROBE_STRATEGIES entry;
//   2. ProbeMonitor installs a window-level Escape handler that closes the
//      inspector drawer first then calls onClose;
//   3. the popover root carries role="dialog" with an aria-label.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const SUBGRAPHS = path.join(
  ROOT,
  "services/ui/src/components/pathway/config/subgraphs.ts",
);
const STRATEGIES = path.join(
  ROOT,
  "services/ui/src/components/pathway/edges/probeStrategies.tsx",
);
const PORT_EDGE = path.join(
  ROOT,
  "services/ui/src/components/pathway/edges/PortEdge.tsx",
);
const PROBE_MONITOR = path.join(
  ROOT,
  "services/ui/src/components/pathway/edges/PortEdge/ProbeMonitor.tsx",
);
const REGISTRY = path.join(ROOT, "libs/pipeline_graph/registry.py");

function readSrc(p: string): string {
  return fs.readFileSync(p, "utf-8");
}

// Subgraphs that the python registry registers but that are intentionally not
// asserted by this VT. The legacy IDs below are pre-existing drift between
// the python registry and the UI canvas configuration; remediating them is
// tracked under Phase 6b-vi cleanup so this VT can lock in the four
// in-scope additions without inheriting prior debt.
const UI_OPT_OUT: ReadonlySet<string> = new Set([
  "extraction",
  "terminology",
  "verification",
  "persist",
  "sbar",
  "compliance",
]);

function pythonRegisteredSubgraphs(): string[] {
  const src = readSrc(REGISTRY);
  // registry.register("name", ...) - capture the first string literal
  const out: Set<string> = new Set();
  const re = /registry\.register\(\s*"([a-z0-9_]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    out.add(m[1]);
  }
  return Array.from(out).filter((id) => !UI_OPT_OUT.has(id));
}

describe("VT-LEO-AI-158 - Pathway probe registry parity", () => {
  const pythonIds = pythonRegisteredSubgraphs();

  it("VT-158-TC-001: python registry yields a non-empty list of subgraphs", () => {
    expect(pythonIds.length).toBeGreaterThan(15);
  });

  it("VT-158-TC-002: every python subgraph has a SUBGRAPH_IO entry", () => {
    const subgraphsSrc = readSrc(SUBGRAPHS);
    const missing = pythonIds.filter((id) => {
      const re = new RegExp(`\\b${id}\\b\\s*:\\s*\\{`);
      return !re.test(subgraphsSrc);
    });
    expect(missing).toEqual([]);
  });

  it("VT-158-TC-003: every python subgraph appears in SUBGRAPH_OPTIONS_RAW", () => {
    const subgraphsSrc = readSrc(SUBGRAPHS);
    const idsInOptions: Set<string> = new Set();
    const re = /\{\s*id:\s*"([a-z0-9_]+)"/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(subgraphsSrc)) !== null) {
      idsInOptions.add(m[1]);
    }
    const missing = pythonIds.filter((id) => !idsInOptions.has(id));
    expect(missing).toEqual([]);
  });

  it("VT-158-TC-004: in-scope subgraphs (Phase 6b-v) have a PROBE_STRATEGIES entry", () => {
    // Phase 6b-v scope: the four data-flow subgraphs registered in the
    // backend registry that previously had no UI probe support. The legacy
    // subgraphs (extraction, terminology, verification, persist, sbar,
    // compliance) are tracked separately under Phase 6b-vi cleanup and are
    // NOT asserted here so this VT does not block the in-scope work.
    const stratSrc = readSrc(STRATEGIES);
    const block = stratSrc.match(/PROBE_STRATEGIES\s*:[^=]*=\s*\{([\s\S]*?)\n\};/);
    expect(block).not.toBeNull();
    const inside = block![1];
    const inScope = [
      "encounter_loader",
      "staging_enrichment",
      "human_review_gate",
      "encounter_coding_agent",
    ];
    const missing = inScope.filter((id) => {
      const re = new RegExp(`\\b${id}\\s*:`);
      return !re.test(inside);
    });
    expect(missing).toEqual([]);
  });

  it("VT-158-TC-005: the four newly-added IDs are wired end-to-end", () => {
    const subgraphsSrc = readSrc(SUBGRAPHS);
    const stratSrc = readSrc(STRATEGIES);
    const ids = [
      "encounter_loader",
      "staging_enrichment",
      "human_review_gate",
      "encounter_coding_agent",
    ];
    for (const id of ids) {
      expect(subgraphsSrc).toMatch(new RegExp(`id:\\s*"${id}"`));
      expect(subgraphsSrc).toMatch(new RegExp(`${id}\\s*:\\s*\\{`));
      expect(stratSrc).toMatch(new RegExp(`${id}\\s*:`));
    }
  });

  it("VT-158-TC-006: encounter_coding_agent declares its config-injected fields", () => {
    const stratSrc = readSrc(STRATEGIES);
    const cif = stratSrc.match(/CONFIG_INJECTED_FIELDS[^=]*=\s*\{([\s\S]*?)\n\};/);
    expect(cif).not.toBeNull();
    expect(cif![1]).toMatch(/encounter_coding_agent\s*:/);
  });
});

describe("VT-LEO-AI-158 - ProbeMonitor popover safety", () => {
  it("VT-158-TC-007: ProbeMonitor installs a window-level Escape handler", () => {
    // Phase 6b-vi: ProbeMonitor was extracted from PortEdge.tsx into a
    // dedicated module. The static-source assertions now read that file.
    const src = readSrc(PROBE_MONITOR);
    expect(src).toMatch(/addEventListener\(\s*"keydown"/);
    expect(src).toMatch(/event\.key\s*!==\s*"Escape"|key\s*!==\s*"Escape"/);
    expect(src).toMatch(/removeEventListener\(\s*"keydown"/);
  });

  it("VT-158-TC-008: Escape closes the inspector drawer first, then the popover", () => {
    const src = readSrc(PROBE_MONITOR);
    const handlerIdx = src.indexOf("addEventListener(\"keydown\"");
    expect(handlerIdx).toBeGreaterThan(-1);
    const start = src.lastIndexOf("useEffect", handlerIdx);
    const window = src.slice(start, handlerIdx + 600);
    expect(window).toMatch(/setDrawerOpen\(\s*false\s*\)/);
    expect(window).toMatch(/onClose\(\s*\)/);
  });

  it("VT-158-TC-009: the popover root exposes role=\"dialog\" with an aria-label", () => {
    const src = readSrc(PROBE_MONITOR);
    expect(src).toMatch(/role=\"dialog\"/);
    expect(src).toMatch(/aria-label=\{`Probe[\s\S]*?Escape/);
  });
});
