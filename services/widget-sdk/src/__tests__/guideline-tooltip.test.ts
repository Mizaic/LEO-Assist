/**
 * VT-56F64205 - Guideline matches render with verbatim text disclosure.
 *
 * Atlas trace:
 *   DI: DI-87FC76AC - Render matched guideline recommendations with verbatim text
 *   DO: DO-A3465F94
 */

import type { GuidelineMatch, SbarAssessmentPayload } from "../data/types";
import { renderSurface } from "../sbar/surface";

function _makePayload(
  matches: GuidelineMatch[],
): SbarAssessmentPayload {
  return {
    assessmentId: "ASSESS-GL-1",
    tenantId: "tenant-A",
    generatedAt: "2026-05-01T10:00:00Z",
    markdown: "## situation\nPatient referred.\n\n## recommendation\nReview.\n",
    backgroundParts: [],
    guidelineMatches: matches,
  };
}

function _mount(payload: SbarAssessmentPayload): HTMLDivElement {
  const mount = document.createElement("div");
  document.body.appendChild(mount);
  renderSurface(mount, { payload, emit: () => {} });
  return mount;
}

describe("guideline matches section - DI-87FC76AC", () => {
  test("TC-1: renders the Matched guidelines section when matches are provided", () => {
    const mount = _mount(
      _makePayload([
        {
          ruleId: "rule:NG12:v1:R001",
          name: "Chest X-ray within 2 weeks",
          strength: "offer",
          guidelineId: "NG12",
          recommendationVerbatim:
            "Offer an urgent chest X-ray within 2 weeks.",
        },
      ]),
    );

    const section = mount.querySelector('[data-testid="leo-guideline-matches"]');
    expect(section).not.toBeNull();

    const items = mount.querySelectorAll('[data-testid="leo-guideline-match"]');
    expect(items).toHaveLength(1);
  });

  test("TC-2: renders <details> disclosure with verbatim text for matches that have it", () => {
    const mount = _mount(
      _makePayload([
        {
          ruleId: "rule:NG12:v1:R001",
          name: "Chest X-ray",
          strength: "offer",
          guidelineId: "NG12",
          recommendationVerbatim: "Offer an urgent chest X-ray within 2 weeks.",
        },
      ]),
    );

    const details = mount.querySelector('[data-testid="leo-verbatim-details"]');
    expect(details).not.toBeNull();
    expect(details!.tagName.toLowerCase()).toBe("details");
    expect(details!.textContent).toContain("Offer an urgent chest X-ray");
  });

  test("TC-3: does not render <details> when recommendationVerbatim is null", () => {
    const mount = _mount(
      _makePayload([
        {
          ruleId: "rule:NG12:v1:R002",
          name: "Refer to colorectal cancer pathway",
          strength: "refer",
          guidelineId: "NG12",
          recommendationVerbatim: null,
        },
      ]),
    );

    const items = mount.querySelectorAll('[data-testid="leo-guideline-match"]');
    expect(items).toHaveLength(1);

    const details = mount.querySelector('[data-testid="leo-verbatim-details"]');
    expect(details).toBeNull();
  });

  test("TC-4: renders multiple matches, selectively showing verbatim details", () => {
    const mount = _mount(
      _makePayload([
        {
          ruleId: "rule:NG12:v1:R001",
          name: "Chest X-ray",
          strength: "offer",
          guidelineId: "NG12",
          recommendationVerbatim: "Offer an urgent chest X-ray.",
        },
        {
          ruleId: "rule:NG12:v1:R002",
          name: "Colorectal referral",
          strength: "refer",
          guidelineId: "NG12",
          recommendationVerbatim: null,
        },
      ]),
    );

    const items = mount.querySelectorAll('[data-testid="leo-guideline-match"]');
    expect(items).toHaveLength(2);

    const allDetails = mount.querySelectorAll(
      '[data-testid="leo-verbatim-details"]',
    );
    expect(allDetails).toHaveLength(1);
  });

  test("TC-5: does not render the Matched guidelines section when matches array is empty", () => {
    const mount = _mount(_makePayload([]));

    const section = mount.querySelector('[data-testid="leo-guideline-matches"]');
    expect(section).toBeNull();
  });

  test("TC-6: does not render the section when guidelineMatches is undefined", () => {
    const payload: SbarAssessmentPayload = {
      assessmentId: "ASSESS-GL-2",
      tenantId: "tenant-A",
      generatedAt: "2026-05-01T10:00:00Z",
      markdown: "## situation\nN/A\n",
      backgroundParts: [],
    };
    const mount = _mount(payload);

    const section = mount.querySelector('[data-testid="leo-guideline-matches"]');
    expect(section).toBeNull();
  });

  test("TC-7: escapes HTML special characters in rule name and verbatim text", () => {
    const mount = _mount(
      _makePayload([
        {
          ruleId: "rule:NG12:v1:R003",
          name: 'Rule with <script> & "quotes"',
          strength: "offer",
          guidelineId: "NG12",
          recommendationVerbatim: "Text with <b>bold</b> & special chars.",
        },
      ]),
    );

    const item = mount.querySelector('[data-testid="leo-guideline-match"]');
    expect(item).not.toBeNull();
    expect(item!.innerHTML).not.toContain("<script>");
    expect(item!.innerHTML).toContain("&lt;script&gt;");
    expect(item!.innerHTML).toContain("&lt;b&gt;");
  });
});
