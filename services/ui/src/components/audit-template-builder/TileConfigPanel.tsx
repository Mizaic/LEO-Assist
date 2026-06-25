"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Right panel: configure the selected tile.
 * Chart type is shown as a visual grid — compatible types are
 * selectable; incompatible types are greyed with a tooltip.
 */

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Divider from "@mui/material/Divider";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import BarChartIcon from "@mui/icons-material/BarChart";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import NumbersIcon from "@mui/icons-material/Numbers";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import TimelineIcon from "@mui/icons-material/Timeline";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import BlockIcon from "@mui/icons-material/Block";
import WidgetsOutlinedIcon from "@mui/icons-material/WidgetsOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import { type AuditTile, type TileType, WIDGET_CATALOGUE } from "@/lib/auditTemplateApi";

const ALL_TYPES: TileType[] = [
  "kpi_strip", "bar_chart", "line_chart", "interval_plot", "table", "text",
];

const TYPE_META: Record<TileType, { Icon: React.ElementType; label: string; colour: string }> = {
  bar_chart:     { Icon: BarChartIcon,           label: "Bar chart",     colour: "#1E40AF" },
  line_chart:    { Icon: ShowChartIcon,           label: "Line chart",    colour: "#047857" },
  kpi_strip:     { Icon: NumbersIcon,             label: "KPI strip",     colour: "#7C3AED" },
  table:         { Icon: TableChartOutlinedIcon,  label: "Table",         colour: "#0E7490" },
  interval_plot: { Icon: TimelineIcon,            label: "Interval plot", colour: "#B45309" },
  text:          { Icon: TextFieldsIcon,          label: "Text",          colour: "#475569" },
  widget:        { Icon: WidgetsOutlinedIcon,     label: "Widget",        colour: "#92400E" },
};

interface TileConfigPanelProps {
  tile: AuditTile;
  compatibleTypes?: TileType[];
  recommendedType?: TileType;
  onChange: (updated: AuditTile) => void;
  onRemove?: (id: string) => void;
}

function TypeGrid({
  current,
  compatible,
  recommended,
  onChange,
}: {
  current: TileType;
  compatible: TileType[];
  recommended: TileType;
  onChange: (t: TileType) => void;
}) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
        Chart type
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 0.75,
        }}
      >
        {ALL_TYPES.map((type) => {
          const { Icon, label, colour } = TYPE_META[type];
          const isSelected = type === current;
          const isCompatible = compatible.includes(type);
          const isRecommended = type === recommended;

          return (
            <Tooltip
              key={type}
              title={
                !isCompatible
                  ? "Not compatible with this metric's data shape"
                  : isRecommended
                  ? "Recommended for this metric"
                  : ""
              }
              placement="top"
            >
              <Box
                component={isCompatible ? "button" : "div"}
                onClick={isCompatible ? () => onChange(type) : undefined}
                aria-label={isCompatible ? `Use ${label}` : `${label} (not compatible)`}
                aria-pressed={isSelected}
                sx={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 0.5,
                  p: 0.75,
                  border: "1.5px solid",
                  borderColor: isSelected ? colour : isCompatible ? "divider" : "divider",
                  borderRadius: 1.5,
                  bgcolor: isSelected
                    ? `${colour}12`
                    : isCompatible
                    ? "background.paper"
                    : "grey.50",
                  cursor: isCompatible ? "pointer" : "default",
                  opacity: isCompatible ? 1 : 0.4,
                  transition: "all 120ms ease-out",
                  boxShadow: isSelected ? `0 0 0 2px ${colour}30` : "none",
                  outline: "none",
                  font: "inherit",
                  position: "relative",
                  "&:hover": isCompatible
                    ? {
                        borderColor: colour,
                        bgcolor: `${colour}08`,
                      }
                    : undefined,
                }}
              >
                {isCompatible ? (
                  <Icon sx={{ fontSize: 18, color: isSelected ? colour : "text.secondary" }} />
                ) : (
                  <BlockIcon sx={{ fontSize: 18, color: "text.disabled" }} />
                )}
                <Typography
                  variant="caption"
                  sx={{
                    fontSize: 10,
                    fontWeight: isSelected ? 700 : 400,
                    color: isSelected ? colour : isCompatible ? "text.secondary" : "text.disabled",
                    lineHeight: 1.2,
                    textAlign: "center",
                  }}
                >
                  {label}
                </Typography>
                {isRecommended && isCompatible && !isSelected && (
                  <Tooltip title="Recommended">
                    <StarOutlineIcon
                      sx={{
                        fontSize: 10,
                        color: colour,
                        position: "absolute",
                        top: 3,
                        right: 3,
                      }}
                    />
                  </Tooltip>
                )}
              </Box>
            </Tooltip>
          );
        })}
      </Box>
      {!compatible.includes(current) && (
        <Typography variant="caption" color="warning.dark" sx={{ display: "block", mt: 0.75, fontSize: 10 }}>
          Current type may not match this metric's data.
        </Typography>
      )}
    </Box>
  );
}

export default function TileConfigPanel({
  tile,
  compatibleTypes,
  recommendedType,
  onChange,
  onRemove,
}: TileConfigPanelProps) {
  const compatible = compatibleTypes ?? ALL_TYPES;
  const recommended = recommendedType ?? tile.tile_type;

  const update = (patch: Partial<AuditTile>) => onChange({ ...tile, ...patch });

  // Widget tiles have no chart-type choice -- show a fixed-widget notice instead.
  if (tile.tile_type === "widget") {
    const widgetEntry = WIDGET_CATALOGUE.find(
      (w) => w.widget_id === tile.metric_id
    );
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

        {/* Fixed widget notice */}
        <Box
          sx={{
            border: "1px solid",
            borderColor: "warning.200",
            borderRadius: 1.5,
            p: 1.25,
            bgcolor: "#FFFBEB",
            display: "flex",
            gap: 1,
            alignItems: "flex-start",
          }}
        >
          <LockOutlinedIcon sx={{ fontSize: 14, color: "warning.dark", mt: 0.2, flexShrink: 0 }} />
          <Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.25 }}>
              <WidgetsOutlinedIcon sx={{ fontSize: 12, color: "warning.dark" }} />
              <Typography variant="caption" fontWeight={700} color="warning.dark">
                Fixed widget
              </Typography>
            </Box>
            {widgetEntry ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ fontSize: 10, lineHeight: 1.5 }}>
                {widgetEntry.description}
              </Typography>
            ) : (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ fontSize: 10 }}>
                This widget renders a full NCDA section. Its appearance cannot be changed.
              </Typography>
            )}
          </Box>
        </Box>

        <TextField
          label="Section heading (optional)"
          size="small"
          value={tile.section ?? ""}
          onChange={(e) => update({ section: e.target.value || undefined })}
          helperText="Group tiles under a heading in the report"
          fullWidth
        />

        {onRemove && (
          <>
            <Divider />
            <Button
              size="small"
              color="error"
              variant="outlined"
              startIcon={<DeleteOutlineIcon />}
              onClick={() => onRemove(tile.tile_id)}
              fullWidth
            >
              Remove widget
            </Button>
          </>
        )}
      </Box>
    );
  }

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

      <TypeGrid
        current={tile.tile_type}
        compatible={compatible}
        recommended={recommended}
        onChange={(t) => update({ tile_type: t })}
      />

      <TextField
        label="Section heading (optional)"
        size="small"
        value={tile.section ?? ""}
        onChange={(e) => update({ section: e.target.value || undefined })}
        helperText="Group tiles under a heading in the report"
        fullWidth
      />

      <Divider />

      <Box>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
          Metric
        </Typography>
        <Chip
          label={tile.metric_id}
          size="small"
          variant="outlined"
          sx={{ fontSize: 11, maxWidth: "100%" }}
        />
      </Box>

      {onRemove && (
        <>
          <Divider />
          <Button
            size="small"
            color="error"
            variant="outlined"
            startIcon={<DeleteOutlineIcon />}
            onClick={() => onRemove(tile.tile_id)}
            fullWidth
          >
            Remove tile
          </Button>
        </>
      )}
    </Box>
  );
}
