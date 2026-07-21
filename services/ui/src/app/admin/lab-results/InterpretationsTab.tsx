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
import { deleteInterpretation, saveInterpretation } from "./api";
import type { LabInterpretation } from "./types";

const CLASSIFICATION_OPTIONS = [
  "high",
  "low",
  "critically_high",
  "critically_low",
  "out_of_range",
];

interface Props {
  conceptId: string;
  interpretations: LabInterpretation[];
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}

export default function InterpretationsTab({
  conceptId,
  interpretations,
  onRefresh,
  onToast,
}: Props) {
  const [classification, setClassification] = useState("high");
  const [findingConceptId, setFindingConceptId] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteClass, setDeleteClass] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    if (!findingConceptId.trim()) {
      setError("Enter the finding SNOMED code.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveInterpretation(conceptId, {
        classification,
        finding_concept_id: findingConceptId.trim(),
      });
      setFindingConceptId("");
      onToast("Interpretation saved.");
      await onRefresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save interpretation.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(cls: string) {
    setDeleteClass(null);
    setError(null);
    try {
      await deleteInterpretation(conceptId, cls);
      onToast("Interpretation removed.");
      await onRefresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to remove interpretation.");
    }
  }

  return (
    <Stack spacing={2}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {interpretations.length > 0 ? (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Classification</TableCell>
              <TableCell>Finding SNOMED</TableCell>
              <TableCell>Term</TableCell>
              <TableCell width={48} />
            </TableRow>
          </TableHead>
          <TableBody>
            {interpretations.map((i) => (
              <TableRow key={i.classification}>
                <TableCell>{i.classification}</TableCell>
                <TableCell>{i.concept_id}</TableCell>
                <TableCell>{i.term || "-"}</TableCell>
                <TableCell align="right">
                  <IconButton
                    size="small"
                    aria-label={"Remove " + i.classification + " interpretation"}
                    onClick={() => setDeleteClass(i.classification)}
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
          No interpretation SNOMED codes yet.
        </Typography>
      )}
      <Stack direction="row" spacing={1.5} alignItems="flex-start" flexWrap="wrap">
        <FormControl size="small" sx={{ minWidth: 170 }}>
          <InputLabel id="classification-label">Classification</InputLabel>
          <Select
            labelId="classification-label"
            label="Classification"
            value={classification}
            onChange={(e) => setClassification(e.target.value)}
          >
            {CLASSIFICATION_OPTIONS.map((o) => (
              <MenuItem key={o} value={o}>
                {o}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <TextField
          label="Finding SNOMED code"
          size="small"
          value={findingConceptId}
          onChange={(e) => setFindingConceptId(e.target.value)}
          sx={{ width: 220 }}
          placeholder="e.g. 75540009"
        />
        <Box sx={{ pt: "4px" }}>
          <ToolbarActions
            actions={[
              {
                id: "add-interpretation",
                label: saving ? "Saving..." : "Save interpretation",
                variant: "secondary",
                disabled: saving,
                onClick: handleAdd,
              },
            ]}
          />
        </Box>
      </Stack>
      {deleteClass && (
        <ConfirmDialog
          title="Remove interpretation?"
          body={"Remove the \"" + deleteClass + "\" interpretation mapping? This cannot be undone."}
          confirmLabel="Remove"
          variant="danger"
          onConfirm={() => handleDelete(deleteClass)}
          onCancel={() => setDeleteClass(null)}
        />
      )}
    </Stack>
  );
}
