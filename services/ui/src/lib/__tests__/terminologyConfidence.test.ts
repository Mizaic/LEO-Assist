import {
  getTerminologyConfidenceBand,
  getTerminologyConfidenceExplanation,
  getTerminologyConfidenceLabel,
} from "@/lib/terminologyConfidence";

describe("terminologyConfidence", () => {
  it("maps score to confidence bands", () => {
    expect(getTerminologyConfidenceBand(0.4)).toBe("low");
    expect(getTerminologyConfidenceBand(0.7)).toBe("medium");
    expect(getTerminologyConfidenceBand(0.95)).toBe("high");
    expect(getTerminologyConfidenceBand(1.3)).toBe("high");
  });

  it("returns readable labels", () => {
    expect(getTerminologyConfidenceLabel(0.6)).toBe("Low");
    expect(getTerminologyConfidenceLabel(0.8)).toBe("Medium");
    expect(getTerminologyConfidenceLabel(1.3)).toBe("High");
  });

  it("returns plain language explanation", () => {
    expect(getTerminologyConfidenceExplanation(0.6)).toContain("Low confidence");
    expect(getTerminologyConfidenceExplanation(0.8)).toContain("Medium confidence");
    expect(getTerminologyConfidenceExplanation(1.3)).toContain("High confidence");
  });
});
