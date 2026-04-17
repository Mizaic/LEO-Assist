import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import EncounterTimelineScrubber from "@/components/mission-control/EncounterTimelineScrubber";

// VT-LEO-AI-173: live-render verification of the encounter timeline
// scrubber primitive (sticky histogram with zoom + per-bin popover).
// Source-level invariants (layoutId, useMotion import, file size,
// sticky positioning) are covered by EncounterTextTab-scrubber-chrome.

interface ScrubberEncounter {
  encounter_id: string;
  date: string;
  text: string | null;
  coded_count: number;
}

// Range = Jan 05 -> Aug 30 (238 days) so pickGranularity returns
// "month". enc-2 and enc-3 both fall in Feb 2024 so the Feb bin is
// multi-encounter; others are single-encounter bins.
const SIX_ENCOUNTERS: ScrubberEncounter[] = [
  { encounter_id: "enc-1", date: "2024-01-05", text: "Initial complaint",  coded_count: 1 },
  { encounter_id: "enc-2", date: "2024-02-10", text: "Routine review",     coded_count: 0 },
  { encounter_id: "enc-3", date: "2024-02-25", text: "Referral to clinic", coded_count: 3 },
  { encounter_id: "enc-4", date: "2024-04-04", text: "Specialist seen",    coded_count: 2 },
  { encounter_id: "enc-5", date: "2024-05-18", text: "Diagnosis recorded", coded_count: 5 },
  { encounter_id: "enc-6", date: "2024-08-30", text: "Follow up letter",   coded_count: 1 },
];

const FOUR_ENCOUNTERS: ScrubberEncounter[] = SIX_ENCOUNTERS.slice(0, 4);

const defaultProps = {
  encounters: SIX_ENCOUNTERS,
  linkedEncounterIds: new Set(["enc-3", "enc-4"]),
  episodeFrom: "2024-03-01",
  episodeTo: "2024-05-31",
  activeEncounterId: null as string | null,
  onJumpToEncounter: jest.fn(),
};

function renderScrubber(overrides: Partial<typeof defaultProps> = {}) {
  const props = { ...defaultProps, ...overrides };
  return render(<EncounterTimelineScrubber {...props} />);
}

function getBars(): HTMLElement[] {
  return screen
    .getAllByRole("button")
    .filter((node) => node.hasAttribute("data-bin-label"));
}

function findBarByLabel(label: string): HTMLElement {
  const bar = getBars().find((node) => node.getAttribute("data-bin-label") === label);
  if (!bar) throw new Error(`bar with label ${label} not found`);
  return bar;
}

describe("EncounterTimelineScrubber - VT-LEO-AI-173", () => {
  beforeEach(() => {
    defaultProps.onJumpToEncounter.mockReset();
  });

  test("VT-173-TC-001: renders the histogram when 5+ encounters present", () => {
    renderScrubber();
    expect(screen.getByTestId("encounter-timeline-scrubber")).toBeInTheDocument();
    expect(getBars().length).toBeGreaterThan(0);
  });

  test("VT-173-TC-002: renders nothing when fewer than 5 encounters", () => {
    const { container } = renderScrubber({ encounters: FOUR_ENCOUNTERS });
    expect(container.firstChild).toBeNull();
    expect(
      screen.queryByTestId("encounter-timeline-scrubber")
    ).not.toBeInTheDocument();
  });

  test("VT-173-TC-003: stacked-bar segments expose linked / other / total counts", () => {
    renderScrubber();
    const feb = findBarByLabel("Feb 24");
    expect(feb.getAttribute("data-total-count")).toBe("2");
    expect(feb.getAttribute("data-linked-count")).toBe("1");
    expect(feb.getAttribute("data-other-count")).toBe("1");
    expect(feb.querySelector('[data-segment="linked"]')).not.toBeNull();
    expect(feb.querySelector('[data-segment="other"]')).not.toBeNull();
    const apr = findBarByLabel("Apr 24");
    expect(apr.getAttribute("data-total-count")).toBe("1");
    expect(apr.getAttribute("data-linked-count")).toBe("1");
    expect(apr.getAttribute("data-other-count")).toBe("0");
    expect(apr.querySelector('[data-segment="other"]')).toBeNull();
  });

  test("VT-173-TC-004: episode window band rendered when both dates present", () => {
    renderScrubber();
    expect(screen.getByTestId("timeline-window-band")).toBeInTheDocument();
  });

  test("episode window band absent when no episode dates", () => {
    renderScrubber({ episodeFrom: null, episodeTo: null });
    expect(screen.queryByTestId("timeline-window-band")).not.toBeInTheDocument();
  });

  test("VT-173-TC-005: clicking a single-encounter bar jumps directly", () => {
    const onJump = jest.fn();
    renderScrubber({ onJumpToEncounter: onJump });
    fireEvent.click(findBarByLabel("Apr 24"));
    expect(onJump).toHaveBeenCalledWith("enc-4");
    expect(screen.queryByTestId("timeline-bin-popover")).not.toBeInTheDocument();
  });

  test("VT-173-TC-006: every bar with content has the prescribed aria-label", () => {
    renderScrubber();
    getBars()
      .filter((node) => Number(node.getAttribute("data-total-count")) > 0)
      .forEach((node) => {
        const label = node.getAttribute("aria-label") ?? "";
        expect(label).toMatch(
          /^Bin .+, \d+ encounters?( \(\d+ linked to focused episode\))?, from .+ to .+$/
        );
      });
  });

  test("VT-173-TC-007: pressing Enter on a focused single-encounter bar jumps", () => {
    const onJump = jest.fn();
    renderScrubber({ onJumpToEncounter: onJump });
    const may = findBarByLabel("May 24");
    may.focus();
    fireEvent.keyDown(may, { key: "Enter" });
    expect(onJump).toHaveBeenCalledWith("enc-5");
  });

  test("VT-173-TC-008: clicking a multi-encounter bar opens the popover", () => {
    const onJump = jest.fn();
    renderScrubber({ onJumpToEncounter: onJump });
    fireEvent.click(findBarByLabel("Feb 24"));
    const popover = screen.getByTestId("timeline-bin-popover");
    expect(popover).toBeInTheDocument();
    expect(popover.getAttribute("data-bin-label")).toBe("Feb 24");
    expect(onJump).not.toHaveBeenCalled();
    const rows = within(popover)
      .getAllByRole("button")
      .filter((node) => node.getAttribute("data-popover-row") === "true");
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.getAttribute("data-encounter-id")).sort()).toEqual([
      "enc-2",
      "enc-3",
    ]);
  });

  test("VT-173-TC-009: clicking a popover row jumps to that encounter", () => {
    const onJump = jest.fn();
    renderScrubber({ onJumpToEncounter: onJump });
    fireEvent.click(findBarByLabel("Feb 24"));
    const popover = screen.getByTestId("timeline-bin-popover");
    const enc3Row = within(popover)
      .getAllByRole("button")
      .find((node) => node.getAttribute("data-encounter-id") === "enc-3");
    expect(enc3Row).toBeDefined();
    fireEvent.click(enc3Row!);
    expect(onJump).toHaveBeenCalledWith("enc-3");
  });

  test("VT-173-TC-010: range brush exposes two role=slider handles with aria-value attributes", () => {
    renderScrubber();
    const brush = screen.getByTestId("timeline-range-brush");
    const handles = within(brush).getAllByRole("slider");
    expect(handles).toHaveLength(2);
    handles.forEach((handle) => {
      expect(handle).toHaveAttribute("aria-valuemin");
      expect(handle).toHaveAttribute("aria-valuemax");
      expect(handle).toHaveAttribute("aria-valuenow");
    });
    expect(handles[0].getAttribute("data-handle")).toBe("from");
    expect(handles[1].getAttribute("data-handle")).toBe("to");
  });

  test("VT-173-TC-011: reset zoom appears after zooming and restores the full range", () => {
    renderScrubber();
    expect(screen.queryByRole("button", { name: /reset zoom/i })).not.toBeInTheDocument();
    const brush = screen.getByTestId("timeline-range-brush");
    const fromHandle = within(brush)
      .getAllByRole("slider")
      .find((node) => node.getAttribute("data-handle") === "from");
    expect(fromHandle).toBeDefined();
    fromHandle!.focus();
    fireEvent.keyDown(fromHandle!, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(fromHandle!, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(fromHandle!, { key: "ArrowRight", shiftKey: true });
    const reset = screen.getByRole("button", { name: /reset zoom/i });
    expect(reset).toBeInTheDocument();
    fireEvent.click(reset);
    expect(screen.queryByRole("button", { name: /reset zoom/i })).not.toBeInTheDocument();
  });

  test("VT-173-TC-012: active bar carries data-active='true' and aria-pressed", () => {
    renderScrubber({ activeEncounterId: "enc-4" });
    const apr = findBarByLabel("Apr 24");
    expect(apr.getAttribute("data-active")).toBe("true");
    expect(apr.getAttribute("aria-pressed")).toBe("true");
    const may = findBarByLabel("May 24");
    expect(may.getAttribute("data-active")).toBe("false");
    expect(may.getAttribute("aria-pressed")).toBe("false");
  });

  test("scrubber root is sticky-positioned (position: sticky; top: 0)", () => {
    renderScrubber();
    const root = screen.getByTestId("encounter-timeline-scrubber");
    const style = window.getComputedStyle(root);
    expect(style.position).toBe("sticky");
    expect(style.top).toBe("0px");
  });

  test("VT-173-TC-013: histogram stays full-range when the focus window narrows", () => {
    renderScrubber();
    const fullBarCount = getBars().length;
    const fromHandle = within(screen.getByTestId("timeline-range-brush"))
      .getAllByRole("slider")
      .find((node) => node.getAttribute("data-handle") === "from")!;
    fromHandle.focus();
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });
    expect(getBars()).toHaveLength(fullBarCount);
    expect(findBarByLabel("Jan 24")).toBeInTheDocument();
    expect(findBarByLabel("Aug 24")).toBeInTheDocument();
  });

  test("VT-173-TC-014: a focus band is drawn on the histogram once zoomed", () => {
    renderScrubber();
    expect(screen.queryByTestId("timeline-focus-band")).not.toBeInTheDocument();
    const fromHandle = within(screen.getByTestId("timeline-range-brush"))
      .getAllByRole("slider")
      .find((node) => node.getAttribute("data-handle") === "from")!;
    fromHandle.focus();
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });
    expect(screen.getByTestId("timeline-focus-band")).toBeInTheDocument();
  });

  test("VT-173-TC-015: bars outside the focus window are marked data-in-focus='false'", () => {
    renderScrubber();
    getBars().forEach((bar) => {
      expect(bar.getAttribute("data-in-focus")).toBe("true");
    });
    const toHandle = within(screen.getByTestId("timeline-range-brush"))
      .getAllByRole("slider")
      .find((node) => node.getAttribute("data-handle") === "to")!;
    toHandle.focus();
    for (let i = 0; i < 12; i += 1) {
      fireEvent.keyDown(toHandle, { key: "ArrowLeft", shiftKey: true });
    }
    const bars = getBars();
    const inFocus = bars.filter((b) => b.getAttribute("data-in-focus") === "true");
    const outOfFocus = bars.filter((b) => b.getAttribute("data-in-focus") === "false");
    expect(inFocus.length).toBeGreaterThan(0);
    expect(outOfFocus.length).toBeGreaterThan(0);
  });

  test("VT-173-TC-016: focus band element is keyboard-pannable via Arrow keys", () => {
    renderScrubber();
    const brush = screen.getByTestId("timeline-range-brush");
    const fromHandle = within(brush)
      .getAllByRole("slider")
      .find((node) => node.getAttribute("data-handle") === "from")!;
    const toHandle = within(brush)
      .getAllByRole("slider")
      .find((node) => node.getAttribute("data-handle") === "to")!;
    fromHandle.focus();
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });
    toHandle.focus();
    fireEvent.keyDown(toHandle, { key: "ArrowLeft", shiftKey: true });
    fireEvent.keyDown(toHandle, { key: "ArrowLeft", shiftKey: true });
    const band = screen.getByTestId("timeline-range-band");
    const labelBeforePan = band.getAttribute("aria-label") ?? "";
    const fromBefore = Number(fromHandle.getAttribute("aria-valuenow"));
    const toBefore = Number(toHandle.getAttribute("aria-valuenow"));
    band.focus();
    fireEvent.keyDown(band, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(band, { key: "ArrowRight", shiftKey: true });
    const fromAfter = Number(fromHandle.getAttribute("aria-valuenow"));
    const toAfter = Number(toHandle.getAttribute("aria-valuenow"));
    expect(fromAfter).toBeGreaterThan(fromBefore);
    expect(toAfter).toBeGreaterThan(toBefore);
    expect(toAfter - fromAfter).toBeCloseTo(toBefore - fromBefore, -3);
    expect(band.getAttribute("aria-label") ?? "").not.toBe(labelBeforePan);
  });
});
