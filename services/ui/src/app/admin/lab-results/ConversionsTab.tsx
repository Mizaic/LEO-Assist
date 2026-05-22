"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
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
import { deleteUnitConversion, saveUnitConversion } from "./api";
import type { LabUnitConversion } from "./types";

interface Props {
  conceptId: string;
  conversions: LabUnitConversion[];
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}

export default function ConversionsTab({
  conceptId,
  conversions,
  onRefresh,
  onToast,
}: Props) {
  const [unit, setUnit] = useState("");
  const [factor, setFactor] = useState("1");
  const [offset, setOffset] = useState("0");
  const [saving, setSaving] = useState(false);
  const [deleteUnit, setDeleteUnit] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    if (!unit.trim()) {
      setError("Enter a unit abbreviation.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveUnitConversion(conceptId, {
        unit: unit.trim(),
        factor: Number(factor),
        offset: Number(offset),
      });
      setUnit("");
      setFactor("1");
      setOffset("0");
      onToast("Conversion added.");
      await onRefresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save conversion.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(u: string) {
    setDeleteUnit(null);
    setError(null);
    try {
      await deleteUnitConversion(conceptId, u);
      onToast("Conversion removed.");
      await onRefresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to remove conversion.");
    }
  }

  return (
    <Stack spacing={2}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {conversions.length > 0 ? (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Unit</TableCell>
              <TableCell align="right">Factor</TableCell>
              <TableCell align="right">Offset</TableCell>
              <TableCell width={48} />
            </TableRow>
          </TableHead>
          <TableBody>
            {conversions.map((c) => (
              <TableRow key={c.unit}>
                <TableCell>{c.unit}</TableCell>
                <TableCell align="right">{c.factor}</TableCell>
                <TableCell align="right">{c.offset}</TableCell>
                <TableCell align="right">
                  <IconButton
                    size="small"
                    aria-label={"Remove conversion for " + c.unit}
                    onClick={() => setDeleteUnit(c.unit)}
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
          No conversions yet. Add one below.
        </Typography>
      )}
      <Stack direction="row" spacing={1.5} alignItems="flex-start" flexWrap="wrap">
        <TextField
          label="Accepted unit"
          size="small"
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          sx={{ width: 160 }}
          placeholder="e.g. mmol/L"
        />
        <TextField
          label="Factor"
          size="small"
          value={factor}
          onChange={(e) => setFactor(e.target.value)}
          sx={{ width: 100 }}
        />
        <TextField
          label="Offset"
          size="small"
          value={offset}
          onChange={(e) => setOffset(e.target.value)}
          sx={{ width: 100 }}
        />
        <Box sx={{ pt: "4px" }}>
          <ToolbarActions
            actions={[
              {
                id: "add-conversion",
                label: saving ? "Adding..." : "Add conversion",
                variant: "secondary",
                disabled: saving,
                onClick: handleAdd,
              },
            ]}
          />
        </Box>
      </Stack>
      {deleteUnit && (
        <ConfirmDialog
          title="Remove unit conversion?"
          body={"Remove the conversion for \"" + deleteUnit + "\"? This cannot be undone."}
          confirmLabel="Remove"
          variant="danger"
          onConfirm={() => handleDelete(deleteUnit)}
          onCancel={() => setDeleteUnit(null)}
        />
      )}
    </Stack>
  );
}
