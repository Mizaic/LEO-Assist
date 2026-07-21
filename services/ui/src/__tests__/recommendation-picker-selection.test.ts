/**
 * Attach mode must start with no recommendations selected.
 *
 * Atlas: DI-EB716E68
 */

import { buildInitialSelection } from "../app/admin/guidance/recommendationPickerSelection";

const chapters = [
  {
    recommendations: [
      {
        rec_id: "r-no-rule",
        is_normative: true,
        verbatim:
          "Refer people using a suspected cancer pathway referral for oesophageal cancer if they have dysphagia",
        title: "Oesophageal",
        rules: [],
      },
      {
        rec_id: "r-with-rule",
        is_normative: true,
        verbatim:
          "Refer people using a suspected cancer pathway referral for lung cancer if they have chest X-ray findings",
        title: "Lung",
        rules: [{ rule_id: "rule-1", status: "pending_review" }],
      },
    ],
  },
];

describe("buildInitialSelection", () => {
  test("rules mode pre-selects ruleable recs without rules", () => {
    const map = buildInitialSelection(chapters, false);
    expect(map["r-no-rule"].checked).toBe(true);
    expect(map["r-with-rule"].checked).toBe(false);
  });

  test("attach mode starts with every normative rec unchecked", () => {
    const map = buildInitialSelection(chapters, true);
    expect(map["r-no-rule"].checked).toBe(false);
    expect(map["r-with-rule"].checked).toBe(false);
  });
});
