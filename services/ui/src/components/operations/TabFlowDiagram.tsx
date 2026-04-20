/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import { useState, useId } from "react";
import {
  Box,
  Card,
  CardContent,
  Chip,
  Collapse,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

/* ================================================================== */
/*  Types                                                              */
/* ================================================================== */

export interface TabStageBranch {
  label: string;
  description: string;
}

export interface TabStage {
  id: string;
  num: number;
  label: string;
  tooltip: string;
  detailIn: string;
  detailOut: string;
  branches?: TabStageBranch[];
}

export interface TabFlowDiagramProps {
  stages: TabStage[];
  color: string;
  lightColor: string;
  trackLabel: string;
}

/* ================================================================== */
/*  Layout constants                                                   */
/* ================================================================== */

const VB_W = 960;
const VB_H = 170;
const TRACK_Y = 82;
const TRACK_X_START = 80;
const TRACK_X_END = 880;
const R = 22;
/* Cap rendered width so the diagram looks the same size across all panels */
const SVG_MAX_W = 820;
const FONT = "'DM Sans',system-ui,sans-serif";
const PARTICLES = 2;
const PARTICLE_DUR = 5;

/* ================================================================== */
/*  Component                                                          */
/* ================================================================== */

export default function TabFlowDiagram({
  stages,
  color,
  lightColor,
  trackLabel,
}: TabFlowDiagramProps) {
  const rawId = useId();
  const uid = rawId.replace(/:/g, "");
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const n = stages.length;
  const xPositions = stages.map((_, i) =>
    n === 1
      ? (TRACK_X_START + TRACK_X_END) / 2
      : TRACK_X_START + (i * (TRACK_X_END - TRACK_X_START)) / (n - 1),
  );

  const trackPath = `M ${TRACK_X_START} ${TRACK_Y} L ${TRACK_X_END} ${TRACK_Y}`;

  const selectedStage = stages.find((s) => s.id === selected) ?? null;
  const hoveredStage = stages.find((s) => s.id === hovered) ?? null;

  const toggle = (id: string) =>
    setSelected((prev) => (prev === id ? null : id));

  return (
    <Box>
      {/* Legend row */}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Box
          sx={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            bgcolor: color,
            flexShrink: 0,
          }}
        />
        <Typography
          variant="caption"
          sx={{ fontWeight: 600, color: "text.secondary" }}
        >
          {trackLabel}
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ ml: "auto !important" }}
        >
          Click any step to learn more
        </Typography>
      </Stack>

      {/* SVG diagram */}
      <Box sx={{ position: "relative", width: "100%", maxWidth: SVG_MAX_W }}>
        <svg
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          width="100%"
          style={{ display: "block" }}
          role="img"
          aria-label={`${trackLabel} pipeline flow diagram`}
        >
          <defs>
            <filter
              id={`${uid}glow`}
              x="-100%"
              y="-100%"
              width="300%"
              height="300%"
            >
              <feGaussianBlur
                in="SourceGraphic"
                stdDeviation="3"
                result="blur"
              />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <marker
              id={`${uid}arr`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 8 5 L 0 9 z" fill={color} opacity="0.5" />
            </marker>
          </defs>

          {/* Track line */}
          <path
            id={`${uid}trk`}
            d={trackPath}
            stroke={color}
            strokeWidth={4}
            strokeLinecap="round"
            fill="none"
            opacity={0.2}
            markerEnd={`url(#${uid}arr)`}
          />

          {/* Particles */}
          {Array.from({ length: PARTICLES }, (_, i) => (
            <circle
              key={`p${i}`}
              r={5}
              fill={color}
              opacity={0.75}
              filter={`url(#${uid}glow)`}
            >
              <animateMotion
                dur={`${PARTICLE_DUR}s`}
                repeatCount="indefinite"
                begin={`${(i * PARTICLE_DUR) / PARTICLES}s`}
              >
                <mpath href={`#${uid}trk`} />
              </animateMotion>
            </circle>
          ))}

          {/* Connector segments between stations */}
          {stages.slice(0, -1).map((s, i) => (
            <line
              key={`seg${i}`}
              x1={xPositions[i] + R}
              y1={TRACK_Y}
              x2={xPositions[i + 1] - R}
              y2={TRACK_Y}
              stroke={color}
              strokeWidth={2}
              opacity={0.15}
            />
          ))}

          {/* Station nodes */}
          {stages.map((s, i) => {
            const x = xPositions[i];
            const isFirst = i === 0;
            const isLast = i === stages.length - 1;
            const active = selected === s.id || hovered === s.id;
            const isInterchange = isFirst || isLast;

            return (
              <g
                key={s.id}
                style={{ cursor: "pointer" }}
                onClick={() => toggle(s.id)}
                onMouseEnter={() => setHovered(s.id)}
                onMouseLeave={() => setHovered(null)}
              >
                {/* Pulse ring on first and last */}
                {isInterchange && (
                  <circle
                    cx={x}
                    cy={TRACK_Y}
                    r={R + 5}
                    fill="none"
                    stroke={color}
                    strokeWidth={1.5}
                    opacity={0.3}
                  >
                    <animate
                      attributeName="r"
                      values={`${R + 4};${R + 9};${R + 4}`}
                      dur="2.5s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      values="0.3;0.08;0.3"
                      dur="2.5s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}

                {/* Main circle */}
                <circle
                  cx={x}
                  cy={TRACK_Y}
                  r={R}
                  fill={active ? color : "#fff"}
                  stroke={color}
                  strokeWidth={3}
                  style={{ transition: "fill 0.15s" }}
                />

                {/* Number */}
                <text
                  x={x}
                  y={TRACK_Y + 5}
                  textAnchor="middle"
                  fontSize={14}
                  fontWeight={700}
                  fill={active ? "#fff" : color}
                  fontFamily={FONT}
                  style={{ pointerEvents: "none", transition: "fill 0.15s" }}
                >
                  {s.num}
                </text>

                {/* Label below */}
                <text
                  x={x}
                  y={TRACK_Y + R + 16}
                  textAnchor="middle"
                  fontSize={11}
                  fontWeight={selected === s.id ? 700 : 500}
                  fill={selected === s.id ? color : "#475569"}
                  fontFamily={FONT}
                  style={{ pointerEvents: "none" }}
                >
                  {s.label}
                </text>

                {/* Branch dot */}
                {s.branches && s.branches.length > 0 && (
                  <circle
                    cx={x + R * 0.7}
                    cy={TRACK_Y - R * 0.7}
                    r={5}
                    fill="#F59E0B"
                    stroke="#fff"
                    strokeWidth={1.5}
                    style={{ pointerEvents: "none" }}
                  />
                )}
              </g>
            );
          })}
        </svg>

        {/* Tooltip overlay */}
        {hoveredStage && hovered !== selected && (
          <Box
            sx={{
              position: "absolute",
              left: `${(xPositions[stages.findIndex((s) => s.id === hoveredStage.id)] / VB_W) * 100}%`,
              top: `${((TRACK_Y - R - 14) / VB_H) * 100}%`,
              transform: "translate(-50%, -100%)",
              bgcolor: "rgba(15,23,42,0.92)",
              color: "#fff",
              borderRadius: 2,
              px: 1.75,
              py: 1,
              maxWidth: 260,
              fontSize: 12,
              lineHeight: 1.5,
              pointerEvents: "none",
              zIndex: 10,
              boxShadow: "0 4px 14px rgba(0,0,0,0.25)",
              fontFamily: FONT,
            }}
          >
            {hoveredStage.tooltip}
          </Box>
        )}
      </Box>

      {/* Detail card */}
      <Collapse in={!!selectedStage} unmountOnExit>
        {selectedStage && (
          <DetailCard
            stage={selectedStage}
            color={color}
            lightColor={lightColor}
            trackLabel={trackLabel}
            onClose={() => setSelected(null)}
          />
        )}
      </Collapse>
    </Box>
  );
}

/* ================================================================== */
/*  Detail card                                                        */
/* ================================================================== */

function DetailCard({
  stage,
  color,
  lightColor,
  trackLabel,
  onClose,
}: {
  stage: TabStage;
  color: string;
  lightColor: string;
  trackLabel: string;
  onClose: () => void;
}) {
  return (
    <Card
      variant="outlined"
      sx={{ mt: 2, borderColor: color, borderWidth: 2 }}
    >
      <CardContent sx={{ p: 3, "&:last-child": { pb: 3 } }}>
        {/* Header */}
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="flex-start"
        >
          <Stack
            direction="row"
            spacing={1.5}
            alignItems="center"
            sx={{ mb: 2 }}
          >
            <Box
              sx={{
                width: 38,
                height: 38,
                borderRadius: "50%",
                bgcolor: color,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Typography sx={{ color: "#fff", fontWeight: 700, fontSize: 16 }}>
                {stage.num}
              </Typography>
            </Box>
            <Box>
              <Typography variant="h6" sx={{ lineHeight: 1.2 }}>
                {stage.label}
              </Typography>
              <Chip
                size="small"
                label={trackLabel}
                sx={{
                  mt: 0.5,
                  bgcolor: lightColor,
                  color: color,
                  fontWeight: 600,
                }}
              />
            </Box>
          </Stack>
          <IconButton aria-label="Close" size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>

        {/* Description */}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          {stage.tooltip}
        </Typography>

        {/* In / Out */}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={3}>
          <Box sx={{ flex: 1, pl: 2, borderLeft: 3, borderColor: "success.main" }}>
            <Typography
              variant="subtitle2"
              sx={{ color: "success.main", mb: 0.5 }}
            >
              What goes in
            </Typography>
            <Typography variant="body2">{stage.detailIn}</Typography>
          </Box>
          <Box sx={{ flex: 1, pl: 2, borderLeft: 3, borderColor: "primary.main" }}>
            <Typography
              variant="subtitle2"
              sx={{ color: "primary.main", mb: 0.5 }}
            >
              What comes out
            </Typography>
            <Typography variant="body2">{stage.detailOut}</Typography>
          </Box>
        </Stack>

        {/* Branches */}
        {stage.branches && stage.branches.length > 0 && (
          <Box
            sx={{
              mt: 2.5,
              p: 2,
              bgcolor: "#FFFBEB",
              borderRadius: 2,
              border: "1px solid #FDE68A",
            }}
          >
            <Typography
              variant="subtitle2"
              sx={{ color: "#92400E", mb: 0.75 }}
            >
              What could happen differently
            </Typography>
            {stage.branches.map((b) => (
              <Typography
                key={b.label}
                variant="body2"
                sx={{ color: "#78350F", mb: 0.5 }}
              >
                <strong>{b.label}:</strong> {b.description}
              </Typography>
            ))}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
