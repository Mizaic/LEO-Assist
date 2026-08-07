/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
import { describe, expect, it } from "@jest/globals";
import {
  DEFAULT_CONCEPT_DEPTH,
  DEFAULT_OBS_THRESHOLD,
  buildMultiSeedCriterion,
  draftHasNumericValue,
  emptyThresholdForHit,
  guessThresholdFromPhrase,
  isConflictingObsMultiPick,
  observationSeedFromPick,
  seedFromHit,
} from "../multiConceptSeed";
import type { ConceptSearchHit } from "../types";

const NAUSEA: ConceptSearchHit = {
  snomed_concept_id: "422587007",
  term: "Nausea",
  semantic_tag: "finding",
};

const VOMITING: ConceptSearchHit = {
  snomed_concept_id: "422400008",
  term: "Vomiting",
  semantic_tag: "finding",
};

const LESION_SIZE: ConceptSearchHit = {
  snomed_concept_id: "396361002",
  term: "Lesion size, largest dimension",
  semantic_tag: "observable_entity",
};

describe("DEFAULT_CONCEPT_DEPTH", () => {
  it("is 0 (exact match only) -- must be asked explicitly, never silently 3", () => {
    expect(DEFAULT_CONCEPT_DEPTH).toBe(0);
  });
});

describe("seedFromHit", () => {
  it("depth 0 produces an exact-match-only seed (include_descendants: false)", () => {
    const seed = seedFromHit(NAUSEA, 0);
    expect(seed).toEqual({
      snomed_concept_id: "422587007",
      preferred_term: "Nausea",
      semantic_tag: "finding",
      include_descendants: false,
      distance_child: null,
    });
  });

  it("depth > 0 produces a descendant-including seed carrying that exact depth", () => {
    const seed = seedFromHit(NAUSEA, 2);
    expect(seed).toEqual({
      snomed_concept_id: "422587007",
      preferred_term: "Nausea",
      semantic_tag: "finding",
      include_descendants: true,
      distance_child: 2,
    });
  });

  it("clamps a negative depth to 0 rather than passing it through", () => {
    const seed = seedFromHit(NAUSEA, -5);
    expect(seed.include_descendants).toBe(false);
    expect(seed.distance_child).toBeNull();
  });

  it("floors a fractional depth", () => {
    const seed = seedFromHit(NAUSEA, 2.9);
    expect(seed.distance_child).toBe(2);
  });
});

describe("buildMultiSeedCriterion", () => {
  it("throws on an empty seed list -- callers must not confirm with zero picks", () => {
    expect(() => buildMultiSeedCriterion([])).toThrow();
  });

  it("a single seed produces a criterion indistinguishable from the legacy single-pick shape", () => {
    const seed = seedFromHit(NAUSEA, 0);
    const criterion = buildMultiSeedCriterion([seed]);
    expect(criterion.snomed_concept_id).toBe("422587007");
    expect(criterion.preferred_term).toBe("Nausea");
    expect(criterion.semantic_tag).toBe("finding");
    expect(criterion.primary_concept_id).toBe("422587007");
    expect(criterion.seeds).toEqual([seed]);
  });

  it("multiple seeds: the first pick is the primary and supplies the legacy display fields", () => {
    const seeds = [seedFromHit(NAUSEA, 0), seedFromHit(VOMITING, 1)];
    const criterion = buildMultiSeedCriterion(seeds);
    expect(criterion.primary_concept_id).toBe("422587007");
    expect(criterion.snomed_concept_id).toBe("422587007");
    expect(criterion.preferred_term).toBe("Nausea");
    expect(criterion.seeds).toEqual(seeds);
    expect(criterion.seeds).toHaveLength(2);
  });

  it("never carries AI-confidence or human-review provenance -- this is a hand-authored pick", () => {
    const criterion = buildMultiSeedCriterion([seedFromHit(NAUSEA, 0)]);
    expect(criterion.confidence).toBeUndefined();
    expect(criterion.needs_human_review).toBeUndefined();
  });
});

describe("guessThresholdFromPhrase", () => {
  it("reads 7 mm or more from checklist-style phrasing", () => {
    expect(
      guessThresholdFromPhrase("largest diameter 7 mm or more"),
    ).toEqual({ value: "7", unit: "mm", operator: ">=" });
  });

  it("returns empty when no number is present", () => {
    expect(guessThresholdFromPhrase("irregular colour")).toEqual({});
  });
});

describe("observationSeedFromPick", () => {
  it("returns null for findings even with a filled value", () => {
    expect(
      observationSeedFromPick(NAUSEA, {
        ...DEFAULT_OBS_THRESHOLD,
        value: "7",
        unit: "mm",
      }),
    ).toBeNull();
  });

  it("returns null for an observable with a blank value (presence path)", () => {
    expect(
      observationSeedFromPick(LESION_SIZE, emptyThresholdForHit(LESION_SIZE)),
    ).toBeNull();
  });

  it("builds an OBSERVATION seed when value is filled", () => {
    expect(
      observationSeedFromPick(LESION_SIZE, {
        operator: ">=",
        value: "7",
        value2: "",
        unit: "mm",
      }),
    ).toEqual({
      observable_id: "396361002",
      observable_term: "Lesion size, largest dimension",
      operator: ">=",
      value: 7,
      unit: "mm",
    });
  });

  it("builds a between seed when both bounds are numeric", () => {
    expect(
      observationSeedFromPick(LESION_SIZE, {
        operator: "between",
        value: "5",
        value2: "10",
        unit: "mm",
      }),
    ).toEqual({
      observable_id: "396361002",
      observable_term: "Lesion size, largest dimension",
      operator: "between",
      value: [5, 10],
      unit: "mm",
    });
  });
});

describe("isConflictingObsMultiPick", () => {
  it("is false for a single pick with a value", () => {
    expect(
      isConflictingObsMultiPick(1, [
        { ...DEFAULT_OBS_THRESHOLD, value: "7", unit: "mm" },
      ]),
    ).toBe(false);
  });

  it("is true when several picks include a filled value", () => {
    expect(
      isConflictingObsMultiPick(2, [
        { ...DEFAULT_OBS_THRESHOLD, value: "7" },
        DEFAULT_OBS_THRESHOLD,
      ]),
    ).toBe(true);
  });

  it("draftHasNumericValue rejects blank and non-numeric strings", () => {
    expect(draftHasNumericValue(DEFAULT_OBS_THRESHOLD)).toBe(false);
    expect(
      draftHasNumericValue({ ...DEFAULT_OBS_THRESHOLD, value: "x" }),
    ).toBe(false);
    expect(
      draftHasNumericValue({ ...DEFAULT_OBS_THRESHOLD, value: "7" }),
    ).toBe(true);
  });
});
