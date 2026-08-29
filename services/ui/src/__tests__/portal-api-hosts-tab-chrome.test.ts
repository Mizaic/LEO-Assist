/**
 * VT -- Platform Management API hosts tab.
 *
 * Static-source verification:
 *   - Portal registers an admin-only "API hosts" tab
 *   - Portal mounts ApiHostManagement
 *   - Panel lists hosts, registers a host, and records artefacts / IFU
 *   - UI proxy routes require a platform-admin session
 *
 * Atlas: VT-E8FEF44A / DI-14809BB8 / DO-6F6771E5
 * Look up via: get_design_control(dc_type="verification-test", dc_id="VT-E8FEF44A")
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(relPath: string): string {
  return fs.readFileSync(path.join(ROOT, relPath), "utf8");
}

describe("Platform Management API hosts tab", () => {
  test("TC-001: portal registers the API hosts tab as adminOnly", () => {
    const src = read("services/ui/src/app/portal/page.tsx");
    const tabBlock = src.match(
      /\{\s*value:\s*"api-hosts"[\s\S]*?adminOnly:\s*true[\s\S]*?\}/,
    );
    expect(tabBlock).not.toBeNull();
    expect(tabBlock![0]).toMatch(/label:\s*"API hosts"/);
  });

  test("TC-002: portal imports and renders ApiHostManagement", () => {
    const src = read("services/ui/src/app/portal/page.tsx");
    expect(src).toMatch(
      /import\s+ApiHostManagement\s+from\s+["']@\/components\/tenant\/ApiHostManagement["']/,
    );
    expect(src).toMatch(/<ApiHostManagement\s*\/>/);
  });

  test("TC-003: panel lists hosts and can register a new host", () => {
    const src = read(
      "services/ui/src/components/tenant/ApiHostManagement.tsx",
    );
    expect(src).toMatch(/listSdkHosts|\/api\/sdk\/governance\/register/);
    expect(src).toMatch(/registerSdkHost|\/api\/sdk\/governance\/hosts/);
    expect(src).toMatch(/data-testid="api-hosts-register"/);
    expect(src).toMatch(/data-testid="api-hosts-list"/);
  });

  test("TC-004: panel can record artefacts and IFU acknowledgement", () => {
    const src = read(
      "services/ui/src/components/tenant/ApiHostManagement.tsx",
    );
    expect(src).toMatch(/saas_embedding_agreement/);
    expect(src).toMatch(/dpa/);
    expect(src).toMatch(/dcb0129_reference/);
    expect(src).toMatch(/ifu_acknowledged/);
    expect(src).toMatch(/\/ifu|acknowledgeSdkHostIfu/);
  });

  test("TC-005: governance proxy routes require platform admin", () => {
    const proxy = read(
      "services/ui/src/app/api/sdk/governance/_proxy.ts",
    );
    expect(proxy).toMatch(/isPlatformAdmin/);
    expect(proxy).toMatch(/403/);
    expect(proxy).toMatch(/\/sdk\/governance\//);
  });
});
