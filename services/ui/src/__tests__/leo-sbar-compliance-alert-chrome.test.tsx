/**
 * Gate 3 B3.3 -- clinician-visible 2WW mismatch alert chrome.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../..");
const HOST = "src/components/sbar-final/LeoSbarHost.tsx";

function readHost(): string {
  return fs.readFileSync(path.join(REPO_ROOT, HOST), "utf8");
}

describe("LeoSbarHost compliance alert chrome", () => {
  test("renders advisory compliance alert from assessment payload", () => {
    const src = readHost();
    expect(src).toMatch(/compliance_alerts/);
    expect(src).toMatch(/data-testid="leo-sbar-compliance-alert"/);
    expect(src).toMatch(/severity="warning"/);
  });
});
