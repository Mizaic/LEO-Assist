/**
 * Stage 9a - NCDA pathway timeline VT.
 *
 * Confirms the new timeline component:
 *   - Renders the four canonical anchors with plain-language labels.
 *   - Switches the Dx label between "Cancer found" and "Cancer ruled out"
 *     based on outcome.
 *   - Hides the treatment node when outcome is cancer_excluded.
 *   - Surfaces the cohort badge.
 */
import { render, screen } from "@testing-library/react";

import NcdaPathwayTimeline from "@/components/ncda/NcdaPathwayTimeline";
import type { NcdaPathway, PathwayBands } from "@/lib/ncdaPathway";

const BANDS: PathwayBands = {
  site_key: "skin",
  ftr_to_seen_typical_max_days: 10,
  seen_to_dx_typical_max_days: 7,
  dx_to_treatment_typical_max_days: 21,
  ftr_to_dx_typical_max_days: 14,
  ftr_to_treatment_typical_max_days: 42,
};

function basePathway(overrides: Partial<NcdaPathway> = {}): NcdaPathway {
  return {
    patient_id: "P1",
    cohort: "1a",
    tier: "auto",
    site_key: "skin",
    ftr: { encounter_id: "F1", date: "2024-01-15", citation_snippet: "Fast track 2WW" },
    seen: { encounter_id: "S1", date: "2024-01-25", citation_snippet: "Seen in clinic" },
    dx: {
      encounter_id: "D1",
      date: "2024-02-10",
      outcome: "cancer_found",
      citation_snippet: "Malignant melanoma confirmed",
    },
    treatment: {
      encounter_id: "T1",
      date: "2024-03-01",
      citation_snippet: "Excision performed",
    },
    ...overrides,
  };
}

describe("NcdaPathwayTimeline", () => {
  it("renders all four anchors with plain language labels for cancer_found", () => {
    render(<NcdaPathwayTimeline pathway={basePathway()} bands={BANDS} />);
    expect(screen.getByText("Urgent referral")).toBeInTheDocument();
    expect(screen.getByText("First hospital visit")).toBeInTheDocument();
    expect(screen.getByText("Cancer found")).toBeInTheDocument();
    expect(screen.getByText("Treatment began")).toBeInTheDocument();
  });

  it("switches dx label to 'Cancer ruled out' when outcome is cancer_excluded", () => {
    const pathway = basePathway({
      cohort: "1b",
      dx: {
        encounter_id: "D1",
        date: "2024-02-10",
        outcome: "cancer_excluded",
        citation_snippet: "Discharged from 2WW pathway",
      },
      treatment: null,
    });
    render(<NcdaPathwayTimeline pathway={pathway} bands={BANDS} />);
    expect(screen.getByText("Cancer ruled out")).toBeInTheDocument();
    expect(screen.queryByText("Treatment began")).not.toBeInTheDocument();
  });

  it("renders the cohort label as a chip", () => {
    render(<NcdaPathwayTimeline pathway={basePathway()} bands={BANDS} />);
    const chip = screen.getByTestId("ncda-cohort-chip");
    expect(chip.textContent).toMatch(/Standard 2WW/i);
    expect(chip.textContent).toMatch(/cancer found/i);
  });

  it("shows 'Not found' when an anchor is missing", () => {
    const pathway = basePathway({
      seen: null,
      seen_missing: true,
    });
    render(<NcdaPathwayTimeline pathway={pathway} bands={BANDS} />);
    const notFoundEntries = screen.getAllByText("Not found");
    expect(notFoundEntries.length).toBeGreaterThan(0);
  });

  it("renders a cohort 3 timeline (no FTR) without crashing", () => {
    const pathway = basePathway({
      cohort: "3",
      tier: "review",
      ftr: null,
    });
    render(<NcdaPathwayTimeline pathway={pathway} bands={BANDS} />);
    expect(screen.getByText("Cancer found without urgent referral")).toBeInTheDocument();
  });
});
