import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CodedLinksSection from "../CodedLinksSection";

jest.mock("@/lib/api", () => ({
  fetchEncounterCodedLinks: jest.fn(),
  deleteCodedLink: jest.fn(),
  recodeCodedLink: jest.fn(),
  updateCodedLinkModifiers: jest.fn(),
  searchTerms: jest.fn(),
}));

import { fetchEncounterCodedLinks, deleteCodedLink } from "@/lib/api";

const links = [
  { concept_id: "C1", term: "Chest pain", read_code: "182..", semantic_tag: "finding" },
  { concept_id: "C2", term: "Hypertension", read_code: "G20..", semantic_tag: "disorder" },
];

describe("CodedLinksSection", () => {
  beforeEach(() => {
    (fetchEncounterCodedLinks as jest.Mock).mockResolvedValue(links);
    (deleteCodedLink as jest.Mock).mockResolvedValue({ deleted: true });
  });

  it("renders coded links after loading", async () => {
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={jest.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByText("Chest pain")).toBeInTheDocument();
    });
    expect(screen.getByText("Hypertension")).toBeInTheDocument();
  });

  it("shows concept IDs", async () => {
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={jest.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByText(/C1/)).toBeInTheDocument();
    });
    expect(screen.getByText(/C2/)).toBeInTheDocument();
  });

  it("shows Read codes", async () => {
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={jest.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByText(/182/)).toBeInTheDocument();
    });
    expect(screen.getByText(/G20/)).toBeInTheDocument();
  });

  it("shows error on fetch failure", async () => {
    (fetchEncounterCodedLinks as jest.Mock).mockRejectedValue(new Error("API down"));
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={jest.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByText(/API down/)).toBeInTheDocument();
    });
  });
});
