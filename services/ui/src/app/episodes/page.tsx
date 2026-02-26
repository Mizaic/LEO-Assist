"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import TextField from "@mui/material/TextField";
import { fetchEpisodeTimeline } from "@/lib/analyticsApi";
import EpisodeList from "@/components/episodes/EpisodeList";
import EpisodeTimelineView from "@/components/episodes/EpisodeTimelineView";

interface Episode {
  episode_id: string;
  patient_id?: string;
  cancer_type: string;
  status: string;
  referral_date?: string;
  milestones?: Array<{
    encounter_id: string;
    date: string;
    milestone_type: string;
  }>;
}

export default function EpisodesPage() {
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Episode | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchEpisodeTimeline()
      .then(setEpisodes)
      .catch(() => setEpisodes([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = episodes.filter(
    (e) =>
      !search ||
      e.cancer_type?.toLowerCase().includes(search.toLowerCase()) ||
      e.patient_id?.toLowerCase().includes(search.toLowerCase()) ||
      e.episode_id?.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Cancer Episodes
      </Typography>

      <TextField
        placeholder="Search by cancer type, patient, or episode ID..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        fullWidth
        sx={{ mb: 2.5 }}
      />

      <Box sx={{ display: "flex", gap: 2.5, minHeight: "70vh" }}>
        <Box sx={{ width: 400, flexShrink: 0 }}>
          {loading ? (
            <Skeleton variant="rectangular" height={400} />
          ) : (
            <EpisodeList
              episodes={filtered}
              selected={selected}
              onSelect={setSelected}
            />
          )}
        </Box>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          {selected ? (
            <Card>
              <CardContent>
                <EpisodeTimelineView episode={selected} />
              </CardContent>
            </Card>
          ) : (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                color: "text.secondary",
              }}
            >
              <Typography>Select an episode to view its timeline</Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
