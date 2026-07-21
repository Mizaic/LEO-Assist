"use client";
/**
 * Inline OBSERVATION leaf row.
 * Supports absolute mode (chip + operator + value + unit + recency).
 * Advanced modes (temporal / reference_range / trend / aggregation)
 * render read-only with a hint.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { useMotion } from "@leo/design-system";

import { OBSERVATION_MODE_LABELS, OPERATOR_LABELS, friendlyTerm } from "../copy";
import type { EditableLogicNode, EditableObservationPayload, NodeUpdate, ObservationOperator } from "../types";
import { popVariants } from "../../motionPresets";

function pickMode(obs: EditableObservationPayload): string {
  if (obs.temporal) return "temporal";
  if (obs.reference_range) return "reference_range";
  if (obs.trend) return "trend";
  if (obs.aggregation) return "aggregate";
  return "absolute";
}

interface Props {
  node: EditableLogicNode;
  onUpdate: (update: NodeUpdate) => void;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
}

export default function ObservationRow({ node, onUpdate, onSelect }: Props) {
  const obs = node.observation;
  const { reducedMotion } = useMotion();
  const entrance = popVariants(reducedMotion);

  if (!obs) {
    return (
      <fm.div variants={entrance} initial="initial" animate="animate">
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ my: 0.5 }}>
          <Chip label="Lab value needs attention" size="small" color="warning" variant="outlined" />
          <Tooltip title="Remove this lab value">
            <IconButton size="small" aria-label="Remove this lab value"
              onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}>
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </fm.div>
    );
  }

  const mode = pickMode(obs);
  const term = friendlyTerm(obs.observable_term) || "Lab value";

  if (mode !== "absolute") {
    return (
      <fm.div variants={entrance} initial="initial" animate="animate">
        <Box sx={{ my: 0.5, px: 1.25, py: 1, bgcolor: "info.50",
          border: "1px dashed", borderColor: "info.200", borderRadius: 1.5 }}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="body2" sx={{ fontWeight: 600, color: "info.dark" }}>{term}</Typography>
            <Chip label={OBSERVATION_MODE_LABELS[mode] ?? mode}
              size="small" color="info" variant="outlined"
              sx={{ height: 22, fontSize: "0.72rem" }} />
            <Typography variant="caption" color="text.secondary">
              Open timing settings to edit.
            </Typography>
            <Box sx={{ flex: 1 }} />
            <Tooltip title="Remove this lab value">
              <IconButton size="small" aria-label="Remove this lab value"
                onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}>
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>
      </fm.div>
    );
  }

  const setObs = (patch: Partial<EditableObservationPayload>) =>
    onUpdate({ kind: "set_observation", nodeId: node.node_id,
      observation: { ...obs, ...patch } });

  const isBetween = obs.operator === "between";
  const lo = Array.isArray(obs.value) ? obs.value[0] : obs.value;
  const hi = Array.isArray(obs.value) ? obs.value[1] : "";

  return (
    <fm.div variants={entrance} initial="initial" animate="animate">
    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ my: 0.5, flexWrap: "wrap" }}>
      <Chip label={term} size="small"
        color={obs.observable_id ? "success" : "warning"}
        variant={obs.observable_id ? "filled" : "outlined"}
        onClick={(e) => onSelect(node.node_id, e.currentTarget)}
        sx={{ fontSize: "0.8rem" }}
        aria-label={`${term}. Click to swap.`}
      />
      <Select size="small" value={obs.operator ?? ">="}
        onChange={(e) => {
          const next = String(e.target.value) as ObservationOperator;
          if (next === "between" && !Array.isArray(obs.value)) {
            setObs({ operator: next, value: [Number(obs.value ?? 0), Number(obs.value ?? 0)] });
          } else if (next !== "between" && Array.isArray(obs.value)) {
            setObs({ operator: next, value: Number(obs.value[0]) });
          } else {
            setObs({ operator: next });
          }
        }}
        inputProps={{ "aria-label": "How to compare the lab value" }}
        sx={{ minWidth: 130, fontSize: "0.8rem" }}
      >
        {([">=", "<=", ">", "<", "=", "between"] as ObservationOperator[]).map((o) => (
          <MenuItem key={o} value={o}>{OPERATOR_LABELS[o] ?? o}</MenuItem>
        ))}
      </Select>
      <TextField size="small" type="number" value={String(lo ?? "")}
        onChange={(e) => {
          const n = Number(e.target.value);
          isBetween
            ? setObs({ value: [n, Number(hi ?? n)] })
            : setObs({ value: Number.isFinite(n) ? n : 0 });
        }}
        placeholder="400"
        inputProps={{ "aria-label": isBetween ? "Lower bound" : "Value" }}
        sx={{ width: 90 }}
      />
      {isBetween && (
        <>
          <Typography variant="body2" color="text.secondary">and</Typography>
          <TextField size="small" type="number" value={String(hi ?? "")}
            onChange={(e) => {
              const n = Number(e.target.value);
              setObs({ value: [Number(lo ?? 0), Number.isFinite(n) ? n : 0] });
            }}
            placeholder="500"
            inputProps={{ "aria-label": "Upper bound" }}
            sx={{ width: 90 }}
          />
        </>
      )}
      <TextField size="small" value={obs.unit ?? ""}
        onChange={(e) => setObs({ unit: e.target.value })}
        placeholder="mmol/L"
        inputProps={{ "aria-label": "Unit" }}
        sx={{ width: 90 }}
      />
      <Tooltip title="Remove this lab value">
        <IconButton size="small" aria-label="Remove this lab value"
          onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}>
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
    </fm.div>
  );
}
