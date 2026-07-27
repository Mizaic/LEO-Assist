/**
 * FE/Python situation-skeleton parity.
 *
 * Loads the shared fixture under tests/fixtures/situation_skeleton_parity.json
 * and asserts splitPathways (or single/tree fallback) matches expected counts.
 *
 * Atlas: DI-85AB13D7 / DO-BEFC4C67
 */
import * as fs from "fs";
import * as path from "path";
import {
  splitPathways,
  type RecommendationStructure,
} from "../SentenceEditor/pathwayTextSplit";

type ParityCase = {
  id: string;
  text: string;
  structure: RecommendationStructure | null;
  expected_count: number;
  expected_source: "structure" | "heuristic" | "tree" | "single";
  fe_null_ok?: boolean;
};

const FIXTURE_PATH = path.resolve(
  __dirname,
  "../../../../../../../../tests/fixtures/situation_skeleton_parity.json",
);

function loadCases(): ParityCase[] {
  const raw = JSON.parse(fs.readFileSync(FIXTURE_PATH, "utf8")) as {
    cases: ParityCase[];
  };
  return raw.cases;
}

describe("situation skeleton FE/Python parity", () => {
  it("loads the shared fixture", () => {
    expect(fs.existsSync(FIXTURE_PATH)).toBe(true);
    expect(loadCases().length).toBeGreaterThanOrEqual(3);
  });

  for (const parityCase of loadCases()) {
    it(`${parityCase.id}: count/source agree with Python fixture`, () => {
      const boundaries = splitPathways(parityCase.text, parityCase.structure);
      if (parityCase.fe_null_ok) {
        // Python emits a single single/tree shell; FE splitPathways returns null.
        expect(boundaries).toBeNull();
        expect(parityCase.expected_count).toBe(1);
        return;
      }
      expect(boundaries).not.toBeNull();
      expect(boundaries).toHaveLength(parityCase.expected_count);
      expect(
        boundaries!.every((b) => b.source === parityCase.expected_source),
      ).toBe(true);
    });
  }
});
