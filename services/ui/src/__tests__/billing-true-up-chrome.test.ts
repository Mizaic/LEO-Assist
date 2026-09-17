/**
 * Atlas trace:
 *   DI: DI-3E297B23
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
 */
import fs from "fs";
import path from "path";

const trueUp = fs.readFileSync(
  path.resolve(__dirname, "../components/admin/AzureTrueUpCard.tsx"),
  "utf8",
);
const billing = fs.readFileSync(
  path.resolve(__dirname, "../app/admin/billing/page.tsx"),
  "utf8",
);
const quota = fs.readFileSync(
  path.resolve(__dirname, "../components/admin/EncounterQuotaCard.tsx"),
  "utf8",
);

test("billing page mounts the daily Azure check card", () => {
  expect(billing).toContain("AzureTrueUpCard");
  expect(trueUp).toContain("Azure is the whole shared account. Our number is this environment only.");
  expect(trueUp).toContain("/api/pricing/true-up");
  expect(trueUp).toContain("Our tokens");
  expect(trueUp).toContain("Azure tokens");
  expect(trueUp).toContain("Our cost");
  expect(trueUp).toContain("Azure bill");
});

test("billing page mounts the soft encounter limit card", () => {
  expect(billing).toContain("EncounterQuotaCard");
  expect(quota).toContain("over limit");
  expect(quota).toContain("/api/pricing/encounter-quotas");
});
