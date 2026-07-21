/**
 * Selection helpers for Validation Lab multi-select delete.
 *
 * Atlas: DI-43E908C6 / VT-3959DFB3 / DO-158BE606
 */

import {
  allSelected,
  clearSelection,
  pruneSelection,
  someSelected,
  toggleId,
} from "../app/admin/validation-lab/testPatientSelection";

describe("validation-lab test patient selection", () => {
  test("toggleId adds and removes ids", () => {
    const once = toggleId(new Set(), "a");
    expect([...once]).toEqual(["a"]);
    const twice = toggleId(once, "a");
    expect([...twice]).toEqual([]);
  });

  test("pruneSelection drops missing ids", () => {
    const pruned = pruneSelection(new Set(["a", "b", "c"]), ["a", "c"]);
    expect([...pruned].sort()).toEqual(["a", "c"]);
  });

  test("allSelected and someSelected reflect visible ids", () => {
    const selected = new Set(["a", "b"]);
    expect(allSelected(["a", "b"], selected)).toBe(true);
    expect(allSelected(["a", "b", "c"], selected)).toBe(false);
    expect(someSelected(["c"], selected)).toBe(false);
    expect(someSelected(["a", "c"], selected)).toBe(true);
  });

  test("clearSelection returns empty set", () => {
    expect(clearSelection().size).toBe(0);
  });
});
