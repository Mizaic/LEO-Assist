/**
 * ReplayResultsDialog -- ISO 13485 / IEC 62304 plain-English copy.
 *
 * Pins the verification-report shape the QA reviewer signs off:
 *
 *   - Header with title + Live / Sandbox provenance chip
 *   - Verdict banner ("Passed" or "Failed -- N saved checks ...")
 *   - "What we tested" facts block (rules version, source, scope,
 *      patients, checks)
 *   - "Results, by patient" section with passed / failed chips
 *   - Audit footer with rules version and engine provenance
 *
 * All visible strings must avoid jargon (regression / drift /
 * bitmap / ruleset / fires / does not fire) per
 * .cursor/rules/health-literacy.mdc.
 */

import React from "react";
import { render, screen } from "@testing-library/react";

import ReplayResultsDialog, {
  PatientConfiguredEvidence,
  friendlyDescription,
} from "../ReplayResultsDialog";
import type {
  ReplayPatientSummary,
  ReplayReport,
} from "../../types";

const PATIENTS: ReplayPatientSummary[] = [
  {
    id: "tp_meso",
    name: "test_retired shipyard worker with persistent cough",
    description:
      "AI-scaffolded test patient for rule rule:NG12:v1:CH002:SEC000:R004 (Suspected cancer: recognition and referral)",
    age: 67,
    sex: "male",
    pathway_id: null,
    codes: ["49727002", "84229001"],
  },
];

function makeReport(overrides: Partial<ReplayReport> = {}): ReplayReport {
  return {
    id: "rep-1",
    ruleset_version: "v20260419-094210",
    scope_type: "global",
    scope_id: "default",
    guideline_id: "NG12",
    patient_count: 1,
    regressions_count: 0,
    passes_count: 1,
    drift_count: 0,
    results: [
      {
        patient_id: "tp_meso",
        patient_name: "test_retired shipyard worker with persistent cough",
        passes: [
          {
            rule_id: "rule:NG12:v1:CH002:SEC000:R004",
            fires: true,
            expected: true,
          },
        ],
        regressions: [],
        unexpected_matches: [],
        total_assertions: 1,
      },
    ],
    ...overrides,
  };
}

describe("ReplayResultsDialog -- ISO 13485 plain-English report", () => {
  test("title reads as a test report against the live rules", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="live"
      />,
    );

    expect(
      screen.getByText(/test report -- live rules/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/^Live$/)).toBeInTheDocument();
    expect(
      screen.getByText(/we checked your saved patients/i),
    ).toBeInTheDocument();
  });

  test("shows a green PASSED verdict banner when all checks match", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="live"
      />,
    );

    expect(screen.getByText(/^Passed$/)).toBeInTheDocument();
    expect(
      screen.getByText(/all 1 saved check matched the rules/i),
    ).toBeInTheDocument();
  });

  test("shows a red FAILED verdict banner with a plain-English count", () => {
    const report = makeReport({
      regressions_count: 1,
      passes_count: 0,
      results: [
        {
          patient_id: "tp_meso",
          patient_name: "test_retired shipyard worker with persistent cough",
          passes: [],
          regressions: [
            {
              rule_id: "rule:NG12:v1:CH002:SEC000:R004",
              fires: false,
              expected: true,
            },
          ],
          unexpected_matches: [],
          total_assertions: 1,
        },
      ],
    });

    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={report}
        patients={PATIENTS}
        mode="live"
      />,
    );

    expect(
      screen.getByText(/failed -- 1 saved check no longer match the rules/i),
    ).toBeInTheDocument();
  });

  test("renders the 'What we tested' configuration block", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="live"
      />,
    );

    expect(screen.getByText("What we tested")).toBeInTheDocument();
    expect(screen.getByText("Source of rules")).toBeInTheDocument();
    expect(screen.getByText("Live in production")).toBeInTheDocument();
    expect(screen.getByText("Rules version")).toBeInTheDocument();
    // The version is shown twice on purpose: once in the "What we
    // tested" facts block (for at-a-glance scanning) and once in the
    // audit footer (for sign-off provenance). Both are required by
    // the ISO 13485 report layout.
    expect(screen.getAllByText("v20260419-094210").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Patients tested")).toBeInTheDocument();
    expect(screen.getByText("Checks made")).toBeInTheDocument();
    expect(screen.getByText("Scope")).toBeInTheDocument();
    expect(screen.getByText("global / default")).toBeInTheDocument();
  });

  test("count chips read as 'failed / passed / changed since saved'", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="live"
      />,
    );

    // Per-row chips and the report-level chips both render the same
    // counts -- one in the "What we tested" block and one on the
    // patient row -- so we accept multiple instances.
    expect(screen.getAllByText(/^0 failed$/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/^1 passed$/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/^0 changed since saved$/).length).toBe(1);
  });

  test("results section uses 'Results, by patient' heading", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="live"
      />,
    );

    expect(screen.getByText(/results, by patient/i)).toBeInTheDocument();
  });

  test("shows the saved patient setup with note text and coded concepts", () => {
    render(
      <PatientConfiguredEvidence
        loading={false}
        patient={{
          id: "tp_meso",
          name: "test_retired shipyard worker with persistent cough",
          description: "AI-scaffolded test patient",
          aspect: "summarisation",
          is_test: true,
          source_patient_id: null,
          age: 67,
          sex: "male",
          pathway_id: null,
          generation_source: "ai",
          guideline_id: "NG12",
          guideline_title: "Suspected cancer",
          created_at: null,
          updated_at: null,
          created_by: null,
          updated_by: null,
          expected_sbar: null,
          encounters: [
            {
              id: "enc-1",
              source_label: "GP note",
              source_id: null,
              date: "2026-05-22",
              text: "Persistent cough and finger clubbing.",
              codes: [
                {
                  concept_id: "84229001",
                  term: "Fatigue",
                  assertion: "present",
                },
              ],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Saved patient setup")).toBeInTheDocument();
    expect(screen.getByText(/Persistent cough and finger clubbing/i)).toBeInTheDocument();
    expect(screen.getByText(/Fatigue \(present\)/i)).toBeInTheDocument();
  });

  test("labels uncoded follow-up notes without warning the whole patient", () => {
    render(
      <PatientConfiguredEvidence
        loading={false}
        patient={{
          id: "tp_meso",
          name: "test_retired shipyard worker with persistent cough",
          description: "AI-scaffolded test patient",
          aspect: "summarisation",
          is_test: true,
          source_patient_id: null,
          age: 67,
          sex: "male",
          pathway_id: null,
          generation_source: "ai",
          guideline_id: "NG12",
          guideline_title: "Suspected cancer",
          created_at: null,
          updated_at: null,
          created_by: null,
          updated_by: null,
          expected_sbar: null,
          encounters: [
            {
              id: "enc-1",
              source_label: "GP note",
              source_id: null,
              date: "2026-05-22",
              text: "Persistent cough.",
              codes: [
                {
                  concept_id: "49727002",
                  term: "Cough",
                  assertion: "present",
                },
              ],
            },
            {
              id: "enc-2",
              source_label: "Follow-up",
              source_id: null,
              date: "2026-05-23",
              text: "FIT kit provided.",
              codes: [],
            },
          ],
        }}
      />,
    );

    expect(
      screen.getByText(/No coded findings attached to this note/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/No SNOMED codes saved for this patient setup/i),
    ).not.toBeInTheDocument();
  });

  test("warns when a saved scenario has no SNOMED codes", () => {
    render(
      <PatientConfiguredEvidence
        loading={false}
        patient={{
          id: "tp_meso",
          name: "test_retired shipyard worker with persistent cough",
          description: "AI-scaffolded test patient",
          aspect: "summarisation",
          is_test: true,
          source_patient_id: null,
          age: 67,
          sex: "male",
          pathway_id: null,
          generation_source: "ai",
          guideline_id: "NG12",
          guideline_title: "Suspected cancer",
          created_at: null,
          updated_at: null,
          created_by: null,
          updated_by: null,
          expected_sbar: null,
          encounters: [
            {
              id: "enc-1",
              source_label: "GP note",
              source_id: null,
              date: "2026-05-22",
              text: "Persistent cough but no coded concept.",
              codes: [],
            },
          ],
        }}
      />,
    );

    expect(
      screen.getByText(/No SNOMED codes saved for this patient setup/i),
    ).toBeInTheDocument();
  });

  test("audit footer cites the rules version and engine provenance", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="live"
      />,
    );

    expect(
      screen.getByText(
        /this test was run by the same rule engine that decides real referrals/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/rules version:/i)).toBeInTheDocument();
  });

  test("avoids jargon in patient-facing copy (regression / drift / bitmap / ruleset / fires)", () => {
    const { container } = render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="live"
      />,
    );

    // textContent walks every visible node, so this catches stray
    // jargon anywhere in the dialog body. We do NOT scan attributes
    // (aria-label, data-testid) so internal accessibility
    // descriptions can keep the technical term where useful.
    const visible = container.textContent || "";
    expect(visible).not.toMatch(/regression/i);
    expect(visible).not.toMatch(/\bdrift\b/i);
    expect(visible).not.toMatch(/bitmap/i);
    expect(visible).not.toMatch(/ruleset/i);
    expect(visible).not.toMatch(/\bfires\b/i);
    expect(visible).not.toMatch(/does not fire/i);
  });

  describe("friendlyDescription helper", () => {
    const RAW_RULE_ID =
      "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13:edit:dd11e8d3:edit:a0b74f59";
    const STEM = "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13";
    const SAVED_DESCRIPTION = `AI-scaffolded test patient for rule ${RAW_RULE_ID} (Suspected cancer: recognition and referral)`;

    test("substitutes a curated rule name when the rules lookup has one", () => {
      const out = friendlyDescription(SAVED_DESCRIPTION, {
        [RAW_RULE_ID]: { name: "Suspected mesothelioma -- urgent X-ray" },
      });
      expect(out).toBe(
        'AI-scaffolded test patient for "Suspected mesothelioma -- urgent X-ray" (Suspected cancer: recognition and referral)',
      );
      expect(out).not.toContain(RAW_RULE_ID);
    });

    test("falls back to the recommendation text when no curated name", () => {
      const out = friendlyDescription(SAVED_DESCRIPTION, {
        [RAW_RULE_ID]: {
          recommendation_text:
            "Offer an urgent chest X-ray to assess for mesothelioma:",
        },
      });
      expect(out).toContain(
        '"Offer an urgent chest X-ray to assess for mesothelioma"',
      );
      expect(out).not.toContain(RAW_RULE_ID);
    });

    test("matches by stem when the lookup only has the pre-edit id", () => {
      const out = friendlyDescription(SAVED_DESCRIPTION, {
        [STEM]: { name: "Suspected mesothelioma" },
      });
      expect(out).toContain(
        'AI-scaffolded test patient for "Suspected mesothelioma"',
      );
      expect(out).not.toContain(RAW_RULE_ID);
    });

    test("matches by stem when the lookup only has another edited descendant", () => {
      const SIBLING_EDIT = `${STEM}:edit:11111111`;
      const out = friendlyDescription(SAVED_DESCRIPTION, {
        [SIBLING_EDIT]: { name: "Suspected mesothelioma" },
      });
      expect(out).toContain('"Suspected mesothelioma"');
      expect(out).not.toContain(RAW_RULE_ID);
    });

    test("strips the raw id even when no rules lookup is provided", () => {
      const out = friendlyDescription(SAVED_DESCRIPTION);
      expect(out).toBe(
        "AI-scaffolded test patient for the rule (Suspected cancer: recognition and referral)",
      );
      expect(out).not.toContain(RAW_RULE_ID);
    });

    test("leaves descriptions with no rule id untouched", () => {
      const plain =
        "Patient cloned from a real one for the SBAR golden set.";
      expect(friendlyDescription(plain, {})).toBe(plain);
    });

    test("truncates very long recommendation text", () => {
      const longRec = "A".repeat(300);
      const out = friendlyDescription(SAVED_DESCRIPTION, {
        [RAW_RULE_ID]: { recommendation_text: longRec },
      });
      expect(out).toMatch(/\.\.\.\"/);
    });
  });

  test("sandbox mode keeps the 'unsaved draft' provenance line", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => {}}
        report={makeReport()}
        patients={PATIENTS}
        mode="sandbox"
      />,
    );

    expect(
      screen.getByText(/test report -- unsaved draft/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/^Sandbox$/)).toBeInTheDocument();
    expect(screen.getByText(/Throwaway draft \(sandbox\)/i)).toBeInTheDocument();
  });
});
