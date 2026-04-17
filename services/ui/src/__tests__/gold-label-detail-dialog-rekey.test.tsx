/**
 * VT-LEO-AI-179 -- GoldLabelDetailDialog re-key + state resync.
 *
 * Static-source verification:
 *   - Every <GoldLabelDetailDialog ...> mount in GoldDatasetPanel.tsx
 *     passes a stable `key` prop derived from the item's label_id.
 *   - The dialog body declares a useEffect that resyncs its
 *     entity-derived state when item.label_id changes.
 *
 * The dialog body is a 3,000+ LOC implementation. The state-leak
 * regression that motivated this VT (a previous candidate's entities
 * rendering against the next candidate's sentence) was caused by
 * lazy useState(() => parseEntities(...)) initialisers that only run
 * on mount. The fix is two-layered:
 *   1. Caller passes `key={item.label_id}` so React unmounts the
 *      dialog when the item changes -- forcing the lazy initialisers
 *      to re-run.
 *   2. Belt-and-braces: a useEffect inside the dialog tracks the
 *      previous label_id via a ref and resyncs entities +
 *      rejectedRelationKeys + drafts when it changes, in case a
 *      future caller forgets the key prop.
 *
 * Design Controls: DI-LEO-AI-185, DO-LEO-AI-184, R-LEO-AI-179.
 */
import fs from "fs";
import path from "path";

const PANEL_PATH = path.resolve(
  __dirname,
  "..",
  "components",
  "gold-dataset",
  "GoldDatasetPanel.tsx"
);

describe("VT-LEO-AI-179 GoldLabelDetailDialog re-key + state resync", () => {
  let source: string;

  beforeAll(() => {
    source = fs.readFileSync(PANEL_PATH, "utf8");
  });

  it("TC-001: every GoldLabelDetailDialog JSX mount carries a key prop", () => {
    const mounts = source.match(/<GoldLabelDetailDialog[\s\S]*?\/>/g) ?? [];
    expect(mounts.length).toBeGreaterThanOrEqual(4);
    for (const mount of mounts) {
      expect(mount).toMatch(/\bkey\s*=\s*\{[^}]*label_id[^}]*\}/);
    }
  });

  it("TC-002: each key uses a distinct namespace prefix to avoid collisions across surfaces", () => {
    const mounts = source.match(/<GoldLabelDetailDialog[\s\S]*?\/>/g) ?? [];
    const keyValues = mounts
      .map((m) => m.match(/\bkey\s*=\s*\{`([^`]+)`/))
      .filter((x): x is RegExpMatchArray => x !== null)
      .map((m) => m[1].split("-")[0]);
    expect(keyValues).toEqual(expect.arrayContaining(["gold", "syn", "cand", "sim"]));
  });

  it("TC-003: dialog body declares a useEffect that resyncs on item.label_id change", () => {
    const dialogStart = source.indexOf("function GoldLabelDetailDialog");
    expect(dialogStart).toBeGreaterThan(0);
    const dialogBody = source.slice(dialogStart, dialogStart + 60_000);
    expect(dialogBody).toMatch(/useRef\s*\(\s*item\.label_id\s*\)/);
    expect(dialogBody).toMatch(
      /useEffect\s*\(\s*\(\)\s*=>\s*\{[\s\S]*?prevLabelIdRef\.current[\s\S]*?\},\s*\[\s*item\.label_id\s*,\s*item\.entities_json\s*\]\s*\)/
    );
  });

  it("TC-004: resync effect calls setEntities + setRejectedRelationKeys + clears suggestions/drafts", () => {
    const dialogStart = source.indexOf("function GoldLabelDetailDialog");
    const dialogBody = source.slice(dialogStart, dialogStart + 60_000);
    const effectMatch = dialogBody.match(
      /useEffect\s*\(\s*\(\)\s*=>\s*\{([\s\S]*?)\},\s*\[\s*item\.label_id\s*,\s*item\.entities_json\s*\]\s*\)/
    );
    expect(effectMatch).not.toBeNull();
    const body = effectMatch![1];
    expect(body).toMatch(/setEntities\s*\(/);
    expect(body).toMatch(/setRejectedRelationKeys\s*\(/);
    expect(body).toMatch(/setSuggestions\s*\(\s*\{\}\s*\)/);
    expect(body).toMatch(/setTermDrafts\s*\(\s*\{\}\s*\)/);
    expect(body).toMatch(/setLookupTarget\s*\(\s*null\s*\)/);
  });

  it("TC-005: entities lazy initialiser is preserved (mount-time fast path)", () => {
    expect(source).toMatch(
      /const\s+\[\s*entities\s*,\s*setEntities\s*\]\s*=\s*useState<Entity\[\]>\(\(\)\s*=>\s*parseEntities\(item\.entities_json\)\)/
    );
  });
});
