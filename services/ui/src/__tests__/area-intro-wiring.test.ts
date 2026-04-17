/**
 * VT-LEO-AI-135 TC-004 - AreaIntro wired into every target page.
 *
 * Source-level assertion that each landing page imports AreaIntro and
 * mounts it with the correct area key.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..");

const CASES: Array<{ file: string; area: string }> = [
  { file: "app/dashboard/page.tsx", area: "care-overview" },
  { file: "app/admin/console/page.tsx", area: "operations" },
  { file: "app/admin/pathway-explorer/page.tsx", area: "pathway-explorer" },
  { file: "app/admin/platform/page.tsx", area: "platform" },
  { file: "app/admin/users/page.tsx", area: "users" },
  { file: "app/admin/portal/page.tsx", area: "portal" },
  { file: "app/admin/support/page.tsx", area: "support" },
  { file: "app/settings/page.tsx", area: "settings" },
  { file: "app/work/page.tsx", area: "work" },
];

describe("AreaIntro wiring across landing pages (VT-LEO-AI-135 TC-004)", () => {
  for (const c of CASES) {
    test(`${c.file} mounts <AreaIntro area="${c.area}"/>`, () => {
      const fullPath = path.join(ROOT, c.file);
      const src = fs.readFileSync(fullPath, "utf8");
      expect(src).toMatch(/import\s+AreaIntro/);
      const pattern = new RegExp(
        'AreaIntro\\s+area=\\"' + c.area + '\\"',
      );
      expect(src).toMatch(pattern);
    });
  }
});
