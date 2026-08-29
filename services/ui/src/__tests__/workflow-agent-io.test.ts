/**
 * Workflow builder -- HCCP-Agents typed I/O on the canvas.
 *
 * Every palette agent must resolve a contract so the properties
 * panel and node chips can show inputs and outputs.
 */

import * as fs from "fs";
import * as path from "path";
import { AGENT_CATALOGUE } from "../app/admin/workflows/agentCatalogue";
import { getAgentIo } from "../app/admin/workflows/agentIo";

describe("agent I/O catalogue", () => {
  test("every catalogue agent has a named contract", () => {
    for (const agent of AGENT_CATALOGUE) {
      const io = getAgentIo(agent.type);
      expect(io).not.toBeNull();
      expect(io!.stateName.length).toBeGreaterThan(0);
      expect(io!.inputs.length + io!.outputs.length).toBeGreaterThan(0);
    }
  });

  test("clinical summary exposes SBAR outputs", () => {
    const io = getAgentIo("clinical_summary_agent");
    const names = io!.outputs.map((f) => f.name);
    expect(names).toEqual(
      expect.arrayContaining([
        "situation_markdown",
        "background_markdown",
        "assessment_markdown",
        "recommendation_markdown",
      ]),
    );
  });

  test("appropriateness exposes the pydantic result shape", () => {
    const io = getAgentIo("appropriateness_agent");
    expect(io!.strictness).toBe("pydantic");
    const names = io!.outputs.map((f) => f.name);
    expect(names).toEqual(
      expect.arrayContaining([
        "is_appropriate",
        "confidence_score",
        "criteria_results",
      ]),
    );
  });

  test("peer review exposes the typed assessment", () => {
    const io = getAgentIo("peer_review_agent");
    const names = io!.outputs.map((f) => f.name);
    expect(names).toContain("standardized_assessment");
  });

  test("unknown agents fall back to the shared AgentState bag", () => {
    const io = getAgentIo("not_a_real_agent");
    expect(io).not.toBeNull();
    expect(io!.stateName).toBe("AgentState");
    expect(io!.strictness).toBe("bag");
  });
});

describe("agent I/O chrome", () => {
  test("properties panel renders the I/O contract", () => {
    const panel = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/PropertiesPanel.tsx",
      ),
      "utf8",
    );
    const contract = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/AgentIoPanel.tsx",
      ),
      "utf8",
    );
    expect(panel).toMatch(/AgentIoPanel/);
    expect(contract).toMatch(/getAgentIo/);
  });

  test("agent nodes show an ER-style I/O table", () => {
    const node = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/nodes/AgentNode.tsx",
      ),
      "utf8",
    );
    const card = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/nodes/WorkflowEntityCard.tsx",
      ),
      "utf8",
    );
    expect(node).toMatch(/WorkflowEntityCard/);
    expect(card).toMatch(/EntityIoTable/);
    expect(card).toMatch(/getAgentIo/);
  });
});
