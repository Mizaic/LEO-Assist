/**
 * VT-FA40F4D3 -- Demo mode context persistence.
 *
 * Design Controls: DI-6FD9D8D1, DO-ACCEEF0C, VT-FA40F4D3.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  DEMO_MODE_STORAGE_KEY,
  DemoModeProvider,
  useDemoMode,
} from "@/context/DemoModeContext";

function Probe() {
  const { isDemoMode, setDemoMode } = useDemoMode();
  return (
    <button type="button" onClick={() => setDemoMode(!isDemoMode)}>
      {isDemoMode ? "on" : "off"}
    </button>
  );
}

describe("VT-FA40F4D3 demo mode context", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  test("TC-001: reads browser-local demo mode state on mount", async () => {
    window.localStorage.setItem(DEMO_MODE_STORAGE_KEY, "true");

    render(
      <DemoModeProvider>
        <Probe />
      </DemoModeProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "on" })).toBeInTheDocument();
    });
  });

  test("TC-002: toggling on stores the browser-local flag", async () => {
    const user = userEvent.setup();
    render(
      <DemoModeProvider>
        <Probe />
      </DemoModeProvider>,
    );

    await user.click(screen.getByRole("button", { name: "off" }));

    expect(window.localStorage.getItem(DEMO_MODE_STORAGE_KEY)).toBe("true");
  });

  test("TC-003: toggling off removes the browser-local flag", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DEMO_MODE_STORAGE_KEY, "true");
    render(
      <DemoModeProvider>
        <Probe />
      </DemoModeProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "on" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "on" }));

    expect(window.localStorage.getItem(DEMO_MODE_STORAGE_KEY)).toBeNull();
  });
});
