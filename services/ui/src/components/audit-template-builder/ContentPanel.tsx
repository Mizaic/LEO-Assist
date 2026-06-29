"use client";

/**
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 *
 * "Content" tab: Canva-style blocks for titles, text, dividers,
 * callouts, banners, images, links, and manual KPI cards.
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";

// Icons
import TitleIcon from "@mui/icons-material/Title";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import SubtitlesOutlinedIcon from "@mui/icons-material/SubtitlesOutlined";
import HorizontalRuleIcon from "@mui/icons-material/HorizontalRule";
import SpaceBarIcon from "@mui/icons-material/SpaceBar";
import CropLandscapeOutlinedIcon from "@mui/icons-material/CropLandscapeOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import NumbersIcon from "@mui/icons-material/Numbers";
import LabelOutlinedIcon from "@mui/icons-material/LabelOutlined";

import { CONTENT_CATALOGUE, CONTENT_GROUPS, type ContentBlockEntry } from "@/lib/contentBlocks";

// ---------------------------------------------------------------------------
// Icon map
// ---------------------------------------------------------------------------

const BLOCK_ICONS: Record<string, React.ElementType> = {
  "content-heading":       TitleIcon,
  "content-subheading":    SubtitlesOutlinedIcon,
  "content-body":          TextFieldsIcon,
  "content-callout":       InfoOutlinedIcon,
  "content-label":         LabelOutlinedIcon,
  "content-divider":       HorizontalRuleIcon,
  "content-spacer":        SpaceBarIcon,
  "content-banner":        CropLandscapeOutlinedIcon,
  "content-image":         ImageOutlinedIcon,
  "content-link":          LinkOutlinedIcon,
  "content-metric-card":   NumbersIcon,
};

// ---------------------------------------------------------------------------
// BlockButton -- a single content block add button
// ---------------------------------------------------------------------------

function BlockButton({ block, onAdd }: { block: ContentBlockEntry; onAdd: () => void }) {
  const Icon = BLOCK_ICONS[block.block_id] ?? TextFieldsIcon;
  return (
    <Tooltip title={block.description} placement="right">
      <Box
        component="button"
        onClick={onAdd}
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 0.5,
          p: 1,
          border: "1px solid",
          borderColor: `${block.colour}30`,
          borderRadius: 2,
          bgcolor: `${block.colour}08`,
          cursor: "pointer",
          transition: "all 120ms",
          "&:hover": {
            bgcolor: `${block.colour}18`,
            borderColor: block.colour,
            transform: "translateY(-1px)",
            boxShadow: `0 2px 8px ${block.colour}20`,
          },
          "&:active": { transform: "none" },
        }}
      >
        <Icon sx={{ fontSize: 18, color: block.colour }} />
        <Typography sx={{ fontSize: 10, fontWeight: 600, color: block.colour, lineHeight: 1.2, textAlign: "center" }}>
          {block.label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// ContentPanel
// ---------------------------------------------------------------------------

interface ContentPanelProps {
  onAddContent: (block: ContentBlockEntry) => void;
}

export default function ContentPanel({ onAddContent }: ContentPanelProps) {
  const [activeGroup, setActiveGroup] = useState<string>("text");

  const visibleBlocks = CONTENT_CATALOGUE.filter((b) => b.group === activeGroup);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Group filter tabs */}
      <Box sx={{ display: "flex", borderBottom: "1px solid", borderColor: "divider", px: 1 }}>
        {CONTENT_GROUPS.map((g) => (
          <Box
            key={g.id}
            component="button"
            onClick={() => setActiveGroup(g.id)}
            sx={{
              flex: 1,
              py: 0.75,
              fontSize: 10,
              fontWeight: activeGroup === g.id ? 700 : 400,
              color: activeGroup === g.id ? "primary.main" : "text.secondary",
              borderBottom: activeGroup === g.id ? "2px solid" : "2px solid transparent",
              borderColor: activeGroup === g.id ? "primary.main" : "transparent",
              bgcolor: "transparent",
              cursor: "pointer",
              transition: "all 120ms",
              "&:hover": { color: "primary.main" },
            }}
          >
            {g.label}
          </Box>
        ))}
      </Box>

      {/* Block grid */}
      <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: 1,
          }}
        >
          {visibleBlocks.map((block) => (
            <BlockButton key={block.block_id} block={block} onAdd={() => onAddContent(block)} />
          ))}
        </Box>

        {/* Usage hint */}
        <Typography variant="caption" color="text.disabled" sx={{ display: "block", textAlign: "center", mt: 2, lineHeight: 1.5 }}>
          Click to add. Select a tile to edit its text inline.
        </Typography>
      </Box>
    </Box>
  );
}
