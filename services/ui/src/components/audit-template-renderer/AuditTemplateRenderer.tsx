"use client";

/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-758B73A5
 */

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import Chip from "@mui/material/Chip";

import { type AuditTemplate } from "@/lib/auditTemplateApi";
import MetricTile from "./MetricTile";
import WidgetTile from "./WidgetTile";

interface AuditTemplateRendererProps {
  template: AuditTemplate;
  orgId: string;
}

function groupBySection(template: AuditTemplate) {
  const groups: Record<string, typeof template.tiles> = {};
  for (const tile of template.tiles) {
    const key = tile.section?.trim() || "General";
    if (!groups[key]) groups[key] = [];
    groups[key].push(tile);
  }
  return groups;
}

const WIDE_TYPES = new Set(["table", "interval_plot", "text", "widget"]);

export default function AuditTemplateRenderer({
  template,
  orgId,
}: AuditTemplateRendererProps) {
  const sections = groupBySection(template);

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
          </Box>
        </Box>
        <Typography variant="caption" color="text.secondary">
          {new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}
        </Typography>
      </Box>

      {/* Sections */}
      {Object.entries(sections).map(([sectionLabel, tiles]) => (
        <Box key={sectionLabel}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
            <Typography variant="subtitle1" fontWeight={700} color="text.primary">
              {sectionLabel}
            </Typography>
            <Divider sx={{ flex: 1 }} />
            <Typography variant="caption" color="text.disabled">
              {tiles.length} {tiles.length === 1 ? "tile" : "tiles"}
            </Typography>
          </Box>

          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: {
                xs: "1fr",
                sm: "1fr 1fr",
                lg: "repeat(3, 1fr)",
              },
              gap: 2,
            }}
          >
            {tiles.map((tile) => (
              <Box
                key={tile.tile_id}
                sx={{
                  gridColumn: WIDE_TYPES.has(tile.tile_type)
                    ? { sm: "span 2", lg: "span 3" }
                    : undefined,
                }}
              >
                {tile.tile_type === "widget" ? (
                  <WidgetTile tile={tile} orgId={orgId} />
                ) : (
                  <MetricTile tile={tile} orgId={orgId} />
                )}
              </Box>
            ))}
          </Box>
        </Box>
      ))}

      {template.tiles.length === 0 && (
        <Typography variant="body2" color="text.disabled" sx={{ textAlign: "center", py: 6 }}>
          No metrics added to this template yet.
        </Typography>
      )}
    </Box>
  );
}
