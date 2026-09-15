/**
 * Already-done Assessment rules sit in a collapsed disclosure.
 *
 * Atlas trace:
 *   DI: DI-B3B44F09
 *   DI: DI-613A48DA
 */

import { renderSurface } from "../sbar/surface";
import { renderMarkdownToHtml } from "../sbar/markdown";
import type { SbarAssessmentPayload } from "../data/types";

const PAYLOAD: SbarAssessmentPayload = {
  assessmentId: "ass-already-done",
  tenantId: "tenant-a",
  generatedAt: "2026-09-15T12:00:00Z",
  markdown:
    "# SBAR\n## Situation\nReferred.\n## Background\nPelvic pain.\n" +
    "## Assessment\n**Supported by receiving service?** yes.\n\n" +
    "**Primary matches**\n- **1.5.14**\n\n" +
    "### Already done (1)\n- **Rule: 1.5.2**\n" +
    "  - **Action:** ~~Ultrasound scan of abdomen and pelvis~~ (already done)\n" +
    "## Recommendation\nReview in clinic.\n",
  backgroundParts: [],
};

describe("Already done Assessment disclosure", () => {
  test("TC-1: Assessment already-done block is collapsed by default", () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    renderSurface(mount, { payload: PAYLOAD, emit: () => {} });

    const wrapper = mount.querySelector<HTMLElement>(
      '[data-testid="leo-disclosure-assessment-already-done"]',
    );
    expect(wrapper).not.toBeNull();
    expect(wrapper?.getAttribute("data-open")).toBe("false");

    const toggle = mount.querySelector<HTMLButtonElement>(
      '[data-testid="leo-disclosure-assessment-already-done-toggle"]',
    );
    expect(toggle).not.toBeNull();
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(toggle?.textContent).toBe("Already done (1)");
    const panel = wrapper?.querySelector<HTMLElement>(".leo-disclosure-panel");
    expect(panel?.hidden).toBe(true);
  });

  test("TC-2: opening the disclosure shows the completed rule", () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    renderSurface(mount, { payload: PAYLOAD, emit: () => {} });
    mount
      .querySelector<HTMLButtonElement>(
        '[data-testid="leo-disclosure-assessment-already-done-toggle"]',
      )!
      .click();
    const wrapper = mount.querySelector<HTMLElement>(
      '[data-testid="leo-disclosure-assessment-already-done"]',
    );
    expect(wrapper?.getAttribute("data-open")).toBe("true");
    expect(mount.textContent).toContain("Rule: 1.5.2");
  });

  test("TC-3: strikethrough markdown renders as del", () => {
    const html = renderMarkdownToHtml(
      "~~Ultrasound scan of abdomen and pelvis~~ (already done)",
    );
    expect(html).toContain("<del>");
    expect(html).toContain("Ultrasound scan of abdomen and pelvis");
  });
});
