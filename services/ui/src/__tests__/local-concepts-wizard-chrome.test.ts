/**
 * Static-source VT for Local Concepts wizard chrome (package step).
 */
import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("Local concepts wizard chrome", () => {
  const src = readFile(
    "services/ui/src/app/admin/guidance/local-concepts/page.tsx",
  );

  test("TC-001: exposes wizard test ids including package step", () => {
    expect(src).toMatch(/data-testid="local-concepts-wizard"/);
    expect(src).toMatch(/data-testid="wizard-step-package"/);
    expect(src).toMatch(/data-testid="wizard-step-define"/);
    expect(src).toMatch(/["']data-testid["']\s*:\s*["']local-concept-alias["']/);
    expect(src).toMatch(/data-testid="local-concept-dry-run"/);
    expect(src).toMatch(/data-testid="local-concept-approve"/);
    expect(src).toMatch(/["']data-testid["']\s*:\s*["']local-concept-package["']/);
  });

  test("TC-002: calls create-local with package_id and dry-run APIs", () => {
    expect(src).toMatch(/createLocalConceptWithAlias/);
    expect(src).toMatch(/dryRunLocalConceptRecovery/);
    expect(src).toMatch(/package_id/);
    expect(src).toMatch(/listLocalTerminologyPackages/);
  });

  test("TC-003: states Audit Domains stay on SNOMED", () => {
    expect(src).toMatch(/Audit domains stay on real[\s\S]*SNOMED/i);
  });

  test("TC-004: package scope picker global vs tenant", () => {
    expect(src).toMatch(/local-concept-package-scope/);
    expect(src).toMatch(/Global \(all organisations\)/);
    expect(src).toMatch(/This organisation \(tenant\)/);
  });
});
