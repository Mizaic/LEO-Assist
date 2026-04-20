/**
 * TestPatientsPanel sandbox-only safety pin -- VT-D7B8FBA9 (Atlas).
 *
 * Phase 1 removed the "Test against live" surface from the rule
 * editor entirely. The previous test ensured the live-bitmap status
 * probe used scope_type=global rather than scope_type=guideline so
 * that reviewers did not see a false "no compiled ruleset" warning.
 * That probe was deleted along with the live-replay path -- the
 * editor now has no business asking the live bitmap anything,
 * because every test the editor offers is a throwaway sandbox.
 *
 * This pin guards against accidental regressions: if anybody
 * re-introduces a live-bitmap call from inside the rule editor we
 * want CI to fail loudly rather than ship a misleading "Live
 * results" panel that actually shows the OLD rule.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";

import TestPatientsPanel from "../TestPatientsPanel";

const SAVED_PATIENT = {
  id: "tp-1",
  name: "55F with rectal bleeding",
  description: "",
  codes: ["443416000"],
  age: 55,
  sex: "female",
  pathway_id: null,
  scope_type: "guideline",
  scope_id: "NG12",
  generation_source: "manual",
  content_hash: "abc",
  guideline_id: "NG12",
  guideline_title: "Suspected cancer",
  created_at: "2026-04-19T12:00:00Z",
  created_by: "qa",
  expectations: [],
};

interface FetchCall {
  url: string;
  init?: RequestInit;
}

function installFetchStub(): { calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  jest
    .spyOn(global, "fetch")
    .mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.includes("/api/guidance/test-patients?")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => [SAVED_PATIENT],
          text: async () => JSON.stringify([SAVED_PATIENT]),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => [],
        text: async () => "[]",
      } as Response);
    });
  return { calls };
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("TestPatientsPanel never touches the live ruleset", () => {
  it("does not call the bitmap status endpoint on mount", async () => {
    const { calls } = installFetchStub();

    render(
      <TestPatientsPanel
        ruleId="rule:NG12:abc"
        guidelineId="NG12"
        ruleName="Refer for rectal bleeding"
      />,
    );

    await waitFor(() =>
      expect(screen.getByText(/1 saved/i)).toBeInTheDocument(),
    );

    const statusCalls = calls.filter((c) =>
      c.url.includes("/api/terminology/guidelines/bitmap/status"),
    );
    expect(statusCalls).toHaveLength(0);
  });

  it("does not call the live replay endpoint on mount", async () => {
    const { calls } = installFetchStub();

    render(
      <TestPatientsPanel
        ruleId="rule:NG12:abc"
        guidelineId="NG12"
        ruleName="Refer for rectal bleeding"
      />,
    );

    await waitFor(() =>
      expect(screen.getByText(/1 saved/i)).toBeInTheDocument(),
    );

    const liveReplayCalls = calls.filter(
      (c) =>
        c.url.includes("/api/guidance/test-patients/replay") &&
        !c.url.includes("/sandbox-replay"),
    );
    expect(liveReplayCalls).toHaveLength(0);
  });

  it("does not render a 'Test against live' button", async () => {
    installFetchStub();

    render(
      <TestPatientsPanel
        ruleId="rule:NG12:abc"
        guidelineId="NG12"
        ruleName="Refer for rectal bleeding"
      />,
    );

    await waitFor(() =>
      expect(screen.getByText(/1 saved/i)).toBeInTheDocument(),
    );

    expect(
      screen.queryByRole("button", { name: /test against live/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /test the saved rule against the production ruleset/i,
      }),
    ).not.toBeInTheDocument();
  });
});
