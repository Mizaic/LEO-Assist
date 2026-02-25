"use client";

import { usePathname, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import RocketLaunchOutlinedIcon from "@mui/icons-material/RocketLaunchOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import { usePipeline } from "@/context/PipelineContext";
import PipelineModal from "./PipelineModal";

const DRAWER_WIDTH = 240;

const NAV_ITEMS = [
  { label: "Patients", path: "/patients", icon: <PeopleOutlineIcon /> },
  { label: "Pipeline", path: "/pipeline", icon: <RocketLaunchOutlinedIcon /> },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const pipeline = usePipeline();

  const hasPipelineState =
    pipeline.running ||
    (pipeline.result && !pipeline.running) ||
    (pipeline.error && !pipeline.running);
  const showIndicator = hasPipelineState && !pipeline.showModal;

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
          },
        }}
      >
        <Box sx={{ px: 2.5, py: 2.5, display: "flex", alignItems: "center", gap: 1.5 }}>
          <LocalHospitalOutlinedIcon sx={{ color: "primary.main", fontSize: 28 }} />
          <Typography variant="h6" sx={{ fontSize: "1rem", lineHeight: 1.3, color: "text.primary" }}>
            Clinical Coding
            <br />
            <Typography component="span" sx={{ fontSize: "0.8rem", color: "text.secondary", fontWeight: 400 }}>
              Review
            </Typography>
          </Typography>
        </Box>

        <Divider />

        <List sx={{ px: 1, pt: 1 }}>
          {NAV_ITEMS.map((item) => {
            const isActive =
              pathname === item.path || pathname.startsWith(item.path + "/");
            return (
              <ListItemButton
                key={item.path}
                selected={isActive}
                onClick={() => router.push(item.path)}
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
          <Box sx={{ mt: "auto", p: 1.5 }}>
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
                "&:hover": {
                  bgcolor: "primary.dark",
                },
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
      </Drawer>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          ml: `${DRAWER_WIDTH}px`,
          minHeight: "100vh",
          bgcolor: "background.default",
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
