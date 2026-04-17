/**
 * VT-LEO-AI-115 TC-004 - ConfirmDialog exposes aria-labelledby and
 * aria-describedby.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import ConfirmDialog from "@/components/ConfirmDialog";

describe("ConfirmDialog a11y", () => {
  test("TC-004 aria-labelledby and aria-describedby point at real elements", () => {
    render(
      <ConfirmDialog
        title="Remove code?"
        body="This will permanently remove the clinical code."
        confirmLabel="Remove"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );
    const dialog = screen.getByRole("dialog");
    const labelId = dialog.getAttribute("aria-labelledby");
    const describedId = dialog.getAttribute("aria-describedby");
    expect(labelId).toBeTruthy();
    expect(describedId).toBeTruthy();
    const labelEl = document.getElementById(labelId as string);
    const describedEl = document.getElementById(describedId as string);
    expect(labelEl?.textContent).toContain("Remove code?");
    expect(describedEl?.textContent).toContain("permanently remove");
  });
});
