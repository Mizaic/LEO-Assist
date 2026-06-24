"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 * Full-page template editor: metric picker + tile grid + config panel.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Divider from "@mui/material/Divider";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import PublishOutlinedIcon from "@mui/icons-material/PublishOutlined";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import {
  createTemplate,
  updateTemplate,
  type AuditTemplate,
  type AuditTile,
  type MetricCatalogueEntry,
} from "@/lib/auditTemplateApi";
import MetricPicker from "./MetricPicker";
import TileGrid from "./TileGrid";
import TileConfigPanel from "./TileConfigPanel";
import PublishDialog from "./PublishDialog";

interface TemplateEditorProps {
  initial?: AuditTemplate;
}

function newTile(metric: MetricCatalogueEntry, index: number): AuditTile {
  const col = (index % 3) * 4;
  return {
    tile_id: `tile-${Date.now()}-${index}`,
    label: metric.title,
    tile_type: metric.output_type as AuditTile["tile_type"],
    metric_id: metric.metric_id,
    param_overrides: {},
    layout: { x: col, y: Math.floor(index / 3) * 3, w: 4, h: 3 },
  };
}

export default function TemplateEditor({ initial }: TemplateEditorProps) {
  const router = useRouter();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [tiles, setTiles] = useState<AuditTile[]>(initial?.tiles ?? []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | undefined>(initial?.template_id);
  const [publishOpen, setPublishOpen] = useState(false);

  const usedMetricIds = useMemo(() => new Set(tiles.map((t) => t.metric_id)), [tiles]);

  const selectedTile = tiles.find((t) => t.tile_id === selectedId) ?? null;

  const handleAddMetric = useCallback(
    (metric: MetricCatalogueEntry) => {
      setTiles((prev) => [...prev, newTile(metric, prev.length)]);
    },
    []
  );

  const handleRemoveTile = useCallback((id: string) => {
    setTiles((prev) => prev.filter((t) => t.tile_id !== id));
    setSelectedId((s) => (s === id ? null : s));
  }, []);

  const handleTileChange = useCallback((updated: AuditTile) => {
    setTiles((prev) => prev.map((t) => (t.tile_id === updated.tile_id ? updated : t)));
  }, []);

  const handleSave = async () => {
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      if (savedId) {
        await updateTemplate(savedId, { title: title.trim(), tiles });
      } else {
        const created = await createTemplate({ title: title.trim(), tiles });
        setSavedId(created.template_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", gap: 0 }}>
      {/* Toolbar */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          px: 2,
          py: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
        }}
      >
        <Button
          size="small"
          startIcon={<ArrowBackIcon />}
          onClick={() => router.push("/admin/audit-templates")}
        >
          Templates
        </Button>
        <Divider orientation="vertical" flexItem />
        <TextField
          size="small"
          placeholder="Template title..."
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          sx={{ minWidth: 260 }}
        />
        <Box sx={{ flex: 1 }} />
        {error && (
          <Alert severity="error" sx={{ py: 0, fontSize: 12 }}>
            {error}
          </Alert>
        )}
        <Button
          variant="outlined"
          size="small"
          startIcon={saving ? <CircularProgress size={14} /> : <SaveOutlinedIcon />}
          onClick={handleSave}
          disabled={!title.trim() || saving}
        >
          Save
        </Button>
        <Button
          variant="contained"
          size="small"
          startIcon={<PublishOutlinedIcon />}
          disabled={!savedId}
          onClick={() => setPublishOpen(true)}
        >
          Publish
        </Button>
      </Box>

      {/* Main layout: picker | grid | config */}
      <Box sx={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Metric picker */}
        <Box
          sx={{
            width: 260,
            flexShrink: 0,
            borderRight: "1px solid",
            borderColor: "divider",
            p: 1.5,
            overflowY: "auto",
          }}
        >
          <MetricPicker onAdd={handleAddMetric} usedMetricIds={usedMetricIds} />
        </Box>

        {/* Tile grid */}
        <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
          <TileGrid
            tiles={tiles}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onRemove={handleRemoveTile}
            onLayoutChange={setTiles}
          />
        </Box>

        {/* Tile config */}
        {selectedTile && (
          <Box
            sx={{
              width: 240,
              flexShrink: 0,
              borderLeft: "1px solid",
              borderColor: "divider",
              p: 1.5,
              overflowY: "auto",
            }}
          >
            <TileConfigPanel tile={selectedTile} onChange={handleTileChange} />
          </Box>
        )}
      </Box>

      {savedId && (
        <PublishDialog
          templateId={savedId}
          templateTitle={title}
          open={publishOpen}
          onClose={() => setPublishOpen(false)}
          onPublished={() => router.push("/admin/audit-templates")}
        />
      )}
    </Box>
  );
}
