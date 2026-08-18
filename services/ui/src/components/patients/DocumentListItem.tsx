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
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import type { DocumentRow } from "@/lib/patientEprApi";
import { DocumentAiReadyChip } from "./DocumentAiReadyChip";
import {
  categoryLabel,
  fileKindLabel,
  inferFileKind,
  type DocumentFileKind,
} from "./documentFormat";

function fmt(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function FileIcon({ kind }: { kind: DocumentFileKind }) {
  if (kind === "pdf") {
    return (
      <PictureAsPdfOutlinedIcon sx={{ fontSize: 18, color: "#B91C1C", flexShrink: 0 }} />
    );
  }
  if (kind === "word") {
    return (
      <DescriptionOutlinedIcon sx={{ fontSize: 18, color: "#002178", flexShrink: 0 }} />
    );
  }
  return <ArticleOutlinedIcon sx={{ fontSize: 18, color: "#64748B", flexShrink: 0 }} />;
}

interface Props {
  doc: DocumentRow;
  selected: boolean;
  onSelect: () => void;
}

export function DocListItem({ doc, selected, onSelect }: Props) {
  const kind = inferFileKind(doc);
  const preview = doc.text_preview?.replace(/^--- Document:.*?---\s*/m, "").trim();

  return (
    <Box
      component="button"
      onClick={onSelect}
      aria-pressed={selected}
      sx={{
        display: "block",
        width: "100%",
        textAlign: "left",
        border: "none",
        borderBottom: "1px solid #E2E8F0",
        p: "12px 14px",
        bgcolor: selected ? "#EFF6FF" : "transparent",
        cursor: "pointer",
        "&:hover": { bgcolor: selected ? "#EFF6FF" : "#F8FAFC" },
      }}
    >
      <Stack direction="row" spacing={1.25} alignItems="flex-start">
        <FileIcon kind={kind} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600} noWrap>
            {doc.title}
          </Typography>
          <Stack
            direction="row"
            spacing={0.75}
            alignItems="center"
            flexWrap="wrap"
            sx={{ mt: 0.25 }}
          >
            <Chip label={fileKindLabel(kind)} size="small" sx={{ height: 18, fontSize: 10 }} />
            {doc.category && (
              <Chip
                label={categoryLabel(doc.category)}
                size="small"
                sx={{ height: 18, fontSize: 10, bgcolor: "#F1F5F9" }}
              />
            )}
            <DocumentAiReadyChip chunkCount={doc.chunk_count ?? 0} />
            {doc.document_date && (
              <Typography variant="caption" color="text.secondary">
                {fmt(doc.document_date)}
              </Typography>
            )}
          </Stack>
          {preview && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                display: "block",
                mt: 0.5,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {preview}
            </Typography>
          )}
        </Box>
      </Stack>
    </Box>
  );
}
