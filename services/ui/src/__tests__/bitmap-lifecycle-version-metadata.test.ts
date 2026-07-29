/**
 * VT-7C66F522 -- Compiled bitmap version metadata list.
 *
 * Atlas:
 *   DI: DI-3DDA3519
 *   DO: DO-15565AF5
 *   VT: VT-7C66F522
 */

import * as fs from "fs";
import * as path from "path";

import {
  formatVersionMeta,
  type VersionEntry,
} from "../app/admin/guidance/bitmapLifecycleHelpers";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, rel), "utf8");
}

describe("VT-7C66F522 - compiled bitmap version metadata list", () => {
  test("TC-001: loads compiled versions with metadata fields", () => {
    const hook = read(
      "services/ui/src/app/admin/guidance/useBitmapLifecycle.ts",
    );
    const helpers = read(
      "services/ui/src/app/admin/guidance/bitmapLifecycleHelpers.tsx",
    );
    expect(hook).toMatch(/\/api\/terminology\/guidelines\/compiled/);
    expect(hook).not.toMatch(
      /\/api\/terminology\/guidelines\/bitmap\/versions\?/,
    );
    expect(helpers).toMatch(/compile_timestamp\?:/);
    expect(helpers).toMatch(/rule_count\?:/);
    expect(helpers).toMatch(/policy_mode\?:/);
    expect(helpers).toMatch(/compile_stats\?:/);
  });

  test("TC-002: version row shows time, rule count, and policy mode", () => {
    const helpers = read(
      "services/ui/src/app/admin/guidance/bitmapLifecycleHelpers.tsx",
    );
    expect(helpers).toMatch(/formatVersionMeta/);
    expect(helpers).toMatch(/meta:\s*metaText/);
    const entry: VersionEntry = {
      version: "v20260729-081307",
      active: false,
      rule_count: 12,
      compile_timestamp: "2026-07-29T08:13:07.000Z",
      policy_mode: "advisory",
    };
    const meta = formatVersionMeta(entry);
    expect(meta).toMatch(/12 rules/);
    expect(meta).toMatch(/advisory/);
    expect(meta.length).toBeGreaterThan(10);
  });

  test("TC-003: compile_stats included/excluded/violations appear in meta", () => {
    const entry: VersionEntry = {
      version: "v1",
      active: true,
      rule_count: 4,
      compile_timestamp: "2026-07-29T08:13:07.000Z",
      policy_mode: "strict",
      compile_stats: {
        rules_included: 4,
        rules_excluded: 2,
        policy_violations: 1,
      },
    };
    const meta = formatVersionMeta(entry);
    expect(meta).toMatch(/included 4/);
    expect(meta).toMatch(/excluded 2/);
    expect(meta).toMatch(/violations 1/);
  });
});
