/**
 * VT for DI-85C95E53 acceptance criterion 3 (jsdom slice):
 *   "A host JS attempting to query or mutate widget-internal DOM
 *    (closed shadow root in the web-component variant; cross-origin
 *    frame in the iframe variant) is rejected by browser sandboxing."
 *
 * Atlas trace:
 *   DI: DI-85C95E53
 *   Risk mitigated: R-4965BCD2
 *
 * jsdom enforces closed shadow roots: element.shadowRoot is null
 * after attachShadow({mode:"closed"}). The iframe-variant half of
 * AC3 is verified at the browser level by Playwright (e2e/).
 *
 * Also verifies AC4 partial: switching variants does not change the
 * embed contract (the public attributes / event names stay the same;
 * the iframe variant uses the same param names via URL).
 */

import {
  LeoSbarElement,
  registerLeoSbarElement,
  _readShadowRootForTesting,
  _renderForTesting,
} from "../component";
import { LEO_EVENT_NAMES, type SbarAssessmentPayload } from "../data/types";

const PAYLOAD: SbarAssessmentPayload = {
  assessmentId: "ass-002",
  tenantId: "tenant-a",
  generatedAt: "2026-04-20T15:00:00Z",
  markdown: "## Situation\nX.\n## Background\nY.\n## Assessment\nZ.\n## Recommendation\nW.\n",
  backgroundParts: [
    {
      index: 1,
      total: 1,
      recordCount: 1,
      recordRange: [1, 1],
      sourceIds: ["enc-A"],
      status: "completed",
    },
  ],
};

describe("VT-DI-85C95E53-AC3 closed shadow root rejects host introspection", () => {
  beforeAll(() => {
    registerLeoSbarElement();
  });

  test("TC-1: <leo-sbar>.shadowRoot is null from outside (closed mode)", () => {
    const el = document.createElement("leo-sbar") as LeoSbarElement;
    el.setAttribute("assessment-id", "ass-002");
    el.setAttribute("widget-token", "test-token");
    document.body.appendChild(el);
    expect((el as unknown as { shadowRoot: ShadowRoot | null }).shadowRoot)
      .toBeNull();
  });

  test("TC-2: rendered disclosure is unreachable from document.querySelector", () => {
    const el = document.createElement("leo-sbar") as LeoSbarElement;
    el.setAttribute("assessment-id", PAYLOAD.assessmentId);
    el.setAttribute("widget-token", "test-token");
    document.body.appendChild(el);
    _renderForTesting(el, PAYLOAD);
    expect(
      document.querySelector('[data-testid="leo-disclosure-background"]'),
    ).toBeNull();
    const internalShadow = _readShadowRootForTesting(el);
    expect(internalShadow).toBeDefined();
    expect(
      internalShadow!.querySelector(
        '[data-testid="leo-disclosure-background"]',
      ),
    ).not.toBeNull();
  });

  test("TC-3: registerLeoSbarElement is idempotent", () => {
    registerLeoSbarElement();
    registerLeoSbarElement();
    expect(customElements.get("leo-sbar")).toBe(LeoSbarElement);
  });

  test("TC-4: lifecycle event names match the public LEO_EVENT_NAMES contract", () => {
    expect(LEO_EVENT_NAMES.loaded).toBe("leo:loaded");
    expect(LEO_EVENT_NAMES.error).toBe("leo:error");
    expect(LEO_EVENT_NAMES.disclosureOpened).toBe("leo:disclosure-opened");
    expect(LEO_EVENT_NAMES.disclosureClosed).toBe("leo:disclosure-closed");
    expect(LEO_EVENT_NAMES.sourceClicked).toBe("leo:source-clicked");
  });

  test("TC-5: leo:loaded fires after a successful render", () => {
    const el = document.createElement("leo-sbar") as LeoSbarElement;
    el.setAttribute("assessment-id", PAYLOAD.assessmentId);
    el.setAttribute("widget-token", "test-token");
    document.body.appendChild(el);
    let loadedDetail: { assessmentId?: string } | null = null;
    el.addEventListener("leo:loaded", ((e: Event) => {
      loadedDetail = (e as CustomEvent).detail as { assessmentId?: string };
    }) as EventListener);
    _renderForTesting(el, PAYLOAD);
    expect(loadedDetail).not.toBeNull();
    expect(loadedDetail!.assessmentId).toBe(PAYLOAD.assessmentId);
  });
});
