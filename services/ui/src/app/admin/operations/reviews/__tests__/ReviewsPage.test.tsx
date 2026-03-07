import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import OperationsReviewsPage from "../page";

jest.mock("@/components/operations/ReviewSection", () => {
  return function MockReviewSection() {
    return <div data-testid="review-section">review-section</div>;
  };
});

describe("Operations reviews page", () => {
  beforeEach(() => {
    jest.spyOn(global, "fetch").mockImplementation((url, init) => {
      if (typeof url === "string" && url.includes("/api/training/coding-review/resolved") && init?.method === "DELETE") {
        return Promise.resolve({ ok: true, json: async () => ({ deleted: 4 }) } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders review section and clears resolved queue", async () => {
    render(<OperationsReviewsPage />);
    expect(screen.getByTestId("review-section")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Clear resolved/i }));
    await waitFor(() => expect(screen.getByText(/Cleared 4 resolved review items./)).toBeInTheDocument());
  });
});

