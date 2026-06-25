/**
 * VT-LEO-AI-149 -- Knowledge tab width parity + Domains/Terminology card
 * style consistency.
 *
 * Static-source verification:
 *   - All eight Knowledge tabs render at the wide (1600px) layout so
 *     content does not jump width when the user moves between tabs.
 *   - DomainCard and PackageCard share radius / padding / 3px accent
 *     strip / header layout so they look like the same card family.
 *   - Domains grid is capped at 3 columns (no lg:4) so cards remain
 *     readable on widescreen.
 *
 * Design Controls: DI-LEO-AI-151, DO-LEO-AI-147, VT-LEO-AI-149.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("VT-LEO-AI-149 - Knowledge tab width + card consistency", () => {
  test("TC-001: every Knowledge tab maps to layout width 'wide'", () => {
    const src = readFile("services/ui/src/app/admin/knowledge/page.tsx");
    const tabWidthBlock = src.match(
      /TAB_WIDTH:\s*Record<KnowledgeTabKey,\s*KnowledgeLayoutWidth>\s*=\s*\{[\s\S]*?\};/m,
    );
    expect(tabWidthBlock).not.toBeNull();
    const block = tabWidthBlock![0];
    const tabs = [
      "training-data",
      "surface-forms",
      "context-rules",
      "ai-instructions",
      "clinical-guidelines",
      "pathways",
      "domains",
      "terminology",
      "results-labs",
    ];
    for (const tab of tabs) {
      const re = new RegExp(`["']?${tab}["']?\\s*:\\s*"wide"`);
      expect(block).toMatch(re);
    }
  });

  test("TC-002: DomainCard uses 12px radius, 18px padding, 3px accent strip", () => {
    // DomainCard was extracted to _components/DomainCard.tsx in the Wave E split.
    const card = readFile(
      "services/ui/src/app/settings/domains/_components/DomainCard.tsx",
    );
    // Accept either numeric (12) or string ("12px") forms.
    expect(card).toMatch(/borderRadius[^;]*12/);
    expect(card).toMatch(/padding[^;]*18/);
    // The 3px left accent strip -- width of 3 and a background on same/next line.
    expect(card).toMatch(/width:\s*3[,\s]/);
  });

  test("TC-003: PackageCard uses 12px radius, 18px padding, 3px accent strip", () => {
    // PackageCard was extracted to settings/terminology/PackageCard.tsx in the Wave E split.
    const card = readFile(
      "services/ui/src/app/settings/terminology/PackageCard.tsx",
    );
    expect(card).toMatch(/borderRadius[^;]*12/);
    expect(card).toMatch(/[pP]adding[^;]*18/);
    expect(card).toMatch(/width:\s*3[,\s]/);
  });

  test("TC-004: Domains grid is capped at 3 columns (no lg:4)", () => {
    const src = readFile("services/ui/src/app/settings/domains/page.tsx");
    const grid = src.match(
      /gridTemplateColumns:\s*\{[\s\S]*?\}/m,
    );
    expect(grid).not.toBeNull();
    expect(grid![0]).not.toMatch(/lg:\s*"repeat\(4/);
    expect(grid![0]).toMatch(/md:\s*"repeat\(3/);
    expect(grid![0]).toMatch(/sm:\s*"repeat\(2/);
  });

  test("TC-005: Domains and Terminology card minHeight is aligned (>=160)", () => {
    // Read from the extracted card component files (Wave E split).
    const domains = readFile(
      "services/ui/src/app/settings/domains/_components/DomainCard.tsx",
    );
    const terminology = readFile(
      "services/ui/src/app/settings/terminology/PackageCard.tsx",
    );
    const domainsMin = domains.match(/minHeight:\s*(\d+)/);
    const termMin = terminology.match(/minHeight:\s*(\d+)/);
    expect(domainsMin).not.toBeNull();
    expect(termMin).not.toBeNull();
    expect(parseInt(domainsMin![1], 10)).toBeGreaterThanOrEqual(160);
    expect(parseInt(termMin![1], 10)).toBeGreaterThanOrEqual(160);
  });

  test("TC-006: DomainCard tone chips use the canonical knowledge palette", () => {
    // DomainCard was extracted to _components/DomainCard.tsx in the Wave E split.
    const src = readFile(
      "services/ui/src/app/settings/domains/_components/DomainCard.tsx",
    );
    expect(src).toMatch(/bgcolor:\s*"#DBEAFE"/);
    expect(src).toMatch(/bgcolor:\s*"#F1F5F9"/);
    expect(src).toMatch(/bgcolor:\s*"#ECFDF5"/);
  });
});
