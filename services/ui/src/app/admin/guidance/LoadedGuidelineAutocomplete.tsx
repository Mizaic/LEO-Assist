/**
 * Atlas trace:
 *   DI: DI-8DD23CE2, DI-EB716E68
 * Search-and-pick over guidelines already in the knowledge graph.
 * Same list as Clinical Guidelines and Validation Lab brainstorm.
 */
"use client";

import { useEffect, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";

export interface LoadedGuidelineOption {
  code: string;
  title: string;
  guideline_source: "nice_syndication_api" | "local_guideline";
  recommendation_count?: number;
}

export interface LoadedGuidelineAutocompleteProps {
  valueCode: string | null;
  onChange: (next: LoadedGuidelineOption | null) => void;
  label?: string;
  helperText?: string;
  testId?: string;
  inputTestId?: string;
}

async function fetchLoadedGuidelines(): Promise<LoadedGuidelineOption[]> {
  const res = await fetch("/api/nice/loaded", { credentials: "include" });
  if (!res.ok) {
    throw new Error("Could not load guidelines from the knowledge graph.");
  }
  const rows = (await res.json()) as LoadedGuidelineOption[];
  return Array.isArray(rows) ? rows : [];
}

export default function LoadedGuidelineAutocomplete({
  valueCode,
  onChange,
  label = "Guideline",
  helperText,
  testId,
  inputTestId,
}: LoadedGuidelineAutocompleteProps) {
  const [options, setOptions] = useState<LoadedGuidelineOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchLoadedGuidelines()
      .then((rows) => {
        if (!cancelled) setOptions(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected =
    options.find((opt) => opt.code === valueCode) ??
    (valueCode
      ? {
          code: valueCode,
          title: valueCode,
          guideline_source: "nice_syndication_api" as const,
        }
      : null);

  return (
    <Autocomplete
      options={options}
      loading={loading}
      value={selected}
      onChange={(_e, value) => onChange(value)}
      getOptionKey={(opt) => opt.code}
      getOptionLabel={(opt) => `${opt.code} -- ${opt.title || "Untitled"}`}
      isOptionEqualToValue={(a, b) => a.code === b.code}
      filterOptions={(opts, state) => {
        const q = state.inputValue.trim().toLowerCase();
        if (!q) return opts;
        return opts.filter(
          (opt) =>
            opt.code.toLowerCase().includes(q) ||
            (opt.title || "").toLowerCase().includes(q),
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder="Search loaded guidelines"
          helperText={error || helperText}
          error={Boolean(error)}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {loading ? <CircularProgress size={16} sx={{ mr: 1 }} /> : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
          inputProps={{
            ...params.inputProps,
            ...(inputTestId ? { "data-testid": inputTestId } : {}),
          }}
        />
      )}
      data-testid={testId}
    />
  );
}
