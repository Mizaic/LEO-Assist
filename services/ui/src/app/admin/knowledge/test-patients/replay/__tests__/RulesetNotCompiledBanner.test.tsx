/**
 * RulesetNotCompiledBanner -- VT-LEO-AI-175.
 *
 * Verifies the loud "no ruleset" banner that the test-patient panel
 * and replay dialog show whenever the bitmap evaluator returns zero
 * matches because nothing was compiled. Without this banner the user
 * cannot tell a missing-ruleset zero from a legitimate zero.
 *
 * Lives next to the moved component (central Test Patient library).
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import RulesetNotCompiledBanner from "../RulesetNotCompiledBanner";

afterEach(() => {
  jest.restoreAllMocks();
});

describe("RulesetNotCompiledBanner", () => {
  it("shows a one-click compile button for the production scope", async () => {
    const fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: "job-123", version: "v20260417" }),
      text: async () => "ok",
    } as Response);

    const onCompileRequested = jest.fn();
    render(
      <RulesetNotCompiledBanner
        scopeType="global"
        scopeId="default"
        onCompileRequested={onCompileRequested}
      />,
    );

    expect(
      screen.getByRole("status", { name: /no active bitmap ruleset/i }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /compile now/i }));

    await waitFor(() => expect(onCompileRequested).toHaveBeenCalledTimes(1));
    expect(onCompileRequested).toHaveBeenCalledWith({
      job_id: "job-123",
      version: "v20260417",
    });
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toMatch(/\/api\/terminology\/guidelines\/bitmap\/compile$/);
  });

  it("does not offer a compile button in the sandbox variant", () => {
    render(
      <RulesetNotCompiledBanner
        scopeType="custom"
        scopeId="draft-abc"
        sandbox
      />,
    );
    expect(
      screen.getByText(/draft sandbox could not be compiled/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /compile now/i }),
    ).not.toBeInTheDocument();
  });

  it("surfaces the compile error when the request fails", async () => {
    jest.spyOn(global, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
      text: async () => "boom",
    } as Response);

    render(<RulesetNotCompiledBanner />);

    fireEvent.click(screen.getByRole("button", { name: /compile now/i }));

    await waitFor(() => expect(screen.getByText(/boom/i)).toBeInTheDocument());
  });
});
