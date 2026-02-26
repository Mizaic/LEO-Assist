import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ManualEntityBanner from "../ManualEntityBanner";

describe("ManualEntityBanner", () => {
  const defaults = {
    fullText: "Patient reports chest pain and shortness of breath",
    onAdd: jest.fn(),
    onCancel: jest.fn(),
    onCorrection: jest.fn(),
  };

  it("renders text input and buttons", () => {
    render(<ManualEntityBanner {...defaults} />);
    expect(screen.getByPlaceholderText(/Type text to match/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("Add button is disabled when no match", () => {
    render(<ManualEntityBanner {...defaults} />);
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  });

  it("shows match position when text is found", async () => {
    const user = userEvent.setup();
    render(<ManualEntityBanner {...defaults} />);
    await user.type(screen.getByPlaceholderText(/Type text to match/), "chest pain");
    expect(screen.getByText(/Found at/)).toBeInTheDocument();
  });

  it("shows 'Not found' when text does not match", async () => {
    const user = userEvent.setup();
    render(<ManualEntityBanner {...defaults} />);
    await user.type(screen.getByPlaceholderText(/Type text to match/), "xyz123");
    expect(screen.getByText("Not found in text")).toBeInTheDocument();
  });

  it("calls onAdd with match span when Add is clicked", async () => {
    const user = userEvent.setup();
    render(<ManualEntityBanner {...defaults} />);
    await user.type(screen.getByPlaceholderText(/Type text to match/), "chest pain");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(defaults.onAdd).toHaveBeenCalledWith("chest pain", 16, 26);
  });

  it("calls onCancel when Cancel is clicked", async () => {
    const user = userEvent.setup();
    render(<ManualEntityBanner {...defaults} />);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(defaults.onCancel).toHaveBeenCalledTimes(1);
  });
});
