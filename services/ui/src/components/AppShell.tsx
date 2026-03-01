"use client";

import { useCallback, useEffect, useState } from "react";
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
import SportsEsportsOutlinedIcon from "@mui/icons-material/SportsEsportsOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import MenuIcon from "@mui/icons-material/Menu";
import BusinessOutlinedIcon from "@mui/icons-material/BusinessOutlined";
import { useAuth } from "@/lib/authContext";
import Avatar from "@mui/material/Avatar";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { useOrg } from "@/context/OrgContext";
import { api } from "@/lib/api";

const DRAWER_WIDTH = 240;
const RAIL_WIDTH = 56;

const NAV_ITEMS = [
  { label: "Overview", path: "/dashboard", icon: <DashboardOutlinedIcon /> },
  { label: "Patients", path: "/patients", icon: <PeopleOutlineIcon /> },
  { label: "Referral Pathways", path: "/pathways", icon: <TimelineOutlinedIcon /> },
  { label: "Safety Netting", path: "/safety-netting", icon: <HealthAndSafetyOutlinedIcon /> },
  { label: "Reports", path: "/reports", icon: <DescriptionOutlinedIcon /> },
  { label: "Measures", path: "/measures", icon: <BarChartOutlinedIcon /> },
  { label: "Benchmarks", path: "/benchmarks", icon: <AssessmentOutlinedIcon /> },
  { label: "Cohorts", path: "/cohorts", icon: <GroupWorkOutlinedIcon /> },
  { label: "Operations", path: "/operations", icon: <SettingsOutlinedIcon />, badgeKey: "reviewQueue" },
  { label: "Games", path: "/games", icon: <SportsEsportsOutlinedIcon /> },
  { label: "Gold Dataset", path: "/gold-dataset", icon: <LibraryBooksOutlinedIcon /> },
  { label: "Domain Config", path: "/settings", icon: <TuneOutlinedIcon /> },
];

function isEditorRoute(pathname: string): boolean {
  return /^\/reports\/[^/]+\/edit/.test(pathname);
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, status, signIn, signOut } = useAuth();
  const { currentOrg, organizations, isPlatformAdmin, switchOrg, viewAll } = useOrg();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [mobileOpen, setMobileOpen] = useState(false);

  const [reviewBadge, setReviewBadge] = useState<number>(0);

  const refreshReviewBadge = useCallback(async () => {
    try {
      const data = await api.get<{ pending_review: number }>(
        "/pipeline/classification-disagreements?limit=1"
      );
      setReviewBadge(data.pending_review ?? 0);
    } catch {
      // badge is non-critical, silently ignore
    }
  }, []);

  useEffect(() => {
    if (status === "authenticated") {
      refreshReviewBadge();
      const id = setInterval(refreshReviewBadge, 60_000);
      return () => clearInterval(id);
    }
  }, [status, refreshReviewBadge]);

  const badgeCounts: Record<string, number> = { reviewQueue: reviewBadge };

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
        <CircularProgress />
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
          onClick={() => handleNav("/dashboard")}
          sx={{ width: 28, height: 28, mb: 1.5, cursor: "pointer" }}
        />
      </Tooltip>
      <Divider sx={{ width: "80%", mb: 1 }} />
      <List sx={{ p: 0, width: "100%" }}>
        {NAV_ITEMS.map((item) => {
          const isActive = item.activePrefix
            ? item.activePrefix.some((p) => pathname === p || pathname.startsWith(p + "/"))
            : pathname === item.path || pathname.startsWith(item.path + "/");
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
            <IconButton size="small" onClick={() => signOut()}>
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
        <Typography variant="h6" sx={{ fontSize: "1rem", lineHeight: 1.3, color: "text.primary" }}>
          LEO
          <br />
          <Typography component="span" sx={{ fontSize: "0.8rem", color: "text.secondary", fontWeight: 400 }}>
            by Mizaic
          </Typography>
        </Typography>
      </Box>

      <Divider />

      {organizations.length > 0 && (
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
              {organizations.map((org) => (
                <MenuItem key={org.id} value={org.id} sx={{ fontSize: "0.8rem" }}>
                  {org.shortName || org.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}

      <Divider />

      <List sx={{ px: 1, pt: 1 }}>
        {NAV_ITEMS.map((item) => {
          const isActive = item.activePrefix
            ? item.activePrefix.some((p) => pathname === p || pathname.startsWith(p + "/"))
            : pathname === item.path || pathname.startsWith(item.path + "/");
          const badgeCount = item.badgeKey ? (badgeCounts[item.badgeKey] ?? 0) : 0;
          return (
            <ListItemButton
              key={item.path}
              selected={isActive}
              onClick={() => handleNav(item.path)}
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
            <IconButton size="small" onClick={() => signOut()}>
              <LogoutIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
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
        sx={{
          flexGrow: 1,
          minWidth: 0,
          overflowX: "hidden",
          mt: isMobile ? "48px" : 0,
          minHeight: "100vh",
          bgcolor: "background.default",
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
