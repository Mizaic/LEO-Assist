/**
 * Teach this form must reuse the tenant org/service catalog.
 *
 * Atlas trace: DI-26546721, UN-3B25A20E, DO-020C7B5C
 */
import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const SCOPE_SRC = fs.readFileSync(
  path.join(ROOT, "services/ui/src/components/operations/FormSchemaScopeFields.tsx"),
  "utf8",
);
const ADMIN_API_SRC = fs.readFileSync(
  path.join(ROOT, "services/ui/src/lib/api/admin.ts"),
  "utf8",
);
const ADMIN_ROUTER = fs.readFileSync(
  path.join(ROOT, "services/api/app/routers/admin.py"),
  "utf8",
);
const FORM_SCHEMA_ROUTER = fs.readFileSync(
  path.join(ROOT, "services/api/app/routers/form_schema.py"),
  "utf8",
);

describe("Teach form org/service catalog", () => {
  it("loads organisations from the tenant drawer listOrgs helper", () => {
    expect(SCOPE_SRC).toMatch(/listOrgs/);
    expect(SCOPE_SRC).toMatch(/from\s+["']@\/lib\/api\/admin["']/);
    expect(SCOPE_SRC).not.toMatch(/\/api\/form-schemas\/scope\/organizations/);
  });

  it("loads services from the tenant drawer listOrgServices helper", () => {
    expect(SCOPE_SRC).toMatch(/listOrgServices/);
    expect(ADMIN_API_SRC).toMatch(/\$\{ADMIN_BASE\}\/orgs/);
    expect(ADMIN_API_SRC).toMatch(/\/services/);
  });

  it("surfaces a catalog load error instead of leaving pickers silently empty", () => {
    expect(SCOPE_SRC).toMatch(/Could not load organisations|Could not load the organisation list/);
    expect(SCOPE_SRC).not.toMatch(/Keep empty pickers when the catalog is unavailable/);
  });

  it("does not invent a second org Cypher catalog on the form-schema router", () => {
    expect(FORM_SCHEMA_ROUTER).not.toMatch(/LIST_SCOPE_ORGANIZATIONS/);
    expect(FORM_SCHEMA_ROUTER).not.toMatch(/LIST_SCOPE_SERVICES/);
  });

  it("lets a form teacher read the existing admin org catalog", () => {
    expect(ADMIN_ROUTER).toMatch(/list_orgs/);
    expect(ADMIN_ROUTER).toMatch(/require_org_catalog_reader|FORM_TEACHER|validation/);
  });
});
