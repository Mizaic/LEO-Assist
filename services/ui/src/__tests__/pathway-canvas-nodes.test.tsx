// VT-LEO-AI-155 - Pathway canvas node primitives (Phase 6b-iii)
//
// Static-source verification that all 10 pathway node types share a single
// BaseNode shell, NodeHandle wrapper, and NodeStatusStrip; expose aria-labels
// on every handle; and have a unified single-click configure interaction.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const NODES_DIR = path.join(ROOT, "services/ui/src/components/pathway/nodes");
const BASE_DIR = path.join(NODES_DIR, "_base");

const NODE_FILES = [
  "ActionNode.tsx",
  "ConditionNode.tsx",
  "ConnectorNode.tsx",
  "TriggerNode.tsx",
  "ParallelNode.tsx",
  "MergeNode.tsx",
  "TransformNode.tsx",
  "SourceNode.tsx",
  "OutputNode.tsx",
  "MiniHitlNode.tsx",
] as const;

function readNode(name: string): string {
  return fs.readFileSync(path.join(NODES_DIR, name), "utf-8");
}

function readBase(name: string): string {
  return fs.readFileSync(path.join(BASE_DIR, name), "utf-8");
}

describe("VT-LEO-AI-155 - Pathway canvas node primitives", () => {
  it("VT-155-TC-001: _base/ primitive files exist", () => {
    expect(fs.existsSync(path.join(BASE_DIR, "BaseNode.tsx"))).toBe(true);
    expect(fs.existsSync(path.join(BASE_DIR, "NodeHandle.tsx"))).toBe(true);
    expect(fs.existsSync(path.join(BASE_DIR, "NodeHeader.tsx"))).toBe(true);
    expect(fs.existsSync(path.join(BASE_DIR, "NodeStatusStrip.tsx"))).toBe(true);
    expect(fs.existsSync(path.join(BASE_DIR, "index.ts"))).toBe(true);
  });

  it("VT-155-TC-002: _base/index.ts re-exports all primitives", () => {
    const src = readBase("index.ts");
    expect(src).toMatch(/export\s*\{\s*BaseNode\s*\}/);
    expect(src).toMatch(/export\s*\{\s*NodeHandle/);
    expect(src).toMatch(/export\s*\{\s*NodeHeader\s*\}/);
    expect(src).toMatch(/export\s*\{\s*NodeStatusStrip\s*\}/);
  });

  it("VT-155-TC-003: every node imports BaseNode from ./_base", () => {
    for (const file of NODE_FILES) {
      const src = readNode(file);
      expect(src).toMatch(/from\s+["']\.\/_base["']/);
      expect(src).toMatch(/\bBaseNode\b/);
    }
  });

  it("VT-155-TC-004: every node renders <BaseNode> as the wrapper", () => {
    for (const file of NODE_FILES) {
      const src = readNode(file);
      expect(src).toMatch(/<BaseNode[\s\S]*?>/);
      expect(src).toMatch(/<\/BaseNode>/);
    }
  });

  it("VT-155-TC-005: every node uses NodeHandle (no raw <Handle ... aria-label-less primitives)", () => {
    for (const file of NODE_FILES) {
      const src = readNode(file);
      expect(src).toMatch(/\bNodeHandle\b/);
      expect(src).not.toMatch(/<Handle\s/);
    }
  });

  it("VT-155-TC-006: NodeHandle always sets an aria-label", () => {
    const src = readBase("NodeHandle.tsx");
    expect(src).toMatch(/aria-label=\{resolvedAria\}/);
    expect(src).toMatch(/resolvedAria/);
  });

  it("VT-155-TC-007: BaseNode unifies onActivate single-click + keyboard", () => {
    const src = readBase("BaseNode.tsx");
    expect(src).toMatch(/onActivate/);
    expect(src).toMatch(/onClick=\{onActivate\}/);
    expect(src).toMatch(/onKeyDown/);
    expect(src).toMatch(/role=\{isInteractive \? "button" : undefined\}/);
    expect(src).toMatch(/tabIndex=\{isInteractive \? 0 : undefined\}/);
  });

  it("VT-155-TC-008: no node still binds onDoubleClick for configure", () => {
    for (const file of NODE_FILES) {
      const src = readNode(file);
      expect(src).not.toMatch(/onDoubleClick=\{[^}]*onConfigure/);
    }
  });

  it("VT-155-TC-009: every interactive node passes onConfigure -> onActivate", () => {
    const interactive = NODE_FILES.filter(
      (f) => !["ParallelNode.tsx", "MergeNode.tsx"].includes(f),
    );
    for (const file of interactive) {
      const src = readNode(file);
      expect(src).toMatch(/onActivate=\{[^}]*onConfigure/);
    }
  });

  it("VT-155-TC-010: BaseNode pins the canonical 12px radius + 2px border", () => {
    const src = readBase("BaseNode.tsx");
    expect(src).toMatch(/borderRadius:\s*"12px"/);
    expect(src).toMatch(/border:\s*`2px \$\{borderStyle\}`/);
  });

  it("VT-155-TC-011: NodeStatusStrip exposes the canonical run states", () => {
    const src = readBase("NodeStatusStrip.tsx");
    for (const state of [
      "idle",
      "queued",
      "running",
      "completed",
      "halted",
      "error",
      "skipped",
    ]) {
      expect(src).toMatch(new RegExp(`"${state}"`));
    }
  });

  it("VT-155-TC-012: ActionNode delegates run state to NodeStatusStrip", () => {
    const src = readNode("ActionNode.tsx");
    expect(src).toMatch(/<NodeStatusStrip[\s\S]*?\/>/);
    expect(src).toMatch(/resolveRunStatus\(/);
  });

  it("VT-155-TC-013: nodeTypes registry still exposes all 10 entries", () => {
    const src = fs.readFileSync(path.join(NODES_DIR, "nodeTypes.ts"), "utf-8");
    for (const key of [
      "action",
      "condition",
      "rest_connector",
      "queue_publish",
      "trigger",
      "parallel",
      "merge",
      "transform",
      "source",
      "output",
      "viewer",
    ]) {
      expect(src).toMatch(new RegExp(`\\b${key}\\s*:`));
    }
  });

  it("VT-155-TC-014: every node file stays under the 300 LOC target / 500 hard limit", () => {
    const all = [
      ...NODE_FILES.map((f) => path.join(NODES_DIR, f)),
      path.join(BASE_DIR, "BaseNode.tsx"),
      path.join(BASE_DIR, "NodeHandle.tsx"),
      path.join(BASE_DIR, "NodeHeader.tsx"),
      path.join(BASE_DIR, "NodeStatusStrip.tsx"),
    ];
    for (const filePath of all) {
      const src = fs.readFileSync(filePath, "utf-8");
      const loc = src.split("\n").length;
      expect(loc).toBeLessThan(500);
    }
  });

  it("VT-155-TC-015: source/output nodes still expose their definitions registry", () => {
    const source = readNode("SourceNode.tsx");
    const output = readNode("OutputNode.tsx");
    expect(source).toMatch(/export const SOURCE_DEFINITIONS/);
    expect(output).toMatch(/export const OUTPUT_DEFINITIONS/);
    for (const key of [
      "encounter_text",
      "patient_graph",
      "knowledge_graph",
      "pubsub_subscribe",
    ]) {
      expect(source).toMatch(new RegExp(`\\b${key}\\b`));
    }
    for (const key of [
      "knowledge_graph",
      "patient_graph",
      "pubsub_publish",
      "webhook",
    ]) {
      expect(output).toMatch(new RegExp(`\\b${key}\\b`));
    }
  });
});
