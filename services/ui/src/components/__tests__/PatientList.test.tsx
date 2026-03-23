import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PatientList from "../PatientList";

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => "/care/patients",
  useParams: () => ({}),
}));

jest.mock("@/lib/api", () => ({
  fetchPatients: jest.fn(),
}));

import { fetchPatients } from "@/lib/api";

const patients = [
  { patient_id: "P001", encounter_count: 10, reviewed_count: 5, progress: 0.5 },
  { patient_id: "P002", encounter_count: 8, reviewed_count: 8, progress: 1.0 },
  { patient_id: "P003", encounter_count: 3, reviewed_count: 0, progress: 0 },
];

describe("PatientList", () => {
  beforeEach(() => {
    mockPush.mockClear();
    (fetchPatients as jest.Mock).mockResolvedValue(patients);
  });

  it("renders patient cards after loading", async () => {
    render(<PatientList />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    expect(screen.getByText("P002")).toBeInTheDocument();
    expect(screen.getByText("P003")).toBeInTheDocument();
  });

  it("shows encounter count for each patient", async () => {
    render(<PatientList />);
    await waitFor(() => {
      expect(screen.getByText("10 encounters")).toBeInTheDocument();
    });
    expect(screen.getByText("8 encounters")).toBeInTheDocument();
  });

  it("filters patients by search query", async () => {
    const user = userEvent.setup();
    render(<PatientList />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    await user.type(screen.getByPlaceholderText(/Search by patient ID/), "P001");
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.queryByText("P002")).not.toBeInTheDocument();
    expect(screen.queryByText("P003")).not.toBeInTheDocument();
  });

  it("shows error message on fetch failure", async () => {
    (fetchPatients as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<PatientList />);
    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("navigates to patient on card click", async () => {
    const user = userEvent.setup();
    render(<PatientList />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    await user.click(screen.getByText("P001"));
    expect(mockPush).toHaveBeenCalledWith("/care/patients/P001");
  });

  it("shows patient count", async () => {
    render(<PatientList />);
    await waitFor(() => {
      expect(screen.getByText(/Showing 3 of 3 patients/)).toBeInTheDocument();
    });
  });

  it("shows filtered count when searching", async () => {
    const user = userEvent.setup();
    render(<PatientList />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    await user.type(screen.getByPlaceholderText(/Search by patient ID/), "P00");
    expect(screen.getByText(/Showing 3 of 3 patients/)).toBeInTheDocument();
  });
});
