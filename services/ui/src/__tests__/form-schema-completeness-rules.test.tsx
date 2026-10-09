/**
 * VT: the teach dialog keeps saved completeness rules and shows proposals.
 *
 * Opening a saved form must show its saved rules, and an unchanged save
 * must send them back, never an empty list. Proposed rules show the form
 * wording behind them, and weak ones are marked for a person to check.
 *
 * Atlas trace: VT-BFDEDB18, DI-9BF69EC9, DO-F120628C, R-A3BD3AC7
 */
import * as fs from "fs";
import * as path from "path";
import React from "react";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  FormSchemaCompletenessEditor,
  hasNoCodes,
} from "../components/operations/FormSchemaCompletenessEditor";
import { useFormSchemaTeach } from "../components/operations/useFormSchemaTeach";
import {
  saveTaughtForm,
  type CompletenessLogicGroup,
} from "../components/operations/formSchemaTeach";

jest.mock("@/components/SnomedLookupField", () => ({
  SnomedLookupField: () => null,
}));

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readSource(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const SAVED_GROUP: CompletenessLogicGroup = {
  name: "Blood results",
  kind: "mandatory",
  required: true,
  semantic_categories: [],
  concept_ids: [],
  section_id: "bloods",
  evidence: "Blood results are mandatory",
  needs_review: false,
};

const SAVED_SCHEMA = {
  form_name: "Lower GI",
  fingerprint: "abcdef0123456789",
  sections: [
    {
      section_id: "bloods",
      section_type: "free_text",
      label: "Blood results",
      start_pattern: "Blood results",
      items: [],
    },
  ],
  completeness_groups: [SAVED_GROUP],
};

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("saved completeness rules", () => {
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn(async (url: string) => {
      if (String(url).startsWith("/api/form-schemas/abcdef0123456789")) {
        return jsonResponse({ schema: SAVED_SCHEMA, match: "fingerprint" });
      }
      return jsonResponse({ sections: [], detection: {} });
    });
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  test("opening the teach dialog for a form with saved rules shows those rules", async () => {
    const { result } = renderHook(() =>
      useFormSchemaTeach("abcdef0123456789", "Blood results", "Lower GI"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.groups).toEqual([SAVED_GROUP]);
  });

  test("saving a form whose saved rules were not changed sends the saved rules unchanged", async () => {
    const { result } = renderHook(() =>
      useFormSchemaTeach("abcdef0123456789", "Blood results", "Lower GI"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    await saveTaughtForm({
      fingerprint: "abcdef0123456789",
      name: result.current.name,
      sections: result.current.sections,
      organizationId: "org-1",
      serviceId: "svc-1",
      completenessGroups: result.current.groups,
      sourceText: "Blood results",
    });
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(String(put?.[1]?.body));
    expect(body.completeness_groups).toEqual([SAVED_GROUP]);
  });

  test("the annotator saves the rules held by the teach hook", () => {
    const src = readSource("services/ui/src/components/operations/FormSchemaAnnotator.tsx");
    expect(src).toMatch(/completenessGroups:\s*teach\.groups/);
    expect(src).toMatch(/groups=\{teach\.groups\}/);
  });
});

const PROPOSED: CompletenessLogicGroup = {
  name: "At least one symptom",
  kind: "optional",
  required: false,
  semantic_categories: [],
  concept_ids: [],
  section_id: "symptoms",
  evidence: "Please tick at least one",
  needs_review: true,
};

const DETECTED_SECTION = {
  section_id: "symptoms",
  section_type: "checkbox_multi",
  label: "Symptoms",
  start_pattern: "Symptoms",
  items: [],
};

function mockDetect(saved: unknown) {
  global.fetch = jest.fn(async (url: string) => {
    if (String(url).endsWith("/detect")) {
      return jsonResponse({
        sections: [DETECTED_SECTION],
        detection: {},
        completeness_groups: [PROPOSED],
      });
    }
    return jsonResponse({ schema: saved, match: saved ? "fingerprint" : "none" });
  }) as unknown as typeof fetch;
}

describe("proposed completeness rules", () => {
  test("a form with no saved rules shows the rules Ask LEO proposed", async () => {
    mockDetect(null);
    const { result } = renderHook(() =>
      useFormSchemaTeach("abcdef0123456789", "Symptoms", "Lower GI"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.groups).toEqual([PROPOSED]);
  });

  test("saved rules are kept when Ask LEO proposes others", async () => {
    mockDetect({ ...SAVED_SCHEMA, sections: [] });
    const { result } = renderHook(() =>
      useFormSchemaTeach("abcdef0123456789", "Symptoms", "Lower GI"),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.sections[0]?.section_id).toBe("symptoms");
    expect(result.current.groups).toEqual([SAVED_GROUP]);
  });
});

describe("completeness editor", () => {
  test("the editor shows each rule's quote and a check mark for weak rules", async () => {
    const onChange = jest.fn();
    render(<FormSchemaCompletenessEditor groups={[SAVED_GROUP, PROPOSED]} onChange={onChange} />);
    expect(screen.getByText(/"Blood results are mandatory"/)).toBeInTheDocument();
    expect(screen.getByText(/"Please tick at least one"/)).toBeInTheDocument();
    expect(screen.getAllByText("Check this rule")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Mark as checked" }));
    expect(onChange).toHaveBeenCalledWith([SAVED_GROUP, { ...PROPOSED, needs_review: false }]);
  });

  test("a rule that points at a taught section needs no SNOMED code", () => {
    expect(hasNoCodes(SAVED_GROUP)).toBe(false);
    expect(
      hasNoCodes({ ...PROPOSED, kind: "one_of", section_id: "", members: [PROPOSED] }),
    ).toBe(false);
  });

  test("the editor says what to do when there are no rules", () => {
    render(<FormSchemaCompletenessEditor groups={[]} onChange={() => undefined} />);
    expect(screen.getByTestId("completeness-empty")).toHaveTextContent(
      "No completeness rules yet.",
    );
  });
});

describe("hard-coded seed is removed", () => {
  test("the 2WW completeness seed is removed from the server and the browser", () => {
    for (const rel of [
      "services/ui/src/components/operations/formSchemaCompletenessSeed.ts",
      "libs/pipeline/form_completeness_seed.py",
    ]) {
      expect(fs.existsSync(path.join(REPO_ROOT, rel))).toBe(false);
    }
    const annotator = readSource("services/ui/src/components/operations/FormSchemaAnnotator.tsx");
    expect(annotator).not.toMatch(/seedCompletenessGroups/);
  });
});
