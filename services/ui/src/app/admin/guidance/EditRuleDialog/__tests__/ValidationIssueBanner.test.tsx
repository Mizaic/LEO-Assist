/**
 * Live-render tests for ValidationIssueBanner -- the "jump to issue"
 * replacement for the old single generic tree-warning Alert.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ValidationIssueBanner from "../ValidationIssueBanner";
import type { ValidationIssue } from "../treeOps";

describe("ValidationIssueBanner", () => {
  it("renders nothing when there are no issues", () => {
    const { container } = render(<ValidationIssueBanner issues={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a singular headline for exactly one issue", () => {
    const issues: ValidationIssue[] = [{ nodeId: "n1", message: "Add at least one condition." }];
    render(<ValidationIssueBanner issues={issues} />);
    expect(screen.getByText("We found 1 problem.")).toBeInTheDocument();
  });

  it("shows a plural headline and lists every issue's own message for 2+ issues", () => {
    const issues: ValidationIssue[] = [
      { nodeId: "n1", message: "Add at least one condition." },
      { nodeId: "n2", message: "This group has no conditions yet." },
    ];
    render(<ValidationIssueBanner issues={issues} />);
    expect(screen.getByText("We found 2 problems.")).toBeInTheDocument();
    expect(screen.getByText("Add at least one condition.")).toBeInTheDocument();
    expect(screen.getByText("This group has no conditions yet.")).toBeInTheDocument();
  });

  it("calls onJumpToIssue with the issue's own nodeId when its button is clicked", async () => {
    const user = userEvent.setup();
    const onJumpToIssue = jest.fn();
    const issues: ValidationIssue[] = [
      { nodeId: "n1", message: "First problem." },
      { nodeId: "n2", message: "Second problem." },
    ];
    render(<ValidationIssueBanner issues={issues} onJumpToIssue={onJumpToIssue} />);

    const buttons = screen.getAllByRole("button", { name: /take me there/i });
    expect(buttons).toHaveLength(2);
    await user.click(buttons[1]);

    expect(onJumpToIssue).toHaveBeenCalledWith("n2");
  });

  it("omits the jump button for an issue with no nodeId (e.g. a wholly empty tree)", () => {
    const onJumpToIssue = jest.fn();
    const issues: ValidationIssue[] = [
      { nodeId: null, message: "This rule needs at least one condition." },
    ];
    render(<ValidationIssueBanner issues={issues} onJumpToIssue={onJumpToIssue} />);

    expect(screen.getByText("This rule needs at least one condition.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /take me there/i })).not.toBeInTheDocument();
  });

  it("omits every jump button when no onJumpToIssue handler is supplied", () => {
    const issues: ValidationIssue[] = [{ nodeId: "n1", message: "First problem." }];
    render(<ValidationIssueBanner issues={issues} />);

    expect(screen.queryByRole("button", { name: /take me there/i })).not.toBeInTheDocument();
  });
});
