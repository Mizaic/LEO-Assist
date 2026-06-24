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

interface AuditTemplateRendererProps {
  template: AuditTemplate;
  orgId: string;
}

function groupBySection(template: AuditTemplate) {
  const groups: Record<string, typeof template.tiles> = {};
  for (const tile of template.tiles) {
    // section is not yet in the type; fall back to "General" for now
    const key = "General";
    if (!groups[key]) groups[key] = [];
    groups[key].push(tile);
  }
  return groups;
}

export default function AuditTemplateRenderer({
  template,
  orgId,
}: AuditTemplateRendererProps) {
  const sections = groupBySection(template);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box>
        <Typography variant="h5" fontWeight={700}>
          {template.title}
        </Typography>
        <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
          <Chip
            label={`v${template.version}`}
            size="small"
            variant="outlined"
          />
          <Chip
            label={template.status}
            size="small"
            color={template.status === "published" ? "success" : "default"}
          />
        </Box>
      </Box>

      {Object.entries(sections).map(([sectionLabel, tiles]) => (
        <Box key={sectionLabel}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
            <Typography variant="h6" fontWeight={600}>
              {sectionLabel}
            </Typography>
            <Divider sx={{ flex: 1 }} />
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
                  gridColumn:
                    tile.tile_type === "table" ||
                    tile.tile_type === "interval_plot" ||
                    tile.tile_type === "text"
                      ? { sm: "span 2", lg: "span 3" }
                      : undefined,
                }}
              >
                <MetricTile tile={tile} orgId={orgId} />
              </Box>
            ))}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
