/**
 * VT -- Chart zoom / expand capability (static-source VT).
 *
 * Verifies that all chart cards and section components correctly wire
 * up the "expand chart" pattern introduced for /audit:
 *
 *   AC1 -- ChartZoomDialog exists and exposes the required props /
 *          structure (Dialog, close button, title, children slot).
 *   AC2 -- CancerTypeRadarCard accepts an onZoom prop and renders an
 *          expand IconButton when it is provided.
 *   AC3 -- CancerTypeEvolutionSection imports ChartZoomDialog, adds
 *          zoomedYear state, and passes onZoom to every radar card.
 *   AC4 -- ComorbidityRadarCard and ComorbiditiesSection follow the
 *          same pattern as AC2/AC3.
 *   AC5 -- IntervalStripPlot accepts onZoom + chartHeight props; both
 *          PrimaryCareIntervalSection and DiagnosticIntervalSection
 *          wire up ChartZoomDialog.
 *   AC6 -- PopulationPyramidCard accepts an onZoom prop;
 *          DemographicsEvolutionSection wires up ChartZoomDialog.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const ZOOM_DIALOG = "services/ui/src/components/audit/ChartZoomDialog.tsx";
const RADAR_CARD =
  "services/ui/src/components/audit/CancerTypeRadarCard.tsx";
const CANCER_EVOLUTION =
  "services/ui/src/components/audit/CancerTypeEvolutionSection.tsx";
const COMORBIDITY_CARD =
  "services/ui/src/components/audit/ComorbidityRadarCard.tsx";
const COMORBIDITIES_SECTION =
  "services/ui/src/components/audit/ComorbiditiesSection.tsx";
const STRIP_PLOT =
  "services/ui/src/components/audit/IntervalStripPlot.tsx";
const PCI_SECTION =
  "services/ui/src/components/audit/PrimaryCareIntervalSection.tsx";
const DI_SECTION =
  "services/ui/src/components/audit/DiagnosticIntervalSection.tsx";
const PYRAMID_CARD =
  "services/ui/src/components/audit/PopulationPyramidCard.tsx";
const DEMO_SECTION =
  "services/ui/src/components/audit/DemographicsEvolutionSection.tsx";

describe("Chart zoom / expand capability", () => {
  describe("AC1 -- ChartZoomDialog component structure", () => {
    let src: string;
    beforeAll(() => {
      src = read(ZOOM_DIALOG);
    });

    test("imports MUI Dialog and DialogTitle", () => {
      expect(src).toMatch(/import\s+Dialog\s+from\s+["']@mui\/material\/Dialog["']/);
      expect(src).toMatch(/import\s+DialogTitle\s+from\s+["']@mui\/material\/DialogTitle["']/);
    });

    test("imports CloseIcon for the dismiss button", () => {
      expect(src).toMatch(/import\s+CloseIcon\s+from\s+["']@mui\/icons-material\/Close["']/);
    });

    test("exposes open, onClose, title, and children props", () => {
      expect(src).toMatch(/open:/);
      expect(src).toMatch(/onClose:/);
      expect(src).toMatch(/title:/);
      expect(src).toMatch(/children:/);
    });

    test("renders a close IconButton with aria-label", () => {
      expect(src).toMatch(/aria-label="Close expanded chart"/);
    });

    test("exposes maxWidth customisation prop", () => {
      expect(src).toMatch(/maxWidth\?:/);
    });

    test("marks the file as use client", () => {
      expect(src).toMatch(/"use client"/);
    });
  });

  describe("AC2 -- CancerTypeRadarCard zoom support", () => {
    let src: string;
    beforeAll(() => {
      src = read(RADAR_CARD);
    });

    test("declares the onZoom optional prop", () => {
      expect(src).toMatch(/onZoom\?:\s*\(\)\s*=>\s*void/);
    });

    test("imports OpenInFullIcon for the expand button", () => {
      expect(src).toMatch(/OpenInFullIcon/);
    });

    test("renders an expand IconButton with an aria-label when onZoom is present", () => {
      expect(src).toMatch(/Expand[\s\S]*?radar chart/);
      expect(src).toMatch(/onClick=\{onZoom\}/);
    });
  });

  describe("AC3 -- CancerTypeEvolutionSection zoom wiring", () => {
    let src: string;
    beforeAll(() => {
      src = read(CANCER_EVOLUTION);
    });

    test("imports ChartZoomDialog", () => {
      expect(src).toMatch(/import\s+ChartZoomDialog\s+from\s+["']\.\/ChartZoomDialog["']/);
    });

    test("maintains zoomedYear state", () => {
      expect(src).toMatch(/zoomedYear/);
      expect(src).toMatch(/setZoomedYear/);
    });

    test("passes onZoom to the baseline radar card", () => {
      const baselineCard = src.match(
        /BASELINE_YEAR[\s\S]*?<CancerTypeRadarCard[\s\S]*?\/>/,
      );
      expect(baselineCard).not.toBeNull();
      expect(baselineCard![0]).toMatch(/onZoom=/);
    });

    test("passes onZoom to the live-year radar cards", () => {
      expect(src).toMatch(/onZoom=\{[\s\S]*?setZoomedYear/);
    });

    test("renders ChartZoomDialog when a year is zoomed", () => {
      expect(src).toMatch(/<ChartZoomDialog[\s\S]*?onClose=/);
    });
  });

  describe("AC4 -- ComorbidityRadarCard and ComorbiditiesSection zoom wiring", () => {
    let card: string;
    let section: string;
    beforeAll(() => {
      card = read(COMORBIDITY_CARD);
      section = read(COMORBIDITIES_SECTION);
    });

    test("ComorbidityRadarCard declares the onZoom optional prop", () => {
      expect(card).toMatch(/onZoom\?:\s*\(\)\s*=>\s*void/);
    });

    test("ComorbidityRadarCard renders an expand IconButton when onZoom is present", () => {
      expect(card).toMatch(/onClick=\{onZoom\}/);
      expect(card).toMatch(/Expand[\s\S]*?comorbidity radar chart/);
    });

    test("ComorbiditiesSection imports ChartZoomDialog", () => {
      expect(section).toMatch(/import\s+ChartZoomDialog/);
    });

    test("ComorbiditiesSection passes onZoom to every ComorbidityRadarCard", () => {
      const onZoomMatches = [...section.matchAll(/onZoom=/g)];
      expect(onZoomMatches.length).toBeGreaterThanOrEqual(2);
    });

    test("ComorbiditiesSection renders ChartZoomDialog", () => {
      expect(section).toMatch(/<ChartZoomDialog[\s\S]*?onClose=/);
    });
  });

  describe("AC5 -- IntervalStripPlot, PCI section and DI section zoom wiring", () => {
    let strip: string;
    let pci: string;
    let di: string;
    beforeAll(() => {
      strip = read(STRIP_PLOT);
      pci = read(PCI_SECTION);
      di = read(DI_SECTION);
    });

    test("IntervalStripPlot declares onZoom optional prop", () => {
      expect(strip).toMatch(/onZoom\?:\s*\(\)\s*=>\s*void/);
    });

    test("IntervalStripPlot declares chartHeight prop with default 160", () => {
      expect(strip).toMatch(/chartHeight\?:\s*number/);
      expect(strip).toMatch(/chartHeight\s*=\s*160/);
    });

    test("IntervalStripPlot uses chartHeight in the ResponsiveContainer", () => {
      expect(strip).toMatch(/height=\{chartHeight\}/);
    });

    test("IntervalStripPlot renders an expand button when onZoom is provided", () => {
      expect(strip).toMatch(/Expand[\s\S]*?strip plot/);
      expect(strip).toMatch(/onClick=\{onZoom\}/);
    });

    test("PrimaryCareIntervalSection imports and renders ChartZoomDialog", () => {
      expect(pci).toMatch(/import\s+ChartZoomDialog/);
      expect(pci).toMatch(/<ChartZoomDialog[\s\S]*?onClose=/);
    });

    test("PrimaryCareIntervalSection passes onZoom to the strip plot", () => {
      expect(pci).toMatch(/onZoom=\{[\s\S]*?setZoomOpen/);
    });

    test("DiagnosticIntervalSection imports and renders ChartZoomDialog", () => {
      expect(di).toMatch(/import\s+ChartZoomDialog/);
      expect(di).toMatch(/<ChartZoomDialog[\s\S]*?onClose=/);
    });

    test("DiagnosticIntervalSection passes onZoom to the strip plot", () => {
      expect(di).toMatch(/onZoom=\{[\s\S]*?setZoomOpen/);
    });
  });

  describe("AC6 -- PopulationPyramidCard and DemographicsEvolutionSection zoom wiring", () => {
    let card: string;
    let section: string;
    beforeAll(() => {
      card = read(PYRAMID_CARD);
      section = read(DEMO_SECTION);
    });

    test("PopulationPyramidCard declares the onZoom optional prop", () => {
      expect(card).toMatch(/onZoom\?:\s*\(\)\s*=>\s*void/);
    });

    test("PopulationPyramidCard renders an expand IconButton when onZoom is provided", () => {
      expect(card).toMatch(/onClick=\{onZoom\}/);
      expect(card).toMatch(/Expand[\s\S]*?demographics chart/);
    });

    test("DemographicsEvolutionSection imports ChartZoomDialog", () => {
      expect(section).toMatch(/import\s+ChartZoomDialog/);
    });

    test("DemographicsEvolutionSection maintains zoomedYear state", () => {
      expect(section).toMatch(/zoomedYear/);
      expect(section).toMatch(/setZoomedYear/);
    });

    test("DemographicsEvolutionSection passes onZoom to every pyramid card", () => {
      const onZoomMatches = [...section.matchAll(/onZoom=/g)];
      expect(onZoomMatches.length).toBeGreaterThanOrEqual(2);
    });

    test("DemographicsEvolutionSection renders ChartZoomDialog", () => {
      expect(section).toMatch(/<ChartZoomDialog[\s\S]*?onClose=/);
    });
  });
});
