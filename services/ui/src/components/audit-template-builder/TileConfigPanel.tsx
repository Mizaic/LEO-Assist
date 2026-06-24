"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 * Right panel: configure the selected tile (label, section, tile type, params).
 */

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import { type AuditTile, type TileType } from "@/lib/auditTemplateApi";

const TILE_TYPES: TileType[] = [
  "bar_chart",
  "line_chart",
  "kpi_strip",
  "table",
  "interval_plot",
  "text",
];

interface TileConfigPanelProps {
  tile: AuditTile;
  onChange: (updated: AuditTile) => void;
}

export default function TileConfigPanel({ tile, onChange }: TileConfigPanelProps) {
  const update = (patch: Partial<AuditTile>) => onChange({ ...tile, ...patch });

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="subtitle2" fontWeight={700}>
        Tile settings
      </Typography>

      <TextField
        label="Label"
        size="small"
        value={tile.label}
        onChange={(e) => update({ label: e.target.value })}
        fullWidth
      />

      <FormControl size="small" fullWidth>
        <InputLabel>Chart type</InputLabel>
        <Select
          label="Chart type"
          value={tile.tile_type}
          onChange={(e) => update({ tile_type: e.target.value as TileType })}
        >
          {TILE_TYPES.map((t) => (
            <MenuItem key={t} value={t}>
              {t}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <Typography variant="caption" color="text.secondary">
        Metric: <strong>{tile.metric_id}</strong>
      </Typography>

      <TextField
        label="Section heading (optional)"
        size="small"
        value={(tile as unknown as Record<string, unknown>).section as string ?? ""}
        onChange={(e) =>
          onChange({ ...tile, ...(({ section: e.target.value } as unknown) as Partial<AuditTile>) })
        }
        helperText="Group tiles under a heading"
        fullWidth
      />
    </Box>
  );
}
