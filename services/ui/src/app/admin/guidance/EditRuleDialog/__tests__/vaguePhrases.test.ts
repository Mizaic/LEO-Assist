import {
  detectVaguePhrase,
  normaliseTopic,
  suggestConceptsForTopic,
} from "../vaguePhrases";

describe("detectVaguePhrase", () => {
  const cases: Array<{ input: string; pattern: string; topic: string }> = [
    { input: "Symptoms of lung cancer", pattern: "symptoms_of", topic: "lung cancer" },
    { input: "symptoms of breast cancer (finding)", pattern: "symptoms_of", topic: "breast cancer" },
    { input: "Signs of dehydration", pattern: "signs_of", topic: "dehydration" },
    { input: "Lung cancer symptoms", pattern: "trailing_symptoms", topic: "lung cancer" },
    {
      input: "CXR indicative of lung cancer",
      pattern: "indicative_of",
      topic: "lung cancer",
    },
    {
      input: "Imaging suggestive of malignancy",
      pattern: "suggestive_of",
      topic: "malignancy",
    },
    {
      input: "Findings consistent with TIA",
      pattern: "consistent_with",
      topic: "tia",
    },
    {
      input: "Features of pancreatic cancer",
      pattern: "features_of",
      topic: "pancreatic cancer",
    },
    { input: "Suspected sepsis", pattern: "suspected", topic: "sepsis" },
    { input: "Possible meningitis", pattern: "possible", topic: "meningitis" },
    {
      input: "Concern of malignancy",
      pattern: "concern_of",
      topic: "malignancy",
    },
    { input: "Risk of stroke", pattern: "risk_of", topic: "stroke" },
    { input: "Abnormal CXR", pattern: "abnormal", topic: "cxr" },
    {
      input: "Red flags for cancer",
      pattern: "red_flags",
      topic: "cancer",
    },
  ];
  it.each(cases)(
    "flags '$input' as vague (pattern: $pattern, topic: $topic)",
    ({ input, pattern, topic }) => {
      const m = detectVaguePhrase(input);
      expect(m.isVague).toBe(true);
      expect(m.patternLabel).toBe(pattern);
      expect(m.topic).toBe(topic);
      expect(m.reason).toMatch(/specific|symptoms|signs|findings|red flags/i);
    },
  );

  it("does not flag concrete SNOMED preferred terms", () => {
    const inputs = [
      "Cough (finding)",
      "Haemoptysis",
      "Weight loss",
      "Acute appendicitis (disorder)",
      "Headache",
    ];
    for (const i of inputs) {
      expect(detectVaguePhrase(i).isVague).toBe(false);
    }
  });

  it("returns a clean empty match for null / empty input", () => {
    expect(detectVaguePhrase("").isVague).toBe(false);
    expect(detectVaguePhrase(null).isVague).toBe(false);
    expect(detectVaguePhrase(undefined).isVague).toBe(false);
  });
});

describe("suggestConceptsForTopic", () => {
  it("returns curated cancer red-flag symptoms for known topics", () => {
    const lung = suggestConceptsForTopic("lung cancer");
    expect(lung.length).toBeGreaterThanOrEqual(5);
    const terms = lung.map((s) => s.preferred_term.toLowerCase());
    expect(terms).toEqual(expect.arrayContaining(["cough", "haemoptysis"]));
    for (const s of lung) {
      expect(s.snomed_concept_id).toMatch(/^\d+$/);
    }
  });

  it("uses the alias map so 'lung' resolves to lung cancer suggestions", () => {
    expect(suggestConceptsForTopic("lung").length).toBeGreaterThan(0);
    expect(suggestConceptsForTopic("bowel").length).toBeGreaterThan(0);
    expect(suggestConceptsForTopic("MI").length).toBeGreaterThan(0);
  });

  it("returns suggestions for cancer_generic when topic is just 'cancer' or 'malignancy'", () => {
    const cancer = suggestConceptsForTopic("cancer");
    const mal = suggestConceptsForTopic("malignancy");
    expect(cancer.length).toBeGreaterThan(0);
    expect(mal.length).toBeGreaterThan(0);
    expect(cancer).toEqual(mal);
  });

  it("returns empty for unknown topics so the popover can offer search-only", () => {
    expect(suggestConceptsForTopic("bigfoot disease")).toEqual([]);
    expect(suggestConceptsForTopic(null)).toEqual([]);
  });
});

describe("normaliseTopic", () => {
  it("strips suspected / possible qualifiers when looking up", () => {
    expect(normaliseTopic("suspected sepsis")).toBe("sepsis");
    expect(normaliseTopic("Possible meningitis")).toBe("meningitis");
  });
});
