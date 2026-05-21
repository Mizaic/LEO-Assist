/**
 * VT-A41C2468 - Completeness panel renders and emits events correctly.
 *
 * Atlas trace:
 *   DI: DI-235AEEC9 - Emit leo:completeness-incomplete when fields are missing
 *   DI: DI-B883B2BE - Render completeness findings in the widget
 *   DO: DO-A3465F94
 */

import type { SbarAssessmentPayload } from "../data/types";
import { LEO_EVENT_NAMES } from "../data/types";
import type { SurfaceEvent } from "../sbar/surface";
import { renderSurface } from "../sbar/surface";

function _makePayload(
  overrides: Partial<SbarAssessmentPayload>,
): SbarAssessmentPayload {
  return {
    assessmentId: "ASSESS-COMP-1",
    tenantId: "tenant-A",
    generatedAt: "2026-05-01T10:00:00Z",
    markdown: "## situation\nPatient referred.\n\n## recommendation\nReview.\n",
    backgroundParts: [],
    ...overrides,
  };
}

function _mount(payload: SbarAssessmentPayload): {
  mount: HTMLDivElement;
  events: SurfaceEvent[];
  teardown: () => void;
} {
  const events: SurfaceEvent[] = [];
  const mount = document.createElement("div");
  document.body.appendChild(mount);
  const teardown = renderSurface(mount, {
    payload,
    emit: (e) => events.push(e),
  });
  return { mount, events, teardown };
}

describe("completeness panel - DI-235AEEC9 / DI-B883B2BE", () => {
  test("TC-1: renders present, missing and unclear fields with distinct CSS classes", () => {
    const payload = _makePayload({
      completenessFinding: {
        requiredFields: ["Diagnosis", "Urgency", "Weight", "GP name"],
        presentFields: ["Diagnosis"],
        missingFields: ["Urgency", "Weight"],
        unclearFields: ["GP name"],
      },
    });

    const { mount } = _mount(payload);

    const panel = mount.querySelector('[data-testid="leo-completeness"]');
    expect(panel).not.toBeNull();

    const present = mount.querySelectorAll('[data-testid="leo-field-present"]');
    expect(present).toHaveLength(1);
    expect(present[0].textContent).toBe("Diagnosis");

    const missing = mount.querySelectorAll('[data-testid="leo-field-missing"]');
    expect(missing).toHaveLength(2);
    const missingTexts = Array.from(missing).map((el) => el.textContent);
    expect(missingTexts).toContain("Urgency");
    expect(missingTexts).toContain("Weight");

    const unclear = mount.querySelectorAll('[data-testid="leo-field-unclear"]');
    expect(unclear).toHaveLength(1);
    expect(unclear[0].textContent).toBe("GP name");
  });

  test("TC-2: leo:completeness-incomplete fires before leo:loaded when fields are missing", () => {
    const payload = _makePayload({
      completenessFinding: {
        requiredFields: ["Diagnosis", "Urgency"],
        presentFields: ["Diagnosis"],
        missingFields: ["Urgency"],
        unclearFields: [],
      },
    });

    const { events } = _mount(payload);

    const types = events.map((e) => e.type);
    const incompleteIdx = types.indexOf(LEO_EVENT_NAMES.completenessIncomplete);
    const loadedIdx = types.indexOf(LEO_EVENT_NAMES.loaded);

    expect(incompleteIdx).toBeGreaterThanOrEqual(0);
    expect(loadedIdx).toBeGreaterThanOrEqual(0);
    expect(incompleteIdx).toBeLessThan(loadedIdx);
  });

  test("TC-3: leo:completeness-incomplete detail includes missingFields and unclearFields", () => {
    const payload = _makePayload({
      completenessFinding: {
        requiredFields: ["Urgency", "Weight"],
        presentFields: [],
        missingFields: ["Urgency"],
        unclearFields: ["Weight"],
      },
    });

    const { events } = _mount(payload);

    const incomplete = events.find(
      (e) => e.type === LEO_EVENT_NAMES.completenessIncomplete,
    );
    expect(incomplete).toBeDefined();
    expect(incomplete!.detail.missingFields).toEqual(["Urgency"]);
    expect(incomplete!.detail.unclearFields).toEqual(["Weight"]);
  });

  test("TC-4: no completeness events when all fields are present", () => {
    const payload = _makePayload({
      completenessFinding: {
        requiredFields: ["Diagnosis"],
        presentFields: ["Diagnosis"],
        missingFields: [],
        unclearFields: [],
      },
    });

    const { events } = _mount(payload);

    expect(
      events.find((e) => e.type === LEO_EVENT_NAMES.completenessIncomplete),
    ).toBeUndefined();
    expect(
      events.find((e) => e.type === LEO_EVENT_NAMES.completenessUnavailable),
    ).toBeUndefined();
  });
});

describe("completeness unavailable - DI-235AEEC9", () => {
  test("TC-5: leo:completeness-unavailable fires when completenessFinding is null", () => {
    const payload = _makePayload({ completenessFinding: null });
    const { events } = _mount(payload);

    const unavailable = events.find(
      (e) => e.type === LEO_EVENT_NAMES.completenessUnavailable,
    );
    expect(unavailable).toBeDefined();
    expect(unavailable!.detail.assessmentId).toBe("ASSESS-COMP-1");
  });

  test("TC-6: leo:completeness-unavailable fires when completenessFinding is undefined", () => {
    const payload = _makePayload({});
    const { events } = _mount(payload);

    const unavailable = events.find(
      (e) => e.type === LEO_EVENT_NAMES.completenessUnavailable,
    );
    expect(unavailable).toBeDefined();
  });

  test("TC-7: no completeness panel is rendered when completenessFinding is null", () => {
    const payload = _makePayload({ completenessFinding: null });
    const { mount } = _mount(payload);

    const panel = mount.querySelector('[data-testid="leo-completeness"]');
    expect(panel).toBeNull();
  });
});
