/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-10218528
 *   Also implements: DO-8972ED05, DO-9A5C65AF, DO-C4EC82F9
 *   DI: DI-5E7E8CEF, DI-B0832A64, DI-BE09736F, DI-F0846E55, DI-FAF97A8C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-10218528")
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import UnauthorizedScreen from "@/components/UnauthorizedScreen";
import { sessionHasLeoAccess } from "@/lib/sessionAccess";
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import FormControl from "@mui/material/FormControl";
import Badge from "@mui/material/Badge";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import HealthAndSafetyOutlinedIcon from "@mui/icons-material/HealthAndSafetyOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import TimelineOutlinedIcon from "@mui/icons-material/TimelineOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import GroupWorkOutlinedIcon from "@mui/icons-material/GroupWorkOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import LibraryBooksOutlinedIcon from "@mui/icons-material/LibraryBooksOutlined";
import SpaOutlinedIcon from "@mui/icons-material/SpaOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import MenuIcon from "@mui/icons-material/Menu";
import AdminPanelSettingsOutlinedIcon from "@mui/icons-material/AdminPanelSettingsOutlined";
import BusinessOutlinedIcon from "@mui/icons-material/BusinessOutlined";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import ModelTrainingOutlinedIcon from "@mui/icons-material/ModelTrainingOutlined";
import PaidOutlinedIcon from "@mui/icons-material/PaidOutlined";
import SupportAgentOutlinedIcon from "@mui/icons-material/SupportAgentOutlined";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined";
import BuildOutlinedIcon from "@mui/icons-material/BuildOutlined";
import ExploreOutlinedIcon from "@mui/icons-material/ExploreOutlined";
import InboxOutlinedIcon from "@mui/icons-material/InboxOutlined";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import PushPinOutlinedIcon from "@mui/icons-material/PushPinOutlined";
import PushPinIcon from "@mui/icons-material/PushPin";
import LinearProgress from "@mui/material/LinearProgress";
import Chip from "@mui/material/Chip";
import { useAuth } from "@/lib/authContext";
import { useIdleLogout } from "@/lib/useIdleLogout";
import Avatar from "@mui/material/Avatar";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Menu from "@mui/material/Menu";
import { useDemoMode } from "@/context/DemoModeContext";
import { useOrg } from "@/context/OrgContext";
import { maskOrgName } from "@/lib/demoMode";
import { compareStringsNatural, orgSortLabel } from "@/lib/sortNatural";
import ImpersonationBanner from "@/components/ImpersonationBanner";
import {
  drawerPaperSx,
  fullNavButtonSx,
  fullNavIconSx,
  mobileAppBarSx,
  NAV_ACCENT,
  NAV_HAIRLINE,
  NAV_HOVER,
  NAV_INK,
  NAV_INK_MUTED,
  NAV_INK_STRONG,
  railButtonSx,
  railIconSx,
} from "@/components/app-shell/drawerChrome";
import { LeoLogo, LeoO, LeoSplash } from "@leo/design-system";

const DRAWER_WIDTH = 240;
const RAIL_WIDTH = 56;

const SIDEBAR_PREF_STORAGE_KEY = "leo-sidebar-pref";

/** Lets users reach portaled menus without the drawer snapping shut mid-move */
const RAIL_HOVER_LEAVE_MS = 240;

type SidebarPref = "follow-breakpoint" | "expanded" | "collapsed";

type NavItem = {
  label: string;
  path: string;
  icon: React.ReactElement;
  badgeKey?: string;
  activePrefix?: string[];
  adminOnly?: boolean;
  hiddenForScopeTypes?: string[];
};

const CARE_NAV_ITEMS: NavItem[] = [
  { label: "Overview", path: "/care/dashboard", icon: <DashboardOutlinedIcon /> },
  { label: "Clinical Audit", path: "/care/audit", icon: <AssignmentOutlinedIcon />, activePrefix: ["/care/audit", "/audit"] },
  { label: "Patients", path: "/care/patients", icon: <PeopleOutlineIcon />, hiddenForScopeTypes: ["icb", "alliance"] },
  { label: "Safety Netting", path: "/care/safety-netting", icon: <HealthAndSafetyOutlinedIcon />, hiddenForScopeTypes: ["icb", "alliance"] },
  { label: "Reports", path: "/care/reports", icon: <AssessmentOutlinedIcon /> },
  { label: "Benchmarks", path: "/care/benchmarks", icon: <AssessmentOutlinedIcon /> },
  { label: "Cohorts", path: "/care/cohorts", icon: <GroupWorkOutlinedIcon /> },
  { label: "Wellbeing Hub", path: "/care/wellbeing", icon: <SpaOutlinedIcon /> },
  { label: "Portal", path: "/care/portal", icon: <AdminPanelSettingsOutlinedIcon /> },
  { label: "Settings", path: "/settings", icon: <SettingsOutlinedIcon /> },
];

const ADMIN_NAV_ITEMS: NavItem[] = [
  {
    label: "Console",
    path: "/admin/console",
    icon: <AutoAwesomeOutlinedIcon />,
    activePrefix: ["/admin/console", "/admin/operations"],
  },
  {
    label: "Knowledge",
    path: "/admin/knowledge",
    icon: <StorageOutlinedIcon />,
    // Phase 2 IA merge (DI-LEO-AI-135): /admin/clinical has been folded
    // into Knowledge as three extra tabs. Legacy routes still surface
    // here so the nav highlight stays correct while the redirect runs.
    activePrefix: [
      "/admin/knowledge",
      "/admin/gold-dataset",
      "/admin/surface-forms",
      "/admin/context-rules",
      "/admin/prompts",
      "/admin/guidance",
      "/admin/clinical",
      "/admin/pathways",
      "/admin/domains",
      "/admin/terminology",
    ],
  },
  {
    label: "Pathway Explorer",
    path: "/admin/pathway-explorer",
    icon: <ExploreOutlinedIcon />,
    activePrefix: ["/admin/pathway-explorer"],
  },
  {
    label: "Platform",
    path: "/admin/platform",
    icon: <BuildOutlinedIcon />,
    activePrefix: [
      "/admin/platform",
      "/admin/billing",
      "/admin/models",
      "/admin/data-quality",
    ],
    adminOnly: true,
  },
  {
    label: "Audit Templates",
    path: "/admin/audit-templates",
    icon: <AssignmentOutlinedIcon />,
    activePrefix: ["/admin/audit-templates"],
    adminOnly: true,
  },
  {
    label: "Encounters",
    path: "/admin/encounters",
    icon: <TimelineOutlinedIcon />,
    activePrefix: ["/admin/encounters", "/care/encounters", "/care/pathways", "/pathways"],
    adminOnly: true,
  },
  { label: "Users", path: "/admin/users", icon: <PeopleOutlineIcon /> },
  { label: "Portal", path: "/admin/portal", icon: <AdminPanelSettingsOutlinedIcon /> },
  { label: "Support", path: "/admin/support", icon: <SupportAgentOutlinedIcon /> },
];

function isEditorRoute(_pathname: string): boolean {
  return false;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, status, signIn, signOut, refetch: refetchAuth } = useAuth();
  const { currentOrg, organizations, isPlatformAdmin, switchOrg, viewAll } = useOrg();
  const { isDemoMode } = useDemoMode();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const prefersCollapsedDesktop = useMediaQuery(theme.breakpoints.down("lg"), { defaultMatches: false });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarPref, setSidebarPref] = useState<SidebarPref>("follow-breakpoint");
  const [orgMenuAnchor, setOrgMenuAnchor] = useState<HTMLElement | null>(null);
  const [railHoverExpanded, setRailHoverExpanded] = useState(false);
  const railHoverLeaveTimerRef = useRef<number | null>(null);
  // Default shell is care; admin is restored from localStorage after mount (SSR-safe).
  const [uiMode, setUiMode] = useState<"care" | "admin">("care");

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("leo-ui-mode");
      if (raw === "admin") {
        setUiMode("admin");
        return;
      }
      if (raw === "legacy" || (raw != null && raw !== "care" && raw !== "admin")) {
        window.localStorage.setItem("leo-ui-mode", "care");
      }
      setUiMode("care");
    } catch {
      setUiMode("care");
    }
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(SIDEBAR_PREF_STORAGE_KEY);
      if (raw === "expanded" || raw === "collapsed" || raw === "follow-breakpoint") {
        setSidebarPref(raw);
      }
    } catch {
      // ignore
    }
  }, []);

  const idleMinutes = status === "authenticated" ? (session?.idleTimeoutMinutes ?? 0) : 0;
  const { isWarning, keepAlive } = useIdleLogout(idleMinutes, signOut);

  const badgeCounts: Record<string, number> = {};

  const baseNavItems = uiMode === "care" ? CARE_NAV_ITEMS : ADMIN_NAV_ITEMS;

  // DI-LEO-AI-138: add a "My Work" entry that surfaces the unified task
  // queue. The role-first shell is the shipped experience (Phase 6
  // removed the rollout flag), so staff always see the queue promoted
  // to the top and every other role still reaches it near the end.
  const selectedRole = session?.selectedRole ?? null;
  const isImpersonating =
    isPlatformAdmin &&
    selectedRole !== null &&
    selectedRole !== "administrator";

  const exitImpersonation = useCallback(async () => {
    await fetch("/api/auth/session/role", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "administrator" }),
    });
    await refetchAuth();
    router.push("/");
  }, [refetchAuth, router]);

  const workNavItem: NavItem = {
    label: "My Work",
    path: "/work",
    icon: <InboxOutlinedIcon />,
    activePrefix: ["/work"],
  };
  const navItemsForMode: NavItem[] =
    selectedRole === "staff"
      ? [workNavItem, ...baseNavItems]
      : [...baseNavItems, workNavItem];

  const currentScopeType = currentOrg?.scopeType ?? null;
  const visibleNavItems = navItemsForMode.filter((item) => {
    if (item.adminOnly && !isPlatformAdmin) return false;
    if (item.hiddenForScopeTypes && currentScopeType && item.hiddenForScopeTypes.includes(currentScopeType)) return false;
    return true;
  });

  const sortedOrganizations = useMemo(
    () =>
      [...organizations].sort((a, b) =>
        compareStringsNatural(orgSortLabel(a), orgSortLabel(b)),
      ),
    [organizations],
  );

  const handleNav = useCallback(
    (path: string) => {
      router.push(path);
      if (isMobile) setMobileOpen(false);
    },
    [router, isMobile],
  );

  const toggleUiMode = useCallback(() => {
    setUiMode((prev) => {
      const next = prev === "care" ? "admin" : "care";
      if (typeof window !== "undefined") {
        window.localStorage.setItem("leo-ui-mode", next);
      }
      return next;
    });
  }, []);

  const persistSidebarPref = useCallback((pref: SidebarPref) => {
    setSidebarPref(pref);
    try {
      window.localStorage.setItem(SIDEBAR_PREF_STORAGE_KEY, pref);
    } catch {
      // ignore
    }
  }, []);

  const isEditor = isEditorRoute(pathname);
  const dockCollapsed =
    !isMobile &&
    !isEditor &&
    (sidebarPref === "collapsed" ||
      (sidebarPref === "follow-breakpoint" && prefersCollapsedDesktop));

  const collapseChromeFromMainClick = useCallback(() => {
    if (isMobile) {
      if (mobileOpen) setMobileOpen(false);
      return;
    }
    if (isEditor) return;
    if (dockCollapsed) return;
    persistSidebarPref("collapsed");
  }, [dockCollapsed, isEditor, isMobile, mobileOpen, persistSidebarPref]);

  useEffect(() => {
    if (!dockCollapsed) setRailHoverExpanded(false);
  }, [dockCollapsed]);

  useEffect(() => {
    return () => {
      if (railHoverLeaveTimerRef.current !== null) {
        window.clearTimeout(railHoverLeaveTimerRef.current);
        railHoverLeaveTimerRef.current = null;
      }
    };
  }, []);

  // Listing public exceptions is safer than enumerating every protected path.
  const isPublicPage =
    pathname === "/" ||
    pathname === "/sign-in" ||
    pathname?.startsWith("/auth/");
  const isProtected = !isPublicPage;

  // Block ALL protected content until auth state is known.
  // This prevents a hacker briefly seeing page content during the loading window.
  if (status === "loading" && isProtected) {
    return <LeoSplash />;
  }

  // No valid session on a protected route -- show the full unauthorized screen,
  // do NOT render the page or the nav drawer.
  if (status === "unauthenticated" && isProtected) {
    return <UnauthorizedScreen onSignIn={signIn} />;
  }

  // Authenticated Microsoft user with no LEO role (and not platform admin):
  // block the shell and page children so clinical data never flashes.
  if (
    status === "authenticated" &&
    isProtected &&
    !sessionHasLeoAccess(session)
  ) {
    return (
      <UnauthorizedScreen variant="no-access" onSignOut={() => void signOut()} />
    );
  }

  if (isPublicPage) {
    return (
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        {children}
      </Box>
    );
  }

  const drawerShowsFullChrome =
    !isMobile && !isEditor && (!dockCollapsed || railHoverExpanded);

  const currentWidth =
    isMobile ? DRAWER_WIDTH : isEditor ? RAIL_WIDTH : drawerShowsFullChrome ? DRAWER_WIDTH : RAIL_WIDTH;

  const homeRoute = uiMode === "admin" ? "/admin/console" : "/care/dashboard";

  const sidebarNavRail = (
    <Box component="nav" aria-label="Main navigation" sx={{ width: "100%" }}>
      <List sx={{ p: 0, width: "100%" }}>
        {visibleNavItems.map((item) => {
          const isActive = pathname
            ? (item.activePrefix
                ? item.activePrefix.some((p) => pathname === p || pathname.startsWith(p + "/"))
                : pathname === item.path || pathname.startsWith(item.path + "/"))
            : false;
          const badgeCount = item.badgeKey ? (badgeCounts[item.badgeKey] ?? 0) : 0;
          return (
            <Tooltip key={item.path} title={item.label} placement="right">
              <ListItemButton
                selected={isActive}
                onClick={() => handleNav(item.path)}
                aria-current={isActive ? "page" : undefined}
                aria-label={item.label}
                sx={railButtonSx(isActive)}
              >
                <ListItemIcon sx={railIconSx(isActive)}>
                  <Badge badgeContent={badgeCount} color="warning" max={99}>
                    {item.icon}
                  </Badge>
                </ListItemIcon>
              </ListItemButton>
            </Tooltip>
          );
        })}
      </List>
    </Box>
  );

  const railContent = (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", height: "100%", py: 1.5 }}>
      <Tooltip title="LEO by Mizaic - go to home" placement="right">
        <IconButton
          aria-label="LEO by Mizaic - go to home"
          onClick={() => handleNav(homeRoute)}
          sx={{ width: 40, height: 40, mb: 1.5, p: 0.5, color: NAV_INK_STRONG }}
        >
          <LeoO size={26} variant="dark" spinning spinDuration={2.4} title="LEO" />
        </IconButton>
      </Tooltip>
      <Divider sx={{ width: "80%", mb: 1, borderColor: NAV_HAIRLINE }} />
      {sidebarNavRail}
      {session?.user && (
        <Box sx={{ mt: "auto", display: "flex", flexDirection: "column", alignItems: "center", gap: 0.5, pb: 0.5 }}>
          <Tooltip title={session.user.name ?? "User"} placement="right">
            <Avatar
              src={session.user.image ?? undefined}
              sx={{ width: 28, height: 28, fontSize: "0.7rem", bgcolor: "primary.main" }}
            >
              {session.user.name?.charAt(0) ?? "U"}
            </Avatar>
          </Tooltip>
          <Tooltip title="Sign out" placement="right">
            <IconButton aria-label="Sign out" size="small" onClick={() => signOut()} sx={{ color: NAV_INK }}>
              <LogoutIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </Box>
  );

  const compactDrawerContent = (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", height: "100%", py: 1.5 }}>
      <Tooltip title="LEO by Mizaic - go to home" placement="right">
        <IconButton
          aria-label="LEO by Mizaic - go to home"
          onClick={() => handleNav(homeRoute)}
          sx={{ width: 40, height: 40, mb: 0.5, p: 0.5, color: NAV_INK_STRONG }}
        >
          <LeoO size={26} variant="dark" spinning spinDuration={2.4} title="LEO" />
        </IconButton>
      </Tooltip>
      <Tooltip title="Expand sidebar" placement="right">
        <IconButton
          aria-label="Expand sidebar"
          size="small"
          onClick={() => persistSidebarPref("expanded")}
          sx={{ mb: 1, color: NAV_INK }}
        >
          <ChevronRightIcon sx={{ fontSize: 20 }} />
        </IconButton>
      </Tooltip>
      <Divider sx={{ width: "80%", mb: 1, borderColor: NAV_HAIRLINE }} />
      {(organizations.length > 0 || isPlatformAdmin) && (
        <>
          <Tooltip title="Select organisation" placement="right">
            <IconButton
              aria-label="Select organisation"
              aria-haspopup="true"
              aria-expanded={orgMenuAnchor ? "true" : "false"}
              size="small"
              sx={{ mb: 0.5, color: NAV_INK }}
              onClick={(e) => setOrgMenuAnchor(e.currentTarget)}
            >
              <BusinessOutlinedIcon sx={{ color: NAV_INK }} />
            </IconButton>
          </Tooltip>
          <Menu
            anchorEl={orgMenuAnchor}
            open={Boolean(orgMenuAnchor)}
            onClose={() => {
              setOrgMenuAnchor(null);
              setRailHoverExpanded(false);
            }}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "left" }}
          >
            {isPlatformAdmin && (
              <MenuItem
                selected={viewAll}
                onClick={() => {
                  switchOrg("__all__");
                  setOrgMenuAnchor(null);
                }}
              >
                All Organisations
              </MenuItem>
            )}
            {sortedOrganizations.map((org) => (
              <MenuItem
                key={org.id}
                selected={!viewAll && currentOrg?.id === org.id}
                onClick={() => {
                  switchOrg(org.id);
                  setOrgMenuAnchor(null);
                }}
              >
                {isDemoMode ? maskOrgName(org.shortName || org.name) : org.shortName || org.name}
              </MenuItem>
            ))}
          </Menu>
        </>
      )}
      {(organizations.length > 0 || isPlatformAdmin) && (
        <Divider sx={{ width: "80%", mb: 1, borderColor: NAV_HAIRLINE }} />
      )}
      {sidebarNavRail}
      {isPlatformAdmin && (
        <Box sx={{ mt: 1, display: "flex", justifyContent: "center", width: "100%" }}>
          <Tooltip title={uiMode === "care" ? "Switch to Admin" : "Switch to Care"} placement="right">
            <IconButton
              aria-label={uiMode === "care" ? "Switch to Admin" : "Switch to Care"}
              size="small"
              onClick={toggleUiMode}
              sx={{ color: NAV_INK }}
            >
              <SwapHorizIcon />
            </IconButton>
          </Tooltip>
        </Box>
      )}
      {session?.user && (
        <Box sx={{ mt: "auto", display: "flex", flexDirection: "column", alignItems: "center", gap: 0.5, pb: 0.5 }}>
          <Tooltip title={session.user.name ?? "User"} placement="right">
            <Avatar
              src={session.user.image ?? undefined}
              sx={{ width: 28, height: 28, fontSize: "0.7rem", bgcolor: "primary.main" }}
            >
              {session.user.name?.charAt(0) ?? "U"}
            </Avatar>
          </Tooltip>
          <Tooltip title="Sign out" placement="right">
            <IconButton aria-label="Sign out" size="small" onClick={() => signOut()} sx={{ color: NAV_INK }}>
              <LogoutIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </Box>
  );

  const fullDrawerContent = (
    <>
      <Box sx={{ px: 2.5, py: 2.5, display: "flex", alignItems: "center", gap: 1.5 }}>
        <IconButton
          aria-label="LEO by Mizaic - go to home"
          onClick={() => handleNav(homeRoute)}
          sx={{ p: 0.5, flex: 1, justifyContent: "flex-start", borderRadius: 1, color: NAV_INK_STRONG }}
        >
          <LeoLogo height={28} variant="dark" spinning spinDuration={2.4} />
        </IconButton>
        {!isMobile && !isEditor && (
          sidebarPref === "expanded" ? (
            <Tooltip title="Unpin sidebar">
              <IconButton
                aria-label="Unpin sidebar"
                size="small"
                onClick={() => persistSidebarPref("follow-breakpoint")}
                sx={{ flexShrink: 0, color: NAV_ACCENT }}
              >
                <PushPinIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </Tooltip>
          ) : dockCollapsed ? (
            <Tooltip title="Pin sidebar open">
              <IconButton
                aria-label="Pin sidebar open"
                size="small"
                onClick={() => persistSidebarPref("expanded")}
                sx={{ flexShrink: 0, color: NAV_INK }}
              >
                <PushPinOutlinedIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </Tooltip>
          ) : (
            <Tooltip title="Collapse sidebar">
              <IconButton
                aria-label="Collapse sidebar"
                size="small"
                onClick={() => persistSidebarPref("collapsed")}
                sx={{ flexShrink: 0, color: NAV_INK }}
              >
                <ChevronLeftIcon sx={{ fontSize: 20 }} />
              </IconButton>
            </Tooltip>
          )
        )}
      </Box>

      <Divider sx={{ borderColor: NAV_HAIRLINE }} />

      {(organizations.length > 0 || isPlatformAdmin) && (
        <Box sx={{ px: 1.5, py: 1.5 }}>
          <Box
            sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5 }}
            aria-hidden="true"
          >
            <BusinessOutlinedIcon sx={{ fontSize: 14, color: NAV_INK_MUTED }} />
            <Typography variant="caption" sx={{ color: NAV_INK_MUTED, fontWeight: 600, letterSpacing: 0.5 }}>
              ORGANISATION
            </Typography>
          </Box>
          <FormControl fullWidth size="small" data-testid="org-select-form-control">
            <InputLabel
              id="leo-org-select-label"
              sx={{
                position: "absolute",
                width: 1,
                height: 1,
                overflow: "hidden",
                whiteSpace: "nowrap",
                clip: "rect(0,0,0,0)",
                border: 0,
                padding: 0,
              }}
            >
              Select organisation
            </InputLabel>
            <Select
              id="leo-org-select"
              labelId="leo-org-select-label"
              value={viewAll ? "__all__" : (currentOrg?.id ?? "")}
              onChange={(e) => switchOrg(e.target.value as string)}
              displayEmpty
              sx={{
                fontSize: "0.9rem",
                bgcolor: NAV_HOVER,
                color: NAV_INK_STRONG,
                borderRadius: 2,
                "& .MuiSelect-select": { py: 0.75, px: 1.5 },
                "& fieldset": { borderColor: "transparent" },
                "&:hover fieldset": { borderColor: NAV_HAIRLINE + " !important" },
                "& .MuiSvgIcon-root": { color: NAV_INK },
              }}
            >
              {isPlatformAdmin && (
                <MenuItem value="__all__" sx={{ fontSize: "0.9rem" }}>
                  All Organisations
                </MenuItem>
              )}
              {sortedOrganizations.map((org) => (
                  <MenuItem key={org.id} value={org.id} sx={{ fontSize: "0.9rem" }}>
                    {isDemoMode
                      ? maskOrgName(org.shortName || org.name)
                      : org.shortName || org.name}
                  </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}

      <Divider sx={{ borderColor: NAV_HAIRLINE }} />

      <Box component="nav" aria-label="Main navigation">
        <List sx={{ px: 1, pt: 1 }}>
          {visibleNavItems.map((item) => {
            const isActive = pathname
              ? (item.activePrefix
                  ? item.activePrefix.some((p) => pathname === p || pathname.startsWith(p + "/"))
                  : pathname === item.path || pathname.startsWith(item.path + "/"))
              : false;
            const badgeCount = item.badgeKey ? (badgeCounts[item.badgeKey] ?? 0) : 0;
            return (
              <ListItem key={item.path} disablePadding>
                <ListItemButton
                  component={Link}
                  href={item.path}
                  selected={isActive}
                  onClick={() => { if (isMobile) setMobileOpen(false); }}
                  aria-current={isActive ? "page" : undefined}
                  sx={fullNavButtonSx(isActive)}
                >
                  <ListItemIcon sx={fullNavIconSx(isActive)}>
                    <Badge badgeContent={badgeCount} color="warning" max={99}>
                      {item.icon}
                    </Badge>
                  </ListItemIcon>
                  <ListItemText
                    primary={item.label}
                    primaryTypographyProps={{
                      fontWeight: isActive ? 600 : 400,
                      fontSize: "0.9rem",
                      color: isActive ? "inherit" : NAV_INK,
                    }}
                  />
                  {badgeCount > 0 && (
                    <Typography variant="caption" sx={{ bgcolor: "warning.main", color: "warning.contrastText", borderRadius: 10, px: 0.8, py: 0.2, fontWeight: 700, fontSize: "0.7rem" }}>
                      {badgeCount}
                    </Typography>
                  )}
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      </Box>

      {isPlatformAdmin && (
        <Box sx={{ px: 1.5, py: 1 }}>
          <Button
            fullWidth
            size="small"
            variant="outlined"
            startIcon={<SwapHorizIcon />}
            onClick={toggleUiMode}
            sx={{
              textTransform: "none",
              fontSize: "0.75rem",
              color: NAV_INK_STRONG,
              borderColor: NAV_HAIRLINE,
              "&:hover": { borderColor: NAV_INK, bgcolor: NAV_HOVER },
            }}
          >
            {uiMode === "care" ? "Switch to Admin" : "Switch to Care"}
          </Button>
        </Box>
      )}

      {session?.user && (
        <Box
          sx={{
            mt: "auto",
            p: 1.5,
            borderTop: "1px solid",
            borderColor: NAV_HAIRLINE,
            display: "flex",
            alignItems: "center",
            gap: 1,
          }}
        >
          <Avatar
            src={session.user.image ?? undefined}
            sx={{ width: 32, height: 32, fontSize: "0.8rem", bgcolor: "primary.main" }}
          >
            {session.user.name?.charAt(0) ?? "U"}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              variant="body2"
              sx={{ fontWeight: 600, fontSize: "0.8rem", color: NAV_INK_STRONG, lineHeight: 1.3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {session.user.name}
            </Typography>
          </Box>
          <Tooltip title="Sign out">
            <IconButton aria-label="Sign out" size="small" onClick={() => signOut()} sx={{ color: NAV_INK }}>
              <LogoutIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </>
  );

  const drawerChildren =
    isMobile ? fullDrawerContent : isEditor ? railContent : drawerShowsFullChrome ? fullDrawerContent : compactDrawerContent;

  const drawerPaperListeners =
    !isMobile && !isEditor && dockCollapsed
      ? {
          onMouseEnter: () => {
            if (railHoverLeaveTimerRef.current !== null) {
              window.clearTimeout(railHoverLeaveTimerRef.current);
              railHoverLeaveTimerRef.current = null;
            }
            setRailHoverExpanded(true);
          },
          onMouseLeave: () => {
            if (orgMenuAnchor) return;
            if (railHoverLeaveTimerRef.current !== null) {
              window.clearTimeout(railHoverLeaveTimerRef.current);
            }
            railHoverLeaveTimerRef.current = window.setTimeout(() => {
              setRailHoverExpanded(false);
              railHoverLeaveTimerRef.current = null;
            }, RAIL_HOVER_LEAVE_MS);
          },
        }
      : undefined;

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      {/* Idle timeout warning dialog */}
      <Dialog open={isWarning} disableEscapeKeyDown>
        <DialogTitle>Are you still there?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            You have not done anything for a while. You will be signed out in 2 minutes.
          </Typography>
          <Typography variant="body2" sx={{ mt: 1, color: "text.secondary" }}>
            Click &ldquo;Stay signed in&rdquo; to keep working.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => signOut()} color="error">Sign out now</Button>
          <Button variant="contained" onClick={keepAlive}>Stay signed in</Button>
        </DialogActions>
      </Dialog>
      {isMobile && (
        <AppBar
          position="fixed"
          elevation={0}
          sx={mobileAppBarSx}
        >
          <Toolbar variant="dense" sx={{ minHeight: 48 }}>
            <IconButton
              edge="start"
              aria-label="open navigation"
              onClick={() => setMobileOpen(true)}
              sx={{ color: NAV_INK_STRONG }}
            >
              <MenuIcon />
            </IconButton>
            <Box sx={{ ml: 1, display: "flex", alignItems: "center" }}>
              <LeoO size={24} variant="dark" spinning spinDuration={2.4} title="LEO" />
            </Box>
            <Typography variant="subtitle2" sx={{ ml: 1, fontWeight: 600 }}>LEO</Typography>
          </Toolbar>
        </AppBar>
      )}

      <Drawer
        variant={isMobile ? "temporary" : "permanent"}
        open={isMobile ? mobileOpen : true}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        PaperProps={drawerPaperListeners}
        sx={{
          width: isMobile ? DRAWER_WIDTH : currentWidth,
          flexShrink: 0,
          transition: "width 0.2s ease",
          "& .MuiDrawer-paper": {
            width: isMobile ? DRAWER_WIDTH : currentWidth,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            transition: "width 0.35s cubic-bezier(0.32, 0.72, 0, 1)",
            overflowX: "hidden",
            ...drawerPaperSx,
          },
        }}
      >
        {drawerChildren}
      </Drawer>

      <Box
        component="main"
        id="main-content"
        onClick={collapseChromeFromMainClick}
        sx={{
          flexGrow: 1,
          minWidth: 0,
          overflowX: "clip",
          mt: isMobile ? "48px" : 0,
          minHeight: "100vh",
          bgcolor: "background.default",
        }}
      >
        {isImpersonating && selectedRole && (
          <ImpersonationBanner
            selectedRole={selectedRole}
            onExit={exitImpersonation}
          />
        )}
        {uiMode === "admin" && <TrainingProgressBanner />}
        {children}
      </Box>
    </Box>
  );
}

// -- Training progress banner (shown in admin mode when a job is running) --

const PHASE_LABELS: Record<string, string> = {
  export: "Export",
  train: "Train",
  evaluate: "Evaluate",
  upload: "Upload",
  register: "Register",
};
const PHASE_ORDER = ["export", "train", "evaluate", "upload", "register"];

function _phaseProgress(phase: string): number {
  const idx = PHASE_ORDER.indexOf(phase);
  return idx < 0 ? 0 : Math.round(((idx + 1) / PHASE_ORDER.length) * 100);
}

function TrainingProgressBanner() {
  const [runningJob, setRunningJob] = useState<{
    job_id: string;
    phase: string;
    f1?: number;
    status: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const ACTIVE_INTERVAL_MS = 5000;
    const IDLE_INTERVAL_MS = 60000;

    const schedule = (delay: number) => {
      if (cancelled) return;
      timer = setTimeout(tick, delay);
    };

    const tick = async () => {
      let active: { job_id: string; phase: string; f1?: number; status: string } | null = null;
      try {
        if (typeof document !== "undefined" && document.visibilityState === "hidden") {
          // Skip polling when the tab is hidden; resume when visible.
          schedule(IDLE_INTERVAL_MS);
          return;
        }
        const res = await fetch("/api/training-worker/jobs");
        if (res.ok) {
          const data = await res.json();
          active = (data.jobs ?? data ?? []).find(
            (j: { status: string }) =>
              j.status === "running" ||
              j.status === "evaluating" ||
              j.status === "uploading"
          ) ?? null;
        }
      } catch {
        // ignore
      }
      if (cancelled) return;
      setRunningJob(active);
      schedule(active ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS);
    };

    const onVisibility = () => {
      if (typeof document === "undefined") return;
      if (document.visibilityState === "visible") {
        if (timer) clearTimeout(timer);
        schedule(0);
      }
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibility);
    }

    schedule(0);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibility);
      }
    };
  }, []);

  if (!runningJob) return null;

  const phase = runningJob.phase ?? "";
  const progress = _phaseProgress(phase);
  const phaseLabel = PHASE_LABELS[phase] ?? phase ?? "Running";

  return (
    <Box
      sx={{
        bgcolor: "primary.main",
        color: "primary.contrastText",
        px: 2,
        py: 0.5,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        minHeight: 36,
      }}
    >
      <Chip
        size="small"
        label={phaseLabel}
        sx={{
          bgcolor: "primary.dark",
          color: "primary.contrastText",
          fontWeight: 700,
          fontSize: "0.68rem",
          height: 20,
        }}
      />
      <Box sx={{ flex: 1 }}>
        <LinearProgress
          variant="determinate"
          value={progress}
          sx={{
            height: 4,
            borderRadius: 2,
            bgcolor: "rgba(255,255,255,0.25)",
            "& .MuiLinearProgress-bar": { bgcolor: "white" },
          }}
        />
      </Box>
      <Typography variant="caption" sx={{ whiteSpace: "nowrap", fontWeight: 500, fontSize: "0.72rem" }}>
        {runningJob.f1 != null ? `F1 ${(runningJob.f1 * 100).toFixed(1)}%` : "Training…"}
      </Typography>
      <Link href="/admin/console" style={{ color: "inherit", fontSize: "0.72rem", textDecoration: "underline" }}>
        View
      </Link>
    </Box>
  );
}
