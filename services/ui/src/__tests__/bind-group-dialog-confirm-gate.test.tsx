/**
 * VT for the BindGroupDialog "type the name to confirm" gate.
 *
 * Pinned to DI-6CF7FCE0 acceptance criterion: a misclick MUST NOT
 * be able to bind a LEO role to the wrong Entra security group.
 *
 * Live-render coverage:
 *  - Bind button is disabled until both a role is picked AND the
 *    confirmation text matches the group displayName exactly.
 *  - Submitting calls bindEntraGroup with the chosen role and the
 *    typed confirmation string.
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("@/lib/api/admin", () => ({
  bindEntraGroup: jest.fn(),
}));

import { bindEntraGroup } from "@/lib/api/admin";
import BindGroupDialog from "@/components/tenant/BindGroupDialog";

const GROUP = {
  id: "group-oid-1",
  displayName: "LEO Coding Reviewers",
  description: "Coding reviewers for LEO",
  securityEnabled: true,
  mailEnabled: false,
};

const ROLES = ["coding_reviewer", "ops_admin"];

afterEach(() => {
  jest.clearAllMocks();
});

async function pickRole(label: RegExp): Promise<void> {
  // MUI Select renders multiple combobox-roled nodes (the visible button +
  // a hidden input). Open the listbox by clicking the visible trigger and
  // then click the option whose accessible name matches.
  const triggers = screen.getAllByRole("combobox");
  const trigger = triggers.find((el) => el.tagName !== "INPUT") || triggers[0];
  fireEvent.mouseDown(trigger);
  const option = await screen.findByRole("option", { name: label });
  fireEvent.click(option);
}

describe("BindGroupDialog confirm gate - DI-6CF7FCE0", () => {
  test("Bind button stays disabled while the confirmation does not match", () => {
    render(
      <BindGroupDialog
        group={GROUP}
        roleNames={ROLES}
        onClose={() => {}}
        onBound={() => {}}
      />,
    );

    const submit = screen.getByRole("button", { name: /bind group/i });
    expect(submit).toBeDisabled();

    const confirm = screen.getByLabelText(/type the group name to confirm/i);
    fireEvent.change(confirm, { target: { value: "wrong name" } });
    expect(submit).toBeDisabled();
  });

  test("Bind button enables only when role + exact name match are present", async () => {
    render(
      <BindGroupDialog
        group={GROUP}
        roleNames={ROLES}
        onClose={() => {}}
        onBound={() => {}}
      />,
    );

    const submit = screen.getByRole("button", { name: /bind group/i });
    const confirm = screen.getByLabelText(/type the group name to confirm/i);
    fireEvent.change(confirm, { target: { value: GROUP.displayName } });

    expect(submit).toBeDisabled();

    await pickRole(/coding reviewer/i);

    await waitFor(() => expect(submit).not.toBeDisabled());
  });

  test("Submitting sends confirm_display_name to the API", async () => {
    (bindEntraGroup as jest.Mock).mockResolvedValueOnce({ shadow: {}, bind: {} });
    const onBound = jest.fn();

    render(
      <BindGroupDialog
        group={GROUP}
        roleNames={ROLES}
        onClose={() => {}}
        onBound={onBound}
      />,
    );

    const confirm = screen.getByLabelText(/type the group name to confirm/i);
    fireEvent.change(confirm, { target: { value: GROUP.displayName } });

    await pickRole(/coding reviewer/i);

    const submit = screen.getByRole("button", { name: /bind group/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    fireEvent.click(submit);

    await waitFor(() =>
      expect(bindEntraGroup).toHaveBeenCalledWith(
        GROUP.id,
        expect.objectContaining({
          role_name: "coding_reviewer",
          confirm_display_name: GROUP.displayName,
        }),
      ),
    );
    await waitFor(() => expect(onBound).toHaveBeenCalled());
  });
});
