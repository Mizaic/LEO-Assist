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
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { color } from "@leo/design-system/tokens";

import ConfirmDialog from "@/components/ConfirmDialog";
import { SnomedPickConfirmDialog } from "@/components/SnomedPickConfirmDialog";

import { deleteInterpretation, saveInterpretation } from "./api";
import { FindingSnomedPicker, type LabSnomedPick } from "./FindingSnomedPicker";
import type { LabInterpretation } from "./types";

const CLASSIFICATION_OPTIONS = [
  { value: "high", label: "High" },
  { value: "low", label: "Low" },
  { value: "critically_high", label: "Critically high" },
  { value: "critically_low", label: "Critically low" },
  { value: "out_of_range", label: "Out of range" },
  { value: "normal", label: "Within range" },
] as const;

function classificationLabel(value: string): string {
  return CLASSIFICATION_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

interface Props {
  conceptId: string;
  displayName: string;
  interpretations: LabInterpretation[];
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}

export default function InterpretationsTab({
  conceptId,
  displayName,
  interpretations,
  onRefresh,
  onToast,
}: Props) {
  const [classification, setClassification] = useState("high");
  const [pending, setPending] = useState<LabSnomedPick | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteClass, setDeleteClass] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    if (!pending?.concept_id) {
      setError("Search SNOMED or Ask LEO, then pick a finding code.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveInterpretation(conceptId, {
        classification,
        finding_concept_id: pending.concept_id,
      });
      setPending(null);
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

  const seedText = `${classificationLabel(classification)} ${displayName}`.trim();

  return (
    <Stack spacing={2}>
      {error ? (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}
      <InterpretationTable rows={interpretations} onDelete={setDeleteClass} />
      <InterpretationForm
        classification={classification}
        onClassification={setClassification}
        seedText={seedText}
        pending={pending}
        onPick={setPending}
      />
      {pending ? (
        <SnomedPickConfirmDialog
          copy={{
            title: "Save this interpretation?",
            lead:
              "Map " +
              classificationLabel(classification) +
              " " +
              displayName +
              " to this finding.",
            confirmLabel: "Save interpretation",
          }}
          pick={{
            term: pending.term,
            conceptId: pending.concept_id,
            tag: pending.semantic_tag,
          }}
          contextRows={[
            { label: "Classification", value: classificationLabel(classification) },
            { label: "Test", value: displayName },
          ]}
          action={{
            busy: saving,
            onConfirm: () => void handleAdd(),
            onCancel: () => setPending(null),
          }}
        />
      ) : null}
      {deleteClass ? (
        <ConfirmDialog
          title="Remove interpretation?"
          body={'Remove the "' + deleteClass + '" interpretation mapping? This cannot be undone.'}
          confirmLabel="Remove"
          variant="danger"
          onConfirm={() => handleDelete(deleteClass)}
          onCancel={() => setDeleteClass(null)}
        />
      ) : null}
    </Stack>
  );
}

function InterpretationForm({
  classification,
  onClassification,
  seedText,
  pending,
  onPick,
}: {
  classification: string;
  onClassification: (next: string) => void;
  seedText: string;
  pending: LabSnomedPick | null;
  onPick: (pick: LabSnomedPick) => void;
}) {
  return (
    <>
      <FormControl size="small" sx={{ minWidth: 170, alignSelf: "flex-start" }}>
        <InputLabel id="classification-label">Classification</InputLabel>
        <Select
          labelId="classification-label"
          label="Classification"
          value={classification}
          onChange={(e) => onClassification(e.target.value)}
        >
          {CLASSIFICATION_OPTIONS.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <FindingSnomedPicker
        seedText={seedText}
        hintTags={["finding"]}
        pickedId={pending?.concept_id || ""}
        onPick={onPick}
        label="Search SNOMED"
      />
    </>
  );
}

function InterpretationTable({
  rows,
  onDelete,
}: {
  rows: LabInterpretation[];
  onDelete: (cls: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: color.text.secondary }}>
        No interpretation SNOMED codes yet.
      </Typography>
    );
  }
  return (
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
        {rows.map((i) => (
          <TableRow key={i.classification}>
            <TableCell>{classificationLabel(i.classification)}</TableCell>
            <TableCell>{i.concept_id}</TableCell>
            <TableCell>{i.term || "-"}</TableCell>
            <TableCell align="right">
              <IconButton
                size="small"
                aria-label={"Remove " + i.classification + " interpretation"}
                onClick={() => onDelete(i.classification)}
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

