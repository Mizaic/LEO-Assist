/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Tests for ViewModeToggle + useViewMode: the Guided/Simple/Advanced
 * segmented control that persists a reviewer's canvas preference in
 * localStorage across rules.
 */
import { act } from "react";
import { fireEvent, render, renderHook, screen } from "@testing-library/react";

import ViewModeToggle, { useViewMode } from "../ViewModeToggle";

const STORAGE_KEY = "leo.editRuleDialog.viewMode";

beforeEach(() => {
  window.localStorage.clear();
});

describe("ViewModeToggle", () => {
  it("renders Guided, Simple, and Advanced tabs with a describing aria-label", () => {
    render(<ViewModeToggle value="advanced" onChange={() => {}} />);
    expect(
      screen.getByRole("tablist", {
        name: /switch between the guided wizard, the simple sentence view, and the advanced tree view/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Guided" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Simple" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Advanced" })).toBeInTheDocument();
  });

  it("calls onChange with the tapped tab's id", () => {
    const onChange = jest.fn();
    render(<ViewModeToggle value="advanced" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Simple" }));
    expect(onChange).toHaveBeenCalledWith("simple");
  });

  it("marks the current value's tab as selected", () => {
    render(<ViewModeToggle value="simple" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Simple" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Advanced" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Guided" })).toHaveAttribute("aria-selected", "false");
  });
});

describe("useViewMode", () => {
  it("defaults to 'guided' with no stored preference", () => {
    const { result } = renderHook(() => useViewMode());
    expect(result.current[0]).toBe("guided");
  });

  it("picks up a previously stored preference on mount", () => {
    window.localStorage.setItem(STORAGE_KEY, "simple");
    const { result } = renderHook(() => useViewMode());
    expect(result.current[0]).toBe("simple");
  });

  it("ignores a corrupt/unexpected stored value and falls back to the default", () => {
    window.localStorage.setItem(STORAGE_KEY, "not-a-real-mode");
    const { result } = renderHook(() => useViewMode());
    expect(result.current[0]).toBe("guided");
  });

  it("persists a new choice to localStorage and updates state", () => {
    const { result } = renderHook(() => useViewMode());
    act(() => {
      result.current[1]("simple");
    });
    expect(result.current[0]).toBe("simple");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("simple");
  });

  it("survives localStorage.setItem throwing (private browsing / quota)", () => {
    const spy = jest
      .spyOn(window.localStorage.__proto__, "setItem")
      .mockImplementation(() => {
        throw new Error("quota exceeded");
      });
    const { result } = renderHook(() => useViewMode());
    expect(() => {
      act(() => {
        result.current[1]("simple");
      });
    }).not.toThrow();
    expect(result.current[0]).toBe("simple");
    spy.mockRestore();
  });
});
