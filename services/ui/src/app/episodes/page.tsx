"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import TextField from "@mui/material/TextField";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import InputAdornment from "@mui/material/InputAdornment";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import ToggleButton from "@mui/material/ToggleButton";
import Tooltip from "@mui/material/Tooltip";
import SearchIcon from "@mui/icons-material/Search";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import ListIcon from "@mui/icons-material/List";
import { fetchEpisodeTimeline } from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import {
  type Episode,
  type CaseloadSummary,
  type PathwayRisk,
  type EpisodeWithRisk,
  type PatientGroup,
  summariseCaseload,
  sortByUrgency,
  groupByPatient,
  normalizeMilestones,
  isStaleEpisode,
} from "@/lib/pathwayRisk";
import EpisodeList from "@/components/episodes/EpisodeList";
import PatientGroupList from "@/components/episodes/PatientGroupList";
import EpisodeTimelineView from "@/components/episodes/EpisodeTimelineView";
import CaseloadStrip from "@/components/episodes/CaseloadStrip";

interface Neo4jDate {
  _Date__year: number;
  _Date__month: number;
  _Date__day: number;
}

function normalizeDate(d: unknown): string | undefined {
  if (!d) return undefined;
  if (typeof d === "string") return d;
  if (typeof d === "object" && d !== null && "_Date__year" in d) {
    const nd = d as Neo4jDate;
    const y = nd._Date__year;
    const m = String(nd._Date__month).padStart(2, "0");
    const day = String(nd._Date__day).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }
  return String(d);
}

function normalizeEpisodes(raw: Episode[]): Episode[] {
  return raw.map((ep) => {
    const normalized = normalizeMilestones(ep.milestones);
    return {
      ...ep,
      referral_date: normalizeDate(ep.referral_date),
      milestones: normalized.map((ms) => ({
        ...ms,
        date: normalizeDate(ms.date) ?? ms.date,
      })),
    };
  });
}

type FilterTab = "attention" | "active" | "completed" | "stale" | "all";
type ViewMode = "grouped" | "flat";

const TAB_DEFS: Array<{ value: FilterTab; label: string }> = [
  { value: "attention", label: "Needs attention" },
  { value: "active", label: "All active" },
  { value: "completed", label: "Completed" },
  { value: "stale", label: "Stale" },
  { value: "all", label: "All" },
];

function filterByTab(
  episodes: EpisodeWithRisk[],
  tab: FilterTab,
): EpisodeWithRisk[] {
  switch (tab) {
    case "attention":
      return episodes.filter(
        (e) => e.risk.level === "breached" || e.risk.level === "at-risk",
      );
    case "active":
      return episodes.filter(
        (e) =>
          e.risk.level !== "completed" &&
          e.status !== "completed" &&
          e.status !== "closed" &&
          e.status !== "merged",
      );
    case "completed":
      return episodes.filter(
        (e) =>
          e.risk.level === "completed" ||
          e.status === "completed" ||
          e.status === "closed",
      );
    case "stale":
      return episodes.filter((e) => isStaleEpisode(e));
    case "all":
    default:
      return episodes;
  }
}

function EpisodesPageContent() {
  const orgId = useOrgId();
  const searchParams = useSearchParams();
  const patientIdFromUrl = searchParams.get("patient_id") ?? undefined;
  const [episodes, setEpisodes] = useState<EpisodeWithRisk[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<EpisodeWithRisk | null>(null);
  const [search, setSearch] = useState(patientIdFromUrl ?? "");
  const [tab, setTab] = useState<FilterTab>("attention");
  const [viewMode, setViewMode] = useState<ViewMode>("grouped");
  const [summary, setSummary] = useState<CaseloadSummary | null>(null);

  const refreshEpisodes = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchEpisodeTimeline(patientIdFromUrl, orgId);
      const normalized = normalizeEpisodes(data);
      const ranked = sortByUrgency(normalized);
      setEpisodes(ranked);
      setSummary(summariseCaseload(normalized));
    } catch {
      setEpisodes([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [orgId, patientIdFromUrl]);

  useEffect(() => {
    if (patientIdFromUrl) setSearch(patientIdFromUrl);
  }, [patientIdFromUrl]);

  useEffect(() => {
    refreshEpisodes();
  }, [refreshEpisodes]);

  const searched = episodes.filter(
    (e) =>
      !search ||
      e.cancer_type?.toLowerCase().includes(search.toLowerCase()) ||
      e.patient_id?.toLowerCase().includes(search.toLowerCase()) ||
      e.episode_id?.toLowerCase().includes(search.toLowerCase()),
  );

  const filtered = filterByTab(searched, tab);

  const patientGroups: PatientGroup[] = useMemo(
    () => groupByPatient(filtered),
    [filtered],
  );

  const siblingEpisodes = useMemo(() => {
    if (!selected?.patient_id) return [];
    return filtered.filter(
      (e) =>
        e.patient_id === selected.patient_id &&
        e.episode_id !== selected.episode_id,
    );
  }, [selected, filtered]);

  const handleTabChange = (_: React.SyntheticEvent, val: FilterTab) => {
    setTab(val);
    setSelected(null);
  };

  const handleViewMode = (
    _: React.MouseEvent<HTMLElement>,
    val: ViewMode | null,
  ) => {
    if (val) setViewMode(val);
  };

  const patientCount = new Set(
    filtered.map((e) => e.patient_id).filter(Boolean),
  ).size;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Referral Pathways
      </Typography>

      {loading ? (
        <Skeleton variant="rounded" height={72} sx={{ mb: 2.5 }} />
      ) : (
        summary && <CaseloadStrip summary={summary} />
      )}

      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          mb: 2,
          flexWrap: "wrap",
        }}
      >
        <Tabs
          value={tab}
          onChange={handleTabChange}
          sx={{
            minHeight: 36,
            "& .MuiTab-root": {
              minHeight: 36,
              py: 0.5,
              textTransform: "none",
            },
          }}
        >
          {TAB_DEFS.map((t) => (
            <Tab key={t.value} value={t.value} label={t.label} />
          ))}
        </Tabs>

        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={handleViewMode}
          size="small"
          sx={{ ml: 1 }}
        >
          <ToggleButton value="grouped" aria-label="group by patient">
            <Tooltip title="Group by patient">
              <PeopleOutlineIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
          <ToggleButton value="flat" aria-label="flat list">
            <Tooltip title="Flat list">
              <ListIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
        </ToggleButtonGroup>

        <TextField
          placeholder="Search by cancer type, patient, or pathway ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          sx={{ ml: "auto", minWidth: 280 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />
      </Box>

      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ mb: 1.5, display: "block" }}
      >
        {viewMode === "grouped"
          ? `${patientCount} patients, ${filtered.length} pathways`
          : `Showing ${filtered.length} of ${episodes.length} pathways`}
      </Typography>

      <Box sx={{ display: "flex", gap: 2.5, minHeight: "70vh" }}>
        <Box sx={{ width: 420, flexShrink: 0 }}>
          {loading ? (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} variant="rounded" height={88} />
              ))}
            </Box>
          ) : viewMode === "grouped" ? (
            <PatientGroupList
              groups={patientGroups}
              selected={selected}
              onSelect={setSelected}
            />
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
                <EpisodeTimelineView
                  episode={selected}
                  risk={selected.risk}
                  siblingEpisodes={siblingEpisodes}
                  onRefresh={refreshEpisodes}
                />
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
              <Typography>
                Select a referral pathway to view its timeline
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}

export default function EpisodesPage() {
  return (
    <Suspense fallback={<Box sx={{ p: 3 }}><Skeleton variant="rounded" height={72} sx={{ mb: 2.5 }} /><Skeleton variant="rounded" height={400} /></Box>}>
      <EpisodesPageContent />
    </Suspense>
  );
}
