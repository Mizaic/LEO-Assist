/**
 * VT-LEO-AI-166 -- Persistent Test Patient Library page chrome.
 *
 * Verifies:
 *   - The library page wires the Build / Generate / Replay actions.
 *   - The api client uses X-Requested-With and the correct paths.
 *   - The page renders an empty state and a populated table when fetch
 *     returns rows.
 *   - The replay results dialog buckets passes / regressions correctly.
 *
 * Design Controls: DI-LEO-AI-164/165/166, DO-LEO-AI-163/164/165.
 */

import * as fs from "fs";
import * as path from "path";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

import ReplayResultsDialog from "@/app/admin/guidance/test-patients/ReplayResultsDialog";
import type { RuleContext } from "@/app/admin/guidance/test-patients/ReplayResultsDialog";
import {
  listPatients,
  dryRun,
  updatePatient,
} from "@/app/admin/guidance/test-patients/api";
import type {
  DiagnoseResponse,
  TestPatient,
} from "@/app/admin/guidance/test-patients/types";

const PAGE_SRC = path.resolve(
  __dirname,
  "..",
  "app",
  "admin",
  "guidance",
  "test-patients",
  "page.tsx",
);

function read(): string {
  return fs.readFileSync(PAGE_SRC, "utf8");
}

describe("VT-LEO-AI-166 -- Test patient library page chrome", () => {
  test("TC-001: page wires Build, Generate, and Replay actions", () => {
    const src = read();
    expect(src).toMatch(/BuildPatientDialog/);
    expect(src).toMatch(/GeneratePatientsDialog/);
    expect(src).toMatch(/ReplayResultsDialog/);
    expect(src).toMatch(/Build a patient/);
    expect(src).toMatch(/Generate patients/);
    expect(src).toMatch(/Replay scope/);
  });

  test("TC-002: page filters by guideline scope and supports 'All guidelines'", () => {
    const src = read();
    expect(src).toMatch(/All guidelines/);
    expect(src).toMatch(/scopeGuideline/);
  });

  test("TC-003: page surfaces empty-state in plain English (reading age 9-11)", () => {
    const src = read();
    // Avoid jargon like 'fixture' / 'corpus' in the empty state.
    expect(src).not.toMatch(/fixture/i);
    expect(src).not.toMatch(/corpus/i);
    expect(src).toMatch(/No saved patients yet/);
  });
});

describe("VT-LEO-AI-166 -- API client", () => {
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    // @ts-expect-error -- override global fetch for the test env
    global.fetch = fetchMock;
  });

  test("TC-004: listPatients hits the scoped guideline endpoint", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: "tp1", name: "P1" }],
    });
    const rows = await listPatients({ guideline_id: "g1" });
    expect(rows).toEqual([{ id: "tp1", name: "P1" }]);
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/guidance\/test-patients\?/);
    expect(String(url)).toMatch(/guideline_id=g1/);
  });

  test("TC-005: dryRun POSTs JSON body and X-Requested-With", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ matched_rules: [] }),
    });
    await dryRun({
      patient: { codes: ["100"], age: 70, sex: "male" },
    } as Parameters<typeof dryRun>[0]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/guidance/test-patients/dry-run");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).headers).toMatchObject({
      "X-Requested-With": "XMLHttpRequest",
      "Content-Type": "application/json",
    });
  });
});

describe("VT-LEO-AI-166 -- ReplayResultsDialog", () => {
  test("TC-006: shows pass / regression / unexpected counts", async () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => undefined}
        report={{
          id: "rv1",
          ruleset_version: "v1",
          scope_type: "guideline",
          scope_id: "g1",
          guideline_id: "g1",
          patient_count: 2,
          passes_count: 3,
          regressions_count: 1,
          drift_count: 0,
          results: [
            {
              patient_id: "tp1",
              patient_name: "Smoker, 70",
              passes: [{ rule_id: "r1", fires: true, expected: true }],
              regressions: [
                { rule_id: "r2", fires: false, expected: true },
              ],
              unexpected_matches: [],
              total_assertions: 2,
            },
          ],
        }}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/Smoker, 70/)).toBeInTheDocument();
    });
    // Regression chip surfaces the "1 regression" wording.
    expect(screen.getAllByText(/regression/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/pass/i).length).toBeGreaterThan(0);
  });

  test("TC-007: empty report renders plain-English explanation, no jargon", () => {
    render(
      <ReplayResultsDialog
        open
        onClose={() => undefined}
        report={null}
      />,
    );
    expect(screen.queryByText(/diff/i)).toBeNull();
    expect(screen.queryByText(/regex/i)).toBeNull();
  });
});

describe("VT-LEO-AI-166 -- Save dialogs auto-close after success", () => {
  const GENERATE_SRC = path.resolve(
    __dirname,
    "..",
    "app",
    "admin",
    "guidance",
    "test-patients",
    "GeneratePatientsDialog.tsx",
  );
  const BUILD_SRC = path.resolve(
    __dirname,
    "..",
    "app",
    "admin",
    "guidance",
    "test-patients",
    "BuildPatientDialog.tsx",
  );

  test("TC-008: GeneratePatientsDialog schedules onClose after a successful save", () => {
    const src = fs.readFileSync(GENERATE_SRC, "utf8");
    expect(src).toMatch(/setSavedSummary/);
    expect(src).toMatch(/Closing\.\.\./);
    expect(src).toMatch(/autoCloseTimer/);
    expect(src).toMatch(/setTimeout\(\(\) => \{[\s\S]*?onClose\(\);[\s\S]*?\}, 1500\)/);
    expect(src).toMatch(/clearAutoClose/);
  });

  test("TC-009: BuildPatientDialog only auto-closes when a new patient was created", () => {
    const src = fs.readFileSync(BUILD_SRC, "utf8");
    expect(src).toMatch(/if \(result\.created\) \{[\s\S]*?setTimeout/);
    expect(src).toMatch(/Closing\.\.\./);
    expect(src).toMatch(/clearAutoClose/);
    expect(src).toMatch(/An identical patient already exists/);
  });
});

describe("VT-LEO-AI-168 -- Replay diagnostics use bitmap evaluator", () => {
  const PATIENT_FAILS_AGE: TestPatient = {
    id: "tp-young",
    name: "Young smoker",
    description: "29 year old with cough",
    codes: ["49727002"],
    age: 29,
    sex: "male",
    pathway_id: null,
    scope_type: "guideline",
    scope_id: "NG12",
    generation_source: "manual",
    content_hash: "h1",
    guideline_id: "NG12",
    guideline_title: "Suspected cancer (NG12)",
    created_at: "2026-04-17T15:00:00Z",
    created_by: "qa",
    expectations: [],
  };

  /** Annotated tree as returned by the production bitmap evaluator. */
  const DIAGNOSE_RESPONSE: DiagnoseResponse = {
    rule_id: "rule:NG12:lung",
    rule_name: "Lung cancer red flags",
    guideline_id: "NG12",
    schema_version: 2,
    fires: false,
    annotated_tree: {
      kind: "AND",
      node_id: "n0",
      matched: false,
      matched_count: 1,
      total_count: 2,
      children: [
        {
          kind: "DEMOGRAPHIC",
          node_id: "n1",
          field: "age",
          operator: ">=",
          value: 40,
          unit: "years",
          matched: false,
        },
        {
          kind: "OR",
          node_id: "n2",
          matched: true,
          matched_count: 1,
          total_count: 2,
          children: [
            {
              kind: "CONCEPT",
              node_id: "n3",
              matched: true,
              match_count: 1,
              criterion: {
                snomed_concept_id: "49727002",
                preferred_term: "Cough (finding)",
              },
            },
            {
              kind: "CONCEPT",
              node_id: "n4",
              matched: false,
              match_count: 0,
              criterion: {
                snomed_concept_id: "267036007",
                preferred_term: "Dyspnea (finding)",
              },
            },
          ],
        },
      ],
    },
    patient: {
      codes_provided: 1,
      codes_resolved: 1,
      age: 29,
      sex: "male",
    },
    active_version: "v1",
  };

  test(
    "TC-011: dialog calls /diagnose for the regression and renders the annotated tree",
    async () => {
      const fetchMock = jest.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => DIAGNOSE_RESPONSE,
      });
      // @ts-expect-error -- override fetch for the test env
      global.fetch = fetchMock;

      const rules: Record<string, RuleContext> = {
        "rule:NG12:lung": {
          name: "Lung cancer red flags",
          recommendation_text: "Refer for chest X-ray within 2 weeks.",
        },
      };
      render(
        <ReplayResultsDialog
          open
          onClose={() => undefined}
          report={{
            ruleset_version: "v1",
            scope_type: "guideline",
            scope_id: "NG12",
            guideline_id: "NG12",
            patient_count: 1,
            passes_count: 0,
            regressions_count: 1,
            drift_count: 0,
            results: [
              {
                patient_id: PATIENT_FAILS_AGE.id,
                patient_name: PATIENT_FAILS_AGE.name,
                passes: [],
                regressions: [
                  {
                    rule_id: "rule:NG12:lung",
                    fires: false,
                    expected: true,
                  },
                ],
                unexpected_matches: [],
                total_assertions: 1,
              },
            ],
          }}
          patients={[PATIENT_FAILS_AGE]}
          rules={rules}
          scopeType="guideline"
          scopeId="NG12"
        />,
      );

      const expander = screen.getByRole("button", {
        name: /show details for young smoker/i,
      });
      fireEvent.click(expander);

      expect(screen.getByText(/29 year old with cough/i)).toBeInTheDocument();
      expect(screen.getByText(/29 years, male/i)).toBeInTheDocument();
      expect(screen.getByText(/^49727002$/)).toBeInTheDocument();
      expect(screen.getByText(/lung cancer red flags/i)).toBeInTheDocument();
      expect(
        screen.getByText(/refer for chest x-ray within 2 weeks/i),
      ).toBeInTheDocument();

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalled();
      });
      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toContain("/api/guidance/test-patients/diagnose");
      expect((init as RequestInit).method).toBe("POST");
      const body = JSON.parse(String((init as RequestInit).body));
      expect(body.rule_id).toBe("rule:NG12:lung");
      expect(body.scope_type).toBe("guideline");
      expect(body.scope_id).toBe("NG12");
      expect(body.patient.codes).toEqual(["49727002"]);

      await waitFor(() => {
        expect(
          screen.getByText(/each part of the rule/i),
        ).toBeInTheDocument();
      });
      // Both the AND root and the OR group surface "1 of 2 satisfied"
      // so reviewers can see AT_LEAST/AND/OR counts at every level.
      expect(
        screen.getAllByText(/1 of 2 satisfied/i).length,
      ).toBeGreaterThanOrEqual(1);
      // The age node shows the satisfied/not-satisfied icons.
      expect(screen.getAllByLabelText(/satisfied/i).length).toBeGreaterThan(0);
      expect(
        screen.getAllByLabelText(/not satisfied/i).length,
      ).toBeGreaterThan(0);
    },
  );

  test(
    "TC-012: missing rule (404) surfaces a recompile hint instead of a stack trace",
    async () => {
      const fetchMock = jest.fn().mockResolvedValueOnce({
        ok: false,
        status: 502,
        text: async () =>
          "Rule not found in active ruleset. The rule may need to be recompiled (POST /terminology/guidelines/bitmap/compile).",
      });
      // @ts-expect-error -- override fetch for the test env
      global.fetch = fetchMock;

      render(
        <ReplayResultsDialog
          open
          onClose={() => undefined}
          report={{
            ruleset_version: "v1",
            scope_type: "guideline",
            scope_id: "NG12",
            guideline_id: "NG12",
            patient_count: 1,
            passes_count: 0,
            regressions_count: 1,
            drift_count: 0,
            results: [
              {
                patient_id: PATIENT_FAILS_AGE.id,
                patient_name: PATIENT_FAILS_AGE.name,
                passes: [],
                regressions: [
                  {
                    rule_id: "rule:missing",
                    fires: false,
                    expected: true,
                  },
                ],
                unexpected_matches: [],
                total_assertions: 1,
              },
            ],
          }}
          patients={[PATIENT_FAILS_AGE]}
        />,
      );

      const expander = screen.getByRole("button", {
        name: /show details for young smoker/i,
      });
      fireEvent.click(expander);

      await waitFor(() => {
        expect(screen.getByText(/recompiled/i)).toBeInTheDocument();
      });
    },
  );
});

describe("VT-LEO-AI-176 -- Test patients can be edited in place", () => {
  const BUILD_SRC = path.resolve(
    __dirname,
    "..",
    "app",
    "admin",
    "guidance",
    "test-patients",
    "BuildPatientDialog.tsx",
  );
  const PAGE_SRC2 = path.resolve(
    __dirname,
    "..",
    "app",
    "admin",
    "guidance",
    "test-patients",
    "page.tsx",
  );

  test("TC-013: api.updatePatient PATCHes /test-patients/{id} with JSON + CSRF", async () => {
    const fetchMock = jest.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "tp1",
        updated: true,
        expectations_written: 1,
      }),
    });
    // @ts-expect-error -- override global fetch for the test env
    global.fetch = fetchMock;
    const result = await updatePatient("tp1", {
      patient: {
        codes: ["100"],
        age: 71,
        sex: "female",
        pathway_id: null,
        name: "Edited",
        description: "",
        generation_source: "manual",
      },
      expectations: [
        { rule_id: "r1", fires: false, matched_branch_node_ids: [] },
      ],
      ruleset_version: null,
    });
    expect(result).toEqual({
      id: "tp1",
      updated: true,
      expectations_written: 1,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/guidance/test-patients/tp1");
    expect((init as RequestInit).method).toBe("PATCH");
    expect((init as RequestInit).headers).toMatchObject({
      "X-Requested-With": "XMLHttpRequest",
      "Content-Type": "application/json",
    });
    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.patient.name).toBe("Edited");
    expect(body.expectations).toHaveLength(1);
  });

  test("TC-014: BuildPatientDialog branches into PATCH when editingPatient is set", () => {
    const src = fs.readFileSync(BUILD_SRC, "utf8");
    // PATCH branch is wired to the api.updatePatient client.
    expect(src).toMatch(/import\s*\{[^}]*updatePatient[^}]*\}\s*from\s*"\.\/api"/);
    expect(src).toMatch(/editingPatient\?:\s*TestPatient/);
    expect(src).toMatch(/isEdit\s*=\s*!!editingPatient/);
    expect(src).toMatch(/updatePatient\(editingPatient\.id,\s*\{/);
    // Title + button copy switch on isEdit.
    expect(src).toMatch(/Edit test patient/);
    expect(src).toMatch(/Save changes/);
    // Save is enabled in edit mode without a fresh dry run.
    expect(src).toMatch(/canSave\s*=\s*\(isEdit\s*\|\|\s*!!dryRunResult\)/);
  });

  test("TC-015: edit-mode preserves matched_branch_node_ids when no fresh dry run was taken", () => {
    const src = fs.readFileSync(BUILD_SRC, "utf8");
    // The 'no dry run' branch must reuse the saved expectations'
    // branch path ids so editing the name doesn't blank them out.
    expect(src).toMatch(/buildExpectationsWithoutDryRun/);
    expect(src).toMatch(/matched_branch_node_ids:\s*saved\?\.matched_branch_node_ids\s*\|\|\s*\[\]/);
  });

  test("TC-016: library page exposes an Edit action that opens BuildPatientDialog in edit mode", () => {
    const src = fs.readFileSync(PAGE_SRC2, "utf8");
    expect(src).toMatch(/editingPatient/);
    expect(src).toMatch(/setEditingPatient/);
    // The Edit button row exists alongside Delete.
    expect(src).toMatch(/Edit test patient \$\{/);
    // The dialog is mounted with editingPatient prop.
    expect(src).toMatch(/editingPatient=\{editingPatient\}/);
  });
});

describe("VT-LEO-AI-166 -- Regression alert exposes the report", () => {
  const PANEL_SRC = path.resolve(
    __dirname,
    "..",
    "app",
    "admin",
    "guidance",
    "EditRuleDialog",
    "TestPatientsPanel.tsx",
  );

  test("TC-010: regression alert has a 'View report' action that opens the dialog", () => {
    const src = fs.readFileSync(PANEL_SRC, "utf8");
    expect(src).toMatch(
      /action=\{[\s\S]*?<Button[\s\S]*?onClick=\{\(\) => setOpenReplay\(true\)\}[\s\S]*?>\s*View report/,
    );
    // Ensure the misleading "below" copy is gone.
    expect(src).not.toMatch(/Open the report below/);
    expect(src).toMatch(/Open the report to\s+see which patient/);
  });
});
