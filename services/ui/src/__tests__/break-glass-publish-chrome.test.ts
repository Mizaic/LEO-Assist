/**
 * VT-1215D85D / DI-B00BD595 -- emergency override chrome.
 */
import { readFileSync } from "fs";
import { join } from "path";

const ROOT = join(__dirname, "..");

function read(rel: string): string {
  return readFileSync(join(ROOT, rel), "utf8");
}

describe("Emergency override chrome", () => {
  it("keeps a named reason field for platform admin authors only", () => {
    const helper = read("app/work/BreakGlassReason.tsx");
    const deploy = read("app/work/EngineerPanes.tsx");
    const dialog = read("app/work/PhrasePublishDialog.tsx");
    expect(helper).toContain("Why do you need this emergency override");
    expect(helper).toContain("REASON_MIN");
    expect(helper).toContain("REASON_MAX");
    expect(deploy).toContain("BreakGlassReason");
    expect(deploy).toContain("isPlatformAdmin");
    expect(dialog).toContain("BreakGlassReason");
    expect(dialog).toContain("isPlatformAdmin");
  });

  it("sends the reason on publish", () => {
    const api = read("app/settings/surface-forms/phraseMappingsApi.ts");
    const work = read("app/work/workFixApi.ts");
    expect(api).toContain("break_glass_reason");
    expect(work).toContain("deployWorkPhrase");
    expect(work).toMatch(/publishPhrase\(phrase,\s*reason\)/);
  });
});
