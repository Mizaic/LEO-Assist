/**
 * Regression coverage for Mission Control coded-data observation values.
 *
 * Static-source verification:
 *   - Observable semantic tags are normalized across spaces, underscores and case.
 *   - Value cells accept string readings as well as numeric readings.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../../..");
const SRC = fs.readFileSync(
  path.join(REPO_ROOT, "services/ui/src/components/mission-control/CodedDataTab.tsx"),
  "utf8",
);
const API_SRC = fs.readFileSync(
  path.join(REPO_ROOT, "services/ui/src/lib/missionControlApi.ts"),
  "utf8",
);

describe("CodedDataTab observation value display", () => {
  test("TC-001: normalizes observable semantic tags across punctuation", () => {
    expect(SRC).toMatch(/function\s+isObservableSemanticTag/);
    expect(SRC).toMatch(/replace\(\s*\/\[\^a-z0-9\]\/g,\s*""\s*\)/);
    expect(SRC).toMatch(/normalized\s*===\s*"observableentity"/);
  });

  test("TC-002: permits string and numeric observation values", () => {
    expect(SRC).toMatch(/value:\s*number\s*\|\s*string\s*\|\s*null/);
    expect(API_SRC).toMatch(/value:\s*number\s*\|\s*string\s*\|\s*null/);
  });
});
