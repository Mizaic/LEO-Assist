/**
 * Unit tests for rule review pool search, filter, and pagination helpers.
 */
import {
  collectGuidelineIds,
  filterRulesByGuideline,
  filterRulesByStrength,
  paginateRules,
  ruleMatchesSearch,
} from "../ruleReviewPoolUtils";

const RULES = [
  {
    rule_id: "r1",
    guideline_id: "NG12",
    recommendation_text: "1.16.2 Refer for suspected cancer.",
    name: "Cancer referral",
    strength: "refer",
  },
  {
    rule_id: "r2",
    guideline_id: "NG151",
    recommendation_text: "Offer FIT testing.",
    name: "FIT offer",
    strength: "offer",
  },
];

describe("ruleReviewPoolUtils", () => {
  it("ruleMatchesSearch matches guideline id and recommendation text", () => {
    expect(ruleMatchesSearch(RULES[0], "NG12")).toBe(true);
    expect(ruleMatchesSearch(RULES[0], "suspected cancer")).toBe(true);
    expect(ruleMatchesSearch(RULES[0], "FIT")).toBe(false);
  });

  it("filterRulesByGuideline keeps all when filter is all", () => {
    expect(filterRulesByGuideline(RULES, "all")).toHaveLength(2);
    expect(filterRulesByGuideline(RULES, "NG12")).toHaveLength(1);
  });

  it("filterRulesByStrength filters by strength value", () => {
    expect(filterRulesByStrength(RULES, "offer")).toHaveLength(1);
  });

  it("collectGuidelineIds returns sorted unique ids", () => {
    expect(collectGuidelineIds(RULES)).toEqual(["NG12", "NG151"]);
  });

  it("paginateRules slices and reports range metadata", () => {
    const page = paginateRules(RULES, 1, 1);
    expect(page.pageRules).toHaveLength(1);
    expect(page.total).toBe(2);
    expect(page.totalPages).toBe(2);
    expect(page.from).toBe(1);
    expect(page.to).toBe(1);
  });
});
