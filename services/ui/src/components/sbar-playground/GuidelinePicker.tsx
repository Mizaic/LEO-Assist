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
 * GuidelinePicker -- multi-select over the loaded NICE guidelines.
 *
 * Design Controls: DI-LEO-AI-233.
 *
 * Wraps MUI Autocomplete (multiple) over the same data source as
 * services/ui/src/app/admin/guidance/LoadedGuidelinesPanel.tsx
 * (`/api/nice/loaded`). Adds an "Use all loaded" shortcut button.
 *
 * Emits an array of guideline codes. Empty array means "use all
 * loaded" downstream (the SBAR orchestrator interprets an empty
 * `guideline_ids` list as the global scope).
 */

import { useEffect, useMemo, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

interface LoadedGuideline {
  code: string;
  title: string;
}

export interface GuidelinePickerProps {
  value: string[];
  onChange: (codes: string[]) => void;
  /** Optional: override the loader for tests. */
  loader?: () => Promise<LoadedGuideline[]>;
  density?: "compact" | "comfortable";
  helperText?: string;
}

async function defaultLoader(): Promise<LoadedGuideline[]> {
  const r = await fetch("/api/nice/loaded");
  if (!r.ok) throw new Error("Could not load guidelines");
  const data = (await r.json()) as Array<LoadedGuideline & Record<string, unknown>>;
  return data.map((d) => ({ code: d.code, title: d.title }));
}

export function GuidelinePicker({
  value,
  onChange,
  loader,
  density = "compact",
  helperText,
}: GuidelinePickerProps) {
  const [options, setOptions] = useState<LoadedGuideline[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useMemo(() => loader ?? defaultLoader, [loader]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    load()
      .then((rows) => {
        if (!cancelled) setOptions(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load the list of guidelines.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const selected = useMemo(
    () => options.filter((o) => value.includes(o.code)),
    [options, value],
  );

  const allSelected =
    options.length > 0 && selected.length === options.length;

  return (
    <Stack spacing={1} data-testid="guideline-picker">
      <Autocomplete
        multiple
        size={density === "compact" ? "small" : "medium"}
        options={options}
        loading={loading}
        value={selected}
        onChange={(_e, next) => onChange(next.map((g) => g.code))}
        getOptionLabel={(o) => `${o.code}  -  ${o.title}`}
        isOptionEqualToValue={(a, b) => a.code === b.code}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Pick guidelines (optional)"
            placeholder={
              selected.length === 0 ? "Search by code or title" : ""
            }
            helperText={
              error ??
              helperText ??
              "Leave empty to evaluate against every loaded guideline."
            }
            error={Boolean(error)}
            InputProps={{
              ...params.InputProps,
              endAdornment: (
                <>
                  {loading ? (
                    <CircularProgress size={16} sx={{ mr: 1 }} />
                  ) : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            }}
          />
        )}
        renderTags={(tagValue, getTagProps) =>
          tagValue.map((option, index) => (
            <Chip
              variant="outlined"
              size="small"
              label={option.code}
              {...getTagProps({ index })}
              key={option.code}
              data-testid={`guideline-picker-chip-${option.code}`}
            />
          ))
        }
      />
      <Box>
        <Button
          size="small"
          onClick={() =>
            onChange(allSelected ? [] : options.map((o) => o.code))
          }
          disabled={loading || options.length === 0}
          data-testid="guideline-picker-toggle-all"
        >
          {allSelected ? "Clear" : "Use all loaded"}
        </Button>
        {options.length > 0 && (
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ ml: 1 }}
          >
            {options.length} guidelines loaded
          </Typography>
        )}
      </Box>
    </Stack>
  );
}
