"use client";

/**
 * OrgGraph — interactive force-directed hierarchy of NHS organisations.
 *
 * Layout:   dagre top-down (Cancer Alliance → ICB → PCN → GP)
 * Library:  @xyflow/react (React Flow v12)
 * Colour:   matches ORG_TYPE_CONFIG palette across the portal
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonGroup from "@mui/material/ButtonGroup";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import FilterListIcon from "@mui/icons-material/FilterList";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import InputAdornment from "@mui/material/InputAdornment";
import {
  getOrgGraph,
  type OrgGraphNode,
  type OrgGraph,
} from "@/lib/api/admin";

// ------------------------------------------------------------------
// Constants
// ------------------------------------------------------------------

const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

const TYPE_STYLE: Record<
  string,
  { bg: string; border: string; text: string; label: string }
> = {
  alliance: { bg: "#ede7f6", border: "#7b1fa2", text: "#4a148c", label: "Cancer Alliance" },
  icb:      { bg: "#e3f2fd", border: "#1565c0", text: "#0d47a1", label: "ICB" },
  pcn:      { bg: "#fff8e1", border: "#f57f17", text: "#e65100", label: "PCN" },
  gp:       { bg: "#e8f5e9", border: "#2e7d32", text: "#1b5e20", label: "GP Practice" },
  organization: { bg: "#f5f5f5", border: "#757575", text: "#424242", label: "Organisation" },
};

// ------------------------------------------------------------------
// Custom node renderer
// ------------------------------------------------------------------

function OrgNode({ data }: NodeProps) {
  const d = data as OrgGraphNodeData;
  const style = TYPE_STYLE[d.type] ?? TYPE_STYLE.organization;
  const hasSyncIssue = d.ods_sync_status === "mismatch" || d.ods_sync_status === "closed";

  return (
    <Box
      onClick={d.onSelect}
      sx={{
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
        px: 1.5,
        py: 1,
        borderRadius: 1.5,
        border: `2px solid ${style.border}`,
        bgcolor: style.bg,
        cursor: "pointer",
        boxShadow: d.selected ? `0 0 0 3px ${style.border}` : "0 1px 3px rgba(0,0,0,0.12)",
        transition: "box-shadow 0.15s",
        "&:hover": { boxShadow: `0 0 0 2px ${style.border}` },
        position: "relative",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 0.5 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              fontSize: "0.65rem",
              color: style.text,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              display: "block",
            }}
          >
            {style.label}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 600,
              fontSize: "0.72rem",
              lineHeight: 1.3,
              color: "#1a1a1a",
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            {d.name}
          </Typography>
          {d.odsCode && (
            <Typography variant="caption" sx={{ color: "#666", fontFamily: "monospace", fontSize: "0.65rem" }}>
              {d.odsCode}
            </Typography>
          )}
          {d.patient_count > 0 && (
            <Typography variant="caption" sx={{ color: style.text, fontSize: "0.65rem", display: "block" }}>
              {d.patient_count.toLocaleString()} pts
            </Typography>
          )}
        </Box>
        {hasSyncIssue && (
          <Tooltip title={d.ods_sync_status === "closed" ? "ODS reports inactive" : "ODS data mismatch"}>
            <WarningAmberIcon
              sx={{ fontSize: 14, color: d.ods_sync_status === "closed" ? "error.main" : "warning.main", mt: 0.25 }}
            />
          </Tooltip>
        )}
      </Box>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </Box>
  );
}

const nodeTypes = { org: OrgNode };

interface OrgGraphNodeData extends OrgGraphNode {
  selected?: boolean;
  onSelect?: () => void;
  [key: string]: unknown;
}

// ------------------------------------------------------------------
// Dagre layout
// ------------------------------------------------------------------

function applyDagreLayout(
  nodes: Node[],
  edges: Edge[],
  direction: "TB" | "LR" = "TB"
): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 30, ranksep: 60, edgesep: 10 });

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 } };
  });
}

// ------------------------------------------------------------------
// Props
// ------------------------------------------------------------------

interface OrgGraphProps {
  onNodeClick?: (node: OrgGraphNode) => void;
}

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

const TYPE_ORDER = ["alliance", "icb", "pcn", "gp", "organization"];

export default function OrgGraph({ onNodeClick }: OrgGraphProps) {
  const [graphData, setGraphData] = useState<OrgGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [typeFilter, setTypeFilter] = useState<Set<string>>(
    new Set(["alliance", "icb", "pcn", "gp"])
  );
  const [search, setSearch] = useState("");
  const [showMismatchOnly, setShowMismatchOnly] = useState(false);
  const [direction, setDirection] = useState<"TB" | "LR">("TB");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setGraphData(await getOrgGraph());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load org graph.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Rebuild React Flow nodes/edges when data or filters change
  useEffect(() => {
    if (!graphData) return;

    const q = search.trim().toLowerCase();

    const filteredNodes = graphData.nodes.filter((n) => {
      if (!typeFilter.has(n.type)) return false;
      if (showMismatchOnly && n.ods_sync_status !== "mismatch" && n.ods_sync_status !== "closed") return false;
      if (q && !n.name.toLowerCase().includes(q) && !(n.odsCode ?? "").toLowerCase().includes(q)) return false;
      return true;
    });

    const filteredIds = new Set(filteredNodes.map((n) => n.id));

    const rfNodes: Node[] = filteredNodes.map((n) => ({
      id: n.id,
      type: "org",
      position: { x: 0, y: 0 }, // dagre will overwrite
      data: {
        ...n,
        selected: n.id === selectedId,
        onSelect: () => {
          setSelectedId(n.id);
          onNodeClick?.(n);
        },
      } as OrgGraphNodeData,
    }));

    const rfEdges: Edge[] = graphData.edges
      .filter((e) => filteredIds.has(e.source) && filteredIds.has(e.target))
      .map((e) => ({
        id: `${e.source}->${e.target}`,
        source: e.source,
        target: e.target,
        style: { stroke: "#bbb", strokeWidth: 1.5 },
        animated: false,
      }));

    const laid = applyDagreLayout(rfNodes, rfEdges, direction);
    setNodes(laid);
    setEdges(rfEdges);
  }, [graphData, typeFilter, search, showMismatchOnly, direction, selectedId, onNodeClick, setNodes, setEdges]);

  const toggleType = (t: string) => {
    setTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(t)) { next.delete(t); } else { next.add(t); }
      return next;
    });
  };

  const mismatchCount = useMemo(
    () => graphData?.nodes.filter((n) => n.ods_sync_status === "mismatch" || n.ods_sync_status === "closed").length ?? 0,
    [graphData]
  );

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 500 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Toolbar */}
      <Box
        sx={{
          display: "flex",
          gap: 1.5,
          alignItems: "center",
          flexWrap: "wrap",
          mb: 1.5,
          px: 0.5,
        }}
      >
        <TextField
          size="small"
          placeholder="Search name or ODS code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ width: 240 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />

        {/* Type filters */}
        <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
          <FilterListIcon fontSize="small" sx={{ color: "text.secondary" }} />
          {TYPE_ORDER.filter((t) => t !== "organization").map((t) => {
            const s = TYPE_STYLE[t];
            const count = graphData?.nodes.filter((n) => n.type === t).length ?? 0;
            return (
              <Chip
                key={t}
                label={`${s.label} (${count})`}
                size="small"
                onClick={() => toggleType(t)}
                variant={typeFilter.has(t) ? "filled" : "outlined"}
                sx={{
                  bgcolor: typeFilter.has(t) ? s.bg : undefined,
                  borderColor: s.border,
                  color: typeFilter.has(t) ? s.text : "text.secondary",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: "0.7rem",
                }}
              />
            );
          })}
        </Box>

        {/* Mismatch toggle */}
        {mismatchCount > 0 && (
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={showMismatchOnly}
                onChange={(e) => setShowMismatchOnly(e.target.checked)}
                color="warning"
              />
            }
            label={
              <Typography variant="caption" sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <WarningAmberIcon sx={{ fontSize: 14, color: "warning.main" }} />
                Issues only ({mismatchCount})
              </Typography>
            }
            sx={{ m: 0 }}
          />
        )}

        {/* Layout toggle */}
        <ButtonGroup size="small" variant="outlined" sx={{ ml: "auto" }}>
          <Button
            onClick={() => setDirection("TB")}
            variant={direction === "TB" ? "contained" : "outlined"}
            sx={{ fontSize: "0.7rem" }}
          >
            Top-down
          </Button>
          <Button
            onClick={() => setDirection("LR")}
            variant={direction === "LR" ? "contained" : "outlined"}
            sx={{ fontSize: "0.7rem" }}
          >
            Left-right
          </Button>
        </ButtonGroup>

        <Tooltip title="Refresh graph">
          <Button size="small" variant="outlined" onClick={load} sx={{ minWidth: 0, px: 1 }}>
            <RefreshIcon fontSize="small" />
          </Button>
        </Tooltip>
      </Box>

      {/* Summary stats */}
      <Box sx={{ display: "flex", gap: 2, mb: 1, px: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          {nodes.length} nodes · {edges.length} edges
          {selectedId && (
            <> · <strong>{(graphData?.nodes.find((n) => n.id === selectedId))?.name}</strong> selected</>
          )}
        </Typography>
      </Box>

      {/* Graph canvas */}
      <Box
        sx={{
          flex: 1,
          minHeight: 560,
          borderRadius: 2,
          border: "1px solid",
          borderColor: "divider",
          overflow: "hidden",
          bgcolor: "#fafafa",
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.05}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#e0e0e0" gap={20} />
          <Controls />
          <MiniMap
            nodeColor={(n) => {
              const t = (n.data as OrgGraphNodeData).type;
              return TYPE_STYLE[t]?.border ?? "#999";
            }}
            pannable
            zoomable
          />
        </ReactFlow>
      </Box>
    </Box>
  );
}
