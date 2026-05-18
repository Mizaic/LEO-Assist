/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Single-concept SNOMED picker -- inline replacement for the
 * SNOMED ID + Term TextField pair in the per-aspect editor.
 *
 * Backed by the production terminology service (/api/terminology/search)
 * so a code picked here is guaranteed to exist in the knowledge graph
 * and the PATCH /test-patients/{id}/full pre-flight will not reject it.
 *
 * Audience standard (UK reading age 11):
 *   - placeholder: "Search a clinical term, like cough or weight loss";
 *   - each option shows the plain-English term first and the SNOMED
 *     id underneath as supporting detail (never the other way round);
 *   - the field is also a free-text input so a reviewer who already
 *     knows the SNOMED id can type or paste it directly.
 *
 * The picker is debounced ~250 ms (matching ConceptSearchPanel) so we
 * do not hammer the terminology service while the user is still typing.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { searchTerminology, type TerminologyHit } from "../api";

interface SnomedConceptPickerProps {
  conceptId: string;
  term: string | null;
  onChange: (next: { conceptId: string; term: string }) => void;
  disabled?: boolean;
  /** Used for stable test ids so each row in a list is addressable. */
  testIdSuffix?: string;
}

const DEBOUNCE_MS = 250;

function freeTextHit(value: string): TerminologyHit {
  return { snomed_concept_id: value.trim(), term: "" };
}

export default function SnomedConceptPicker({
  conceptId,
  term,
  onChange,
  disabled = false,
  testIdSuffix,
}: SnomedConceptPickerProps) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<TerminologyHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqRef = useRef(0);

  // The currently-selected value is reconstructed from the controlled
  // conceptId / term props so the parent stays the source of truth.
  // An empty conceptId means "no value selected" (renders an empty
  // input, not a stale chip).
  const selected = useMemo<TerminologyHit | null>(() => {
    if (!conceptId) return null;
    return { snomed_concept_id: conceptId, term: term ?? "" };
  }, [conceptId, term]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setOptions([]);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const handle = window.setTimeout(() => {
      const myReq = ++reqRef.current;
      searchTerminology(trimmed)
        .then((hits) => {
          if (myReq !== reqRef.current) return;
          setOptions(hits);
        })
        .catch(() => {
          if (myReq !== reqRef.current) return;
          setError("Could not search the clinical terms. Please try again.");
          setOptions([]);
        })
        .finally(() => {
          if (myReq !== reqRef.current) return;
          setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query]);

  const dataTestId = testIdSuffix
    ? `snomed-concept-picker-${testIdSuffix}`
    : "snomed-concept-picker";

  return (
    <Autocomplete
      size="small"
      sx={{ minWidth: 320, flex: 1 }}
      options={options}
      value={selected}
      inputValue={query}
      onInputChange={(_, next) => setQuery(next)}
      onChange={(_, next) => {
        if (next === null) {
          onChange({ conceptId: "", term: "" });
          return;
        }
        const hit =
          typeof next === "string" ? freeTextHit(next) : (next as TerminologyHit);
        onChange({
          conceptId: hit.snomed_concept_id.trim(),
          term: hit.term ?? "",
        });
      }}
      filterOptions={(opts) => opts}
      loading={loading}
      disabled={disabled}
      freeSolo
      autoHighlight
      clearOnBlur={false}
      handleHomeEndKeys
      noOptionsText={
        query.trim().length < 2
          ? "Type at least 2 letters to search"
          : error
            ? error
            : "No clinical terms match. Try a shorter word or a different spelling."
      }
      isOptionEqualToValue={(opt, val) =>
        typeof opt !== "string" &&
        typeof val !== "string" &&
        opt.snomed_concept_id === val.snomed_concept_id
      }
      getOptionLabel={(opt) => {
        if (typeof opt === "string") return opt;
        if (opt.term && opt.snomed_concept_id) {
          return `${opt.term} (${opt.snomed_concept_id})`;
        }
        return opt.term || opt.snomed_concept_id;
      }}
      renderOption={(props, opt) => {
        const hit = opt as TerminologyHit;
        // MUI v5.13+ injects `key` into `props`. React drops keys from
        // spread props, so destructure it and pass it explicitly --
        // otherwise React logs "each child should have a unique key".
        // SNOMED ids alone are not unique within an option list (the
        // same concept can be returned twice for different surface
        // forms), so fall back to MUI's key when ids collide.
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
            <Typography
              variant="body2"
              sx={{ fontWeight: 500, lineHeight: 1.2 }}
            >
              {hit.term || "(no term)"}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              SNOMED {hit.snomed_concept_id}
              {hit.semantic_tag ? ` - ${hit.semantic_tag}` : ""}
            </Typography>
          </Box>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label="Clinical term"
          placeholder="Search a clinical term, like cough or weight loss"
          required
          inputProps={{
            ...params.inputProps,
            "aria-label": "Search a clinical term",
            "data-testid": dataTestId,
          }}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {loading ? (
                  <CircularProgress
                    size={16}
                    aria-label="Searching clinical terms"
                  />
                ) : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
          error={Boolean(error)}
          helperText={
            error
              ? error
              : conceptId && !term
                ? `Using SNOMED ${conceptId} (no term yet -- pick a result to fill the term)`
                : "Pick a result so the SNOMED id and the term stay in sync."
          }
        />
      )}
    />
  );
}
