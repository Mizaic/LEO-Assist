/** Unit tests for Validation Lab trace flow map helpers. */

import {
  buildFlowEndpoints,
  endpointLinkRows,
  resolveFlowLinks,
} from "../app/admin/validation-lab/inspector/traceFlowUtils";

describe("traceFlowUtils", () => {
  const planSteps = [
    { action_id: "act-a", subgraph_id: "extraction", sequence: 0 },
    { action_id: "act-b", subgraph_id: "post_processing", sequence: 1 },
    { action_id: "act-c", subgraph_id: "compliance", sequence: 2 },
  ];

  it("falls back to sequence order when plan edges are missing", () => {
    const links = resolveFlowLinks(planSteps, []);
    expect(links).toEqual([
      { source: "act-a", target: "act-b", relationship: "after-end" },
      { source: "act-b", target: "act-c", relationship: "after-end" },
    ]);
  });

  it("builds endpoint status from spans", () => {
    const endpoints = buildFlowEndpoints(planSteps, [
      { step_id: "act-a", status: "failed" },
      { step_id: "act-b", status: "completed" },
    ]);
    expect(endpoints[0].status).toBe("failed");
    expect(endpoints[2].status).toBe("pending");
  });

  it("lists upstream and downstream links for a selected endpoint", () => {
    const links = resolveFlowLinks(planSteps, []);
    const endpoints = buildFlowEndpoints(planSteps, []);
    expect(endpointLinkRows("act-b", "upstream", endpoints, links)).toHaveLength(1);
    expect(endpointLinkRows("act-b", "downstream", endpoints, links)).toHaveLength(1);
  });
});
