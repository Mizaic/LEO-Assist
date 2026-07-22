/**
 * VT for DI-7DE8E8ED -- problem list chips show SNOMED code, term, and
 * dated evidence.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-7DE8E8ED
 *
 * Covers:
 *   TC-001: a chip with no concept_id renders as a plain, non-interactive chip.
 *   TC-002: selecting a coded chip shows the SNOMED CT concept ID and preferred term.
 *   TC-003: the popover lists every dated mention returned by the API.
 *   TC-004: selecting a date fetches and reveals its evidence sentence.
 *   TC-005: a single-mention concept auto-expands its evidence without an
 *           extra selection step.
 *   TC-006: a mentions-fetch failure surfaces a plain-English error, not a
 *           silent empty state.
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CodedEntityChip } from "@/components/patients/CodedEntityChip";
import * as api from "@/lib/patientEprApi";

jest.mock("@/lib/patientEprApi", () => ({
  fetchConceptMentions: jest.fn(),
  fetchConceptMentionDetail: jest.fn(),
}));

const mockedFetchMentions = api.fetchConceptMentions as jest.Mock;
const mockedFetchDetail = api.fetchConceptMentionDetail as jest.Mock;

describe("VT-7DE8E8ED - CodedEntityChip evidence popover", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("TC-001: a chip with no concept_id renders as a plain, non-interactive chip", () => {
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId={null} />);
    expect(screen.getByText("Obesity")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(mockedFetchMentions).not.toHaveBeenCalled();
  });

  test("TC-002: selecting a coded chip shows the SNOMED code and preferred term", async () => {
    mockedFetchMentions.mockResolvedValue([]);
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);

    fireEvent.click(screen.getByText("Obesity"));

    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("Obesity");
    expect(dialog.textContent).toContain("123456");
  });

  test("TC-003: the popover lists every dated mention, most recent first", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        encounter_id: "enc-2",
        encounter_date: "2026-06-01",
        assertion: "present",
        confidence: 0.9,
      },
      {
        encounter_id: "enc-1",
        encounter_date: "2025-01-15",
        assertion: "historical",
        confidence: 0.8,
      },
    ]);
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    fireEvent.click(screen.getByText("Obesity"));

    const dialog = await screen.findByRole("dialog");
    await waitFor(() => {
      expect(dialog.textContent).toMatch(/01 Jun 2026/);
      expect(dialog.textContent).toMatch(/15 Jan 2025/);
    });
    const juneIdx = dialog.textContent!.indexOf("01 Jun 2026");
    const janIdx = dialog.textContent!.indexOf("15 Jan 2025");
    expect(juneIdx).toBeGreaterThanOrEqual(0);
    expect(juneIdx).toBeLessThan(janIdx);
  });

  test("TC-004: selecting a date fetches and reveals its evidence sentence", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        encounter_id: "enc-2",
        encounter_date: "2026-06-01",
        assertion: "present",
        confidence: 0.9,
      },
      {
        encounter_id: "enc-1",
        encounter_date: "2025-01-15",
        assertion: "historical",
        confidence: 0.8,
      },
    ]);
    mockedFetchDetail.mockResolvedValue({
      encounter_id: "enc-2",
      encounter_date: "2026-06-01",
      concept_id: "123456",
      name: "Obesity (disorder)",
      read_code: "22K.",
      assertion: "present",
      confidence: 0.9,
      evidence: "obesity",
      evidence_sentence: "Patient reports weight gain consistent with obesity.",
    });
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    fireEvent.click(screen.getByText("Obesity"));

    const dateRow = await screen.findByText("01 Jun 2026");
    expect(mockedFetchDetail).not.toHaveBeenCalled();
    fireEvent.click(dateRow);

    await waitFor(() => {
      expect(mockedFetchDetail).toHaveBeenCalledWith("pat-1", "123456", "enc-2");
    });
    expect(
      await screen.findByText(/Patient reports weight gain consistent with obesity\./),
    ).toBeInTheDocument();
  });

  test("TC-005: a single-mention concept auto-expands its evidence", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        encounter_id: "enc-1",
        encounter_date: "2026-06-01",
        assertion: "present",
        confidence: 0.9,
      },
    ]);
    mockedFetchDetail.mockResolvedValue({
      encounter_id: "enc-1",
      encounter_date: "2026-06-01",
      concept_id: "123456",
      name: "Obesity (disorder)",
      read_code: "22K.",
      assertion: "present",
      confidence: 0.9,
      evidence: "obesity",
      evidence_sentence: "BMI 34, counselled on weight management.",
    });
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    fireEvent.click(screen.getByText("Obesity"));

    await waitFor(() => {
      expect(mockedFetchDetail).toHaveBeenCalledWith("pat-1", "123456", "enc-1");
    });
    expect(
      await screen.findByText(/BMI 34, counselled on weight management\./),
    ).toBeInTheDocument();
  });

  test("TC-006: a mentions-fetch failure shows a plain-English error", async () => {
    mockedFetchMentions.mockRejectedValue(new Error("Unable to load evidence."));
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    fireEvent.click(screen.getByText("Obesity"));

    expect(await screen.findByText("Unable to load evidence.")).toBeInTheDocument();
  });
});
