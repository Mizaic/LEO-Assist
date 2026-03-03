"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import ApartmentOutlinedIcon from "@mui/icons-material/ApartmentOutlined";
import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import OrgManagement from "@/components/tenant/OrgManagement";
import UserManagement from "@/components/tenant/UserManagement";
import AuthConfig from "@/components/tenant/AuthConfig";

const TABS = [
  {
    value: "orgs",
    label: "Organisations",
    icon: <ApartmentOutlinedIcon fontSize="small" />,
    desc: "Manage GP practices, ICBs, and Cancer Alliances.",
  },
  {
    value: "users",
    label: "People & Groups",
    icon: <PeopleAltOutlinedIcon fontSize="small" />,
    desc: "Add or remove people and organise them into groups.",
  },
  {
    value: "auth",
    label: "Login & Security",
    icon: <LockOutlinedIcon fontSize="small" />,
    desc: "Control how long people stay logged in and see who is active.",
  },
];

export default function TenantPage() {
  const [tab, setTab] = useState("orgs");
  const current = TABS.find((t) => t.value === tab)!;

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: "auto" }}>
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
        Tenant Management
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Manage who can use LEO, which organisations are in the system, and security settings.
        Only platform admins can see this page.
      </Typography>

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{ mb: 1, borderBottom: 1, borderColor: "divider" }}
      >
        {TABS.map((t) => (
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
        {current.desc}
      </Typography>

      {tab === "orgs" && <OrgManagement />}
      {tab === "users" && <UserManagement />}
      {tab === "auth" && <AuthConfig />}
    </Box>
  );
}
