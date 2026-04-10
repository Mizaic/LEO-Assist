import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import EncounterTextTab from "@/components/mission-control/EncounterTextTab";
import type { MissionEpisode } from "@/lib/missionControlApi";
import { fetchPatientEncounters, resetAndRecodeEncounter } from "@/lib/missionControlApi";
import { fetchEncounterCodedLinks } from "@/lib/api";

const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;

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

beforeAll(() => {
  HTMLElement.prototype.getBoundingClientRect = function mockRect(): DOMRect {
    return {
      x: 0,
      y: 0,
      width: 240,
      height: 40,
      top: 0,
      left: 0,
      right: 240,
      bottom: 40,
      toJSON: () => ({}),
    } as DOMRect;
  };
});

afterAll(() => {
  HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
});

const MOCK_EPISODE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "colorectal",
  condition_type: "cancer",
  status: "completed",
  cancer_stage: null,
  referral_date: "2024-06-01",
  end_date: "2024-07-20",
  diagnostic_interval_days: 49,
  primary_care_interval_days: 14,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
  milestones: [
    { milestone_type: "first_presentation", encounter_id: "enc-1", date: "2024-05-20" },
    { milestone_type: "gp_referral", encounter_id: "enc-2", date: "2024-06-01" },
    { milestone_type: "cancer_diagnosis", encounter_id: "enc-3", date: "2024-07-20" },
  ],
};

describe("EncounterTextTab milestone jump", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (fetchPatientEncounters as jest.Mock).mockResolvedValue([
      { encounter_id: "enc-1", date: "2024-05-20", text: "first", coded_count: 1 },
      { encounter_id: "enc-2", date: "2024-06-01", text: "referral", coded_count: 2 },
      { encounter_id: "enc-3", date: "2024-07-20", text: "diagnosis", coded_count: 1 },
    ]);
    (resetAndRecodeEncounter as jest.Mock).mockResolvedValue({});
    (fetchEncounterCodedLinks as jest.Mock).mockResolvedValue([]);
  });

  test("renders milestone jump chips and switches to all encounters on jump", async () => {
    render(<EncounterTextTab patientId="patient-1" episode={MOCK_EPISODE} />);

    await waitFor(() => {
      expect(screen.getByText("Jump to milestone encounter:")).toBeInTheDocument();
    });

    expect(screen.getByText("First seen - 20 May 24")).toBeInTheDocument();
    expect(screen.getByText("Referred - 01 Jun 24")).toBeInTheDocument();
    const diagnosisChip = screen.getByText("Diagnosed - 20 Jul 24");
    expect(diagnosisChip).toBeInTheDocument();

    fireEvent.click(diagnosisChip);

    await waitFor(() => {
      const allEncountersChip = screen.getByText("All encounters (3)");
      const chipRoot = allEncountersChip.closest('[role="button"]');
      expect(chipRoot?.className).toContain("MuiChip-colorPrimary");
    });
  });

  test("shows sentence evidence in coded concept tooltip", async () => {
    (fetchEncounterCodedLinks as jest.Mock).mockResolvedValue([
      {
        concept_id: "149421000000109",
        term: "Provision of faecal immunochemical test kit",
        evidence: "faecal immunochemical test kit",
        evidence_sentence:
          "Provision of faecal immunochemical test kit sent to patient.",
        evidence_start: 13,
        evidence_end: 42,
        sentence_index: 2,
      },
    ]);

    render(<EncounterTextTab patientId="patient-1" episode={MOCK_EPISODE} />);

    // Codes auto-load above the encounter text -- no toggle needed.
    // All 3 encounters share the mock, so multiple chips appear; target the first.
    await waitFor(() => {
      expect(
        screen.getAllByText(
          "Provision of faecal immunochemical test kit (149421000000109)"
        ).length
      ).toBeGreaterThan(0);
    });

    fireEvent.mouseOver(
      screen.getAllByText("Provision of faecal immunochemical test kit (149421000000109)")[0]
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          /Sentence: Provision of faecal immunochemical test kit sent to patient\./
        )
      ).toBeInTheDocument();
      expect(screen.getByText(/Mention offsets: 13-42/)).toBeInTheDocument();
    });
  });

  test("derives sentence evidence from encounter text when not stored", async () => {
    (fetchPatientEncounters as jest.Mock).mockResolvedValue([
      {
        encounter_id: "enc-1",
        date: "2024-05-20",
        text: "Patient noticed she's a bit more constipated one and off, not as regular as before.",
        coded_count: 1,
      },
    ]);
    (fetchEncounterCodedLinks as jest.Mock).mockResolvedValue([
      {
        concept_id: "363693003",
        term: "Constipation",
        evidence: "noticed she's a bit more constipated one and off",
      },
    ]);

    render(<EncounterTextTab patientId="patient-1" episode={MOCK_EPISODE} />);

    // Codes auto-load above the encounter text -- no toggle needed
    await waitFor(() => {
      expect(screen.getByText("Constipation (363693003)")).toBeInTheDocument();
    });

    fireEvent.mouseOver(screen.getByText("Constipation (363693003)"));
    await waitFor(() => {
      expect(screen.getByText(/Sentence:/)).toBeInTheDocument();
    });
  });
});
