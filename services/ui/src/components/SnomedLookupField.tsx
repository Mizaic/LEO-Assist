/**
 * Async SNOMED concept lookup for form editors.
 *
 * Atlas trace: DI-5C9CA57B
 */
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";

import { searchTerms } from "@/lib/api";

const SEARCH_DEBOUNCE_MS = 250;

type SnomedHit = {
  snomed_concept_id: string;
  term: string;
  semantic_tag?: string;
};

export interface SnomedLookupValue {
  conceptId: string;
  display: string;
}

export function SnomedLookupField({
  label,
  ariaLabel,
  semanticTags,
  value,
  onChange,
  placeholder = "Type at least 2 letters to search",
  testId,
  sx,
}: {
  label: string;
  ariaLabel: string;
  semanticTags: string[];
  value: SnomedLookupValue;
  onChange: (next: SnomedLookupValue) => void;
  placeholder?: string;
  testId?: string;
  sx?: SxProps<Theme>;
}) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<SnomedHit[]>([]);
  const [loading, setLoading] = useState(false);
  const reqRef = useRef(0);

  const selected = useMemo<SnomedHit | null>(() => {
    if (!value.conceptId) return null;
    return {
      snomed_concept_id: value.conceptId,
      term: value.display,
    };
  }, [value.conceptId, value.display]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setOptions([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const handle = window.setTimeout(() => {
      const myReq = ++reqRef.current;
      void searchTerms(
        trimmed,
        15,
        semanticTags.length > 0 ? semanticTags : undefined,
      )
        .then((rows) => {
          if (myReq !== reqRef.current) return;
          setOptions(rows);
        })
        .catch(() => {
          if (myReq !== reqRef.current) return;
          setOptions([]);
        })
        .finally(() => {
          if (myReq !== reqRef.current) return;
          setLoading(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query, semanticTags]);

  return (
    <Autocomplete
      size="small"
      sx={{ flex: 1, minWidth: 0, ...((sx as object) || {}) }}
      options={options}
      value={selected}
      inputValue={query}
      onInputChange={(_, next) => setQuery(next)}
      onChange={(_, hit) => {
        if (!hit) {
          onChange({ conceptId: "", display: "" });
          setQuery("");
          setOptions([]);
          return;
        }
        onChange({
          conceptId: hit.snomed_concept_id,
          display: hit.term || "",
        });
        setQuery("");
        setOptions([]);
      }}
      filterOptions={(opts) => opts}
      loading={loading}
      autoHighlight
      clearOnBlur={false}
      getOptionLabel={(opt) =>
        opt.term && opt.snomed_concept_id
          ? `${opt.term} (${opt.snomed_concept_id})`
          : opt.term || opt.snomed_concept_id
      }
      isOptionEqualToValue={(a, b) => a.snomed_concept_id === b.snomed_concept_id}
      noOptionsText={
        query.trim().length < 2
          ? "Type at least 2 letters to search"
          : "No SNOMED terms match"
      }
      slotProps={{
        popper: { placement: "bottom-start" },
        paper: { sx: { minWidth: 320 } },
      }}
      renderOption={(props, hit) => {
        const { key: muiKey, ...liProps } = props as typeof props & {
          key?: string | number;
        };
        return (
          <Box
            component="li"
            key={muiKey ?? hit.snomed_concept_id}
            {...liProps}
            sx={{ display: "block !important", py: 0.75 }}
          >
            <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.2 }}>
              {hit.term || "(no term)"}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {hit.snomed_concept_id}
              {hit.semantic_tag ? ` - ${hit.semantic_tag}` : ""}
            </Typography>
          </Box>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={placeholder}
          inputProps={{
            ...params.inputProps,
            "aria-label": ariaLabel,
            "data-testid": testId,
          }}
          InputProps={{
            ...params.InputProps,
            startAdornment: value.conceptId ? (
              <Chip
                size="small"
                label={chipLabel(value)}
                onDelete={() => {
                  onChange({ conceptId: "", display: "" });
                  setQuery("");
                }}
                sx={{ maxWidth: "100%", mr: 0.5 }}
                data-testid={testId ? `${testId}-chip` : "snomed-lookup-chip"}
              />
            ) : (
              params.InputProps.startAdornment
            ),
            endAdornment: (
              <>
                {loading ? (
                  <CircularProgress size={16} aria-label="Searching SNOMED terms" />
                ) : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
        />
      )}
    />
  );
}

function chipLabel(value: SnomedLookupValue): string {
  if (value.display && value.conceptId) {
    return `${value.display} (${value.conceptId})`;
  }
  return value.display || value.conceptId;
}
