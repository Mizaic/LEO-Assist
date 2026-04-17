import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import EncounterTextTab from "@/components/mission-control/EncounterTextTab";
import type { MissionEpisode } from "@/lib/missionControlApi";
import {
  fetchPatientEncounters,
  resetAndRecodeEncounter,
} from "@/lib/missionControlApi";
import { fetchEncounterCodedLinks } from "@/lib/api";

// VT-LEO-AI-173-TC-020 / TC-021: integration verification that the
// timeline scrubber's zoom brush filters the encounter list and that
// jumping to an encounter clears the filter so the target stays
// visible.

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

function clickAllScope(): void {
  const allChip = screen
    .getAllByRole("button")
    .find((node) => /^All encounters \(\d+\)$/.test(node.textContent ?? ""));
  if (!allChip) throw new Error("All encounters chip not found");
  fireEvent.click(allChip);
}

function getFromHandle(): HTMLElement {
  const brush = screen.getByTestId("timeline-range-brush");
  const handle = within(brush)
    .getAllByRole("slider")
    .find((node) => node.getAttribute("data-handle") === "from");
  if (!handle) throw new Error("from handle not found");
  return handle;
}

function countAllEncountersChip(): number {
  const all = screen
    .getAllByRole("button")
    .find((node) => /^All encounters \(\d+\)$/.test(node.textContent ?? ""));
  if (!all) throw new Error("All encounters chip not found");
  const match = (all.textContent ?? "").match(/All encounters \((\d+)\)/);
  return match ? Number(match[1]) : 0;
}

describe("EncounterTextTab + timeline brush filter - VT-LEO-AI-173", () => {
  test("VT-173-TC-020: dragging the brush narrows the encounter list and shows a banner", async () => {
    await renderTab();
    clickAllScope();
    await waitFor(() => {
      expect(countAllEncountersChip()).toBe(SIX_ENCOUNTERS.length);
    });
    expect(screen.queryByTestId("timeline-filter-banner")).not.toBeInTheDocument();

    const fromHandle = getFromHandle();
    fromHandle.focus();
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });

    await waitFor(() => {
      expect(screen.getByTestId("timeline-filter-banner")).toBeInTheDocument();
      expect(countAllEncountersChip()).toBeLessThan(SIX_ENCOUNTERS.length);
    });
  });

  test("VT-173-TC-021: clearing the timeline filter restores every encounter", async () => {
    await renderTab();
    clickAllScope();
    await waitFor(() => expect(countAllEncountersChip()).toBe(SIX_ENCOUNTERS.length));

    const fromHandle = getFromHandle();
    fromHandle.focus();
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });

    const banner = await screen.findByTestId("timeline-filter-banner");
    const clearButton = within(banner).getByRole("button", { name: /clear/i });
    fireEvent.click(clearButton);

    await waitFor(() => {
      expect(screen.queryByTestId("timeline-filter-banner")).not.toBeInTheDocument();
      expect(countAllEncountersChip()).toBe(SIX_ENCOUNTERS.length);
    });
  });

  test("VT-173-TC-022: jumping via the timeline (single-bin click) clears the filter", async () => {
    await renderTab();
    clickAllScope();
    await waitFor(() => expect(countAllEncountersChip()).toBe(SIX_ENCOUNTERS.length));

    const fromHandle = getFromHandle();
    fromHandle.focus();
    fireEvent.keyDown(fromHandle, { key: "ArrowRight", shiftKey: true });
    await screen.findByTestId("timeline-filter-banner");

    const aprBar = screen
      .getAllByRole("button")
      .find((node) => node.getAttribute("data-bin-label") === "Apr 24");
    expect(aprBar).toBeDefined();
    fireEvent.click(aprBar!);

    await waitFor(() => {
      expect(screen.queryByTestId("timeline-filter-banner")).not.toBeInTheDocument();
      expect(countAllEncountersChip()).toBe(SIX_ENCOUNTERS.length);
    });
  });
});
