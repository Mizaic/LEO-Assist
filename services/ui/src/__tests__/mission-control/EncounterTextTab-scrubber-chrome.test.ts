import { readFileSync } from "fs";
import { resolve } from "path";

// VT-LEO-AI-173 static-source verification: confirms structural
// invariants of the histogram scrubber, its sibling modules, and
// its EncounterTextTab wiring without booting React. Source
// assertions are stable across runtime environments and complement
// the live-render spec in EncounterTimelineScrubber.test.tsx.

const SCRUBBER_PATH = resolve(
  __dirname,
  "../../components/mission-control/EncounterTimelineScrubber.tsx"
);
const HISTOGRAM_BAR_PATH = resolve(
  __dirname,
  "../../components/mission-control/TimelineHistogramBar.tsx"
);
const POPOVER_PATH = resolve(
  __dirname,
  "../../components/mission-control/TimelineBinPopover.tsx"
);
const BRUSH_PATH = resolve(
  __dirname,
  "../../components/mission-control/TimelineRangeBrush.tsx"
);
const BINS_PATH = resolve(
  __dirname,
  "../../components/mission-control/timelineBins.ts"
);
const TAB_PATH = resolve(
  __dirname,
  "../../components/mission-control/EncounterTextTab.tsx"
);

function readSource(path: string): string {
  return readFileSync(path, "utf8");
}

describe("EncounterTimelineScrubber static source - VT-LEO-AI-173", () => {
  const src = readSource(SCRUBBER_PATH);
  const barSrc = readSource(HISTOGRAM_BAR_PATH);

  test("VT-173-TC-008: active bar wraps motion.div with layoutId='timeline-active-bin'", () => {
    expect(barSrc).toMatch(/layoutId=["']timeline-active-bin["']/);
  });

  test("VT-173-TC-009: imports useMotion from @leo/design-system", () => {
    expect(src).toMatch(
      /import\s*\{[^}]*useMotion[^}]*\}\s*from\s*["']@leo\/design-system["']/
    );
  });

  test("scrubber consumes useMotion() and reads transitions tokens", () => {
    expect(src).toMatch(/useMotion\(\)/);
    expect(src).toMatch(/transitions\.hover\.duration/);
    expect(src).toMatch(/reducedMotion/);
  });

  test("scrubber uses framer-motion AnimatePresence and motion primitives", () => {
    expect(src).toMatch(/from\s*["']framer-motion["']/);
    expect(src).toMatch(/AnimatePresence/);
    expect(barSrc).toMatch(/fm\.div/);
  });

  test("scrubber exposes data-testid for episode window band", () => {
    expect(src).toMatch(/data-testid=["']timeline-window-band["']/);
  });

  test("scrubber exposes data-testid for the strip itself", () => {
    expect(src).toMatch(/data-testid=["']encounter-timeline-scrubber["']/);
  });

  test("scrubber auto-hides below the 5-encounter threshold", () => {
    expect(src).toMatch(/MIN_ENCOUNTERS_FOR_SCRUBBER\s*=\s*5/);
    expect(src).toMatch(
      /encounters\.length\s*<\s*MIN_ENCOUNTERS_FOR_SCRUBBER[\s\S]*?return\s+null/
    );
  });

  test("scrubber root uses position: sticky with top: 0", () => {
    expect(src).toMatch(/position:\s*["']sticky["']/);
    expect(src).toMatch(/top:\s*0/);
  });

  test("scrubber composes binning helpers, brush, and popover siblings", () => {
    expect(src).toMatch(/from\s*["']\.\/timelineBins["']/);
    expect(src).toMatch(/from\s*["']\.\/TimelineBinPopover["']/);
    expect(src).toMatch(/from\s*["']\.\/TimelineRangeBrush["']/);
    expect(src).toMatch(/buildBins/);
    expect(src).toMatch(/pickGranularity/);
  });

  test("scrubber wires reset zoom button only when zoomed", () => {
    expect(src).toMatch(/isZoomed/);
    expect(src).toMatch(/Reset zoom/);
  });
});

describe("timelineBins helpers - VT-LEO-AI-173", () => {
  const src = readSource(BINS_PATH);

  test("pickGranularity covers all five thresholds", () => {
    expect(src).toMatch(/days\s*<=\s*60[\s\S]*?return\s+["']day["']/);
    expect(src).toMatch(/days\s*<=\s*180[\s\S]*?return\s+["']week["']/);
    expect(src).toMatch(/days\s*<=\s*730[\s\S]*?return\s+["']month["']/);
    expect(src).toMatch(/days\s*<=\s*1825[\s\S]*?return\s+["']quarter["']/);
    expect(src).toMatch(/return\s+["']year["']/);
  });

  test("exports buildBins, buildDated, pickGranularity, clampRange", () => {
    expect(src).toMatch(/export function buildBins/);
    expect(src).toMatch(/export function buildDated/);
    expect(src).toMatch(/export function pickGranularity/);
    expect(src).toMatch(/export function clampRange/);
  });
});

describe("TimelineBinPopover static source - VT-LEO-AI-173", () => {
  const src = readSource(POPOVER_PATH);

  test("popover exposes data-testid and per-row data-encounter-id markers", () => {
    expect(src).toMatch(/data-testid=["']timeline-bin-popover["']/);
    expect(src).toMatch(/data-popover-row=["']true["']/);
    expect(src).toMatch(/data-encounter-id=\{id\}/);
  });

  test("popover handles Escape to close", () => {
    expect(src).toMatch(/event\.key\s*===\s*["']Escape["']/);
  });
});

describe("TimelineRangeBrush static source - VT-LEO-AI-173", () => {
  const src = readSource(BRUSH_PATH);

  test("brush exposes role=slider handles with aria-value attributes", () => {
    expect(src).toMatch(/role=["']slider["']/);
    expect(src).toMatch(/aria-valuemin=\{fullMinMs\}/);
    expect(src).toMatch(/aria-valuemax=\{fullMaxMs\}/);
    expect(src).toMatch(/aria-valuenow=\{visibleFromMs\}/);
    expect(src).toMatch(/aria-valuenow=\{visibleToMs\}/);
  });

  test("brush handles ArrowLeft / ArrowRight with shift for large steps", () => {
    expect(src).toMatch(/ArrowLeft/);
    expect(src).toMatch(/ArrowRight/);
    expect(src).toMatch(/shiftKey/);
  });

  test("VT-173-TC-017: brush exposes a draggable focus band (mouse + keyboard)", () => {
    expect(src).toMatch(/data-testid=["']timeline-range-band["']/);
    expect(src).toMatch(/data-handle=["']band["']/);
    expect(src).toMatch(/handleBandMouseDown/);
    expect(src).toMatch(/handleBandKeyDown/);
    expect(src).toMatch(/cursor:\s*drag\s*===\s*["']band["']\s*\?\s*["']grabbing["']\s*:\s*["']grab["']/);
  });

  test("VT-173-TC-018: band drag pans both ends together and clamps inside the full range", () => {
    expect(src).toMatch(/const updateBand/);
    expect(src).toMatch(/nextFrom\s*<\s*fullMinMs/);
    expect(src).toMatch(/nextTo\s*>\s*fullMaxMs/);
  });
});

describe("EncounterTimelineScrubber focus-band invariants - VT-LEO-AI-173", () => {
  const src = readSource(SCRUBBER_PATH);

  test("VT-173-TC-019: histogram bins are computed from the FULL range (not the zoom window)", () => {
    expect(src).toMatch(/buildBins\(dated,\s*fullMinMs,\s*fullMaxMs,\s*granularity\)/);
    expect(src).toMatch(/pickGranularity\([^)]*fullMaxMs\s*-\s*fullMinMs[^)]*\)/);
  });

  test("VT-173-TC-020: scrubber renders a focus band when zoomed and marks out-of-focus bars", () => {
    const barSrc = readSource(HISTOGRAM_BAR_PATH);
    expect(src).toMatch(/data-testid=["']timeline-focus-band["']/);
    expect(barSrc).toMatch(/data-in-focus=\{isOutOfFocus\s*\?\s*["']false["']\s*:\s*["']true["']\}/);
  });
});

describe("EncounterTextTab scrubber wiring - VT-LEO-AI-173", () => {
  const src = readSource(TAB_PATH);

  test("VT-173-TC-010: imports EncounterTimelineScrubber and renders it", () => {
    expect(src).toMatch(
      /import\s+EncounterTimelineScrubber\s+from\s+["']\.\/EncounterTimelineScrubber["']/
    );
    expect(src).toMatch(/<EncounterTimelineScrubber\s/);
  });

  test("scrubber receives encounters, linked set, episode window, milestones and jump handler", () => {
    expect(src).toMatch(/encounters=\{encounters\}/);
    expect(src).toMatch(/linkedEncounterIds=\{linkedEncounterIds\}/);
    expect(src).toMatch(/episodeFrom=\{from\}/);
    expect(src).toMatch(/episodeTo=\{to\}/);
    expect(src).toMatch(/milestones=\{episode\.milestones\s*\?\?\s*\[\]\}/);
    expect(src).toMatch(/onJumpToEncounter=\{jumpToEncounter\}/);
  });

  test("tab uses IntersectionObserver to keep scrubber in sync with scroll", () => {
    expect(src).toMatch(/new IntersectionObserver/);
    expect(src).toMatch(/setVisibleEncounterId/);
  });

  test("VT-173-TC-011: EncounterTextTab.tsx is at or under 500 LOC", () => {
    const lineCount = src.split("\n").length;
    expect(lineCount).toBeLessThanOrEqual(500);
  });
});

describe("EncounterTextTab overlay-first chrome - VT-LEO-AI-205", () => {
  const src = readSource(TAB_PATH);

  test("VT-205-TC-CHROME-001: scope chips and accordions are gone", () => {
    expect(src).not.toMatch(/Episode linked \(/);
    expect(src).not.toMatch(/Episode window \(/);
    expect(src).not.toMatch(/All encounters \(/);
    expect(src).not.toMatch(/<Accordion[\s>]/);
    expect(src).not.toMatch(/setScope/);
    expect(src).not.toMatch(/splitEncounters/);
  });

  test("VT-205-TC-CHROME-002: Coded only switch and Search field are kept", () => {
    expect(src).toMatch(/label=\{<Typography variant="caption">Coded only<\/Typography>\}/);
    expect(src).toMatch(/Search text in shown encounters/);
  });

  test("VT-205-TC-CHROME-003: brush state defaults to padded episode-linked window", () => {
    expect(src).toMatch(/episodeLinkedRange/);
    expect(src).toMatch(/padRange/);
    expect(src).toMatch(/defaultRangeAppliedRef/);
  });

  test("VT-205-TC-CHROME-004: visible encounters use applyCommonFilters with the brush range", () => {
    expect(src).toMatch(/applyCommonFilters\(encounters,\s*\{[\s\S]*timelineRange[\s\S]*\}\)/);
  });

  test("VT-205-TC-CHROME-005: episode-linked encounters render an In episode chip", () => {
    expect(src).toMatch(/isLinkedToEpisode=\{isLinked\}/);
  });
});

const SCRUBBER_OVERLAYS_PATH = resolve(
  __dirname,
  "../../components/mission-control/TimelineOverlays.tsx"
);

describe("EncounterTimelineScrubber overlays - VT-LEO-AI-205", () => {
  const src = readSource(SCRUBBER_PATH);
  const overlaysSrc = readSource(SCRUBBER_OVERLAYS_PATH);

  test("VT-205-TC-OVERLAY-001: scrubber accepts a milestones prop", () => {
    expect(src).toMatch(/milestones\?:\s*Array<\{\s*milestone_type:\s*string;/);
  });

  test("VT-205-TC-OVERLAY-002: episode band is derived from linked-encounter dates (not referral_date / end_date)", () => {
    expect(src).toMatch(/linkedTicks/);
    expect(src).toMatch(/Tightened episode band/);
    expect(src).not.toMatch(/toTimestamp\(episodeFrom\)/);
  });

  test("VT-205-TC-OVERLAY-003: per-encounter linked tick markers and milestone markers are rendered", () => {
    expect(src).toMatch(/<LinkedEncounterTicks\s/);
    expect(src).toMatch(/<MilestoneMarkers\s/);
    expect(overlaysSrc).toMatch(/data-testid=["']timeline-linked-tick["']/);
    expect(overlaysSrc).toMatch(/data-testid=["']timeline-milestone-marker["']/);
  });

  test("VT-205-TC-OVERLAY-004: caption copy reflects brush as a viewing tool", () => {
    expect(src).toMatch(/widen or narrow your view/);
    expect(src).not.toMatch(/drag the focus band to filter\b/);
  });

  test("VT-205-TC-OVERLAY-005: milestone markers expose accessible labels and keyboard activation", () => {
    expect(overlaysSrc).toMatch(/aria-label=\{`Milestone:/);
    expect(overlaysSrc).toMatch(/event\.key === "Enter"/);
  });
});
