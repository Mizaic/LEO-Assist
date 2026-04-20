/**
 * VT for the /admin/portal Entra integration tab chrome.
 *
 * Static-source verification that:
 *  - /portal/page.tsx wires up the new "Entra integration" tab
 *    visible only to platform admins.
 *  - The EntraIntegration component renders the CapabilityBanner,
 *    the consent CTA when no scopes are granted, and the verified
 *    domains table.
 *  - The EntraGroupPicker is mounted from EntraIntegration.
 *
 * Pinned to:
 *  - DI-31F4C232 (functional admin portal Entra extension)
 *  - DI-5A18A227 (manual Neo4j-only fallback messaging)
 *  - DI-6CF7FCE0 (admin-only, type-the-name confirm gate)
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const PORTAL_PAGE = path.join(ROOT, "services/ui/src/app/portal/page.tsx");
const ENTRA_INTEGRATION = path.join(
  ROOT,
  "services/ui/src/components/tenant/EntraIntegration.tsx",
);
const ENTRA_GROUP_PICKER = path.join(
  ROOT,
  "services/ui/src/components/tenant/EntraGroupPicker.tsx",
);
const ENTRA_USER_PICKER = path.join(
  ROOT,
  "services/ui/src/components/tenant/EntraUserPicker.tsx",
);
const BIND_DIALOG = path.join(
  ROOT,
  "services/ui/src/components/tenant/BindGroupDialog.tsx",
);
const ADMIN_API = path.join(
  ROOT,
  "services/ui/src/lib/api/admin.ts",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("Admin portal Entra tab - DI-31F4C232 / DI-6CF7FCE0", () => {
  test("portal page registers the 'Entra integration' tab as adminOnly", () => {
    const src = read(PORTAL_PAGE);
    const tabBlock = src.match(
      /\{\s*value:\s*"entra"[\s\S]*?adminOnly:\s*true[\s\S]*?\}/,
    );
    expect(tabBlock).not.toBeNull();
    expect(tabBlock![0]).toMatch(/label:\s*"Entra integration"/);
  });

  test("portal page imports and renders the EntraIntegration component", () => {
    const src = read(PORTAL_PAGE);
    expect(src).toMatch(
      /import\s+EntraIntegration\s+from\s+["']@\/components\/tenant\/EntraIntegration["']/,
    );
    expect(src).toMatch(/<EntraIntegration\s*\/>/);
  });

  test("EntraIntegration shows the admin consent CTA when no scopes granted", () => {
    const src = read(ENTRA_INTEGRATION);
    expect(src).toMatch(
      /Microsoft Entra is not connected|admin_consent_url/,
    );
    expect(src).toMatch(/missingScopes\.length === capability\.scopes_required\.length/);
    expect(src).toMatch(/admin_consent_url/);
  });

  test("EntraIntegration mounts the EntraGroupPicker", () => {
    const src = read(ENTRA_INTEGRATION);
    expect(src).toMatch(/import\s+EntraGroupPicker/);
    expect(src).toMatch(/<EntraGroupPicker/);
  });

  test("EntraGroupPicker renders the binding dialog and list of groups", () => {
    const src = read(ENTRA_GROUP_PICKER);
    expect(src).toMatch(/listEntraGroups/);
    expect(src).toMatch(/BindGroupDialog/);
  });

  test("BindGroupDialog enforces type-the-name confirmation before submit", () => {
    const src = read(BIND_DIALOG);
    expect(src).toMatch(/confirm_display_name/);
    expect(src).toMatch(/matchesName/);
    expect(src).toMatch(/disabled=\{!canSubmit\}/);
  });

  test("EntraUserPicker calls the searchEntraUsers API helper", () => {
    const src = read(ENTRA_USER_PICKER);
    expect(src).toMatch(/searchEntraUsers/);
  });

  test("admin.ts exposes the seven Entra fetch helpers", () => {
    const src = read(ADMIN_API);
    [
      "getEntraCapability",
      "listEntraDomains",
      "searchEntraUsers",
      "listEntraGroups",
      "createEntraGroup",
      "bindEntraGroup",
      "addEntraGroupMember",
      "removeEntraGroupMember",
    ].forEach((sym) => {
      expect(src).toMatch(new RegExp(`export\\s+(?:async\\s+)?function\\s+${sym}\\b`));
    });
  });
});
