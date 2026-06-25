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
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import {
  createTemplate,
  updateTemplate,
  fetchMetricCatalogue,
  type AuditTemplate,
  type AuditTile,
  type MetricCatalogueEntry,
  type TileType,
  type WidgetCatalogueEntry,
} from "@/lib/auditTemplateApi";
import { useOrg } from "@/context/OrgContext";
import MetricPicker from "./MetricPicker";
import TileGrid from "./TileGrid";
import TileConfigPanel from "./TileConfigPanel";
import PublishDialog from "./PublishDialog";
import PreviewPanel from "./PreviewPanel";
import AuditDraftAssistant from "./AuditDraftAssistant";

interface TemplateEditorProps {
  initial?: AuditTemplate;
}

function newTile(metric: MetricCatalogueEntry, index: number, tileType?: TileType): AuditTile {
  const col = (index % 3) * 4;
  return {
    tile_id: `tile-${Date.now()}-${index}`,
    label: metric.title,
    tile_type: (tileType ?? metric.output_type) as AuditTile["tile_type"],
    metric_id: metric.metric_id,
    param_overrides: {},
    section: undefined,
    layout: { x: col, y: Math.floor(index / 3) * 3, w: 4, h: 3 },
  };
}

export default function TemplateEditor({ initial }: TemplateEditorProps) {
  const router = useRouter();
  const { organizations } = useOrg();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [tiles, setTiles] = useState<AuditTile[]>(initial?.tiles ?? []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | undefined>(initial?.template_id);
  const [publishOpen, setPublishOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [previewOrgId, setPreviewOrgId] = useState<string>("");
  const [assistantOpen, setAssistantOpen] = useState(false);

  // Catalogue is loaded once here and shared with MetricPicker + TileConfigPanel
  // so we avoid two separate fetches and can derive tile compatibility.
  const [catalogue, setCatalogue] = useState<MetricCatalogueEntry[]>([]);
  const [catalogueLoading, setCatalogueLoading] = useState(true);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);

  useEffect(() => {
    fetchMetricCatalogue()
      .then(setCatalogue)
      .catch((e) => setCatalogueError(e instanceof Error ? e.message : "Failed to load metrics"))
      .finally(() => setCatalogueLoading(false));
  }, []);

  const catalogueById = useMemo(
    () => new Map(catalogue.map((m) => [m.metric_id, m])),
    [catalogue],
  );

  // Default to first available org when orgs load in.
  useEffect(() => {
    if (!previewOrgId && organizations.length > 0) {
      setPreviewOrgId(organizations[0].id);
    }
  }, [organizations, previewOrgId]);

  const usedMetricIds = useMemo(() => new Set(tiles.map((t) => t.metric_id)), [tiles]);

  const selectedTile = tiles.find((t) => t.tile_id === selectedId) ?? null;

  const handleAddMetric = useCallback(
    (metric: MetricCatalogueEntry, tileType: TileType) => {
      setTiles((prev) => [...prev, newTile(metric, prev.length, tileType)]);
    },
    []
  );

  const handleAddWidget = useCallback((widget: WidgetCatalogueEntry) => {
    setTiles((prev) => {
      const index = prev.length;
      const col = (index % 2) * 6;
      const entry: AuditTile = {
        tile_id: `tile-widget-${Date.now()}-${index}`,
        label: widget.title,
        tile_type: "widget",
        metric_id: widget.widget_id,
        param_overrides: {},
        section: undefined,
        layout: { x: col, y: Math.floor(index / 2) * 5, w: 12, h: 5 },
      };
      return [...prev, entry];
    });
  }, []);

  const handleRemoveTile = useCallback((id: string) => {
    setTiles((prev) => prev.filter((t) => t.tile_id !== id));
    setSelectedId((s) => (s === id ? null : s));
  }, []);

  const handleTileChange = useCallback((updated: AuditTile) => {
    setTiles((prev) => prev.map((t) => (t.tile_id === updated.tile_id ? updated : t)));
  }, []);

  const handleAddTileFromAI = useCallback(
    (
      metric_id: string,
      label: string,
      tile_type: string,
      _section?: string,
    ) => {
      setTiles((prev) => {
        const index = prev.length;
        const col = (index % 3) * 4;
        const newTileEntry: AuditTile = {
          tile_id: `tile-ai-${Date.now()}-${index}`,
          label,
          tile_type: tile_type as AuditTile["tile_type"],
          metric_id,
          param_overrides: {},
          layout: { x: col, y: Math.floor(index / 3) * 3, w: 4, h: 3 },
        };
        return [...prev, newTileEntry];
      });
    },
    [],
  );

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
          variant={previewMode ? "outlined" : "text"}
          size="small"
          color={previewMode ? "primary" : "inherit"}
          startIcon={previewMode ? <EditOutlinedIcon /> : <VisibilityOutlinedIcon />}
          onClick={() => setPreviewMode((m) => !m)}
        >
          {previewMode ? "Edit" : "Preview"}
        </Button>
        <Divider orientation="vertical" flexItem />
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
        <Divider orientation="vertical" flexItem />
        <Button
          variant={assistantOpen ? "outlined" : "text"}
          size="small"
          color={assistantOpen ? "primary" : "inherit"}
          startIcon={<AutoAwesomeOutlinedIcon />}
          onClick={() => setAssistantOpen((o) => !o)}
        >
          AI
        </Button>
      </Box>

      {/* Main layout: preview OR picker | grid | config */}
      <Box sx={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {previewMode ? (
          <PreviewPanel
            tiles={tiles}
            title={title}
            savedId={savedId}
            organizations={organizations}
            previewOrgId={previewOrgId}
            onOrgChange={setPreviewOrgId}
          />
        ) : (
          <>
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
              <MetricPicker
                onAdd={handleAddMetric}
                onAddWidget={handleAddWidget}
                usedMetricIds={usedMetricIds}
                catalogue={catalogue}
                loading={catalogueLoading}
                error={catalogueError}
              />
            </Box>

            {/* Tile grid */}
            <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
              <TileGrid
                tiles={tiles}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onRemove={handleRemoveTile}
                onLayoutChange={setTiles}
                onOpenAssistant={() => setAssistantOpen(true)}
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
                <TileConfigPanel
                  tile={selectedTile}
                  compatibleTypes={
                    catalogueById.get(selectedTile.metric_id)?.compatible_tile_types
                  }
                  recommendedType={
                    catalogueById.get(selectedTile.metric_id)?.output_type as TileType | undefined
                  }
                  onChange={handleTileChange}
                  onRemove={handleRemoveTile}
                />
              </Box>
            )}
          </>
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

      <AuditDraftAssistant
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        tiles={tiles.map((t) => ({ metric_id: t.metric_id, label: t.label }))}
        onAddTile={handleAddTileFromAI}
      />
    </Box>
  );
}
