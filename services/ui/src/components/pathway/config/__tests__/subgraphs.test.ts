import { SUBGRAPH_IO, SUBGRAPH_OPTIONS, getPortsFromDescriptor } from "../subgraphs";

describe("pathway subgraph config", () => {
  it("exposes runtime-only subgraphs in the builder palette", () => {
    const ids = new Set(SUBGRAPH_OPTIONS.map((option) => option.id));
    expect(ids.has("extraction_check")).toBe(true);
    expect(ids.has("coding_check")).toBe(true);
    expect(ids.has("surface_form_validation")).toBe(true);
    expect(ids.has("guidance_rule_extraction")).toBe(true);
    expect(ids.has("rest_connector")).toBe(true);
    expect(ids.has("queue_publish")).toBe(true);
    expect(ids.has("coding_verifier")).toBe(true);
    expect(ids.has("referral_reason")).toBe(true);
    expect(ids.has("sbar")).toBe(true);
  });

  it("adds next/prev sequence ports for durable canvas wiring", () => {
    const keys = getPortsFromDescriptor("extraction").map((port) => port.key);
    expect(keys).toContain("prev");
    expect(keys).toContain("next");
  });

  it("derives ports for guidance rule extraction", () => {
    expect(SUBGRAPH_IO.guidance_rule_extraction.reads).toEqual(["recommendation", "guideline_id"]);
    const ports = getPortsFromDescriptor("guidance_rule_extraction");
    const keys = ports.map((port) => port.key);
    expect(keys).toContain("recommendation");
    expect(keys).toContain("guideline_id");
    expect(keys).toContain("coded_criteria");
  });

  it("derives ports for extraction and coding quality checks", () => {
    expect(SUBGRAPH_IO.extraction_check.reads).toEqual(["entities", "encounter_text"]);
    expect(SUBGRAPH_IO.coding_check.reads).toEqual(["entities", "encounter_text"]);

    const extractionPorts = getPortsFromDescriptor("extraction_check");
    const extractionKeys = extractionPorts.map((port) => port.key);
    expect(extractionKeys).toContain("llm_check_result");
    expect(extractionKeys).toContain("llm_check_changes");

    const codingPorts = getPortsFromDescriptor("coding_check");
    const codingKeys = codingPorts.map((port) => port.key);
    expect(codingKeys).toContain("llm_check_result");
    expect(codingKeys).toContain("llm_check_changes");
  });
});
