/**
 * DocumentListPanel -- split-pane clinical document browser.
 *
 * Left: filing-cabinet list grouped by episode, with file-type icons.
 * Right: rendered letter / PDF link viewer (DocumentViewer).
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import type { DocumentRow } from "@/lib/patientEprApi";
import { fetchEprAssessments, fetchEprDocuments } from "@/lib/patientEprApi";
import { DocumentViewer } from "./DocumentViewer";
import {
  categoryLabel,
  fileKindLabel,
  inferFileKind,
  isSbarDocument,
  mergeDocumentsNewestFirst,
  type DocumentFileKind,
} from "./documentFormat";

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#1E40AF",
  breast: "#9D174D",
  prostate: "#6D28D9",
  colorectal: "#B45309",
  lower_gi: "#B45309",
  upper_gi: "#7C3AED",
  skin: "#047857",
  haematology: "#0369A1",
  gynaecology: "#BE185D",
  head_and_neck: "#1D4ED8",
  urology: "#4338CA",
};

function accentForLabel(label: string): string {
  const key = label.toLowerCase().split(" ")[0].replace(/-/g, "_");
  return CONDITION_ACCENT[key] ?? "#475569";
}

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
    return <PictureAsPdfOutlinedIcon sx={{ fontSize: 18, color: "#B91C1C", flexShrink: 0 }} />;
  }
  if (kind === "word") {
    return <DescriptionOutlinedIcon sx={{ fontSize: 18, color: "#1E40AF", flexShrink: 0 }} />;
  }
  return <ArticleOutlinedIcon sx={{ fontSize: 18, color: "#64748B", flexShrink: 0 }} />;
}

function DocListItem({
  doc,
  selected,
  onSelect,
}: {
  doc: DocumentRow;
  selected: boolean;
  onSelect: () => void;
}) {
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
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" sx={{ mt: 0.25 }}>
            <Chip label={fileKindLabel(kind)} size="small" sx={{ height: 18, fontSize: 10 }} />
            {doc.category && (
              <Chip
                label={categoryLabel(doc.category)}
                size="small"
                sx={{ height: 18, fontSize: 10, bgcolor: "#F1F5F9" }}
              />
            )}
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

function FolderBlock({
  label,
  docs,
  accent,
  selectedId,
  onSelect,
}: {
  label: string;
  docs: DocumentRow[];
  accent: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Box sx={{ mb: 1 }}>
      <Box
        sx={{
          position: "sticky",
          top: 0,
          zIndex: 2,
          bgcolor: "#F8FAFC",
          borderLeft: `3px solid ${accent}`,
          px: 1.5,
          py: 0.75,
          mb: 0.5,
        }}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          <FolderOutlinedIcon sx={{ fontSize: 15, color: accent }} />
          <Typography variant="caption" fontWeight={700} color={accent} sx={{ textTransform: "capitalize" }}>
            {label}
          </Typography>
          <Chip label={String(docs.length)} size="small" sx={{ height: 16, fontSize: 10 }} />
        </Stack>
      </Box>
      {docs.map((d) => (
        <DocListItem
          key={d.document_id}
          doc={d}
          selected={selectedId === d.document_id}
          onSelect={() => onSelect(d.document_id)}
        />
      ))}
    </Box>
  );
}

const FILTER_OPTIONS = [
  { id: "all", label: "All" },
  { id: "referral", label: "Referrals" },
  { id: "letter", label: "Letters" },
  { id: "summary", label: "Summaries" },
  { id: "sbar", label: "SBARs" },
];

function matchesFilter(doc: DocumentRow, filter: string): boolean {
  if (filter === "all") return true;
  const t = doc.document_type.toLowerCase();
  const title = doc.title.toLowerCase();
  const cat = (doc.category ?? "").toLowerCase();
  if (filter === "sbar") return isSbarDocument(doc);
  if (filter === "referral") {
    return (
      t.includes("referral") ||
      title.includes("referral") ||
      cat.includes("referral") ||
      title.includes("clinical information") ||
      title.includes("2ww") ||
      title.includes("form v")
    );
  }
  if (filter === "letter") {
    if (isSbarDocument(doc)) return false;
    return (
      t.includes("letter") ||
      t.includes("clinic") ||
      t.includes("document") ||
      cat.includes("letter") ||
      Boolean(doc.text_preview?.trim().toLowerCase().startsWith("dear "))
    );
  }
  if (filter === "summary") {
    return t.includes("summary") || t.includes("discharge") || cat.includes("summary");
  }
  return true;
}

interface Props {
  patientId: string;
  scopeEpisodeIds?: string[];
  /** Pre-select a document when opening from Timeline or another tab. */
  initialDocumentId?: string;
  /** Pre-select the first document linked to this referral id. */
  initialReferralId?: string;
}

function docMatchesReferral(doc: DocumentRow, referralId: string): boolean {
  const prefix = referralId.trim();
  if (!prefix) return false;
  const docId = doc.document_id;
  return docId === prefix || docId.startsWith(`${prefix}-`);
}

export function DocumentListPanel({
  patientId,
  scopeEpisodeIds,
  initialDocumentId,
  initialReferralId,
}: Props) {
  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setSelectedId(null);
    setError(null);
    Promise.all([
      fetchEprDocuments(patientId),
      fetchEprAssessments(patientId).catch(() => []),
    ])
      .then(([rows, assessments]) => {
        const scopedDocs = scopeEpisodeIds
          ? rows.filter(
              (r) => !r.episode_id || scopeEpisodeIds.includes(r.episode_id),
            )
          : rows;
        const scopedAssessments = scopeEpisodeIds
          ? assessments.filter(
              (a) => !a.episode_id || scopeEpisodeIds.includes(a.episode_id),
            )
          : assessments;
        const merged = mergeDocumentsNewestFirst(
          scopedDocs,
          scopedAssessments,
        );
        setDocs(merged);
        setSelectedId(merged[0]?.document_id ?? null);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load documents."),
      )
      .finally(() => setLoading(false));
  }, [patientId, scopeEpisodeIds]);

  useEffect(() => {
    if (loading || docs.length === 0) return;
    if (initialDocumentId && docs.some((d) => d.document_id === initialDocumentId)) {
      setSelectedId(initialDocumentId);
      return;
    }
    if (initialReferralId) {
      const match = docs.find((d) => docMatchesReferral(d, initialReferralId));
      if (match) setSelectedId(match.document_id);
    }
  }, [loading, docs, initialDocumentId, initialReferralId]);

  const filtered = useMemo(() => {
    const base = docs.filter((d) => matchesFilter(d, filter));
    if (!search.trim()) return base;
    const q = search.toLowerCase();
    return base.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        (d.text_preview ?? "").toLowerCase().includes(q) ||
        (d.category ?? "").toLowerCase().includes(q)
    );
  }, [docs, filter, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, DocumentRow[]>();
    for (const doc of filtered) {
      const key = doc.episode_label ?? "General";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(doc);
    }
    return map;
  }, [filtered]);

  const selected = docs.find((d) => d.document_id === selectedId) ?? null;

  if (loading) {
    return (
      <Stack spacing={1.5}>
        {[1, 2, 3].map((i) => <Skeleton key={i} variant="rounded" height={80} />)}
      </Stack>
    );
  }

  if (error) return <Alert severity="error">{error}</Alert>;

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} flexWrap="wrap">
        {FILTER_OPTIONS.map((opt) => (
          <Chip
            key={opt.id}
            label={opt.label}
            onClick={() => setFilter(opt.id)}
            variant={filter === opt.id ? "filled" : "outlined"}
            color={filter === opt.id ? "primary" : "default"}
            size="small"
          />
        ))}
      </Stack>

      <Box
        sx={{
          display: "flex",
          border: "1px solid #E2E8F0",
          borderRadius: "10px",
          overflow: "hidden",
          height: "calc(100vh - 300px)",
          minHeight: 420,
        }}
      >
        <Box
          sx={{
            width: 300,
            flexShrink: 0,
            borderRight: "1px solid #E2E8F0",
            display: "flex",
            flexDirection: "column",
            bgcolor: "#FFFFFF",
          }}
        >
          <Box sx={{ p: 1.25, borderBottom: "1px solid #E2E8F0" }}>
            <TextField
              size="small"
              placeholder="Search documents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              fullWidth
              InputProps={{
                startAdornment: (
                  <DescriptionOutlinedIcon sx={{ mr: 0.5, fontSize: 16, color: "#94A3B8" }} />
                ),
              }}
            />
          </Box>
          <Box sx={{ flex: 1, overflowY: "auto" }}>
            {grouped.size === 0 ? (
              <Alert severity="info" sx={{ m: 1.25, fontSize: 12 }}>
                No documents match.
              </Alert>
            ) : (
              Array.from(grouped.entries()).map(([label, labelDocs]) => (
                <FolderBlock
                  key={label}
                  label={label}
                  docs={labelDocs}
                  accent={accentForLabel(label)}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              ))
            )}
          </Box>
        </Box>

        <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#FFFFFF" }}>
          {selected ? (
            <DocumentViewer doc={selected} patientId={patientId} />
          ) : (
            <Box sx={{ p: 4, textAlign: "center", color: "#94A3B8" }}>
              <ArticleOutlinedIcon sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="body2">Select a document to read it.</Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
