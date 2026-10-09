/**
 * Teach dialog: the sample letter area folds away so the section editor
 * has room when a saved form is edited.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
import * as fs from "fs";
import * as path from "path";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import FormSchemaTeachDialog from "../app/settings/form-schemas/FormSchemaTeachDialog";

jest.mock("@/components/operations/FormSchemaAnnotator", () => ({
  __esModule: true,
  default: () => <div data-testid="annotator-stub" />,
}));

const SAVED = {
  fingerprint: "abcdef0123456789",
  form_name: "Lower GI",
  sections: [{ section_id: "A", section_type: "free_text", label: "History" }],
};

function respond(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function mockFetch(schema: unknown) {
  global.fetch = jest.fn(async (url: string) => {
    if (String(url).startsWith("/api/form-schemas/letter-text")) {
      return respond({ text: "Line one\nLine two\nLine three", fingerprint: "fp", chunk_count: 1 });
    }
    return respond({ schema });
  }) as unknown as typeof fetch;
}

function renderDialog() {
  return render(
    <FormSchemaTeachDialog
      open
      fingerprint="abcdef0123456789"
      formName="Lower GI"
      onClose={() => undefined}
    />,
  );
}

function letterToggle(): HTMLElement {
  return screen.getByRole("button", { name: /sample letter/i });
}

describe("sample letter area", () => {
  test("editing a saved form with no letter starts with the area folded away", async () => {
    mockFetch(SAVED);
    renderDialog();
    await screen.findByTestId("annotator-stub");
    const toggle = letterToggle();
    await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "false"));
    const panelId = toggle.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    expect(document.getElementById(String(panelId))).not.toBeNull();
  });

  test("the toggle opens the folded area", async () => {
    mockFetch(SAVED);
    renderDialog();
    await screen.findByTestId("annotator-stub");
    await waitFor(() => expect(letterToggle()).toHaveAttribute("aria-expanded", "false"));
    await userEvent.click(letterToggle());
    expect(letterToggle()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("UBRN")).toBeVisible();
  });

  test("a new form starts with the area open", async () => {
    mockFetch(null);
    renderDialog();
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(letterToggle()).toHaveAttribute("aria-expanded", "true");
  });

  test("after Load the area folds away and says the letter is loaded", async () => {
    mockFetch(null);
    renderDialog();
    await userEvent.type(screen.getByLabelText("UBRN"), "000123456789");
    await userEvent.click(screen.getByTestId("load-from-referral-btn"));
    await waitFor(() => expect(letterToggle()).toHaveAttribute("aria-expanded", "false"));
    expect(screen.getByTestId("sample-letter-summary")).toHaveTextContent(
      "Sample letter loaded (3 lines).",
    );
  });

  test("the dialog has a fixed tall height so the editor fills it", () => {
    const src = fs.readFileSync(
      path.join(__dirname, "../app/settings/form-schemas/FormSchemaTeachDialog.tsx"),
      "utf8",
    );
    expect(src).toMatch(/height:\s*"90vh"/);
  });
});
