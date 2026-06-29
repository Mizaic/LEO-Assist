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
  WIDGET_CATALOGUE,
  type AuditPage,
  type AuditTemplate,
  type AuditTile,
  type MetricCatalogueEntry,
  type TileType,
  type WidgetCatalogueEntry,
} from "@/lib/auditTemplateApi";
import { resolvePages, tilesForPage } from "@/lib/auditPages";
import { type ContentBlockEntry } from "@/lib/contentBlocks";
import { useOrg } from "@/context/OrgContext";
import MetricPicker from "./MetricPicker";
import CanvasGrid from "./CanvasGrid";
import TileConfigPanel from "./TileConfigPanel";
import PublishDialog from "./PublishDialog";
import PreviewPanel from "./PreviewPanel";
import AuditDraftAssistant from "./AuditDraftAssistant";
import PageTabs from "./PageTabs";
import {
  type StarterLayout as StarterLayoutDef,
  pickMetricsForSlots,
} from "./StarterLayouts";

interface TemplateEditorProps {
  initial?: AuditTemplate;
}

function newTile(
  metric: MetricCatalogueEntry,
  index: number,
  pageId: string,
  tileType?: TileType,
  at?: { x: number; y: number },
): AuditTile {
  const col = at ? at.x : (index % 3) * 4;
  const row = at ? at.y : Math.floor(index / 3) * 3;
  return {
    tile_id: `tile-${Date.now()}-${index}`,
    label: metric.title,
    tile_type: (tileType ?? metric.output_type) as AuditTile["tile_type"],
    metric_id: metric.metric_id,
    param_overrides: {},
    section: undefined,
    page_id: pageId,
    layout: { x: col, y: row, w: 4, h: 3 },
  };
}

export default function TemplateEditor({ initial }: TemplateEditorProps) {
  const router = useRouter();
  const { organizations } = useOrg();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [tiles, setTiles] = useState<AuditTile[]>(initial?.tiles ?? []);
  const [pages, setPages] = useState<AuditPage[]>(() => resolvePages(initial?.pages));
  const [activePageId, setActivePageId] = useState<string>(
    () => resolvePages(initial?.pages)[0].page_id,
  );
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

  const usedCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const t of tiles) counts.set(t.metric_id, (counts.get(t.metric_id) ?? 0) + 1);
    return counts;
  }, [tiles]);

  const isFirstPage = pages.length > 0 && pages[0].page_id === activePageId;
  const pageTiles = useMemo(
    () => tilesForPage(tiles, activePageId, isFirstPage),
    [tiles, activePageId, isFirstPage],
  );

  const selectedTile = tiles.find((t) => t.tile_id === selectedId) ?? null;

  // Replace the active page's tiles after a drag/resize, leaving other pages
  // untouched.
  const handlePageLayoutChange = useCallback(
    (updated: AuditTile[]) => {
      setTiles((prev) => {
        const updatedIds = new Set(updated.map((t) => t.tile_id));
        const others = prev.filter((t) => !updatedIds.has(t.tile_id));
        return [...others, ...updated];
      });
    },
    [],
  );

  const handleAddPage = useCallback(() => {
    const id = `page-${Date.now()}`;
    setPages((prev) => [...prev, { page_id: id, title: `Page ${prev.length + 1}` }]);
    setActivePageId(id);
  }, []);

  const handleRenamePage = useCallback((pageId: string, newTitle: string) => {
    setPages((prev) => prev.map((p) => (p.page_id === pageId ? { ...p, title: newTitle } : p)));
  }, []);

  const handleDeletePage = useCallback(
    (pageId: string) => {
      setPages((prev) => {
        if (prev.length <= 1) return prev;
        const remaining = prev.filter((p) => p.page_id !== pageId);
        const firstId = remaining[0].page_id;
        setActivePageId((cur) => (cur === pageId ? firstId : cur));
        // Drop tiles that lived on the deleted page.
        const deletedIsFirst = prev[0].page_id === pageId;
        setTiles((ts) =>
          ts.filter((t) => {
            const tp = t.page_id ?? prev[0].page_id;
            if (deletedIsFirst && (t.page_id == null || tp === pageId)) return false;
            return tp !== pageId;
          }),
        );
        return remaining;
      });
    },
    [],
  );

  const handleAddMetric = useCallback(
    (metric: MetricCatalogueEntry, tileType: TileType) => {
      setTiles((prev) => {
        const idx = tilesForPage(prev, activePageId, isFirstPage).length;
        return [...prev, newTile(metric, idx, activePageId, tileType)];
      });
    },
    [activePageId, isFirstPage],
  );

  const handleAddWidget = useCallback(
    (widget: WidgetCatalogueEntry) => {
      setTiles((prev) => {
        const index = tilesForPage(prev, activePageId, isFirstPage).length;
        const col = (index % 2) * 6;
        const entry: AuditTile = {
          tile_id: `tile-widget-${Date.now()}-${index}`,
          label: widget.title,
          tile_type: "widget",
          metric_id: widget.widget_id,
          param_overrides: {},
          section: undefined,
          page_id: activePageId,
          layout: { x: col, y: Math.floor(index / 2) * 5, w: 12, h: 5 },
        };
        return [...prev, entry];
      });
    },
    [activePageId, isFirstPage],
  );

  const handleAddContent = useCallback(
    (block: ContentBlockEntry) => {
      setTiles((prev) => {
        const index = tilesForPage(prev, activePageId, isFirstPage).length;
        const maxY = prev.reduce((m, t) => Math.max(m, (t.layout?.y ?? 0) + (t.layout?.h ?? 1)), 0);
        const entry: AuditTile = {
          tile_id: `tile-content-${Date.now()}-${index}`,
          label: block.label,
          tile_type: "text",
          metric_id: block.block_id,
          param_overrides: { ...block.defaultParams },
          section: undefined,
          page_id: activePageId,
          layout: { x: 0, y: maxY, ...block.defaultLayout },
        };
        return [...prev, entry];
      });
    },
    [activePageId, isFirstPage],
  );

  const handleDropMetric = useCallback(
    (metricId: string, tileType: TileType, at?: { x: number; y: number }) => {
      const metric = catalogueById.get(metricId);
      if (metric)
        setTiles((prev) => {
          const idx = tilesForPage(prev, activePageId, isFirstPage).length;
          return [...prev, newTile(metric, idx, activePageId, tileType, at)];
        });
    },
    [catalogueById, activePageId, isFirstPage],
  );

  const handleDropWidget = useCallback(
    (widgetId: string, at?: { x: number; y: number }) => {
      const widget = WIDGET_CATALOGUE.find((w) => w.widget_id === widgetId);
      if (!widget) return;
      setTiles((prev) => {
        const index = tilesForPage(prev, activePageId, isFirstPage).length;
        const col = at ? at.x : (index % 2) * 6;
        const row = at ? at.y : Math.floor(index / 2) * 5;
        const entry: AuditTile = {
          tile_id: `tile-widget-${Date.now()}-${index}`,
          label: widget.title,
          tile_type: "widget",
          metric_id: widget.widget_id,
          param_overrides: {},
          section: undefined,
          page_id: activePageId,
          layout: { x: col, y: row, w: 12, h: 5 },
        };
        return [...prev, entry];
      });
    },
    [activePageId, isFirstPage],
  );

  const handleAddStarter = useCallback(
    (starter: StarterLayoutDef, cat: MetricCatalogueEntry[]) => {
      const assignments = pickMetricsForSlots(starter.slots, cat);
      setTiles((prev) => {
        const newTiles = assignments.map(({ slot, metric }, i) => ({
          tile_id: `tile-starter-${Date.now()}-${i}`,
          label: metric.title,
          tile_type: slot.tileType as AuditTile["tile_type"],
          metric_id: metric.metric_id,
          param_overrides: {},
          section: undefined,
          page_id: activePageId,
          layout: { ...slot.layout },
        }));
        return [...prev, ...newTiles];
      });
    },
    [activePageId],
  );

  const handleRemoveTile = useCallback((id: string) => {
    setTiles((prev) => prev.filter((t) => t.tile_id !== id));
    setSelectedId((s) => (s === id ? null : s));
  }, []);

  const handleTileChange = useCallback((updated: AuditTile) => {
    setTiles((prev) => prev.map((t) => (t.tile_id === updated.tile_id ? updated : t)));
  }, []);

  const handleTypeChange = useCallback((tileId: string, newType: TileType) => {
    setTiles((prev) =>
      prev.map((t) => (t.tile_id === tileId ? { ...t, tile_type: newType } : t))
    );
  }, []);

  const handleAddTileFromAI = useCallback(
    (
      metric_id: string,
      label: string,
      tile_type: string,
      _section?: string,
      storyHeadline?: string,
      highlightKey?: string,
    ) => {
      setTiles((prev) => {
        const index = tilesForPage(prev, activePageId, isFirstPage).length;
        const col = (index % 3) * 4;
        const story =
          storyHeadline || highlightKey
            ? { headline: storyHeadline, highlight_key: highlightKey }
            : undefined;
        const newTileEntry: AuditTile = {
          tile_id: `tile-ai-${Date.now()}-${index}`,
          label,
          tile_type: tile_type as AuditTile["tile_type"],
          metric_id,
          param_overrides: {},
          page_id: activePageId,
          layout: { x: col, y: Math.floor(index / 3) * 3, w: 4, h: 3 },
          story,
        };
        return [...prev, newTileEntry];
      });
    },
    [activePageId, isFirstPage],
  );

  const handleSave = async () => {
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      // Only persist explicit pages when the report is genuinely multi-page;
      // a single default page stays implicit for back-compatibility.
      const pagesPayload = pages.length > 1 ? pages : [];
      if (savedId) {
        await updateTemplate(savedId, { title: title.trim(), tiles, pages: pagesPayload });
      } else {
        const created = await createTemplate({ title: title.trim(), tiles, pages: pagesPayload });
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

      {/* Main layout: preview OR picker | canvas (floating config) */}
      <Box sx={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {previewMode ? (
          <PreviewPanel
            tiles={tiles}
            title={title}
            savedId={savedId}
            organizations={organizations}
            previewOrgId={previewOrgId}
            onOrgChange={setPreviewOrgId}
            catalogue={catalogue}
            pages={pages}
          />
        ) : (
          <>
            {/* Metric picker sidebar */}
            <Box
              sx={{
                width: 240,
                flexShrink: 0,
                borderRight: "1px solid",
                borderColor: "divider",
                p: 1.5,
                overflowY: "auto",
                bgcolor: "background.paper",
              }}
            >
              <MetricPicker
                onAdd={handleAddMetric}
                onAddWidget={handleAddWidget}
                onAddStarter={handleAddStarter}
                onAddContent={handleAddContent}
                usedCounts={usedCounts}
                catalogue={catalogue}
                loading={catalogueLoading}
                error={catalogueError}
              />
            </Box>

            {/* Canvas area with page tabs + floating config */}
            <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
              <PageTabs
                pages={pages}
                activePageId={activePageId}
                onSelect={setActivePageId}
                onAdd={handleAddPage}
                onRename={handleRenamePage}
                onDelete={handleDeletePage}
              />
              <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
                <CanvasGrid
                  tiles={pageTiles}
                  catalogue={catalogue}
                  selectedId={selectedId}
                  onSelect={(id) => setSelectedId(id)}
                  onRemove={handleRemoveTile}
                  onLayoutChange={handlePageLayoutChange}
                  onTileParamChange={handleTileChange}
                  onOpenAssistant={() => setAssistantOpen(true)}
                  onDropMetric={handleDropMetric}
                  onDropWidget={handleDropWidget}
                />
              </Box>

              {/* Floating config panel -- slides in over the canvas */}
              <Box
                sx={{
                  position: "absolute",
                  right: 0,
                  top: 0,
                  bottom: 0,
                  width: 260,
                  bgcolor: "background.paper",
                  borderLeft: "1px solid",
                  borderColor: "divider",
                  overflowY: "auto",
                  boxShadow: "-4px 0 16px rgba(0,0,0,0.08)",
                  transform: selectedTile ? "translateX(0)" : "translateX(100%)",
                  transition: "transform 200ms ease-out",
                  zIndex: 10,
                  p: 1.5,
                }}
              >
                {selectedTile && (
                  <TileConfigPanel
                    tile={selectedTile}
                    compatibleTypes={
                      catalogueById.get(selectedTile.metric_id)?.compatible_tile_types
                    }
                    recommendedType={
                      catalogueById.get(selectedTile.metric_id)?.output_type as TileType | undefined
                    }
                    paramSchema={catalogueById.get(selectedTile.metric_id)?.param_schema}
                    onChange={handleTileChange}
                    onRemove={handleRemoveTile}
                  />
                )}
              </Box>
            </Box>
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
