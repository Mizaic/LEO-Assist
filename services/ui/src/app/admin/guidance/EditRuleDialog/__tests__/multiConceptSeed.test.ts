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
  buildMultiSeedCriterion,
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
