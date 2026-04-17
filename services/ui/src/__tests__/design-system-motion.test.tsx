/**
 * VT-LEO-AI-127: MotionProvider reduced-motion gate.
 * Covers TC-001 (default state) and TC-002 (reduced-motion state).
 */

import { act, render } from "@testing-library/react";
import React from "react";

import { MotionProvider, useMotion } from "@leo/design-system/motion";

function Probe({ onResolve }: { onResolve: (m: ReturnType<typeof useMotion>) => void }) {
  const m = useMotion();
  React.useEffect(() => {
    onResolve(m);
  }, [m, onResolve]);
  return null;
}

function installMatchMedia(matches: boolean): void {
  const listeners = new Set<(ev: MediaQueryListEvent) => void>();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (_query: string) => ({
      matches,
      media: _query,
      onchange: null,
      addListener: (l: (ev: MediaQueryListEvent) => void) => listeners.add(l),
      removeListener: (l: (ev: MediaQueryListEvent) => void) =>
        listeners.delete(l),
      addEventListener: (
        _type: string,
        l: (ev: MediaQueryListEvent) => void,
      ) => listeners.add(l),
      removeEventListener: (
        _type: string,
        l: (ev: MediaQueryListEvent) => void,
      ) => listeners.delete(l),
      dispatchEvent: () => true,
    }),
  });
}

describe("VT-127 - MotionProvider reduced-motion gate", () => {
  test("TC-001 default motion state", async () => {
    installMatchMedia(false);
    let resolved: ReturnType<typeof useMotion> | null = null;
    await act(async () => {
      render(
        <MotionProvider>
          <Probe onResolve={(m) => (resolved = m)} />
        </MotionProvider>,
      );
    });
    expect(resolved).not.toBeNull();
    expect(resolved!.reducedMotion).toBe(false);
    expect(resolved!.transitions.default.duration).toBe(180);
    expect(resolved!.transitions.route.type).toBe("spring");
  });

  test("TC-002 reduced-motion state collapses transitions", async () => {
    installMatchMedia(true);
    let resolved: ReturnType<typeof useMotion> | null = null;
    await act(async () => {
      render(
        <MotionProvider>
          <Probe onResolve={(m) => (resolved = m)} />
        </MotionProvider>,
      );
    });
    expect(resolved).not.toBeNull();
    expect(resolved!.reducedMotion).toBe(true);
    expect(resolved!.transitions.default.duration).toBe(0);
    expect(resolved!.transitions.route.duration).toBe(0);
    expect(resolved!.transitions.hover.duration).toBe(0);
  });
});
