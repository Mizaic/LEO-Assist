"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import type { MissionCatalogueResponse, MissionDescription, PersonaLens } from "@/lib/researchApi";
import MissionCard from "./MissionCard";

interface Props {
  catalogue: MissionCatalogueResponse | null;
  loading: boolean;
  error: string | null;
  lens: PersonaLens;
  onSelect: (mission: MissionDescription) => void;
}

export default function MissionCardGrid({
  catalogue,
  loading,
  error,
  lens,
  onSelect,
}: Props) {
  if (loading) {
    return (
      <Box sx={{ px: 3, py: 2 }}>
        <Grid container spacing={2}>
          {Array.from({ length: 9 }).map((_, i) => (
            <Grid item xs={12} sm={6} md={4} key={i}>
              <Skeleton variant="rounded" height={160} />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ px: 3, py: 2 }}>
        <Alert severity="error">
          Could not load investigations. {error}
        </Alert>
      </Box>
    );
  }

  if (!catalogue || catalogue.missions.length === 0) {
    return (
      <Box sx={{ px: 3, py: 2 }}>
        <Alert severity="info">
          No investigations are available yet. Check back after the graph
          projections have been built.
        </Alert>
      </Box>
    );
  }

  // Group missions by group label
  const groups: Array<{
    key: string;
    title: string;
    subtitle: string;
    missions: MissionDescription[];
  }> = [];
  const seen = new Set<string>();

  for (const m of catalogue.missions) {
    if (!seen.has(m.group)) {
      seen.add(m.group);
      groups.push({
        key: m.group,
        title: m.group_title,
        subtitle: m.group_subtitle,
        missions: [],
      });
    }
    groups.find((g) => g.key === m.group)!.missions.push(m);
  }

  return (
    <Box sx={{ px: 3, py: 2 }}>
      {groups.map((group) => (
        <Box key={group.key} sx={{ mb: 4 }}>
          <Typography
            variant="subtitle1"
            sx={{ fontWeight: 700, mb: 0.5 }}
          >
            {group.title}
          </Typography>
          <Typography
            variant="body2"
            sx={{ color: "text.secondary", mb: 2 }}
          >
            {group.subtitle}
          </Typography>
          <Grid container spacing={2}>
            {group.missions.map((m) => (
              <Grid item xs={12} sm={6} md={4} key={m.id}>
                <MissionCard mission={m} lens={lens} onSelect={onSelect} />
              </Grid>
            ))}
          </Grid>
        </Box>
      ))}
    </Box>
  );
}
