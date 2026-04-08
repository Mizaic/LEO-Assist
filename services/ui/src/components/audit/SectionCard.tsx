"use client";

import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import CloudDownloadOutlinedIcon from "@mui/icons-material/CloudDownloadOutlined";
import HourglassEmptyOutlinedIcon from "@mui/icons-material/HourglassEmptyOutlined";

export type DataAvailability = "ready" | "pipeline_pending" | "manual_entry" | "external_feed";

interface SectionCardProps {
  id: string;
  title: string;
  description?: string;
  availability?: DataAvailability;
  loading?: boolean;
  error?: string | null;
  children: React.ReactNode;
}

const AVAILABILITY_CONFIG: Record<
  DataAvailability,
  { label: string; severity: "info" | "warning"; message: string; icon: React.ReactElement }
> = {
  ready: {
    label: "Live data",
    severity: "info",
    message: "",
    icon: <StorageOutlinedIcon fontSize="small" />,
  },
  pipeline_pending: {
    label: "Reading records",
    severity: "info",
    message:
      "We are still reading through the clinical records. The numbers shown may change when this is done.",
    icon: <HourglassEmptyOutlinedIcon fontSize="small" />,
  },
  manual_entry: {
    label: "Needs data entry",
    severity: "warning",
    message:
      "A team member needs to add data for this section. We show national comparison figures for now, but your practice data is not yet included.",
    icon: <EditNoteOutlinedIcon fontSize="small" />,
  },
  external_feed: {
    label: "Needs external data",
    severity: "warning",
    message:
      "This section needs data from an outside source (for example the Cancer Outcomes and Services Dataset, COSD). National comparison figures are shown for reference.",
    icon: <CloudDownloadOutlinedIcon fontSize="small" />,
  },
};

export default function SectionCard({
  id,
  title,
  description,
  availability = "ready",
  loading = false,
  error = null,
  children,
}: SectionCardProps) {
  const cfg = AVAILABILITY_CONFIG[availability];

  return (
    <Card
      id={id}
      component="section"
      aria-labelledby={`${id}-title`}
      sx={{ mb: 3, scrollMarginTop: "80px" }}
    >
      <CardContent sx={{ pb: "16px !important" }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", mb: 0.5, flexWrap: "wrap", gap: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              id={`${id}-title`}
              variant="h6"
              component="h2"
              sx={{ fontSize: "1rem", fontWeight: 700 }}
            >
              {title}
            </Typography>
            {description && (
              <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.8rem", mt: 0.25 }}>
                {description}
              </Typography>
            )}
          </Box>
          {availability !== "ready" && (
            <Chip
              icon={cfg.icon}
              label={cfg.label}
              size="small"
              color={cfg.severity === "warning" ? "warning" : "default"}
              variant="outlined"
              sx={{ flexShrink: 0 }}
            />
          )}
        </Box>

        {cfg.message && (
          <Alert severity={cfg.severity} sx={{ mb: 2, fontSize: "0.8rem" }}>
            {cfg.message}
          </Alert>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {loading ? (
          <Skeleton variant="rectangular" height={220} aria-label={`Loading ${title}`} />
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
