import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import ReviewView from "../ReviewView";
import { fetchTaskDetail } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  fetchTaskDetail: jest.fn(),
  fetchTasks: jest.fn(),
  submitDecision: jest.fn(),
  addCodedLink: jest.fn(),
}));

jest.mock("@/lib/nerAnnotation", () => ({
  themeForTag: () => "#ccc",
  tagFromSnomedTerm: () => "disorder",
  renderNerSpans: (text: string) => text,
}));

jest.mock("@/context/PipelineContext", () => ({
  usePipeline: () => ({
    running: false,
    status: null,
    live: null,
    result: null,
    error: null,
    workerStates: {},
    start: jest.fn(),
    cancel: jest.fn(),
  }),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    prefetch: jest.fn(),
  }),
}));

jest.mock("../CodedLinksSection", () => () => <div data-testid="coded-links" />);
jest.mock("../EntitySidebar", () => () => <div data-testid="entity-sidebar" />);
jest.mock("../EntityCard", () => () => null);
jest.mock("../TermSearch", () => () => null);
jest.mock("../ManualEntityBanner", () => () => null);
jest.mock("../CorrectionsLog", () => () => null);

const mockDetail = {
  task: {
    task_id: "T1",
    candidate_id: "C1",
    patient_id: "P1",
    encounter_id: "E1",
    priority: 2,
    status: "pending",
    warning_count: 0,
    created_at: "2024-01-01",
    updated_at: "2024-01-01",
  },
  candidate: {
    candidate_id: "C1",
    patient_id: "P1",
    encounter_id: "E1",
    date: "2024-01-01",
    source_hash: "h1",
    deidentified_hash: "h2",
    deidentified_text: "Patient has chest pain.",
    approval_status: "pending",
    hard_fail_reasons: [],
    warning_reasons: [],
    sentences: [
      {
        sentence_id: "S1",
        start: 0,
        end: 25,
        text: "Patient has chest pain.",
        terms: [
          {
            term_id: "T1",
            text: "chest pain",
            span_start: 16,
            span_end: 26,
            context: {
              negated: false,
              uncertain: false,
              historical: false,
              subject: "patient",
              temporality: "present",
            },
            coding: {
              snomed_concept_id: "29857009",
              snomed_term: "Chest pain",
              score: 0.95,
              read_code: "182..",
            },
            evidence_text: "chest pain",
            extraction_method: "llm",
            extraction_confidence: 0.92,
          },
        ],
      },
    ],
  },
};

describe("ReviewView", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows loading spinner with accessible label", async () => {
    (fetchTaskDetail as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<ReviewView taskId="T1" patientId="P1" />);
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("shows error alert when fetch fails", async () => {
    (fetchTaskDetail as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<ReviewView taskId="T1" patientId="P1" />);
    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("shows informative alert when no candidate data", async () => {
    (fetchTaskDetail as jest.Mock).mockResolvedValue({
      task: mockDetail.task,
      candidate: null,
    });
    render(<ReviewView taskId="T1" patientId="P1" />);
    await waitFor(() => {
      expect(screen.getByText(/No candidate data available/)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Return to encounters" })).toBeInTheDocument();
  });

  it("keyboard R opens ConfirmDialog for reject", async () => {
    (fetchTaskDetail as jest.Mock).mockResolvedValue(mockDetail);
    render(<ReviewView taskId="T1" patientId="P1" />);
    await waitFor(() => {
      expect(screen.getByText("Review: E1")).toBeInTheDocument();
    });
    fireEvent.keyDown(document.body, { key: "r" });
    expect(screen.getByText("Reject this encounter?")).toBeInTheDocument();
  });

  it("keyboard shortcut does not fire from input elements", async () => {
    (fetchTaskDetail as jest.Mock).mockResolvedValue(mockDetail);
    render(<ReviewView taskId="T1" patientId="P1" />);
    await waitFor(() => {
      expect(screen.getByText("Review: E1")).toBeInTheDocument();
    });
    const input = screen.getByPlaceholderText("Reason (required for Reject)");
    await act(async () => {
      input.focus();
    });
    fireEvent.keyDown(input, { key: "r" });
    expect(screen.queryByText("Reject this encounter?")).not.toBeInTheDocument();
  });

  it("keyboard shortcut does not fire from contentEditable", async () => {
    (fetchTaskDetail as jest.Mock).mockResolvedValue(mockDetail);
    render(<ReviewView taskId="T1" patientId="P1" />);
    await waitFor(() => {
      expect(screen.getByText("Review: E1")).toBeInTheDocument();
    });
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    document.body.appendChild(editable);
    editable.focus();
    Object.defineProperty(editable, "isContentEditable", { value: true, configurable: true });
    fireEvent.keyDown(editable, { key: "r" });
    expect(screen.queryByText("Reject this encounter?")).not.toBeInTheDocument();
    document.body.removeChild(editable);
  });

  it("keyboard shortcut does not fire from select", async () => {
    (fetchTaskDetail as jest.Mock).mockResolvedValue(mockDetail);
    render(<ReviewView taskId="T1" patientId="P1" />);
    await waitFor(() => {
      expect(screen.getByText("Review: E1")).toBeInTheDocument();
    });
    const select = document.createElement("select");
    document.body.appendChild(select);
    select.focus();
    fireEvent.keyDown(select, { key: "r" });
    expect(screen.queryByText("Reject this encounter?")).not.toBeInTheDocument();
    document.body.removeChild(select);
  });
});
