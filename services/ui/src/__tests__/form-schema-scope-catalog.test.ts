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

// ---------------------------------------------------------------------------
// Locked pickers: pre-population from extraction context
// ---------------------------------------------------------------------------

const ANNOTATOR_SRC = fs.readFileSync(
  path.join(ROOT, "services/ui/src/components/operations/FormSchemaAnnotator.tsx"),
  "utf8",
);
const DIALOG_SRC = fs.readFileSync(
  path.join(ROOT, "services/ui/src/components/operations/ExtractionQualityReviewDialog.tsx"),
  "utf8",
);

describe("Teach form locked pickers -- pre-population from extraction context", () => {
  it("FormSchemaAnnotator accepts initialOrganizationId and initialServiceId props", () => {
    expect(ANNOTATOR_SRC).toMatch(/initialOrganizationId/);
    expect(ANNOTATOR_SRC).toMatch(/initialServiceId/);
  });

  it("FormSchemaAnnotator passes locked flag to FormSchemaScopeFields when initial values set", () => {
    expect(ANNOTATOR_SRC).toMatch(/locked/);
  });

  it("FormSchemaScopeFields accepts a locked prop", () => {
    expect(SCOPE_SRC).toMatch(/locked[\s?:]/);
  });

  it("FormSchemaScopeFields renders Chip elements in locked mode", () => {
    expect(SCOPE_SRC).toMatch(/Chip/);
    expect(SCOPE_SRC).toMatch(/locked/);
  });

  it("ExtractionQualityReviewDialog reads organization_id and service_id from API response", () => {
    expect(DIALOG_SRC).toMatch(/organization_id/);
    expect(DIALOG_SRC).toMatch(/service_id/);
  });

  it("ExtractionQualityReviewDialog passes initialOrganizationId and initialServiceId to FormSchemaAnnotator", () => {
    expect(DIALOG_SRC).toMatch(/initialOrganizationId/);
    expect(DIALOG_SRC).toMatch(/initialServiceId/);
  });

  it("extraction review backend query returns organization_id and service_id fields", () => {
    const storeSrc = fs.readFileSync(
      path.join(ROOT, "libs/pipeline/extraction_review_store.py"),
      "utf8",
    );
    expect(storeSrc).toMatch(/organization_id/);
    expect(storeSrc).toMatch(/service_id/);
    expect(storeSrc).toMatch(/healthcare_service_org_id/);
    expect(storeSrc).toMatch(/healthcare_service_id/);
  });
});
