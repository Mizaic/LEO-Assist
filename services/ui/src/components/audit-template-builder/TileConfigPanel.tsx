"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * Right panel: configure the selected tile.
 * Two tabs: Settings (type, label, section) and Story (headline, highlight,
 * benchmarks, callout annotations, animate-in toggle).
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import BarChartIcon from "@mui/icons-material/BarChart";
import BlockIcon from "@mui/icons-material/Block";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import NumbersIcon from "@mui/icons-material/Numbers";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import TimelineIcon from "@mui/icons-material/Timeline";
import WidgetsOutlinedIcon from "@mui/icons-material/WidgetsOutlined";
import MenuItem from "@mui/material/MenuItem";
import {
  type AuditTile,
  type MetricParamSpec,
  type TileAnnotation,
  type TileStoryConfig,
  type TileType,
  WIDGET_CATALOGUE,
} from "@/lib/auditTemplateApi";

const ALL_TYPES: TileType[] = [
  "kpi_strip", "bar_chart", "line_chart", "interval_plot", "table", "text",
];

const TYPE_META: Record<TileType, { Icon: React.ElementType; label: string; colour: string }> = {
  bar_chart:     { Icon: BarChartIcon,           label: "Bar chart",     colour: "#002178" },
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
  /** The selected metric's param schema, used to render the Parameters tab. */
  paramSchema?: Record<string, MetricParamSpec>;
  onChange: (updated: AuditTile) => void;
  onRemove?: (id: string) => void;
}

// ---------------------------------------------------------------------------
// ParamsTab sub-component - renders controls from the metric param_schema
// ---------------------------------------------------------------------------

function humanise(key: string): string {
  const s = key.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function ParamField({
  name,
  spec,
  value,
  onChange,
}: {
  name: string;
  spec: MetricParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const label = humanise(name);
  const current = value ?? spec.default ?? "";

  if (spec.enum && spec.enum.length > 0) {
    return (
      <TextField
        select
        size="small"
        label={label}
        value={current === "" ? "" : String(current)}
        onChange={(e) => onChange(e.target.value || undefined)}
        fullWidth
      >
        <MenuItem value="">
          <em>Default</em>
        </MenuItem>
        {spec.enum.map((opt) => (
          <MenuItem key={opt} value={opt}>
            {humanise(opt)}
          </MenuItem>
        ))}
      </TextField>
    );
  }

  if (spec.type === "boolean") {
    return (
      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={Boolean(current)}
            onChange={(e) => onChange(e.target.checked)}
          />
        }
        label={<Typography variant="caption">{label}</Typography>}
        sx={{ ml: 0 }}
      />
    );
  }

  const isNumber = spec.type === "number" || spec.type === "integer";
  const isDate = spec.format === "date" || spec.format === "date-time";
  return (
    <TextField
      size="small"
      label={label}
      type={isDate ? "date" : isNumber ? "number" : "text"}
      value={current === undefined ? "" : String(current)}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw === "") return onChange(undefined);
        onChange(isNumber ? Number(raw) : raw);
      }}
      inputProps={isNumber ? { min: spec.minimum, max: spec.maximum } : undefined}
      InputLabelProps={isDate ? { shrink: true } : undefined}
      helperText={spec.required ? "Required" : undefined}
      fullWidth
    />
  );
}

function ParamsTab({
  schema,
  overrides,
  onChange,
}: {
  schema: Record<string, MetricParamSpec>;
  overrides: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const entries = Object.entries(schema);
  const setParam = (key: string, v: unknown) => {
    const next = { ...overrides };
    if (v === undefined) delete next[key];
    else next[key] = v;
    onChange(next);
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.75 }}>
      <Typography variant="caption" color="text.secondary">
        Override the metric&apos;s default settings for this tile. Leave a field
        blank to use the metric default.
      </Typography>
      {entries.map(([name, spec]) => (
        <ParamField
          key={name}
          name={name}
          spec={spec}
          value={overrides[name]}
          onChange={(v) => setParam(name, v)}
        />
      ))}
      {Object.keys(overrides).length > 0 && (
        <Button size="small" onClick={() => onChange({})} sx={{ alignSelf: "flex-start", fontSize: 11 }}>
          Reset all to defaults
        </Button>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// TypeGrid sub-component
// ---------------------------------------------------------------------------

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
      <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0.75 }}>
        {ALL_TYPES.map((type) => {
          const { Icon, label, colour } = TYPE_META[type];
          const isSelected = type === current;
          const isCompatible = compatible.includes(type);
          const isRecommended = type === recommended;
          return (
            <TypeCell
              key={type}
              type={type}
              Icon={Icon}
              label={label}
              colour={colour}
              isSelected={isSelected}
              isCompatible={isCompatible}
              isRecommended={isRecommended}
              onClick={isCompatible ? () => onChange(type) : undefined}
            />
          );
        })}
      </Box>
      {!compatible.includes(current) && (
        <Typography
          variant="caption"
          color="warning.dark"
          sx={{ display: "block", mt: 0.75, fontSize: 10 }}
        >
          Current type may not match this metric's data.
        </Typography>
      )}
    </Box>
  );
}

function TypeCell({
  Icon,
  label,
  colour,
  isSelected,
  isCompatible,
  isRecommended,
  onClick,
}: {
  type: TileType;
  Icon: React.ElementType;
  label: string;
  colour: string;
  isSelected: boolean;
  isCompatible: boolean;
  isRecommended: boolean;
  onClick?: () => void;
}) {
  return (
    <Tooltip
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
        onClick={onClick}
        aria-label={isCompatible ? `Use ${label}` : `${label} (not compatible)`}
        aria-pressed={isSelected}
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 0.5,
          p: 0.75,
          border: "1.5px solid",
          borderColor: isSelected ? colour : "divider",
          borderRadius: 1.5,
          bgcolor: isSelected ? `${colour}12` : isCompatible ? "background.paper" : "grey.50",
          cursor: isCompatible ? "pointer" : "default",
          opacity: isCompatible ? 1 : 0.4,
          transition: "all 120ms ease-out",
          boxShadow: isSelected ? `0 0 0 2px ${colour}30` : "none",
          outline: "none",
          font: "inherit",
          position: "relative",
          "&:hover": isCompatible ? { borderColor: colour, bgcolor: `${colour}08` } : undefined,
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
              sx={{ fontSize: 10, color: colour, position: "absolute", top: 3, right: 3 }}
            />
          </Tooltip>
        )}
      </Box>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// StoryTab sub-component
// ---------------------------------------------------------------------------

function StoryTab({
  story,
  onChange,
}: {
  story: TileStoryConfig;
  onChange: (s: TileStoryConfig) => void;
}) {
  const annotations = story.annotations ?? [];

  const update = (patch: Partial<TileStoryConfig>) => onChange({ ...story, ...patch });

  const updateAnnotation = (i: number, patch: Partial<TileAnnotation>) => {
    const next = annotations.map((a, idx) => (idx === i ? { ...a, ...patch } : a));
    update({ annotations: next });
  };

  const removeAnnotation = (i: number) => {
    update({ annotations: annotations.filter((_, idx) => idx !== i) });
  };

  const addAnnotation = (type: TileAnnotation["type"]) => {
    update({ annotations: [...annotations, { type, label: "" }] });
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      <TextField
        label="Data headline"
        size="small"
        multiline
        maxRows={3}
        value={story.headline ?? ""}
        onChange={(e) => update({ headline: e.target.value || undefined })}
        helperText='One-sentence insight, e.g. "Breast cancer accounts for 34% of referrals"'
        fullWidth
      />

      <TextField
        label="Highlight category"
        size="small"
        value={story.highlight_key ?? ""}
        onChange={(e) => update({ highlight_key: e.target.value || undefined })}
        helperText="Emphasise this category value with a contrasting colour"
        fullWidth
      />

      <Box>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
          Benchmark lines
        </Typography>
        {annotations
          .filter((a) => a.type === "threshold")
          .map((a, i) => (
            <AnnotationRow
              key={i}
              annotation={a}
              idx={annotations.indexOf(a)}
              onUpdate={updateAnnotation}
              onRemove={removeAnnotation}
              showValue
            />
          ))}
        <Button
          size="small"
          startIcon={<AddIcon />}
          onClick={() => addAnnotation("threshold")}
          sx={{ mt: 0.5, fontSize: 11 }}
        >
          Add benchmark
        </Button>
      </Box>

      <Box>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
          Callout annotations
        </Typography>
        {annotations
          .filter((a) => a.type === "callout")
          .map((a, i) => (
            <AnnotationRow
              key={i}
              annotation={a}
              idx={annotations.indexOf(a)}
              onUpdate={updateAnnotation}
              onRemove={removeAnnotation}
              showValue={false}
            />
          ))}
        <Button
          size="small"
          startIcon={<AddIcon />}
          onClick={() => addAnnotation("callout")}
          sx={{ mt: 0.5, fontSize: 11 }}
        >
          Add callout
        </Button>
      </Box>

      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={story.animate_in ?? false}
            onChange={(e) => update({ animate_in: e.target.checked })}
          />
        }
        label={
          <Typography variant="caption">Animate in (presentation mode)</Typography>
        }
        sx={{ ml: 0 }}
      />
    </Box>
  );
}

function AnnotationRow({
  annotation,
  idx,
  onUpdate,
  onRemove,
  showValue,
}: {
  annotation: TileAnnotation;
  idx: number;
  onUpdate: (i: number, patch: Partial<TileAnnotation>) => void;
  onRemove: (i: number) => void;
  showValue: boolean;
}) {
  return (
    <Box sx={{ display: "flex", gap: 0.75, mb: 0.75, alignItems: "flex-start" }}>
      <TextField
        size="small"
        placeholder="Label"
        value={annotation.label}
        onChange={(e) => onUpdate(idx, { label: e.target.value })}
        sx={{ flex: 1, fontSize: 11 }}
      />
      {showValue && (
        <TextField
          size="small"
          placeholder="Value"
          type="number"
          value={annotation.value ?? ""}
          onChange={(e) =>
            onUpdate(idx, { value: e.target.value ? Number(e.target.value) : undefined })
          }
          sx={{ width: 72 }}
        />
      )}
      {!showValue && (
        <TextField
          size="small"
          placeholder="Key"
          value={annotation.target_key ?? ""}
          onChange={(e) => onUpdate(idx, { target_key: e.target.value || undefined })}
          sx={{ width: 80 }}
        />
      )}
      <IconButton size="small" onClick={() => onRemove(idx)}>
        <DeleteOutlineIcon sx={{ fontSize: 14 }} />
      </IconButton>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Widget-only panel
// ---------------------------------------------------------------------------

function WidgetPanel({
  tile,
  update,
  onRemove,
}: {
  tile: AuditTile;
  update: (patch: Partial<AuditTile>) => void;
  onRemove?: (id: string) => void;
}) {
  const widgetEntry = WIDGET_CATALOGUE.find((w) => w.widget_id === tile.metric_id);
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="subtitle2" fontWeight={700}>Tile settings</Typography>
      <TextField
        label="Label"
        size="small"
        value={tile.label}
        onChange={(e) => update({ label: e.target.value })}
        fullWidth
      />
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
          <Typography variant="caption" color="text.secondary" display="block" sx={{ fontSize: 10 }}>
            {widgetEntry?.description ??
              "This widget renders a full NCDA section. Its appearance cannot be changed."}
          </Typography>
        </Box>
      </Box>
      <TextField
        label="Section heading (optional)"
        size="small"
        value={tile.section ?? ""}
        onChange={(e) => update({ section: e.target.value || undefined })}
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

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function TileConfigPanel({
  tile,
  compatibleTypes,
  recommendedType,
  paramSchema,
  onChange,
  onRemove,
}: TileConfigPanelProps) {
  const [tab, setTab] = useState(0);
  const compatible = compatibleTypes ?? ALL_TYPES;
  const recommended = recommendedType ?? tile.tile_type;
  const update = (patch: Partial<AuditTile>) => onChange({ ...tile, ...patch });

  if (tile.tile_type === "widget") {
    return <WidgetPanel tile={tile} update={update} onRemove={onRemove} />;
  }

  const story: TileStoryConfig = tile.story ?? {};
  const hasParams = Boolean(paramSchema && Object.keys(paramSchema).length > 0);
  const paramTabIndex = 2;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0 }}>
      <Typography variant="subtitle2" fontWeight={700} sx={{ px: 0, pb: 1 }}>
        Tile settings
      </Typography>

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v as number)}
        sx={{ mb: 1.5, minHeight: 32, "& .MuiTab-root": { minHeight: 32, fontSize: 12 } }}
      >
        <Tab label="Settings" />
        <Tab label="Story" />
        {hasParams && <Tab label="Parameters" />}
      </Tabs>

      {tab === 0 && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
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
            <Chip label={tile.metric_id} size="small" variant="outlined" sx={{ fontSize: 11, maxWidth: "100%" }} />
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
      )}

      {tab === 1 && (
        <StoryTab
          story={story}
          onChange={(s) => update({ story: s })}
        />
      )}

      {hasParams && tab === paramTabIndex && (
        <ParamsTab
          schema={paramSchema as Record<string, MetricParamSpec>}
          overrides={tile.param_overrides ?? {}}
          onChange={(next) => update({ param_overrides: next })}
        />
      )}
    </Box>
  );
}
