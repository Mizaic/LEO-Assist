/**
 * Unit tests for the shared pathway-split heuristic -- VT parity task
 * for the sentence-style rule builder plan.
 *
 * The critical cases:
 *  - NG12 1.2.9: `AND[DEMOGRAPHIC(age>=55), OR[6 pathways]]` -- OR at
 *    depth 1 must still be detected as a pathway split.
 *  - NG12 1.1.3: `AND[DEMOGRAPHIC(age>=40), OR[leaf, leaf, ...]]` -- a
 *    flat OR of findings is ONE situation ("any of these"), not N
 *    pathways.
 */
import { isPathwaySplit, type PathwaySplitNode } from "../pathwayDetection";
import { makeNg12129Tree } from "./fixtures/ng12129";

function concept(): PathwaySplitNode {
  return { kind: "CONCEPT" };
}

function andOf(...children: PathwaySplitNode[]): PathwaySplitNode {
  return { kind: "AND", children };
}

describe("isPathwaySplit", () => {
  it("returns true for an OR of grouped branches at depth 0", () => {
    expect(
      isPathwaySplit(
        { kind: "OR", children: [andOf(concept()), andOf(concept())] },
        0,
      ),
    ).toBe(true);
  });

  it("returns true for an OR of grouped branches at depth 1", () => {
    expect(
      isPathwaySplit(
        { kind: "OR", children: [andOf(concept()), andOf(concept())] },
        1,
      ),
    ).toBe(true);
  });

  it("returns false for a flat OR of leaf concepts (NG12 1.1.3 shape)", () => {
    expect(
      isPathwaySplit({ kind: "OR", children: [concept(), concept()] }, 0),
    ).toBe(false);
    expect(
      isPathwaySplit({ kind: "OR", children: [concept(), concept()] }, 1),
    ).toBe(false);
  });

  it("returns true when at least one OR child is a group (mixed shape)", () => {
    expect(
      isPathwaySplit(
        { kind: "OR", children: [concept(), andOf(concept(), concept())] },
        0,
      ),
    ).toBe(true);
  });

  it("returns false for an OR deeper than depth 1", () => {
    expect(
      isPathwaySplit(
        { kind: "OR", children: [andOf(concept()), andOf(concept())] },
        2,
      ),
    ).toBe(false);
  });

  it("returns false for a single-child OR", () => {
    expect(isPathwaySplit({ kind: "OR", children: [andOf(concept())] }, 0)).toBe(
      false,
    );
  });

  it("returns false for a non-OR group", () => {
    expect(
      isPathwaySplit({ kind: "AND", children: [concept(), concept()] }, 0),
    ).toBe(false);
  });

  it("is case-insensitive on kind", () => {
    expect(
      isPathwaySplit(
        { kind: "or", children: [andOf(concept()), andOf(concept())] },
        0,
      ),
    ).toBe(true);
  });

  it("NG12 1.2.9: detects the OR nested one level inside the demographic AND", () => {
    const tree = makeNg12129Tree();
    expect(tree.kind).toBe("AND");
    expect(tree.children).toHaveLength(2);

    const [demographic, or] = tree.children!;
    expect(demographic.kind).toBe("DEMOGRAPHIC");
    expect(or.kind).toBe("OR");
    expect(or.children).toHaveLength(6);

    // The literal root (the AND) is not itself a pathway split...
    expect(isPathwaySplit(tree, 0)).toBe(false);
    // ...but the OR one level down is, which is exactly the shape a
    // literal-root-only check like the old isPathwayRoot() would miss.
    expect(isPathwaySplit(or, 1)).toBe(true);
  });

  it("NG12 1.1.3: flat OR of findings under age is not a pathway split", () => {
    const findings = {
      kind: "OR",
      children: [
        { kind: "CONCEPT" },
        { kind: "CONCEPT" },
        { kind: "CONCEPT" },
        { kind: "CONCEPT" },
        { kind: "CONCEPT" },
      ],
    };
    const tree: PathwaySplitNode = {
      kind: "AND",
      children: [{ kind: "DEMOGRAPHIC" }, findings],
    };
    expect(isPathwaySplit(tree, 0)).toBe(false);
    expect(isPathwaySplit(findings, 1)).toBe(false);
  });
});
