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

interface Branch {
  label: string;
  description: string;
}

interface Stage {
  id: string;
  line: LineKey;
  num: number;
  label: string;
  tooltip: string;
  detailIn: string;
  detailOut: string;
  branches?: Branch[];
}

interface Connection {
  id: string;
  path: string;
  label: string;
  labelX: number;
  labelY: number;
  dashed?: boolean;
}

/* ================================================================== */
/*  Palette & layout                                                   */
/* ================================================================== */

const LINE_META = {
  coding: {
    main: "#3B5FD9",
    light: "#DBEAFE",
    label: "Reading the Notes",
  },
  analysis: {
    main: "#14B8A6",
    light: "#CCFBF1",
    label: "Understanding the Story",
  },
  training: {
    main: "#7C3AED",
    light: "#EDE9FE",
    label: "Teaching the AI",
  },
} as const;

type LineKey = keyof typeof LINE_META;
const LINE_KEYS = Object.keys(LINE_META) as LineKey[];

const COL: Record<LineKey, number> = { coding: 155, analysis: 480, training: 805 };
const ROWS = [75, 160, 245, 330, 415];
const R = 22;
const VB_W = 960;
const VB_H = 550;
const FONT = "'DM Sans',system-ui,sans-serif";

const INTERCHANGE = new Set(["c2", "c5", "a1", "a5", "t1", "t5"]);

/* ================================================================== */
/*  Stage definitions (plain English for reading‑age 11)               */
/* ================================================================== */

const STAGES: Stage[] = [
  /* ── Coding pipeline ── */
  {
    id: "c1", line: "coding", num: 1,
    label: "Sort the Notes",
    tooltip:
      "The computer reads each note and decides: is this about health, or just admin?",
    detailIn: "Patient notes from the database",
    detailOut: "Health notes go forward; admin notes are set aside",
    branches: [
      {
        label: "Admin or transfer notes",
        description:
          "These are set aside — they don't need medical coding",
      },
    ],
  },
  {
    id: "c2", line: "coding", num: 2,
    label: "Find Medical Words",
    tooltip:
      "The AI reads the health notes and picks out important medical words like 'asthma' or 'blood pressure'.",
    detailIn: "Health notes (text)",
    detailOut: "A list of medical words with what they mean",
    branches: [
      {
        label: "LLM (large language model)",
        description:
          "A powerful cloud AI reads the notes — always available",
      },
      {
        label: "Trained NER model",
        description:
          "A smaller AI trained on human‑reviewed examples — faster and cheaper",
      },
      {
        label: "Auto mode",
        description:
          "Tries the trained model first; falls back to the LLM if needed",
      },
    ],
  },
  {
    id: "c3", line: "coding", num: 3,
    label: "Tidy Up",
    tooltip:
      "We clean up the list — fix mistakes, add missing details, and check the context.",
    detailIn: "Raw list of medical words",
    detailOut: "A neat, checked list of medical words",
  },
  {
    id: "c4", line: "coding", num: 4,
    label: "Match to Codes",
    tooltip:
      "Every medical word gets matched to its official SNOMED code, so computers everywhere understand it.",
    detailIn: "Medical words",
    detailOut: "Words paired with their official SNOMED codes",
  },
  {
    id: "c5", line: "coding", num: 5,
    label: "Save Everything",
    tooltip: "All the coded information is saved to the database.",
    detailIn: "Coded medical words",
    detailOut: "Stored safely in the database",
    branches: [
      {
        label: "Preview mode (dry run)",
        description:
          "If preview is turned on, we show results but don't actually save anything",
      },
    ],
  },

  /* ── Analysis pipeline ── */
  {
    id: "a1", line: "analysis", num: 1,
    label: "Find Key Dates",
    tooltip:
      "We look for key moments — like when a patient was referred or started treatment.",
    detailIn: "Coded data stored in the database",
    detailOut: "A timeline of key dates (referrals, diagnoses, treatments)",
  },
  {
    id: "a2", line: "analysis", num: 2,
    label: "Build the Story",
    tooltip:
      "We connect the dates to build a picture of the patient's care journey.",
    detailIn: "Key dates and related visits",
    detailOut: "A care episode — the patient's full pathway",
    branches: [
      {
        label: "No referral found",
        description:
          "We try to build the story from diagnosis or treatment dates instead",
      },
      {
        label: "Unclear result",
        description:
          "Two AI models vote; if they disagree, a human checks",
      },
    ],
  },
  {
    id: "a3", line: "analysis", num: 3,
    label: "Check for Safety",
    tooltip:
      "We check: was anything missed? Did the patient wait too long?",
    detailIn: "The care episode",
    detailOut: "Safety warnings if something looks wrong",
  },
  {
    id: "a4", line: "analysis", num: 4,
    label: "Spot Odd Results",
    tooltip: "We flag any test results that look unusual or worrying.",
    detailIn: "Test results from the episode",
    detailOut: "A list of flagged results that need attention",
  },
  {
    id: "a5", line: "analysis", num: 5,
    label: "Work Out Scores",
    tooltip:
      "We calculate how well the care went — like a report card for the pathway.",
    detailIn: "The episode, warnings, and flagged results",
    detailOut: "Performance scores for the care pathway",
  },

  /* ── Training pipeline ── */
  {
    id: "t1", line: "training", num: 1,
    label: "Gather Reviews",
    tooltip:
      "We collect all the examples that humans have checked and approved.",
    detailIn: "Approved labels from human reviewers",
    detailOut: "A training dataset (lots of correct examples)",
    branches: [
      {
        label: "Not enough examples",
        description:
          "If fewer than 50 reviewed examples exist, training can't start yet",
      },
    ],
  },
  {
    id: "t2", line: "training", num: 2,
    label: "Teach the AI",
    tooltip:
      "We show the AI thousands of correct examples so it can learn the patterns.",
    detailIn: "Training dataset",
    detailOut: "A freshly trained AI model",
    branches: [
      {
        label: "Hardware retry",
        description:
          "If training fails on a fast GPU, we retry on slower hardware — up to 4 attempts",
      },
    ],
  },
  {
    id: "t3", line: "training", num: 3,
    label: "Test the AI",
    tooltip:
      "We give the AI a quiz to make sure it learned well enough.",
    detailIn: "Trained model + test examples it hasn't seen before",
    detailOut:
      "A score — the AI must get at least 80% precision and 75% recall to pass",
    branches: [
      {
        label: "Failed the test",
        description:
          "If the AI doesn't score high enough, we stop here — it won't be used",
      },
    ],
  },
  {
    id: "t4", line: "training", num: 4,
    label: "Upload New AI",
    tooltip: "We save the improved AI so it's ready to use.",
    detailIn: "The AI model that passed the test",
    detailOut: "Model stored safely in the cloud",
  },
  {
    id: "t5", line: "training", num: 5,
    label: "Switch It On",
    tooltip:
      "We register the new AI and make it available for the pipeline to use.",
    detailIn: "Uploaded model in the cloud",
    detailOut: "Model is live and ready to find medical words",
  },
];

/* ================================================================== */
/*  Cross‑connections between pipelines                                */
/* ================================================================== */

const CONNECTIONS: Connection[] = [
  {
    id: "c5a1",
    path: `M 155 ${415 + R} C 155 500, 480 500, 480 ${75 - R}`,
    label: "Triggers analysis",
    labelX: 320,
    labelY: 495,
  },
  {
    id: "a5t1",
    path: `M 480 ${415 + R} C 480 505, 805 505, 805 ${75 - R}`,
    label: "Human review \u2192 training",
    labelX: 645,
    labelY: 500,
  },
  {
    id: "t5c2",
    path: `M 805 ${415 + R} C 805 535, 155 535, 155 ${160 + R}`,
    label: "Improved AI feeds back",
    labelX: 480,
    labelY: 530,
    dashed: true,
  },
];

/* ================================================================== */
/*  Helpers                                                            */
/* ================================================================== */

function trackD(line: LineKey): string {
  return `M ${COL[line]} ${ROWS[0]} L ${COL[line]} ${ROWS[4]}`;
}

const TRACK_PARTICLES = 3;
const TRACK_DUR = 4;
const CONN_DUR = 6;

const HEADER_W: Record<LineKey, number> = {
  coding: 155,
  analysis: 195,
  training: 150,
};

/* ================================================================== */
/*  Component                                                          */
/* ================================================================== */

export default function PipelineOverviewDiagram() {
  const rawId = useId();
  const uid = rawId.replace(/:/g, "");
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const selectedStage = STAGES.find((s) => s.id === selected) ?? null;
  const hoveredStage = STAGES.find((s) => s.id === hovered) ?? null;

  const toggle = (id: string) =>
    setSelected((prev) => (prev === id ? null : id));

  return (
    <Box>
      {/* ── Legend ── */}
      <Stack
        direction="row"
        spacing={2}
        sx={{ mb: 1, flexWrap: "wrap" }}
        alignItems="center"
      >
        {LINE_KEYS.map((k) => (
          <Stack key={k} direction="row" spacing={0.75} alignItems="center">
            <Box
              sx={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                bgcolor: LINE_META[k].main,
              }}
            />
            <Typography
              variant="caption"
              sx={{ fontWeight: 600, color: "text.secondary" }}
            >
              {LINE_META[k].label}
            </Typography>
          </Stack>
        ))}
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ ml: "auto !important" }}
        >
          Click any station to learn more
        </Typography>
      </Stack>

      {/* ── SVG diagram ── */}
      <Box sx={{ position: "relative", width: "100%" }}>
        <svg
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          width="100%"
          style={{ display: "block" }}
        >
          {/* ── Defs ── */}
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
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#94a3b8" />
            </marker>
          </defs>

          {/* ── Column headers ── */}
          {LINE_KEYS.map((k) => {
            const w = HEADER_W[k];
            return (
              <g key={`hdr-${k}`}>
                <rect
                  x={COL[k] - w / 2}
                  y={10}
                  width={w}
                  height={28}
                  rx={14}
                  fill={LINE_META[k].light}
                />
                <text
                  x={COL[k]}
                  y={29}
                  textAnchor="middle"
                  fontSize={11.5}
                  fontWeight={600}
                  fill={LINE_META[k].main}
                  fontFamily={FONT}
                >
                  {LINE_META[k].label}
                </text>
              </g>
            );
          })}

          {/* ── Track lines (behind everything) ── */}
          {LINE_KEYS.map((k) => (
            <path
              key={`trk-${k}`}
              id={`${uid}trk${k}`}
              d={trackD(k)}
              stroke={LINE_META[k].main}
              strokeWidth={4}
              strokeLinecap="round"
              fill="none"
              opacity={0.2}
            />
          ))}

          {/* ── Cross‑connection arcs ── */}
          {CONNECTIONS.map((c) => (
            <g key={c.id}>
              <path
                id={`${uid}cn${c.id}`}
                d={c.path}
                stroke="#94a3b8"
                strokeWidth={2}
                strokeDasharray={c.dashed ? "8 5" : "6 4"}
                fill="none"
                opacity={0.5}
                markerEnd={`url(#${uid}arr)`}
              />
              <text
                x={c.labelX}
                y={c.labelY}
                textAnchor="middle"
                fontSize={10}
                fill="#94a3b8"
                fontFamily={FONT}
                fontWeight={500}
              >
                {c.label}
              </text>
            </g>
          ))}

          {/* ── Particles on tracks ── */}
          {LINE_KEYS.flatMap((k) =>
            Array.from({ length: TRACK_PARTICLES }, (_, i) => (
              <circle
                key={`tp-${k}-${i}`}
                r={5}
                fill={LINE_META[k].main}
                opacity={0.75}
                filter={`url(#${uid}glow)`}
              >
                <animateMotion
                  dur={`${TRACK_DUR}s`}
                  repeatCount="indefinite"
                  begin={`${(i * TRACK_DUR) / TRACK_PARTICLES}s`}
                >
                  <mpath href={`#${uid}trk${k}`} />
                </animateMotion>
              </circle>
            )),
          )}

          {/* ── Particles on cross‑connections ── */}
          {CONNECTIONS.map((c) => (
            <circle
              key={`cp-${c.id}`}
              r={4}
              fill="#94a3b8"
              opacity={0.45}
              filter={`url(#${uid}glow)`}
            >
              <animateMotion dur={`${CONN_DUR}s`} repeatCount="indefinite">
                <mpath href={`#${uid}cn${c.id}`} />
              </animateMotion>
            </circle>
          ))}

          {/* ── Station nodes ── */}
          {STAGES.map((s) => {
            const x = COL[s.line];
            const y = ROWS[s.num - 1];
            const color = LINE_META[s.line].main;
            const active = selected === s.id || hovered === s.id;

            return (
              <g
                key={s.id}
                style={{ cursor: "pointer" }}
                onClick={() => toggle(s.id)}
                onMouseEnter={() => setHovered(s.id)}
                onMouseLeave={() => setHovered(null)}
              >
                {/* Interchange pulse ring */}
                {INTERCHANGE.has(s.id) && (
                  <circle
                    cx={x}
                    cy={y}
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
                  cy={y}
                  r={R}
                  fill={active ? color : "#fff"}
                  stroke={color}
                  strokeWidth={3}
                  style={{ transition: "fill 0.15s" }}
                />

                {/* Number label */}
                <text
                  x={x}
                  y={y + 5}
                  textAnchor="middle"
                  fontSize={14}
                  fontWeight={700}
                  fill={active ? "#fff" : color}
                  fontFamily={FONT}
                  style={{ pointerEvents: "none", transition: "fill 0.15s" }}
                >
                  {s.num}
                </text>

                {/* Station name below circle */}
                <text
                  x={x}
                  y={y + R + 16}
                  textAnchor="middle"
                  fontSize={11}
                  fontWeight={selected === s.id ? 700 : 500}
                  fill={selected === s.id ? color : "#475569"}
                  fontFamily={FONT}
                  style={{ pointerEvents: "none" }}
                >
                  {s.label}
                </text>

                {/* Branch indicator dot */}
                {s.branches && s.branches.length > 0 && (
                  <circle
                    cx={x + R * 0.7}
                    cy={y - R * 0.7}
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

        {/* ── Tooltip (HTML overlay) ── */}
        {hoveredStage && hovered !== selected && (
          <Box
            sx={{
              position: "absolute",
              left: `${(COL[hoveredStage.line] / VB_W) * 100}%`,
              top: `${((ROWS[hoveredStage.num - 1] - R - 14) / VB_H) * 100}%`,
              transform: "translate(-50%, -100%)",
              bgcolor: "rgba(15,23,42,0.92)",
              color: "#fff",
              borderRadius: 2,
              px: 1.75,
              py: 1,
              maxWidth: 280,
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

      {/* ── Detail panel ── */}
      <Collapse in={!!selectedStage} unmountOnExit>
        {selectedStage && (
          <DetailCard
            stage={selectedStage}
            onClose={() => setSelected(null)}
          />
        )}
      </Collapse>
    </Box>
  );
}

/* ================================================================== */
/*  Detail card (extracted for readability)                            */
/* ================================================================== */

function DetailCard({
  stage,
  onClose,
}: {
  stage: Stage;
  onClose: () => void;
}) {
  const meta = LINE_META[stage.line];
  return (
    <Card
      variant="outlined"
      sx={{
        mt: 2,
        borderColor: meta.main,
        borderWidth: 2,
        animation: "cardIn 0.25s ease",
      }}
    >
      <CardContent sx={{ p: 3, "&:last-child": { pb: 3 } }}>
        {/* Header */}
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="flex-start"
        >
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
            <Box
              sx={{
                width: 38,
                height: 38,
                borderRadius: "50%",
                bgcolor: meta.main,
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
                label={meta.label}
                sx={{
                  mt: 0.5,
                  bgcolor: meta.light,
                  color: meta.main,
                  fontWeight: 600,
                }}
              />
            </Box>
          </Stack>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>

        {/* Description */}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          {stage.tooltip}
        </Typography>

        {/* In / Out */}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={3}>
          <Box
            sx={{
              flex: 1,
              pl: 2,
              borderLeft: 3,
              borderColor: "success.main",
            }}
          >
            <Typography
              variant="subtitle2"
              sx={{ color: "success.main", mb: 0.5 }}
            >
              What goes in
            </Typography>
            <Typography variant="body2">{stage.detailIn}</Typography>
          </Box>
          <Box
            sx={{
              flex: 1,
              pl: 2,
              borderLeft: 3,
              borderColor: "primary.main",
            }}
          >
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
