"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Avatar from "@mui/material/Avatar";
import Tooltip from "@mui/material/Tooltip";
import AddIcon from "@mui/icons-material/Add";
import TuneIcon from "@mui/icons-material/Tune";
import SearchIcon from "@mui/icons-material/Search";
import CategoryIcon from "@mui/icons-material/Category";
import BuildIcon from "@mui/icons-material/Build";
import VerifiedIcon from "@mui/icons-material/Verified";
import FilterAltIcon from "@mui/icons-material/FilterAlt";
import ManageSearchIcon from "@mui/icons-material/ManageSearch";
import MergeTypeIcon from "@mui/icons-material/MergeType";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { api } from "@/lib/api";

interface PromptConfig {
  id: string;
  name: string;
  description: string;
  version: number;
  verification: boolean;
  fewShotCount: number;
  updatedAt: string;
}

function formatDate(iso: string) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return null;
  }
}

// Maps prompt name patterns to a color + icon
type PromptCategory = {
  color: string;
  bg: string;
  icon: React.ReactNode;
  label: string;
};

function categorise(name: string): PromptCategory {
  const n = name.toLowerCase();
  if (n.includes("extract")) return { color: "#1565c0", bg: "#e3f2fd", icon: <SearchIcon sx={{ fontSize: 18 }} />, label: "Extraction" };
  if (n.includes("classif") || n.includes("detect") || n.includes("exclusion")) return { color: "#6a1b9a", bg: "#f3e5f5", icon: <FilterAltIcon sx={{ fontSize: 18 }} />, label: "Classification" };
  if (n.includes("disambig")) return { color: "#e65100", bg: "#fff3e0", icon: <ManageSearchIcon sx={{ fontSize: 18 }} />, label: "Disambiguation" };
  if (n.includes("verif") || n.includes("anchor")) return { color: "#2e7d32", bg: "#e8f5e9", icon: <VerifiedIcon sx={{ fontSize: 18 }} />, label: "Verification" };
  if (n.includes("episode") || n.includes("consolid") || n.includes("builder")) return { color: "#00695c", bg: "#e0f2f1", icon: <MergeTypeIcon sx={{ fontSize: 18 }} />, label: "Episode builder" };
  if (n.includes("label")) return { color: "#f57f17", bg: "#fff8e1", icon: <CategoryIcon sx={{ fontSize: 18 }} />, label: "Labelling" };
  return { color: "#37474f", bg: "#eceff1", icon: <BuildIcon sx={{ fontSize: 18 }} />, label: "General" };
}

function humanName(raw: string) {
  return raw
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function PromptCard({ p, onClick }: { p: PromptConfig; onClick: () => void }) {
  const cat = categorise(p.name);
  const date = formatDate(p.updatedAt);

  return (
    <Card
      variant="outlined"
      sx={{
        height: "100%",
        borderRadius: 2.5,
        borderColor: "divider",
        transition: "box-shadow 0.18s, border-color 0.18s, transform 0.12s",
        "&:hover": {
          boxShadow: "0 4px 20px rgba(0,0,0,0.10)",
          borderColor: cat.color,
          transform: "translateY(-2px)",
        },
      }}
    >
      <CardActionArea
        onClick={onClick}
        sx={{ height: "100%", alignItems: "flex-start", display: "flex", flexDirection: "column" }}
      >
        <CardContent sx={{ width: "100%", p: 2.5 }}>
          {/* Category avatar + version */}
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1.5 }}>
            <Avatar
              sx={{
                width: 36, height: 36,
                bgcolor: cat.bg,
                color: cat.color,
                border: `1.5px solid ${cat.color}30`,
              }}
            >
              {cat.icon}
            </Avatar>
            <Chip
              label={`v${p.version}`}
              size="small"
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 20, borderColor: "divider" }}
            />
          </Stack>

          {/* Name */}
          <Typography
            variant="subtitle1"
            fontWeight={700}
            sx={{
              mb: 0.5,
              lineHeight: 1.25,
              color: "text.primary",
              wordBreak: "break-word",
            }}
          >
            {humanName(p.name)}
          </Typography>

          {/* Category label */}
          <Typography variant="caption" sx={{ color: cat.color, fontWeight: 600, display: "block", mb: 1 }}>
            {cat.label}
          </Typography>

          {/* Description */}
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              mb: 1.5,
              minHeight: 40,
              display: "-webkit-box",
              WebkitLineClamp: 3,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              lineHeight: 1.5,
              fontSize: "0.8rem",
            }}
          >
            {p.description || (
              <Box component="em" sx={{ opacity: 0.5 }}>No description yet — click to add one.</Box>
            )}
          </Typography>

          {/* Footer chips */}
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap alignItems="center">
            {p.verification && (
              <Tooltip title="A second AI check runs after the first to confirm accuracy">
                <Chip
                  size="small"
                  icon={<CheckCircleOutlineIcon sx={{ fontSize: "13px !important" }} />}
                  label="Double-check"
                  color="success"
                  sx={{ height: 20, fontSize: "0.68rem" }}
                />
              </Tooltip>
            )}
            {p.fewShotCount > 0 && (
              <Chip
                size="small"
                label={`${p.fewShotCount} example${p.fewShotCount !== 1 ? "s" : ""}`}
                color="info"
                variant="outlined"
                sx={{ height: 20, fontSize: "0.68rem" }}
              />
            )}
            {date && (
              <Typography variant="caption" color="text.disabled" sx={{ ml: "auto !important", fontSize: "0.68rem" }}>
                {date}
              </Typography>
            )}
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}

function SkeletonCard() {
  return (
    <Card variant="outlined" sx={{ borderRadius: 2.5, p: 2.5 }}>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Skeleton variant="circular" width={36} height={36} />
        <Skeleton width={28} height={20} variant="rounded" />
      </Stack>
      <Skeleton width="70%" height={22} sx={{ mb: 0.5 }} />
      <Skeleton width="40%" height={16} sx={{ mb: 1 }} />
      <Skeleton width="100%" height={14} />
      <Skeleton width="85%" height={14} />
      <Skeleton width="60%" height={14} sx={{ mb: 1.5 }} />
      <Stack direction="row" spacing={0.75}>
        <Skeleton width={70} height={20} variant="rounded" />
        <Skeleton width={60} height={20} variant="rounded" />
      </Stack>
    </Card>
  );
}

export default function PromptsPage() {
  const router = useRouter();
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ prompts: PromptConfig[] }>("/api/prompts")
      .then((d) => setPrompts(d.prompts || []))
      .catch(() => setPrompts([]))
      .finally(() => setLoading(false));
  }, []);

  const grouped = prompts.reduce<Record<string, PromptConfig[]>>((acc, p) => {
    const cat = categorise(p.name).label;
    (acc[cat] ??= []).push(p);
    return acc;
  }, {});
  const sortedGroups = Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b));

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: "auto" }}>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 4 }}>
        <Box>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.75 }}>
            <TuneIcon sx={{ color: "primary.main", fontSize: 28 }} />
            <Typography variant="h4" fontWeight={800} letterSpacing="-0.5px">
              AI Instructions
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520 }}>
            Each card is a set of instructions that tells the AI how to read and understand clinical text.
            Click any card to view or update its instructions.
          </Typography>
        </Box>
        <Button
          variant="contained"
          size="large"
          startIcon={<AddIcon />}
          onClick={() => router.push("/admin/prompts/new")}
          sx={{ mt: 0.5, flexShrink: 0, borderRadius: 2 }}
        >
          New instructions
        </Button>
      </Stack>

      {/* Cards */}
      {loading ? (
        <Grid container spacing={2}>
          {Array.from({ length: 9 }).map((_, i) => (
            <Grid item xs={12} sm={6} md={4} key={i}>
              <SkeletonCard />
            </Grid>
          ))}
        </Grid>
      ) : prompts.length === 0 ? (
        <Box sx={{
          textAlign: "center", py: 10, px: 3,
          border: "2px dashed", borderColor: "divider", borderRadius: 3,
        }}>
          <TuneIcon sx={{ fontSize: 56, color: "text.disabled", mb: 1.5 }} />
          <Typography variant="h6" gutterBottom fontWeight={700}>No instructions yet</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Add your first set of AI instructions to get the pipeline working.
          </Typography>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => router.push("/admin/prompts/new")}>
            Add instructions
          </Button>
        </Box>
      ) : (
        <Stack spacing={4}>
          {sortedGroups.map(([groupLabel, items]) => {
            const cat = categorise(items[0].name);
            return (
              <Box key={groupLabel}>
                {/* Group header */}
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                  <Box sx={{
                    display: "flex", alignItems: "center", justifyContent: "center",
                    width: 28, height: 28, borderRadius: "50%",
                    bgcolor: cat.bg, color: cat.color,
                  }}>
                    {cat.icon}
                  </Box>
                  <Typography variant="subtitle1" fontWeight={700} color="text.primary">
                    {groupLabel}
                  </Typography>
                  <Typography variant="caption" color="text.disabled">
                    {items.length} instruction{items.length !== 1 ? "s" : ""}
                  </Typography>
                </Stack>

                <Grid container spacing={2}>
                  {items.map((p) => (
                    <Grid item xs={12} sm={6} md={4} key={p.id}>
                      <PromptCard p={p} onClick={() => router.push(`/admin/prompts/${p.id}`)} />
                    </Grid>
                  ))}
                </Grid>
              </Box>
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
