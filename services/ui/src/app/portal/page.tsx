"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import ApartmentOutlinedIcon from "@mui/icons-material/ApartmentOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";
import CreditCardOutlinedIcon from "@mui/icons-material/CreditCardOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import AuthConfig from "@/components/tenant/AuthConfig";
import OrgManagement from "@/components/tenant/OrgManagement";
import OrgDrawer from "@/components/tenant/OrgDrawer";
import UserManagement from "@/components/tenant/UserManagement";
import SubOrgManagement from "@/components/tenant/SubOrgManagement";
import SubscriptionPanel from "@/components/tenant/SubscriptionPanel";
import { useAuth } from "@/lib/authContext";
import type { OrgGraphNode } from "@/lib/api/admin";
import type { Org } from "@/lib/api/admin";

// Lazy-load the heavy graph component (avoids SSR issues with React Flow)
const OrgGraph = dynamic(() => import("@/components/tenant/OrgGraph"), {
  ssr: false,
  loading: () => (
    <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
      <CircularProgress />
    </Box>
  ),
});

// ------------------------------------------------------------------
// Tab definitions — filtered by role in the component
// ------------------------------------------------------------------

const ALL_TABS = [
  {
    value: "overview",
    label: "Overview",
    icon: <DashboardOutlinedIcon fontSize="small" />,
    desc: "Summary of your organisation, subscription status, and recent activity.",
    adminOnly: false,
    orgAdminOnly: false,
  },
  {
    value: "suborgs",
    label: "Sub-Organisations",
    icon: <AccountTreeOutlinedIcon fontSize="small" />,
    desc: "Onboard and manage sub-organisations within your hierarchy.",
    adminOnly: false,
    orgAdminOnly: false,
  },
  {
    value: "orgs",
    label: "All Organisations",
    icon: <ApartmentOutlinedIcon fontSize="small" />,
    desc: "Manage all GP practices, ICBs, PCNs, and Cancer Alliances in the system.",
    adminOnly: true,
    orgAdminOnly: false,
  },
  {
    value: "graph",
    label: "Org Graph",
    icon: <HubOutlinedIcon fontSize="small" />,
    desc: "Interactive hierarchy graph of all organisations — Cancer Alliances, ICBs, PCNs, and GP practices. Click any node to manage it.",
    adminOnly: true,
    orgAdminOnly: false,
  },
  {
    value: "users",
    label: "People & Groups",
    icon: <PeopleAltOutlinedIcon fontSize="small" />,
    desc: "Add or remove people and organise them into groups.",
    adminOnly: false,
    orgAdminOnly: false,
  },
  {
    value: "auth",
    label: "Login & Security",
    icon: <LockOutlinedIcon fontSize="small" />,
    desc: "Control session settings and see who is currently signed in.",
    adminOnly: false,
    orgAdminOnly: false,
  },
  {
    value: "subscription",
    label: "Subscription",
    icon: <CreditCardOutlinedIcon fontSize="small" />,
    desc: "View your subscription tier, credit balance, and usage.",
    adminOnly: false,
    orgAdminOnly: true,   // org admins only — platform admins manage billing internally
  },
];

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

export default function PortalPage() {
  const { session, status } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState("overview");
  const [graphSelectedOrg, setGraphSelectedOrg] = useState<Org | null>(null);

  const isPlatformAdmin = session?.isPlatformAdmin ?? false;
  // An org admin has at least one organization in their session and is not a platform admin
  const isOrgAdmin = !isPlatformAdmin && (session?.organizations?.length ?? 0) > 0;
  const hasAccess = isPlatformAdmin || isOrgAdmin;

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/sign-in");
    } else if (status === "authenticated" && !hasAccess) {
      router.replace("/care/dashboard");
    }
  }, [status, hasAccess, router]);

  if (status === "loading") {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 300 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!hasAccess) return null;

  const visibleTabs = ALL_TABS.filter((t) => {
    if (t.adminOnly && !isPlatformAdmin) return false;
    if (t.orgAdminOnly && isPlatformAdmin) return false;
    return true;
  });

  const currentTab = visibleTabs.find((t) => t.value === tab) ?? visibleTabs[0];

  // Ensure selected tab is visible (e.g. after role change)
  const activeTab = visibleTabs.find((t) => t.value === tab)
    ? tab
    : visibleTabs[0]?.value ?? "overview";

  const pageTitle = isPlatformAdmin ? "Platform Management" : "Organisation Portal";
  const pageSubtitle = isPlatformAdmin
    ? "Manage all tenants, organisations, users, and platform security settings."
    : "Manage your organisation, sub-organisations, users, and subscription.";

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: "auto" }}>
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
        {pageTitle}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        {pageSubtitle}
      </Typography>

      {isPlatformAdmin && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You are signed in as a platform administrator and can see all organisations and users.
        </Alert>
      )}

      <Tabs
        value={activeTab}
        onChange={(_, v) => setTab(v)}
        sx={{ mb: 1, borderBottom: 1, borderColor: "divider" }}
        variant="scrollable"
        scrollButtons="auto"
      >
        {visibleTabs.map((t) => (
          <Tab
            key={t.value}
            value={t.value}
            label={t.label}
            icon={t.icon}
            iconPosition="start"
            sx={{ textTransform: "none", fontWeight: 500, minHeight: 48 }}
          />
        ))}
      </Tabs>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {currentTab?.desc ?? ""}
      </Typography>

      {activeTab === "overview" && (
        <OverviewPanel isPlatformAdmin={isPlatformAdmin} session={session} />
      )}
      {activeTab === "suborgs" && <SubOrgManagement isPlatformAdmin={isPlatformAdmin} />}
      {activeTab === "orgs" && <OrgManagement />}
      {activeTab === "graph" && (
        <Box sx={{ height: "calc(100vh - 280px)", minHeight: 600, display: "flex", flexDirection: "column" }}>
          <OrgGraph
            onNodeClick={(node: OrgGraphNode) => {
              // Map OrgGraphNode → minimal Org shape for OrgDrawer
              setGraphSelectedOrg({
                id: node.id,
                name: node.name,
                short_name: node.short_name,
                odsCode: node.odsCode,
                type: node.type,
                ods_sync_status: node.ods_sync_status,
                ods_parent_ods_code: node.ods_parent_ods_code,
                ods_address: node.ods_address,
                onboarding_status: node.onboarding_status,
                patient_count: node.patient_count ?? 0,
                labels: [],
                parent_id: undefined,
                parent_name: undefined,
                alliance_id: undefined,
                alliance_name: undefined,
                pcn_id: undefined,
                pcn_name: undefined,
                entra_tenant_id: undefined,
                ods_discrepancy: undefined,
                ods_sync_last_checked: undefined,
                subscription: undefined,
              } as Org);
            }}
          />
          <OrgDrawer
            org={graphSelectedOrg}
            onClose={() => setGraphSelectedOrg(null)}
            onChanged={() => setGraphSelectedOrg(null)}
          />
        </Box>
      )}
      {activeTab === "users" && <UserManagement />}
      {activeTab === "auth" && <AuthConfig />}
      {activeTab === "subscription" && (
        <SubscriptionPanel orgId={session?.organizations?.[0]?.id} />
      )}
    </Box>
  );
}

// ------------------------------------------------------------------
// Inline overview panel (simple stats summary)
// ------------------------------------------------------------------

function OverviewPanel({
  isPlatformAdmin,
  session,
}: {
  isPlatformAdmin: boolean;
  session: ReturnType<typeof useAuth>["session"];
}) {
  const orgs = session?.organizations ?? [];
  return (
    <Box>
      {!isPlatformAdmin && orgs.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle1" fontWeight={600}>
            {orgs[0].name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            ODS code: {orgs[0].odsCode ?? "—"} · Type: {orgs[0].type ?? "—"}
          </Typography>
        </Box>
      )}
      {isPlatformAdmin && (
        <Typography variant="body2" color="text.secondary">
          Use the tabs above to manage tenants, organisations, users, and platform security.
        </Typography>
      )}
      {!isPlatformAdmin && (
        <Typography variant="body2" color="text.secondary">
          Use the tabs above to manage your sub-organisations, invite users, and view your subscription.
        </Typography>
      )}
    </Box>
  );
}
