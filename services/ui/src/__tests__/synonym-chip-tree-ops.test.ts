/**
 * Synonym chip + treeOps unit tests (UN-LEO-AI-093 / DI-LEO-AI-511).
 *
 * Covers the small pure helpers the dialog reaches for when the
 * SynonymChipEditor dispatches NodeUpdate actions:
 *   - addSeed / removeSeed / setPrimarySeed
 *   - toggleIncludeDescendants / setSeedDistance
 *   - addExcluded / removeExcluded
 *   - applyUpdate routes the new NodeUpdate variants correctly
 *   - findValidationError catches forbidden states (empty seeds,
 *     primary not in seeds, seed/excluded overlap)
 *
 * No live render is required for these helpers, so we keep the test
 * static and fast (per `code-quality.mdc::Testing::TypeScript`).
 */

import {
  addExcluded,
  addSeed,
  applyUpdate,
  findValidationError,
  removeExcluded,
  removeSeed,
  setPrimarySeed,
  setSeedDistance,
  toggleIncludeDescendants,
} from "@/app/admin/guidance/EditRuleDialog/treeOps";
import type {
  EditableLogicNode,
  LogicSeed,
} from "@/app/admin/guidance/EditRuleDialog/types";

const seed = (cid: string, term: string, extra: Partial<LogicSeed> = {}): LogicSeed => ({
  snomed_concept_id: cid,
  preferred_term: term,
  semantic_tag: "finding",
  include_descendants: true,
  ...extra,
});

const legacyChip = (): EditableLogicNode => ({
  node_id: "n1",
  kind: "CONCEPT",
  criterion: {
    snomed_concept_id: "1",
    preferred_term: "Smoker",
    semantic_tag: "finding",
  },
});

describe("treeOps -- synonym set helpers", () => {
  test("addSeed promotes a legacy chip to a 2-seed synonym set", () => {
    const out = addSeed(legacyChip(), seed("2", "Cigarette smoker"));
    const seeds = out.criterion!.seeds!;
    expect(seeds.map((s) => s.snomed_concept_id)).toEqual(["1", "2"]);
    expect(out.criterion!.primary_concept_id).toBe("1");
    expect(out.criterion!.snomed_concept_id).toBe("1");
  });

  test("addSeed is idempotent for the same SNOMED id", () => {
    const after = addSeed(legacyChip(), seed("1", "Smoker"));
    expect(after.criterion!.seeds!.length).toBe(1);
  });

  test("removeSeed refuses to drop the only remaining seed", () => {
    const before = legacyChip();
    const after = removeSeed(before, "1");
    // The chip is promoted to a 1-seed synonym set but the seed list
    // is not allowed to fall below 1 -- the chip would otherwise
    // become uncodable, and the API would reject the save.
    expect((after.criterion!.seeds ?? []).length).toBe(1);
    expect(after.criterion!.snomed_concept_id).toBe("1");
  });

  test("removeSeed picks a new primary when the primary is removed", () => {
    const node = addSeed(legacyChip(), seed("2", "Cigarette smoker"));
    const after = removeSeed(node, "1");
    expect(after.criterion!.snomed_concept_id).toBe("2");
    expect(after.criterion!.primary_concept_id).toBe("2");
    expect(after.criterion!.preferred_term).toBe("Cigarette smoker");
  });

  test("setPrimarySeed swaps the chip label to the chosen seed", () => {
    const node = addSeed(legacyChip(), seed("2", "Cigarette smoker"));
    const after = setPrimarySeed(node, "2");
    expect(after.criterion!.primary_concept_id).toBe("2");
    expect(after.criterion!.preferred_term).toBe("Cigarette smoker");
  });

  test("toggleIncludeDescendants flips just the targeted seed", () => {
    const node = addSeed(legacyChip(), seed("2", "Cigarette smoker"));
    const after = toggleIncludeDescendants(node, "2");
    const updated = after.criterion!.seeds!.find((s) => s.snomed_concept_id === "2")!;
    const untouched = after.criterion!.seeds!.find((s) => s.snomed_concept_id === "1")!;
    expect(updated.include_descendants).toBe(false);
    expect(untouched.include_descendants ?? true).toBe(true);
  });

  test("setSeedDistance accepts null to clear the override", () => {
    const node = setSeedDistance(legacyChip(), "1", 4);
    expect(node.criterion!.seeds![0].distance_child).toBe(4);
    const cleared = setSeedDistance(node, "1", null);
    expect(cleared.criterion!.seeds![0].distance_child).toBeNull();
  });

  test("addExcluded refuses to block an id that is also a seed", () => {
    const node = addExcluded(legacyChip(), "1");
    expect(node.criterion!.excluded_concept_ids ?? []).toEqual([]);
  });

  test("addExcluded then removeExcluded returns to no-exclusion state", () => {
    const node = addExcluded(legacyChip(), "999");
    expect(node.criterion!.excluded_concept_ids).toEqual(["999"]);
    const cleared = removeExcluded(node, "999");
    expect(cleared.criterion!.excluded_concept_ids).toEqual([]);
  });
});

describe("applyUpdate -- routes synonym ops by kind", () => {
  test("add_seed dispatches through to addSeed", () => {
    const root = legacyChip();
    const after = applyUpdate(root, {
      kind: "add_seed",
      nodeId: "n1",
      seed: seed("2", "Cigarette smoker"),
    })!;
    expect(after.criterion!.seeds!.length).toBe(2);
  });

  test("set_primary_seed and toggle_include_descendants compose", () => {
    let root: EditableLogicNode | null = legacyChip();
    root = applyUpdate(root, {
      kind: "add_seed",
      nodeId: "n1",
      seed: seed("2", "Cigarette smoker"),
    });
    root = applyUpdate(root!, {
      kind: "set_primary_seed",
      nodeId: "n1",
      conceptId: "2",
    });
    root = applyUpdate(root!, {
      kind: "toggle_include_descendants",
      nodeId: "n1",
      conceptId: "2",
    });
    const seeds = root!.criterion!.seeds!;
    const primary = seeds.find((s) => s.snomed_concept_id === "2")!;
    expect(root!.criterion!.primary_concept_id).toBe("2");
    expect(primary.include_descendants).toBe(false);
  });
});

describe("findValidationError -- synonym set rules", () => {
  test("flags empty seed list when seeds array provided but empty", () => {
    const node: EditableLogicNode = {
      node_id: "n1",
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "",
        preferred_term: "",
        seeds: [],
      },
    };
    const err = findValidationError(node);
    expect(err).toMatch(/symptom|sign|pill|code|seed/i);
  });

  test("flags primary id that is not in seeds", () => {
    const node: EditableLogicNode = {
      node_id: "n1",
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "1",
        preferred_term: "Smoker",
        primary_concept_id: "999",
        seeds: [seed("1", "Smoker")],
      },
    };
    const err = findValidationError(node);
    expect(err).toMatch(/main|primary/i);
  });

  test("flags overlap between seeds and excluded ids", () => {
    const node: EditableLogicNode = {
      node_id: "n1",
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "1",
        preferred_term: "Smoker",
        seeds: [seed("1", "Smoker")],
        excluded_concept_ids: ["1"],
      },
    };
    const err = findValidationError(node);
    expect(err).toMatch(/block|exclud/i);
  });

  test("returns null for a valid 2-seed criterion", () => {
    const node = addSeed(legacyChip(), seed("2", "Cigarette smoker"));
    expect(findValidationError(node)).toBeNull();
  });
});
