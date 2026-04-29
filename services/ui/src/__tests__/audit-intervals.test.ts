import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("audit interval chart scales", () => {
  test("primary care interval uses a 90-day strip plot scale", () => {
    const src = readFile(
      "services/ui/src/components/audit/PrimaryCareIntervalSection.tsx",
    );

    expect(src).toMatch(/intervalKey="pci_days"[\s\S]*?maxDays=\{90\}/);
  });

  test("diagnostic interval keeps its longer diagnosis scale", () => {
    const src = readFile(
      "services/ui/src/components/audit/DiagnosticIntervalSection.tsx",
    );

    expect(src).toMatch(/intervalKey="di_days"[\s\S]*?maxDays=\{365\}/);
  });
});
