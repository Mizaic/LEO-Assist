import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TermSearch from "../TermSearch";

const mockOnSelect = jest.fn();
const mockOnClose = jest.fn();
const mockOnCorrection = jest.fn();

jest.mock("@/lib/api", () => ({
  searchTerms: jest.fn(),
}));

import { searchTerms } from "@/lib/api";

const mockSearchTerms = searchTerms as jest.Mock;

const mockResults = [
  {
    snomed_concept_id: "123456",
    term: "Diabetes mellitus",
    read_code: "C10",
    semantic_tag: "disorder",
    score: 0.95,
  },
  {
    snomed_concept_id: "789012",
    term: "Hypertension",
    read_code: "G20",
    semantic_tag: "finding",
    score: 0.88,
  },
];

describe("TermSearch", () => {
  beforeEach(() => {
    mockOnSelect.mockClear();
    mockOnClose.mockClear();
    mockOnCorrection.mockClear();
    mockSearchTerms.mockClear();
  });

  it("renders dialog with search title", () => {
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    expect(screen.getByText("Search SNOMED terms")).toBeInTheDocument();
  });

  it("renders search input with placeholder", () => {
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    expect(screen.getByPlaceholderText(/Search SNOMED terms/)).toBeInTheDocument();
  });

  it("renders Cancel button", () => {
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", async () => {
    const user = userEvent.setup();
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(mockOnClose).toHaveBeenCalled();
  });

  it("calls searchTerms when user types 2+ characters", async () => {
    mockSearchTerms.mockResolvedValue([]);
    const user = userEvent.setup();
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    await user.type(screen.getByPlaceholderText(/Search SNOMED terms/), "dia");
    await waitFor(
      () => {
        expect(mockSearchTerms).toHaveBeenCalledWith("dia");
      },
      { timeout: 500 }
    );
  });

  it("displays search results when search returns data", async () => {
    mockSearchTerms.mockResolvedValue(mockResults);
    const user = userEvent.setup();
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    await user.type(screen.getByPlaceholderText(/Search SNOMED terms/), "diab");
    await waitFor(() => {
      expect(screen.getByText("Diabetes mellitus")).toBeInTheDocument();
    });
    expect(screen.getByText("Hypertension")).toBeInTheDocument();
  });

  it("calls onSelect and onClose when result is clicked (without captureValueUnit)", async () => {
    mockSearchTerms.mockResolvedValue(mockResults);
    const user = userEvent.setup();
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    await user.type(screen.getByPlaceholderText(/Search SNOMED terms/), "diab");
    await waitFor(() => {
      expect(screen.getByText("Diabetes mellitus")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Diabetes mellitus"));
    expect(mockOnSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        snomed_concept_id: "123456",
        term: "Diabetes mellitus",
      })
    );
    expect(mockOnClose).toHaveBeenCalled();
    expect(mockOnCorrection).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "reassign",
        text: "Diabetes mellitus",
      })
    );
  });

  it("shows Add code button when captureValueUnit is true", () => {
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
        captureValueUnit
        confirmLabel="Add code"
      />
    );
    expect(screen.getByRole("button", { name: "Add code" })).toBeInTheDocument();
  });

  it("shows No results when search returns empty", async () => {
    mockSearchTerms.mockResolvedValue([]);
    const user = userEvent.setup();
    render(
      <TermSearch
        onSelect={mockOnSelect}
        onClose={mockOnClose}
        onCorrection={mockOnCorrection}
      />
    );
    await user.type(screen.getByPlaceholderText(/Search SNOMED terms/), "xyz");
    await waitFor(() => {
      expect(screen.getByText("No results")).toBeInTheDocument();
    });
  });
});
