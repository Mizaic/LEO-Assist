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
 *   TC-004: See more fetches and reveals the letter sentence.
 *   TC-005: a single mention shows term, assertion, and value first;
 *           letter text stays behind See more.
 *   TC-006: a mentions-fetch failure surfaces a plain-English error, not a
 *           silent empty state.
 *   TC-007: a concept coded only from a document/chunk (no Encounter
 *           mention) still shows its mention and fetches detail using the
 *           document source type -- regression guard for the bug where
 *           document-sourced concepts showed "No recorded mentions found".
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    const user = userEvent.setup();
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);

    await user.click(screen.getByText("Obesity"));

    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("Obesity");
    expect(dialog.textContent).toContain("123456");
  });

  test("TC-003: the popover lists every dated mention, most recent first", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        source_id: "enc-2",
        source_type: "encounter",
        source_date: "2026-06-01",
        assertion: "present",
        confidence: 0.9,
      },
      {
        source_id: "enc-1",
        source_type: "encounter",
        source_date: "2025-01-15",
        assertion: "historical",
        confidence: 0.8,
      },
    ]);
    const user = userEvent.setup();
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    await user.click(screen.getByText("Obesity"));

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

  test("TC-004: See more fetches and reveals the letter sentence", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        source_id: "enc-2",
        source_type: "encounter",
        source_date: "2026-06-01",
        assertion: "present",
        confidence: 0.9,
      },
      {
        source_id: "enc-1",
        source_type: "encounter",
        source_date: "2025-01-15",
        assertion: "historical",
        confidence: 0.8,
      },
    ]);
    mockedFetchDetail.mockResolvedValue({
      source_id: "enc-2",
      source_type: "encounter",
      source_date: "2026-06-01",
      concept_id: "123456",
      name: "Obesity (disorder)",
      read_code: "22K.",
      assertion: "present",
      confidence: 0.9,
      evidence: "obesity",
      evidence_sentence: "Patient reports weight gain consistent with obesity.",
    });
    const user = userEvent.setup();
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    await user.click(screen.getByText("Obesity"));

    const seeMore = await screen.findAllByRole("button", { name: "See more" });
    expect(mockedFetchDetail).not.toHaveBeenCalled();
    await user.click(seeMore[0]);

    await waitFor(() => {
      expect(mockedFetchDetail).toHaveBeenCalledWith(
        "pat-1",
        "123456",
        "encounter",
        "enc-2"
      );
    });
    expect(
      await screen.findByText(/Patient reports weight gain consistent with obesity\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(/evidence:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/evidence_sentence:/i)).not.toBeInTheDocument();
  });

  test("TC-005: a single mention shows term, assertion, and value first", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        source_id: "enc-1",
        source_type: "encounter",
        source_date: "2026-06-01",
        assertion: "present",
        confidence: 0.9,
        value: "31",
        unit: "mmol/mol",
      },
    ]);
    mockedFetchDetail.mockResolvedValue({
      source_id: "enc-1",
      source_type: "encounter",
      source_date: "2026-06-01",
      concept_id: "123456",
      name: "Obesity (disorder)",
      read_code: "22K.",
      assertion: "present",
      confidence: 0.9,
      evidence: "obesity",
      evidence_sentence: "BMI 34, counselled on weight management.",
    });
    const user = userEvent.setup();
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    await user.click(screen.getByText("Obesity"));

    const dialog = await screen.findByRole("dialog");
    await waitFor(() => {
      expect(dialog.textContent).toMatch(/Obesity/);
      expect(dialog.textContent).toMatch(/Present/);
      expect(dialog.textContent).toMatch(/31 mmol\/mol/);
    });
    expect(mockedFetchDetail).not.toHaveBeenCalled();
    expect(
      screen.queryByText(/BMI 34, counselled on weight management\./),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "See more" }));
    expect(
      await screen.findByText(/BMI 34, counselled on weight management\./),
    ).toBeInTheDocument();
  });

  test("TC-006: a mentions-fetch failure shows a plain-English error", async () => {
    mockedFetchMentions.mockRejectedValue(new Error("Unable to load evidence."));
    const user = userEvent.setup();
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="123456" />);
    await user.click(screen.getByText("Obesity"));

    expect(await screen.findByText("Unable to load evidence.")).toBeInTheDocument();
  });

  test("TC-007: a document-sourced mention (no encounter) still shows and expands", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        source_id: "doc-9",
        source_type: "document",
        source_date: "2026-03-10",
        assertion: "present",
        confidence: 0.85,
      },
    ]);
    mockedFetchDetail.mockResolvedValue({
      source_id: "doc-9",
      source_type: "document",
      source_date: "2026-03-10",
      concept_id: "414916001",
      name: "Obesity (disorder)",
      read_code: "22K.",
      assertion: "present",
      confidence: 0.85,
      evidence: "obesity",
      evidence_sentence: "Referral letter notes long-standing obesity.",
    });
    const user = userEvent.setup();
    render(<CodedEntityChip patientId="pat-1" name="Obesity" conceptId="414916001" />);
    await user.click(screen.getByText("Obesity"));

    expect(await screen.findByText("Document")).toBeInTheDocument();
    expect(mockedFetchDetail).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "See more" }));
    await waitFor(() => {
      expect(mockedFetchDetail).toHaveBeenCalledWith(
        "pat-1",
        "414916001",
        "document",
        "doc-9"
      );
    });
    expect(
      await screen.findByText(/Referral letter notes long-standing obesity\./),
    ).toBeInTheDocument();
  });

  test("TC-008: a reading mention shows value, unit, and the letter date", async () => {
    mockedFetchMentions.mockResolvedValue([
      {
        source_id: "chunk-7",
        source_type: "document",
        source_date: "2026-08-31",
        assertion: "present",
        confidence: 0.9,
        value: "70",
        unit: "bpm",
        observed_at: "2025-11-24",
      },
    ]);
    mockedFetchDetail.mockResolvedValue({
      source_id: "chunk-7",
      source_type: "document",
      source_date: "2026-08-31",
      concept_id: "364075005",
      name: "Heart rate",
      read_code: null,
      assertion: "present",
      confidence: 0.9,
      evidence: "Heart rate 70 bpm",
      evidence_sentence: "Heart rate | 70 bpm, 24 Nov 2025",
      value: "70",
      unit: "bpm",
      observed_at: "2025-11-24",
    });
    const user = userEvent.setup();
    render(<CodedEntityChip patientId="pat-1" name="Heart rate" conceptId="364075005" />);
    await user.click(screen.getByText("Heart rate"));

    const dialog = await screen.findByRole("dialog");
    await waitFor(() => {
      expect(dialog.textContent).toMatch(/70 bpm/);
      expect(dialog.textContent).toMatch(/24 Nov 2025/);
      expect(dialog.textContent).toMatch(/Present/);
    });
    expect(screen.queryByText(/Heart rate \| 70 bpm/)).not.toBeInTheDocument();
  });
});
