/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-D5B9FE5F
 *   DI: DI-6E1B71A4
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")
 *
 * Visualization approach inspired by Dr Ben Noble's Cancer Maps (gatewayc.org.uk).
 */
"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { forceCollide, forceRadial } from "d3-force";
import {
  sankey as d3sankey,
  sankeyLinkHorizontal,
  type SankeyGraph,
  type SankeyLink,
  type SankeyNode,
} from "d3-sankey";

import {
  fetchAuditSymptomsDrilldown,
  type AuditSymptomBreakdownSlice,
  type AuditSymptomsDrilldown,
} from "@/lib/analyticsApi";

// ── Dynamic import: react-force-graph uses browser APIs ───────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D: any = dynamic(
  () => import("react-force-graph-2d"),
  {
    ssr: false,
    loading: () => (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", flex: 1 }}>
        <CircularProgress aria-label="Loading" role="status" sx={{ color: "#1E40AF" }} />
      </Box>
    ),
  },
);

// ── Types ─────────────────────────────────────────────────────────────────────

type ViewMode = "referral" | "diagnosis" | "compare";
type OverlayKey = "age" | "gender";
type LayoutMode = "sankey" | "flow" | "network";

interface GraphNode {
  id: string;
  label: string;
  group: "symptom" | "cancer" | "age" | "gender";
  value: number;
  metric: number;
}

interface GraphLink {
  source: string;
  target: string;
  type: "referral" | "diagnosis" | "age" | "gender";
  value: number;
  metric: number;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface CancerOption {
  id: string;
  label: string;
  referralN: number;
  diagnosisN: number;
  topSymptom: string;
  topSymptomN: number;
  matchPct: number | null;
}

interface DemographicBucket {
  label: string;
  n: number;
  pct: number;
}

interface SymptomDemographics {
  age: DemographicBucket[];
  gender: DemographicBucket[];
}

type SymptomDemographicMap = Map<string, SymptomDemographics>;

// ── Colour palette ────────────────────────────────────────────────────────────

const LINK_COLOR: Record<string, string> = {
  referral: "#B45309",
  diagnosis: "#047857",
  age: "#7C3AED",
  gender: "#0E7490",
};

const TARGET_GLOW: Record<string, string> = {
  cancer: "#1E40AF",
  age: "#7C3AED",
  gender: "#0E7490",
};

function symptomGlow(metric: number): string {
  if (metric >= 75) return "#047857";
  if (metric >= 50) return "#1D4ED8";
  if (metric >= 25) return "#B45309";
  return "#64748B";
}

// ── Data builder ──────────────────────────────────────────────────────────────

function buildGraph(
  data: AuditSymptomsDrilldown,
  view: ViewMode,
  overlays: Set<OverlayKey>,
  minN: number,
): GraphData {
  const nodeMap = new Map<string, GraphNode>();
  const links: GraphLink[] = [];

  const upsert = (n: GraphNode) => {
    const ex = nodeMap.get(n.id);
    if (!ex) nodeMap.set(n.id, { ...n });
    else {
      if (n.value > ex.value) ex.value = n.value;
      if (n.metric > ex.metric) ex.metric = n.metric;
    }
  };

  const addSlices = (
    slices: AuditSymptomBreakdownSlice[],
    type: GraphLink["type"],
    targetGroup: GraphNode["group"],
  ) => {
    for (const slice of slices) {
      const tid = `${targetGroup}:${slice.slice_key}`;
      upsert({ id: tid, label: slice.slice_label, group: targetGroup, value: slice.cohort_n, metric: 0 });
      for (const row of slice.rows) {
        if (row.n < minN) continue;
        const sid = `symptom:${row.symptom}`;
        upsert({ id: sid, label: row.symptom, group: "symptom", value: row.n, metric: row.pct });
        links.push({ source: sid, target: tid, type, value: row.n, metric: row.pct });
        // propagate metric to target
        const t = nodeMap.get(tid);
        if (t && row.pct > t.metric) t.metric = row.pct;
      }
    }
  };

  if (view === "referral" || view === "compare")
    addSlices(data.by_suspected_cancer_type, "referral", "cancer");
  if (view === "diagnosis" || view === "compare")
    addSlices(data.by_diagnosed_cancer_type, "diagnosis", "cancer");
  if (overlays.has("age"))
    addSlices(data.by_age_band, "age", "age");
  if (overlays.has("gender"))
    addSlices(data.by_gender, "gender", "gender");

  return { nodes: [...nodeMap.values()], links };
}

function topSymptom(slice?: AuditSymptomBreakdownSlice): { label: string; n: number } {
  if (!slice) return { label: "No coded symptoms yet", n: 0 };
  const top = [...slice.rows].sort((a, b) => b.n - a.n)[0];
  return top && top.n > 0
    ? { label: top.symptom, n: top.n }
    : { label: "No coded symptoms yet", n: 0 };
}

function buildCancerOptions(data: AuditSymptomsDrilldown): CancerOption[] {
  const byId = new Map<string, CancerOption>();
  for (const slice of data.by_suspected_cancer_type) {
    const id = `cancer:${slice.slice_key}`;
    const top = topSymptom(slice);
    byId.set(id, {
      id,
      label: slice.slice_label,
      referralN: slice.cohort_n,
      diagnosisN: 0,
      topSymptom: top.label,
      topSymptomN: top.n,
      matchPct: null,
    });
  }

  for (const slice of data.by_diagnosed_cancer_type) {
    const id = `cancer:${slice.slice_key}`;
    const top = topSymptom(slice);
    const existing = byId.get(id);
    if (existing) {
      existing.diagnosisN = slice.cohort_n;
      if (existing.topSymptomN === 0 || top.n > existing.topSymptomN) {
        existing.topSymptom = top.label;
        existing.topSymptomN = top.n;
      }
    } else {
      byId.set(id, {
        id,
        label: slice.slice_label,
        referralN: 0,
        diagnosisN: slice.cohort_n,
        topSymptom: top.label,
        topSymptomN: top.n,
        matchPct: null,
      });
    }
  }

  return [...byId.values()]
    .map((option) => ({
      ...option,
      matchPct:
        option.referralN > 0
          ? Math.round((option.diagnosisN / option.referralN) * 100)
          : null,
    }))
    .sort((a, b) => {
      const totalA = Math.max(a.referralN, a.diagnosisN);
      const totalB = Math.max(b.referralN, b.diagnosisN);
      if (totalB !== totalA) return totalB - totalA;
      return a.label.localeCompare(b.label);
    });
}

function buildSymptomDemographics(
  data: AuditSymptomsDrilldown,
): SymptomDemographicMap {
  const map: SymptomDemographicMap = new Map();

  const add = (
    kind: keyof SymptomDemographics,
    slices: AuditSymptomBreakdownSlice[],
  ) => {
    for (const slice of slices) {
      for (const row of slice.rows) {
        if (row.n <= 0) continue;
        const entry = map.get(row.symptom) ?? { age: [], gender: [] };
        entry[kind].push({
          label: slice.slice_label,
          n: row.n,
          pct: row.pct,
        });
        map.set(row.symptom, entry);
      }
    }
  };

  add("age", data.by_age_band);
  add("gender", data.by_gender);

  for (const entry of map.values()) {
    entry.age.sort((a, b) => b.n - a.n || b.pct - a.pct);
    entry.gender.sort((a, b) => b.n - a.n || b.pct - a.pct);
    entry.age = entry.age.slice(0, 3);
    entry.gender = entry.gender.slice(0, 3);
  }

  return map;
}

function filterGraphByCancerTargets(
  graph: GraphData,
  selectedCancerIds: Set<string>,
): GraphData {
  if (selectedCancerIds.size === 0) return graph;

  const selectedSymptomIds = new Set<string>();
  const cancerLinks = graph.links.filter((link) => {
    const targetId =
      typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
    const sourceId =
      typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
    const keep = selectedCancerIds.has(targetId);
    if (keep) selectedSymptomIds.add(sourceId);
    return keep;
  });

  const links = cancerLinks;
  const usedNodeIds = new Set<string>();
  for (const link of links) {
    usedNodeIds.add(
      typeof link.source === "string" ? link.source : (link.source as GraphNode).id,
    );
    usedNodeIds.add(
      typeof link.target === "string" ? link.target : (link.target as GraphNode).id,
    );
  }

  return {
    nodes: graph.nodes.filter((node) => usedNodeIds.has(node.id)),
    links,
  };
}

// ── Canvas rendering helpers ───────────────────────────────────────────────────

function drawPill(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  w: number,
  h: number,
) {
  const r = h / 2;
  ctx.beginPath();
  ctx.arc(cx + w / 2 - r, cy, r, -Math.PI / 2, Math.PI / 2);
  ctx.arc(cx - w / 2 + r, cy, r, Math.PI / 2, -Math.PI / 2);
  ctx.closePath();
}

// ── Legend ────────────────────────────────────────────────────────────────────

function Legend({ view }: { view: ViewMode }) {
  const entries: { c: string; label: string }[] = [];
  if (view === "referral" || view === "compare")
    entries.push({ c: LINK_COLOR.referral, label: "Referral edge" });
  if (view === "diagnosis" || view === "compare")
    entries.push({ c: LINK_COLOR.diagnosis, label: "Diagnosis edge" });
  entries.push(
    { c: "#047857", label: "Prevalence 75%+" },
    { c: "#1D4ED8", label: "50-74%" },
    { c: "#B45309", label: "25-49%" },
  );
  return (
    <Stack direction="row" gap={2} flexWrap="wrap" alignItems="center">
      {entries.map(({ c, label }) => (
        <Stack key={label} direction="row" alignItems="center" gap={0.5}>
          <Box sx={{ width: 16, height: 2.5, bgcolor: c, borderRadius: 1 }} />
          <Typography variant="caption" sx={{ color: "#475569", fontSize: "0.72rem" }}>
            {label}
          </Typography>
        </Stack>
      ))}
      <Typography variant="caption" sx={{ color: "#6B7280", fontSize: "0.72rem" }}>
        Ribbon width = patient count. Colour shows referral or diagnosis view.
        {view === "compare" && " Compare: amber = referral, green = diagnosis"}
      </Typography>
    </Stack>
  );
}

// ── Sankey view ───────────────────────────────────────────────────────────────

type SkNodeData = GraphNode & { panel?: "referral" | "diagnosis" };
type SkLinkData = GraphLink;

type SkNode = SankeyNode<SkNodeData, SkLinkData>;
type SkLink = SankeyLink<SkNodeData, SkLinkData>;

interface SankeyPanelProps {
  data: GraphData;
  edgeType: "referral" | "diagnosis";
  width: number;
  height: number;
  hovered: GraphNode | null;
  onHover: (n: GraphNode | null) => void;
  demographics: SymptomDemographicMap;
}

/**
 * One Sankey panel: symptoms (left) → targets (right) for a single edge type.
 * In Compare mode we render two of these stacked.
 */
function SankeyPanel({
  data,
  edgeType,
  width,
  height,
  hovered,
  onHover,
  demographics,
}: SankeyPanelProps) {
  const [hoveredLink, setHoveredLink] = useState<{
    x: number;
    y: number;
    source: string;
    target: string;
    value: number;
    metric: number;
    demographics?: SymptomDemographics;
  } | null>(null);

  const svgWidth = Math.max(width, 640);
  const isCompact = svgWidth < 900;
  const labelGutter = Math.max(150, Math.min(isCompact ? 210 : 300, svgWidth * 0.24));
  const targetGutter = Math.max(120, Math.min(isCompact ? 180 : 250, svgWidth * 0.18));
  const chartTop = 36;
  const chartBottom = 34;

  const layout = useMemo(() => {
    const links = data.links.filter((l) => l.type === edgeType);
    if (links.length === 0) return null;

    // Only include nodes that participate in links of this type
    const usedIds = new Set<string>();
    for (const l of links) {
      const sId = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const tId = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      usedIds.add(sId);
      usedIds.add(tId);
    }

    const nodesIn: SkNodeData[] = data.nodes
      .filter((n) => usedIds.has(n.id))
      .map((n) => ({ ...n }));

    const linksIn: SkLinkData[] = links.map((l) => ({
      ...l,
      source: typeof l.source === "string" ? l.source : (l.source as GraphNode).id,
      target: typeof l.target === "string" ? l.target : (l.target as GraphNode).id,
    }));

    if (nodesIn.length === 0) return null;

    const sk = d3sankey<SkNodeData, SkLinkData>()
      .nodeId((n) => n.id)
      .nodeWidth(12)
      .nodePadding(isCompact ? 8 : 12)
      .nodeAlign((n) => (n.group === "symptom" ? 0 : 1))
      .extent([
        [labelGutter, chartTop],
        [svgWidth - targetGutter, height - chartBottom],
      ]);

    return sk({ nodes: nodesIn, links: linksIn } as SankeyGraph<SkNodeData, SkLinkData>);
  }, [data, edgeType, isCompact, labelGutter, targetGutter, svgWidth, height]);

  if (!layout) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height,
          color: "#6B7280",
          fontSize: "0.85rem",
          bgcolor: "#FFFFFF",
          border: "1px solid #E2E8F0",
          borderRadius: "12px",
        }}
      >
        No {edgeType} edges to display.
      </Box>
    );
  }

  const linkPath = sankeyLinkHorizontal<SkNodeData, SkLinkData>();
  const edgeCol = LINK_COLOR[edgeType];
  const maxNodeValue = Math.max(1, ...layout.nodes.map((n) => n.value ?? 0));

  const truncate = (label: string, maxChars: number) =>
    label.length > maxChars ? `${label.slice(0, maxChars - 1)}...` : label;

  const isLitNode = (n: SkNode) => !hovered || hovered.id === n.id || (
    layout.links.some((l) => {
      const sId = (l.source as SkNode).id;
      const tId = (l.target as SkNode).id;
      return (sId === hovered.id && tId === n.id) || (tId === hovered.id && sId === n.id);
    })
  );
  const isLitLink = (l: SkLink) => {
    if (!hovered) return true;
    const sId = (l.source as SkNode).id;
    const tId = (l.target as SkNode).id;
    return sId === hovered.id || tId === hovered.id;
  };

  return (
    <Box sx={{ position: "relative", width: svgWidth, height }}>
      <svg
        width={svgWidth}
        height={height}
        style={{ display: "block", background: "#FFFFFF" }}
        role="img"
        aria-label={`${edgeType} symptom flow sankey`}
      >
      <defs>
        <filter id={`glow-${edgeType}`}>
          <feGaussianBlur stdDeviation="2" />
        </filter>
      </defs>

      {/* Ribbons */}
      <g fill="none">
        {layout.links.map((link, i) => {
          const lit = isLitLink(link);
          const path = linkPath(link);
          if (!path) return null;
          return (
            <path
              key={`l-${i}`}
              d={path}
              stroke={edgeCol}
              strokeOpacity={lit ? 0.32 : 0.04}
              strokeWidth={Math.max(1, link.width ?? 0)}
              style={{ transition: "stroke-opacity 0.15s", mixBlendMode: "multiply" }}
              aria-label={`${(link.source as SkNode).label} to ${(link.target as SkNode).label}: ${link.value} patient${link.value !== 1 ? "s" : ""}`}
              onMouseMove={(event) => {
                const source = link.source as SkNode;
                const target = link.target as SkNode;
                setHoveredLink({
                  x: event.clientX,
                  y: event.clientY,
                  source: source.label,
                  target: target.label,
                  value: link.value ?? 0,
                  metric: (link as GraphLink).metric,
                  demographics: demographics.get(source.label),
                });
              }}
              onMouseLeave={() => setHoveredLink(null)}
            />
          );
        })}
      </g>

      {/* Nodes */}
      <g>
        {layout.nodes.map((node) => {
          const lit = isLitNode(node);
          const x0 = node.x0 ?? 0;
          const x1 = node.x1 ?? 0;
          const y0 = node.y0 ?? 0;
          const y1 = node.y1 ?? 0;
          const nh = Math.max(2, y1 - y0);
          const isLeft = node.group === "symptom";
          const labelPad = isCompact ? 8 : 12;
          const labelX = isLeft ? x0 - labelPad : x1 + labelPad;
          const mainY = Math.max(18, Math.min(height - 30, (y0 + y1) / 2 - 5));
          const metaY = mainY + 14;
          const valueBarWidth = isLeft
            ? Math.max(14, Math.min(isCompact ? 42 : 60, ((node.value ?? 0) / maxNodeValue) * 60))
            : 0;
          const fill =
            node.group === "symptom"
              ? symptomGlow(node.metric)
              : TARGET_GLOW[node.group] ?? "#9ca3af";
          return (
            <g
              key={node.id}
              opacity={lit ? 1 : 0.22}
              onMouseEnter={() => onHover(node)}
              onMouseLeave={() => onHover(null)}
              aria-label={`${node.label}: ${node.value} patient${(node.value ?? 0) !== 1 ? "s" : ""}`}
              style={{ cursor: "pointer", transition: "opacity 0.15s" }}
            >
              <rect
                x={x0}
                y={y0}
                width={x1 - x0}
                height={nh}
                fill={fill}
                rx={2}
                style={{ filter: `drop-shadow(0 1px 2px ${fill}44)` }}
              />
              {isLeft ? (
                <rect
                  x={x0 - valueBarWidth - 8}
                  y={y0}
                  width={valueBarWidth}
                  height={Math.max(2, Math.min(8, nh))}
                  fill={fill}
                  rx={4}
                  opacity={0.2}
                />
              ) : null}
              <text
                x={labelX}
                y={mainY}
                textAnchor={isLeft ? "end" : "start"}
                dominantBaseline="middle"
                fontSize={isCompact ? 10.5 : 12}
                fill="#0F172A"
                fontFamily="system-ui, sans-serif"
                fontWeight={node.group === "symptom" ? 500 : 750}
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {truncate(node.label, isLeft ? (isCompact ? 22 : 32) : (isCompact ? 15 : 22))}
              </text>
              <text
                x={labelX}
                y={metaY}
                textAnchor={isLeft ? "end" : "start"}
                dominantBaseline="middle"
                fontSize={isCompact ? 8.5 : 9.5}
                fill="#64748B"
                fontWeight={600}
                fontFamily="system-ui, sans-serif"
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {node.value} {isCompact ? "pt" : "patient"}{!isCompact && (node.value ?? 0) !== 1 ? "s" : ""}
                {node.metric > 0 ? ` · ${node.metric}%` : ""}
              </text>
            </g>
          );
        })}
      </g>
      </svg>

      {hoveredLink ? (
        <Box
          sx={{
            position: "fixed",
            left: hoveredLink.x + 16,
            top: hoveredLink.y + 16,
            width: 320,
            zIndex: 1500,
            bgcolor: "#FFFFFF",
            border: "1px solid #CBD5E1",
            borderRadius: "12px",
            boxShadow: "0 18px 48px rgba(15,23,42,0.18)",
            p: 1.5,
            pointerEvents: "none",
          }}
        >
          <Typography variant="caption" sx={{ color: "#6B7280", fontWeight: 700 }}>
            Symptom flow
          </Typography>
          <Typography variant="subtitle2" sx={{ color: "#0F172A", fontWeight: 750, mt: 0.25 }}>
            {hoveredLink.source}
          </Typography>
          <Typography variant="body2" sx={{ color: "#475569", mt: 0.25 }}>
            to {hoveredLink.target}
          </Typography>

          <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mt: 1 }}>
            <Chip
              size="small"
              label={`${hoveredLink.value} patient${hoveredLink.value !== 1 ? "s" : ""}`}
              sx={{ bgcolor: "#F1F5F9", color: "#334155", fontWeight: 700 }}
            />
            <Chip
              size="small"
              label={`${hoveredLink.metric}% prevalence`}
              sx={{ bgcolor: "#DBEAFE", color: "#1E40AF", fontWeight: 700 }}
            />
          </Stack>

          <Typography variant="caption" sx={{ color: "#6B7280", display: "block", mt: 1.25 }}>
            Age and gender below are overall context for this symptom, not a
            breakdown of this ribbon.
          </Typography>

          <Stack direction="row" gap={1.5} sx={{ mt: 1.5 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="caption" sx={{ color: "#6B7280", fontWeight: 700 }}>
                Age context
              </Typography>
              {(hoveredLink.demographics?.age ?? []).length > 0 ? (
                hoveredLink.demographics!.age.map((bucket) => (
                  <Typography key={bucket.label} variant="caption" display="block" sx={{ color: "#334155" }}>
                    {bucket.label}: {bucket.n} patient{bucket.n !== 1 ? "s" : ""}
                  </Typography>
                ))
              ) : (
                <Typography variant="caption" display="block" sx={{ color: "#94A3B8" }}>
                  No age signal
                </Typography>
              )}
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="caption" sx={{ color: "#6B7280", fontWeight: 700 }}>
                Gender
              </Typography>
              {(hoveredLink.demographics?.gender ?? []).length > 0 ? (
                hoveredLink.demographics!.gender.map((bucket) => (
                  <Typography key={bucket.label} variant="caption" display="block" sx={{ color: "#334155" }}>
                    {bucket.label}: {bucket.n} patient{bucket.n !== 1 ? "s" : ""}
                  </Typography>
                ))
              ) : (
                <Typography variant="caption" display="block" sx={{ color: "#94A3B8" }}>
                  No gender signal
                </Typography>
              )}
            </Box>
          </Stack>
        </Box>
      ) : null}
    </Box>
  );
}

interface SankeyViewProps {
  data: GraphData;
  view: ViewMode;
  width: number;
  height: number;
  hovered: GraphNode | null;
  onHover: (n: GraphNode | null) => void;
  demographics: SymptomDemographicMap;
}

function SankeyView({
  data,
  view,
  width,
  height,
  hovered,
  onHover,
  demographics,
}: SankeyViewProps) {
  // Compare mode: stack two panels with a divider band labelled
  if (view === "compare") {
    const halfH = (height - 56) / 2;
    return (
      <Box sx={{ width, height, display: "flex", flexDirection: "column", bgcolor: "#FFFFFF" }}>
        <Box
          sx={{
            px: 3,
            py: 1,
            display: "flex",
            alignItems: "center",
            gap: 1,
            color: LINK_COLOR.referral,
            fontSize: "0.75rem",
            fontWeight: 700,
            letterSpacing: 0.4,
            borderBottom: "1px solid #E2E8F0",
          }}
        >
          Symptoms recorded around referral
        </Box>
        <SankeyPanel
          data={data}
          edgeType="referral"
          width={width}
          height={halfH}
          hovered={hovered}
          onHover={onHover}
          demographics={demographics}
        />
        <Box
          sx={{
            px: 3,
            py: 1,
            display: "flex",
            alignItems: "center",
            gap: 1,
            color: LINK_COLOR.diagnosis,
            fontSize: "0.75rem",
            fontWeight: 700,
            letterSpacing: 0.4,
            borderTop: "1px solid #E2E8F0",
            borderBottom: "1px solid #E2E8F0",
          }}
        >
          Symptoms linked to eventual diagnosis
        </Box>
        <SankeyPanel
          data={data}
          edgeType="diagnosis"
          width={width}
          height={halfH}
          hovered={hovered}
          onHover={onHover}
          demographics={demographics}
        />
      </Box>
    );
  }

  return (
    <SankeyPanel
      data={data}
      edgeType={view === "diagnosis" ? "diagnosis" : "referral"}
      width={width}
      height={height}
      hovered={hovered}
      onHover={onHover}
      demographics={demographics}
    />
  );
}

interface CancerSelectorProps {
  options: CancerOption[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
  onAnalyse: () => void;
}

function CancerSelector({
  options,
  selected,
  onToggle,
  onSelectAll,
  onClear,
  onAnalyse,
}: CancerSelectorProps) {
  if (options.length === 0) {
    return (
      <Box
        sx={{
          bgcolor: "#FFFFFF",
          border: "1px solid #E2E8F0",
          borderRadius: "12px",
          p: 3,
        }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 700, color: "#0F172A" }}>
          No tumour sites available
        </Typography>
        <Typography variant="body2" sx={{ color: "#475569", mt: 0.75 }}>
          No coded cancer-type slices were returned for this cohort.
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        bgcolor: "#FFFFFF",
        border: "1px solid #E2E8F0",
        borderRadius: "12px",
        p: 3,
        height: "100%",
        overflowY: "auto",
      }}
    >
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "stretch", md: "center" }}
        gap={2}
        sx={{ mb: 2.5 }}
      >
        <Box>
          <Typography variant="h6" component="h2" sx={{ color: "#0F172A", fontWeight: 750 }}>
            Choose tumour sites to analyse
          </Typography>
          <Typography variant="body2" sx={{ color: "#475569", mt: 0.5, maxWidth: 780 }}>
            Start with one or two tumour sites. The chart will only show symptoms
            linked to your selection, so the result stays readable as the cohort grows.
          </Typography>
        </Box>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
          <Button size="small" variant="outlined" onClick={onSelectAll}>
            Select all
          </Button>
          <Button size="small" variant="text" onClick={onClear} disabled={selected.size === 0}>
            Clear
          </Button>
          <Button
            size="small"
            variant="contained"
            onClick={onAnalyse}
            disabled={selected.size === 0}
            sx={{ bgcolor: "#1E40AF", "&:hover": { bgcolor: "#1D4ED8" } }}
          >
            Analyse {selected.size > 0 ? `(${selected.size})` : ""}
          </Button>
        </Stack>
      </Stack>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(2, minmax(0, 1fr))",
            lg: "repeat(3, minmax(0, 1fr))",
            xl: "repeat(4, minmax(0, 1fr))",
          },
          gap: 2,
        }}
      >
        {options.map((option) => {
          const isSelected = selected.has(option.id);
          return (
            <Button
              key={option.id}
              onClick={() => onToggle(option.id)}
              variant="outlined"
              sx={{
                position: "relative",
                justifyContent: "flex-start",
                alignItems: "stretch",
                textAlign: "left",
                minHeight: 168,
                p: 0,
                borderRadius: "12px",
                borderColor: isSelected ? "#1E40AF" : "#E2E8F0",
                bgcolor: isSelected ? "#EFF6FF" : "#FFFFFF",
                color: "#0F172A",
                overflow: "hidden",
                textTransform: "none",
                boxShadow: isSelected ? "0 10px 24px rgba(30,64,175,0.12)" : "none",
                "&:hover": {
                  borderColor: "#1E40AF",
                  bgcolor: isSelected ? "#EFF6FF" : "#F8FAFC",
                },
              }}
            >
              <Box
                component="span"
                aria-hidden="true"
                sx={{
                  position: "absolute",
                  left: 0,
                  top: 14,
                  bottom: 14,
                  width: 3,
                  borderRadius: 2,
                  bgcolor: isSelected ? "#1E40AF" : "#CBD5E1",
                }}
              />
              <Stack sx={{ p: "18px", width: "100%" }} gap={1.25}>
                <Stack direction="row" justifyContent="space-between" gap={1}>
                  <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 750 }}>
                    {option.label}
                  </Typography>
                  <Chip
                    size="small"
                    label={isSelected ? "Selected" : "Select"}
                    sx={{
                      bgcolor: isSelected ? "#DBEAFE" : "#F1F5F9",
                      color: isSelected ? "#1E40AF" : "#475569",
                      fontWeight: 700,
                      fontSize: "0.68rem",
                    }}
                  />
                </Stack>

                <Stack direction="row" gap={1} flexWrap="wrap">
                  <Chip
                    size="small"
                    label={`${option.referralN} referrals`}
                    sx={{ bgcolor: "#FEF3C7", color: "#92400E", fontWeight: 700 }}
                  />
                  <Chip
                    size="small"
                    label={`${option.diagnosisN} diagnoses`}
                    sx={{ bgcolor: "#ECFDF5", color: "#047857", fontWeight: 700 }}
                  />
                  {option.matchPct !== null ? (
                    <Chip
                      size="small"
                      label={`${option.matchPct}% match`}
                      sx={{ bgcolor: "#DBEAFE", color: "#1E40AF", fontWeight: 700 }}
                    />
                  ) : null}
                </Stack>

                <Box sx={{ mt: "auto" }}>
                  <Typography variant="caption" sx={{ color: "#6B7280", fontWeight: 700 }}>
                    Top symptom signal
                  </Typography>
                  <Typography variant="body2" sx={{ color: "#334155", mt: 0.25 }}>
                    {option.topSymptom}
                    {option.topSymptomN > 0 ? ` (${option.topSymptomN} patients)` : ""}
                  </Typography>
                </Box>
              </Stack>
            </Button>
          );
        })}
      </Box>
    </Box>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
  orgId?: string;
  dateFrom?: string;
  dateTo?: string;
}

// ── Main dialog ───────────────────────────────────────────────────────────────

export default function SymptomsDrilldownDialog({
  open,
  onClose,
  orgId,
  dateFrom,
  dateTo,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AuditSymptomsDrilldown | null>(null);

  const [view, setView] = useState<ViewMode>("referral");
  const overlays = useMemo(() => new Set<OverlayKey>(), []);
  const [minN, setMinN] = useState(1);
  const [layout, setLayout] = useState<LayoutMode>("sankey");
  const [selectedCancerIds, setSelectedCancerIds] = useState<Set<string>>(new Set());
  const [analysisStarted, setAnalysisStarted] = useState(false);
  const [dims, setDims] = useState({ w: 1200, h: 700 });

  // Ref to react-force-graph instance for force customisation
  const fgRef = useRef<any>(null);

  // Window dimensions
  useEffect(() => {
    const update = () =>
      setDims({
        // Account for dialog body padding and keep SVG inside the visible card.
        w: Math.max(640, window.innerWidth - 36),
        h: window.innerHeight - 150,
      });
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  // Fetch drilldown data
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setAnalysisStarted(false);
    setSelectedCancerIds(new Set());
    fetchAuditSymptomsDrilldown(orgId, dateFrom, dateTo)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError("Unable to load symptom data."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, orgId, dateFrom, dateTo]);

  const cancerOptions = useMemo(
    () => (data ? buildCancerOptions(data) : []),
    [data],
  );
  const symptomDemographics = useMemo(
    () => (data ? buildSymptomDemographics(data) : new Map()),
    [data],
  );

  // Build graph data
  const fullGraphData: GraphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    return buildGraph(data, view, overlays, minN);
  }, [data, view, overlays, minN]);

  const graphData = useMemo(
    () => filterGraphByCancerTargets(fullGraphData, selectedCancerIds),
    [fullGraphData, selectedCancerIds],
  );

  const toggleCancer = (id: string) =>
    setSelectedCancerIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const maxNodeVal = useMemo(
    () => Math.max(1, ...graphData.nodes.map((n) => n.value)),
    [graphData],
  );
  const maxLinkVal = useMemo(
    () => Math.max(1, ...graphData.links.map((l) => l.value)),
    [graphData],
  );

  const NODE_REL_SIZE = 7;

  // Hovered node + neighbour set for highlight/dim
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const neighbours = useMemo(() => {
    if (!hovered) return null;
    const ids = new Set<string>([hovered.id]);
    for (const l of graphData.links) {
      const sId = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const tId = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      if (sId === hovered.id) ids.add(tId);
      if (tId === hovered.id) ids.add(sId);
    }
    return ids;
  }, [hovered, graphData.links]);

  const isLit = useCallback(
    (node: GraphNode) => !neighbours || neighbours.has(node.id),
    [neighbours],
  );
  const isLinkLit = useCallback(
    (link: GraphLink) => {
      if (!hovered) return true;
      const sId = typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
      const tId = typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
      return sId === hovered.id || tId === hovered.id;
    },
    [hovered],
  );

  // In flow (DAG) mode the library lays out columns; we just need collision
  // to prevent label overlap. In network mode add charge/link/radial to
  // give a free-form layout
  const handleRef = useCallback(
    (fg: any) => {
      fgRef.current = fg;
      if (!fg) return;

      fg.d3Force(
        "collide",
        forceCollide<GraphNode>((n) => {
          if (n.group === "symptom") {
            const v = 1 + (n.value / Math.max(1, maxNodeVal)) * 8;
            return Math.sqrt(v) * NODE_REL_SIZE + 16;
          }
          return 50;
        }).strength(0.95),
      );

      if (layout === "flow") {
        // DAG mode: gentler charge so columns stay clean, library handles X
        fg.d3Force("charge")?.strength(-180).distanceMax(280);
        fg.d3Force("link")?.distance(120).strength(0.35);
        fg.d3Force("radial", null);
      } else {
        // Network mode: strong repulsion + radial perimeter for targets
        fg.d3Force("charge")?.strength(-650).distanceMax(450);
        fg.d3Force("link")?.distance(180).strength(0.6);
        fg.d3Force(
          "radial",
          forceRadial<GraphNode>(
            (n) => (n.group === "symptom" ? 0 : Math.min(dims.w, dims.h) * 0.34),
            dims.w / 2,
            dims.h / 2,
          ).strength((n) => (n.group === "symptom" ? 0 : 0.18)),
        );
      }
      fg.d3ReheatSimulation();
    },
    [dims.w, dims.h, maxNodeVal, layout],
  );

  // "after"  = draw on top of the library's own circle (symptoms)
  // "replace" = replace entirely (pill-shaped target nodes)
  const nodeCanvasObjectMode = useCallback(
    (n: any) => ((n as GraphNode).group === "symptom" ? "after" : "replace"),
    [],
  );

  // Helper: rounded rect for label backdrops
  const roundedRect = useCallback(
    (
      ctx: CanvasRenderingContext2D,
      x: number, y: number, w: number, h: number, r: number,
    ) => {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + w - r, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + r);
      ctx.lineTo(x + w, y + h - r);
      ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      ctx.lineTo(x + r, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - r);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.closePath();
    },
    [],
  );

  // Node canvas object — glow ring + prevalence arc + label for symptoms;
  // full pill rendering for cancer / age / gender nodes
  const nodeCanvasObject = useCallback(
    (nodeObj: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const node = nodeObj as GraphNode & { x: number; y: number };
      if (node.x == null) return;

      const lit = isLit(node);
      const isHover = hovered?.id === node.id;
      ctx.globalAlpha = lit ? 1 : 0.18;

      if (node.group === "symptom") {
        const val = 1 + (node.value / maxNodeVal) * 8;
        const r = Math.sqrt(val) * NODE_REL_SIZE;
        const glowCol = symptomGlow(node.metric);

        ctx.shadowBlur = isHover ? 28 : 16;
        ctx.shadowColor = glowCol;
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
        ctx.fillStyle = `${glowCol}1a`;
        ctx.fill();
        ctx.shadowBlur = 0;

        if (node.metric > 0) {
          ctx.beginPath();
          ctx.arc(
            node.x, node.y, r + 2,
            -Math.PI / 2,
            -Math.PI / 2 + (node.metric / 100) * 2 * Math.PI,
          );
          ctx.strokeStyle = glowCol;
          ctx.lineWidth = isHover ? 3.5 : 2.5;
          ctx.stroke();
        }

        // Label with a light backdrop pill - only when lit and zoomed enough
        if (lit && globalScale > 0.55) {
          const fs = Math.max(10, 11 / globalScale);
          ctx.font = `${isHover ? "600 " : ""}${fs}px system-ui, sans-serif`;
          const lbl = node.label.length > 22 ? node.label.slice(0, 21) + "\u2026" : node.label;
          const tw = ctx.measureText(lbl).width;
          const padX = 6;
          const padY = 3;
          const lx = node.x - tw / 2 - padX;
          const ly = node.y + r + 6;
          roundedRect(ctx, lx, ly, tw + padX * 2, fs + padY * 2, 4);
          ctx.fillStyle = "rgba(255,255,255,0.92)";
          ctx.fill();
          ctx.fillStyle = isHover ? "#0F172A" : "#334155";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(lbl, node.x, ly + (fs + padY * 2) / 2);
          ctx.textBaseline = "alphabetic";
        }
      } else {
        const col = TARGET_GLOW[node.group] ?? "#9ca3af";
        const fs = Math.max(11, 13 / globalScale);
        ctx.font = `700 ${fs}px system-ui, sans-serif`;
        const lbl = node.label.length > 18 ? node.label.slice(0, 17) + "\u2026" : node.label;
        const textW = ctx.measureText(lbl).width;
        const w = Math.max(textW + 28, 72);
        const h = fs + 14;

        ctx.shadowBlur = isHover ? 26 : 16;
        ctx.shadowColor = col;
        drawPill(ctx, node.x, node.y, w, h);
        ctx.fillStyle = `${col}26`;
        ctx.fill();
        ctx.strokeStyle = col;
        ctx.lineWidth = isHover ? 2.5 : 1.5;
        ctx.stroke();
        ctx.shadowBlur = 0;

        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(lbl, node.x, node.y);
        ctx.textBaseline = "alphabetic";
      }

      ctx.globalAlpha = 1;
    },
    [maxNodeVal, NODE_REL_SIZE, hovered, isLit, roundedRect],
  );

  const linkColor = useCallback(
    (link: any) => {
      const l = link as GraphLink;
      const base = LINK_COLOR[l.type] ?? "#9ca3af";
      if (!hovered) return base;
      return isLinkLit(l) ? base : `${base}1a`;
    },
    [hovered, isLinkLit],
  );

  const linkWidth = useCallback(
    (link: any) => {
      const l = link as GraphLink;
      const base = 1.5 + (l.value / maxLinkVal) * 5.5;
      return hovered && isLinkLit(l) ? base + 1.5 : base;
    },
    [maxLinkVal, hovered, isLinkLit],
  );

  // In compare mode curve referral and diagnosis edges in opposite directions
  // so overlapping edges between same node pair are distinguishable
  const linkCurvature = useCallback(
    (link: any) => {
      const l = link as GraphLink;
      if (view !== "compare") return 0;
      if (l.type === "referral") return 0.25;
      if (l.type === "diagnosis") return -0.25;
      return 0;
    },
    [view],
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen
      PaperProps={{
        sx: {
          bgcolor: "#F8FAFC",
          backgroundImage: "none",
          display: "flex",
          flexDirection: "column",
        },
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Box
        sx={{
          px: 3,
          py: 1.5,
          bgcolor: "#FFFFFF",
          borderBottom: "1px solid #E2E8F0",
          display: "flex",
          alignItems: "center",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Typography
          variant="h6"
          sx={{ color: "#0F172A", fontWeight: 700, mr: 1, flexShrink: 0 }}
        >
          Symptom Pattern Explorer
        </Typography>
        <Typography
          variant="body2"
          sx={{ color: "#475569", width: "100%", mt: -0.5, order: 10 }}
        >
          Follow the ribbons from symptoms recorded around referral to the tumour
          site. Wider ribbons mean more patients followed that pattern.
        </Typography>

        {/* View toggle */}
        <ToggleButtonGroup
          value={view}
          exclusive
          onChange={(_, v) => v && setView(v)}
          size="small"
          sx={{
            "& .MuiToggleButton-root": {
              color: "#475569",
              borderColor: "#CBD5E1",
              fontSize: "0.75rem",
              py: 0.5,
              px: 1.5,
            },
          }}
        >
          <ToggleButton
            value="referral"
            sx={{ "&.Mui-selected": { color: "#92400E", bgcolor: "#FEF3C7 !important" } }}
          >
            At Referral
          </ToggleButton>
          <ToggleButton
            value="diagnosis"
            sx={{ "&.Mui-selected": { color: "#047857", bgcolor: "#ECFDF5 !important" } }}
          >
            At Diagnosis
          </ToggleButton>
          <ToggleButton
            value="compare"
            sx={{ "&.Mui-selected": { color: "#1E40AF", bgcolor: "#DBEAFE !important" } }}
          >
            Compare
          </ToggleButton>
        </ToggleButtonGroup>

        {/* Layout toggle */}
        <ToggleButtonGroup
          value={layout}
          exclusive
          onChange={(_, v) => v && setLayout(v)}
          size="small"
          sx={{
            "& .MuiToggleButton-root": {
              color: "#475569",
              borderColor: "#CBD5E1",
              fontSize: "0.7rem",
              py: 0.5,
              px: 1.25,
            },
          }}
        >
          <ToggleButton
            value="sankey"
            sx={{ "&.Mui-selected": { color: "#0F172A", bgcolor: "#F1F5F9 !important" } }}
          >
            Sankey
          </ToggleButton>
          <ToggleButton
            value="flow"
            sx={{ "&.Mui-selected": { color: "#0F172A", bgcolor: "#F1F5F9 !important" } }}
          >
            Flow
          </ToggleButton>
          <ToggleButton
            value="network"
            sx={{ "&.Mui-selected": { color: "#0F172A", bgcolor: "#F1F5F9 !important" } }}
          >
            Network
          </ToggleButton>
        </ToggleButtonGroup>

        {/* Min patients */}
        <Stack direction="row" gap={0.75} alignItems="center">
          <Typography variant="caption" sx={{ color: "#6B7280", fontSize: "0.72rem" }}>
            min&nbsp;n:
          </Typography>
          {[1, 2, 5].map((v) => (
            <Chip
              key={v}
              size="small"
              label={`${v}+`}
              variant={minN === v ? "filled" : "outlined"}
              onClick={() => setMinN(v)}
              sx={{
                fontSize: "0.68rem",
                cursor: "pointer",
                color: minN === v ? "#1E40AF" : "#475569",
                borderColor: "#CBD5E1",
                bgcolor: minN === v ? "#DBEAFE" : "transparent",
              }}
            />
          ))}
        </Stack>

        <Box sx={{ flex: 1 }} />

        {/* Node / link counts */}
        <Typography
          variant="caption"
          sx={{ color: "#6B7280", fontSize: "0.72rem", flexShrink: 0 }}
        >
          {analysisStarted
            ? `${graphData.nodes.length} nodes · ${graphData.links.length} connections`
            : `${selectedCancerIds.size} selected`}
        </Typography>

        {analysisStarted ? (
          <Button
            onClick={() => setAnalysisStarted(false)}
            size="small"
            variant="outlined"
            sx={{ color: "#1E40AF", borderColor: "#CBD5E1", flexShrink: 0 }}
          >
            Change selection
          </Button>
        ) : null}

        <Button
          onClick={onClose}
          size="small"
          sx={{ color: "#1E40AF", borderColor: "#CBD5E1", flexShrink: 0 }}
          variant="outlined"
        >
          Close
        </Button>
      </Box>

      {/* ── Graph area ─────────────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, position: "relative", overflow: "hidden", p: 2 }}>
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
            <CircularProgress aria-label="Loading" role="status" sx={{ color: "#1E40AF" }} />
          </Box>
        )}
        {!loading && error && (
          <Typography color="error" sx={{ p: 3 }}>
            {error}
          </Typography>
        )}
        {!loading && !error && data && !analysisStarted && (
          <CancerSelector
            options={cancerOptions}
            selected={selectedCancerIds}
            onToggle={toggleCancer}
            onSelectAll={() => setSelectedCancerIds(new Set(cancerOptions.map((o) => o.id)))}
            onClear={() => setSelectedCancerIds(new Set())}
            onAnalyse={() => setAnalysisStarted(true)}
          />
        )}
        {!loading && !error && data && analysisStarted && layout === "sankey" && (
          <Box
            sx={{
              width: "100%",
              height: "100%",
              overflowY: "auto",
              overflowX: "hidden",
              bgcolor: "#FFFFFF",
              border: "1px solid #E2E8F0",
              borderRadius: "12px",
            }}
          >
            <SankeyView
              data={graphData}
              view={view}
              width={dims.w}
              height={dims.h}
              hovered={hovered}
              onHover={setHovered}
              demographics={symptomDemographics}
            />
          </Box>
        )}
        {!loading && !error && data && analysisStarted && layout !== "sankey" && (
          <Tooltip
            title={
              view === "compare"
                ? "Amber curves = referral edges · Green curves = diagnosis edges · Thicker = more patients"
                : "Hover a node to see connections · Drag nodes · Scroll to zoom"
            }
            placement="bottom-start"
            arrow
          >
            <Box sx={{ width: "100%", height: "100%" }}>
              <ForceGraph2D
                ref={handleRef}
                graphData={graphData}
                nodeId="id"
                width={dims.w}
                height={dims.h}
                backgroundColor="#FFFFFF"
                dagMode={layout === "flow" ? "lr" : undefined}
                dagLevelDistance={layout === "flow" ? 380 : undefined}
                // Standard library node sizing + colour (drives physics repulsion too)
                nodeVal={(n: any) => 1 + ((n as GraphNode).value / maxNodeVal) * 8}
                nodeRelSize={NODE_REL_SIZE}
                nodeColor={(n: any) => {
                  const node = n as GraphNode;
                  return node.group === "symptom"
                    ? `${symptomGlow(node.metric)}cc`
                    : `${TARGET_GLOW[node.group] ?? "#9ca3af"}cc`;
                }}
                // Canvas decorations: glow + arc + label ("after") or full pill ("replace")
                nodeCanvasObjectMode={nodeCanvasObjectMode}
                nodeCanvasObject={nodeCanvasObject}
                nodeLabel={(n: any) => {
                  const node = n as GraphNode;
                  return `${node.label} · ${node.value} patient${node.value !== 1 ? "s" : ""} · ${node.metric}% prevalence`;
                }}
                onNodeHover={(n: any) => setHovered((n as GraphNode | null) ?? null)}
                linkColor={linkColor}
                linkWidth={linkWidth}
                linkCurvature={linkCurvature}
                linkDirectionalParticles={(l: any) => (hovered && isLinkLit(l as GraphLink) ? 3 : 0)}
                linkDirectionalParticleSpeed={0.008}
                linkDirectionalParticleWidth={(l: any) =>
                  2 + ((l as GraphLink).value / maxLinkVal) * 3
                }
                linkDirectionalParticleColor={linkColor}
                cooldownTicks={200}
                d3AlphaDecay={0.012}
                d3VelocityDecay={0.28}
                warmupTicks={50}
                onEngineStop={() => fgRef.current?.zoomToFit(600, 100)}
              />
            </Box>
          </Tooltip>
        )}
      </Box>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <Box
        sx={{
          px: 3,
          py: 1,
          bgcolor: "#FFFFFF",
          borderTop: "1px solid #E2E8F0",
          display: "flex",
          alignItems: "center",
          gap: 3,
          flexWrap: "wrap",
        }}
      >
        <Legend view={view} />
        <Box sx={{ flex: 1 }} />
        <Typography variant="caption" sx={{ color: "#6B7280", fontSize: "0.72rem" }}>
          Inspired by{" "}
          <Link
            href="https://www.gatewayc.org.uk/cancer-maps/"
            target="_blank"
            rel="noopener noreferrer"
            sx={{ color: "#1E40AF" }}
          >
            Dr Ben Noble&apos;s Cancer Maps
          </Link>{" "}
          (Gateway C)
        </Typography>
      </Box>
    </Dialog>
  );
}
