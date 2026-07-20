/**
 * Portal / RBAC chrome -- Service Provider scopeType and OrgDrawer SP section.
 *
 * Static-source verification for multi-tenant RBAC leftovers.
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(ROOT, relPath), "utf8");
}

describe("portal-rbac chrome - Service Provider scope", () => {
  test("TC-001: OrgInfo.scopeType includes service_provider", () => {
    const src = readFile("services/ui/src/lib/authContext.tsx");
    expect(src).toMatch(
      /scopeType\?:\s*"gp"\s*\|\s*"pcn"\s*\|\s*"icb"\s*\|\s*"alliance"\s*\|\s*"service_provider"/,
    );
  });

  test("TC-002: SubOrgManagement offers service_provider MenuItem", () => {
    const src = readFile("services/ui/src/components/tenant/SubOrgManagement.tsx");
    expect(src).toMatch(/service_provider/);
    expect(src).toMatch(/Service Provider \(Hospital \/ Trust\)/);
  });

  test("TC-003: AppShell uses hiddenForScopeTypes for aggregated tiers", () => {
    const src = readFile("services/ui/src/components/AppShell.tsx");
    expect(src).toMatch(/hiddenForScopeTypes/);
    expect(src).toMatch(/\["icb",\s*"alliance"\]/);
  });

  test("TC-004: OrgDrawer has Service Provider linked-services section", () => {
    const src = readFile("services/ui/src/components/tenant/OrgDrawer.tsx");
    expect(src).toMatch(/service_provider:\s*\{\s*label:\s*"Service Provider"/);
    expect(src).toMatch(/Linked services/);
    expect(src).toMatch(/listOrgServices/);
    expect(src).toMatch(/org\.type\s*===\s*"service_provider"/);
  });
});
