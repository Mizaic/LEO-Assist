import React from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrgProvider, useOrg, useOrgId } from "../OrgContext";

const ORGS = [
  { id: "org-1", name: "Practice A", odsCode: "A001" },
  { id: "org-2", name: "Practice B", odsCode: "B002" },
];

let mockSession: any = null;

jest.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    session: mockSession,
    status: mockSession ? "authenticated" : "unauthenticated",
    signIn: jest.fn(),
    signOut: jest.fn(),
    refetch: jest.fn(),
  }),
  AuthProvider: ({ children }: any) => children,
}));

const localStore: Record<string, string> = {};
beforeEach(() => {
  Object.keys(localStore).forEach((k) => delete localStore[k]);
  jest.spyOn(Storage.prototype, "getItem").mockImplementation((k) => localStore[k] ?? null);
  jest.spyOn(Storage.prototype, "setItem").mockImplementation((k, v) => { localStore[k] = v; });
});

function OrgDisplay() {
  const { currentOrg, organizations, isPlatformAdmin, viewAll } = useOrg();
  const orgId = useOrgId();
  return (
    <div>
      <span data-testid="org-count">{organizations.length}</span>
      <span data-testid="current">{currentOrg?.name ?? "none"}</span>
      <span data-testid="admin">{String(isPlatformAdmin)}</span>
      <span data-testid="view-all">{String(viewAll)}</span>
      <span data-testid="org-id">{orgId ?? "undefined"}</span>
    </div>
  );
}

function OrgSwitcher() {
  const { switchOrg, organizations } = useOrg();
  return (
    <div>
      {organizations.map((o) => (
        <button key={o.id} onClick={() => switchOrg(o.id)}>
          {o.name}
        </button>
      ))}
      <button onClick={() => switchOrg("__all__")}>All</button>
      <OrgDisplay />
    </div>
  );
}

describe("OrgContext", () => {
  describe("with platform admin session", () => {
    beforeEach(() => {
      mockSession = {
        user: { name: "Rob", email: "rob@test.ai" },
        isPlatformAdmin: true,
        organizations: ORGS,
      };
    });

    it("defaults platform admin to viewAll", () => {
      render(
        <OrgProvider>
          <OrgDisplay />
        </OrgProvider>,
      );
      expect(screen.getByTestId("view-all").textContent).toBe("true");
      expect(screen.getByTestId("org-id").textContent).toBe("undefined");
    });

    it("shows all organizations", () => {
      render(
        <OrgProvider>
          <OrgDisplay />
        </OrgProvider>,
      );
      expect(screen.getByTestId("org-count").textContent).toBe("2");
      expect(screen.getByTestId("admin").textContent).toBe("true");
    });

    it("defaults platform admin with no org rows to viewAll", () => {
      mockSession = {
        user: { name: "Rob", email: "rob@test.ai" },
        isPlatformAdmin: true,
        organizations: [],
      };
      render(
        <OrgProvider>
          <OrgDisplay />
        </OrgProvider>,
      );
      expect(screen.getByTestId("view-all").textContent).toBe("true");
      expect(screen.getByTestId("org-id").textContent).toBe("undefined");
      expect(localStore["leo_selected_org"]).toBe("__all__");
    });
  });

  describe("with standard user session", () => {
    beforeEach(() => {
      mockSession = {
        user: { name: "Ben", email: "ben@nhs.net" },
        isPlatformAdmin: false,
        organizations: [ORGS[1]],
      };
    });

    it("auto-selects single org", () => {
      render(
        <OrgProvider>
          <OrgDisplay />
        </OrgProvider>,
      );
      expect(screen.getByTestId("current").textContent).toBe("Practice B");
      expect(screen.getByTestId("org-id").textContent).toBe("org-2");
      expect(screen.getByTestId("view-all").textContent).toBe("false");
    });
  });

  describe("with no session", () => {
    beforeEach(() => {
      mockSession = null;
    });

    it("shows empty state", () => {
      render(
        <OrgProvider>
          <OrgDisplay />
        </OrgProvider>,
      );
      expect(screen.getByTestId("org-count").textContent).toBe("0");
      expect(screen.getByTestId("current").textContent).toBe("none");
    });
  });

  describe("switching orgs", () => {
    beforeEach(() => {
      mockSession = {
        user: { name: "Rob", email: "rob@test.ai" },
        isPlatformAdmin: true,
        organizations: ORGS,
      };
    });

    it("switches to a specific org", async () => {
      const user = userEvent.setup();
      render(
        <OrgProvider>
          <OrgSwitcher />
        </OrgProvider>,
      );

      await user.click(screen.getByRole("button", { name: "Practice A" }));
      expect(screen.getByTestId("current").textContent).toBe("Practice A");
      expect(screen.getByTestId("org-id").textContent).toBe("org-1");
      expect(screen.getByTestId("view-all").textContent).toBe("false");
    });

    it("switches back to all", async () => {
      const user = userEvent.setup();
      render(
        <OrgProvider>
          <OrgSwitcher />
        </OrgProvider>,
      );

      await user.click(screen.getByRole("button", { name: "Practice A" }));
      expect(screen.getByTestId("view-all").textContent).toBe("false");

      await user.click(screen.getByRole("button", { name: "All" }));
      expect(screen.getByTestId("view-all").textContent).toBe("true");
      expect(screen.getByTestId("org-id").textContent).toBe("undefined");
    });

    it("persists selection to localStorage", async () => {
      const user = userEvent.setup();
      render(
        <OrgProvider>
          <OrgSwitcher />
        </OrgProvider>,
      );

      await user.click(screen.getByRole("button", { name: "Practice B" }));
      expect(localStore["leo_selected_org"]).toBe("org-2");
    });
  });

  it("throws when useOrg called outside provider", () => {
    const spy = jest.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<OrgDisplay />)).toThrow(
      "useOrg must be used within OrgProvider",
    );
    spy.mockRestore();
  });
});
