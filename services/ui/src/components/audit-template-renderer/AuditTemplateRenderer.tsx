"use client";

/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-758B73A5
 */

import { useMemo, useState } from "react";
import { AnimatePresence, motion as fm, useReducedMotion } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import SlideshowOutlinedIcon from "@mui/icons-material/SlideshowOutlined";

import {
  type AuditTemplate,
  type MetricCatalogueEntry,
  type MetricRunResult,
} from "@/lib/auditTemplateApi";
import { generateMockData } from "@/lib/auditMockData";
import MetricTile from "./MetricTile";
import PresentationMode from "./PresentationMode";
import WidgetTile from "./WidgetTile";

interface AuditTemplateRendererProps {
  template: AuditTemplate;
  orgId: string;
  useMockData?: boolean;
  catalogue?: MetricCatalogueEntry[];
}

const WIDE_TYPES = new Set(["table", "interval_plot", "text", "widget"]);

function groupBySection(template: AuditTemplate) {
  const groups: Record<string, typeof template.tiles> = {};
  for (const tile of template.tiles) {
    const key = tile.section?.trim() || "General";
    if (!groups[key]) groups[key] = [];
    groups[key].push(tile);
  }
  return groups;
}

function MockBadge() {
  return (
    <Chip
      label="Mock data"
      size="small"
      color="warning"
      variant="outlined"
      sx={{ fontSize: 10 }}
    />
  );
}

// Shared item variant for stagger children
const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.22, ease: "easeOut" } },
};

const MotionBox = fm(Box);

export default function AuditTemplateRenderer({
  template,
  orgId,
  useMockData = false,
  catalogue = [],
}: AuditTemplateRendererProps) {
  const reduced = useReducedMotion();
  const [presentationOpen, setPresentationOpen] = useState(false);
  const sections = groupBySection(template);

  const mockDataMap = useMemo<Map<string, MetricRunResult>>(() => {
    if (!useMockData || catalogue.length === 0) return new Map();
    const map = new Map<string, MetricRunResult>();
    for (const entry of catalogue) {
      map.set(entry.metric_id, generateMockData(entry));
    }
    return map;
  }, [useMockData, catalogue]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {/* Report header */}
      <Box
        sx={{
          pb: 2,
          borderBottom: "2px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 1,
        }}
      >
        <Box>
          <Typography variant="h5" fontWeight={700} component="h1">
            {template.title}
          </Typography>
          <Box sx={{ display: "flex", gap: 1, mt: 0.75, flexWrap: "wrap" }}>
            <Chip
              label={`v${template.version}`}
              size="small"
              variant="outlined"
              sx={{ fontSize: 11 }}
            />
            <Chip
              label={template.status}
              size="small"
              color={template.status === "published" ? "success" : "default"}
              sx={{ fontSize: 11, textTransform: "capitalize" }}
            />
            {useMockData && <MockBadge />}
          </Box>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="caption" color="text.secondary">
            {new Date().toLocaleDateString("en-GB", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </Typography>
          <Button
            size="small"
            variant="outlined"
            startIcon={<SlideshowOutlinedIcon />}
            onClick={() => setPresentationOpen(true)}
          >
            Present
          </Button>
        </Box>
      </Box>

      {/* Sections */}
      {Object.entries(sections).map(([sectionLabel, tiles]) => (
        <Box key={sectionLabel}>
          <MotionBox
            initial={reduced ? false : { opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduced ? 0 : 0.2 }}
            sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}
          >
            <Typography variant="subtitle1" fontWeight={700} color="text.primary">
              {sectionLabel}
            </Typography>
            <Divider sx={{ flex: 1 }} />
            <Typography variant="caption" color="text.disabled">
              {tiles.length} {tiles.length === 1 ? "tile" : "tiles"}
            </Typography>
          </MotionBox>

          <MotionBox
            key={sectionLabel}
            variants={reduced ? {} : { hidden: {}, visible: { transition: { staggerChildren: 0.06 } } }}
            initial="hidden"
            animate="visible"
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(3, 1fr)" },
              gap: 2,
            }}
          >
            {tiles.map((tile) => (
              <MotionBox
                key={tile.tile_id}
                variants={reduced ? {} : itemVariants}
                sx={{
                  gridColumn: WIDE_TYPES.has(tile.tile_type)
                    ? { sm: "span 2", lg: "span 3" }
                    : undefined,
                }}
              >
                {tile.tile_type === "widget" ? (
                  <WidgetTile tile={tile} orgId={orgId} />
                ) : (
                  <MetricTile
                    tile={tile}
                    orgId={orgId}
                    mockData={mockDataMap.get(tile.metric_id)}
                  />
                )}
              </MotionBox>
            ))}
          </MotionBox>
        </Box>
      ))}

      {template.tiles.length === 0 && (
        <Typography
          variant="body2"
          color="text.disabled"
          sx={{ textAlign: "center", py: 6 }}
        >
          No metrics added to this template yet.
        </Typography>
      )}

      <AnimatePresence>
        {presentationOpen && (
          <fm.div
            key="presentation"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduced ? 0 : 0.15 }}
          >
            <PresentationMode
              template={template}
              orgId={orgId}
              onClose={() => setPresentationOpen(false)}
            />
          </fm.div>
        )}
      </AnimatePresence>
    </Box>
  );
}
