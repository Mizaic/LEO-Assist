/**
 * VT-592D30E9 -- fact tree groups by context then kind.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 */

import { buildFactTree } from "../app/admin/validation-lab/factTreeGroups";
import type { LabWorkItem } from "../app/admin/validation-lab/inspectorTypes";

function fact(partial: Partial<LabWorkItem> & { text: string }): LabWorkItem {
  return { kind: "fact", ...partial };
}

describe("buildFactTree", () => {
  test("always shows the five core context groups", () => {
    const tree = buildFactTree([]);
    expect(tree.map((group) => group.key)).toEqual([
      "present",
      "historical",
      "family",
      "absent",
      "planned",
    ]);
    expect(tree.every((group) => group.count === 0)).toBe(true);
    expect(tree.every((group) => group.tags.length === 0)).toBe(true);
  });

  test("adds extra assertion tops only when count is greater than 0", () => {
    const tree = buildFactTree([
      fact({ text: "maybe cancer", assertion: "possible", semanticTag: "finding" }),
    ]);
    expect(tree.map((group) => group.key)).toEqual([
      "present",
      "historical",
      "family",
      "absent",
      "planned",
      "possible",
    ]);
    expect(tree.find((group) => group.key === "possible")?.count).toBe(1);
    expect(tree.find((group) => group.key === "hypothetical")).toBeUndefined();
  });

  test("hides empty semantic-tag groups and keeps tasteful leaf fields", () => {
    const tree = buildFactTree([
      fact({
        text: "new postmenopausal bleeding",
        assertion: "present",
        semanticTag: "finding",
        code: "123456789",
        value: "8.2",
        unit: "mmol/L",
        relationType: "linked to",
        relationTarget: "endometrial cancer",
      }),
      fact({
        text: "atrial fibrillation",
        assertion: "historical",
        semanticTag: "disorder",
      }),
      { kind: "sbar", text: "Situation: urgent bleed" },
      {
        kind: "relation",
        text: "weight loss -- linked to -- pancreatic cancer",
      },
    ]);
    const present = tree.find((group) => group.key === "present");
    expect(present?.count).toBe(1);
    expect(present?.tags.map((tag) => tag.key)).toEqual(["finding"]);
    expect(present?.tags[0].leaves[0]).toEqual({
      text: "new postmenopausal bleeding",
      code: "123456789",
      value: "8.2",
      unit: "mmol/L",
      relation: "linked to endometrial cancer",
    });
    const history = tree.find((group) => group.key === "historical");
    expect(history?.count).toBe(1);
    expect(history?.tags[0].leaves[0]).toEqual({
      text: "atrial fibrillation",
    });
  });
});
