/**
 * Live-render VT for Teach this form empty-state teaching.
 *
 * Detect failure must not be a dead end: Add section stays visible,
 * click creates a section, and Save stays disabled until a section exists.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import FormSchemaAnnotator from "../components/operations/FormSchemaAnnotator";

const theme = createTheme();

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function mockDetectFailure() {
  jest.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = (init?.method || "GET").toUpperCase();
    if (url.includes("/api/form-schemas/detect") && method === "POST") {
      return jsonResponse(403, { detail: "Platform admin access required" });
    }
    if (url.includes("/api/form-schemas/") && method === "GET") {
      return jsonResponse(403, { detail: "Platform admin access required" });
    }
    return jsonResponse(200, {});
  });
}

function renderAnnotator(sourceText = "Narrative letter with no tick boxes.") {
  return render(
    <ThemeProvider theme={theme}>
      <FormSchemaAnnotator
        fingerprint="fp-gynae"
        sourceText={sourceText}
        formName="Sherwood Forest 2WW gynae"
      />
    </ThemeProvider>,
  );
}

describe("FormSchemaAnnotator live empty-state teaching", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("shows Add section when detect fails and Save stays disabled", async () => {
    mockDetectFailure();
    renderAnnotator();

    const add = await screen.findByRole("button", { name: /add section/i });
    expect(add).toBeVisible();
    expect(screen.getByRole("button", { name: /save schema/i })).toBeDisabled();
    expect(
      screen.queryByText(/using the button below/i),
    ).not.toBeInTheDocument();
  });

  it("creates a section when Add section is clicked and then enables Save", async () => {
    mockDetectFailure();
    const user = userEvent.setup();
    renderAnnotator();

    await user.click(await screen.findByRole("button", { name: /add section/i }));

    expect(await screen.findByDisplayValue("New section")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save schema/i })).toBeEnabled();
    });
  });

  it("surfaces a real detect error instead of a silent dead end", async () => {
    mockDetectFailure();
    renderAnnotator();

    expect(
      await screen.findByText(/You are not allowed to auto-detect this form/),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /add section/i }),
    ).toBeVisible();
  });

  it("falls back to local section detect on a checkbox form when the API fails", async () => {
    mockDetectFailure();
    renderAnnotator(
      "Section A: Gynaecological Cancer type suspected\nOvary [ ] Cervix [X]",
    );

    expect(
      await screen.findByDisplayValue(/Section A: Gynaecological Cancer type suspected/),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save schema/i })).toBeEnabled();
    });
    expect(
      screen.queryByText(/You are not allowed to auto-detect this form/),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/could not detect/i)).not.toBeInTheDocument();
  });

  it("finds Section A in a markdown table when detect fails", async () => {
    mockDetectFailure();
    renderAnnotator(
      [
        "Minimum Dataset",
        "| Section A: Gynaecological Cancer type suspected |",
        "| Ovary [ ] Cervix [X] |",
      ].join("\n"),
    );

    expect(
      await screen.findByDisplayValue(/Section A: Gynaecological Cancer type suspected/),
    ).toBeInTheDocument();
  });

  it("still detects when a saved schema is admin-only", async () => {
    jest.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = (init?.method || "GET").toUpperCase();
      if (url.includes("/api/form-schemas/detect") && method === "POST") {
        return jsonResponse(200, {
          sections: [
            {
              section_id: "A",
              section_type: "checkbox_single",
              label: "Section A: Gynaecological Cancer type suspected",
              start_pattern: "(?i)section\\s+a:",
              items: [],
            },
          ],
        });
      }
      if (url.includes("/api/form-schemas/") && method === "GET") {
        return jsonResponse(200, {
          schema: {
            form_name: "Sherwood Forest 2WW gynae",
            sections: [
              {
                section_id: "MDS",
                section_type: "admin",
                label: "Minimum Dataset",
                start_pattern: "(?i)minimum",
                items: [],
              },
            ],
          },
        });
      }
      return jsonResponse(200, {});
    });
    renderAnnotator(
      "Minimum Dataset\nSection A: Gynaecological Cancer type suspected\nOvary [ ]",
    );

    expect(
      await screen.findByDisplayValue(/Section A: Gynaecological Cancer type suspected/),
    ).toBeInTheDocument();
  });

  it("shows Ask LEO again so the reviewer can retry detect", async () => {
    mockDetectFailure();
    renderAnnotator();
    expect(
      await screen.findByRole("button", { name: /ask leo again/i }),
    ).toBeVisible();
  });
});
