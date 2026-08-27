/**
 * Live-render VT: Edit a taught form without pasting a sample letter.
 *
 * A listed template already has sections in Neo4j. Edit must open the
 * schema editor immediately. Letter / UBRN stay optional help.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import FormSchemaTeachDialog from "../app/settings/form-schemas/FormSchemaTeachDialog";

const theme = createTheme();

const SAVED_SCHEMA = {
  schema_id: "schema-sfh",
  fingerprint: "sfh-gynae-2ww-v1",
  form_name: "Sherwood Forest Gynae 2WW",
  organization_id: "org-sfh",
  service_id: "svc-gynae",
  status: "active",
  sections: [
    {
      section_id: "A",
      section_type: "checkbox_single",
      label: "Section A: Gynaecological Cancer type suspected",
      start_pattern: "(?i)section\\s+a:",
      items: [
        {
          pattern: "Ovary",
          entity_text: "Ovary",
          semantic_tag: "finding",
          assertion: "present",
        },
      ],
    },
    {
      section_id: "D",
      section_type: "ordered_tests",
      label: "Section D: Investigations performed",
      start_pattern: "(?i)section\\s+d:",
      items: [
        {
          pattern: "FBC",
          entity_text: "Full blood count",
          semantic_tag: "procedure",
          assertion: "present",
          analytes: [{ label: "Hb", snomed_code: "1022280009", display: "Hb" }],
        },
      ],
    },
  ],
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => body,
  } as Response;
}

function mockSavedSchemaFetch() {
  jest.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = (init?.method || "GET").toUpperCase();
    if (url.includes("/api/form-schemas/") && method === "GET") {
      return jsonResponse(200, { schema: SAVED_SCHEMA });
    }
    if (url.includes("/api/form-schemas/detect") && method === "POST") {
      return jsonResponse(200, { sections: [] });
    }
    if (url.includes("/api/admin/orgs")) {
      return jsonResponse(200, []);
    }
    return jsonResponse(200, {});
  });
}

function renderEditDialog() {
  return render(
    <ThemeProvider theme={theme}>
      <FormSchemaTeachDialog
        open
        fingerprint="sfh-gynae-2ww-v1"
        formName="Sherwood Forest Gynae 2WW"
        organizationId="org-sfh"
        serviceId="svc-gynae"
        onClose={() => undefined}
      />
    </ThemeProvider>,
  );
}

describe("FormSchemaTeachDialog Edit without sample letter", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("opens the schema editor from saved sections without letter text", async () => {
    mockSavedSchemaFetch();
    renderEditDialog();

    expect(
      await screen.findByDisplayValue(/Section A: Gynaecological Cancer type suspected/),
    ).toBeInTheDocument();
    expect(
      screen.getByDisplayValue(/Section D: Investigations performed/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("form-completeness-editor")).toBeInTheDocument();

    const letter = screen.getByLabelText(/sample referral letter/i);
    expect(letter).toHaveValue("");

    const openEditor = screen.queryByRole("button", { name: /open schema editor/i });
    if (openEditor) {
      expect(openEditor).toBeEnabled();
    }
  });

  it("GETs the schema by fingerprint instead of waiting for a letter", async () => {
    mockSavedSchemaFetch();
    renderEditDialog();

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls as Array<[unknown]>;
      const gotSaved = calls.some((call) =>
        String(call[0]).includes("/api/form-schemas/sfh-gynae-2ww-v1"),
      );
      expect(gotSaved).toBe(true);
    });
  });
});
