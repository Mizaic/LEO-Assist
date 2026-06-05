/**
 * VT-LEO-AI-129: RoleGate / RolePicker / RoleSwitcher primitives.
 *
 * TC-001 picker renders when selected_role is null
 * TC-002 picker PATCHes on confirm
 * TC-003 switcher hidden for single-role users
 * TC-004 switcher visible for multi-role users
 * TC-005 feature flag off preserves legacy shell (no picker rendered)
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

import {
  RoleGate,
  RoleProvider,
  RoleSwitcher,
  type RoleApi,
  type RoleState,
} from "@leo/design-system/roles";

function makeApi(
  initial: RoleState,
  onSet?: (role: string) => void,
): RoleApi {
  return {
    getRoleState: async () => initial,
    setSelectedRole: async (role) => {
      onSet?.(role);
      return {
        selectedRole: role,
        allowedRoles: initial.allowedRoles,
        needsSessionRoleChoice: false,
      };
    },
  };
}

describe("VT-129 - Role-first primitives", () => {
  test("TC-001 picker renders when selected_role is null", async () => {
    const api = makeApi({
      selectedRole: null,
      allowedRoles: ["clinician", "staff"],
      needsSessionRoleChoice: true,
    });
    render(
      <RoleProvider
        initialState={{
          selectedRole: null,
          allowedRoles: ["clinician", "staff"],
          needsSessionRoleChoice: true,
        }}
        api={api}
      >
        <RoleGate>
          <div data-testid="app">app</div>
        </RoleGate>
      </RoleProvider>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText(/Pick your role/i)).toBeInTheDocument();
    expect(screen.getByText(/Clinician/i)).toBeInTheDocument();
    expect(screen.getByText(/Audit or coding staff/i)).toBeInTheDocument();
  });

  test("TC-002 picker PATCHes on confirm", async () => {
    const calls: string[] = [];
    const api = makeApi(
      {
        selectedRole: null,
        allowedRoles: ["clinician", "staff"],
        needsSessionRoleChoice: true,
      },
      (role) => calls.push(role),
    );
    const user = userEvent.setup();
    render(
      <RoleProvider
        initialState={{
          selectedRole: null,
          allowedRoles: ["clinician", "staff"],
          needsSessionRoleChoice: true,
        }}
        api={api}
      >
        <RoleGate>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    await user.click(screen.getByRole("radio", { name: /Clinician/i }));
    await user.click(screen.getByRole("button", { name: /Continue/i }));
    await waitFor(() => expect(calls).toEqual(["clinician"]));
  });

  test("TC-003 switcher hidden for single-role users", async () => {
    const { container } = render(
      <RoleProvider
        initialState={{
          selectedRole: "clinician",
          allowedRoles: ["clinician"],
          needsSessionRoleChoice: false,
        }}
        api={makeApi({
          selectedRole: "clinician",
          allowedRoles: ["clinician"],
          needsSessionRoleChoice: false,
        })}
      >
        <RoleSwitcher />
      </RoleProvider>,
    );
    expect(container.firstChild).toBeNull();
  });

  test("TC-004 switcher visible for multi-role users", async () => {
    render(
      <RoleProvider
        initialState={{
          selectedRole: "clinician",
          allowedRoles: ["clinician", "qa_ra_lead"],
          needsSessionRoleChoice: false,
        }}
        api={makeApi({
          selectedRole: "clinician",
          allowedRoles: ["clinician", "qa_ra_lead"],
          needsSessionRoleChoice: false,
        })}
      >
        <RoleSwitcher />
      </RoleProvider>,
    );
    const button = screen.getByRole("button", { name: /Switch role/i });
    expect(button).toBeInTheDocument();
  });

  test("TC-005 disabled RoleGate does not render the picker", async () => {
    render(
      <RoleProvider
        initialState={{
          selectedRole: null,
          allowedRoles: ["clinician", "staff"],
          needsSessionRoleChoice: true,
        }}
        api={makeApi({
          selectedRole: null,
          allowedRoles: ["clinician", "staff"],
          needsSessionRoleChoice: true,
        })}
      >
        <RoleGate enabled={false}>
          <div data-testid="app">app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("app")).toBeInTheDocument();
  });

  test("TC-006 picker blocks app rendering until multi-role session is confirmed", async () => {
    const api = makeApi({
      selectedRole: "clinician",
      allowedRoles: ["clinician", "staff"],
      needsSessionRoleChoice: true,
    });
    render(
      <RoleProvider
        initialState={{
          selectedRole: "clinician",
          allowedRoles: ["clinician", "staff"],
          needsSessionRoleChoice: true,
        }}
        api={api}
      >
        <RoleGate>
          <div data-testid="app">app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByTestId("app")).not.toBeInTheDocument();
    const continueBtn = screen.getByRole("button", { name: /Continue/i });
    expect(continueBtn).not.toBeDisabled();
  });
});
