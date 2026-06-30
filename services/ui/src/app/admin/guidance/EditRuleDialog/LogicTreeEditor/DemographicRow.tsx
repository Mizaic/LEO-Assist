"use client";
/**
 * Inline age/sex demographic leaf row.
 * Field select, operator select, value input, unit input, remove.
 *
 * Atlas trace: DO-D6CE2AA5 / DI-A3107424
 */
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { DEMOGRAPHIC_FIELD_LABELS, OPERATOR_LABELS } from "../copy";
import { DEMOGRAPHIC_FIELDS, DEMOGRAPHIC_OPERATORS, type EditableLogicNode, type NodeUpdate } from "../types";

interface Props {
  node: EditableLogicNode;
  onUpdate: (update: NodeUpdate) => void;
}

export default function DemographicRow({ node, onUpdate }: Props) {
  const set = (patch: Partial<Parameters<typeof onUpdate>[0] & { kind: "set_demographic" }>) =>
    onUpdate({
      kind: "set_demographic",
      nodeId: node.node_id,
      field: node.field ?? "age",
      operator: node.operator ?? ">=",
      value: String(node.value ?? ""),
      unit: node.unit ?? "years",
      ...(patch as object),
    } as Parameters<typeof onUpdate>[0]);

  return (
    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexWrap: "wrap", my: 0.5 }}>
      <Select
        size="small"
        value={node.field ?? "age"}
        onChange={(e) => set({ field: String(e.target.value) })}
        inputProps={{ "aria-label": "What patient detail to check" }}
        sx={{ minWidth: 150, fontSize: "0.8rem" }}
      >
        {DEMOGRAPHIC_FIELDS.map((f) => (
          <MenuItem key={f} value={f}>
            {DEMOGRAPHIC_FIELD_LABELS[f] ?? f}
          </MenuItem>
        ))}
      </Select>
      <Select
        size="small"
        value={node.operator ?? ">="}
        onChange={(e) => set({ operator: String(e.target.value) })}
        inputProps={{ "aria-label": "How to compare" }}
        sx={{ minWidth: 130, fontSize: "0.8rem" }}
      >
        {DEMOGRAPHIC_OPERATORS.map((o) => (
          <MenuItem key={o} value={o}>
            {OPERATOR_LABELS[o] ?? o}
          </MenuItem>
        ))}
      </Select>
      <TextField
        size="small"
        value={node.value ?? ""}
        onChange={(e) => set({ value: e.target.value })}
        placeholder="40"
        inputProps={{ "aria-label": "Value to compare with" }}
        sx={{ width: 80 }}
      />
      <TextField
        size="small"
        value={node.unit ?? ""}
        onChange={(e) => set({ unit: e.target.value || null })}
        placeholder="years"
        inputProps={{ "aria-label": "Unit (for example: years)" }}
        sx={{ width: 90 }}
      />
      <Tooltip title="Remove this patient detail">
        <IconButton
          size="small"
          aria-label="Remove this patient detail"
          onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
        >
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}
