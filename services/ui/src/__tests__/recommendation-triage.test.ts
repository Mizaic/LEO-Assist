import {
  defaultSelectedForTriage,
  triageRecommendation,
} from "@/lib/recommendationTriage";

describe("recommendation triage (picker)", () => {
  test("urgent referral is full_rule and pre-selected", () => {
    const bucket = triageRecommendation(
      "Urgently refer people with acne fulminans on the same day to dermatology",
    );
    expect(bucket).toBe("full_rule");
    expect(defaultSelectedForTriage(bucket)).toBe(true);
  });

  test("information-only is no_rule and not pre-selected", () => {
    const bucket = triageRecommendation(
      "Give people with acne clear information tailored to their needs. Topics to cover include scarring.",
    );
    expect(bucket).toBe("no_rule");
    expect(defaultSelectedForTriage(bucket)).toBe(false);
  });

  test("empty text is no_rule", () => {
    expect(triageRecommendation("")).toBe("no_rule");
  });
});
