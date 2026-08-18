/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import type { DocumentRow } from "@/lib/patientEprApi";
import { DocListItem } from "./DocumentListItem";

interface Props {
  label: string;
  docs: DocumentRow[];
  accent: string;
  expanded: boolean;
  selectedId: string | null;
  onToggle: () => void;
  onSelect: (id: string) => void;
}

export function DocumentFolderBlock({
  label,
  docs,
  accent,
  expanded,
  selectedId,
  onToggle,
  onSelect,
}: Props) {
  const panelId = `doc-folder-${label.replace(/\s+/g, "-").toLowerCase()}`;

  return (
    <Box sx={{ mb: 0.5 }}>
      <Box
        component="button"
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        sx={{
          display: "block",
          width: "100%",
          border: "none",
          cursor: "pointer",
          position: "sticky",
          top: 0,
          zIndex: 2,
          bgcolor: "#F8FAFC",
          borderLeft: `3px solid ${accent}`,
          px: 1,
          py: 0.75,
          mb: 0.25,
          textAlign: "left",
          "&:hover": { bgcolor: "#F1F5F9" },
        }}
      >
        <Stack direction="row" spacing={0.5} alignItems="center">
          <ExpandMoreIcon
            aria-hidden
            sx={{
              fontSize: 18,
              color: accent,
              transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 0.15s ease",
            }}
          />
          <FolderOutlinedIcon sx={{ fontSize: 15, color: accent }} />
          <Typography
            variant="caption"
            fontWeight={700}
            color={accent}
            sx={{ textTransform: "capitalize", flex: 1 }}
          >
            {label}
          </Typography>
          <Chip label={String(docs.length)} size="small" sx={{ height: 16, fontSize: 10 }} />
        </Stack>
      </Box>
      <Collapse in={expanded} timeout="auto">
        <Box id={panelId}>
          {docs.map((d) => (
            <DocListItem
              key={d.document_id}
              doc={d}
              selected={selectedId === d.document_id}
              onSelect={() => onSelect(d.document_id)}
            />
          ))}
        </Box>
      </Collapse>
    </Box>
  );
}
