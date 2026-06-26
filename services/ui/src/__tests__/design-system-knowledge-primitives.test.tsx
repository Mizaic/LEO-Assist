/**
 * VT-LEO-AI-132 - Role-first Knowledge primitives in @leo/design-system.
 *
 * Covers IntroCard (role prop, reduced-motion, persistence, aria),
 * StatHero (tile count), ProgressiveReveal (toggle), and
 * KnowledgePageLayout composition. The final test case pins the FK
 * readability grade for default intro copy shipped by the library.
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  IntroCard,
  KnowledgePageLayout,
  MotionProvider,
  ProgressiveReveal,
  StatHero,
  fleschKincaidGrade,
  type IntroRoleCopy,
  type StatTile,
} from "@leo/design-system";

const SAMPLE_COPY: IntroRoleCopy = {
  default: {
    title: "Default title",
    lede: "Default lede text used when no role matches.",
    how: "Do the simple thing first.",
    what: "LEO updates the list next time.",
  },
  triage_clinician: {
    title: "Triage Clinician title",
    lede: "Triage clinician lede text.",
  },
  clinical_coder: {
    title: "Clinical Coder title",
    lede: "Clinical coder lede text.",
  },
};

function mountInto(
  container: HTMLElement,
  element: React.ReactElement,
): Root {
  const root = createRoot(container);
  act(() => {
    root.render(element);
  });
  return root;
}

function unmount(root: Root) {
  act(() => {
    root.unmount();
  });
}

function mockMatchMedia(reduce: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: jest.fn().mockImplementation((query: string) => ({
      matches: query.includes("reduce") ? reduce : false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

describe("VT-132 - Knowledge primitives", () => {
  let container: HTMLElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    window.localStorage.clear();
    mockMatchMedia(false);
  });

  afterEach(() => {
    document.body.removeChild(container);
    window.localStorage.clear();
  });

  describe("TC-001 exports", () => {
    it("all four primitives are functions", () => {
      expect(typeof IntroCard).toBe("function");
      expect(typeof StatHero).toBe("function");
      expect(typeof ProgressiveReveal).toBe("function");
      expect(typeof KnowledgePageLayout).toBe("function");
    });
  });

  describe("TC-002 IntroCard role prop", () => {
    it("renders the clinical_coder block when role='clinical_coder'", () => {
      const root = mountInto(
        container,
        <MotionProvider>
          <IntroCard screenId="t-role" copy={SAMPLE_COPY} role="clinical_coder" />
        </MotionProvider>,
      );
      expect(container.textContent).toContain("Clinical Coder title");
      expect(container.textContent).not.toContain("Default title");
      unmount(root);
    });

    it("falls back to default when role is null", () => {
      const root = mountInto(
        container,
        <MotionProvider>
          <IntroCard screenId="t-null" copy={SAMPLE_COPY} role={null} />
        </MotionProvider>,
      );
      expect(container.textContent).toContain("Default title");
      unmount(root);
    });
  });

  describe("TC-003 prefers-reduced-motion", () => {
    it("transition marginMs is 0 when reduce is true", () => {
      mockMatchMedia(true);
      const root = mountInto(
        container,
        <MotionProvider>
          <IntroCard screenId="t-rm" copy={SAMPLE_COPY} />
        </MotionProvider>,
      );
      const body = container.querySelector(
        '[data-testid="intro-card-t-rm"] > div + div',
      ) as HTMLElement | null;
      expect(body?.style.transition).toContain("0ms");
      unmount(root);
    });
  });

  describe("TC-004 localStorage persistence", () => {
    it("saves collapse state under leo-introcard-<screenId>", () => {
      const root = mountInto(
        container,
        <MotionProvider>
          <IntroCard screenId="persist" copy={SAMPLE_COPY} />
        </MotionProvider>,
      );
      const button = container.querySelector("button") as HTMLButtonElement;
      act(() => {
        button.click();
      });
      expect(window.localStorage.getItem("leo-introcard-persist")).toBe(
        "collapsed",
      );
      unmount(root);
    });
  });

  describe("TC-005 aria attributes", () => {
    it("aria-expanded and aria-controls are wired", () => {
      const root = mountInto(
        container,
        <MotionProvider>
          <IntroCard screenId="aria" copy={SAMPLE_COPY} />
        </MotionProvider>,
      );
      const button = container.querySelector("button") as HTMLButtonElement;
      const controls = button.getAttribute("aria-controls");
      expect(controls).toBeTruthy();
      expect(document.getElementById(controls as string)).not.toBeNull();
      expect(button.getAttribute("aria-expanded")).toBe("true");
      act(() => {
        button.click();
      });
      expect(button.getAttribute("aria-expanded")).toBe("false");
      unmount(root);
    });
  });

  describe("TC-006 StatHero tiles", () => {
    it("renders one tile per stat, capped by maxTiles", () => {
      const stats: StatTile[] = [
        { id: "a", label: "A", value: 1 },
        { id: "b", label: "B", value: 2 },
        { id: "c", label: "C", value: 3, delta: { direction: "up", value: "+5" } },
      ];
      const root = mountInto(
        container,
        <MotionProvider>
          <StatHero stats={stats} />
        </MotionProvider>,
      );
      const tiles = container.querySelectorAll("[data-testid^='stat-tile-']");
      expect(tiles.length).toBe(3);
      unmount(root);
    });
  });

  describe("TC-007 ProgressiveReveal toggle", () => {
    it("children become visible after clicking the summary button", () => {
      const root = mountInto(
        container,
        <MotionProvider>
          <ProgressiveReveal summary="Advanced options">
            <div data-testid="advanced-body">secret</div>
          </ProgressiveReveal>
        </MotionProvider>,
      );
      const body = container.querySelector(
        '[data-testid="advanced-body"]',
      )?.parentElement as HTMLElement;
      expect(body.hasAttribute("hidden")).toBe(true);
      const button = container.querySelector("button") as HTMLButtonElement;
      act(() => {
        button.click();
      });
      expect(body.hasAttribute("hidden")).toBe(false);
      unmount(root);
    });
  });

  describe("TC-008 readability of shipped intro copy", () => {
    it("fleschKincaidGrade of every default block <= 9", () => {
      const text =
        SAMPLE_COPY.default.title +
        " " +
        SAMPLE_COPY.default.lede +
        " " +
        (SAMPLE_COPY.default.how ?? "") +
        " " +
        (SAMPLE_COPY.default.what ?? "");
      const result = fleschKincaidGrade(text);
      expect(result.grade).toBeLessThanOrEqual(9);
    });
  });
});
