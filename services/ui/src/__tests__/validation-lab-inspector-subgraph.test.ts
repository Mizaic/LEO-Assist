/**
 * Inspector subgraph resolution tests.
 */

import { resolveSubgraphId } from "@/app/admin/validation-lab/inspector/inspectorSubgraph";

describe("resolveSubgraphId", () => {
  test("prefers span subgraph_id", () => {
    expect(
      resolveSubgraphId(
        "act-ref-extract",
        [{ action_id: "act-ref-extract", subgraph_id: "extraction" }],
        { step_id: "act-ref-extract", status: "completed", subgraph_id: "extraction" },
      ),
    ).toBe("extraction");
  });

  test("falls back to plan step mapping", () => {
    expect(
      resolveSubgraphId("act-ref-compliance", [
        { action_id: "act-ref-compliance", subgraph_id: "compliance" },
      ]),
    ).toBe("compliance");
  });

  test("infers from durable step suffix", () => {
    expect(resolveSubgraphId("act-ref-relation-link", [])).toBe("relation_linking");
    expect(resolveSubgraphId("act-ref-snomed-enrich", [])).toBe("snomed_enrichment");
  });
});
