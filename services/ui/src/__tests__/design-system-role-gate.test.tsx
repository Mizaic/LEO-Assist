/**
 * VT-LEO-AI-129: RoleGate / RolePicker / RoleSwitcher primitives.
 *
 * Role picker is retired for Mizaic-staff-only use. RoleGate auto-applies
 * the assigned or first allowed role and never blocks the app.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

import {
  RoleGate,
  RolePicker,
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

const MULTI_ROLE_STATE: RoleState = {
  selectedRole: null,
  allowedRoles: ["triage_clinician", "clinical_coder"],
  needsSessionRoleChoice: true,
};

describe("VT-129 - Role-first primitives", () => {
  test("TC-001 RoleGate does not render the picker when selected_role is null", async () => {
    const calls: string[] = [];
    render(
      <RoleProvider
        initialState={MULTI_ROLE_STATE}
        api={makeApi(MULTI_ROLE_STATE, (role) => calls.push(role))}
      >
        <RoleGate>
          <div data-testid="app">app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.queryByTestId("role-picker-overlay")).not.toBeInTheDocument();
    expect(screen.getByTestId("app")).toBeInTheDocument();
    await waitFor(() => expect(calls).toEqual(["triage_clinician"]));
  });

  test("TC-002 RoleGate auto-confirms the first allowed role", async () => {
    const calls: string[] = [];
    render(
      <RoleProvider
        initialState={MULTI_ROLE_STATE}
        api={makeApi(MULTI_ROLE_STATE, (role) => calls.push(role))}
      >
        <RoleGate>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    await waitFor(() => expect(calls).toEqual(["triage_clinician"]));
  });

  test("TC-003 switcher hidden for single-role users", async () => {
    const { container } = render(
      <RoleProvider
        initialState={{
          selectedRole: "triage_clinician",
          allowedRoles: ["triage_clinician"],
          needsSessionRoleChoice: false,
        }}
        api={makeApi({
          selectedRole: "triage_clinician",
          allowedRoles: ["triage_clinician"],
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
          selectedRole: "triage_clinician",
          allowedRoles: ["triage_clinician", "auditor"],
          needsSessionRoleChoice: false,
        }}
        api={makeApi({
          selectedRole: "triage_clinician",
          allowedRoles: ["triage_clinician", "auditor"],
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
        initialState={MULTI_ROLE_STATE}
        api={makeApi(MULTI_ROLE_STATE)}
      >
        <RoleGate enabled={false}>
          <div data-testid="app">app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.queryByTestId("role-picker-overlay")).not.toBeInTheDocument();
    expect(screen.getByTestId("app")).toBeInTheDocument();
  });

  test("TC-006 RoleGate does not block the app for multi-role sessions", async () => {
    const state: RoleState = {
      selectedRole: "triage_clinician",
      allowedRoles: ["triage_clinician", "clinical_coder"],
      needsSessionRoleChoice: true,
    };
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RoleGate>
          <div data-testid="app">app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.queryByTestId("role-picker-overlay")).not.toBeInTheDocument();
    expect(screen.getByTestId("app")).toBeInTheDocument();
  });

  test("TC-007 roles are grouped by category with count badges", async () => {
    const state: RoleState = {
      selectedRole: null,
      allowedRoles: [
        "triage_clinician",
        "auditor",
        "appointment_booking",
        "clinical_administrator",
      ],
      needsSessionRoleChoice: true,
    };
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RolePicker pinned />
      </RoleProvider>,
    );
    expect(screen.getByText("Clinical Roles")).toBeInTheDocument();
    expect(screen.getByText("Administration & Management")).toBeInTheDocument();
    expect(screen.getAllByText(/2 roles/i).length).toBeGreaterThanOrEqual(1);
  });

  test("TC-008 search filters roles by label", async () => {
    const state: RoleState = {
      selectedRole: null,
      allowedRoles: ["triage_clinician", "clinical_coder"],
      needsSessionRoleChoice: true,
    };
    const user = userEvent.setup();
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RolePicker pinned />
      </RoleProvider>,
    );
    const search = screen.getByRole("searchbox", { name: /Search roles/i });
    await user.type(search, "Triage Clinician");
    expect(screen.getByText(/Triage Clinician/i)).toBeInTheDocument();
    expect(screen.queryByText(/Clinical Coder/i)).not.toBeInTheDocument();
  });
});
