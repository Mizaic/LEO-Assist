/**
 * VT-LEO-AI-114 - Density provider tests.
 *
 * Extended for VT-LEO-AI-168 (Wave E Phase 1): the provider now also
 * consumes the practitioner's saved server preference via useAuth, so
 * the auth module is mocked to control that input.
 */

import React from "react";
import { act, render, waitFor } from "@testing-library/react";
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

let mockSession: {
  user: { email?: string; name?: string };
  densityPreference: "compact" | "comfortable" | "spacious" | null;
} | null = null;
const mockRefetch = jest.fn(async () => {});

jest.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    session: mockSession,
    status: mockSession ? "authenticated" : "unauthenticated",
    signIn: jest.fn(),
    signOut: jest.fn(),
    refetch: mockRefetch,
  }),
}));

beforeEach(() => {
  mockSession = null;
  mockRefetch.mockClear();
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ density_preference: "compact" }),
    }),
  ) as unknown as jest.Mock;
});

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

  test("TC-006 server preference wins over localStorage on staff routes", () => {
    expect(
      resolveInitialDensity("/admin/console", "compact", "spacious"),
    ).toBe("spacious");
  });

  test("TC-007 server preference is overridden on patient-reachable routes", () => {
    expect(resolveInitialDensity("/portal", null, "compact")).toBe("spacious");
  });

  test("TC-008 setDensity PATCHes /auth/session/density when authenticated", async () => {
    currentPathname = "/dashboard";
    mockSession = {
      user: { email: "user@example.com" },
      densityPreference: "comfortable",
    };
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
    await act(async () => {
      captured!.setDensity("compact");
    });
    const fetchMock = global.fetch as jest.Mock;
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/auth/session/density",
        expect.objectContaining({ method: "PATCH" }),
      );
    });
    await waitFor(() => {
      expect(mockRefetch).toHaveBeenCalled();
    });
  });

  test("TC-009 setDensity does NOT call API when unauthenticated", async () => {
    currentPathname = "/dashboard";
    mockSession = null;
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
    await act(async () => {
      captured!.setDensity("compact");
    });
    expect(global.fetch).not.toHaveBeenCalled();
    expect(window.localStorage.getItem("leo-density")).toBe("compact");
  });
});
