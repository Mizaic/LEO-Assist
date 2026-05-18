/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

/**
 * PatientFinder -- shared primitive for picking a patient by Search,
 * Filter, or Saved cohort.
 *
 * Design Controls: DI-LEO-AI-230, R-LEO-AI-NEW (patient mismatch).
 *
 * NHS number and date of birth are MANDATORY columns on every result
 * row so a reviewer can confirm the correct patient before selecting.
 *
 * Consumed by:
 *   - SbarPlayground (admin AI Summarisation surface)
 *   - /cohorts (saved-cohort browsing)
 *   - any future surface that needs a "pick a patient" affordance
 *
 * Emits a SelectedPatient {id, displayName, dob, nhsNumber} via the
 * `onSelect` callback. The dialog auto-closes on selection.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import {
  fetchCohorts,
  patientsByCohort,
  patientsByFilter,
  previewCohort,
  searchPatients,
  type Cohort,
  type CohortFilter,
  type PatientFinderRow,
} from "@/lib/analyticsApi";
import { useDemoMode } from "@/context/DemoModeContext";
import {
  maskBirthDate,
  maskGpName,
  maskNhsNumber,
  maskPatientId,
} from "@/lib/demoMode";

// -- Types ----------------------------------------------------------------

export interface SelectedPatient {
  id: string;
  displayName: string | null;
  dob: string | null;
  nhsNumber: string | null;
}

export interface PatientFinderProps {
  open: boolean;
  onClose: () => void;
  onSelect: (patient: SelectedPatient) => void;
  /** Optional: pre-select a tab on open. Defaults to "search". */
  initialTab?: "search" | "filter" | "cohort";
  /** Compact = list rows only show NHS+DOB inline (default true). */
  density?: "compact" | "comfortable";
}

type FinderTab = "search" | "filter" | "cohort";

const DEFAULT_TAB: FinderTab = "search";

// Plain-English helpers (reading age 9-11) used by the Filter tab.
const SEX_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Any" },
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
];

const SMOKING_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Any" },
  { value: "current_smoker", label: "Current smoker" },
  { value: "ever_smoker", label: "Ever smoked" },
];

const OUTCOME_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Any outcome" },
  { value: "confirmed_cancer", label: "Cancer confirmed" },
  { value: "two_week_wait_route", label: "On a 2WW (urgent) pathway" },
  { value: "benign", label: "Benign / not cancer" },
  { value: "in_progress", label: "Still being worked up" },
  { value: "any_open", label: "Any open episode" },
];

// -- Component ------------------------------------------------------------

export function PatientFinder({
  open,
  onClose,
  onSelect,
  initialTab = DEFAULT_TAB,
  density = "compact",
}: PatientFinderProps) {
  const [tab, setTab] = useState<FinderTab>(initialTab);

  useEffect(() => {
    if (open) setTab(initialTab);
  }, [open, initialTab]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      data-testid="patient-finder"
      aria-labelledby="patient-finder-title"
    >
      <DialogTitle
        id="patient-finder-title"
        sx={{ display: "flex", alignItems: "center", gap: 1 }}
      >
        Find a patient
        <Box sx={{ flexGrow: 1 }} />
        <IconButton
          size="small"
          onClick={onClose}
          aria-label="Close patient finder"
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <Tabs
        value={tab}
        onChange={(_e, v) => setTab(v as FinderTab)}
        aria-label="Patient finder tabs"
        sx={{ px: 2 }}
      >
        <Tab
          label="Search"
          value="search"
          data-testid="patient-finder-tab-search"
        />
        <Tab
          label="Filter"
          value="filter"
          data-testid="patient-finder-tab-filter"
        />
        <Tab
          label="Saved cohort"
          value="cohort"
          data-testid="patient-finder-tab-cohort"
        />
      </Tabs>
      <Divider />
      <DialogContent>
        {tab === "search" && (
          <SearchTab onSelect={onSelect} density={density} />
        )}
        {tab === "filter" && (
          <FilterTab onSelect={onSelect} density={density} />
        )}
        {tab === "cohort" && (
          <CohortTab onSelect={onSelect} density={density} />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// -- Search tab -----------------------------------------------------------

function SearchTab({
  onSelect,
  density,
}: {
  onSelect: (p: SelectedPatient) => void;
  density: "compact" | "comfortable";
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PatientFinderRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const needle = q.trim();
    if (needle.length < 2) {
      setResults([]);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(async () => {
      try {
        const r = await searchPatients(needle, 25);
        if (!cancelled) {
          setResults(r.results);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not search patients.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [q]);

  return (
    <Stack spacing={1.5} sx={{ pt: 1 }}>
      <TextField
        autoFocus
        fullWidth
        size="small"
        label="Find a patient"
        placeholder="Type a name, NHS number, date of birth, or local id"
        helperText="At least 2 letters or digits."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        inputProps={{ "data-testid": "patient-finder-search-input" }}
      />
      <ResultsList
        rows={results}
        loading={loading}
        error={error}
        onSelect={onSelect}
        density={density}
        emptyMessage={
          q.trim().length < 2
            ? "Start typing to find a patient."
            : "No patients matched. Try a different name or NHS number."
        }
      />
    </Stack>
  );
}

// -- Filter tab -----------------------------------------------------------

function FilterTab({
  onSelect,
  density,
}: {
  onSelect: (p: SelectedPatient) => void;
  density: "compact" | "comfortable";
}) {
  const [filters, setFilters] = useState<CohortFilter>({});
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [results, setResults] = useState<PatientFinderRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = useCallback((patch: Partial<CohortFilter>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
  }, []);

  const isEmpty = useMemo(() => {
    return Object.values(filters).every(
      (v) => v === undefined || v === "" || (Array.isArray(v) && v.length === 0),
    );
  }, [filters]);

  const onPreview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await previewCohort(filters);
      setPreviewCount(p.patient_count);
      const r = await patientsByFilter(filters, 50, 0);
      setResults(r.results);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not match patients with these filters.",
      );
    } finally {
      setLoading(false);
    }
  }, [filters]);

  return (
    <Stack spacing={2} sx={{ pt: 1 }}>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        <NumberField
          label="Age from"
          value={filters.age_min}
          onChange={(n) => update({ age_min: n })}
        />
        <NumberField
          label="Age to"
          value={filters.age_max}
          onChange={(n) => update({ age_max: n })}
        />
        <SelectField
          label="Sex"
          value={filters.sex ?? ""}
          options={SEX_OPTIONS}
          onChange={(v) => update({ sex: v || undefined })}
        />
        <SelectField
          label="Smoking"
          value={filters.smoking_status ?? ""}
          options={SMOKING_OPTIONS}
          onChange={(v) =>
            update({
              smoking_status:
                (v as CohortFilter["smoking_status"]) || undefined,
            })
          }
        />
      </Stack>

      <Tooltip
        title="1 = poorest area, 10 = richest area"
        placement="top-start"
      >
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
          <NumberField
            label="How well-off the area is (from)"
            value={filters.imd_decile_min}
            onChange={(n) => update({ imd_decile_min: n })}
          />
          <NumberField
            label="How well-off the area is (to)"
            value={filters.imd_decile_max}
            onChange={(n) => update({ imd_decile_max: n })}
          />
        </Stack>
      </Tooltip>

      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        <NumberField
          label="Visits in the last year (from)"
          value={filters.encounter_count_min}
          onChange={(n) => update({ encounter_count_min: n })}
        />
        <NumberField
          label="Visits in the last year (to)"
          value={filters.encounter_count_max}
          onChange={(n) => update({ encounter_count_max: n })}
        />
        <NumberField
          label="Window (months)"
          value={filters.encounter_count_window_months}
          onChange={(n) => update({ encounter_count_window_months: n })}
        />
      </Stack>

      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Long-term condition area"
          placeholder="e.g. cancer_audit"
          value={filters.episode_domain ?? ""}
          onChange={(e) =>
            update({ episode_domain: e.target.value || undefined })
          }
        />
        <TextField
          size="small"
          label="Sub-area"
          placeholder="e.g. breast"
          value={filters.episode_subdomain ?? ""}
          onChange={(e) =>
            update({ episode_subdomain: e.target.value || undefined })
          }
        />
        <SelectField
          label="Outcome"
          value={filters.episode_outcome ?? ""}
          options={OUTCOME_OPTIONS}
          onChange={(v) =>
            update({
              episode_outcome:
                (v as CohortFilter["episode_outcome"]) || undefined,
            })
          }
        />
      </Stack>

      <Stack direction="row" spacing={1} alignItems="center">
        <Button
          variant="contained"
          onClick={onPreview}
          disabled={isEmpty || loading}
          data-testid="patient-finder-filter-preview"
        >
          {loading ? "Matching..." : "Match patients"}
        </Button>
        {typeof previewCount === "number" && (
          <Chip
            size="small"
            label={`Found ${previewCount} patients`}
            color={previewCount > 0 ? "primary" : "default"}
            data-testid="patient-finder-filter-count"
          />
        )}
      </Stack>

      <ResultsList
        rows={results}
        loading={loading}
        error={error}
        onSelect={onSelect}
        density={density}
        emptyMessage={
          previewCount === null
            ? "Set a filter and tap Match patients."
            : "No patients matched. Try widening the filter."
        }
      />
    </Stack>
  );
}

// -- Cohort tab -----------------------------------------------------------

function CohortTab({
  onSelect,
  density,
}: {
  onSelect: (p: SelectedPatient) => void;
  density: "compact" | "comfortable";
}) {
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [cohortId, setCohortId] = useState<string>("");
  const [results, setResults] = useState<PatientFinderRow[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCohorts()
      .then((rows) => {
        if (!cancelled) setCohorts(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load saved cohorts.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onPick = useCallback(async (id: string) => {
    setCohortId(id);
    if (!id) {
      setResults([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await patientsByCohort(id, 50, 0);
      setResults(r.results);
      setTotal(r.total);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load cohort patients.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <Stack spacing={1.5} sx={{ pt: 1 }}>
      <FormControl size="small" fullWidth>
        <InputLabel id="patient-finder-cohort-label">Saved cohort</InputLabel>
        <Select
          labelId="patient-finder-cohort-label"
          label="Saved cohort"
          value={cohortId}
          onChange={(e) => onPick(String(e.target.value))}
          inputProps={{ "data-testid": "patient-finder-cohort-select" }}
        >
          <MenuItem value="">
            <em>Pick a cohort</em>
          </MenuItem>
          {cohorts.map((c) => (
            <MenuItem key={c.cohort_id} value={c.cohort_id}>
              {c.name}
              {typeof c.patient_count === "number"
                ? ` (${c.patient_count})`
                : ""}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {cohortId && (
        <Typography variant="caption" color="text.secondary">
          Showing first {results.length} of {total} patients in this cohort.
        </Typography>
      )}
      <ResultsList
        rows={results}
        loading={loading}
        error={error}
        onSelect={onSelect}
        density={density}
        emptyMessage={
          cohortId
            ? "No patients in this cohort."
            : "Pick a saved cohort to list its patients."
        }
      />
    </Stack>
  );
}

// -- Shared atoms ---------------------------------------------------------

function ResultsList({
  rows,
  loading,
  error,
  onSelect,
  density,
  emptyMessage,
}: {
  rows: PatientFinderRow[];
  loading: boolean;
  error: string | null;
  onSelect: (p: SelectedPatient) => void;
  density: "compact" | "comfortable";
  emptyMessage: string;
}) {
  const { isDemoMode } = useDemoMode();

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }
  if (error) {
    return (
      <Typography color="error" variant="body2" data-testid="patient-finder-error">
        {error}
      </Typography>
    );
  }
  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {emptyMessage}
      </Typography>
    );
  }
  return (
    <List dense={density === "compact"} disablePadding>
      {rows.map((r) => {
        const displayName = isDemoMode
          ? maskPatientId(r.id)
          : r.display_name || "(no recorded name)";
        const nhsLabel = isDemoMode
          ? maskNhsNumber(r.nhs_number)
          : r.nhs_number || "unknown";
        const dobLabel = isDemoMode
          ? maskBirthDate(r.dob)
          : r.dob || "unknown";
        const secondary = [
          r.gender ? `Sex: ${r.gender}` : null,
          r.registered_org_id
            ? `GP: ${isDemoMode ? maskGpName(r.registered_org_id) : r.registered_org_id}`
            : null,
          `Local id: ${isDemoMode ? maskPatientId(r.id) : r.id}`,
        ]
          .filter(Boolean)
          .join("  -  ");

        return (
          <ListItem key={r.id} disablePadding>
            <ListItemButton
              onClick={() =>
                onSelect({
                  id: r.id,
                  displayName: r.display_name ?? null,
                  dob: r.dob ?? null,
                  nhsNumber: r.nhs_number ?? null,
                })
              }
              data-testid={`patient-finder-row-${r.id}`}
            >
              <ListItemText
                primary={
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" fontWeight={600}>
                      {displayName}
                    </Typography>
                    <Chip
                      size="small"
                      label={`NHS: ${nhsLabel}`}
                      variant="outlined"
                      data-testid={`patient-finder-row-${r.id}-nhs`}
                    />
                    <Chip
                      size="small"
                      label={`DOB: ${dobLabel}`}
                      variant="outlined"
                      data-testid={`patient-finder-row-${r.id}-dob`}
                    />
                  </Stack>
                }
                secondary={secondary}
              />
            </ListItemButton>
          </ListItem>
        );
      })}
    </List>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | undefined;
  onChange: (next: number | undefined) => void;
}) {
  return (
    <TextField
      size="small"
      type="number"
      label={label}
      value={value ?? ""}
      onChange={(e) => {
        const v = e.target.value;
        if (v === "") {
          onChange(undefined);
        } else {
          const n = Number(v);
          onChange(Number.isFinite(n) ? n : undefined);
        }
      }}
      sx={{ minWidth: 160 }}
    />
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (v: string) => void;
}) {
  return (
    <FormControl size="small" sx={{ minWidth: 180 }}>
      <InputLabel>{label}</InputLabel>
      <Select
        label={label}
        value={value}
        onChange={(e) => onChange(String(e.target.value))}
      >
        {options.map((o) => (
          <MenuItem key={o.value || "__any"} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
