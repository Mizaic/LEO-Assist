/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import Alert from "@mui/material/Alert";
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
import { color } from "@leo/design-system/tokens";

import ConfirmDialog from "@/components/ConfirmDialog";

import { ConfirmRows, formCardStyle, formGridStyle, spanTwo } from "./labConfigForm";
import type { LabUnitConversion } from "./types";
import { useConversionsTab } from "./useConversionsTab";

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
  const page = useConversionsTab({ conceptId, onRefresh, onToast });
  return (
    <Stack spacing={2}>
      {page.error ? (
        <Alert severity="error" onClose={() => page.setError(null)}>
          {page.error}
        </Alert>
      ) : null}
      <ConversionTable rows={conversions} onDelete={page.setDeleteUnit} />
      <ConversionForm
        draft={{ unit: page.unit, factor: page.factor, offset: page.offset }}
        saving={page.saving}
        onPatch={(patch) => {
          if (patch.unit != null) page.setUnit(patch.unit);
          if (patch.factor != null) page.setFactor(patch.factor);
          if (patch.offset != null) page.setOffset(patch.offset);
        }}
        onSubmit={() => page.setPending(true)}
      />
      {page.pending ? (
        <ConfirmDialog
          title="Add this conversion?"
          body="Check the unit maths, then save. Cancel leaves the list unchanged."
          confirmLabel="Add conversion"
          busy={page.saving}
          maxWidth="sm"
          onConfirm={() => void page.handleAdd()}
          onCancel={() => page.setPending(false)}
        >
          <ConfirmRows
            rows={[
              { label: "Unit", value: page.unit.trim() || "Missing" },
              { label: "Factor", value: page.factor },
              { label: "Offset", value: page.offset },
            ]}
          />
        </ConfirmDialog>
      ) : null}
      {page.deleteUnit ? (
        <ConfirmDialog
          title="Remove unit conversion?"
          body={'Remove the conversion for "' + page.deleteUnit + '"? This cannot be undone.'}
          confirmLabel="Remove"
          variant="danger"
          onConfirm={() => page.handleDelete(page.deleteUnit as string)}
          onCancel={() => page.setDeleteUnit(null)}
        />
      ) : null}
    </Stack>
  );
}

function ConversionTable({
  rows,
  onDelete,
}: {
  rows: LabUnitConversion[];
  onDelete: (unit: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: color.text.secondary }}>
        No conversions yet. Add one below.
      </Typography>
    );
  }
  return (
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
        {rows.map((c) => (
          <TableRow key={c.unit}>
            <TableCell>{c.unit}</TableCell>
            <TableCell align="right">{c.factor}</TableCell>
            <TableCell align="right">{c.offset}</TableCell>
            <TableCell align="right">
              <IconButton
                size="small"
                aria-label={"Remove conversion for " + c.unit}
                onClick={() => onDelete(c.unit)}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ConversionForm({
  draft,
  saving,
  onPatch,
  onSubmit,
}: {
  draft: { unit: string; factor: string; offset: string };
  saving: boolean;
  onPatch: (patch: { unit?: string; factor?: string; offset?: string }) => void;
  onSubmit: () => void;
}) {
  return (
    <fieldset data-testid="add-conversion-form" style={formCardStyle}>
      <legend style={{ padding: "0 6px" }}>Add conversion</legend>
      <div style={{ ...formGridStyle, marginTop: 8 }}>
        <div style={spanTwo()}>
          <TextField
            label="Accepted unit"
            size="small"
            value={draft.unit}
            onChange={(e) => onPatch({ unit: e.target.value })}
            placeholder="e.g. mmol/L"
            fullWidth
          />
        </div>
        <TextField
          label="Factor"
          size="small"
          value={draft.factor}
          onChange={(e) => onPatch({ factor: e.target.value })}
          inputMode="decimal"
          fullWidth
        />
        <TextField
          label="Offset"
          size="small"
          value={draft.offset}
          onChange={(e) => onPatch({ offset: e.target.value })}
          inputMode="decimal"
          fullWidth
        />
      </div>
      <div style={{ marginTop: 12 }}>
        <ToolbarActions
          align="start"
          actions={[
            {
              id: "add-conversion",
              label: "Review conversion",
              variant: "primary",
              disabled: saving,
              onClick: onSubmit,
            },
          ]}
        />
      </div>
    </fieldset>
  );
}
