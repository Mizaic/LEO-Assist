/**
 * VT -- Platform Management people full CRUD.
 *
 * Static-source verification:
 *   - People can be added, edited, and removed
 *   - The list shows groups and an old-schema badge
 *   - Edit saves name, orgs, groups, and can clear legacy roles
 *
 * Atlas: VT-A6EE05FF. Look up via get_design_control(
 *   dc_type="verification-test", dc_id="VT-A6EE05FF").
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(relPath: string): string {
  return fs.readFileSync(path.join(ROOT, relPath), "utf8");
}

describe("Platform Management people CRUD", () => {
  test("TC-001: people panel can add, edit, and remove a person", () => {
    const src = read("services/ui/src/components/tenant/UserManagement.tsx");
    expect(src).toMatch(/Add person|inviteOpen/);
    expect(src).toMatch(/data-testid="people-edit"|setEditUser|Edit person/);
    expect(src).toMatch(/deleteUser|deactivateConfirm/);
  });

  test("TC-002: people list shows groups and old role schema", () => {
    const src = read("services/ui/src/components/tenant/PeopleList.tsx");
    expect(src).toMatch(/legacy_roles|Old role schema/);
    expect(src).toMatch(/u\.groups|No groups/);
  });

  test("TC-003: edit dialog patches user including group_ids", () => {
    const edit = read("services/ui/src/components/tenant/UserEditDialog.tsx");
    expect(edit).toMatch(/patchUser/);
    expect(edit).toMatch(/group_ids/);
    expect(edit).toMatch(/clear_legacy_roles/);
    expect(edit).toMatch(/data-testid="people-edit-save"/);
  });

  test("TC-004: admin client sends groups and legacy_roles on patch", () => {
    const src = read("services/ui/src/lib/api/admin.ts");
    expect(src).toMatch(/legacy_roles/);
    expect(src).toMatch(/group_ids\?:/);
    expect(src).toMatch(/clear_legacy_roles/);
  });
});
