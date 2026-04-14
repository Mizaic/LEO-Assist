"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import CircularProgress from "@mui/material/CircularProgress";
import UnauthorizedScreen from "@/components/UnauthorizedScreen";
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
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
import FormControl from "@mui/material/FormControl";
import Badge from "@mui/material/Badge";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import HealthAndSafetyOutlinedIcon from "@mui/icons-material/HealthAndSafetyOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import TimelineOutlinedIcon from "@mui/icons-material/TimelineOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
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
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import BuildOutlinedIcon from "@mui/icons-material/BuildOutlined";
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
import { useOrg } from "@/context/OrgContext";

const DRAWER_WIDTH = 240;
const RAIL_WIDTH = 56;

type NavItem = {
  label: string;
  path: string;
  icon: React.ReactElement;
  badgeKey?: string;
  activePrefix?: string[];
  adminOnly?: boolean;
};

const CARE_NAV_ITEMS: NavItem[] = [
  { label: "Overview", path: "/care/dashboard", icon: <DashboardOutlinedIcon /> },
  { label: "Clinical Audit", path: "/care/audit", icon: <AssignmentOutlinedIcon />, activePrefix: ["/care/audit", "/audit"] },
  { label: "Patients", path: "/care/patients", icon: <PeopleOutlineIcon /> },
  { label: "Encounters", path: "/care/encounters", icon: <TimelineOutlinedIcon />, activePrefix: ["/care/encounters", "/care/pathways", "/pathways"] },
  { label: "Safety Netting", path: "/care/safety-netting", icon: <HealthAndSafetyOutlinedIcon /> },
  { label: "Reports", path: "/care/reports", icon: <DescriptionOutlinedIcon /> },
  { label: "Measures", path: "/care/measures", icon: <BarChartOutlinedIcon /> },
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
    activePrefix: [
      "/admin/knowledge",
      "/admin/gold-dataset",
      "/admin/surface-forms",
      "/admin/context-rules",
      "/admin/prompts",
      "/admin/guidance",
    ],
  },
  {
    label: "Clinical",
    path: "/admin/clinical",
    icon: <LocalHospitalOutlinedIcon />,
    activePrefix: [
      "/admin/clinical",
      "/admin/pathways",
      "/admin/domains",
      "/admin/terminology",
    ],
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
  { label: "Users", path: "/admin/users", icon: <PeopleOutlineIcon /> },
  { label: "Portal", path: "/admin/portal", icon: <AdminPanelSettingsOutlinedIcon /> },
  { label: "Support", path: "/admin/support", icon: <SupportAgentOutlinedIcon /> },
];

function isEditorRoute(pathname: string): boolean {
  return (
    /^\/reports\/[^/]+\/edit/.test(pathname) ||
    /^\/care\/reports\/[^/]+\/edit/.test(pathname)
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, status, signIn, signOut } = useAuth();
  const { currentOrg, organizations, isPlatformAdmin, switchOrg, viewAll } = useOrg();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [mobileOpen, setMobileOpen] = useState(false);
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

  const idleMinutes = status === "authenticated" ? (session?.idleTimeoutMinutes ?? 0) : 0;
  const { isWarning, keepAlive } = useIdleLogout(idleMinutes, signOut);

  const badgeCounts: Record<string, number> = {};

  const navItemsForMode = uiMode === "care" ? CARE_NAV_ITEMS : ADMIN_NAV_ITEMS;

  const visibleNavItems = navItemsForMode.filter((item) => !item.adminOnly || isPlatformAdmin);

  const toggleUiMode = useCallback(() => {
    setUiMode((prev) => {
      const next = prev === "care" ? "admin" : "care";
      if (typeof window !== "undefined") {
        window.localStorage.setItem("leo-ui-mode", next);
      }
      return next;
    });
  }, []);

  const isEditor = isEditorRoute(pathname);
  // Listing public exceptions is safer than enumerating every protected path.
  const isPublicPage =
    pathname === "/" ||
    pathname === "/sign-in" ||
    pathname?.startsWith("/auth/");
  const isProtected = !isPublicPage;

  // Block ALL protected content until auth state is known.
  // This prevents a hacker briefly seeing page content during the loading window.
  if (status === "loading" && isProtected) {
    return (
      <Box
        sx={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "background.default",
        }}
      >
        <CircularProgress aria-label="Loading" />
      </Box>
    );
  }

  // No valid session on a protected route — show the full unauthorized screen,
  // do NOT render the page or the nav drawer.
  if (status === "unauthenticated" && isProtected) {
    return <UnauthorizedScreen onSignIn={signIn} />;
  }

  if (isPublicPage) {
    return (
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        {children}
      </Box>
    );
  }

  const handleNav = (path: string) => {
    router.push(path);
    if (isMobile) setMobileOpen(false);
  };

  const currentWidth = isEditor ? RAIL_WIDTH : DRAWER_WIDTH;

  const railContent = (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", height: "100%", py: 1.5 }}>
      <Tooltip title="LEO by Mizaic" placement="right">
        <Box
          component="img"
          src="/leo-icon.svg"
          alt="LEO"
          onClick={() => handleNav(uiMode === "admin" ? "/admin/console" : "/care/dashboard")}
          sx={{ width: 28, height: 28, mb: 1.5, cursor: "pointer" }}
        />
      </Tooltip>
      <Divider sx={{ width: "80%", mb: 1 }} />
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
                sx={{
                  justifyContent: "center",
                  px: 0,
                  py: 1,
                  minHeight: 40,
                }}
              >
                <ListItemIcon sx={{ minWidth: 0, color: isActive ? "primary.main" : "text.secondary" }}>
                  <Badge badgeContent={badgeCount} color="warning" max={99}>
                    {item.icon}
                  </Badge>
                </ListItemIcon>
              </ListItemButton>
            </Tooltip>
          );
        })}
      </List>
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
            <IconButton aria-label="Sign out" size="small" onClick={() => signOut()}>
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
        <Box
          component="img"
          src="/leo-icon.svg"
          alt="LEO"
          sx={{ width: 32, height: 32 }}
        />
        <Typography component="span" sx={{ fontSize: "1rem", lineHeight: 1.3, color: "text.primary", fontWeight: 600 }}>
          LEO
          <br />
          <Typography component="span" sx={{ fontSize: "0.8rem", color: "text.secondary", fontWeight: 400 }}>
            by Mizaic
          </Typography>
        </Typography>
      </Box>

      <Divider />

      {(organizations.length > 0 || isPlatformAdmin) && (
        <Box sx={{ px: 1.5, py: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5 }}>
            <BusinessOutlinedIcon sx={{ fontSize: 14, color: "text.secondary" }} />
            <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 500, letterSpacing: 0.5 }}>
              ORGANISATION
            </Typography>
          </Box>
          <FormControl fullWidth size="small">
            <Select
              value={viewAll ? "__all__" : (currentOrg?.id ?? "")}
              onChange={(e) => switchOrg(e.target.value as string)}
              displayEmpty
              sx={{
                fontSize: "0.8rem",
                bgcolor: "action.hover",
                borderRadius: 2,
                "& .MuiSelect-select": { py: 0.75, px: 1.5 },
                "& fieldset": { borderColor: "transparent" },
                "&:hover fieldset": { borderColor: "divider !important" },
              }}
            >
              {isPlatformAdmin && (
                <MenuItem value="__all__" sx={{ fontSize: "0.8rem" }}>
                  All Organisations
                </MenuItem>
              )}
              {[...organizations]
                .sort((a, b) =>
                  (a.shortName || a.name).localeCompare(b.shortName || b.name, "en", {
                    sensitivity: "base",
                  }),
                )
                .map((org) => (
                  <MenuItem key={org.id} value={org.id} sx={{ fontSize: "0.8rem" }}>
                    {org.shortName || org.name}
                  </MenuItem>
                ))}
            </Select>
          </FormControl>
        </Box>
      )}

      <Divider />

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
              <ListItemButton
                key={item.path}
                component={Link}
                href={item.path}
                selected={isActive}
                onClick={() => { if (isMobile) setMobileOpen(false); }}
                aria-current={isActive ? "page" : undefined}
                sx={{ py: 1.2 }}
              >
                <ListItemIcon sx={{ minWidth: 36, color: isActive ? "primary.main" : "text.secondary" }}>
                  <Badge badgeContent={badgeCount} color="warning" max={99}>
                    {item.icon}
                  </Badge>
                </ListItemIcon>
                <ListItemText
                  primary={item.label}
                  primaryTypographyProps={{
                    fontWeight: isActive ? 600 : 400,
                    fontSize: "0.9rem",
                  }}
                />
                {badgeCount > 0 && (
                  <Typography variant="caption" sx={{ bgcolor: "warning.main", color: "warning.contrastText", borderRadius: 10, px: 0.8, py: 0.2, fontWeight: 700, fontSize: "0.7rem" }}>
                    {badgeCount}
                  </Typography>
                )}
              </ListItemButton>
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
            sx={{ textTransform: "none", fontSize: "0.75rem" }}
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
            borderColor: "divider",
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
              sx={{ fontWeight: 600, fontSize: "0.8rem", color: "text.primary", lineHeight: 1.3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {session.user.name}
            </Typography>
          </Box>
          <Tooltip title="Sign out">
            <IconButton aria-label="Sign out" size="small" onClick={() => signOut()}>
              <LogoutIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </>
  );

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
          sx={{ bgcolor: "background.paper", borderBottom: "1px solid", borderColor: "divider" }}
        >
          <Toolbar variant="dense" sx={{ minHeight: 48 }}>
            <IconButton
              edge="start"
              aria-label="open navigation"
              onClick={() => setMobileOpen(true)}
              sx={{ color: "text.primary" }}
            >
              <MenuIcon />
            </IconButton>
            <Box component="img" src="/leo-icon.svg" alt="LEO" sx={{ width: 24, height: 24, ml: 1 }} />
            <Typography variant="subtitle2" sx={{ ml: 1, fontWeight: 600 }}>LEO</Typography>
          </Toolbar>
        </AppBar>
      )}

      <Drawer
        variant={isMobile ? "temporary" : "permanent"}
        open={isMobile ? mobileOpen : true}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          width: isMobile ? DRAWER_WIDTH : currentWidth,
          flexShrink: 0,
          transition: "width 0.2s ease",
          "& .MuiDrawer-paper": {
            width: isMobile ? DRAWER_WIDTH : currentWidth,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            transition: "width 0.2s ease",
            overflowX: "hidden",
          },
        }}
      >
        {isMobile || !isEditor ? fullDrawerContent : railContent}
      </Drawer>

      <Box
        component="main"
        id="main-content"
        sx={{
          flexGrow: 1,
          minWidth: 0,
          overflowX: "clip",
          mt: isMobile ? "48px" : 0,
          minHeight: "100vh",
          bgcolor: "background.default",
        }}
      >
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
    const poll = async () => {
      try {
        const res = await fetch("/api/training-worker/jobs");
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        const active = (data.jobs ?? data ?? []).find(
          (j: { status: string }) => j.status === "running" || j.status === "evaluating" || j.status === "uploading"
        );
        setRunningJob(active ?? null);
      } catch {
        // ignore
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
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
