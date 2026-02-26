"use client";

import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActionArea from "@mui/material/CardActionArea";
import Grid from "@mui/material/Grid";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

const SETTINGS_CARDS = [
  {
    id: "domains",
    title: "Domain Configuration",
    description:
      "Manage clinical domains, SNOMED concept sets, and related terms. Add or remove concepts, configure descriptions, milestone types, and surface forms for anchor detection and episode building.",
    icon: <TuneOutlinedIcon sx={{ fontSize: 40, color: "primary.main" }} />,
    path: "/settings/domains",
  },
  {
    id: "general",
    title: "General Settings",
    description: "Application preferences, organisation defaults, and system configuration.",
    icon: <SettingsOutlinedIcon sx={{ fontSize: 40, color: "text.secondary" }} />,
    path: null,
    disabled: true,
  },
];

export default function SettingsPage() {
  const router = useRouter();

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
        Settings
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure domains, agents, and application preferences.
      </Typography>

      <Grid container spacing={2}>
        {SETTINGS_CARDS.map((card) => (
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
