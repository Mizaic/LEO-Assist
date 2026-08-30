/**
 * Soft checks and FIT policy in the guidance editor.
 *
 * Atlas: DI-C136E4B7, DI-0C904503, DI-55CCC312
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf-8");
}

describe("Soft checks and FIT policy editor", () => {
  it("chip editor shows Soft checks beside Blocked codes", () => {
    const dialog = read("ConceptSynonymDialog.tsx");
    expect(dialog).toMatch(/SoftChecksPanel/);
    expect(dialog).toMatch(/BlockedCodesPanel/);
    const panel = read("SoftChecksPanel.tsx");
    expect(panel).toMatch(/Soft checks/);
    expect(panel).toMatch(/enforcement/);
    expect(panel).toMatch(/SOFT_QUALIFIER_LABELS/);
    expect(panel).toMatch(/RECENCY_LABELS/);
    expect(panel).toMatch(/we will still offer the test if we cannot check this/);
  });

  it("exposes the five soft kinds and a hard toggle", () => {
    const copy = read("copy.ts");
    expect(copy).toMatch(/first_presentation/);
    expect(copy).toMatch(/repeat_or_chronic/);
    expect(copy).toMatch(/unexplained/);
    expect(copy).toMatch(/unintentional/);
    expect(copy).toMatch(/persistent/);
    const panel = read("SoftChecksPanel.tsx");
    expect(panel).toMatch(/Hard/);
  });

  it("rule details expose FIT policy Required / Not required / Result gate / None", () => {
    const src = read("PriorityPanel.tsx");
    expect(src).toMatch(/FIT policy/);
    expect(src).toMatch(/FIT_POLICY_LABELS/);
    const copy = read("copy.ts");
    expect(copy).toMatch(/required/);
    expect(copy).toMatch(/not_required/);
    expect(copy).toMatch(/result_gate/);
  });

  it("save payload keeps soft_qualifiers and investigation_policy", () => {
    const ops = read("treeOps.ts");
    expect(ops).toMatch(/soft_qualifiers/);
    const dialog = read("index.tsx");
    expect(dialog).toMatch(/investigation_policy/);
  });
});
