/**
 * VTs for DI-85944331:
 *   VT-011DF831 - tokens locked at single source                (AC1)
 *   VT-623578BE - widget reacts to prefers-color-scheme         (AC2)
 *   VT-AD41127B - widget exposes no brand-mutation API          (AC3)
 *
 * Atlas trace:
 *   DO: DO-7F469209
 *   DI: DI-85944331
 *   Risk mitigated: R-4965BCD2 (no host-controllable surface
 *     can be used to obscure the source-record disclosure)
 */

import { BRAND, MIZAIC_MARK_SVG, STAGE_THEME } from "../branding/tokens";
import { buildShadowStylesheet } from "../branding/stylesheet";
import { LeoSbarElement } from "../component";

const FORBIDDEN = /color|font|typo|palette|disclosure|theme/i;

// ---------------------------------------------------------------------------
// VT-011DF831 - AC1 tokens locked at single source
// ---------------------------------------------------------------------------

describe("VT-011DF831 - tokens are the single source of brand truth", () => {
  test("BRAND exposes the expected shape", () => {
    expect(BRAND.productName).toBe("LEO by Mizaic");
    expect(BRAND.fontFamily).toContain("Albert Sans");
    expect(BRAND.fontFamilyHeading).toContain("Overpass");
    expect(BRAND.light.primary).toBe("#0d46d6");
    expect(BRAND.light.markInk).toBe("#00093b");
    expect(BRAND.light.background).toBe("#ffffff");
    expect(BRAND.dark.background).toBe("#0f172a");
  });

  test("chrome tokens do not use the retired generic blues", () => {
    const css = buildShadowStylesheet();
    expect(css).not.toMatch(/#1F3A8A|#1E40AF|#1D4ED8|#0F766E/i);
    expect(BRAND.light.primary).not.toMatch(/#1e3a8a/i);
  });

  test("STAGE_THEME covers all four SBAR stages", () => {
    expect(Object.keys(STAGE_THEME).sort()).toEqual([
      "assessment",
      "background",
      "recommendation",
      "situation",
    ]);
  });

  test("MIZAIC_MARK_SVG is an inline SVG bound into the bundle", () => {
    expect(MIZAIC_MARK_SVG).toMatch(/^<svg/);
    expect(MIZAIC_MARK_SVG).toContain("LEO by Mizaic");
    expect(MIZAIC_MARK_SVG).toContain("#d758ff");
    expect(MIZAIC_MARK_SVG).toContain("currentColor");
  });

  test("BRAND is frozen at runtime - host cannot mutate the palette", () => {
    expect(Object.isFrozen(BRAND)).toBe(true);
    expect(Object.isFrozen(BRAND.light)).toBe(true);
    expect(Object.isFrozen(BRAND.dark)).toBe(true);
    expect(() => {
      (BRAND.light as { primary: string }).primary = "magenta";
    }).toThrow(TypeError);
  });

  test("STAGE_THEME is frozen at runtime", () => {
    expect(Object.isFrozen(STAGE_THEME)).toBe(true);
    expect(Object.isFrozen(STAGE_THEME.situation)).toBe(true);
    expect(() => {
      (STAGE_THEME.situation as { accent: string }).accent = "magenta";
    }).toThrow(TypeError);
  });
});

// ---------------------------------------------------------------------------
// VT-623578BE - AC2 widget reacts to prefers-color-scheme
// ---------------------------------------------------------------------------

describe("VT-623578BE - stylesheet supports reactive light / dark", () => {
  test("emits a prefers-color-scheme: dark @media block", () => {
    const css = buildShadowStylesheet();
    expect(css).toContain("@media (prefers-color-scheme: dark)");
  });

  test("dark block carries colour values that differ from the light defaults", () => {
    const css = buildShadowStylesheet();
    expect(BRAND.light.background).not.toBe(BRAND.dark.background);
    expect(BRAND.light.text).not.toBe(BRAND.dark.text);
    expect(css).toContain(BRAND.light.background);
    expect(css).toContain(BRAND.dark.background);
    expect(css).toContain(BRAND.light.text);
    expect(css).toContain(BRAND.dark.text);
  });
});

// ---------------------------------------------------------------------------
// VT-AD41127B - AC3 widget exposes no brand-mutation API
// ---------------------------------------------------------------------------

describe("VT-AD41127B - widget exposes no brand-mutation API", () => {
  test("observedAttributes contains no forbidden attribute name", () => {
    const observed = (LeoSbarElement as unknown as {
      observedAttributes?: readonly string[];
    }).observedAttributes ?? [];
    for (const attr of observed) {
      expect(FORBIDDEN.test(attr)).toBe(false);
    }
  });

  test("LeoSbarElement.prototype has no own property whose name reveals branding", () => {
    const proto = LeoSbarElement.prototype as unknown as object;
    const own = Object.getOwnPropertyNames(proto);
    for (const name of own) {
      // setAttribute / attributeChangedCallback are inherited; we
      // only enforce on names defined on this class.
      expect(FORBIDDEN.test(name)).toBe(false);
    }
  });

  test("Setting a forbidden CSS custom property does not change rendered styling", () => {
    if (typeof customElements.get("leo-sbar") === "undefined") {
      const { registerLeoSbarElement } = require("../component");
      registerLeoSbarElement();
    }
    const el = document.createElement("leo-sbar");
    el.setAttribute("style", "--leo-brand-color: magenta; --leo-font: Comic;");
    document.body.appendChild(el);
    const computed = getComputedStyle(el);
    expect(computed.getPropertyValue("color")).not.toContain("magenta");
    document.body.removeChild(el);
  });
});
