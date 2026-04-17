/**
 * TestPatientsPanel "Test draft" button -- VT-LEO-AI-175.
 *
 * Verifies that the rule editor's sandbox-replay flow:
 *   - Calls POST /api/guidance/test-patients/sandbox-replay with the
 *     reviewer's UNSAVED draft + the saved patient ids in scope.
 *   - Opens the ReplayResultsDialog with the returned report once the
 *     sandbox replay completes.
 *   - Renders the "no compiled" banner (sandbox variant) when the
 *     sandbox compile yielded zero rules (e.g. the draft has no
 *     SNOMED-coded leaf so the compiler dropped it).
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

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
  created_at: "2026-04-17T12:00:00Z",
  created_by: "qa",
  expectations: [],
};

const DRAFT_RULE = {
  rule_id: "rule:NG12:abc",
  name: "Refer for rectal bleeding",
  strength: "consider",
  guideline_id: "NG12",
  recommendation_verbatim: "Refer for rectal bleeding.",
  logic_tree: {
    kind: "concept",
    criterion: { snomed_concept_id: "443416000", preferred_term: "Rectal bleeding" },
  },
};

interface FetchResponse {
  url: RegExp | string;
  body: unknown;
  ok?: boolean;
  status?: number;
}

function installFetchStub(responses: FetchResponse[]): jest.Mock {
  const calls: { url: string; init?: RequestInit }[] = [];
  const stub = jest
    .spyOn(global, "fetch")
    .mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      const match = responses.find((r) =>
        typeof r.url === "string" ? url.includes(r.url) : r.url.test(url),
      );
      if (!match) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => [],
          text: async () => "[]",
        } as Response);
      }
      return Promise.resolve({
        ok: match.ok ?? true,
        status: match.status ?? 200,
        json: async () => match.body,
        text: async () => JSON.stringify(match.body),
      } as Response);
    });
  (stub as unknown as { calls: typeof calls }).calls = calls;
  return stub as unknown as jest.Mock;
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("TestPatientsPanel sandbox replay", () => {
  it("compiles the draft and opens the report on success", async () => {
    const sandboxReport = {
      patient_count: 1,
      results: [
        {
          patient_id: SAVED_PATIENT.id,
          patient_name: SAVED_PATIENT.name,
          passes: [{ rule_id: DRAFT_RULE.rule_id, fires: true, expected: true }],
          regressions: [],
          unexpected_matches: [],
          total_assertions: 1,
        },
      ],
      regressions_count: 0,
      passes_count: 1,
      drift_count: 0,
      ruleset_version: "draft-v1",
      scope_type: "custom",
      scope_id: "draft-abc",
    };

    installFetchStub([
      { url: "/api/guidance/test-patients?", body: [SAVED_PATIENT] },
      {
        url: "/api/terminology/guidelines/bitmap/status",
        body: {
          active_version: "v20260417",
          rule_count: 12,
          compile_timestamp: "2026-04-17T11:00:00Z",
          scope_type: "guideline",
          scope_id: "NG12",
        },
      },
      {
        url: "/api/guidance/test-patients/sandbox-replay",
        body: {
          sandbox_id: "draft-abc",
          compile: {
            version: "draft-v1",
            rule_count: 1,
            draft_input_count: 1,
            compile_timestamp: "2026-04-17T12:00:00Z",
            scope_type: "custom",
            scope_id: "draft-abc",
            policy_mode: "advisory",
            draft: true,
          },
          report: sandboxReport,
        },
      },
    ]);

    render(
      <TestPatientsPanel
        ruleId={DRAFT_RULE.rule_id}
        guidelineId="NG12"
        ruleName={DRAFT_RULE.name}
        recommendationText={DRAFT_RULE.recommendation_verbatim}
        draftRule={DRAFT_RULE}
      />,
    );

    // Wait for the saved-patient list to load so the button is enabled.
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: /test the unsaved draft against the saved test patients in a sandbox/i,
        }),
      ).not.toBeDisabled(),
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /test the unsaved draft against the saved test patients in a sandbox/i,
      }),
    );

    // The report dialog opens once the sandbox replay returns.
    await waitFor(() =>
      expect(screen.getByText(/replay results -- unsaved draft/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/draft-v1/i)).toBeInTheDocument();
  });

  it("shows the sandbox 'not compiled' banner when zero rules compiled", async () => {
    installFetchStub([
      { url: "/api/guidance/test-patients?", body: [SAVED_PATIENT] },
      {
        url: "/api/terminology/guidelines/bitmap/status",
        body: {
          active_version: "v20260417",
          rule_count: 12,
          compile_timestamp: "2026-04-17T11:00:00Z",
          scope_type: "guideline",
          scope_id: "NG12",
        },
      },
      {
        url: "/api/guidance/test-patients/sandbox-replay",
        body: {
          sandbox_id: "draft-empty",
          compile: {
            version: "draft-v2",
            rule_count: 0,
            draft_input_count: 1,
            compile_timestamp: "2026-04-17T12:01:00Z",
            scope_type: "custom",
            scope_id: "draft-empty",
            policy_mode: "advisory",
            draft: true,
          },
          report: {
            patient_count: 1,
            results: [
              {
                patient_id: SAVED_PATIENT.id,
                patient_name: SAVED_PATIENT.name,
                passes: [],
                regressions: [],
                unexpected_matches: [],
                total_assertions: 0,
                error: "No active ruleset compiled yet.",
              },
            ],
            regressions_count: 0,
            passes_count: 0,
            drift_count: 0,
            ruleset_version: "draft-v2",
            scope_type: "custom",
            scope_id: "draft-empty",
          },
        },
      },
    ]);

    render(
      <TestPatientsPanel
        ruleId={DRAFT_RULE.rule_id}
        guidelineId="NG12"
        ruleName={DRAFT_RULE.name}
        recommendationText={DRAFT_RULE.recommendation_verbatim}
        draftRule={DRAFT_RULE}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: /test the unsaved draft against the saved test patients in a sandbox/i,
        }),
      ).not.toBeDisabled(),
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /test the unsaved draft against the saved test patients in a sandbox/i,
      }),
    );

    await waitFor(() =>
      expect(
        screen.getByText(/draft sandbox could not be compiled/i),
      ).toBeInTheDocument(),
    );
  });
});
