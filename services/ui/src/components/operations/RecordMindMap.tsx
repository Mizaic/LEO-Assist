/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  Divider,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import BlockIcon from "@mui/icons-material/Block";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import AssertionChip from "@/components/AssertionChip";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LabelEntity {
  text: string;
  label: string;
  start: number;
  end: number;
  assertion?: string;
  numeric_value?: string | number | null;
  unit?: string | null;
  value?: string | number | null;
  [k: string]: unknown;
}

interface ResolvedCandidate {
  snomed_concept_id: string | null;
  snomed_term: string | null;
  semantic_tag: string | null;
  score: number;
  source: string;
}

// ---------------------------------------------------------------------------
// Colour + label constants
// ---------------------------------------------------------------------------

const ENTITY_LABEL_COLORS: Record<string, { bg: string; border: string }> = {
  disorder: { bg: "#FEE2E2", border: "#DC2626" },
  finding: { bg: "#DBEAFE", border: "#2563EB" },
  procedure: { bg: "#D1FAE5", border: "#059669" },
  observable_entity: { bg: "#E0E7FF", border: "#4F46E5" },
  qualifier_value: { bg: "#FEF3C7", border: "#D97706" },
  substance: { bg: "#FCE7F3", border: "#DB2777" },
  medicinal_product: { bg: "#ECFCCB", border: "#65A30D" },
  clinical_drug: { bg: "#D9F99D", border: "#4D7C0F" },
  situation: { bg: "#E0F2FE", border: "#0284C7" },
  event: { bg: "#F3E8FF", border: "#7C3AED" },
  body_structure: { bg: "#FFEDD5", border: "#EA580C" },
  tumor_staging: { bg: "#FECACA", border: "#B91C1C" },
  assessment_scale: { bg: "#BFDBFE", border: "#0d46d6" },
  staging_scale: { bg: "#C4B5FD", border: "#6D28D9" },
  regime_therapy: { bg: "#BBF7D0", border: "#15803D" },
  record_artifact: { bg: "#E5E7EB", border: "#4B5563" },
  physical_object: { bg: "#FDE68A", border: "#B45309" },
  organism: { bg: "#A7F3D0", border: "#047857" },
  morphologic_abnormality: { bg: "#FBCFE8", border: "#BE185D" },
  occupation: { bg: "#DDD6FE", border: "#5B21B6" },
  attribute: { bg: "#FECDD3", border: "#E11D48" },
  environment: { bg: "#CCFBF1", border: "#0D9488" },
  product: { bg: "#D9F99D", border: "#3F6212" },
  X_TEMPORAL: { bg: "#E0F2FE", border: "#0369A1" },
  X_DOSAGE: { bg: "#FEF9C3", border: "#CA8A04" },
  X_FREQUENCY: { bg: "#FEF3C7", border: "#B45309" },
  X_ROUTE: { bg: "#FDE68A", border: "#D97706" },
};

const ENTITY_LABEL_DISPLAY: Record<string, string> = {
  disorder: "Health condition",
  finding: "Finding or symptom",
  procedure: "Treatment or procedure",
  observable_entity: "Test or measurement",
  qualifier_value: "Qualifier",
  substance: "Substance",
  medicinal_product: "Medicine",
  clinical_drug: "Drug",
  situation: "Situation",
  event: "Event",
  body_structure: "Body part",
  tumor_staging: "Tumour stage",
  assessment_scale: "Assessment scale",
  staging_scale: "Staging scale",
  regime_therapy: "Therapy plan",
  record_artifact: "Record type",
  physical_object: "Physical object",
  organism: "Organism",
  morphologic_abnormality: "Structural change",
  occupation: "Job or role",
  attribute: "Attribute",
  environment: "Environment",
  product: "Product",
  X_TEMPORAL: "Time or date",
  X_DOSAGE: "Dose",
  X_FREQUENCY: "How often",
  X_ROUTE: "How given",
};

const DEFAULT_ENTITY_COLOR = { bg: "#F3F4F6", border: "#9CA3AF" };

// ---------------------------------------------------------------------------
// HighlightedText — encounter text with coloured inline marks and hover state
// ---------------------------------------------------------------------------

function HighlightedText({
  text,
  entities,
  hoveredIdx,
  onHover,
}: {
  text: string;
  entities: LabelEntity[];
  hoveredIdx: number | null;
  onHover: (idx: number | null) => void;
}) {
  const sorted = [...entities]
    .filter((e) => typeof e.start === "number" && typeof e.end === "number")
    .sort((a, b) => a.start - b.start);

  const segments: { text: string; entityIdx?: number; entity?: LabelEntity }[] = [];
  let cursor = 0;

  for (const ent of sorted) {
    const s = Math.max(ent.start, cursor);
    const e = ent.end;
    if (s >= e) continue;
    if (s > cursor) segments.push({ text: text.slice(cursor, s) });
    const origIdx = entities.indexOf(ent);
    segments.push({ text: text.slice(s, e), entity: ent, entityIdx: origIdx });
    cursor = e;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });

  return (
    <Typography
      component="div"
      sx={{ fontSize: 13.5, lineHeight: 2, whiteSpace: "pre-wrap", wordBreak: "break-word" }}
    >
      {segments.map((seg, i) => {
        if (!seg.entity) return <span key={i}>{seg.text}</span>;
        const colors = ENTITY_LABEL_COLORS[seg.entity.label] ?? DEFAULT_ENTITY_COLOR;
        const isActive = hoveredIdx === seg.entityIdx;
        const isDimmed = hoveredIdx !== null && !isActive;
        return (
          <Tooltip
            key={i}
            title={ENTITY_LABEL_DISPLAY[seg.entity.label] ?? seg.entity.label}
            arrow
            placement="top"
          >
            <mark
              data-entity-idx={seg.entityIdx}
              onMouseEnter={() => onHover(seg.entityIdx!)}
              onMouseLeave={() => onHover(null)}
              style={{
                background: isActive ? colors.border + "30" : colors.bg,
                borderBottom: `2px solid ${colors.border}`,
                borderRadius: 3,
                padding: "2px 4px",
                cursor: "default",
                color: "inherit",
                opacity: isDimmed ? 0.4 : 1,
                transition: "opacity 0.15s, background 0.15s",
                boxShadow: isActive ? `0 0 0 2px ${colors.border}50` : "none",
              }}
            >
              {seg.text}
            </mark>
          </Tooltip>
        );
      })}
    </Typography>
  );
}

// ---------------------------------------------------------------------------
// EntityCard
// ---------------------------------------------------------------------------

function EntityCard({
  entity,
  top,
}: {
  entity: LabelEntity;
  top: ResolvedCandidate | undefined;
}) {
  const colors = ENTITY_LABEL_COLORS[entity.label] ?? DEFAULT_ENTITY_COLOR;
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" flexWrap="wrap" gap={0.4} useFlexGap alignItems="center">
        <Chip
          label={entity.text}
          size="small"
          variant="outlined"
          sx={{
            fontSize: 11,
            fontWeight: 600,
            maxWidth: 220,
            bgcolor: colors.bg,
            borderColor: colors.border,
            "& .MuiChip-label": { color: colors.border },
          }}
        />
        {entity.assertion && entity.assertion !== "present" && (
          <AssertionChip assertion={entity.assertion} />
        )}
      </Stack>

      <Chip
        label={ENTITY_LABEL_DISPLAY[entity.label] ?? entity.label}
        size="small"
        sx={{
          height: 17,
          fontSize: 9.5,
          bgcolor: colors.bg,
          color: colors.border,
          border: `1px solid ${colors.border}35`,
          alignSelf: "flex-start",
          "& .MuiChip-label": { px: 0.75 },
        }}
      />

      {top?.snomed_term && (
        <Typography variant="caption" sx={{ fontSize: 10.5, fontFamily: "monospace", color: "text.primary", lineHeight: 1.4 }}>
          {top.snomed_term}
        </Typography>
      )}
      {top?.snomed_concept_id && (
        <Typography variant="caption" sx={{ fontSize: 9.5, fontFamily: "monospace", color: "text.disabled" }}>
          {top.snomed_concept_id}
        </Typography>
      )}

      {(entity.numeric_value != null || entity.value != null) && (
        <Stack direction="row" spacing={0.75} alignItems="baseline">
          <Typography variant="caption" sx={{ fontSize: 9.5, color: "text.secondary" }}>Value</Typography>
          <Typography variant="caption" sx={{ fontSize: 10, fontFamily: "monospace", fontWeight: 600 }}>
            {String(entity.numeric_value ?? entity.value ?? "")}
            {entity.unit ? ` ${entity.unit}` : ""}
          </Typography>
        </Stack>
      )}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

function rectEdgePoint(
  cx: number, cy: number,
  hw: number, hh: number,
  tx: number, ty: number,
): [number, number] {
  const dx = tx - cx;
  const dy = ty - cy;
  if (dx === 0 && dy === 0) return [cx, cy];
  const scaleX = dx !== 0 ? hw / Math.abs(dx) : Infinity;
  const scaleY = dy !== 0 ? hh / Math.abs(dy) : Infinity;
  const scale = Math.min(scaleX, scaleY);
  return [cx + dx * scale, cy + dy * scale];
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

function layoutCards(
  n: number,
  cardSizes: { w: number; h: number }[],
  ncx: number, ncy: number, nhw: number, nhh: number,
  canvasW: number, canvasH: number,
): { x: number; y: number }[] {
  if (n === 0) return [];

  const edgePad = 20;
  const rx = (canvasW / 2 - edgePad) * 0.72;
  const ry = (canvasH / 2 - edgePad) * 0.72;
  const startAngle = -Math.PI / 3;

  const pts = Array.from({ length: n }, (_, i) => {
    const angle = (i / n) * 2 * Math.PI + startAngle;
    return { x: ncx + rx * Math.cos(angle), y: ncy + ry * Math.sin(angle) };
  });

  const nucleusGap = 32;
  const cardGap = 20;

  for (let iter = 0; iter < 30; iter++) {
    let moved = false;

    for (let i = 0; i < n; i++) {
      const dx = pts[i].x - ncx;
      const dy = pts[i].y - ncy;
      const clearW = nhw + cardSizes[i].w / 2 + nucleusGap;
      const clearH = nhh + cardSizes[i].h / 2 + nucleusGap;
      const ovX = clearW - Math.abs(dx);
      const ovY = clearH - Math.abs(dy);
      if (ovX > 0 && ovY > 0) {
        moved = true;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const push = Math.max(ovX, ovY);
        pts[i].x += (dx / dist) * push;
        pts[i].y += (dy / dist) * push;
      }
    }

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = pts[j].x - pts[i].x;
        const dy = pts[j].y - pts[i].y;
        const sepW = (cardSizes[i].w + cardSizes[j].w) / 2 + cardGap;
        const sepH = (cardSizes[i].h + cardSizes[j].h) / 2 + cardGap;
        const ovX = sepW - Math.abs(dx);
        const ovY = sepH - Math.abs(dy);
        if (ovX > 0 && ovY > 0) {
          moved = true;
          if (ovX < ovY) {
            const push = ovX / 2 + 1;
            const sign = dx >= 0 ? 1 : -1;
            pts[i].x -= sign * push;
            pts[j].x += sign * push;
          } else {
            const push = ovY / 2 + 1;
            const sign = dy >= 0 ? 1 : -1;
            pts[i].y -= sign * push;
            pts[j].y += sign * push;
          }
        }
      }
    }

    for (let i = 0; i < n; i++) {
      const px = cardSizes[i].w / 2 + edgePad;
      const py = cardSizes[i].h / 2 + edgePad;
      pts[i].x = Math.max(px, Math.min(canvasW - px, pts[i].x));
      pts[i].y = Math.max(py, Math.min(canvasH - py, pts[i].y));
    }

    if (!moved) break;
  }

  return pts;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface RecordMindMapProps {
  open: boolean;
  onClose: () => void;
  text: string;
  entitiesJson: string;
  resolvedData: Record<string, ResolvedCandidate[]>;
  resolving?: boolean;
  /** Include/exclude state of the current record */
  included: boolean;
  /** Navigation */
  currentIndex: number;
  totalCount: number;
  onNext: () => void;
  onPrev: () => void;
  onInclude: () => void;
  onExclude: () => void;
}

const CARD_W = 240;
const CARD_HW = CARD_W / 2;
const CARD_HH = 60;

interface SpanAnchor {
  x: number;
  y: number;
  bottom: number;
}

export default function RecordMindMap({
  open,
  onClose,
  text,
  entitiesJson,
  resolvedData,
  resolving = false,
  included,
  currentIndex,
  totalCount,
  onNext,
  onPrev,
  onInclude,
  onExclude,
}: RecordMindMapProps) {
  const entities: LabelEntity[] = useMemo(() => {
    try { return JSON.parse(entitiesJson) as LabelEntity[]; } catch { return []; }
  }, [entitiesJson]);

  const canvasRef = useRef<HTMLDivElement>(null);
  const nucleusRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 });
  const [nucleusSize, setNucleusSize] = useState({ hw: 200, hh: 80 });
  const [spanAnchors, setSpanAnchors] = useState<Record<number, SpanAnchor>>({});
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const measureSpans = useCallback(() => {
    if (!canvasRef.current || !nucleusRef.current) return;
    const canvasRect = canvasRef.current.getBoundingClientRect();
    const marks = nucleusRef.current.querySelectorAll<HTMLElement>("mark[data-entity-idx]");
    const anchors: Record<number, SpanAnchor> = {};
    marks.forEach((mark) => {
      const idx = Number(mark.dataset.entityIdx);
      if (isNaN(idx)) return;
      const r = mark.getBoundingClientRect();
      anchors[idx] = {
        x: r.left + r.width / 2 - canvasRect.left,
        y: r.top + r.height / 2 - canvasRect.top,
        bottom: r.bottom - canvasRect.top,
      };
    });
    setSpanAnchors(anchors);
  }, []);

  const measure = useCallback(() => {
    if (canvasRef.current) {
      const r = canvasRef.current.getBoundingClientRect();
      if (r.width > 0) setCanvasSize({ w: r.width, h: r.height });
    }
    if (nucleusRef.current) {
      const r = nucleusRef.current.getBoundingClientRect();
      if (r.width > 0 && r.height > 0)
        setNucleusSize({ hw: r.width / 2, hh: r.height / 2 });
    }
    measureSpans();
  }, [measureSpans]);

  useEffect(() => {
    if (!open) return;
    measure();
    const t1 = setTimeout(measure, 60);
    const t2 = setTimeout(measure, 250);
    const t3 = setTimeout(measure, 500);
    const t4 = setTimeout(measure, 800);
    const ro = new ResizeObserver(measure);
    if (canvasRef.current) ro.observe(canvasRef.current);
    if (nucleusRef.current) ro.observe(nucleusRef.current);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); clearTimeout(t4); ro.disconnect(); };
  }, [open, entities, measure]);

  useEffect(() => { measure(); }, [resolvedData, measure]);

  const handleNucleusScroll = useCallback(() => { measureSpans(); }, [measureSpans]);

  // Keyboard navigation: left/right arrows
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); onNext(); }
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); onPrev(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onNext, onPrev]);

  // Reset hover when record changes
  useEffect(() => { setHoveredIdx(null); }, [entitiesJson]);

  const { w, h } = canvasSize;
  const cx = w / 2;
  const cy = h / 2;

  const nucleusW = Math.min(420, Math.max(300, text.length * 2.5 + 60));

  const cardSizes = useMemo(() =>
    entities.map((ent) => {
      let ch = 60;
      const hasResolved = !!resolvedData[ent.text?.trim() ?? ""]?.[0];
      if (hasResolved) ch += 42;
      if (ent.numeric_value != null || ent.value != null) ch += 22;
      if (ent.assertion && ent.assertion !== "present") ch += 6;
      return { w: CARD_W, h: ch };
    }),
    [entities, resolvedData]
  );

  const cardPositions = useMemo(() => {
    if (w === 0 || h === 0) return entities.map(() => ({ x: 0, y: 0 }));
    return layoutCards(
      entities.length, cardSizes,
      cx, cy, nucleusSize.hw, nucleusSize.hh,
      w, h,
    );
  }, [entities.length, cardSizes, cx, cy, w, h, nucleusSize.hw, nucleusSize.hh]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={false}
      fullWidth
      PaperProps={{
        sx: {
          width: "94vw",
          height: "90vh",
          maxWidth: "none",
          m: 1.5,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          borderRadius: 3,
        },
      }}
    >
      {/* ── Header toolbar ── */}
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{
          px: 2,
          py: 0.75,
          borderBottom: "1px solid",
          borderColor: "divider",
          flexShrink: 0,
          bgcolor: "background.paper",
        }}
      >
        {/* Navigation */}
        <Tooltip title="Previous record (←)">
          <span>
            <IconButton size="small" onClick={onPrev} disabled={currentIndex <= 0} aria-label="Previous record">
              <ChevronLeftIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: 12, minWidth: 60, textAlign: "center" }}>
          {currentIndex + 1} of {totalCount}
        </Typography>
        <Tooltip title="Next record (→)">
          <span>
            <IconButton size="small" onClick={onNext} disabled={currentIndex >= totalCount - 1} aria-label="Next record">
              <ChevronRightIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

        <Typography variant="subtitle2" sx={{ fontWeight: 700, flex: 1, fontSize: 14 }}>
          Entity map
        </Typography>

        {resolving && (
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mr: 0.5 }}>
            <CircularProgress size={12} />
            <Typography variant="caption" color="text.secondary">Resolving…</Typography>
          </Stack>
        )}

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

        {/* Include / Exclude actions */}
        {included ? (
          <Button
            size="small"
            color="error"
            variant="outlined"
            startIcon={<BlockIcon sx={{ fontSize: 15 }} />}
            onClick={onExclude}
            sx={{ textTransform: "none", fontSize: 12, py: 0.25 }}
          >
            Exclude
          </Button>
        ) : (
          <Button
            size="small"
            color="success"
            variant="outlined"
            startIcon={<CheckCircleOutlineIcon sx={{ fontSize: 15 }} />}
            onClick={onInclude}
            sx={{ textTransform: "none", fontSize: 12, py: 0.25 }}
          >
            Include
          </Button>
        )}

        <Chip
          label={included ? "Included" : "Excluded"}
          size="small"
          color={included ? "success" : "default"}
          variant="outlined"
          sx={{ fontSize: 11 }}
        />

        <IconButton size="small" onClick={onClose} aria-label="Close entity map">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>

      {/* ── Canvas ── */}
      <Box
        ref={canvasRef}
        sx={{
          flex: 1,
          position: "relative",
          overflow: "hidden",
          background: (t) =>
            t.palette.mode === "dark"
              ? "radial-gradient(ellipse at center, #1e293b 0%, #0f172a 100%)"
              : "radial-gradient(ellipse at center, #eef2ff 0%, #f8fafc 60%, #f1f5f9 100%)",
        }}
      >
        {/* Orbit ellipse */}
        {w > 0 && (
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 0 }}>
            <ellipse
              cx={cx} cy={cy}
              rx={(w / 2 - 20) * 0.72} ry={(h / 2 - 20) * 0.72}
              fill="none" stroke="#94a3b8" strokeWidth={1} strokeOpacity={0.1} strokeDasharray="6 4"
            />
          </svg>
        )}

        {/* SVG connectors */}
        {w > 0 && (
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 3 }}>
            <defs>
              {entities.map((ent, i) => {
                const colors = ENTITY_LABEL_COLORS[ent.label] ?? DEFAULT_ENTITY_COLOR;
                return (
                  <marker key={`dot-${i}`} id={`dot-${i}`} viewBox="0 0 8 8" refX="4" refY="4" markerWidth="6" markerHeight="6">
                    <circle cx="4" cy="4" r="3" fill={colors.border} opacity={0.8} />
                  </marker>
                );
              })}
            </defs>

            {cardPositions.map((card, i) => {
              const ent = entities[i];
              const colors = ENTITY_LABEL_COLORS[ent.label] ?? DEFAULT_ENTITY_COLOR;
              const span = spanAnchors[i];

              let nx: number, ny: number;
              if (span) { nx = span.x; ny = span.bottom + 2; }
              else { [nx, ny] = rectEdgePoint(cx, cy, nucleusSize.hw + 6, nucleusSize.hh + 6, card.x, card.y); }

              const cardHH = (cardSizes[i]?.h ?? CARD_HH * 2) / 2;
              const [kx, ky] = rectEdgePoint(card.x, card.y, CARD_HW + 6, cardHH + 6, nx, ny);

              const dx = kx - nx;
              const dy = ky - ny;
              const len = Math.sqrt(dx * dx + dy * dy) || 1;
              const pull = len * 0.35;
              const ux = dx / len;
              const uy = dy / len;
              const perp = len * 0.05;
              const px = -uy * perp;
              const py = ux * perp;

              const isActive = hoveredIdx === i;
              const isDimmed = hoveredIdx !== null && !isActive;

              return (
                <path
                  key={i}
                  d={`M ${nx} ${ny} C ${nx + ux * pull + px} ${ny + uy * pull + py} ${kx - ux * pull + px} ${ky - uy * pull + py} ${kx} ${ky}`}
                  fill="none"
                  stroke={colors.border}
                  strokeWidth={isActive ? 2.5 : 1.6}
                  strokeOpacity={isDimmed ? 0.12 : isActive ? 0.85 : 0.45}
                  strokeLinecap="round"
                  markerStart={`url(#dot-${i})`}
                  markerEnd={`url(#dot-${i})`}
                  style={{ transition: "stroke-opacity 0.15s, stroke-width 0.15s" }}
                />
              );
            })}
          </svg>
        )}

        {/* Nucleus */}
        <Paper
          ref={nucleusRef}
          elevation={4}
          onScroll={handleNucleusScroll}
          sx={{
            position: "absolute",
            left: "50%",
            top: "50%",
            transform: "translate(-50%, -50%)",
            width: nucleusW,
            maxHeight: "48%",
            overflowY: "auto",
            borderRadius: 2.5,
            border: "2px solid",
            borderColor: "primary.main",
            p: 2.5,
            zIndex: 2,
          }}
        >
          <Typography
            variant="caption"
            sx={{
              textTransform: "uppercase",
              letterSpacing: 0.8,
              fontWeight: 700,
              fontSize: 10,
              color: "primary.main",
              display: "block",
              mb: 1,
            }}
          >
            Encounter text
          </Typography>
          <HighlightedText
            text={text}
            entities={entities}
            hoveredIdx={hoveredIdx}
            onHover={setHoveredIdx}
          />
        </Paper>

        {/* Entity cards */}
        {w > 0 && cardPositions.map((pos, i) => {
          const ent = entities[i];
          const colors = ENTITY_LABEL_COLORS[ent.label] ?? DEFAULT_ENTITY_COLOR;
          const top = resolvedData[ent.text?.trim() ?? ""]?.[0];
          const isActive = hoveredIdx === i;
          const isDimmed = hoveredIdx !== null && !isActive;

          return (
            <Paper
              key={i}
              elevation={isActive ? 8 : 2}
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
              sx={{
                position: "absolute",
                left: pos.x,
                top: pos.y,
                transform: isActive
                  ? "translate(-50%, -50%) scale(1.04)"
                  : "translate(-50%, -50%)",
                width: CARD_W,
                p: 1.5,
                borderRadius: 2,
                borderLeft: "3.5px solid",
                borderLeftColor: colors.border,
                zIndex: isActive ? 4 : 2,
                bgcolor: "background.paper",
                opacity: isDimmed ? 0.4 : 1,
                transition: "opacity 0.15s, box-shadow 0.15s, transform 0.15s",
                cursor: "default",
              }}
            >
              <EntityCard entity={ent} top={top} />
            </Paper>
          );
        })}

        {/* Empty state */}
        {entities.length === 0 && (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              pointerEvents: "none",
            }}
          >
            <Typography variant="body2" color="text.disabled">No entities to map</Typography>
          </Box>
        )}
      </Box>
    </Dialog>
  );
}
