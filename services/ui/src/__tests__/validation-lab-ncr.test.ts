/**
 * Validation Lab product NCR lookup and create -- acceptance checks.
 *
 * Design Controls: DI-287FFFD0 / DI-ED5A9AC3
 */
import fs from "fs";
import path from "path";

import {
  emptyNcrDraft,
  filterProductNcrs,
  ncrDraftError,
  visibleProductNcrs,
  type ProductNcr,
} from "../app/admin/validation-lab/ncrDraft";
import {
  addInvestigationCase,
  removeInvestigationCase,
} from "../app/admin/validation-lab/ncrInvestigationCases";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "validation-lab");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Validation Lab product NCR", () => {
  const door = read("ClinicalDoor.tsx");
  const panel = read("ClinicalNcrPanel.tsx");
  const api = read("clinicalNcrApi.ts");
  const router = fs.readFileSync(
    path.resolve(
      __dirname,
      "../../../../services/api/app/routers/validation_lab_ncr.py",
    ),
    "utf8",
  );
  const shape = fs.readFileSync(
    path.resolve(__dirname, "../../../../libs/atlas_qms/ncr_shape.py"),
    "utf8",
  );

  it("shows lookup and open-new on the investigate door", () => {
    expect(door).toMatch(/ClinicalNcrPanel/);
    expect(door).toMatch(/Start with the product non-conformance/);
    expect(door).toMatch(/!linkedNcr/);
    expect(door).toMatch(/onLinked/);
    expect(door).toMatch(/validation-lab-clinical-after-ncr/);
    expect(door).toMatch(/Cases in this investigation/);
    expect(door).toMatch(/stay in LEO/);
    expect(door).toMatch(/Atlas gets a\s+note with numbers removed/);
    expect(door).toMatch(/ncrInvestigationCases/);
    expect(door).toMatch(/useNcrInvestigation/);
    expect(door).toMatch(/logReview/);
    expect(panel).toMatch(/validation-lab-ncr-panel/);
    expect(panel).toMatch(/Open a new NCR/);
    expect(panel).toMatch(/Minimum needed/);
    expect(panel).toMatch(/Do not put an NHS number/);
    expect(panel).toMatch(/Product is locked/);
    expect(panel).toMatch(/Type is locked/);
    expect(panel).toMatch(/Found during testing/);
    expect(panel).toMatch(/Closed and/);
    expect(panel).toMatch(/cancelled records stay in Atlas/);
    expect(panel).not.toMatch(/product_id/);
    expect(panel).not.toMatch(/slice\(0,\s*8\)/);
    expect(panel).toMatch(/visibleProductNcrs/);
  });

  it("persists cases locally and logs redacted notes", () => {
    const invApi = read("ncrInvestigationApi.ts");
    const hook = read("useNcrInvestigation.ts");
    expect(invApi).toMatch(/investigation\/cases/);
    expect(invApi).toMatch(/investigation\/events/);
    expect(invApi).toMatch(/nhs_number/);
    expect(invApi).toMatch(/ubrn/);
    expect(hook).toMatch(/saveInvestigationCases/);
    expect(hook).toMatch(/logInvestigationEvent/);
    expect(hook).toMatch(/Local run/);
    expect(hook).not.toMatch(/nhs_number/);
  });

  it("lists and creates through the locked product API", () => {
    expect(api).toMatch(/\/api\/validation-lab\/ncrs/);
    expect(api).toMatch(/getProductNcr/);
    expect(api).not.toMatch(/product_id/);
    expect(api).not.toMatch(/nhs_number/);
    expect(api).not.toMatch(/ubrn/);
    expect(router).toMatch(/LEO_CDS_PRODUCT_ID/);
    expect(router).not.toMatch(/body\.product_id/);
    expect(shape).toMatch(/LEO_CDS_PRODUCT_ID/);
    const client = fs.readFileSync(
      path.resolve(__dirname, "../../../../libs/atlas_qms/ncr_client.py"),
      "utf8",
    );
    expect(client).toMatch(/X-Service-Token/);
    expect(client).toMatch(/X-Organization-ID/);
    expect(client).toMatch(/ORGANIZATION_REQUIRED/);
    expect(client).toMatch(/GET", f"\/non-conformances\/\{safe_id\}/);
    expect(client).not.toMatch(/advance_non_conformance/);
    expect(client).not.toMatch(/Authorization/);
  });

  it("requires title, what went wrong, and severity", () => {
    expect(ncrDraftError(emptyNcrDraft())).toMatch(/Title/);
    expect(
      ncrDraftError({
        title: "Missed code",
        description: "x",
        severity: "minor",
      }),
    ).toMatch(/what went wrong/);
    expect(
      ncrDraftError({
        title: "Missed code",
        description: "LEO missed a finding.",
        severity: "minor",
      }),
    ).toBe("");
  });

  it("filters product records by title", () => {
    const rows: ProductNcr[] = [
      {
        id: "1",
        title: "Missed code",
        description: "",
        severity: "minor",
        status: "identified",
        created_at: "",
        product_id: "PROD-LEO",
      },
      {
        id: "2",
        title: "Wrong unit",
        description: "",
        severity: "major",
        status: "closed",
        created_at: "",
        product_id: "PROD-LEO",
      },
    ];
    expect(filterProductNcrs(rows, "missed").map((row) => row.id)).toEqual(["1"]);
    expect(filterProductNcrs(rows, "").map((row) => row.id)).toEqual(["1"]);
    expect(
      filterProductNcrs(rows, "2").map((row) => row.id),
    ).toEqual(["2"]);
  });

  it("keeps more than eight search matches on screen", () => {
    const rows: ProductNcr[] = Array.from({ length: 12 }, (_, index) => ({
      id: String(index + 1),
      title: `Open miss ${index + 1}`,
      description: "",
      severity: "minor",
      status: "identified",
      created_at: "",
      product_id: "PROD-LEO",
    }));
    expect(visibleProductNcrs(rows)).toHaveLength(12);
  });

  it("lets one investigation hold more than one case in LEO", () => {
    const a = {
      run_id: "r1",
      status: "done",
      created_at: "",
      plan_id: "",
      patient_id: "p1",
      patient_name: "A",
      nhs_number: "9434765919",
    };
    const b = {
      run_id: "r2",
      status: "done",
      created_at: "",
      plan_id: "",
      patient_id: "p2",
      patient_name: "B",
      ubrn: "000012345678",
    };
    const two = addInvestigationCase(addInvestigationCase([], a), b);
    expect(two).toHaveLength(2);
    expect(removeInvestigationCase(two, a)).toHaveLength(1);
  });
});
