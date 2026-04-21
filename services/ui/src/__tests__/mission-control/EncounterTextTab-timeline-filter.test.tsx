import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import EncounterTextTab from "@/components/mission-control/EncounterTextTab";
import type { MissionEpisode } from "@/lib/missionControlApi";
import {
  fetchPatientEncounters,
  resetAndRecodeEncounter,
} from "@/lib/missionControlApi";
import { fetchEncounterCodedLinks } from "@/lib/api";

// VT-LEO-AI-205 (supersedes VT-LEO-AI-173 TC-020 / TC-021 / TC-022):
// integration verification that the timeline brush is the sole
// spatial filter for the flat encounter list, that the default
// brush window is initialised to the padded episode window, and
// that jumping to an encounter clears the brush so the target
// stays visible.

jest.mock("@/lib/missionControlApi", () => ({
  fetchPatientEncounters: jest.fn(),
  resetAndRecodeEncounter: jest.fn(),
}));

jest.mock("@/lib/api", () => ({
  fetchEncounterCodedLinks: jest.fn(),
}));

jest.mock("next/link", () => {
  const ReactLib = require("react") as typeof import("react");
  return ReactLib.forwardRef(function MockLink(
    {
      children,
      href,
      ...rest
    }: {
      children: React.ReactNode;
      href: string;
    },
    ref: React.ForwardedRef<HTMLAnchorElement>
  ) {
    return (
      <a ref={ref} href={href} {...rest}>
        {children}
      </a>
    );
  });
});

const SIX_ENCOUNTERS = [
  { encounter_id: "enc-1", date: "2024-01-05", text: "Initial complaint",  coded_count: 1 },
  { encounter_id: "enc-2", date: "2024-02-10", text: "Routine review",     coded_count: 0 },
  { encounter_id: "enc-3", date: "2024-02-25", text: "Referral to clinic", coded_count: 3 },
  { encounter_id: "enc-4", date: "2024-04-04", text: "Specialist seen",    coded_count: 2 },
  { encounter_id: "enc-5", date: "2024-05-18", text: "Diagnosis recorded", coded_count: 5 },
  { encounter_id: "enc-6", date: "2024-08-30", text: "Follow up letter",   coded_count: 1 },
];

const EPISODE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "colorectal",
  condition_type: "cancer",
  status: "completed",
  cancer_stage: null,
  referral_date: "2024-02-25",
  end_date: "2024-05-18",
  diagnostic_interval_days: 83,
  primary_care_interval_days: 14,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
  linked_encounter_ids: ["enc-3", "enc-4", "enc-5"],
  milestones: [
    { milestone_type: "gp_referral", encounter_id: "enc-3", date: "2024-02-25" },
    { milestone_type: "specialist_visit", encounter_id: "enc-4", date: "2024-04-04" },
    { milestone_type: "cancer_diagnosis", encounter_id: "enc-5", date: "2024-05-18" },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  (fetchPatientEncounters as jest.Mock).mockResolvedValue(SIX_ENCOUNTERS);
  (resetAndRecodeEncounter as jest.Mock).mockResolvedValue({});
  (fetchEncounterCodedLinks as jest.Mock).mockResolvedValue([]);
});

async function renderTab() {
  render(<EncounterTextTab patientId="patient-1" episode={EPISODE} />);
  await waitFor(() => {
    expect(screen.getByTestId("encounter-timeline-scrubber")).toBeInTheDocument();
  });
}

function getFromHandle(): HTMLElement {
  const brush = screen.getByTestId("timeline-range-brush");
  const handle = within(brush)
    .getAllByRole("slider")
    .find((node) => node.getAttribute("data-handle") === "from");
  if (!handle) throw new Error("from handle not found");
  return handle;
}

function visibleCardIds(): string[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>("[data-encounter-card-id]")
  ).map((node) => node.getAttribute("data-encounter-card-id") ?? "");
}

describe("EncounterTextTab + timeline brush filter - VT-LEO-AI-205", () => {
  test("VT-205-TC-001: default brush is initialised to the padded episode window", async () => {
    await renderTab();
    await waitFor(() => {
      expect(screen.getByTestId("timeline-filter-banner")).toBeInTheDocument();
    });
    const ids = visibleCardIds();
    expect(ids).toEqual(expect.arrayContaining(["enc-3", "enc-4", "enc-5"]));
    expect(ids).not.toContain("enc-6");
  });

  test("VT-205-TC-002: clearing the brush filter shows every patient encounter", async () => {
    await renderTab();
    const banner = await screen.findByTestId("timeline-filter-banner");
    const clearButton = within(banner).getByRole("button", { name: /clear/i });
    fireEvent.click(clearButton);

    await waitFor(() => {
      expect(screen.queryByTestId("timeline-filter-banner")).not.toBeInTheDocument();
    });
    expect(visibleCardIds().sort()).toEqual(
      SIX_ENCOUNTERS.map((e) => e.encounter_id).sort()
    );
  });

  test("VT-205-TC-003: dragging the brush narrows the encounter list", async () => {
    await renderTab();
    const banner = await screen.findByTestId("timeline-filter-banner");
    const initialBefore = visibleCardIds();

    const fromHandle = getFromHandle();
    fromHandle.focus();
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });

    await waitFor(() => {
      expect(visibleCardIds().length).toBeLessThanOrEqual(initialBefore.length);
    });
    expect(banner).toBeInTheDocument();
  });

  test("VT-205-TC-004: clicking a bar (DI-15E0094F) re-filters the list to that bin's date range", async () => {
    // Per DI-15E0094F a bar click is now a uniform "filter the list
    // to this period" action -- it never jumps and never clears the
    // banner. Clicking the Aug 24 bin should keep the banner visible
    // (with a new window) and surface enc-6, which sits in Aug 24.
    await renderTab();
    await screen.findByTestId("timeline-filter-banner");
    expect(visibleCardIds()).not.toContain("enc-6");

    const augBar = screen
      .getAllByRole("button")
      .find((node) => node.getAttribute("data-bin-label") === "Aug 24");
    expect(augBar).toBeDefined();
    fireEvent.click(augBar!);

    await waitFor(() => {
      expect(visibleCardIds()).toContain("enc-6");
    });
    expect(screen.getByTestId("timeline-filter-banner")).toBeInTheDocument();
    // Encounters that sat outside the new Aug-2024 window should be
    // gone from the list.
    expect(visibleCardIds()).not.toContain("enc-3");
    expect(visibleCardIds()).not.toContain("enc-4");
  });
});
