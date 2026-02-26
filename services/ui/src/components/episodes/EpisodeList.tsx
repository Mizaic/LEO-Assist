"use client";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";

interface Episode {
  episode_id: string;
  patient_id?: string;
  cancer_type: string;
  status: string;
  referral_date?: string;
}

export default function EpisodeList({
  episodes,
  selected,
  onSelect,
}: {
  episodes: Episode[];
  selected: Episode | null;
  onSelect: (e: Episode) => void;
}) {
  if (!episodes.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No episodes found.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: "70vh", overflow: "auto" }}>
      {episodes.map((ep) => {
        const isSelected = selected?.episode_id === ep.episode_id;
        return (
          <Card
            key={ep.episode_id}
            onClick={() => onSelect(ep)}
            sx={{
              cursor: "pointer",
              border: "2px solid",
              borderColor: isSelected ? "primary.main" : "transparent",
              bgcolor: isSelected ? "primary.50" : "background.paper",
            }}
          >
            <Box sx={{ px: 2, py: 1.5 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.85rem" }}>
                  {ep.cancer_type || "Unknown type"}
                </Typography>
                <Chip
                  label={ep.status}
                  size="small"
                  color={ep.status === "active" ? "success" : "default"}
                  sx={{ textTransform: "capitalize" }}
                />
              </Box>
              <Typography variant="caption" color="text.secondary">
                {ep.patient_id && `Patient: ${ep.patient_id}`}
                {ep.referral_date && ` | Referred: ${ep.referral_date}`}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mt: 0.25, fontFamily: "monospace", fontSize: "0.7rem" }}
              >
                {ep.episode_id}
              </Typography>
            </Box>
          </Card>
        );
      })}
    </Box>
  );
}
