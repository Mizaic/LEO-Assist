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

interface RenderOverrides {
  encounters?: ScrubberEncounter[];
  linkedEncounterIds?: Set<string>;
  episodeFrom?: string | null;
  episodeTo?: string | null;
  milestones?: Array<{ milestone_type: string; encounter_id: string; date: string }>;
  activeEncounterId?: string | null;
  onJumpToEncounter?: jest.Mock;
  onVisibleRangeChange?: jest.Mock;
  searchMatchEncounterIds?: Set<string>;
}

const defaultProps = {
  encounters: SIX_ENCOUNTERS,
  linkedEncounterIds: new Set(["enc-3", "enc-4"]),
  episodeFrom: "2024-03-01" as string | null,
  episodeTo: "2024-05-31" as string | null,
  milestones: [
    { milestone_type: "gp_referral", encounter_id: "enc-3", date: "2024-02-25" },
    { milestone_type: "specialist_visit", encounter_id: "enc-4", date: "2024-04-04" },
  ],
  activeEncounterId: null as string | null,
  onJumpToEncounter: jest.fn(),
};

function renderScrubber(overrides: RenderOverrides = {}) {
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

  test("VT-173-TC-004: episode window band rendered when linked encounters present", () => {
    renderScrubber();
    expect(screen.getByTestId("timeline-window-band")).toBeInTheDocument();
  });

  test("episode window band absent when no linked encounters resolve", () => {
    renderScrubber({ linkedEncounterIds: new Set<string>() });
    expect(screen.queryByTestId("timeline-window-band")).not.toBeInTheDocument();
  });

  test("VT-205-TC-OVERLAY-A: per-encounter linked tick is drawn for each linked encounter", () => {
    renderScrubber();
    const ticks = screen.getAllByTestId("timeline-linked-tick");
    expect(ticks.length).toBe(2);
    const ids = ticks
      .map((node) => node.getAttribute("data-encounter-id"))
      .sort();
    expect(ids).toEqual(["enc-3", "enc-4"]);
  });

  test("VT-205-TC-OVERLAY-B: linked ticks are absent when no linked encounters", () => {
    renderScrubber({ linkedEncounterIds: new Set<string>() });
    expect(screen.queryAllByTestId("timeline-linked-tick").length).toBe(0);
  });

  test("VT-205-TC-OVERLAY-C: milestone markers render with accessible labels and jump on click", () => {
    const onJump = jest.fn();
    renderScrubber({ onJumpToEncounter: onJump });
    const markers = screen.getAllByTestId("timeline-milestone-marker");
    expect(markers.length).toBe(2);
    const referral = markers.find(
      (node) => node.getAttribute("data-milestone-type") === "gp_referral"
    );
    expect(referral).toBeDefined();
    expect(referral!.getAttribute("aria-label")).toMatch(/^Milestone: Referred on /);
    fireEvent.click(referral!);
    expect(onJump).toHaveBeenCalledWith("enc-3");
  });

  test("VT-205-TC-OVERLAY-D: milestone markers absent when no milestones provided", () => {
    renderScrubber({ milestones: [] });
    expect(screen.queryAllByTestId("timeline-milestone-marker").length).toBe(0);
  });

  test("VT-173-TC-005: clicking a single-encounter bar filters the list to that bin (DI-15E0094F)", () => {
    // Per DI-15E0094F the click-to-filter behaviour is uniform for
    // every bar: it never calls onJumpToEncounter, it never opens
    // a popover, it always sets the visible range to the bar's bin.
    const onJump = jest.fn();
    const onRange = jest.fn();
    renderScrubber({
      onJumpToEncounter: onJump,
      onVisibleRangeChange: onRange,
    });
    fireEvent.click(findBarByLabel("Apr 24"));
    expect(onJump).not.toHaveBeenCalled();
    expect(onRange).toHaveBeenCalledTimes(1);
    const [fromMs, toMs] = onRange.mock.calls[0] as [number, number];
    expect(typeof fromMs).toBe("number");
    expect(typeof toMs).toBe("number");
    expect(toMs).toBeGreaterThan(fromMs);
    // April 2024 falls inside the chosen window.
    const apr15 = Date.parse("2024-04-15T00:00:00.000Z");
    expect(apr15).toBeGreaterThanOrEqual(fromMs);
    expect(apr15).toBeLessThanOrEqual(toMs);
    expect(screen.queryByTestId("timeline-bin-popover")).not.toBeInTheDocument();
  });

  test("VT-173-TC-006: every bar with content has the prescribed aria-label", () => {
    renderScrubber();
    getBars()
      .filter((node) => Number(node.getAttribute("data-total-count")) > 0)
      .forEach((node) => {
        const label = node.getAttribute("aria-label") ?? "";
        // Coded suffix (", X of Y coded") is appended for bins with
        // codedCount > 0; permitted but optional. DI-8ECE2DAE.
        expect(label).toMatch(
          /^Bin .+, \d+ encounters?( \(\d+ linked to focused episode\))?(, \d+ of \d+ coded)?, from .+ to .+$/
        );
      });
  });

  test("VT-173-TC-007: pressing Enter on a focused bar filters to that bin (DI-15E0094F)", () => {
    const onJump = jest.fn();
    const onRange = jest.fn();
    renderScrubber({
      onJumpToEncounter: onJump,
      onVisibleRangeChange: onRange,
    });
    const may = findBarByLabel("May 24");
    may.focus();
    fireEvent.keyDown(may, { key: "Enter" });
    expect(onJump).not.toHaveBeenCalled();
    expect(onRange).toHaveBeenCalledTimes(1);
  });

  test("VT-173-TC-008: clicking a multi-encounter bar filters to that bin (no popover, DI-15E0094F)", () => {
    const onJump = jest.fn();
    const onRange = jest.fn();
    renderScrubber({
      onJumpToEncounter: onJump,
      onVisibleRangeChange: onRange,
    });
    fireEvent.click(findBarByLabel("Feb 24"));
    expect(screen.queryByTestId("timeline-bin-popover")).not.toBeInTheDocument();
    expect(onJump).not.toHaveBeenCalled();
    expect(onRange).toHaveBeenCalledTimes(1);
    const [fromMs, toMs] = onRange.mock.calls[0] as [number, number];
    const feb15 = Date.parse("2024-02-15T00:00:00.000Z");
    expect(feb15).toBeGreaterThanOrEqual(fromMs);
    expect(feb15).toBeLessThanOrEqual(toMs);
  });

  test("VT-173-TC-009: bar click in uncontrolled mode triggers internal zoom and Reset zoom appears", () => {
    // When the parent does not pass onVisibleRangeChange the
    // scrubber falls back to its internal zoom state, so the only
    // public-observable side-effect of the click is the appearance
    // of the Reset zoom button (TC-011 covers the full reset flow).
    const onJump = jest.fn();
    renderScrubber({ onJumpToEncounter: onJump });
    expect(
      screen.queryByRole("button", { name: /reset zoom/i })
    ).not.toBeInTheDocument();
    fireEvent.click(findBarByLabel("Feb 24"));
    expect(onJump).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: /reset zoom/i })
    ).toBeInTheDocument();
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

// VT-827AA57F: histogram search overlay + click-to-filter
// (Atlas DI-15E0094F, R-LEO-AI-174). Live-render coverage of the
// per-bin amber outline, the dimming of non-matching bins, and the
// click-to-filter contract (TC-005..TC-009 above already cover the
// click side; this block focuses on the search overlay).
describe("EncounterTimelineScrubber search overlay - VT-827AA57F", () => {
  test("VT-827AA57F-LIVE-001: with no search, bars carry data-search-active='false' and no match ring", () => {
    renderScrubber();
    getBars().forEach((bar) => {
      expect(bar.getAttribute("data-search-active")).toBe("false");
      expect(bar.getAttribute("data-search-match")).toBe("false");
    });
    expect(
      screen.queryAllByTestId("timeline-search-match-ring").length
    ).toBe(0);
  });

  test("VT-827AA57F-LIVE-002: matching bins outline amber, non-matching bins dim", () => {
    // enc-3 matches in Feb; enc-4 matches in Apr. All other bins
    // should be dimmed and carry data-search-match='false'.
    renderScrubber({
      searchMatchEncounterIds: new Set(["enc-3", "enc-4"]),
    });
    getBars().forEach((bar) => {
      expect(bar.getAttribute("data-search-active")).toBe("true");
    });
    const feb = findBarByLabel("Feb 24");
    const apr = findBarByLabel("Apr 24");
    const may = findBarByLabel("May 24");
    expect(feb.getAttribute("data-search-match")).toBe("true");
    expect(apr.getAttribute("data-search-match")).toBe("true");
    expect(may.getAttribute("data-search-match")).toBe("false");
    // Feb and Apr each get an amber ring rendered inside their
    // motion wrapper.
    expect(
      within(feb).getByTestId("timeline-search-match-ring")
    ).toBeInTheDocument();
    expect(
      within(apr).getByTestId("timeline-search-match-ring")
    ).toBeInTheDocument();
    expect(
      within(may).queryByTestId("timeline-search-match-ring")
    ).not.toBeInTheDocument();
  });

  test("VT-827AA57F-LIVE-003: zero-match search dims every bin and shows zero rings", () => {
    renderScrubber({ searchMatchEncounterIds: new Set<string>() });
    getBars().forEach((bar) => {
      expect(bar.getAttribute("data-search-active")).toBe("true");
      expect(bar.getAttribute("data-search-match")).toBe("false");
    });
    expect(
      screen.queryAllByTestId("timeline-search-match-ring").length
    ).toBe(0);
  });

  test("VT-827AA57F-LIVE-004: per-bin match count is exposed for assistive tech and tests", () => {
    renderScrubber({
      searchMatchEncounterIds: new Set(["enc-2", "enc-3", "enc-5"]),
    });
    expect(findBarByLabel("Feb 24").getAttribute("data-search-match-count")).toBe("2");
    expect(findBarByLabel("May 24").getAttribute("data-search-match-count")).toBe("1");
    expect(findBarByLabel("Apr 24").getAttribute("data-search-match-count")).toBe("0");
  });

  test("VT-827AA57F-LIVE-005: bar aria-label includes the search match count", () => {
    renderScrubber({
      searchMatchEncounterIds: new Set(["enc-3"]),
    });
    expect(findBarByLabel("Feb 24").getAttribute("aria-label")).toMatch(
      /1 match search/
    );
    expect(findBarByLabel("May 24").getAttribute("aria-label") ?? "").not.toMatch(
      /match search/
    );
  });
});

// VT-C54B4A77: coded-data indicator on histogram bars (DI-8ECE2DAE).
// SIX_ENCOUNTERS coding profile by month, after binning by month:
//   Jan 24: total=1, coded=1 (enc-1, coded_count=1)            -> fraction 1.00
//   Feb 24: total=2, coded=1 (enc-2 uncoded, enc-3 coded=3)    -> fraction 0.50
//   Apr 24: total=1, coded=1 (enc-4, coded_count=2)            -> fraction 1.00
//   May 24: total=1, coded=1 (enc-5, coded_count=5)            -> fraction 1.00
//   Aug 24: total=1, coded=1 (enc-6, coded_count=1)            -> fraction 1.00
// Mar / Jun / Jul: total=0 (empty months) -> no underline.
describe("EncounterTimelineScrubber coded-data indicator - VT-C54B4A77", () => {
  test("VT-C54B4A77-LIVE-001: bars expose data-coded-count and data-coded-fraction", () => {
    renderScrubber();
    const feb = findBarByLabel("Feb 24");
    expect(feb.getAttribute("data-coded-count")).toBe("1");
    expect(Number(feb.getAttribute("data-coded-fraction"))).toBeCloseTo(0.5, 2);
    const apr = findBarByLabel("Apr 24");
    expect(apr.getAttribute("data-coded-count")).toBe("1");
    expect(Number(apr.getAttribute("data-coded-fraction"))).toBeCloseTo(1.0, 2);
  });

  test("VT-C54B4A77-LIVE-002: empty bins (total=0) carry zero coded count and no underline", () => {
    renderScrubber();
    const empties = getBars().filter(
      (bar) => Number(bar.getAttribute("data-total-count")) === 0
    );
    expect(empties.length).toBeGreaterThan(0);
    empties.forEach((bar) => {
      expect(bar.getAttribute("data-coded-count")).toBe("0");
      expect(
        within(bar).queryByTestId("timeline-coded-underline")
      ).not.toBeInTheDocument();
    });
  });

  test("VT-C54B4A77-LIVE-003: bars with codedCount > 0 render the emerald underline", () => {
    renderScrubber();
    const feb = findBarByLabel("Feb 24");
    expect(within(feb).getByTestId("timeline-coded-underline")).toBeInTheDocument();
    const apr = findBarByLabel("Apr 24");
    expect(within(apr).getByTestId("timeline-coded-underline")).toBeInTheDocument();
  });

  test("VT-C54B4A77-LIVE-004: underline opacity scales with coded fraction (clamped >= 0.25)", () => {
    renderScrubber();
    const apr = findBarByLabel("Apr 24");
    const aprUnderline = within(apr).getByTestId("timeline-coded-underline");
    expect(Number(window.getComputedStyle(aprUnderline).opacity)).toBeCloseTo(1.0, 2);
    const feb = findBarByLabel("Feb 24");
    const febUnderline = within(feb).getByTestId("timeline-coded-underline");
    expect(Number(window.getComputedStyle(febUnderline).opacity)).toBeCloseTo(0.5, 2);
  });

  test("VT-C54B4A77-LIVE-005: bar aria-label appends ', X of Y coded' when codedCount > 0", () => {
    renderScrubber();
    expect(findBarByLabel("Feb 24").getAttribute("aria-label")).toMatch(/1 of 2 coded/);
    expect(findBarByLabel("Apr 24").getAttribute("aria-label")).toMatch(/1 of 1 coded/);
  });

  test("VT-C54B4A77-LIVE-006: HoverPreview shows the 'X of Y coded' line when bar is hovered", () => {
    renderScrubber();
    const feb = findBarByLabel("Feb 24");
    fireEvent.mouseEnter(feb);
    const codedLine = screen.getByTestId("timeline-coded-hover-line");
    expect(codedLine).toHaveTextContent("1 of 2 coded");
  });

  test("VT-C54B4A77-LIVE-007: bars with zero coded encounters render no coded-line in hover", () => {
    // Construct a fixture where one month has encounters but none coded.
    const ENCOUNTERS_WITH_UNCODED_BIN: ScrubberEncounter[] = [
      { encounter_id: "u1", date: "2024-01-05", text: "n", coded_count: 0 },
      { encounter_id: "u2", date: "2024-02-10", text: "n", coded_count: 0 },
      { encounter_id: "u3", date: "2024-03-12", text: "n", coded_count: 0 },
      { encounter_id: "u4", date: "2024-04-04", text: "n", coded_count: 0 },
      { encounter_id: "u5", date: "2024-05-18", text: "n", coded_count: 0 },
      { encounter_id: "u6", date: "2024-08-30", text: "n", coded_count: 0 },
    ];
    renderScrubber({ encounters: ENCOUNTERS_WITH_UNCODED_BIN });
    expect(
      screen.queryAllByTestId("timeline-coded-underline").length
    ).toBe(0);
    fireEvent.mouseEnter(findBarByLabel("Feb 24"));
    expect(
      screen.queryByTestId("timeline-coded-hover-line")
    ).not.toBeInTheDocument();
  });
});
