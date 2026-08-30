/**
 * Workflow API client -- empty 204 bodies must not be parsed as JSON.
 */

import { parseApiBody } from "../app/admin/workflows/workflowApi";

describe("parseApiBody", () => {
  it("returns undefined for a 204 with no body", () => {
    expect(parseApiBody(204, "")).toBeUndefined();
  });

  it("returns undefined for an empty 200 body", () => {
    expect(parseApiBody(200, "")).toBeUndefined();
  });

  it("parses a JSON body when one is present", () => {
    expect(parseApiBody(200, '{"id":"wf-1"}')).toEqual({ id: "wf-1" });
  });
});
