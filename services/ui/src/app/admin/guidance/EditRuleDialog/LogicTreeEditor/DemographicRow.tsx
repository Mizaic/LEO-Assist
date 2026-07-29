"use client";
/**
 * Inline age/sex demographic leaf row.
 *
 * Age:  field select | age operator select | value | [and value2] | unit | delete
 * Sex:  field select | "is" (fixed label)  | Male/Female select   |      | delete
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { motion as fm } from "framer-motion";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { useMotion } from "@leo/design-system";

import { DEMOGRAPHIC_FIELD_LABELS, OPERATOR_LABELS } from "../copy";
import {
  DEMOGRAPHIC_FIELDS,
  DEMOGRAPHIC_OPERATORS,
  type EditableLogicNode,
  type NodeUpdate,
} from "../types";
import { popVariants } from "../../motionPresets";

// Operators that make sense for age only (sex supports "=" only).
const AGE_OPERATORS = DEMOGRAPHIC_OPERATORS;
const SEX_VALUES = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
] as const;

interface Props {
  node: EditableLogicNode;
  onUpdate: (update: NodeUpdate) => void;
}

export default function DemographicRow({ node, onUpdate }: Props) {
  const field = node.field ?? "age";
  const isSex = field === "sex";
  const isBetween = !isSex && (node.operator ?? ">=") === "between";
  const { reducedMotion } = useMotion();

  const set = (patch: Record<string, unknown>) =>
    onUpdate({
      kind: "set_demographic",
      nodeId: node.node_id,
      field,
      operator: isSex ? "=" : (node.operator ?? ">="),
      value: isSex ? String(node.value ?? "male") : String(node.value ?? ""),
      value2: node.value2 != null ? String(node.value2) : undefined,
      unit: isSex ? null : (node.unit ?? "years"),
      ...patch,
    } as Parameters<typeof onUpdate>[0]);

  function handleFieldChange(newField: string) {
    // Reset operator/value/unit to sensible defaults when field type changes.
    const defaults =
      newField === "sex"
        ? { field: newField, operator: "=", value: "male", value2: undefined, unit: null }
        : { field: newField, operator: ">=", value: "", value2: undefined, unit: "years" };
    onUpdate({
      kind: "set_demographic",
      nodeId: node.node_id,
      ...defaults,
    } as Parameters<typeof onUpdate>[0]);
  }

  return (
    <fm.div variants={popVariants(reducedMotion)} initial="initial" animate="animate">
    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexWrap: "wrap", my: 0.5 }}>
      {/* Field selector */}
      <Select
        size="small"
        value={field}
        onChange={(e) => handleFieldChange(String(e.target.value))}
        inputProps={{ "aria-label": "What patient detail to check" }}
        SelectDisplayProps={{ "aria-label": "What patient detail to check" }}
        sx={{ minWidth: 150, fontSize: "0.8rem" }}
      >
        {DEMOGRAPHIC_FIELDS.map((f) => (
          <MenuItem key={f} value={f}>
            {DEMOGRAPHIC_FIELD_LABELS[f] ?? f}
          </MenuItem>
        ))}
      </Select>

      {isSex ? (
        <>
          {/* Fixed "is" label for sex — only equality makes sense */}
          <Typography variant="body2" color="text.secondary" sx={{ px: 0.5, fontWeight: 500 }}>
            is
          </Typography>
          <Select
            size="small"
            value={String(node.value ?? "male")}
            onChange={(e) => set({ value: e.target.value })}
            inputProps={{ "aria-label": "Which sex" }}
            SelectDisplayProps={{ "aria-label": "Which sex" }}
            sx={{ minWidth: 110, fontSize: "0.8rem" }}
          >
            {SEX_VALUES.map(({ value, label }) => (
              <MenuItem key={value} value={value}>{label}</MenuItem>
            ))}
          </Select>
        </>
      ) : (
        <>
          {/* Age: operator + value(s) + unit */}
          <Select
            size="small"
            value={node.operator ?? ">="}
            onChange={(e) => set({ operator: String(e.target.value) })}
            inputProps={{ "aria-label": "How to compare age" }}
            SelectDisplayProps={{ "aria-label": "How to compare age" }}
            sx={{ minWidth: 130, fontSize: "0.8rem" }}
          >
            {AGE_OPERATORS.map((o) => (
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
            inputProps={{ "aria-label": "Lower bound" }}
            sx={{ width: 72 }}
          />
          {isBetween && (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ px: 0.25 }}>
                and
              </Typography>
              <TextField
                size="small"
                value={node.value2 ?? ""}
                onChange={(e) => set({ value2: e.target.value })}
                placeholder="49"
                inputProps={{ "aria-label": "Upper bound" }}
                sx={{ width: 72 }}
              />
            </>
          )}
          <TextField
            size="small"
            value={node.unit ?? ""}
            onChange={(e) => set({ unit: e.target.value || null })}
            placeholder="years"
            inputProps={{ "aria-label": "Unit (for example: years)" }}
            sx={{ width: 80 }}
          />
        </>
      )}

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
    </fm.div>
  );
}
