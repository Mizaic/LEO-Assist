import React from "react";
import { render, screen } from "@testing-library/react";
import AdminOperationsPage from "../page";

jest.mock("@/components/operations/OperationsWorkspace", () => ({
  __esModule: true,
  default: ({ initialTab }: { initialTab: string }) => (
    <div data-testid="operations-workspace" data-tab={initialTab}>
      Operations Workspace
    </div>
  ),
}));

describe("Operations dashboard", () => {
  it("renders the operations workspace with review as the initial tab", () => {
    render(<AdminOperationsPage />);
    const workspace = screen.getByTestId("operations-workspace");
    expect(workspace).toBeInTheDocument();
    expect(workspace).toHaveAttribute("data-tab", "review");
  });
});
