/**
 * VT-8A590E7A -- Knowledge areas tenant completeness list.
 *
 * Static-source verification:
 *   - organisation filter loads /api/completeness-domains/
 *   - tenant rows show completeness groups
 *   - selected organisation id is passed on the list request
 *   - NICE and built-in filters still use the knowledge-graph domains API
 *
 * Atlas trace: UN-3B25A20E, DI-10667413, DO-9C9CB1D8, VT-8A590E7A
 */

import * as fs from "fs";
import * as path from "path";

const REPO = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO, rel), "utf8");
}

const PAGE = "services/ui/src/app/settings/domains/page.tsx";
const HOOK = "services/ui/src/app/settings/domains/_components/useDomainsList.ts";
const TENANT =
  "services/ui/src/app/settings/domains/_components/TenantCompletenessList.tsx";
const API =
  "services/ui/src/app/settings/domains/_components/tenantCompletenessApi.ts";
const ROUTER = "services/api/app/routers/completeness_domains.py";

describe("VT-8A590E7A - Knowledge areas tenant completeness list", () => {
  test("TC-001: organisation filter loads domains from the patient-graph completeness-domains API", () => {
    const hook = read(HOOK);
    const api = read(API);
    expect(hook).toMatch(/filter === ["']tenant["']/);
    expect(hook).toMatch(/fetchTenantCompletenessDomains/);
    expect(hook + api).toMatch(/\/api\/completeness-domains\//);
    expect(hook).not.toMatch(/fetchDomains\(\s*["']tenant["']\s*\)/);
  });

  test("TC-002: tenant rows show the domain name and completeness groups", () => {
    const src = read(TENANT);
    expect(src).toMatch(/domain_name/);
    expect(src).toMatch(/completeness_groups/);
    expect(src).toMatch(/data-testid=["']tenant-completeness-list["']/);
  });

  test("TC-003: list request passes the selected organisation id", () => {
    const api = read(API);
    const router = read(ROUTER);
    expect(api).toMatch(/organization_id/);
    expect(api).toMatch(/completeness-domains\//);
    expect(router).toMatch(/organization_id/);
    expect(router).toMatch(/org\.id\s*=\s*\$organization_id|org\.id = \$organization_id/);
  });

  test("TC-004: NICE and built-in areas still load from the knowledge-graph domains API", () => {
    const hook = read(HOOK);
    const page = read(PAGE);
    expect(hook).toMatch(/fetchDomains\(/);
    expect(page).toMatch(/id:\s*["']nice["']/);
    expect(page).toMatch(/id:\s*["']platform["']/);
    expect(hook).toMatch(/sourceFilter\s*===\s*["']all["']|filter === ["']all["']/);
  });
});
