/**
 * TestPatientsPanel scope regression -- VT-LEO-AI-175.
 *
 * Pins the fix for the "No bitmap ruleset is loaded" false positive
 * that fired in the EditRuleDialog whenever a per-guideline rule (e.g.
 * NG12) was opened. Production bitmaps live at scope_type=global /
 * scope_id=default; per-guideline scopes are reserved for sandbox /
 * draft compiles. The panel must therefore probe the global scope
 * regardless of which guideline the rule belongs to, otherwise
 * reviewers see a loud warning that the ruleset is missing when in
 * fact the production bitmap is fully loaded.
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
      if (url.includes("/api/terminology/guidelines/bitmap/status")) {
        // The global production bitmap IS compiled. The per-guideline
        // scope is empty -- but the panel must never ask for that
        // scope, so this branch is unreachable in the happy path.
        const isGlobal = url.includes("scope_type=global");
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () =>
            isGlobal
              ? {
                  active_version: "v20260419",
                  rule_count: 42,
                  compile_timestamp: "2026-04-19T11:00:00Z",
                  scope_type: "global",
                  scope_id: "default",
                }
              : {
                  active_version: null,
                  rule_count: 0,
                  compile_timestamp: null,
                  scope_type: "guideline",
                  scope_id: "NG12",
                  message: "No active ruleset.",
                },
          text: async () => "",
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

describe("TestPatientsPanel bitmap-status scope", () => {
  it("VT-175-TC-007: probes the global scope even when a guidelineId is supplied", async () => {
    const { calls } = installFetchStub();

    render(
      <TestPatientsPanel
        ruleId="rule:NG12:abc"
        guidelineId="NG12"
        ruleName="Refer for rectal bleeding"
      />,
    );

    // Wait for the saved-patient list to load so the status check has
    // certainly fired.
    await waitFor(() =>
      expect(screen.getByText(/1 saved/i)).toBeInTheDocument(),
    );

    const statusCalls = calls.filter((c) =>
      c.url.includes("/api/terminology/guidelines/bitmap/status"),
    );
    expect(statusCalls.length).toBeGreaterThan(0);
    for (const call of statusCalls) {
      expect(call.url).toContain("scope_type=global");
      expect(call.url).toContain("scope_id=default");
      expect(call.url).not.toContain("scope_type=guideline");
      expect(call.url).not.toContain("scope_id=NG12");
    }

    expect(
      screen.queryByText(/no bitmap ruleset is loaded/i),
    ).not.toBeInTheDocument();
  });
});
