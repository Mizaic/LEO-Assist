/**
 * Encounter list with FilterBar, paging, and a fill-height reader.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CodeIcon from "@mui/icons-material/Code";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import {
  EmptyState,
  FilterBar,
  color,
  type FilterChip,
} from "@leo/design-system";
import type { EncounterRow } from "@/lib/patientEprApi";
import { fetchEprEncounters } from "@/lib/patientEprApi";
import { encounterTypeLabel } from "./clinicalLabels";
import {
  EncounterViewer,
  encounterTypeTint,
  formatEncounterDate,
} from "./EncounterViewer";
import { RecordShowMore } from "./RecordShowMore";
import { RECORD_PAGE_SIZE, remainingCount, visibleSlice } from "./recordPage";

function EncounterListItem({
  enc,
  selected,
  onSelect,
}: {
  enc: EncounterRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const label = encounterTypeLabel(enc.encounter_id, enc.encounter_type);
  const tint = encounterTypeTint(label);
  return (
    <Box
      component="button"
      type="button"
      onClick={onSelect}
      sx={{
        display: "block",
        width: "100%",
        textAlign: "left",
        border: "none",
        borderBottom: "1px solid",
        borderColor: color.surface.divider,
        p: "12px 16px",
        bgcolor: selected ? color.surface.alt : "transparent",
        cursor: "pointer",
        "@media (hover: hover) and (pointer: fine)": {
          "&:hover": { bgcolor: color.surface.alt },
        },
      }}
      aria-pressed={selected}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Typography variant="caption" sx={{ color: color.text.caption }}>
          {formatEncounterDate(enc.encounter_date)}
        </Typography>
        {enc.coded_count > 0 && (
          <Stack direction="row" spacing={0.5} alignItems="center">
            <CodeIcon sx={{ fontSize: 14, color: color.text.caption }} />
            <Typography variant="caption" sx={{ color: color.text.caption }}>
              {enc.coded_count}
            </Typography>
          </Stack>
        )}
      </Stack>
      <Chip
        label={label}
        size="small"
        sx={{
          my: 0.5,
          height: 24,
          fontSize: 12,
          bgcolor: `${tint}18`,
          color: tint,
        }}
      />
      {enc.specialty && (
        <Typography variant="caption" sx={{ display: "block", color: color.text.caption }}>
          {enc.specialty}
        </Typography>
      )}
      {enc.text_preview && (
        <Typography
          variant="caption"
          sx={{
            display: "block",
            mt: 0.5,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: color.text.caption,
          }}
        >
          "{enc.text_preview}"
        </Typography>
      )}
    </Box>
  );
}

function encounterChips(
  rows: EncounterRow[],
  typeFilter: string,
  setTypeFilter: (id: string) => void,
): FilterChip[] {
  const types = Array.from(new Set(rows.map((r) => r.encounter_type).filter(Boolean)));
  return [
    {
      id: "all",
      label: "All",
      active: typeFilter === "all",
      onToggle: () => setTypeFilter("all"),
    },
    ...types.slice(0, 6).map((typeId) => ({
      id: typeId,
      label: encounterTypeLabel(
        rows.find((r) => r.encounter_type === typeId)?.encounter_id ?? typeId,
        typeId,
      ),
      active: typeFilter === typeId,
      onToggle: () => setTypeFilter(typeId),
    })),
  ];
}

function matchesSearch(enc: EncounterRow, q: string): boolean {
  if (!q) return true;
  return (
    enc.encounter_type.toLowerCase().includes(q) ||
    (enc.text_preview ?? "").toLowerCase().includes(q) ||
    (enc.specialty ?? "").toLowerCase().includes(q)
  );
}

interface Props {
  patientId: string;
  initialEncounterId?: string;
  scopeEpisodeIds?: string[];
}

export function EncounterListPanel({
  patientId,
  initialEncounterId,
  scopeEpisodeIds,
}: Props) {
  const [encounters, setEncounters] = useState<EncounterRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(
    initialEncounterId ?? null,
  );
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [shown, setShown] = useState(RECORD_PAGE_SIZE);

  useEffect(() => {
    setLoading(true);
    fetchEprEncounters(patientId)
      .then((rows) => {
        const scoped = scopeEpisodeIds
          ? rows.filter(
              (r) => !r.episode_id || scopeEpisodeIds.includes(r.episode_id),
            )
          : rows;
        setEncounters(scoped);
        if (!selectedId && scoped.length) setSelectedId(scoped[0].encounter_id);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load encounters."),
      )
      .finally(() => setLoading(false));
  }, [patientId, scopeEpisodeIds]);

  useEffect(() => {
    setShown(RECORD_PAGE_SIZE);
  }, [search, typeFilter]);

  const chips = useMemo(
    () => encounterChips(encounters, typeFilter, setTypeFilter),
    [encounters, typeFilter],
  );
  const q = search.trim().toLowerCase();
  const filtered = encounters.filter((enc) => {
    if (typeFilter !== "all" && enc.encounter_type !== typeFilter) return false;
    return matchesSearch(enc, q);
  });
  const visible = visibleSlice(filtered, shown);

  if (loading) {
    return (
      <Stack spacing={1.5}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} variant="rounded" height={80} />
        ))}
      </Stack>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <Box
      data-testid="epr-encounter-workspace"
      sx={{
        height: "100%",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
      }}
    >
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Search encounters"
        aria-label="Encounter filters"
        chips={chips}
      />
      <Box
        sx={{
          display: "flex",
          flex: 1,
          minHeight: 0,
          border: "1px solid",
          borderColor: color.surface.divider,
          borderRadius: "10px",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            width: 280,
            flexShrink: 0,
            borderRight: "1px solid",
            borderColor: color.surface.divider,
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
          }}
        >
          <Box sx={{ flex: 1, overflowY: "auto" }}>
            {visible.length === 0 ? (
              <Alert severity="info" sx={{ m: 1.5, fontSize: 13 }}>
                No encounters match.
              </Alert>
            ) : (
              visible.map((enc) => (
                <EncounterListItem
                  key={enc.encounter_id}
                  enc={enc}
                  selected={selectedId === enc.encounter_id}
                  onSelect={() => setSelectedId(enc.encounter_id)}
                />
              ))
            )}
          </Box>
          <Box sx={{ p: 1.5, borderTop: "1px solid", borderColor: color.surface.divider }}>
            <RecordShowMore
              remaining={remainingCount(filtered.length, shown)}
              onShowMore={() => setShown((n) => n + RECORD_PAGE_SIZE)}
            />
          </Box>
        </Box>
        <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
          {selectedId ? (
            <EncounterViewer patientId={patientId} encounterId={selectedId} />
          ) : (
            <EmptyState
              icon={<MedicalServicesOutlinedIcon />}
              title="Select an encounter"
              body="Choose a row to read the full note and coded terms."
            />
          )}
        </Box>
      </Box>
    </Box>
  );
}
