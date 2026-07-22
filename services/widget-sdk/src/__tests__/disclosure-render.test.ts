/**
 * VT for DI-85C95E53 acceptance criterion 1:
 *   "Both variants are publishable from the same source tree and
 *    produce byte-identical rendering of the source-record disclosure
 *    given the same assessment payload."
 *
 * Atlas trace:
 *   DI: DI-85C95E53
 *   Risk mitigated: R-4965BCD2
 *
 * Strategy: render the SBAR surface (which is the SHARED module both
 * variants import unchanged) into two different containers - one
 * inside a closed shadow root, one inside a plain document.body. The
 * disclosure markup is sliced out of each and compared byte-for-byte.
 */

import type { SbarAssessmentPayload } from "../data/types";
import { formatSourceLabel } from "../sbar/disclosure";
import { renderSurface, type RenderSurfaceOptions } from "../sbar/surface";

const PAYLOAD: SbarAssessmentPayload = {
  assessmentId: "ass-001",
  tenantId: "tenant-a",
  generatedAt: "2026-04-20T15:00:00Z",
  markdown:
    "# SBAR\n## Situation\nPatient referred for 2WW lower GI.\n" +
    "## Background\nIron-deficiency anaemia 6 weeks.\n" +
    "## Assessment\nIDA likely cause: occult GI bleed.\n" +
    "## Recommendation\nUrgent colonoscopy within 2 weeks.\n",
  backgroundParts: [
    {
      index: 1,
      total: 2,
      recordCount: 3,
      recordRange: [1, 3],
      sourceIds: ["enc-001", "enc-002", "enc-003"],
      status: "completed",
    },
    {
      index: 2,
      total: 2,
      recordCount: 2,
      recordRange: [4, 5],
      sourceIds: ["enc-004", "enc-005"],
      status: "completed",
    },
  ],
};

function _disclosureMarkup(root: ParentNode): string {
  const node = (root as Element).querySelector(
    '[data-testid="leo-disclosure-background"]',
  );
  return node ? node.outerHTML : "";
}

describe("VT-DI-85C95E53-AC1 disclosure renders identically across variants", () => {
  test("TC-1: shadow-root variant disclosure equals iframe-shell variant disclosure (byte-identical)", () => {
    const shadowHost = document.createElement("div");
    document.body.appendChild(shadowHost);
    const shadow = shadowHost.attachShadow({ mode: "open" });
    renderSurface(shadow, { payload: PAYLOAD, emit: () => {} });

    const iframeMount = document.createElement("div");
    document.body.appendChild(iframeMount);
    renderSurface(iframeMount, { payload: PAYLOAD, emit: () => {} });

    const shadowDisclosure = _disclosureMarkup(shadow);
    const iframeDisclosure = _disclosureMarkup(iframeMount);

    expect(shadowDisclosure.length).toBeGreaterThan(0);
    expect(iframeDisclosure.length).toBeGreaterThan(0);
    expect(shadowDisclosure).toBe(iframeDisclosure);
  });

  test("TC-2: disclosure includes every source ID from every part", () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    renderSurface(mount, { payload: PAYLOAD, emit: () => {} });
    const disclosure = mount.querySelector(
      '[data-testid="leo-disclosure-background"]',
    );
    expect(disclosure).not.toBeNull();
    const ids = ["enc-001", "enc-002", "enc-003", "enc-004", "enc-005"];
    for (const id of ids) {
      const chip = disclosure!.querySelector(
        `.leo-source-chip[data-source-id="${id}"]`,
      );
      expect(chip).not.toBeNull();
    }
  });

  test("TC-3: disclosure toggle switches data-open and emits events", () => {
    const events: Array<{ type: string; detail: unknown }> = [];
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    renderSurface(mount, {
      payload: PAYLOAD,
      emit: (e) => events.push({ type: e.type, detail: e.detail }),
    });
    const toggle = mount.querySelector<HTMLButtonElement>(
      '[data-testid="leo-disclosure-background-toggle"]',
    );
    expect(toggle).not.toBeNull();
    const wrapper = mount.querySelector<HTMLElement>(
      '[data-testid="leo-disclosure-background"]',
    );
    expect(wrapper?.getAttribute("data-open")).toBe("false");
    toggle!.click();
    expect(wrapper?.getAttribute("data-open")).toBe("true");
    expect(toggle!.getAttribute("aria-expanded")).toBe("true");
    const opened = events.find((e) => e.type === "leo:disclosure-opened");
    expect(opened).toBeDefined();
    toggle!.click();
    expect(wrapper?.getAttribute("data-open")).toBe("false");
    const closed = events.find((e) => e.type === "leo:disclosure-closed");
    expect(closed).toBeDefined();
  });

  test("TC-4: clicking a source chip emits leo:source-clicked with the source id", () => {
    const events: Array<{ type: string; detail: { sourceId?: string } }> = [];
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    renderSurface(mount, {
      payload: PAYLOAD,
      emit: (e) =>
        events.push({
          type: e.type,
          detail: e.detail as { sourceId?: string },
        }),
    });
    mount
      .querySelector<HTMLButtonElement>(
        '[data-testid="leo-disclosure-background-toggle"]',
      )!
      .click();
    const chip = mount.querySelector<HTMLButtonElement>(
      '.leo-source-chip[data-source-id="enc-003"]',
    );
    expect(chip).not.toBeNull();
    chip!.click();
    const event = events.find((e) => e.type === "leo:source-clicked");
    expect(event).toBeDefined();
    expect(event!.detail.sourceId).toBe("enc-003");
    expect(
      mount.querySelector('[data-testid="leo-source-dialog"]'),
    ).not.toBeNull();
  });

  test("TC-5: enriched sources show clinician-friendly labels", () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    const enriched: SbarAssessmentPayload = {
      ...PAYLOAD,
      backgroundParts: [
        {
          index: 1,
          total: 1,
          recordCount: 1,
          recordRange: [1, 1],
          sourceIds: ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
          sources: [
            {
              id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              type: "Chunk",
              label: "Letter chunk 1",
              preview: "Progressive jaundice.",
            },
          ],
          status: "completed",
        },
      ],
    };
    renderSurface(mount, { payload: enriched, emit: () => {} });
    mount
      .querySelector<HTMLButtonElement>(
        '[data-testid="leo-disclosure-background-toggle"]',
      )!
      .click();
    const chip = mount.querySelector<HTMLButtonElement>(
      '.leo-source-chip[data-source-id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]',
    );
    expect(chip?.textContent).toBe("Letter chunk 1");
    expect(formatSourceLabel("uuid:form:encounter")).toContain("encounter");
  });

  test("TC-6: source dialog shows the exact record text when fullText is present", () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    const withFullText: SbarAssessmentPayload = {
      ...PAYLOAD,
      backgroundParts: [
        {
          index: 1,
          total: 1,
          recordCount: 1,
          recordRange: [1, 1],
          sourceIds: ["chunk-full-1"],
          sources: [
            {
              id: "chunk-full-1",
              type: "Chunk",
              label: "Referral letter chunk 1",
              preview: "Dear Colleague,",
              fullText:
                "Dear Colleague,\n\nThank you for referring this patient with " +
                "iron-deficiency anaemia. Full letter text continues here.",
            },
          ],
          status: "completed",
        },
      ],
    };
    renderSurface(mount, { payload: withFullText, emit: () => {} });
    mount
      .querySelector<HTMLButtonElement>(
        '[data-testid="leo-disclosure-background-toggle"]',
      )!
      .click();
    mount
      .querySelector<HTMLButtonElement>(
        '.leo-source-chip[data-source-id="chunk-full-1"]',
      )!
      .click();
    const body = mount.querySelector('[data-testid="leo-source-dialog-body"]');
    expect(body?.textContent).toContain(
      "Thank you for referring this patient with iron-deficiency anaemia",
    );
    expect(
      mount.querySelector('[data-testid="leo-source-dialog-note"]')
        ?.textContent,
    ).toMatch(/exact record text/i);
  });

  test("TC-7: source dialog falls back to the short preview when fullText is absent", () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    renderSurface(mount, {
      payload: {
        ...PAYLOAD,
        backgroundParts: [
          {
            index: 1,
            total: 1,
            recordCount: 1,
            recordRange: [1, 1],
            sourceIds: ["enc-legacy"],
            sources: [
              {
                id: "enc-legacy",
                type: "Encounter",
                label: "Encounter (legacy)",
                preview: "Progressive jaundice.",
              },
            ],
            status: "completed",
          },
        ],
      },
      emit: () => {},
    });
    mount
      .querySelector<HTMLButtonElement>(
        '[data-testid="leo-disclosure-background-toggle"]',
      )!
      .click();
    mount
      .querySelector<HTMLButtonElement>(
        '.leo-source-chip[data-source-id="enc-legacy"]',
      )!
      .click();
    expect(
      mount.querySelector('[data-testid="leo-source-dialog-body"]')
        ?.textContent,
    ).toBe("Progressive jaundice.");
    expect(
      mount.querySelector('[data-testid="leo-source-dialog-note"]')
        ?.textContent,
    ).toMatch(/short preview only/i);
  });

  function _renderLegacySource(
    mount: HTMLElement,
    resolveSourceText: RenderSurfaceOptions["resolveSourceText"],
  ): void {
    renderSurface(mount, {
      payload: {
        ...PAYLOAD,
        backgroundParts: [
          {
            index: 1,
            total: 1,
            recordCount: 1,
            recordRange: [1, 1],
            sourceIds: ["chunk-live-1"],
            sources: [
              {
                id: "chunk-live-1",
                type: "Chunk",
                label: "Referral letter chunk 1",
                preview: "Dear Colleague,",
              },
            ],
            status: "completed",
          },
        ],
      },
      emit: () => {},
      resolveSourceText,
    });
    mount
      .querySelector<HTMLButtonElement>(
        '[data-testid="leo-disclosure-background-toggle"]',
      )!
      .click();
    mount
      .querySelector<HTMLButtonElement>(
        '.leo-source-chip[data-source-id="chunk-live-1"]',
      )!
      .click();
  }

  test("TC-8: dialog upgrades in place with live text when resolveSourceText succeeds", async () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    let resolveLive: (text: string) => void = () => {};
    _renderLegacySource(
      mount,
      () =>
        new Promise<string>((resolve) => {
          resolveLive = resolve;
        }),
    );

    expect(
      mount.querySelector('[data-testid="leo-source-dialog-note"]')
        ?.textContent,
    ).toMatch(/looking up/i);

    resolveLive("Dear Colleague,\n\nFull letter text resolved live.");
    await Promise.resolve();
    await Promise.resolve();

    expect(
      mount.querySelector('[data-testid="leo-source-dialog-body"]')
        ?.textContent,
    ).toBe("Dear Colleague,\n\nFull letter text resolved live.");
    expect(
      mount.querySelector('[data-testid="leo-source-dialog-note"]')
        ?.textContent,
    ).toMatch(/retrieved from the patient record/i);
  });

  test("TC-9: dialog keeps the preview fallback when resolveSourceText rejects", async () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    _renderLegacySource(mount, () => Promise.reject(new Error("network down")));

    await Promise.resolve();
    await Promise.resolve();

    expect(
      mount.querySelector('[data-testid="leo-source-dialog-body"]')
        ?.textContent,
    ).toBe("Dear Colleague,");
    expect(
      mount.querySelector('[data-testid="leo-source-dialog-note"]')
        ?.textContent,
    ).toMatch(/short preview only/i);
  });

  test("TC-10: closing the dialog before resolveSourceText resolves does not throw or reopen it", async () => {
    const mount = document.createElement("div");
    document.body.appendChild(mount);
    let resolveLive: (text: string) => void = () => {};
    _renderLegacySource(
      mount,
      () =>
        new Promise<string>((resolve) => {
          resolveLive = resolve;
        }),
    );
    mount
      .querySelector<HTMLButtonElement>(".leo-source-dialog-close")!
      .click();
    expect(mount.querySelector('[data-testid="leo-source-dialog"]')).toBeNull();

    resolveLive("Late text that must not reappear.");
    await Promise.resolve();
    await Promise.resolve();

    expect(mount.querySelector('[data-testid="leo-source-dialog"]')).toBeNull();
  });
});
