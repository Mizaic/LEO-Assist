/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { ToolbarActions } from "@leo/design-system";
import ConfirmDialog from "@/components/ConfirmDialog";
import { deleteReferenceRange, saveReferenceRange } from "./api";
import type { LabReferenceRange } from "./types";

interface Props {
  conceptId: string;
  ranges: LabReferenceRange[];
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}

function numOrNull(v: string): number | null {
  const n = Number(v);
  return v.trim() && Number.isFinite(n) ? n : null;
}

function fmtRange(low: number | null | undefined, high: number | null | undefined): string {
  if (low == null && high == null) return "-";
  return (low ?? "-") + " to " + (high ?? "-");
}

export default function RangesTab({ conceptId, ranges, onRefresh, onToast }: Props) {
  const [sex, setSex] = useState("all");
  const [ageMin, setAgeMin] = useState("");
  const [ageMax, setAgeMax] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [critLow, setCritLow] = useState("");
  const [critHigh, setCritHigh] = useState("");
  const [source, setSource] = useState("manual");
  const [saving, setSaving] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    setSaving(true);
    setError(null);
    try {
      await saveReferenceRange(conceptId, {
        sex,
        age_min: numOrNull(ageMin),
        age_max: numOrNull(ageMax),
        low: numOrNull(low),
        high: numOrNull(high),
        critical_low: numOrNull(critLow),
        critical_high: numOrNull(critHigh),
        source,
      });
      setAgeMin("");
      setAgeMax("");
      setLow("");
      setHigh("");
      setCritLow("");
      setCritHigh("");
      onToast("Range added.");
      await onRefresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save range.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    setDeleteId(null);
    setError(null);
    try {
      await deleteReferenceRange(conceptId, id);
      onToast("Range removed.");
      await onRefresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to remove range.");
    }
  }

  return (
    <Stack spacing={2}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {ranges.length > 0 ? (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Sex</TableCell>
              <TableCell>Age (years)</TableCell>
              <TableCell>Normal</TableCell>
              <TableCell>Critical</TableCell>
              <TableCell width={48} />
            </TableRow>
          </TableHead>
          <TableBody>
            {ranges.map((r) => (
              <TableRow key={r.range_id}>
                <TableCell>{r.sex || "all"}</TableCell>
                <TableCell>
                  {r.age_min ?? "-"} - {r.age_max ?? "-"}
                </TableCell>
                <TableCell>{fmtRange(r.low, r.high)}</TableCell>
                <TableCell>
                  {r.critical_low ?? "-"} / {r.critical_high ?? "-"}
                </TableCell>
                <TableCell align="right">
                  <IconButton
                    size="small"
                    aria-label={"Remove range for " + (r.sex || "all")}
                    onClick={() => setDeleteId(r.range_id)}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <Typography variant="body2" color="text.secondary">
          No ranges yet. Add the first range below.
        </Typography>
      )}
      <Box
        component="fieldset"
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          p: 2,
          m: 0,
        }}
      >
        <Typography component="legend" variant="caption" sx={{ px: 0.5 }}>
          Add reference range
        </Typography>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="flex-start" sx={{ mt: 1.5 }}>
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel id="sex-label">Sex</InputLabel>
            <Select
              labelId="sex-label"
              label="Sex"
              value={sex}
              onChange={(e) => setSex(e.target.value)}
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="male">Male</MenuItem>
              <MenuItem value="female">Female</MenuItem>
            </Select>
          </FormControl>
          <TextField
            label="Min age (years)"
            size="small"
            value={ageMin}
            onChange={(e) => setAgeMin(e.target.value)}
            sx={{ width: 130 }}
          />
          <TextField
            label="Max age (years)"
            size="small"
            value={ageMax}
            onChange={(e) => setAgeMax(e.target.value)}
            sx={{ width: 130 }}
          />
          <TextField
            label="Low"
            size="small"
            value={low}
            onChange={(e) => setLow(e.target.value)}
            sx={{ width: 100 }}
            placeholder="lower normal"
          />
          <TextField
            label="High"
            size="small"
            value={high}
            onChange={(e) => setHigh(e.target.value)}
            sx={{ width: 100 }}
            placeholder="upper normal"
          />
          <TextField
            label="Critical low"
            size="small"
            value={critLow}
            onChange={(e) => setCritLow(e.target.value)}
            sx={{ width: 110 }}
          />
          <TextField
            label="Critical high"
            size="small"
            value={critHigh}
            onChange={(e) => setCritHigh(e.target.value)}
            sx={{ width: 110 }}
          />
          <TextField
            label="Source"
            size="small"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            sx={{ width: 120 }}
          />
          <Box sx={{ pt: "4px" }}>
            <ToolbarActions
              actions={[
                {
                  id: "add-range",
                  label: saving ? "Adding..." : "Add range",
                  variant: "secondary",
                  disabled: saving,
                  onClick: handleAdd,
                },
              ]}
            />
          </Box>
        </Stack>
      </Box>
      {deleteId && (
        <ConfirmDialog
          title="Remove reference range?"
          body="Remove this reference range? This cannot be undone."
          confirmLabel="Remove"
          variant="danger"
          onConfirm={() => handleDelete(deleteId)}
          onCancel={() => setDeleteId(null)}
        />
      )}
    </Stack>
  );
}
