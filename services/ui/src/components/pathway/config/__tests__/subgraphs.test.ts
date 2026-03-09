import { SUBGRAPH_IO, SUBGRAPH_OPTIONS, getPortsFromDescriptor } from "../subgraphs";

describe("pathway subgraph config", () => {
  it("exposes runtime-only subgraphs in the builder palette", () => {
    const ids = new Set(SUBGRAPH_OPTIONS.map((option) => option.id));
    expect(ids.has("surface_form_validation")).toBe(true);
    expect(ids.has("guidance_rule_extraction")).toBe(true);
    expect(ids.has("rest_connector")).toBe(true);
    expect(ids.has("queue_publish")).toBe(true);
  });

  it("derives ports for guidance rule extraction", () => {
    expect(SUBGRAPH_IO.guidance_rule_extraction.reads).toEqual(["recommendation", "guideline_id"]);
    const ports = getPortsFromDescriptor("guidance_rule_extraction");
    const keys = ports.map((port) => port.key);
    expect(keys).toContain("recommendation");
    expect(keys).toContain("guideline_id");
    expect(keys).toContain("coded_criteria");
  });
});
