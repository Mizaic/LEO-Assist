/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
import { useMemo, useState } from "react";
import type { Edge, Node } from "@xyflow/react";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { SUBGRAPH_IO } from "../config/subgraphs";
import type { ActionConfig, ActionNodeData, FieldMappingRow } from "../config/types";
import { buildProducedFields } from "./usePredecessorIO";

export interface ValidationWarning {
  severity: "error" | "warning" | "info";
  message: string;
}

export function useValidationWarnings(
  nodes: Node[],
  edges: Edge[],
  nodeConfigs: Record<string, ActionConfig>,
  triggerEvent: string,
): ValidationWarning[] {
  return useMemo(() => {
    const warnings: ValidationWarning[] = [];
    if (nodes.length === 0) {
      warnings.push({ severity: "warning", message: "Pipeline has no action steps. Add at least one action." });
      return warnings;
    }
    if (!triggerEvent) {
      warnings.push({ severity: "error", message: "No trigger event configured. The pipeline cannot be invoked without a trigger." });
    }

    const ordered = [...nodes].sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0));
    const GLOBAL_KEYS = new Set(["encounter_text", "patient_id", "encounter_id", "run_id"]);

    for (const node of nodes) {
      const cfg = nodeConfigs[node.id];
      const inputSource = cfg?.inputSource ?? "previous_step";
      const nodeType = cfg?.nodeType ?? "action";

      if (nodeType === "condition") {
        const rules = (cfg?.params?.rules as Array<{ field?: string; outputPort?: string }> | undefined) ?? [];
        if (rules.length === 0) warnings.push({ severity: "warning", message: `"${cfg?.label || node.id}" has no condition rules configured.` });
        const outEdges = edges.filter((e) => e.source === node.id);
        if (outEdges.length === 0) warnings.push({ severity: "warning", message: `"${cfg?.label || node.id}" has no outgoing branches connected.` });
      }

      if (inputSource !== "previous_step" || nodeType !== "action") continue;

      const subgraphId = (node.data as unknown as ActionNodeData)?.subgraphId || "";
      const io = SUBGRAPH_IO[subgraphId];
      if (!io) continue;

      const predecessorIds = edges.filter((e) => e.target === node.id).map((e) => e.source);
      const predecessorWrites = new Set<string>([...GLOBAL_KEYS]);
      for (const predId of predecessorIds) {
        const predNode = nodes.find((n) => n.id === predId);
        const predSubgraphId = (predNode?.data as unknown as ActionNodeData | undefined)?.subgraphId;
        if (predSubgraphId) SUBGRAPH_IO[predSubgraphId]?.writes.forEach((w) => predecessorWrites.add(w));
      }

      const missingKeys = io.reads.filter((k) => !predecessorWrites.has(k));
      for (const key of missingKeys) {
        warnings.push({
          severity: predecessorIds.length === 0 ? "warning" : "error",
          message: `"${(node.data as unknown as ActionNodeData).label}" needs key "${key}" but ${predecessorIds.length === 0 ? "has no connected predecessor" : "the previous step does not produce it"}.`,
        });
      }

      if (io.requiredFields) {
        for (const predId of predecessorIds) {
          const predCfg = nodeConfigs[predId];
          const mappings = predCfg?.params?.field_mappings as FieldMappingRow[] | undefined;
          if (!mappings || mappings.length === 0) continue;
          const producedFields = buildProducedFields(mappings);
          for (const [stateKey, reqFields] of Object.entries(io.requiredFields)) {
            const produced = producedFields[stateKey];
            // Only validate sub-fields when the predecessor explicitly maps this key at
            // sub-field level (e.g. "entities[].text"). If produced is undefined the
            // predecessor passes the key through as a whole block — no false positive.
            if (!produced) continue;
            const missingFields = reqFields.filter((f) => !produced.has(f));
            if (missingFields.length > 0) {
              const label = (node.data as unknown as ActionNodeData).label;
              warnings.push({
                severity: "error",
                message: `"${label}" needs ${stateKey}[].${missingFields.join(", " + stateKey + "[].")} but the previous step's field mappings do not include ${missingFields.length === 1 ? "it" : "them"}. Update the previous step's mappings.`,
              });
            }
          }
        }
      }
    }

    const hasVerify = nodes.some((n) => (n.data as unknown as ActionNodeData)?.subgraphId === "verification");
    const hasPersist = nodes.some((n) => (n.data as unknown as ActionNodeData)?.subgraphId === "persist");
    const persistGold = nodes.some((n) => {
      const cfg = nodeConfigs[n.id];
      return (n.data as unknown as ActionNodeData)?.subgraphId === "persist" && cfg?.outputTarget === "gold_training";
    });
    if (hasPersist && persistGold && !hasVerify) {
      warnings.push({
        severity: "error",
        message: "Persisting to Gold Training without a Verification step. Unverified data could corrupt training labels.",
      });
    }
    if (hasVerify && hasPersist) {
      const verifyIdx = ordered.findIndex((n) => (n.data as unknown as ActionNodeData)?.subgraphId === "verification");
      const persistIdx = ordered.findIndex((n) => (n.data as unknown as ActionNodeData)?.subgraphId === "persist");
      if (verifyIdx > persistIdx) {
        warnings.push({
          severity: "error",
          message: "Verification runs AFTER persist. Move Verification before Persist so it can gate the output.",
        });
      }
    }

    const orphaned = nodes.filter((n) => {
      const hasIncoming = edges.some((e) => e.target === n.id);
      const isFirst = ordered[0]?.id === n.id;
      // Source nodes are data providers — they don't need an incoming edge.
      const isSource = n.type === "source";
      return !hasIncoming && !isFirst && !isSource;
    });
    for (const o of orphaned) {
      warnings.push({
        severity: "warning",
        message: `"${(o.data as unknown as ActionNodeData).label}" has no incoming edge — it won't receive data from previous steps.`,
      });
    }
    if (warnings.length === 0) warnings.push({ severity: "info", message: "Pipeline looks good. All steps are connected and I/O keys are consistent." });
    return warnings;
  }, [nodes, edges, nodeConfigs, triggerEvent]);
}

export function ValidationPanel({ warnings }: { warnings: ValidationWarning[] }) {
  const [expanded, setExpanded] = useState(false);
  const errorCount = warnings.filter((w) => w.severity === "error").length;
  const warnCount = warnings.filter((w) => w.severity === "warning").length;
  const allGood = errorCount === 0 && warnCount === 0;
  return (
    <Paper variant="outlined" sx={{ mx: 2, mt: 1 }}>
      <Box sx={{ px: 2, py: 1, display: "flex", alignItems: "center", gap: 1, cursor: "pointer" }} onClick={() => setExpanded((e) => !e)}>
        {allGood ? <CheckCircleOutlineIcon fontSize="small" color="success" /> : <WarningAmberIcon fontSize="small" color={errorCount > 0 ? "error" : "warning"} />}
        <Typography variant="subtitle2" sx={{ flex: 1 }}>Pipeline Validation</Typography>
        {errorCount > 0 && <Chip size="small" label={`${errorCount} error${errorCount > 1 ? "s" : ""}`} color="error" variant="outlined" />}
        {warnCount > 0 && <Chip size="small" label={`${warnCount} warning${warnCount > 1 ? "s" : ""}`} color="warning" variant="outlined" sx={{ ml: 0.5 }} />}
        {allGood && <Chip size="small" label="Valid" color="success" variant="outlined" />}
        {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
      </Box>
      {expanded && (
        <Box sx={{ px: 2, pb: 2 }}>
          <Divider sx={{ mb: 1 }} />
          <Stack spacing={0.5}>
            {warnings.map((w, i) => (
              <Alert key={i} severity={w.severity} sx={{ py: 0, fontSize: "0.78rem", "& .MuiAlert-message": { py: 0.5 } }}>
                {w.message}
              </Alert>
            ))}
          </Stack>
        </Box>
      )}
    </Paper>
  );
}

