"use client";

import Stack from "@mui/material/Stack";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import type { ConditionRule } from "../config/types";

export function ConditionRuleBuilder({
  rules,
  defaultPort,
  onRulesChange,
  onDefaultPortChange,
}: {
  rules: ConditionRule[];
  defaultPort: string;
  onRulesChange: (rules: ConditionRule[]) => void;
  onDefaultPortChange: (port: string) => void;
}) {
  const patchRule = (id: string, patch: Partial<ConditionRule>) =>
    onRulesChange(rules.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const removeRule = (id: string) => onRulesChange(rules.filter((r) => r.id !== id));
  const addRule = () =>
    onRulesChange([
      ...rules,
      { id: `rule_${Date.now()}`, field: "is_verified", operator: "==", value: "true", outputPort: "verified" },
    ]);

  return (
    <Stack spacing={1.5}>
      {rules.map((rule) => (
        <Paper key={rule.id} variant="outlined" sx={{ p: 1 }}>
          <Stack spacing={1}>
            <Stack direction="row" spacing={1}>
              <TextField size="small" label="Field" value={rule.field} onChange={(e) => patchRule(rule.id, { field: e.target.value })} sx={{ flex: 1 }} />
              <Select size="small" value={rule.operator} onChange={(e) => patchRule(rule.id, { operator: e.target.value as ConditionRule["operator"] })}>
                <MenuItem value="==">==</MenuItem>
                <MenuItem value="!=">!=</MenuItem>
                <MenuItem value=">">{">"}</MenuItem>
                <MenuItem value="<">{"<"}</MenuItem>
                <MenuItem value="contains">contains</MenuItem>
                <MenuItem value="exists">exists</MenuItem>
              </Select>
              <TextField size="small" label="Value" value={rule.value} onChange={(e) => patchRule(rule.id, { value: e.target.value })} sx={{ flex: 1 }} />
              <IconButton size="small" color="error" onClick={() => removeRule(rule.id)}><DeleteOutlineIcon fontSize="small" /></IconButton>
            </Stack>
            <TextField size="small" label="Output port" value={rule.outputPort} onChange={(e) => patchRule(rule.id, { outputPort: e.target.value })} />
          </Stack>
        </Paper>
      ))}
      <Button size="small" variant="outlined" onClick={addRule} sx={{ alignSelf: "flex-start", textTransform: "none" }}>+ Add rule</Button>
      <TextField size="small" label="Default port" value={defaultPort} onChange={(e) => onDefaultPortChange(e.target.value)} />
    </Stack>
  );
}

