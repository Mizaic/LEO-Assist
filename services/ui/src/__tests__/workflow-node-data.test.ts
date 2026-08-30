/**
 * Workflow canvas node data must satisfy xyflow's Node generic.
 *
 * Next.js production builds fail when WorkflowNodeData is a bare
 * interface without a string index signature.
 */

import * as fs from "fs";
import * as path from "path";

const TYPES = path.resolve(
  __dirname,
  "../app/admin/workflows/types.ts",
);

function read(): string {
  return fs.readFileSync(TYPES, "utf8");
}

describe("WorkflowNodeData xyflow constraint", () => {
  test("WorkflowNodeData is a type that extends Record<string, unknown>", () => {
    const src = read();
    expect(src).toMatch(
      /export type WorkflowNodeData = \{[\s\S]*?\} & Record<string, unknown>/,
    );
  });

  test("WorkflowEdgeData is a type that extends Record<string, unknown>", () => {
    const src = read();
    expect(src).toMatch(
      /export type WorkflowEdgeData = \{[\s\S]*?\} & Record<string, unknown>/,
    );
  });

  test("hooks and node props use Node and Edge wrappers", () => {
    const editor = fs.readFileSync(
      path.resolve(__dirname, "../app/admin/workflows/[id]/useWorkflowEditor.ts"),
      "utf8",
    );
    const agent = fs.readFileSync(
      path.resolve(__dirname, "../app/admin/workflows/[id]/nodes/AgentNode.tsx"),
      "utf8",
    );
    expect(editor).toMatch(/useNodesState<Node<WorkflowNodeData>>/);
    expect(editor).toMatch(/useEdgesState<Edge<WorkflowEdgeData>>/);
    expect(agent).toMatch(/NodeProps<Node<WorkflowNodeData>>/);
  });
});
