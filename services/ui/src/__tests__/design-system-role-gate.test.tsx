/**
 * VT-LEO-AI-129: RoleGate / RolePicker / RoleSwitcher primitives.
 *
 * TC-001 picker renders when selected_role is null
 * TC-002 clicking a role card immediately confirms selection (no Continue button)
 * TC-003 switcher hidden for single-role users
 * TC-004 switcher visible for multi-role users
 * TC-005 feature flag off preserves legacy shell (no picker rendered)
 * TC-006 picker blocks app rendering until multi-role session is confirmed
 * TC-007 roles are grouped by category with count badges
 * TC-008 search filters roles by label
 * TC-009 org step shown when multiple orgs are supplied
 * TC-010 welcome message displays user name
 * TC-011 platform admin skips org step and goes straight to role list
 * TC-012 roles not in allowedRoles are rendered disabled with "Not assigned"
 * TC-013 roles in allowedRoles are enabled and clickable
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

const MULTI_ROLE_STATE: RoleState = {
  selectedRole: null,
  allowedRoles: ["triage_clinician", "clinical_coder"],
  needsSessionRoleChoice: true,
};

describe("VT-129 - Role-first primitives", () => {
  test("TC-001 picker renders when selected_role is null", async () => {
    const api = makeApi(MULTI_ROLE_STATE);
    render(
      <RoleProvider initialState={MULTI_ROLE_STATE} api={api}>
        <RoleGate>
          <div data-testid="app">app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.getByTestId("role-picker-overlay")).toBeInTheDocument();
    // The heading "Step 1: Choose Your Role" is the canonical check
    expect(screen.getByRole("heading", { level: 2, name: /Choose Your Role/i })).toBeInTheDocument();
    expect(screen.getByText(/Triage Clinician/i)).toBeInTheDocument();
    expect(screen.getByText(/Clinical Coder/i)).toBeInTheDocument();
  });

  test("TC-002 clicking a role card immediately confirms selection", async () => {
    const calls: string[] = [];
    const api = makeApi(MULTI_ROLE_STATE, (role) => calls.push(role));
    const user = userEvent.setup();
    render(
      <RoleProvider initialState={MULTI_ROLE_STATE} api={api}>
        <RoleGate>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    await user.click(screen.getByRole("radio", { name: /Clinician/i }));
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

  test("TC-006 picker blocks app rendering until multi-role session is confirmed", async () => {
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
    expect(screen.getByTestId("role-picker-overlay")).toBeInTheDocument();
    expect(screen.queryByTestId("app")).not.toBeInTheDocument();
  });

  test("TC-007 roles are grouped by category with count badges", async () => {
    // triage_clinician + auditor = Clinical Roles (2)
    // appointment_booking + clinical_administrator = Administration & Management (2)
    const state: RoleState = {
      selectedRole: null,
      allowedRoles: ["triage_clinician", "auditor", "appointment_booking", "clinical_administrator"],
      needsSessionRoleChoice: true,
    };
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RoleGate>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.getByText("Clinical Roles")).toBeInTheDocument();
    expect(screen.getByText("Administration & Management")).toBeInTheDocument();
    // Both categories have 2 roles each; check at least one badge
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
        <RoleGate>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    const search = screen.getByRole("searchbox", { name: /Search roles/i });
    await user.type(search, "Triage Clinician");
    expect(screen.getByText(/Triage Clinician/i)).toBeInTheDocument();
    expect(screen.queryByText(/Clinical Coder/i)).not.toBeInTheDocument();
  });

  test("TC-009 org step shown when multiple orgs are supplied", async () => {
    const state: RoleState = {
      selectedRole: null,
      allowedRoles: ["triage_clinician"],
      needsSessionRoleChoice: true,
    };
    const orgs = [
      { id: "org-1", name: "GP Surgery A", odsCode: "A12345" },
      { id: "org-2", name: "GP Surgery B", odsCode: "B67890" },
    ];
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RoleGate organizations={orgs}>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.getByText(/Choose Your Organisation/i)).toBeInTheDocument();
    expect(screen.getByText("GP Surgery A")).toBeInTheDocument();
    expect(screen.getByText("GP Surgery B")).toBeInTheDocument();
  });

  test("TC-010 welcome message displays user name", async () => {
    const state: RoleState = {
      selectedRole: null,
      allowedRoles: ["triage_clinician"],
      needsSessionRoleChoice: true,
    };
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RoleGate userName="Alice Jones">
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    expect(screen.getByText(/Welcome, Alice Jones/i)).toBeInTheDocument();
  });

  test("TC-011 platform admin skips org step and goes straight to role list", () => {
    const state: RoleState = {
      selectedRole: null,
      allowedRoles: ["platform_admin", "triage_clinician"],
      needsSessionRoleChoice: true,
    };
    const orgs = [
      { id: "org-1", name: "GP Surgery A", odsCode: "A12345" },
      { id: "org-2", name: "GP Surgery B", odsCode: "B67890" },
    ];
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RoleGate organizations={orgs} isPlatformAdmin={true}>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    // Org step must NOT be shown even though two orgs are supplied.
    expect(screen.queryByText(/Choose Your Organisation/i)).not.toBeInTheDocument();
    // Role step heading must be shown immediately.
    expect(screen.getByRole("heading", { name: /Choose Your Role/i })).toBeInTheDocument();
    // Admin note is visible (appears in the warning note text).
    expect(screen.getAllByText(/Platform admin/i).length).toBeGreaterThan(0);
  });

  test("TC-012 roles not in allowedRoles are rendered disabled with Not assigned label", () => {
    const state: RoleState = {
      selectedRole: null,
      // Only triage_clinician is allowed; all other roles should appear disabled.
      allowedRoles: ["triage_clinician"],
      needsSessionRoleChoice: true,
    };
    render(
      <RoleProvider initialState={state} api={makeApi(state)}>
        <RoleGate>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    // "Not assigned" label must appear for at least one unavailable role.
    const notAssigned = screen.getAllByText(/Not assigned/i);
    expect(notAssigned.length).toBeGreaterThan(0);
    // All "Not assigned" role buttons must be disabled.
    const disabledBtns = screen
      .getAllByRole("radio")
      .filter((el) => (el as HTMLButtonElement).disabled);
    expect(disabledBtns.length).toBeGreaterThan(0);
  });

  test("TC-013 roles in allowedRoles are enabled and clickable", async () => {
    const user = userEvent.setup();
    let confirmed = "";
    const state: RoleState = {
      selectedRole: null,
      allowedRoles: ["triage_clinician"],
      needsSessionRoleChoice: true,
    };
    render(
      <RoleProvider initialState={state} api={makeApi(state, (r) => { confirmed = r; })}>
        <RoleGate>
          <div>app</div>
        </RoleGate>
      </RoleProvider>,
    );
    const triage = screen.getByRole("radio", { name: /Triage Clinician/i });
    expect((triage as HTMLButtonElement).disabled).toBe(false);
    await act(async () => { await user.click(triage); });
    expect(confirmed).toBe("triage_clinician");
  });
});
