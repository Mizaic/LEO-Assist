/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-E5B04297
 *   DO: DO-C38E6184
 *   VT: VT-409A9A74
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-E5B04297")
 */
"use client";

/**
 * Build age x lab-threshold situations (PSA / CA125 table shape).
 * Confirm returns a filled AgeLabBandSpec for the host to materialise.
 */
import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { OPERATOR_LABELS } from "../copy";
import { isLikelyObservable } from "../observableHit";
import type { ConceptSearchHit, ObservationOperator } from "../types";
import {
  DEFAULT_AGE_LAB_BANDS,
  validateAgeLabBandSpec,
  type AgeLabBandRow,
  type AgeLabBandSpec,
} from "./ageLabBands";

const OPS: ObservationOperator[] = [">", ">=", "<", "<=", "="];

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: (spec: AgeLabBandSpec) => void;
}

export default function AgeLabBandsDialog({ open, onClose, onConfirm }: Props) {
  const [query, setQuery] = useState("PSA");
  const [hits, setHits] = useState<ConceptSearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [observableId, setObservableId] = useState("");
  const [observableTerm, setObservableTerm] = useState("");
  const [unit, setUnit] = useState("ug/L");
  const [operator, setOperator] = useState<ObservationOperator>(">");
  const [bands, setBands] = useState<AgeLabBandRow[]>(DEFAULT_AGE_LAB_BANDS);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setHits([]);
      return;
    }
    setLoading(true);
    const handle = window.setTimeout(() => {
      const url =
        `/api/terminology/search?q=${encodeURIComponent(trimmed)}` +
        `&limit=12&semantic_tag=observable_entity`;
      fetch(url)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
        .then((rows: ConceptSearchHit[]) => {
          const list = Array.isArray(rows) ? rows : [];
          setHits(list.filter((h) => isLikelyObservable(h) || !!h.semantic_tag));
        })
        .catch(() => setHits([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query, open]);

  function updateBand(index: number, patch: Partial<AgeLabBandRow>) {
    setBands((prev) => prev.map((b, i) => (i === index ? { ...b, ...patch } : b)));
  }

  function handleConfirm() {
    const spec: AgeLabBandSpec = {
      observableId,
      observableTerm,
      unit,
      operator,
      bands,
    };
    const err = validateAgeLabBandSpec(spec);
    if (err) {
      setError(err);
      return;
    }
    setError(null);
    onConfirm(spec);
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Age and lab bands</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Build one situation per age range, each with its own lab
            threshold. Example: 40 to 49 with PSA more than 2 ug/L, or 50
            to 59 with PSA more than 3.5 ug/L.
          </Typography>

          <TextField
            size="small"
            label="Search lab reading"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            inputProps={{ "aria-label": "Search lab reading" }}
          />
          {loading && (
            <Typography variant="caption" color="text.secondary">
              Searching...
            </Typography>
          )}
          {!loading && hits.length > 0 && (
            <Box
              sx={{
                maxHeight: 160,
                overflowY: "auto",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
              }}
              aria-label="Lab reading search results"
            >
              {hits.map((hit) => (
                <Button
                  key={hit.snomed_concept_id}
                  fullWidth
                  size="small"
                  onClick={() => {
                    setObservableId(hit.snomed_concept_id);
                    setObservableTerm(hit.term);
                  }}
                  sx={{
                    justifyContent: "flex-start",
                    textTransform: "none",
                    bgcolor:
                      observableId === hit.snomed_concept_id
                        ? "action.selected"
                        : undefined,
                  }}
                >
                  {hit.term} ({hit.snomed_concept_id})
                </Button>
              ))}
            </Box>
          )}
          {observableId ? (
            <Typography variant="body2">
              Selected: <strong>{observableTerm}</strong> ({observableId})
            </Typography>
          ) : (
            <Typography variant="caption" color="text.secondary">
              Pick a lab reading above (for example serum PSA).
            </Typography>
          )}

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Select
              size="small"
              value={operator}
              onChange={(e) =>
                setOperator(String(e.target.value) as ObservationOperator)
              }
              inputProps={{ "aria-label": "Lab comparison" }}
              sx={{ minWidth: 140 }}
            >
              {OPS.map((op) => (
                <MenuItem key={op} value={op}>
                  {OPERATOR_LABELS[op] ?? op}
                </MenuItem>
              ))}
            </Select>
            <TextField
              size="small"
              label="Unit"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              inputProps={{ "aria-label": "Lab unit" }}
              sx={{ width: 120 }}
            />
          </Stack>

          <Typography variant="subtitle2">Bands</Typography>
          {bands.map((row, index) => (
            <Stack
              key={`band-${index}`}
              direction="row"
              spacing={1}
              alignItems="center"
              flexWrap="wrap"
              useFlexGap
            >
              <TextField
                size="small"
                label="Age from"
                type="number"
                value={row.ageFrom}
                onChange={(e) => updateBand(index, { ageFrom: e.target.value })}
                inputProps={{
                  "aria-label": `Age from for band ${index + 1}`,
                  style: { width: 72 },
                }}
              />
              <TextField
                size="small"
                label="Age to"
                type="number"
                value={row.ageTo}
                placeholder="blank = and over"
                onChange={(e) => updateBand(index, { ageTo: e.target.value })}
                inputProps={{
                  "aria-label": `Age to for band ${index + 1}`,
                  style: { width: 72 },
                }}
              />
              <TextField
                size="small"
                label="Lab value"
                type="number"
                value={row.value}
                onChange={(e) => updateBand(index, { value: e.target.value })}
                inputProps={{
                  "aria-label": `Lab value for band ${index + 1}`,
                  style: { width: 88 },
                }}
              />
              <IconButton
                size="small"
                aria-label={`Remove band ${index + 1}`}
                onClick={() =>
                  setBands((prev) => prev.filter((_, i) => i !== index))
                }
                disabled={bands.length <= 1}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Stack>
          ))}
          <Button
            size="small"
            onClick={() =>
              setBands((prev) => [
                ...prev,
                { ageFrom: "", ageTo: "", value: "" },
              ])
            }
          >
            Add band
          </Button>

          {error && (
            <Alert severity="warning" sx={{ py: 0.5 }}>
              {error}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleConfirm}>
          Create situations
        </Button>
      </DialogActions>
    </Dialog>
  );
}
