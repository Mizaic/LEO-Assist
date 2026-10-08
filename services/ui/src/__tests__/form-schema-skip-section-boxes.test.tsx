/**
 * Live-render VT: a skipped section lists the tick boxes LEO found in it.
 *
 * Detect fills admin and template guidance sections with their printed
 * tick boxes, so the save check can match the form to its letter. The
 * teacher sees those boxes, read-only, and is told they are not coded.
 *
 * Atlas trace: UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1
 */
import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";

import { FormSchemaSectionEditor } from "../components/operations/FormSchemaSectionEditor";
import type {
  FormSchemaSection,
  SectionType,
} from "../components/operations/formSchemaDetector";

const theme = createTheme();
const HOSPITAL_BOXES = ["Pt Contacted", "Interpreter Booked", "Transport Booked", "Accepted"];

function skipSection(sectionType: SectionType, labels: string[]): FormSchemaSection {
  return {
    section_id: "S5",
    section_type: sectionType,
    label: "Hospital Use Only",
    start_pattern: "Hospital Use Only",
    items: labels.map((label) => ({
      pattern: label,
      entity_text: label,
      semantic_tag: "none",
      assertion: "present",
    })),
  };
}

function noop() {
  return undefined;
}

function renderSection(section: FormSchemaSection) {
  return render(
    <ThemeProvider theme={theme}>
      <FormSchemaSectionEditor
        section={section}
        onPatch={noop}
        onPatchItem={noop}
        onAddItem={noop}
        onRemoveItem={noop}
      />
    </ThemeProvider>,
  );
}

describe("Teach this form -- skipped section tick boxes", () => {
  it("lists the tick boxes of an admin section, read-only, once expanded", async () => {
    const user = userEvent.setup();
    renderSection(skipSection("admin", HOSPITAL_BOXES));

    await user.click(screen.getByRole("button", { name: "Expand section" }));

    const list = screen.getByRole("list", { name: "Tick boxes in this section" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual(HOSPITAL_BOXES);
    expect(screen.getByText(/LEO skips these/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add item" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove item" })).not.toBeInTheDocument();
  });

  it("lists the tick boxes of a template guidance section", async () => {
    const user = userEvent.setup();
    renderSection(skipSection("template_noise", ["Bloating noted"]));

    await user.click(screen.getByRole("button", { name: "Expand section" }));

    const list = screen.getByRole("list", { name: "Tick boxes in this section" });
    expect(within(list).getByRole("listitem")).toHaveTextContent("Bloating noted");
  });

  it("shows no list for a skipped section with no tick boxes", async () => {
    const user = userEvent.setup();
    renderSection(skipSection("admin", []));

    await user.click(screen.getByRole("button", { name: "Expand section" }));

    expect(
      screen.queryByRole("list", { name: "Tick boxes in this section" }),
    ).not.toBeInTheDocument();
  });
});
