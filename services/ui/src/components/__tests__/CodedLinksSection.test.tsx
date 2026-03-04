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

  it("delete button has aria-label with term name", async () => {
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={jest.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByText("Chest pain")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Remove Chest pain" })).toBeInTheDocument();
  });

  it("delete button opens ConfirmDialog before removing", async () => {
    const user = userEvent.setup();
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={jest.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByText("Chest pain")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Remove Chest pain" }));
    expect(screen.getByText("Remove clinical code?")).toBeInTheDocument();
    expect(screen.getByText(/permanently delete/)).toBeInTheDocument();
  });

  it("cancelling ConfirmDialog does not delete the code", async () => {
    const user = userEvent.setup();
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={jest.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByText("Chest pain")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Remove Chest pain" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Remove clinical code?")).not.toBeInTheDocument();
    expect(deleteCodedLink).not.toHaveBeenCalled();
  });

  it("confirming ConfirmDialog calls deleteCodedLink", async () => {
    const user = userEvent.setup();
    const onCorrection = jest.fn();
    render(
      <CodedLinksSection patientId="P1" encounterId="E1" onCorrection={onCorrection} />,
    );
    await waitFor(() => {
      expect(screen.getByText("Chest pain")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Remove Chest pain" }));
    await user.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => {
      expect(deleteCodedLink).toHaveBeenCalledWith("P1", "E1", "C1");
    });
  });
});
