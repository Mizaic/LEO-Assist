/**
 * VT-35051473 -- Rule edit draft save and resume (static chrome).
 *
 * Atlas: DI-D52E923B / DO-BED08F09 / VT-35051473
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../../../../../..");

function readRel(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

describe("VT-35051473 - rule edit draft chrome", () => {
  test("TC-001: dialog wires Save progress and resume banner", () => {
    const src = readRel(
      "services/ui/src/app/admin/guidance/EditRuleDialog/index.tsx",
    );
    expect(src).toMatch(/DI-D52E923B/);
    expect(src).toMatch(/DraftResumeBanner/);
    expect(src).toMatch(/useRuleEditDraft/);
    expect(src).toMatch(/DRAFT_PROGRESS_COPY\.saveProgressLabel/);
    expect(src).toMatch(/ConfirmDialog/);
    expect(src).toMatch(/beforeunload/);
  });

  test("TC-002: draft API targets Neo4j draft routes", () => {
    const src = readRel(
      "services/ui/src/app/admin/guidance/EditRuleDialog/ruleEditDraftApi.ts",
    );
    expect(src).toMatch(/\/api\/guidance\/rules\/review\/.*\/draft/);
    expect(src).toMatch(/method:\s*"PUT"/);
    expect(src).toMatch(/method:\s*"DELETE"/);
  });

  test("TC-003: copy distinguishes progress save from final Save", () => {
    const src = readRel(
      "services/ui/src/app/admin/guidance/EditRuleDialog/copy.ts",
    );
    expect(src).toMatch(/Save progress/);
    expect(src).toMatch(/does not update the live rule/);
  });

  test("TC-004: backend draft service uses RuleEditDraft DRAFT_OF link", () => {
    const src = readRel("services/api/app/services/guidance_rule_draft.py");
    expect(src).toMatch(/RuleEditDraft/);
    expect(src).toMatch(/DRAFT_OF/);
    expect(src).toMatch(/_UPSERT_DRAFT/);
    const upsert = src.match(/_UPSERT_DRAFT = """([\s\S]*?)"""/)?.[1] ?? "";
    expect(upsert).toMatch(/MERGE \(draft\)-\[:DRAFT_OF\]->\(rule\)/);
    expect(upsert).not.toMatch(/SUPERSEDES/);
    expect(upsert).not.toMatch(/status:\s*'active'/);
  });
});
