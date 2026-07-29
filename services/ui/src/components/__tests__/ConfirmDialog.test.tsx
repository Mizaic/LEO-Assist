import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConfirmDialog from "../ConfirmDialog";

describe("ConfirmDialog", () => {
  const defaults = {
    title: "Delete patient?",
    body: "This action cannot be undone.",
    confirmLabel: "Delete",
    onConfirm: jest.fn(),
    onCancel: jest.fn(),
  };

  it("renders title, body, and buttons", () => {
    render(<ConfirmDialog {...defaults} />);
    expect(screen.getByText("Delete patient?")).toBeInTheDocument();
    expect(screen.getByText("This action cannot be undone.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("calls onConfirm when confirm button is clicked", async () => {
    const user = userEvent.setup();
    render(<ConfirmDialog {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(defaults.onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when cancel button is clicked", async () => {
    const user = userEvent.setup();
    render(<ConfirmDialog {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(defaults.onCancel).toHaveBeenCalledTimes(1);
  });

  it("uses custom cancel label", () => {
    render(<ConfirmDialog {...defaults} cancelLabel="Go back" />);
    expect(screen.getByRole("button", { name: "Go back" })).toBeInTheDocument();
  });

  it("applies danger variant to confirm button", () => {
    render(<ConfirmDialog {...defaults} variant="danger" />);
    const btn = screen.getByRole("button", { name: "Delete" });
    expect(btn.className.toLowerCase()).toContain("error");
  });

  it("shows busy feedback and disables actions while in progress", () => {
    const onConfirm = jest.fn();
    const onCancel = jest.fn();
    render(
      <ConfirmDialog
        {...defaults}
        busy
        busyLabel="Going live..."
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole("button", { name: /Going live/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });
});
