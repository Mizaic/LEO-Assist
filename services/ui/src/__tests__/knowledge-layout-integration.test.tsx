/**
 * VT-LEO-AI-133 TC-004 - Knowledge page uses KnowledgePageLayout.
 * Source-level inspection keeps the test fast and avoids the heavy
 * dynamic imports inside KnowledgePage.
 */

import fs from "fs";
import path from "path";

const UI_ROOT = path.resolve(__dirname, "..", "..");

function readSource(rel: string): string {
  return fs.readFileSync(path.join(UI_ROOT, rel), "utf-8");
}

describe("VT-133 TC-004 - KnowledgePageLayout integration", () => {
  const src = readSource("src/app/admin/knowledge/page.tsx");

  it("imports KnowledgePageLayout from @leo/design-system", () => {
    expect(src).toMatch(/KnowledgePageLayout.*@leo\/design-system/);
  });

  it("uses KnowledgePageLayout in the render tree", () => {
    expect(src).toContain("<KnowledgePageLayout");
  });

  it("passes the session role into the layout", () => {
    expect(src).toContain("role={role}");
  });

  it("supplies KNOWLEDGE_TAB_COPY[activeKey] as the intro prop", () => {
    expect(src).toContain("intro={KNOWLEDGE_TAB_COPY[activeKey]}");
  });
});
