"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Button from "@mui/material/Button";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import CloseIcon from "@mui/icons-material/Close";
import { OverviewTab } from "./OverviewTab";
import { InputsTab } from "./InputsTab";
import { OutputsTab } from "./OutputsTab";
import { ReviewTab } from "./ReviewTab";
import { ConditionRuleBuilder } from "./ConditionRuleBuilder";
import type { ActionConfig, FieldMappingRow } from "../config/types";

export function SidePanel({
  nodeId,
  config,
  prevStepWrites,
  onConfigChange,
  onDelete,
  onClose,
}: {
  nodeId: string;
  config: ActionConfig;
  prevStepWrites: string[] | null;
  onConfigChange: (nodeId: string, config: ActionConfig) => void;
  onDelete: (nodeId: string) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState(0);
  const rules = useMemo(
    () =>
      (config.params.rules as Array<{ id: string; field: string; operator: "==" | "!=" | ">" | "<" | "contains" | "exists"; value: string; outputPort: string }> | undefined) ?? [],
    [config.params.rules],
  );

  const patchConfig = (patch: Partial<ActionConfig>) => onConfigChange(nodeId, { ...config, ...patch });
  const patchParams = (patch: Record<string, unknown>) =>
    onConfigChange(nodeId, { ...config, params: { ...config.params, ...patch } });

  return (
    <Box sx={{ width: 420, borderLeft: 1, borderColor: "divider", display: "flex", flexDirection: "column", bgcolor: "background.paper", flexShrink: 0 }}>
      <Box sx={{ px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="subtitle2" sx={{ flex: 1 }}>{config.label || "Configure node"}</Typography>
        <IconButton size="small" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </Box>
      <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto">
        <Tab label="Overview" />
        <Tab label="Inputs" />
        <Tab label="Outputs" />
        <Tab label="Review" />
      </Tabs>
      <Divider />
      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        {tab === 0 && <OverviewTab config={config} onChange={patchConfig} />}
        {tab === 1 && (
          config.nodeType === "condition" ? (
            <ConditionRuleBuilder
              rules={rules}
              defaultPort={String((config.params.defaultPort as string | undefined) || "else")}
              onRulesChange={(nextRules) => patchParams({ rules: nextRules })}
              onDefaultPortChange={(port) => patchParams({ defaultPort: port })}
            />
          ) : (
            <InputsTab config={config} prevStepWrites={prevStepWrites} onChange={patchConfig} />
          )
        )}
        {tab === 2 && (
          <OutputsTab
            config={config}
            onRowsChange={(rows: FieldMappingRow[]) => patchParams({ field_mappings: rows })}
          />
        )}
        {tab === 3 && <ReviewTab config={config} />}
      </Box>
      <Divider />
      <Stack direction="row" spacing={1} sx={{ p: 1.5 }}>
        <Button color="error" startIcon={<DeleteOutlineIcon />} onClick={() => onDelete(nodeId)} sx={{ textTransform: "none" }}>
          Delete
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" onClick={() => onClose()} sx={{ textTransform: "none" }}>
          Done
        </Button>
      </Stack>
    </Box>
  );
}

