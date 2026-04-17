/**
 * VT-LEO-AI-114 - Density provider tests.
 */

import React from "react";
import { act, render } from "@testing-library/react";
import {
  DensityProvider,
  resolveInitialDensity,
  useDensity,
} from "@/context/DensityContext";
import { DENSITY_MAP } from "@/theme/tokens";

let currentPathname = "/dashboard";

jest.mock("next/navigation", () => ({
  usePathname: () => currentPathname,
}));

function Probe({ onValue }: { onValue: (value: ReturnType<typeof useDensity>) => void }) {
  const value = useDensity();
  React.useEffect(() => {
    onValue(value);
  }, [onValue, value]);
  return null;
}

describe("VT-LEO-AI-114 density", () => {
  beforeEach(() => {
    currentPathname = "/dashboard";
    window.localStorage.clear();
  });

  test("TC-001 no storage, staff route: default is comfortable", () => {
    currentPathname = "/dashboard";
    expect(resolveInitialDensity("/dashboard", null)).toBe("comfortable");
  });

  test("TC-002 patient route forces spacious even when storage=compact", () => {
    expect(resolveInitialDensity("/portal", "compact")).toBe("spacious");
    expect(resolveInitialDensity("/safety-netting/abc", "compact")).toBe("spacious");
  });

  test("TC-003 DENSITY_MAP.spacious guarantees 44px touch target", () => {
    expect(DENSITY_MAP.spacious.minHeightPx).toBeGreaterThanOrEqual(44);
  });

  test("TC-004 setDensity persists to localStorage", () => {
    currentPathname = "/dashboard";
    let captured: ReturnType<typeof useDensity> | null = null;
    render(
      <DensityProvider>
        <Probe
          onValue={(value) => {
            captured = value;
          }}
        />
      </DensityProvider>,
    );
    act(() => {
      captured!.setDensity("compact");
    });
    expect(window.localStorage.getItem("leo-density")).toBe("compact");
  });

  test("TC-005 localStorage value used on non-patient route", () => {
    expect(resolveInitialDensity("/admin/console", "spacious")).toBe("spacious");
    expect(resolveInitialDensity("/admin/console", null)).toBe("comfortable");
  });
});
