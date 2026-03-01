import React from "react";
import { render, screen } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";

const theme = createTheme();

const ORGS = [
  { id: "org-1", name: "Practice A", odsCode: "A001" },
  { id: "org-2", name: "WOODBROOK MEDICAL CENTRE", odsCode: "C82070" },
];

const mockSwitchOrg = jest.fn();

let mockOrgCtx: any = {
  currentOrg: null,
  organizations: ORGS,
  isPlatformAdmin: true,
  switchOrg: mockSwitchOrg,
  viewAll: true,
  setViewAll: jest.fn(),
};

let mockSession: any = {
  user: { name: "Rob Smith", email: "rob@test.ai", image: null },
  isPlatformAdmin: true,
  organizations: ORGS,
};

let mockPathname = "/dashboard";

jest.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    session: mockSession,
    status: "authenticated",
    signIn: jest.fn(),
    signOut: jest.fn(),
    refetch: jest.fn(),
  }),
  AuthProvider: ({ children }: any) => children,
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => mockPathname,
  useParams: () => ({}),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/context/OrgContext", () => ({
  useOrg: () => mockOrgCtx,
  OrgProvider: ({ children }: any) => children,
}));

jest.mock("@/context/PipelineContext", () => ({
  usePipeline: () => ({
    running: false,
    status: null,
    live: null,
    result: null,
    error: null,
    workerStates: {},
    start: jest.fn(),
    cancel: jest.fn(),
  }),
}));

import AppShell from "../AppShell";

function renderShell(children: React.ReactNode = <div>child</div>) {
  return render(
    <ThemeProvider theme={theme}>
      <AppShell>{children}</AppShell>
    </ThemeProvider>,
  );
}

describe("AppShell — Tenant Switcher", () => {
  beforeEach(() => {
    mockSwitchOrg.mockClear();
    mockPathname = "/dashboard";
    mockOrgCtx = {
      currentOrg: null,
      organizations: ORGS,
      isPlatformAdmin: true,
      switchOrg: mockSwitchOrg,
      viewAll: true,
      setViewAll: jest.fn(),
    };
  });

  it("renders ORGANISATION label when orgs are present", () => {
    renderShell();
    expect(screen.getByText("ORGANISATION")).toBeInTheDocument();
  });

  it("renders org selector for platform admin", () => {
    renderShell();
    const select = screen.getByRole("combobox");
    expect(select).toBeInTheDocument();
  });

  it("does not show tenant switcher when no orgs", () => {
    mockOrgCtx = { ...mockOrgCtx, organizations: [] };
    renderShell();
    expect(screen.queryByText("ORGANISATION")).not.toBeInTheDocument();
  });

  it("renders nav items", () => {
    renderShell();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Patients")).toBeInTheDocument();
    expect(screen.getByText("Safety Netting")).toBeInTheDocument();
    expect(screen.getByText("Reports")).toBeInTheDocument();
  });

  it("renders user info in sidebar", () => {
    renderShell();
    expect(screen.getByText("Rob Smith")).toBeInTheDocument();
  });

  it("renders children", () => {
    renderShell(<div>test-child-content</div>);
    expect(screen.getByText("test-child-content")).toBeInTheDocument();
  });

  it("hides sidebar on public pages", () => {
    mockPathname = "/";
    renderShell(<div>public</div>);
    expect(screen.queryByText("ORGANISATION")).not.toBeInTheDocument();
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
    expect(screen.getByText("public")).toBeInTheDocument();
  });

  it("hides sidebar on sign-in page", () => {
    mockPathname = "/sign-in";
    renderShell(<div>sign-in-page</div>);
    expect(screen.queryByText("ORGANISATION")).not.toBeInTheDocument();
    expect(screen.getByText("sign-in-page")).toBeInTheDocument();
  });
});
