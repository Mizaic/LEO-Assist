"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
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
import LogoutIcon from "@mui/icons-material/Logout";
import MenuIcon from "@mui/icons-material/Menu";
import BusinessOutlinedIcon from "@mui/icons-material/BusinessOutlined";
import { useAuth } from "@/lib/authContext";
import Avatar from "@mui/material/Avatar";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { usePipeline } from "@/context/PipelineContext";
import { useOrg } from "@/context/OrgContext";
import PipelineModal from "./PipelineModal";

const DRAWER_WIDTH = 240;
const RAIL_WIDTH = 56;

const NAV_ITEMS = [
  { label: "Overview", path: "/dashboard", icon: <DashboardOutlinedIcon /> },
  { label: "Patients", path: "/patients", icon: <PeopleOutlineIcon /> },
  { label: "Referral Pathways", path: "/episodes", icon: <TimelineOutlinedIcon /> },
  { label: "Safety Netting", path: "/css", icon: <HealthAndSafetyOutlinedIcon /> },
  { label: "Reports", path: "/reports", icon: <DescriptionOutlinedIcon /> },
  { label: "Measures", path: "/measures", icon: <BarChartOutlinedIcon /> },
  { label: "Benchmarks", path: "/benchmarks", icon: <AssessmentOutlinedIcon /> },
  { label: "Cohorts", path: "/cohorts", icon: <GroupWorkOutlinedIcon /> },
  { label: "Processing", path: "/pipeline", icon: <SettingsOutlinedIcon /> },
  { label: "Domain Config", path: "/settings", icon: <TuneOutlinedIcon /> },
];

function isEditorRoute(pathname: string): boolean {
  return /^\/reports\/[^/]+\/edit/.test(pathname);
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const pipeline = usePipeline();
  const { session, status, signOut } = useAuth();
  const { currentOrg, organizations, isPlatformAdmin, switchOrg, viewAll } = useOrg();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [mobileOpen, setMobileOpen] = useState(false);

  const isPublicPage = pathname === "/" || pathname === "/sign-in";
  const isEditor = isEditorRoute(pathname);
  const isProtected =
    pathname?.startsWith("/dashboard") ||
    pathname?.startsWith("/episodes") ||
    pathname?.startsWith("/css") ||
    pathname?.startsWith("/reports") ||
    pathname?.startsWith("/patients") ||
    pathname?.startsWith("/pipeline") ||
    pathname?.startsWith("/measures") ||
    pathname?.startsWith("/benchmarks") ||
    pathname?.startsWith("/cohorts") ||
    pathname?.startsWith("/settings");

  useEffect(() => {
    if (status === "unauthenticated" && isProtected) {
      router.replace("/sign-in");
    }
  }, [status, isProtected, router]);

  const hasPipelineState =
    pipeline.running ||
    (pipeline.result && !pipeline.running) ||
    (pipeline.error && !pipeline.running);
  const showIndicator = hasPipelineState && !pipeline.showModal;

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
          const isActive = pathname === item.path || pathname.startsWith(item.path + "/");
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
                  {item.icon}
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
          const isActive =
            pathname === item.path || pathname.startsWith(item.path + "/");
          return (
            <ListItemButton
              key={item.path}
              selected={isActive}
              onClick={() => handleNav(item.path)}
              sx={{ py: 1.2 }}
            >
              <ListItemIcon sx={{ minWidth: 36, color: isActive ? "primary.main" : "text.secondary" }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.label}
                primaryTypographyProps={{
                  fontWeight: isActive ? 600 : 400,
                  fontSize: "0.9rem",
                }}
              />
            </ListItemButton>
          );
        })}
      </List>

      {showIndicator && (
        <Box sx={{ p: 1.5 }}>
          <Box
            component="button"
            onClick={() => pipeline.setShowModal(true)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              width: "100%",
              px: 1.5,
              py: 1,
              borderRadius: 2,
              border: "1px solid",
              borderColor: "primary.main",
              bgcolor: "primary.main",
              color: "primary.contrastText",
              cursor: "pointer",
              fontSize: "0.8rem",
              fontWeight: 600,
              textAlign: "left",
              transition: "background-color 0.2s",
              "&:hover": { bgcolor: "primary.dark" },
            }}
          >
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                bgcolor: pipeline.running ? "success.light" : "grey.400",
                animation: pipeline.running ? "pulse 1.5s infinite" : "none",
                "@keyframes pulse": {
                  "0%, 100%": { opacity: 1 },
                  "50%": { opacity: 0.4 },
                },
              }}
            />
            {pipeline.running
              ? "View progress"
              : pipeline.error
                ? "View error"
                : "View results"}
          </Box>
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
          ml: isMobile ? 0 : `${currentWidth}px`,
          mt: isMobile ? "48px" : 0,
          minHeight: "100vh",
          bgcolor: "background.default",
          transition: "margin-left 0.2s ease",
        }}
      >
        {children}
      </Box>

      {pipeline.showModal && (
        <PipelineModal
          running={pipeline.running}
          status={pipeline.status}
          live={pipeline.live}
          result={pipeline.result}
          error={pipeline.error}
          workerStates={pipeline.workerStates}
          onClose={() => pipeline.setShowModal(false)}
          onMinimize={() => pipeline.setShowModal(false)}
        />
      )}
    </Box>
  );
}
