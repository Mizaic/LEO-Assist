/**
 * VT-1BB20B2A -- SBAR PDF download acceptance verification.
 *
 * Static-source verification:
 *   - LeoSbarHost exposes Download PDF wired to assessment fetch + exportSbarPdf
 *   - export captures widget-faithful HTML (cards, markdown, advisory)
 *   - Failure path keeps leo-sbar mounted
 *
 * Design Controls: DI-B03BD651, DO-BEE23936, VT-1BB20B2A, UN-1D7BF4A8.
 */

import * as fs from "fs";
import * as path from "path";
import {
  composeSbarMarkdownFromAssessment,
  markdownBodyToHtml,
  planPdfPageSlices,
  SBAR_PDF_ADVISORY,
  SBAR_PDF_IG_FOOTER,
} from "@/lib/exportSbarPdf";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const HOST = "services/ui/src/components/sbar-final/LeoSbarHost.tsx";
const PDF_EXPORT = "services/ui/src/lib/exportSbarPdf.ts";
const PDF_MARKUP = "services/ui/src/lib/sbarPdfMarkup.ts";

describe("VT-1BB20B2A - SBAR PDF download chrome", () => {
  test("TC-001: LeoSbarHost exposes a Download PDF control", () => {
    const src = readFile(HOST);
    expect(src).toContain('data-testid="leo-sbar-download-pdf"');
    expect(src).toContain("Download PDF");
    expect(src).toContain('aria-label="Download SBAR as PDF"');
  });

  test("TC-002: Download PDF loads assessment and saves via exportSbarPdf", () => {
    const src = readFile(HOST);
    expect(src).toContain('from "@/lib/exportSbarPdf"');
    expect(src).toContain("composeSbarMarkdownFromAssessment");
    expect(src).toContain("await exportSbarPdf");
    expect(src).toMatch(
      /\/api\/sbar\/assessments\/\$\{encodeURIComponent\(assessmentId\)\}/,
    );
    const pdfSrc = readFile(PDF_EXPORT);
    expect(pdfSrc).toContain('from "html2canvas"');
    expect(pdfSrc).toContain("buildSbarPdfCaptureRoot");
    expect(pdfSrc).toContain("doc.save");
    expect(pdfSrc).toMatch(/sbar-\$\{idSlug\}-\$\{dateSlug\}\.pdf/);
  });

  test("TC-003: PDF includes the mandatory AI advisory text", () => {
    const markup = readFile(PDF_MARKUP);
    expect(markup).toContain("SBAR_PDF_ADVISORY");
    expect(markup).toContain("leo-advisory");
    expect(SBAR_PDF_ADVISORY).toContain(
      "AI-generated summary. Clinician review required before acting on this",
    );
    expect(SBAR_PDF_ADVISORY).toContain("decision support aid");
  });

  test("TC-004: PDF lists SBAR sections in canonical widget card order", () => {
    const markup = readFile(PDF_MARKUP);
    expect(markup).toContain("splitFinalSbar");
    expect(markup).toContain("leo-stage");
    expect(markup).toContain("text-transform: uppercase");
    expect(markup).toContain("STAGE_THEME");

    const md = composeSbarMarkdownFromAssessment({
      situation: "Sit",
      background: "Bg",
      assessment: "Ass",
      recommendation: "Rec",
    });
    expect(md.indexOf("## Situation")).toBeLessThan(md.indexOf("## Background"));
    expect(md.indexOf("## Background")).toBeLessThan(md.indexOf("## Assessment"));
    expect(md.indexOf("## Assessment")).toBeLessThan(
      md.indexOf("## Recommendation"),
    );
  });

  test("TC-005: Each PDF page includes the information governance footer", () => {
    const pdfSrc = readFile(PDF_EXPORT);
    expect(pdfSrc).toContain("SBAR_PDF_IG_FOOTER");
    expect(pdfSrc).toContain("drawFooter");
    expect(SBAR_PDF_IG_FOOTER).toContain("information governance policy");
    expect(pdfSrc).toContain("planPdfPageSlices");
    expect(pdfSrc).toContain("collectPdfBlocks");
    expect(pdfSrc).toContain("drawFooter(doc, index + 1, totalPages)");
  });

  test("TC-008: page planner breaks between blocks instead of mid-card", () => {
    const markup = readFile(PDF_MARKUP);
    expect(markup).toContain('data-pdf-block="chrome"');
    expect(markup).toContain('data-pdf-block="stage"');

    // Chrome 80 + four stage cards 100 each; page holds 250 -> pack 2+2+1.
    const blocks = [
      { topPx: 0, bottomPx: 80 },
      { topPx: 90, bottomPx: 190 },
      { topPx: 200, bottomPx: 300 },
      { topPx: 310, bottomPx: 410 },
      { topPx: 420, bottomPx: 520 },
    ];
    const slices = planPdfPageSlices(blocks, 250, 530);
    expect(slices.length).toBeGreaterThan(1);
    // No slice should end inside a block except when the block itself is tall.
    for (const slice of slices) {
      const end = slice.topPx + slice.heightPx;
      const midCut = blocks.some(
        (b) => slice.topPx < b.bottomPx && end > b.topPx && end < b.bottomPx,
      );
      expect(midCut).toBe(false);
    }
    // First page should include chrome + first fitting stages only.
    expect(slices[0].topPx).toBe(0);
    expect(slices[0].heightPx).toBe(190);
  });

  test("TC-006: Download failure shows error and keeps leo-sbar mount path", () => {
    const src = readFile(HOST);
    expect(src).toContain('data-testid="leo-sbar-download-pdf-error"');
    expect(src).toContain('data-testid="leo-sbar-widget"');
    expect(src).toMatch(/!loading && token && \([\s\S]*?<leo-sbar/);
    expect(src).not.toMatch(/exportError[\s\S]*return null/);
  });

  test("TC-007: markdown body keeps bold and nested list structure", () => {
    const html = markdownBodyToHtml(
      [
        "**2 guideline rule(s) fired** (scope: global).",
        "",
        "### Routine",
        "",
        "- **Rule: 1.2.3** (_strength: consider_)",
        "  - **Recommendation:** for people with treatment resistant dyspepsia",
        "  - **Matched on:** indigestion",
      ].join("\n"),
    );
    expect(html).toContain("<strong>2 guideline rule(s) fired</strong>");
    expect(html).toContain('class="leo-md-h"');
    expect(html).toContain("Routine");
    expect(html).toContain("<strong>Recommendation:</strong>");
    expect(html).toContain("treatment resistant dyspepsia");
    expect(html).not.toMatch(/t r e a t m e n t/);
    expect(html).toContain('class="leo-md-list"');
  });
});
