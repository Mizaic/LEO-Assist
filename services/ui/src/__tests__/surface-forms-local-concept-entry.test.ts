/**
 * Static-source VT: Surface Forms entry to Create local concept wizard.
 */
import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("Surface Forms local concept entry chrome", () => {
  const sf = readFile("services/ui/src/app/settings/surface-forms/page.tsx");
  const guidelines = readFile(
    "services/ui/src/app/admin/guidance/LoadedGuidelinesPanel.tsx",
  );

  test("TC-001: toolbar Create local concept navigates to wizard", () => {
    expect(sf).toMatch(/create-local-concept/);
    expect(sf).toMatch(/Create local concept/);
    expect(sf).toMatch(/\/admin\/guidance\/local-concepts/);
  });

  test("TC-002: createLocal query deep-links to wizard", () => {
    expect(sf).toMatch(/createLocal/);
    expect(sf).toMatch(/router\.replace\(\s*["']\/admin\/guidance\/local-concepts["']/);
  });

  test("TC-003: Guidelines button deep-links to Surface Forms entry", () => {
    expect(guidelines).toMatch(/Create local concept/);
    expect(guidelines).toMatch(
      /\/settings\/surface-forms\?createLocal=1/,
    );
  });
});
