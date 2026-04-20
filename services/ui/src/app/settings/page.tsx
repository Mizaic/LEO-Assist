/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A59215DA
 *   DI: DI-900CB621
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A59215DA")
 */
"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useOrg } from "@/context/OrgContext";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActionArea from "@mui/material/CardActionArea";
import Grid from "@mui/material/Grid";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import DensityMediumOutlinedIcon from "@mui/icons-material/DensityMediumOutlined";
import AreaIntro from "@/components/AreaIntro";

interface SettingsCard {
  id: string;
  title: string;
  description: string;
  icon: React.ReactElement;
  path: string;
  disabled?: boolean;
}

const SETTINGS_CARDS: SettingsCard[] = [
  {
    id: "domains",
    title: "Domain Configuration",
    description:
      "Manage clinical domains, SNOMED concept sets, and related terms. Add or remove concepts, configure descriptions, milestone types, and surface forms for anchor detection and episode building.",
    icon: <TuneOutlinedIcon sx={{ fontSize: 40, color: "primary.main" }} />,
    path: "/settings/domains",
  },
  {
    id: "surface-forms",
    title: "Surface Forms",
    description:
      "View and manage the text strings the NLP pipeline maps to SNOMED concepts. Remove spurious or over-broad mappings that cause false positives in anchor detection.",
    icon: <TextFieldsOutlinedIcon sx={{ fontSize: 40, color: "primary.main" }} />,
    path: "/settings/surface-forms",
  },
  {
    id: "terminology",
    title: "Terminology data",
    description:
      "Check for new SNOMED CT and dm+d releases from NHS TRUD. Download and load them into the knowledge graph. Platform admins only.",
    icon: <HubOutlinedIcon sx={{ fontSize: 40, color: "primary.main" }} />,
    path: "/settings/terminology",
  },
  {
    id: "context-rules",
    title: "Context rules",
    description:
      "Teach the system how to handle new clinical phrases -- for example, that 'would not consider' means DECLINED. Rules are added to the context detection pipeline without a code deploy.",
    icon: <AccountTreeOutlinedIcon sx={{ fontSize: 40, color: "primary.main" }} />,
    path: "/settings/context-rules",
  },
  {
    id: "preferences",
    title: "Preferences",
    description:
      "Personal display settings, including how tightly LEO packs information on the page. Saved to your account and applied on every device after sign-in.",
    icon: <DensityMediumOutlinedIcon sx={{ fontSize: 40, color: "primary.main" }} />,
    path: "/settings/preferences",
  },
  {
    id: "tenant",
    title: "Tenant Management",
    description:
      "Manage organisations, users, groups, roles, and auth settings. Platform admins only.",
    icon: <SettingsOutlinedIcon sx={{ fontSize: 40, color: "primary.main" }} />,
    path: "/tenant",
  },
];

export default function SettingsPage() {
  const router = useRouter();
  const { isPlatformAdmin } = useOrg();

  const adminOnly = new Set(["tenant", "terminology"]);
  const cards = SETTINGS_CARDS.filter((c) => !adminOnly.has(c.id) || isPlatformAdmin);

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <AreaIntro area="settings" />
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
        Settings
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure domains, agents, and application preferences.
      </Typography>

      <Grid container spacing={2}>
        {cards.map((card) => (
          <Grid key={card.id} size={{ xs: 12, sm: 6 }}>
            <Card
              sx={{
                opacity: card.disabled ? 0.6 : 1,
                height: "100%",
              }}
            >
              <CardActionArea
                onClick={() => !card.disabled && card.path && router.push(card.path)}
                disabled={card.disabled}
                sx={{ height: "100%", display: "block" }}
              >
                <CardContent sx={{ p: 2.5 }}>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "flex-start",
                      justifyContent: "space-between",
                      mb: 1.5,
                    }}
                  >
                    {card.icon}
                    {!card.disabled && (
                      <ChevronRightIcon color="action" fontSize="small" />
                    )}
                  </Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.5 }}>
                    {card.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {card.description}
                  </Typography>
                  {card.disabled && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: 1, display: "block", fontStyle: "italic" }}
                    >
                      Coming soon
                    </Typography>
                  )}
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
