"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  getLabResultConfig,
  listLabResultConfigs,
  saveInterpretation,
  saveLabResultConfig,
  saveReferenceRange,
  saveUnitConversion,
} from "./api";
import type { LabResultConfig, LabResultConfigSummary } from "./types";
import type {
  LabInterpretation,
  LabReferenceRange,
  LabUnitConversion,
} from "./types";

interface RangeForm {
  sex: string;
  age_min: string;
  age_max: string;
  low: string;
  high: string;
  critical_low: string;
  critical_high: string;
  source: string;
}

interface ConversionForm {
  unit: string;
  factor: string;
  offset: string;
}

interface InterpretationForm {
  classification: string;
  finding_concept_id: string;
}

const EMPTY_CONFIG = {
  conceptId: "",
  displayName: "",
  canonicalUnit: "",
  source: "manual",
};

export default function LabResultsPanel() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<LabResultConfigSummary[]>([]);
  const [selected, setSelected] = useState<LabResultConfig | null>(null);
  const [configForm, setConfigForm] = useState(EMPTY_CONFIG);
  const [conversion, setConversion] = useState({ unit: "", factor: "1", offset: "0" });
  const [range, setRange] = useState({
    sex: "all",
    age_min: "",
    age_max: "",
    low: "",
    high: "",
    critical_low: "",
    critical_high: "",
    source: "manual",
  });
  const [interpretation, setInterpretation] = useState({
    classification: "high",
    finding_concept_id: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedId = selected?.concept_id || configForm.conceptId;

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listLabResultConfigs(query);
      setItems(data.items || []);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load lab configs.");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const selectConfig = useCallback(async (conceptId: string) => {
    setError(null);
    try {
      const data = await getLabResultConfig(conceptId);
      setSelected(data.item);
      setConfigForm({
        conceptId: data.item.concept_id,
        displayName: data.item.display_name,
        canonicalUnit: data.item.canonical_unit,
        source: data.item.source || "manual",
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load config.");
    }
  }, []);

  const rangeRows = useMemo(() => selected?.ranges || [], [selected]);
  const conversionRows = useMemo(() => selected?.conversions || [], [selected]);
  const interpretationRows = useMemo(
    () => selected?.interpretations || [],
    [selected],
  );

  async function refreshSelected(conceptId = selectedId) {
    if (!conceptId) return;
    await selectConfig(conceptId);
    await loadList();
  }

  async function handleSaveConfig() {
    if (!configForm.conceptId.trim()) {
      setError("Enter the observable SNOMED code.");
      return;
    }
    await saveLabResultConfig(configForm.conceptId.trim(), {
      display_name: configForm.displayName,
      canonical_unit: configForm.canonicalUnit,
      source: configForm.source,
    });
    await refreshSelected(configForm.conceptId.trim());
  }

  async function handleSaveConversion() {
    if (!selectedId) return;
    await saveUnitConversion(selectedId, {
      unit: conversion.unit,
      factor: Number(conversion.factor),
      offset: Number(conversion.offset),
    });
    setConversion({ unit: "", factor: "1", offset: "0" });
    await refreshSelected();
  }

  async function handleSaveRange() {
    if (!selectedId) return;
    await saveReferenceRange(selectedId, {
      sex: range.sex,
      age_min: numberOrNull(range.age_min),
      age_max: numberOrNull(range.age_max),
      low: numberOrNull(range.low),
      high: numberOrNull(range.high),
      critical_low: numberOrNull(range.critical_low),
      critical_high: numberOrNull(range.critical_high),
      source: range.source,
    });
    await refreshSelected();
  }

  async function handleSaveInterpretation() {
    if (!selectedId) return;
    await saveInterpretation(selectedId, interpretation);
    setInterpretation({ classification: "high", finding_concept_id: "" });
    await refreshSelected();
  }

  return (
    <Stack spacing={3}>
      {error && <Alert severity="error">{error}</Alert>}
      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6">Results and labs</Typography>
            <Typography color="text.secondary">
              Configure reference ranges, unit conversions, and the SNOMED
              findings used when a result is high, low, or out of range.
            </Typography>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
              <TextField
                label="Search configs"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                size="small"
              />
              <Button onClick={loadList} variant="outlined" disabled={loading}>
                Search
              </Button>
            </Stack>
            <ConfigTable items={items} onSelect={selectConfig} />
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6">Observable config</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  label="Observable SNOMED"
                  value={configForm.conceptId}
                  onChange={(event) =>
                    setConfigForm({ ...configForm, conceptId: event.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  label="Display name"
                  value={configForm.displayName}
                  onChange={(event) =>
                    setConfigForm({ ...configForm, displayName: event.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} md={2}>
                <TextField
                  fullWidth
                  label="Canonical unit"
                  value={configForm.canonicalUnit}
                  onChange={(event) =>
                    setConfigForm({ ...configForm, canonicalUnit: event.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  label="Source"
                  value={configForm.source}
                  onChange={(event) =>
                    setConfigForm({ ...configForm, source: event.target.value })
                  }
                />
              </Grid>
            </Grid>
            <Box>
              <Button variant="contained" onClick={handleSaveConfig}>
                Save observable config
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {selected && (
        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="h6">{selected.display_name}</Typography>
                <Chip label={selected.concept_id} size="small" />
                <Chip label={selected.canonical_unit} size="small" />
              </Stack>
              <Divider />
              <EditableSections
                conversion={conversion}
                setConversion={setConversion}
                range={range}
                setRange={setRange}
                interpretation={interpretation}
                setInterpretation={setInterpretation}
                onSaveConversion={handleSaveConversion}
                onSaveRange={handleSaveRange}
                onSaveInterpretation={handleSaveInterpretation}
              />
              <SummaryTables
                conversions={conversionRows}
                ranges={rangeRows}
                interpretations={interpretationRows}
              />
            </Stack>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}

function ConfigTable({
  items,
  onSelect,
}: {
  items: LabResultConfigSummary[];
  onSelect: (conceptId: string) => void;
}) {
  if (!items.length) {
    return <Alert severity="info">No lab result configs found.</Alert>;
  }
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Observable</TableCell>
          <TableCell>SNOMED</TableCell>
          <TableCell>Canonical unit</TableCell>
          <TableCell />
        </TableRow>
      </TableHead>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.concept_id}>
            <TableCell>{item.display_name}</TableCell>
            <TableCell>{item.concept_id}</TableCell>
            <TableCell>{item.canonical_unit}</TableCell>
            <TableCell align="right">
              <Button size="small" onClick={() => onSelect(item.concept_id)}>
                Open
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function EditableSections(props: {
  conversion: ConversionForm;
  setConversion: Dispatch<SetStateAction<ConversionForm>>;
  range: RangeForm;
  setRange: Dispatch<SetStateAction<RangeForm>>;
  interpretation: InterpretationForm;
  setInterpretation: Dispatch<SetStateAction<InterpretationForm>>;
  onSaveConversion: () => void;
  onSaveRange: () => void;
  onSaveInterpretation: () => void;
}) {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={4}>
        <Stack spacing={1.5}>
          <Typography variant="subtitle1">Unit conversion</Typography>
          <TextField
            label="Accepted unit"
            value={props.conversion.unit}
            onChange={(e) => props.setConversion({ ...props.conversion, unit: e.target.value })}
          />
          <TextField
            label="Factor"
            value={props.conversion.factor}
            onChange={(e) => props.setConversion({ ...props.conversion, factor: e.target.value })}
          />
          <TextField
            label="Offset"
            value={props.conversion.offset}
            onChange={(e) => props.setConversion({ ...props.conversion, offset: e.target.value })}
          />
          <Button variant="outlined" onClick={props.onSaveConversion}>
            Add conversion
          </Button>
        </Stack>
      </Grid>
      <Grid item xs={12} md={4}>
        <Stack spacing={1.5}>
          <Typography variant="subtitle1">Reference range</Typography>
          {(
            [
              "sex",
              "age_min",
              "age_max",
              "low",
              "high",
              "critical_low",
              "critical_high",
              "source",
            ] as Array<keyof RangeForm>
          ).map((key) => (
            <TextField
              key={key}
              label={key.replaceAll("_", " ")}
              value={props.range[key] || ""}
              onChange={(e) => props.setRange({ ...props.range, [key]: e.target.value })}
            />
          ))}
          <Button variant="outlined" onClick={props.onSaveRange}>
            Add range
          </Button>
        </Stack>
      </Grid>
      <Grid item xs={12} md={4}>
        <Stack spacing={1.5}>
          <Typography variant="subtitle1">Interpretation SNOMED</Typography>
          <TextField
            label="Classification"
            helperText="high, low, out_of_range, critically_high, critically_low"
            value={props.interpretation.classification}
            onChange={(e) =>
              props.setInterpretation({
                ...props.interpretation,
                classification: e.target.value,
              })
            }
          />
          <TextField
            label="Finding SNOMED"
            value={props.interpretation.finding_concept_id}
            onChange={(e) =>
              props.setInterpretation({
                ...props.interpretation,
                finding_concept_id: e.target.value,
              })
            }
          />
          <Button variant="outlined" onClick={props.onSaveInterpretation}>
            Save interpretation
          </Button>
        </Stack>
      </Grid>
    </Grid>
  );
}

function SummaryTables({
  conversions,
  ranges,
  interpretations,
}: {
  conversions: LabUnitConversion[];
  ranges: LabReferenceRange[];
  interpretations: LabInterpretation[];
}) {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={4}>
        <Typography variant="subtitle2">Conversions</Typography>
        {conversions.map((row) => (
          <Typography key={row.unit} variant="body2">
            {row.unit}: x{row.factor} + {row.offset}
          </Typography>
        ))}
      </Grid>
      <Grid item xs={12} md={4}>
        <Typography variant="subtitle2">Ranges</Typography>
        {ranges.map((row) => (
          <Typography key={row.range_id} variant="body2">
            {row.sex || "all"} age {row.age_min ?? "-"}-{row.age_max ?? "-"}:
            {row.low ?? "-"} to {row.high ?? "-"}
          </Typography>
        ))}
      </Grid>
      <Grid item xs={12} md={4}>
        <Typography variant="subtitle2">Interpretations</Typography>
        {interpretations.map((row) => (
          <Typography key={row.classification} variant="body2">
            {row.classification}: {row.concept_id} {row.term || ""}
          </Typography>
        ))}
      </Grid>
    </Grid>
  );
}

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
