"use client";

/**
 * Left-side agent palette.
 * Users drag chips from here onto the React Flow canvas to add steps.
 */

import { useCallback } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import SearchIcon from "@mui/icons-material/Search";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import LoopIcon from "@mui/icons-material/Loop";
import { useState } from "react";
import { AGENT_CATALOGUE } from "../agentCatalogue";
import type { AgentDef } from "../types";

const ELECTRIC_BLUE = "#0d46d6";
const VIOLET = "#9338ff";
const AMBIENT = "#0071e2";

function kindColor(def: AgentDef): string {
  if (def.kind === "human") return VIOLET;
  if (def.kind === "ambient") return AMBIENT;
  return ELECTRIC_BLUE;
}

function KindIcon({ def }: { def: AgentDef }) {
  if (def.kind === "human") return <PersonOutlineIcon sx={{ fontSize: 14 }} />;
  if (def.kind === "ambient") return <LoopIcon sx={{ fontSize: 14 }} />;
  return <SmartToyOutlinedIcon sx={{ fontSize: 14 }} />;
}

interface PaletteChipProps {
  def: AgentDef;
}

function PaletteChip({ def }: PaletteChipProps) {
  const color = kindColor(def);

  const onDragStart = useCallback(
    (e: React.DragEvent) => {
      e.dataTransfer.setData(
        "application/leo-agent",
        JSON.stringify({ agentType: def.type, label: def.label, kind: def.kind })
      );
      e.dataTransfer.effectAllowed = "copy";
    },
    [def]
  );

  return (
    <Tooltip title={def.description} placement="right" arrow>
      <Box
        draggable
        onDragStart={onDragStart}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.8,
          px: 1,
          py: 0.7,
          borderRadius: "8px",
          border: `1px solid ${color}33`,
          bgcolor: `${color}0a`,
          cursor: "grab",
          userSelect: "none",
          transition: "background 0.12s, box-shadow 0.12s",
          "&:hover": {
            bgcolor: `${color}18`,
            boxShadow: `0 0 0 2px ${color}33`,
          },
          "&:active": { cursor: "grabbing" },
        }}
      >
        <Box sx={{ color, display: "flex", alignItems: "center" }}>
          <KindIcon def={def} />
        </Box>
        <Typography sx={{ fontSize: "0.76rem", fontWeight: 600, color: "#1a2233", lineHeight: 1.3 }}>
          {def.label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

export function AgentPalette() {
  const [search, setSearch] = useState("");

  const filtered = AGENT_CATALOGUE.filter(
    (a) =>
      !search ||
      a.label.toLowerCase().includes(search.toLowerCase()) ||
      a.description.toLowerCase().includes(search.toLowerCase())
  );

  const agents = filtered.filter((a) => a.kind === "agent");
  const humans = filtered.filter((a) => a.kind === "human");
  const ambient = filtered.filter((a) => a.kind === "ambient");

  return (
    <Box
      sx={{
        width: 224,
        flexShrink: 0,
        height: "100%",
        overflowY: "auto",
        borderRight: "1px solid #e2e8f0",
        bgcolor: "#f8fafc",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <Box sx={{ px: 1.5, pt: 1.5, pb: 1 }}>
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            fontSize: "0.68rem",
            color: "#6b7280",
            textTransform: "uppercase",
            letterSpacing: 0.6,
          }}
        >
          Steps -- drag to add
        </Typography>
        <TextField
          size="small"
          fullWidth
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ mt: 1 }}
          inputProps={{ "aria-label": "Search agents" }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon sx={{ fontSize: 16, color: "#94a3b8" }} />
              </InputAdornment>
            ),
          }}
        />
      </Box>

      {/* Sections */}
      <Box sx={{ px: 1, pb: 2, flex: 1 }}>
        {agents.length > 0 && (
          <PaletteSection label="AI Agents" items={agents} />
        )}
        {humans.length > 0 && (
          <PaletteSection label="Human Gates" items={humans} />
        )}
        {ambient.length > 0 && (
          <PaletteSection label="Scheduled / Ambient" items={ambient} />
        )}
        {filtered.length === 0 && (
          <Typography variant="caption" sx={{ color: "#94a3b8", px: 0.5 }}>
            No agents match your search.
          </Typography>
        )}
      </Box>
    </Box>
  );
}

function PaletteSection({ label, items }: { label: string; items: AgentDef[] }) {
  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          fontSize: "0.63rem",
          color: "#94a3b8",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          px: 0.5,
          display: "block",
          mb: 0.5,
        }}
      >
        {label}
      </Typography>
      <Stack spacing={0.4}>
        {items.map((def) => (
          <PaletteChip key={def.type} def={def} />
        ))}
      </Stack>
    </Box>
  );
}
